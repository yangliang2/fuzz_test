# DuckDuckGo 三层 fuzzing 路线验证方案

> 2026-08-29 grilling 会话产出。依据文档：`docs/adr/0001-oracle-and-spec-strategy.md`（oracle 策略）、`target-app-selection-mega.md`（目标选型）、`kea2-deep-dive.md`（Kea2 技术路线）、DDG 仓库一手调研（2026-08-29，`gh api` + 193 个 build.gradle 逐一审计）。
> 本文档是 20 个已决设计点的汇总，作为 W1 开工前的基线；执行中偏离本文档的决策需回写。

## 1. 目标与成功标准

- **目标**：在 DuckDuckGo Android（~90 万行，首选；Thunderbird 备选）上验证 Kea2 + Jazzer + 静态分析三层应用层 fuzzing 路线。
- **成功标准（效果口径）**：每层在时间盒内至少发现以下数量的此前未知真实问题——
  - Kea2 层 ≥ 2 个确认的功能 bug；
  - Jazzer 层 ≥ 1 个崩溃/断言违例；
  - intent fuzz 层 ≥ 1 个畸形 Intent 崩溃。
- **零发现预案（mutation testing 兜底）**：第 3 周末零发现的层，人工向 DDG 源码注入 3–5 个已知 bug 重新构建，验证该层能否检出。能检出 = 路线有效、目标太稳；检不出 = 路线本身有缺陷。由此把"运气"从成功标准中剔除。

## 2. 时间盒与里程碑

总周期 **4 周**，每周末 go/no-go 检查：

| 周 | 内容 | 硬验收点 |
|---|---|---|
| W1 | DDG `--recursive` clone + debug APK 构建；静态分析盘点产出 exported 组件 JSON | debug APK 出包（**TB 切换判定点**） |
| W2 | Jazzer harness 跑通首批模块；Kea2 链路裸跑验证；intent fuzz 首轮 | harness 出首批运行结果 |
| W3 | 10 条 property 全部进试用期（夜间跑）；oracle 第 2 层转写启动（5 个 fix commit） | **mutation testing 判定点** |
| W4 | 试用期数据收割；零发现层做 mutation testing；结题报告 | 报告含每层发现数 + 第 3 层规则规模估算 + ADR 风险条款复核 |

- Kea2 跑**夜间任务**（模拟器，`--running-minutes` 360 级）；Jazzer 无设备依赖，随时跑。
- 构建只用 debug 变体（`internalDebug`；`fdroidDebug` 被 DDG `variantFilter` 排除，不存在，2026-08-29 实测回写，详见 `docs/ddg-build-recipe.md`），**不碰 `assemblePlayRelease`/`assembleInternalRelease`**（DuckSans 专有字体校验会失败）。另：构建需 JDK 21 跑 Gradle daemon（Metro plugin 要求），本机 JDK 17 不够。
- 本机资源：16 核 / 15G RAM / 816G 空闲，JDK 17、adb、emulator、Docker 齐备；RAM 偏小，构建与模拟器不同时跑。

## 3. 三层落地顺序与范围

顺序：**静态分析（W1，纯主机任务）→ Jazzer（W1–W2）→ Kea2（W2 起，等 APK 与设备链路就绪）**。

### 3.1 静态分析层（含 intent fuzz）

- **盘点**：从**构建后 APK 的合并 manifest**（`aapt dump xmltree`）提取 exported 组件——源码审计会漏各 feature 模块的合并 manifest。输出 JSON（组件名/类型/intent-filter/exported 标志）。
- 已知核心暴露面（源码初审，以合并 manifest 为准）：
  - `IntentDispatcherActivity`：deeplink 总入口，`duck://` + 全域名 http/https BROWSABLE + SEND text/plain + NDEF；
  - `LaunchBridgeActivity`（MAIN）+ 8 个 launcher alias；`.BrowserActivity` exported 无 intent-filter（显式 Intent 可直拉）；`SystemSearchActivity`（ASSIST）；`DuckDuckGoCustomTabService`（CustomTabs）；
  - Provider/Receiver 均 exported=false。
- **intent fuzz**：自写一个 Python 脚本（不引入 Drozer/MobSF）——消费暴露面 JSON，对每个 exported 组件经 `adb shell am start/startservice/broadcast` 发 N=50 条畸形 Intent（null extras、类型错乱、超长字符串、畸形 URI、空 action）；oracle = 崩溃（logcat FATAL/进程死亡），零人工审。

### 3.2 Jazzer 层

- **物理形态**：harness 在本仓库 `harness/` 目录，引用 DDG 编译产物/源码，DDG 仓库保持原样（clone 在 `~/project/duckduckgo-android`，不进本 repo git）。
- **首批目标**（依据一手调研重排，mega 报告中 privacy grade/autoconsent 的设想已被推翻——前者是 JS submodule 无 Kotlin 实现，后者规则引擎是 JS bundle）：
  1. **remote-messaging-impl**（主目标，W2 必成）：`RemoteMessagingConfigJsonMapper.map` + `JsonRemoteMessageMapper.mapToRemoteMessage`，Moshi 解析、无 Context/Looper、防御性代码密集；
  2. **privacy-config-impl 的 feature plugin**（第二目标）：各 plugin 的 `store(featureName, jsonString)` 解析，org.json 用真实 jar；
  3. **browser-api `UriString`/`SpecialUrlDetector` + ad-click-impl URL 匹配**（第三目标，取决于 Q20 spike）：URL 字符串输入面，需解决 `android.net.Uri` 的 JVM stub 问题；
  4. TDS tracker list 解析**放弃**（代码在巨型 app 模块，构建成本不划算）；httpsupgrade BloomFilter **排除**（依赖 native 库）。
- **Robolectric × Jazzer spike**（W2，**半天时间盒**）：验证 jazzer + Robolectric shadow 共存；不通则 ③ 类目标降级为"只 fuzz 不碰 Uri 的函数子集"，不写 shim。
- harness 风格：JUnit4 + mockito-kotlin fake（DDG 测试栈事实标准；不用 MockK），绕过 Anvil/Dagger DI 直接构造类。
- oracle：首批以崩溃（未捕获异常逃逸）为主，roundtrip/differential 断言机会性补充。

### 3.3 Kea2 层

- **第一批 property：10 条 = 5 业务域 × 2，全部第 1 层通用不变量**（ADR-0001；不写导航脚本——DDG 无需登录，无深层状态引导痛点）：
  1. 书签：增删后列表计数 ±1；save→重新打开往返一致；
  2. 历史记录：访问后计数 +1；清空后为空；
  3. 标签页：开关后计数一致；
  4. Fire Button：执行后书签/历史/Cookie 三类 DB 为空（adb 查 DB 做 oracle）；
  5. 设置：设置项 save→load 往返；旋转后 UI 状态不丢。
- **试用期参数**：N=10 个夜间轮次；从未触发→淘汰；触发 ≥5 且违例率 >50% → 降级为疑似脚本 bug 待修；高触发 + 偶发违例 → 上人审。
- **解耦层**：property 主体为纯 uiautomator2 断言函数（`properties/core/`），Kea2 装饰器只做调度绑定（`properties/kea2_bindings/`）——对冲 Kea2 学术团队单点维护 + 非标准许可证风险。
- **被测环境**：新建专用 AVD（API 34、x86_64、**三键导航**（Fastbot 手势误判坑）、2G+ RAM）；暂不打 `setWebContentsDebuggingEnabled` 补丁——首批 property 全在原生 UI 层，保持零侵入起步。
- **本地 HTTP server**：用 DDG 官方 [privacy-test-pages](https://github.com/duckduckgo/privacy-test-pages)，`python3 -m http.server` 起服务，模拟器经 `10.0.2.2` 访问；tracker 测试域名（`bad.third-party.site` 等）经 adb 改模拟器 hosts 指向本机——tracker 拦截 oracle 由此获得确定性基准。HTTPS/HSTS 类页面本轮不用。

## 4. Oracle 分层在本次范围中的映射（ADR-0001 执行口径）

- **第 1 层（通用不变量）**：全量做——Kea2 的 10 条 property + intent fuzz 的"畸形 Intent 不得崩溃"。
- **第 2 层（存量资产转写）**：W3–W4 从 DDG 近期 bug fix commit 挑 5 个转写为 Kea2 property 或 Jazzer 断言，走试用期；验证"转写而非创作"论点。
- **第 3 层（AI 业务断言）**：**跳过实施**，仅在结题报告中估算 DDG 业务关键规则的大致条数，验证 ADR "几十条"假设（对应 ADR 风险条款）。

## 5. 合规、风险与处置

- **Kea2 许可证**（Revised License，仅内部使用）：本项目按纯内部研究处理，property 脚本与发现不对外分发；Fastbot 3.0 闭源二进制只跑在专用模拟器（无个人数据）。
- **bug 处置**：finding 全部进本仓库 GitHub issue（`[finding]` 前缀 + `needs-triage`，确认后转 `ready-for-human`）。上报上游门槛：可稳定复现 + 人工确认 + 非已知 issue 重复；**安全类走 HackerOne**（hackerone.com/duckduckgo，DDG 无 SECURITY.md），不走公开 issue。
- **Thunderbird 切换触发条件**（仅两类硬故障，零 bug 不构成切换理由）：① W1 末 DDG 仍出不了 debug APK（>2 人日排查无果）；② Kea2/Fastbot 在 DDG 上有特异性故障。触发后不重排时间盒，从切换点继续。

## 6. 本仓库结构

```
fuzz_test/
├── harness/         # Jazzer fuzz harness
├── properties/      # Kea2 property（core/ 纯函数 + kea2_bindings/）
├── static-analysis/ # 暴露面盘点脚本 + 输出 JSON
├── intent-fuzz/     # 畸形 Intent 发送脚本
├── test-pages/      # privacy-test-pages 本地服务脚本
└── docs/            # 现有调研文档 + 本文档
```

## 7. 环境基线（2026-08-29 核实）

adb 1.0.41、`~/Android/Sdk`（含 emulator）、JDK 17.0.20、Python 3.12.3、Docker 可用、磁盘 816G 空闲、16 核 / 15G RAM。现有 AVD `Calendar_Test` 不动，另建专用 AVD。

# Kea2 技术路线深入调研报告

> 调研日期：2026-08-28。本报告是 `android-fuzzing-research.md` 的深化篇，聚焦 Kea2（ECNU，FSE 2026）。所有关键结论均来自一手来源：Kea2 GitHub 仓库（README、源码、docs、examples，本次调研克隆了 main 分支，v1.2.4）、FSE 2026 论文 PDF（全文提取）、论文通讯作者 Ting Su 主页、GitHub API 仓库元数据。仓库本地副本路径为 `/tmp/kea2-repo`（调研用，可删）。

## 1. 概述

Kea2 是华东师大可信智能软件实验室（Ting Su 团队）开发的 Android app property-based testing（PBT）工具，FSE 2026 工具论文（5 页，FSE Companion '26, pp.182–186, DOI 10.1145/3803437.3806416）。它是团队前作 Kea（ASE 2024）的完全重写版本：Kea 使用自定义的 property 描述语言（PDL），而 Kea2 把 property 直接写成 Python（unittest 测试方法 + 装饰器），以降低工业落地门槛（来源：[论文 §1](https://tingsu.github.io/files/fse26-Kea2.pdf)）。

技术栈上，Kea2 建立在三个开源项目之上（来源：[README](https://github.com/ecnusse/Kea2)、论文 §3.1）：

- **unittest**：管理 property 脚本（测试发现、执行、结果）；
- **uiautomator2**（openatx）：设备交互驱动，property 脚本用它操作 UI；
- **Fastbot 3.0**：输入生成器（GUI fuzzing 引擎）。注意这是字节原版 Fastbot 2.0 的修改增强版，Kea2 仓库内以二进制制品形式内置（`kea2/assets/` 下的 `monkeyq.jar`、`framework.jar`、`kea2-thirdpart.jar` 与四个 ABI 的 `libfastbot_native.so`），构建来源标注为 `zhangzhao4444/Fastbot3` 仓库的 commit `177807df`（来源：`fastbot3-build.json`、`fastbot_version.json`、`kea2/fastbotManager.py:148-189`）。

它的核心价值主张正好命中我们路线中的短板：**把 GUI fuzzing 的 oracle 从"仅崩溃"扩展到人工编写的业务性质（property）**，同时保留 Fastbot 的全部崩溃发现能力，并反过来用脚本引导 Fastbot 到达深层状态。论文与 README 宣称的工业采用方包括腾讯微信（iExplorer、微信支付 UAT）、华为 DevEco Studio（HarmonyOS）、OPay（POS 机回归测试）、海尔、小米（来源：[README "Kea2's Users"](https://github.com/ecnusse/Kea2)、论文 §5、[Ting Su 主页](https://tingsu.github.io/)）。

## 2. 架构与执行模型

### 2.1 Client/Server 架构

论文 §3.4 描述 Kea2 为 client/server 架构，源码证实如下：

- **Server（宿主 PC）**：Python 进程，`kea2/keaUtils.py` 中的 `KeaTestRunner` 是主控。它通过 uiautomator2 的 HTTP 通道（设备端口 8090，adb forward）与设备端通信（`kea2/fastbotManager.py:56-67`）。
- **Client（Android 设备）**：Fastbot 以 `app_process` 方式从 adb shell 启动（`CLASSPATH=/sdcard/monkeyq.jar:... exec app_process /system/bin com.android.commands.monkey.Monkey --agent-u2 double-sarsa ...`，见 `kea2/fastbotManager.py:191-229`），监听 8090 端口，暴露 `/stepMonkey`、`/dumpHierarchy`、`/stopMonkey`、`/init`、`/logScript` 等 HTTP 端点。

### 2.2 调度策略：逐步交替，而非"Fastbot 自主跑、Kea2 打断"

这是本次调研从源码得到的最关键澄清。README 中 OPay 用户的通俗描述是"Fastbot 探索时 Kea2 持续评估触发条件，条件满足时暂停 Fastbot、执行脚本、再交还控制权"。但实际实现（`kea2/keaUtils.py:448-538`，Kea2 主测试循环）是**更彻底的逐步驱动模型**：

1. 每个迭代，server 调用 `fb.stepMonkey(...)` —— Fastbot 只执行**一个** monkey 事件并把新的 UI hierarchy XML 返回给 server（`fastbotManager.py:90-97`）。同时把当前的黑名单控件 XPath 集合随请求下发（`_monkeyStepInfo`，`keaUtils.py:573-592`）。
2. Server 拿到 XML 后，先在**静态 hierarchy** 上检查所有 `@invariant`（不变式，每步必查）。
3. 然后在同一份 XML 上用静态 checker（`U2StaticDevice`，不接触设备）评估所有 property 的 `@precondition`，得到满足前置条件的集合（`getCheckableProperties`，`keaUtils.py:594-645`）。
4. 若集合非空：采样阈值 `u ~ U(0,1)`，过滤掉 `@prob` 小于 u 的、以及已达 `@max_tries` 上限的 property，从剩余中**随机选一个**，通过 uiautomator2 代理驱动在真机上执行脚本（交互序列 I + 断言 Q）。
5. 执行过 property 的下一迭代**不再发 monkey 事件**，而是调 `/dumpHierarchy` 只取当前界面（避免丢失脚本到达的状态），然后回到步骤 2。
6. 若没有可执行的 property，下一迭代继续 `stepMonkey`。

即：**"随机探索一步 → 检查所有前置条件 → 有则执行一个 property / 无则再探索一步"** 的细粒度交替，与论文 Algorithm 1 一致。旧的 `--agent` "native 模式"（Fastbot 连续自主运行）已被废弃，源码中直接报错 "native mode is no longer supported"（`kea2/kea_launcher.py:262-263`）。

调度参数对"探索 vs 利用"的权衡：`@prob`（前置满足时执行概率，默认 1）、`@max_tries`（整场最多执行次数，默认无限，适合登录等一次性脚本）。多 property 同时可执行时是均匀随机选择，而非按 prob 加权——手册用三函数例子明确说明了语义（`docs/manual_en.md` "Decorators" 节）。

### 2.3 另外两个执行模式

- **Hybrid test（Feature 4，实验性）**：先跑普通 unittest/pytest/Appium 脚本到达深层状态（如登录后），在 `@interruptable` 断点处拉起 Fastbot+property 测试做探索。源码：`HybridTestRunner`（`keaUtils.py:809-881`）与 `kea2_breakpoint()`；示例在 `hybridtest_examples/`（u2/Appium × unittest/pytest 四种）。论文 §4 称之为 "fusing scripted testing and GUI fuzzing"。
- **WebView 交互**：通过插件 `u2_webview`（DrissionPage 语法）在 property 内操作 WebView，但要求被测 app 源码开启 `WebView.setWebContentsDebuggingEnabled(true)`（`docs/manual_en.md` Advanced Feature 4）——这是对被测 app 唯一的侵入性要求，且仅限该特性。

### 2.4 工程优化（论文 §3.4）

- **控件遮挡检测**：从 dump 的 UI 布局中排除被遮挡控件，消除 property 检查的假阳性（仓库 `tests/hidden_widget_test.xml` 等测试佐证该功能存在）。
- **前置条件缓存**：所有 property 的前置在一次 UI dump 上统一静态评估，避免每个前置都往返设备——这是"前置条件多时仍能扩展"的关键。代价是前置中复杂选择器（父子关系）不被该优化支持，手册建议改用 XPath（`docs/manual_en.md` "Tricks to enhance Kea2 performance"）。

## 3. Property 机制详解

### 3.1 形式化模型（论文 §2）

App 状态 `s = ⟨l, σ⟩`（l 为 GUI 布局，σ 为 app 内部数据）。Property 是 Hoare 三元组 `ϕ = ⟨P, I, Q⟩`：前置 P 定义何时可检查，I 是交互场景程序，Q 是后置断言。语义：`s ⊧ P ∧ s ⇝I s' ⇒ s' ⊧ Q`；P 成立但执行 I 后 Q 不成立即发现一个 property violation。

### 3.2 编写方式：Python + 装饰器，无自定义 DSL

Property 是 `unittest.TestCase` 里的测试方法，用三个装饰器标注（`kea2/keaUtils.py:46-102`）：

- `@precondition(lambda self: <bool>)`：可叠加多个；
- `@prob(p)`：0<p≤1；
- `@max_tries(n)`；
- 另有 `@invariant`（无 P/I、每步检查 Q 的不变式，`kea2/state.py:20-22`）和 `@interruptable`（hybrid 模式断点）。

方法体内是**任意 Python 代码** + uiautomator2 API；断言用普通 `assert`。可配合 hypothesis 生成随机输入（README Feature 3 示例用 `hypothesis.strategies.text` 生成随机非空字符串输入输入框）。

### 3.3 官方示例

仓库自带的 Omni Notes 示例（`properties/Omninotes_Sample.py`，旋转后搜索框应保持打开的回归性质）：

```python
@max_tries(1)
@precondition(
    lambda self: self.d(resourceId="it.feio.android.omninotes.alpha:id/search_src_text").exists
)
def test_rotation(self):
    self.d.set_orientation("l")   # 交互序列 I：旋转再转回
    sleep(2)
    self.d.set_orientation("n")
    sleep(2)
    assert self.d(resourceId="...:id/search_src_text").exists()  # 断言 Q
```

论文 Listing 1 展示的 stateful testing 示例（创建笔记 → 之后能搜到该笔记），核心是全局单例 `state`（`kea2/state.py`，一个共享 dict）跨 property 记录/查询业务数据：

```python
state["notes"] = list()

@precondition(lambda self: self.d(resourceId="create").exists)
def create_note(self):
    self.d(resourceId="create").click()
    content = generate_random_text()
    self.d(resourceId="content").set_text(content)
    state["notes"].append(content)          # 记录模型状态

@prob(0.5)
@precondition(lambda self: self.d(resourceId="search").exists
              and len(state["notes"]) > 0)
def search_note(self):
    self.d(resourceId="search").click()
    note = random.choice(state["notes"])    # 查询模型状态
    self.d(resourceId="search_box").input(note)
    self.d.press("ENTER")
    assert self.d(text=note).exists         # 功能性断言
```

### 3.4 表达能力评估

**能表达的**（综合论文 §4、手册 Advanced Features、示例代码）：

- GUI 可达状态上的任意断言：控件存在/文本/计数/页面一致性（如"输入非空时发送按钮必须出现"、"字数统计非负"）；
- **有状态性质**：CRUD 一致性、创建-搜索-删除闭环（用 `state` 建模 app 内部数据 σ）；论文评估中 40 个 property 里 15 个用了 stateful testing；
- **引导式探索**：Q 恒为 True 的 property 退化为"导航脚本"，把 Fastbot 带进深层页面（登录、隐私页等）；评估中 5 个 property 用于此；
- 方法体内是完整 Python，理论上可以断言 GUI 之外的东西（adb shell 查文件/数据库、HTTP 查后端），但官方文档未把这类用法列为支持场景；
- 随机输入生成（hypothesis）使单个 property 本身也是小型 PBT。

**表达不了 / 表达成本高的**：

- **时序/并发性质**：调度模型是串行"一步一检查"，无法表达"事件 A 必须在事件 B 的 500ms 内发生"这类实时性质；
- **反例自动最小化（shrinking）**：经典 PBT（QuickCheck/Hypothesis）的 shrink 能力在 Kea2 中没有对应物——violation 的报告粒度是"第 N 步执行的某 property 失败"，复现要靠截图/日志/报告人工回溯（`--take-screenshots`、`--pre/post-failure-screenshots` 即为此设）；
- **GUI 不可见的内部状态**只能依赖人工维护的 `state` 模型，模型与真实 app 状态可能脱节（测试本身引入的误差源）；
- 前置条件的性能约束：复杂选择器需写 XPath，否则拖慢主循环（手册明示）；
- WebView 内容默认不可见（需插件 + app 侧开 debug 开关）；
- property 编写依赖对 app 的 resourceId/文本的掌握，本质上需要源码或 uiautomatorviewer 类工具辅助逆向 UI 结构——**有源码对我们反而是优势**。

## 4. 实证结果

### 4.1 Kea2 论文（FSE 2026，§5）报告的 bug 数据

| 被测对象 | 规模 | property 数 | 测试时长 | 新发现功能 bug | 状态 |
|---|---|---|---|---|---|
| Markor（5.1K star） | 开源 | 8（8 个用 stateful） | 每 app 3 小时 | 1（Issue #2720） | 均已确认 |
| AnkiDroid（11K star） | 开源 | 7（4 stateful + 2 guided） | 同上 | 3（#20094/#20095/#20102） | 确认 |
| Amaze（6K star） | 开源 | 25（3 stateful + 1 guided） | 同上 | 4（#4558–#4561） | 确认，3 个已修复 |
| 微信（Tencent 部署） | 工业，十亿级用户 | 133（从回归测试推导） | 三个发布版本 v8.0.55–v8.0.57 | **41 个**（幽灵联系人、控件丢失、hang 等） | — |

开源部分合计：40 个 property（35 个带断言），3 个 app 各 3 小时，共 8 个此前未知的功能 bug，全部被开发者确认。典型案例：Amaze Issue #4558——"Audio" 标签页下删除文件后文件列表不自动刷新；开发者此前已在 PR#4493 修过主页面的同类 bug，Kea2 用同一 property 的不同输入抓到了遗漏分支——这是 PBT 相对 example-based 测试价值的直接体现。

微信部署的另一个架构信号：**Kea2 的 GUI fuzzing 引擎可替换**——微信场景把 Fastbot 换成了自家 iExplorer（multi-armed bandits + 随机探索），说明 server 端调度与引擎解耦（论文 §5）。

### 4.2 前作 Kea（ASE 2024）的对照实验数据

Kea2 论文本身没做与基线的对照实验（工具论文定位），但同团队 Kea 的 ASE 2024 论文（README 引用，DOI 10.1145/3691620.3694986）提供了可迁移的证据：124 个历史功能 bug（8 个流行开源 app），PDL 能表达全部 124 个性质；范围内 97 个 bug 在两种探索策略下分别找回 66（68.0%）和 92（94.8%）；另发现 25 个新 bug（全部确认、21 个已修复）；**对比基线（此前 SOTA 技术）只找回 13 个（13.4%）历史 bug 和 1 个新 bug**。这说明 PBT 路线对非崩溃功能 bug 的有效性有独立实证支撑，Kea2 是该路线的工程化继承者。

### 4.3 社区/工业反馈

- PyPI 下载 28k+、GitHub 200+ star（论文 §1，2026 年初口径；本次 GitHub API 实测 282 star / 32 fork，2026-08-27）；
- OPay 作为 POS 机默认回归测试工具；Haier 测试人员反馈"结合 unittest(PBT) 后比单用 Fastbot 更有效"；华为把 Kea2 集成进 DevEco Studio 用于自动发现**性能 bug**（论文 §5、README）。

## 5. 工程接入清单

来源：README Installation/Quick Test、`pyproject.toml`、`docs/manual_en.md`、`kea2/kea_launcher.py`。

**环境依赖**

- 宿主 OS：Windows / macOS / Linux；Python ≥ 3.8（`pyproject.toml: requires-python = ">=3.8"`）；
- pip 包：`pip install kea2-python`，传递依赖 `uiautomator2>=3.7.0`、`adbutils>=2.9.3`、`rtree>=1.3.0`、`jinja2`、`flatbuffers`、`packaging`（`pyproject.toml`）。注意 `rtree` 是原生依赖（libspatialindex），已有 CentOS 7 不兼容的 bug 报告（issue #237，2026-08-25），修复 PR #238（改用内置索引）同日提交——**在旧 Linux CI 镜像上是已知坑**；
- Android SDK / adb；设备 Android 5.0–16.0，真机或模拟器均可；
- 必须关闭 localhost 代理/VPN（否则 uiautomator2 连不上，README 明示）；
- 首次使用需 `kea2 init` 生成 `configs/`（Fastbot 配置文件、黑白名单模板、`teardown.py` 等）。

**对被测 app 的侵入性：基本为零**

- 不需要源码、不插桩、不重打包；黑盒方式经 adb 向设备推 jar（`/sdcard/*.jar`）和 so（`/data/local/tmp/*/libfastbot_native.so`），以 `app_process` 启动 Fastbot 服务（`fastbotManager.py:148-229`）；
- 唯一例外：WebView 操作特性需 app 开启 WebContentsDebugging（见 §2.3）；
- 有源码的价值体现在写 property 时容易拿到稳定的 resourceId，以及可以用 debug build。

**运行方式与输出（CI 友好度）**

- 典型命令：`kea2 run -s <serial> -p <pkg> --running-minutes 10 propertytest discover -p 'property*.py'`；`-p` 支持多包名；
- **退出码位掩码设计**（`kea_launcher.py:8-13`）：0 成功 / 1 property 违例 / 2 崩溃或 ANR / 3 两者皆有 / 4 运行错误——CI 里直接按退出码分流"逻辑 bug vs 稳定性 bug"，不需要解析报告；
- 输出：HTML 测试报告（property 覆盖、违例统计、触发 bug 的测试、activity/widget 覆盖趋势）+ `result_*.json` + Fastbot 日志；支持 `kea2 report` 重新生成、`kea2 merge` 合并多场运行（手册 "Read and Manage Kea2 test reports"）；
- 崩溃检测靠监听 Fastbot 日志（`logWatcher.py`，`result.has_crash_or_anr`），ANR 也在覆盖范围内；
- CI 接入路径：模拟器（仓库自带 `tests/run_emulators.sh` 冒烟脚本）或真机 farm + 定时任务；`--merge-fbm`（实验性）支持多设备模型聚合，面向"一台 PC 拖多台设备"的分布式跑法（手册 Experimental Feature 1）；
- 已知设备适配问题：手势导航会被 Fastbot 的滑动事件误判为返回手势，官方建议三键导航（手册 FAQ，issue #99）。

**调试复现支持**：`--take-screenshots` 每步截图、`--pre/post-failure-screenshots` 失败前后截 N 帧；报告内含 bug-triggering tests。

## 6. 局限与风险

**维护活跃度（实测，GitHub API，2026-08-27）——总体健康，但核心团队小**

- 仓库创建 2025-04-02，最近一次 push 2026-08-26；近三个月 commit 数：2026-05 46、06 18、07 36；最新 release v1.2.4（2026-07-29），2026 年内已发 10+ 个版本（含 beta），迭代节奏快；
- issue 响应快：如 issue #237（rtree 兼容性）当天即有修复 PR #238；近期 PR 多在数日内合入；
- 风险面：开发几乎全部由 ECNU 学生团队（Xixian Liang、Bo Ma、Cheng Peng 等 5 人 + 导师 Ting Su）承担，属于学术团队主导的单一来源项目；`DEVELOP.md` 开头就在招募 maintainer，说明维护压力存在。

**许可证风险（重要，易被忽略）**：`LICENSE` 是 2025-05-01 起生效的 **"Kea2 Revised License"**——非 OSI 标准许可证：禁止向第三方提供/分发软件，**仅限内部使用**（关联公司与代表你行事的承包商除外）。内部使用、内部改 derivative works 是允许的，但若计划把基于 Kea2 的测试服务对外提供、或把修改版分发到公司法律边界之外，需要法务确认。GitHub API 识别的 license 为 "Other"。

**property 编写与维护成本**

- 论文自己的数字：3 个开源 app 写了 40 个 property；微信 133 个（从既有回归测试推导——有存量测试资产时成本可摊薄）；
- property 依赖 UI 标识符（resourceId/text），app UI 改版会带来维护负担——但 Kea2 的设计论点是脚本短且只做局部导航（到达深层状态交给 Fastbot），比 Appium 全链路脚本健壮（README OPay 用户评论、论文 §1）；
- 脚本自身故障与真 bug 的区分靠报告中的 `fail`（断言失败=疑似 bug）vs `error`（脚本异常=脚本需修）两个计数（手册 "Meaning of Property Violations"）——**error 率高说明脚本脆弱**，需要人工盯。

**能力边界**

- 无代码级覆盖率反馈：报告覆盖指标是 activity/widget 级（Fastbot 模型），不是语句/分支覆盖；
- 无反例 shrink、无确定性复现机制（随机探索 + 概率调度，同一条命令两次执行路径不同）；
- 非崩溃 oracle 完全依赖人工 property 的数量与质量——不写 property 就退化为 Fastbot；
- 引擎层绑定 Fastbot 3.0 二进制（闭源 so + jar 由 Kea2 仓库分发，上游为个人账号仓库 `zhangzhao4444/Fastbot3`），引擎内部不可审计、不可自编译；微信案例证明可换引擎，但那是定制开发；
- 学术工具文档以中英混合、飞书/bilibili 外链为主，部分教程（如 Lark 案例）在飞书文档，存在链接腐烂风险。

## 7. 在整体路线中的位置

回到我们的三层目标，Kea2 与既有路线的拼合关系：

| 目标 | 主责任工具 | Kea2 的角色 |
|---|---|---|
| 崩溃类 bug | Fastbot（GUI 遍历）+ Jazzer（库级） | Kea2 **内嵌 Fastbot 3.0**，直接继承崩溃发现能力，同时把崩溃/ANR 与 property 违例分流到不同退出码；等于"用 Kea2 跑 Fastbot"而不是另起一个 Fastbot 进程 |
| 业务逻辑 bug | **Kea2（唯一主流活跃方案）** | 核心增量。property（P/I/Q + state + invariant）覆盖 CRUD 一致性、页面状态回归、跨页面数据一致性；我们的优势是有源码，resourceId 稳定、可配合 debug build |
| 组件暴露面安全 | 静态分析（manifest/导出组件/deeplink）+ 可能的 intent fuzz harness | Kea2 **基本不覆盖**：它经 UI 层触达 exported Activity 的界面行为，但对 Service/Receiver/Provider 的 intent 注入无专门能力；与静态分析互补、几乎无重叠 |

分工建议：

1. **Jazzer（离线库 fuzzing）**：解析/序列化/业务逻辑纯函数，覆盖率引导、CI 常驻、无设备依赖——与 Kea2 零重叠，先行落地。
2. **Kea2（设备端 GUI 层）**：一鱼三吃——(a) 裸跑当增强版 Fastbot 找崩溃（Feature 1）；(b) 写导航 property 做深层状态引导（Feature 2，对应 Fastbot 原生自定义事件序列难维护的痛点，README 脚注 1 引用了 Fastbot issue #209/#225/#286 佐证）；(c) 写带断言的 property + invariant 找逻辑 bug（Feature 3）。建议从 (b) 起步——把既有登录/初始化脚本改造成 guided exploration，成本最低、立刻提升崩溃探索深度；再逐步为核心业务流补断言 property。
3. **静态分析**：组件暴露面（exported 组件、deeplink、权限）独立做，Kea2 不可替代。
4. CI 形态：Kea2 需要设备/模拟器，适合夜间任务 + 模拟器 farm（或少量真机），退出码直接做质量门禁；Jazzer 走 PR 级（ClusterFuzzLite 式），两者节奏不同不必强求统一。

风险对冲：许可证（内部使用 OK，对外分发需法务）、学术团队单点维护、Fastbot3 引擎二进制闭源——三者都建议在正式采用前做一次内部评审；有条件可将 property 脚本与 Kea2 解耦编写（纯 uiautomator2 断言函数 + 薄装饰器层），以便未来迁移到自研调度器或后续替代工具。

## 8. 参考来源

**一手来源（本报告全部依据）**

1. Kea2 GitHub 仓库：https://github.com/ecnusse/Kea2 （README、LICENSE、pyproject.toml、docs/manual_en.md、properties/Omninotes_Sample.py、hybridtest_examples/、tests/；源码引用行号基于 main 分支 v1.2.4，本地调研副本 /tmp/kea2-repo）
2. Kea2 论文：Liang et al., "Kea2: Practical Property-based Testing for Mobile Apps", FSE Companion '26, pp.182–186. https://tingsu.github.io/files/fse26-Kea2.pdf （DOI 10.1145/3803437.3806416）
3. Kea（前作）论文：Xiong et al., "General and Practical Property-based Testing for Android Apps", ASE 2024, DOI 10.1145/3691620.3694986（摘要数据引自 Kea2 README 中的官方 BibTeX/摘要）
4. 通讯作者主页（团队与采用方信息交叉验证）：https://tingsu.github.io/
5. GitHub API 仓库元数据（star/fork/issue/commit/release 统计，2026-08-27 查询）：https://api.github.com/repos/ecnusse/Kea2
6. Fastbot 3.0 来源标注：Kea2 仓库 `kea2/assets/fastbot3-build.json`（上游仓库 zhangzhao4444/Fastbot3，commit 177807df）
7. Fastbot 原版：https://github.com/bytedance/Fastbot_Android （Kea2 手册配置文件说明指向其 handbook）
8. uiautomator2：https://github.com/openatx/uiautomator2

**调研中的不确定之处**

- 论文报告的微信 41 个 bug、OPay/海尔/华为采用等工业数据来自论文作者自述与 README 用户墙，无法独立核实；
- Kea（ASE 2024）的对照实验数据（68.0%/94.8% 召回、基线 13.4%）引自其论文摘要（经 Kea2 README 转载），本次未展开阅读 ASE'24 全文，细节（如两种探索策略的具体配置）未核实；
- "Fastbot 3.0 相对 2.0 的具体改动"只能从 README 的 OPay 用户评论（替换条件触发/黑名单/剪枝机制、增加断言支持等）侧面了解，Fastbot3 上游仓库本身未在本次调研中展开审计；
- issue 响应速度结论基于近 15 条 issue/PR 的抽样，样本量有限。

# Fuzzing 练手目标 App 筛选评估报告

> 调研日期：2026-08-29。评估目的：为 "Kea2（GUI 层 PBT，黑盒）+ Jazzer（库级 fuzzing，需离线构建）+ 静态分析（组件暴露面）" 技术路线挑选练手/验证用开源 Android app。
> 筛选标准（用户给定）：①充分可验证（本地 CRUD、状态可经文件系统/数据库/UI 直接观察、有存量测试、维护活跃）；②依赖条件少（标准 Gradle 出 APK、无 Firebase/私有 key/签名/服务端、无复杂 NDK；运行不需账号/联网/特殊硬件）；③规模 2 万–15 万行。
> 方法：全部结论来自一手来源——GitHub API（仓库元数据、languages、git trees、actions runs）、各仓库 README / .github/workflows / build.gradle(.kts) 原文、论文 bug issue 当前状态。代码行数为按 GitHub languages 字节数 ÷ 约 35–40 字节/行的粗略估算。

## 1. 候选对比表

| 候选 | Star | 规模（估算） | 语言/NDK | 构建依赖（secret/key/签名） | CI 状态 | 测试存量（unit / androidTest 文件数） | 运行依赖 | 活跃度（最近 push） | Kea2 论文锚点 |
|---|---|---|---|---|---|---|---|---|---|
| **Markor** | 6.0k | Java ≈1.6MB（~4–5 万行） | 纯 Java/Kotlin，README 明示无 NDK | **无任何 secret/key**；flavor Atest/Default/Gplay 均不需签名 | ✅ `make clean all`（JDK 21），2026-08-28 绿 | 20 / 0（偏弱） | 完全离线，本地文件 | 2026-08-25，issue 当日响应 | #2720 已修复关闭 |
| **Amaze FileManager** | 6.4k | Kotlin 2.1MB + Java 1.9MB（~10 万行） | **有 Rust 模块**（file_operations）+ NDK r28c | 无 firebase/key；release 签名走 signing.properties（可选，debug 不需要） | ✅ android-build.yml 2026-08-26 绿（含 Rust/NDK 安装步骤） | 186 / 15（Robolectric+Mockito，厚） | 完全离线，本地文件系统 | 2026-08-26，活跃 | #4558、#4560 已修复；**#4559、#4561 仍 open** |
| **AnkiDroid** | 11.6k | Kotlin 8MB（**~20 万行，超标**） | 纯 Kotlin/Java，无 NDK | 无 firebase/gms/secret | ✅ 单测 3 OS + 模拟器测试，2026-08-29 绿 | **410 / 46（最厚）** | 完全离线，本地 SQLite | 2026-08-29，极活跃 | #20094/#20095/#20102 全部已修复关闭 |
| **Tasks.org** | 5.5k | Kotlin 5.5MB（~13–14 万行，含 KMP 桌面代码） | 纯 Kotlin（pebble/ 的 C 是手表端，与 Android 构建无关） | ⚠️ 应用了 google-services/crashlytics 插件且 **repo 内无 google-services.json**：googleplay flavor 构建会失败；**generic flavor 无 Firebase 可正常构建**；mapbox/google key 缺省为空串 | ✅ check.yml（JDK 21）2026-08-28 绿，CI 直接跑 generic flavor 单测 | 60 / 76 | 本地清单完全离线；CalDAV 同步可选 | 2026-08-26，维护者响应快 | 无 |
| Simple Notes（SimpleMobileTools） | 0.9k | — | — | — | — | — | — | **已停更**（最后 push 2024-06，SMT 被收购） | 无 |
| Fossify Notes（SMT 继任 fork） | 0.5k | Kotlin 230KB（**~6–8 千行，太小**） | 纯 Kotlin | 无 secret（CI 构建 assembleFossDebug/Release） | ✅ 共享 workflow，绿 | **0 / 0（无测试）** | 离线 | 2026-08-25 活跃 | 无 |
| **KeePassDX** | 7.2k | Kotlin 3.2MB（~8–9 万行） | ⚠️ crypto 模块含 C/ASM（AES），CMake + NDK 25.2 构建 | 无 firebase；backup API key placeholder 有默认值 "unused" | ❌ **无 GitHub CI**（.github 下无 workflows），无法确认构建常绿 | 21 / 4（薄） | 完全离线，本地 kdbx 文件 | 2026-08-29 活跃，issue 有响应 | 无 |
| **AntennaPod** | 8.1k | Java 3.2MB（~8–9 万行），多模块 | 纯 Java/Kotlin，无 NDK | 无 firebase；free/play 两个 flavor 均在 CI 无 secret 构建（PlayDebug/PlayRelease/FreeRelease 矩阵） | ✅ checks.yml（checkstyle/lint/spotbugs + 单测，JDK 21）2026-08-28 绿 | 62 / 26 | ⚠️ 核心场景（订阅/拉取/播放播客）**依赖网络 feed**；仅本地队列/DB 操作可离线 | 2026-08-26，活跃 | 无 |

## 2. 逐项核验证据

### 2.1 Markor（gsantner/markor）—— 首选

- **构建**：CI 唯一 workflow `build-android-project.yml`，步骤为 JDK 21 (temurin) + `make clean all`（Makefile 内部调 `./gradlew` + lint + 单测 + aapt 校验）；2026-08-28 最近 5 次运行全部 success。来源：https://github.com/gsantner/markor/blob/master/.github/workflows/build-android-project.yml
- **无 secret/key**：`app/build.gradle` 全文 grep 无 firebase/gms/google-services/apikey/ndk 命中；三个 flavor（flavorAtest/flavorDefault/flavorGplay）均只设 buildConfigField，release 未配置签名（release 构建默认未签名/需自行配置，debug 无任何要求）。第三方依赖为 flexmark（markdown 解析）、opencsv、gson、EpubParser 等纯 Java 库 + 少量 jitpack 库。来源：https://github.com/gsantner/markor/blob/master/app/build.gradle
- **无 NDK、完全离线**：README 明示 "No dependency on NDK, 1 APK = all Android supported Architectures"、"The app works completely offline, no internet connection required"、"Files are stored locally in a user selectable folder"。来源：https://github.com/gsantner/markor/blob/master/README.md
- **可验证性**：纯本地文件 CRUD（笔记=文本文件，QuickNote/ToDo=固定文件），状态直接用 `adb shell` 读文件系统即可断言——天然匹配 Kea2 的 stateful property（创建→搜索→删除闭环）。论文 bug markor#2720（QuickNote 文件删除后内容未同步）已于 2026-01-17 修复关闭：https://github.com/gsantner/markor/issues/2720 —— property 思路可原样复现并作为回归。
- **测试存量**：unit test 20 个文件、androidTest 0（git tree 统计）。偏弱，但 spec 来源可由论文 property + 存量 issue 补足。
- **Jazzer 视角**：仓库含 `thirdparty/java`  vendored 源码 sourceSet，加上自身的格式转换/渲染代码（纯 Java），可抽离线 fuzz target；flexmark 虽是依赖，但 Jazzer 同样可直接 fuzz 依赖库版本。
- **活跃度**：push 2026-08-25；近 4 个 issue（#2881–#2888）均有维护者评论/关闭，当日响应。

### 2.2 Amaze FileManager（TeamAmaze/AmazeFileManager）—— 备选 1

- **构建**：CI `android-build.yml` 显示构建需 NDK r28c（nttld/setup-ndk）+ Rust stable 工具链（`file_operations/setup_rust_android.sh` 脚本化安装 Android target），JDK 17；2026-08-26 运行 success。来源：https://github.com/TeamAmaze/AmazeFileManager/blob/master/.github/workflows/android-build.yml
- **无 secret/key**：`app/build.gradle` 无 firebase/gms 命中；fdroid/play 两个 flavor 只差 `IS_VERSION_FDROID` 标志；release 签名从 `signing.properties` 读取（文件不存在则跳过），debug 构建无任何签名/key 要求。来源：https://github.com/TeamAmaze/AmazeFileManager/blob/master/app/build.gradle
- **论文锚点（独家优势）**：4 个论文 bug 中 **#4559（文件/文件夹混合排序大小不一致）与 #4561（"Audios"/"APKs" 分类页搜索失效）至今仍 open**——可直接作为待复现目标，"找到已确认但未修的 bug" 闭环成本最低；#4558（分类页删除后不刷新）、#4560（分类页重命名失效）已修复，可做回归 property。来源：https://github.com/TeamAmaze/AmazeFileManager/issues/4558 …/4559/4560/4561
- **测试存量**：unit 186 文件（Robolectric + Mockito/MockK + awaitility，含 SSH/SMB 等协议测试）、androidTest 15 文件——候选中最适合"收割存量测试为 spec"的项目之一。
- **可验证性**：文件管理器，全部状态在文件系统，oracle 极清晰。
- **代价**：Rust/NDK 工具链是硬性额外构建依赖（虽已脚本化）；file_operations 走 JNI，这部分不适于 Jazzer（但 Kotlin/Java 侧逻辑占比 99%，不受影响）。

### 2.3 AnkiDroid（ankidroid/Anki-Android）—— 重量级备选

- **构建**：无 firebase/gms 命中；CI 成熟（tests_unit.yml 在 ubuntu/macOS/Windows 三平台跑单测，tests_emulator.yml 跑模拟器测试），2026-08-29 main 绿。来源：https://github.com/ankidroid/Anki-Android/blob/main/.github/workflows/tests_unit.yml
- **测试存量最厚**：unit 410 + androidTest 46。
- **论文锚点**：#20094/#20095（新增/删除卡片类型后 UI 不更新）、#20102（Custom Study 后新卡计数不更新）三个全部已修复关闭，可做回归 property。来源：https://github.com/ankidroid/Anki-Android/issues/20094 等
- **减分项**：Kotlin 8MB ≈ 20 万行以上，**超出 15 万行上限**；模块多（libanki、api、compat 等 11 个），全量构建慢；SRS 调度领域逻辑复杂，property 设计门槛高于文件/笔记类。适合作为路线打通后的第二个验证对象。

### 2.4 Tasks.org（tasks/tasks）—— 备选 2

- **构建陷阱（重要）**：`app/build.gradle.kts` 无条件应用 `com.google.gms.google-services` 与 `firebase.crashlytics` 插件，而 repo 内**不存在** `google-services.json`（API 404 确认）→ 裸跑 `./gradlew assembleDebug` 会因 googleplay flavor 缺 json 失败；必须显式构建 **generic flavor**（`./gradlew assembleGenericDebug`）。generic flavor 无 Firebase 依赖，CI（check.yml 的 jvmTest 跑 `createGenericDebugUnitTestCoverageReport`）在无 json 环境下常绿即为此的直接证据。mapbox/google/posthog key 缺省为空字符串，不阻塞构建。来源：https://github.com/tasks/tasks/blob/main/app/build.gradle.kts、https://github.com/tasks/tasks/blob/main/.github/workflows/check.yml
- **无 NDK**：languages 中的 C 来自 `pebble/`（Pebble 手表端独立代码），与 Android app 构建无关。
- **可验证性**：本地任务清单完全离线可用（不需账号），数据在 Room/SQLite，UI/DB 双通道可观察；CRUD + 重复任务 + 标签/过滤是天然的 stateful property 场景。
- **测试存量**：unit 60 + androidTest 76（androidTest 比例为候选中最高）。
- **活跃度**：维护者 abaker 响应极快（2026-08-28 issue 当日回复/关闭）；注意 1181 个 open issue 中含大量 feature request。

### 2.5 Simple Notes / Fossify Notes —— 不推荐

- SimpleMobileTools/Simple-Notes 最后 push 2024-06-11，项目已停更（SMT 系整体被收购），不满足"维护活跃、bug 能闭环"。来源：https://github.com/SimpleMobileTools/Simple-Notes
- 社区继任 fork FossifyOrg/Notes 活跃（push 2026-08-25）且构建简单（共享 CI 构建 assembleFossDebug 无 secret），但 Kotlin 仅 230KB（约 6–8 千行）**业务逻辑太薄，且测试文件为 0**（git tree 统计），不满足"有存量测试可收割 + 有业务逻辑可测"。来源：https://github.com/FossifyOrg/Notes

### 2.6 KeePassDX（Kunzisoft/KeePassDX）—— 不推荐（本轮）

- **NDK 依赖**：`crypto` 模块含 AES 的 C/汇编实现，CMake + 固定 NDK 25.2.9519653 构建。来源：https://github.com/Kunzisoft/KeePassDX/blob/master/crypto/build.gradle.kts
- **无 CI**：`.github/` 下只有 FUNDING.yml 与 ISSUE_TEMPLATE，无任何 workflow，无法确认"最近构建常绿"。
- 测试存量薄（unit 21 / androidTest 4）。
- 优点本身其实契合（完全离线、kdbx 文件状态可观察、安全关键正确性、无 firebase），若未来想测"加密文件格式 + 自动填充"场景可作为二期目标；Jazzer 角度 kdbx 解析在 Kotlin 侧，但 NDK 构建与无 CI 增加了练手期摩擦。

### 2.7 AntennaPod（AntennaPod/AntennaPod）—— 不推荐（本轮）

- 构建与工程素质很好：无 firebase，free/play flavor 都在 CI 无 secret 构建（checks.yml 单测矩阵含 PlayDebug/PlayRelease/FreeRelease，JDK 21，2026-08-28 绿），62 unit + 26 androidTest，`parser:feed`、`parser:media` 是纯 Java 解析模块（Jazzer 理想目标）。来源：https://github.com/AntennaPod/AntennaPod/blob/develop/.github/workflows/checks.yml、https://github.com/AntennaPod/AntennaPod/blob/develop/settings.gradle
- **出局原因**：核心业务流（订阅 RSS、拉取、下载、播放）依赖网络 feed，违反"运行不需要联网后端"的硬标准；离线可测面（本地队列/DB CRUD）只是边角。GUI 层 property 的确定性难以保证。

## 3. 推荐结论

**首选：Markor**

- 完美命中三条硬标准：①本地纯文件 CRUD，状态经文件系统/UI 双通道直接可观察，oracle 零歧义；②零 secret、零 NDK、纯 Java/Kotlin、标准 Gradle 一条命令出 APK（CI 常绿佐证），运行完全离线不需账号；③约 4–5 万行，规模正好落在理想区间。
- 自带论文验证锚点（Kea2 论文 #2720，已修复 → 既可复现 property 思路又可做回归），resourceId 有源码可查，Kea2 property 编写成本低。
- Jazzer 侧有 vendored 解析/格式代码与纯 Java 依赖（flexmark、opencsv）可抽离线 target。
- 唯一短板：存量单测仅 20 个文件——"收割存量测试为 spec" 的空间小，spec 主要靠论文 property + issue 历史补齐。

**备选 1：Amaze FileManager**（与首选互补，建议作为第二目标）

- 独有优势：论文 4 个 bug 中 2 个（#4559、#4561）**至今 open**——"fuzz 找到已被确认的真 bug" 这一验证闭环几乎现成；另 2 个已修复可做回归。
- 测试存量厚（186 单测文件，Robolectric 体系），最适合验证"存量测试 → property/spec" 的收割路径；文件系统状态可观察性与 Markor 同级。
- 代价：构建需 NDK r28c + Rust 工具链（已脚本化但仍是额外依赖）；文件操作底层走 JNI，不适于 Jazzer（Kotlin/Java 侧不受影响）。

**备选 2：Tasks.org（限 generic flavor）**

- 本地任务 CRUD + Room DB 可观察，androidTest 存量最高，维护者响应极快。
- 务必注意 flavor 陷阱：只能 `assembleGenericDebug`，裸 `assembleDebug` 会因缺 google-services.json 失败。

**AnkiDroid 作为路线打通后的进阶目标**：测试/CI/维护均为候选中最强，论文 3 个 bug 全部已修复可做回归，但 ~20 万行超出规模标准、构建慢、领域复杂，不适合第一个练手对象。

**不推荐**：KeePassDX（NDK + 无 CI + 测试薄）、AntennaPod（核心场景依赖网络）、Simple-Notes（停更）/Fossify Notes（太小且无测试）。

## 4. 风险与注意事项

1. **Markor 存量测试薄**：若"收割存量测试为 spec"是路线验证的关键环节，Markor 提供不了素材——这正是把 Amaze 列为互补第二目标的原因（两者正好覆盖 Kea2 论文三个开源对象中的两个）。
2. **Amaze 的 Rust/NDK 工具链**：练手环境需预装 NDK r28c 与 Rust（CI 中有现成脚本 `file_operations/setup_rust_android.sh`）；若团队环境装 Rust 不便，可用 F-Droid/GitHub release 的预编译 APK 跑 Kea2（黑盒不需要源码构建），仅 Jazzer 环节需要源码。
3. **Tasks.org flavor 陷阱**：写构建文档/脚本时必须钉死 generic flavor，否则新环境第一次构建即失败，容易误判为"项目不可构建"。
4. **AGP/JDK 版本**：Markor（JDK 21）、Tasks（JDK 21）、Amaze（JDK 17）CI 均已验证现代工具链可构建；练手环境建议统一 JDK 17–21。
5. **论文 bug 的时效性**：Markor/AnkiDroid 的论文 bug 均已修复，复现时是"在新版本上验证 property 不再触发 + 回退旧版本验证能触发"，需按 issue 时间线 checkout 旧版 APK；Amaze #4559/#4561 在 master 上仍可直接触发（截至 2026-08-29 issue open）。
6. **代码行数为估算**：基于 GitHub languages 字节数换算，精确量级建议在克隆后用 tokei/cloc 复核（尤其 Tasks.org 的 Kotlin 字节数包含 KMP 桌面端代码，Android app 实际规模小于估算值）。
7. **KeePassDX 留作二期**：若路线后期想覆盖"加密文件格式解析（kdbx）+ 自动填充框架"场景，它是比 AnkiDroid 更贴业务的选择，届时再评估其 NDK 构建成本。

## 5. 数据来源清单

- GitHub REST API（2026-08-29 查询）：`/repos/{owner}/{repo}`（star/pushed_at/open_issues）、`/languages`（代码量）、`/git/trees/{branch}?recursive=1`（测试文件统计）、`/actions/runs` 与 `/actions/workflows/{file}/runs`（CI 状态）、`/issues/{n}`（论文 bug 状态）
- Markor：https://github.com/gsantner/markor ｜ CI https://github.com/gsantner/markor/blob/master/.github/workflows/build-android-project.yml ｜ issue #2720
- Amaze：https://github.com/TeamAmaze/AmazeFileManager ｜ CI android-build.yml ｜ app/build.gradle ｜ issues #4558–#4561
- AnkiDroid：https://github.com/ankidroid/Anki-Android ｜ tests_unit.yml / tests_emulator.yml ｜ issues #20094/#20095/#20102
- Tasks.org：https://github.com/tasks/tasks ｜ app/build.gradle.kts ｜ .github/workflows/check.yml / bundle.yml
- Fossify Notes：https://github.com/FossifyOrg/Notes ｜ Simple-Notes https://github.com/SimpleMobileTools/Simple-Notes
- KeePassDX：https://github.com/Kunzisoft/KeePassDX ｜ crypto/build.gradle.kts
- AntennaPod：https://github.com/AntennaPod/AntennaPod ｜ .github/workflows/checks.yml ｜ settings.gradle / playFlavor.gradle

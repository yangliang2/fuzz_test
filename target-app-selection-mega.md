# Fuzzing 验证目标 App 筛选评估报告（超大型档 >20 万行）

> 调研日期：2026-08-29。评估目的：在上一报告（`target-app-selection.md`，2–15 万行档，结论 Markor/Amaze/AnkiDroid）之上，再上一档评估 **>20 万行、优先 50 万行级** 的开源 Android app，为 "Kea2（GUI 层 PBT）+ Jazzer（库级 fuzzing）+ 静态分析" 技术路线挑选有参照价值的超大型验证目标。
> 硬约束（沿用用户给定）：①**依赖条件少**——构建走标准 Gradle 出 debug APK，无私有 API key/secret/签名文件，AGP/JDK 现代可构建、有 CI 且近期绿，NDK/Rust/自研工具链为重大减分项；运行不需账号登录、不需特定后端，核心场景可离线或在本地可控环境（本地 HTTP server / 本地文件）运行。②**充分可验证**——本地可观察状态（文件/DB/UI）丰富、存量测试厚、维护活跃 issue 能闭环。
> 方法：全部结论来自一手来源——GitHub API（仓库元数据、languages、git trees、actions runs）、各仓库 README / .github/workflows / build.gradle(.kts) 原文、官方构建文档。代码行数为 GitHub languages 字节数 ÷ 约 38 字节/行的粗略估算（仅统计主要语言，未含子模块外部仓库）。

## 1. 候选对比总表

| 候选 | Star | 规模（估算） | 构建：secret/key/签名 | 工具链/NDK | CI 近期状态 | 测试存量（unit / androidTest） | 运行依赖 | 活跃度（最近 push） | 初判 |
|---|---|---|---|---|---|---|---|---|---|
| **DuckDuckGo** | 4.8k | Kotlin 34.2MB（**~90 万行**） | **debug 无需任何 secret**（私有 debug 证书有 fallback；DuckSans 字体仅卡 PlayRelease/InternalRelease）；F-Droid 可复现构建 | 纯 Kotlin，无 NDK | ✅ ci.yml 与 build-fdroid-apk.yml 2026-08-29 连绿 | **1608 / 116（全候选最厚）** | 浏览器：本地 HTTP server 即可覆盖核心场景；书签/标签/历史/隐私统计全在本地 DB | 2026-08-29，merge queue 高频合并 | **完全满足** |
| **Thunderbird（K-9 Mail）** | 13.9k | Kotlin+Java 12MB（**~32 万行**） | 无任何 secret；foss/full flavor，CI 直接 `assemble` | 纯 Kotlin/Java，无 NDK | ✅ build-android.yml main 2026-08-27 绿（含单测 job） | **603 / 0** | 邮件账号：可指向本地 IMAP/SMTP（Docker 可控）；同步后本地查看离线可用 | 2026-08-27，issue 有 needinfo 机器人+人工响应 | **完全满足（需本地邮件服务器）** |
| **Element 经典版** | 3.7k | Kotlin 13.6MB（**~36 万行**） | 无任何 secret（google-services.json 已随 repo 提交，gplay/fdroid debug 均直接构建） | 无 NDK（olm 原生库经 Maven 预编译引入） | ✅ nightly APK 构建每日绿 | 416 / 151 | 需 Matrix homeserver，但 **CI 自身就用本地 Synapse 容器跑测试**——本地可控环境成立 | 2026-08-21，维护模式（Element X 为重心） | **完全满足（需本地 Synapse）** |
| **Signal** | 29.3k | Kotlin+Java 30.8MB（**~81 万行**） | 构建无 secret（含 reproducible-builds 目录；CI 的 secrets 仅用于 Gradle 缓存） | 纯 Kotlin/Java，无 NDK | ✅ Android CI main 2026-08-27 绿 | 599 / 94 | ❌ **硬约束**：必须手机号注册 + Signal 官方服务器，无本地化路径 | 2026-08-27，极活跃 | **排除（运行约束）** |
| **OsmAnd** | 5.9k | Java+Kotlin 27.5MB（**~72 万行**） | free/legacy flavor 无 secret（F-Droid 构建 OsmAnd~ 佐证）；根 buildscript 声明 gms classpath 但 app 模块未对 free flavor 应用 | legacy flavor 纯 Java；**但需 7 个 sibling 仓库 + builder.osmand.net ivy 私服**；workflow 钉 JDK 11 | ⚠️ **无自动化构建 CI**：build-debug-apk.yml 仅手动触发且零运行记录 | 31 / 1（薄） | ✅ 完全离线（离线地图），运行约束满分 | 2026-08-29，极活跃 | **部分满足（构建可复现性存疑）** |
| **Organic Maps** | 15.2k | C++ 核心 18.5MB（~49 万行）+ Android 侧 Java/Kotlin 仅 ~5.6 万行 | debug 构建无 secret | ❌ **NDK + CMake + ninja + ccache**，C++ 核心全量编译 | ✅ android-check.yaml PR 绿（含模拟器测试） | 12 / 1（Android 侧薄） | ✅ 完全离线（离线地图），运行约束满分 | 2026-08-29，极活跃 | **满足但代价大（NDK）** |
| **Firefox Android（Fenix）** | 1.8k（旧 repo） | 旧 mono-repo ~58 万行 | — | ❌ **仓库已归档**（2024-06），代码迁入 mozilla-central，mach/bootstrap 自研工具链 | — | 旧 repo 1205 / 275 | — | 已归档 | **排除（归档 + 工具链）** |
| **VLC Android** | 4.0k | Kotlin+Java 4.6MB（~12 万行，**不达标**） | 无 secret；Debug/Release 直接拉 Maven 预编译 libvlc（**无需 NDK**）；仅 Dev 模式才全量编译 | 可选 NDK | ⚠️ GitHub 无 CI（在 GitLab） | 8 / 45 | ✅ 完全离线，本地媒体文件 | 2026-07-27 | **排除（规模不达标）** |
| **Wikipedia** | 3.0k | Kotlin 5.4MB（~14 万行，**不达标**） | 无 secret（google-services.json 已提交；签名仅用于 alpha 发布 job，PR job 不签名） | 纯 Kotlin，无 NDK | ✅ PR 测试 + main 构建 2026-08-29 绿 | 66 / 86 | 内容需联网（维基 API）；收藏列表可离线阅读，账号可选 | 2026-08-29，活跃 | **排除（规模不达标）** |
| **Nextcloud** | 5.5k | Kotlin+Java 6.6MB（~17 万行，**不达标**） | 无 secret；Generic/Gplay/Huawei 三 flavor 均在 PR CI 无 secret 构建 | 纯 Kotlin/Java | ✅ unit-tests master 绿 | 65 / 160 | ❌ 必须 Nextcloud 服务端（可 Docker 自建，但非"离线/本地文件"级） | 2026-08-29，活跃 | **排除（规模不达标 + 运行依赖服务端）** |
| **Lawnchair** | 13.4k | Java+Kotlin 34.5MB（~91 万行，**但大量 vendored AOSP Launcher3/SystemUI 代码**） | 无 secret（签名步骤有 secrets 存在才执行的条件判断） | 纯 Java/Kotlin | ✅ CI 2026-08-28 绿 | **0 / 0** | 离线可用，但形态是 Launcher（被测对象即桌面本身，Kea2 驱动语义尴尬） | 2026-08-28，活跃 | **排除（零测试 + 代码含金量低）** |
| **Mihon** | 23.2k | Kotlin 3.4MB（~9 万行，**不达标**） | 无 secret（CI 直接 assembleRelease） | 纯 Kotlin | ✅ Build & Test 2026-08-28 绿 | **7 / 0（极薄）** | 本地书源可离线；在线图源需网络 | 2026-08-28，活跃 | **排除（规模 + 测试不达标）** |
| （补充）**Element X** | 2.4k | Kotlin 14.7MB（**~39 万行**） | gplay+fdroid debug 在 CI 构建；maptiler/sentry/posthog key 走 env（本地构建可缺省） | 无 NDK/Rust 工具链（matrix-rust-sdk 以预编译 AAR 引入） | ✅ build.yml develop 2026-08-28 绿 | **885 / 1** | 同 Element：本地 Synapse 可控 | 2026-08-28，极活跃（主力项目） | **完全满足（需本地 Synapse）** |

## 2. 逐候选核验证据

### 2.1 DuckDuckGo（duckduckgo/Android）—— 首选

- **规模**：Kotlin 34,151,441 字节 ≈ 90 万行（含 167 个 Gradle 子模块：tracker 拦截、autoconsent、隐私仪表盘、密码管理、同步等）。来源：https://api.github.com/repos/duckduckgo/Android/languages
- **构建无 secret（逐项排除"私有 key 陷阱"）**：
  - `app/build.gradle` 中私有 debug 证书逻辑有完整 fallback：`$HOME/jenkins_static/.../ddg_android_debug_build.properties` 文件**存在才**读取自定义签名，否则用默认 debug 签名（app/build.gradle 约 95–130 行）。来源：https://github.com/duckduckgo/Android/blob/develop/app/build.gradle
  - 专有 DuckSans 字体校验仅挂在 `assemblePlayRelease`/`assembleInternalRelease` 两个 task 上（`protectedVariants = ['PlayRelease', 'InternalRelease']`），debug 与 fdroid 构建不受限，且可 `-PuseProprietaryFont=false` 绕过。同文件 225–250 行。
  - CI 的 `build-debug-apk.yaml` 虽注入 DEBUG_PROPERTIES/DEBUG_KEY/MALICIOUS_SITE_PROTECTION_AUTH_TOKEN 等 secret，但那是 DDG 内部证书对齐需要；`build-fdroid-apk.yml` 与 F-Droid 官方可复现构建（[F-Droid 页面标注 "Reproducible build"](https://f-droid.org/packages/com.duckduckgo.mobile.android/)）证明 release 构建同样不依赖私有材料。来源：https://github.com/duckduckgo/Android/blob/develop/.github/workflows/build-fdroid-apk.yml
  - 注意：clone 必须 `--recursive`（content-scope-scripts 等子模块），README 明示。来源：https://github.com/duckduckgo/Android/blob/develop/README.md
- **CI**：ci.yml（spotless + 单测矩阵 AnvilDagger/Metro）与 build-fdroid-apk.yml 在 develop 上 2026-08-28/29 连续 success；项目用 merge queue，合并频率高。来源：https://github.com/duckduckgo/Android/actions/workflows/ci.yml
- **测试存量**：unit 1608 文件 + androidTest 116 文件（git tree 统计）——本报告全部候选中最厚，"收割存量测试为 spec" 空间最大。
- **运行依赖**：浏览器核心场景（打开页面、书签、标签、历史、下载、Fire Button 清数据、隐私仪表盘统计）全部可指向本地 HTTP server 或纯本地操作；tracker 拦截/HTTPS 升级等网络层逻辑对本地 server 同样生效。本地可观察状态丰富（书签/历史/标签/隐私统计多个 DB + WebView UI）。
- **Jazzer 视角**：大量纯 Kotlin 离线模块（tracker list 解析、URL/域名处理、autoconsent 规则、privacy grade 计算）是天然 fuzz target，不需要 WebView 环境。
- **活跃度**：push 2026-08-29；167 open issues，维护团队全职。

### 2.2 Thunderbird for Android（thunderbird/thunderbird-android，原 K-9 Mail）—— 备选 1

- **规模**：Kotlin 9.9MB + Java 2.1MB ≈ 32 万行（app-k9mail / app-thunderbird / app-common 多模块）。
- **构建**：CI `build-android.yml` 无 secret 直接 `./gradlew :app-k9mail:assemble` / `:app-thunderbird:assemble`（JDK 现代、ubuntu-latest），另有 `testsOnCi` 单测 job 与 lint/spotless/detekt 质量 job；main 2026-08-27 success。来源：https://github.com/thunderbird/thunderbird-android/blob/main/.github/workflows/build-android.yml
- **无 secret**：app-k9mail/build.gradle.kts 与根 build.gradle.kts grep 无 firebase/gms/google-services/apikey 命中；foss/full flavor 仅差 Google Play  funding 依赖。来源：https://github.com/thunderbird/thunderbird-android/blob/main/app-thunderbird/build.gradle.kts
- **测试存量**：unit 603 文件（极厚）；androidTest 0——GUI 层 spec 只能靠单测与手工 property。
- **运行依赖**：核心场景（收发、同步、文件夹管理）需要邮件账号，但可全部指向本地可控 IMAP/SMTP（Docker 跑 Dovecot/GreenMail）；账号配置完成后本地缓存查看离线可用。**MIME/邮件解析是教科书级 fuzz 目标**（Jazzer 对解析层、Kea2 对文件夹/消息列表 CRUD）。
- **活跃度**：push 2026-08-27；1044 open issues，有 needinfo 机器人 + 团队响应；Mozilla/Thunderbird 全职团队。

### 2.3 Element 经典版（element-hq/element-android）—— 备选 2

- **规模**：Kotlin 13.6MB ≈ 36 万行。注意与 Element X（element-x-android）区分：经典版是维护中的老架构，Matrix SDK 在 app 内；Element X 走 matrix-rust-sdk。
- **构建**：CI `build.yml` 无 secret 直接 `./gradlew assembleGplayDebug` / `assembleFdroidDebug`（JDK 21）；release 构建也未签名上传（unsigned）。google-services.json 已随 repo 提交（gplay flavor）。来源：https://github.com/element-hq/element-android/blob/develop/.github/workflows/build.yml
- **无 NDK**：languages 无任何 C/C++/Rust；olm 加密库以 Maven 预编译 AAR 引入。
- **运行依赖**：需要 Matrix homeserver——但 tests.yml 里官方 CI 用 `michaelkaye/setup-matrix-synapse` 在 runner 本地起 Synapse 跑测试，证明"本地可控服务端"路径成熟可复用。来源：https://github.com/element-hq/element-android/blob/develop/.github/workflows/tests.yml
- **测试存量**：unit 416 + androidTest 151（含截图测试）。
- **减分项**：项目处于维护模式（公司重心在 Element X），issue 2210 个 open，非安全类 bug 闭环速度存疑；E2EE 场景 property 设计门槛高。

### 2.4 Signal（signalapp/Signal-Android）—— 排除（运行约束）

- 构建面几乎完美：无 app 级 secret（CI 的 secrets 仅用于 Gradle 构建缓存与加密 key），repo 内含 `reproducible-builds/` 目录，Android CI main 2026-08-27 绿，GIPHY_API_KEY 等 buildConfigField 均为硬编码公开值；firebase-messaging 依赖排除了 analytics 组件，未应用 google-services 插件。来源：https://github.com/signalapp/Signal-Android/blob/main/.github/workflows/android.yml、https://github.com/signalapp/Signal-Android/blob/main/app/build.gradle.kts
- 规模 ~81 万行、测试 599+94、活跃度均为顶级。
- **出局原因**：核心场景（注册、发消息）强制手机号 + Signal 官方服务器，无自托管/离线路径——直接违反"运行不需账号、不需特定后端"硬约束，且无法像 Synapse/Dovecot 那样本地化。

### 2.5 OsmAnd（osmandapp/OsmAnd）—— 部分满足（构建可复现性存疑）

- **规模**：Java 23.5MB + Kotlin 4MB ≈ 72 万行，Java -heavy 老项目。
- **运行依赖满分**：完全离线地图应用，本地文件（OBF 地图、轨迹、收藏）状态极丰富——单看运行时是最理想的 Kea2 对象。
- **构建问题（一手核验后发现与"常识"不符）**：
  - repo 内唯一的构建 workflow `build-debug-apk.yml` 是 **workflow_dispatch 手动触发且零运行记录**（API 查询无 runs）——没有"CI 近期绿"的证据。来源：https://github.com/osmandapp/OsmAnd/actions/workflows/build-debug-apk.yml
  - 该 workflow 需 checkout **7 个 sibling 仓库**（OsmAnd-resources/core/core-legacy/build/tools/misc）到固定相对路径，且钉 JDK 11（而根 build.gradle 用 AGP 8.7.3，按 AGP 要求应需 JDK 17——文档/脚本可能滞后，存在踩坑面）。来源：https://github.com/osmandapp/OsmAnd/blob/master/.github/workflows/build-debug-apk.yml
  - 根 build.gradle 引入 builder.osmand.net ivy 私服作为依赖源；gms google-services classpath 在 buildscript 中声明（free/legacy flavor 未应用，app 模块 build.gradle grep 无命中）。来源：https://github.com/osmandapp/OsmAnd/blob/master/build.gradle
  - 可构建性的旁证：F-Droid 持续构建 OsmAnd~（free flavor），且 CI 目标 `assembleNightlyFreeLegacyFatDebug` 的 "Legacy" 变体走纯 Java 渲染器、避开 OsmAnd-core C++。
- **测试存量薄**：unit 31 / androidTest 1。
- **结论**：运行与规模完美，但"标准 Gradle 一条命令出 APK"不成立（sibling 仓库布局 + 私服 + 无自动 CI 背书），归为"满足但有大代价"，建议仅在 DDG/TB 路线走通后作为离线地图场景专项目标。

### 2.6 Organic Maps（organicmaps/organicmaps）—— 满足但代价大（NDK）

- **运行依赖满分**：与 OsmAnd 同为完全离线地图。
- **构建代价**：android-check.yaml 显示构建需安装 ninja-build、配置 ccache、CMake 全量编译 C++ 核心（18.5MB C++ ≈ 49 万行）；debug 构建本身无 secret，`./gradlew -Parm64 assembleWebDebug/FdroidDebug` 一条命令可出 APK（CI 在标准 runner 上完成，含模拟器测试），但首次全量编译时间长、磁盘占用大。来源：https://github.com/organicmaps/organicmaps/blob/master/.github/workflows/android-check.yaml
- **Android 侧代码薄**：app 壳 Java/Kotlin 仅 ~5.6 万行；Jazzer 无用武之地（核心逻辑全在 C++，Jazzer 不覆盖 native），Kea2 只能 fuzz UI 壳。测试 unit 12 / androidTest 1（Android 侧）。
- **结论**：若目标只是"超大型 + 离线"的 Kea2 对象它合格；但对"Kea2+Jazzer+静态分析"三线并行的路线，C++ 核心是盲区，性价比低。

### 2.7 Firefox Android（mozilla-mobile/firefox-android）—— 排除（归档 + 工具链）

- repo README 顶部明示：2024-06-17 起归档，Fenix/Focus/android-components 全部迁入 Mozilla Central，贡献文档转至 firefox-source-docs.mozilla.org。来源：https://github.com/mozilla-mobile/firefox-android/blob/main/README.md
- 迁入后构建走 Mozilla 自研 mach/bootstrap 工具链（类比 Chromium depot_tools 的成本级别），完全脱离"标准 Gradle 出 APK"约束。直接排除，无需进一步评估。

### 2.8 VLC Android（videolan/vlc-android）—— 排除（规模不达标）

- **"常识"被推翻**：README 明示 `Release`/`Debug` 构建模式直接从 Maven 拉预编译 LibVLC/Medialibrary，**应用层构建不需要 NDK**；只有 `Dev` 模式才全量编译 VLC 原生栈（那才是真正的重工具链：automake/ant/cmake/protobuf/ragel + NDK）。来源：https://github.com/videolan/vlc-android/blob/master/README.md
- 但 Kotlin+Java 仅 4.6MB ≈ 12 万行，不达 >20 万行门槛；GitHub 无 CI（官方 CI 在 code.videolan.org GitLab）；测试 8/45。运行面（完全离线、本地媒体库 DB）本来很好——若未来放宽规模可作候补。

### 2.9 Wikipedia（wikimedia/apps-android-wikipedia）—— 排除（规模不达标）

- 工程素质好：PR workflow 无 secret 跑 `ktlint assembleAlphaRelease lintAlphaRelease testAlphaDebugUnitTest`（签名 secret 仅用于 main 分支 alpha 发布 job），google-services.json 已提交，2026-08-29 绿。来源：https://github.com/wikimedia/apps-android-wikipedia/blob/main/.github/workflows/android_pr.yml
- 但 Kotlin 5.4MB ≈ 14 万行，不达标；核心内容场景依赖维基 API 网络（收藏列表可离线阅读）。

### 2.10 Nextcloud Android（nextcloud/android）—— 排除（规模不达标 + 运行依赖服务端）

- 构建面好：assembleFlavors.yml 对 Generic/Gplay/Huawei 三 flavor 无 secret 构建，unit-tests master 绿。来源：https://github.com/nextcloud/android/blob/master/.github/workflows/assembleFlavors.yml
- 但 ~17 万行不达门槛，且 app 无账号/无 Nextcloud 服务端完全不可用（可 Docker 自建，但属于"特定后端服务器"）。

### 2.11 Lawnchair（LawnchairLauncher/lawnchair）—— 排除（零测试 + 代码含金量低）

- 估算 ~91 万行是候选中最大，但 Java/Kotlin 大头是 vendored 的 AOSP Launcher3/Quickstep 代码（fork 自系统源码），业务增量有限；**测试文件 0/0**（git tree 统计），"收割存量测试为 spec"无从谈起。
- 形态问题：被测对象是 Launcher（桌面本身），Kea2 以"目标 app"驱动 GUI 的语义在 Launcher 上不成立（应用切换/回到桌面即进入被测对象），property 设计会很别扭。
- 构建本身倒是无 secret 且 CI 绿（签名步骤有 `if: secrets 存在` 条件分支）。来源：https://github.com/LawnchairLauncher/lawnchair/blob/16-dev/.github/workflows/ci.yml

### 2.12 Mihon（mihonapp/mihon）—— 排除（规模 + 测试不达标）

- Kotlin 3.4MB ≈ 9 万行，不达门槛（Tachiyomi 系"大项目"的直觉不成立——大量功能在扩展插件仓库，不在主 repo）；测试仅 7 个 unit 文件。
- 构建无 secret（CI `assembleRelease -Pinclude-telemetry -Penable-updater` 直接出包，2026-08-28 绿）；本地书源可离线。来源：https://github.com/mihonapp/mihon/blob/main/.github/workflows/build.yml

### 2.13 （补充）Element X（element-hq/element-x-android）

- 评估 Element 经典版时发现其公司已把重心移至 Element X，顺手核验：Kotlin 14.7MB ≈ 39 万行；build.yml 无文件型 secret 直接构建 `:app:assembleGplayDebug app:assembleFDroidDebug`（maptiler/sentry/posthog 均走环境变量，本地构建可缺省）；**无 Rust 工具链**——matrix-rust-sdk 以预编译 AAR 依赖引入（languages 无 Rust）；unit 885 个文件；develop 2026-08-28 绿，极活跃。来源：https://github.com/element-hq/element-x-android/blob/develop/.github/workflows/build.yml
- 定位：若选 Matrix 系做目标，Element X 比经典版更有"参照价值"（现役主力、架构现代 Compose），缺点是 androidTest 仅 1 个、项目迭代快 API 面变动频繁。

## 3. 分层结论

**完全满足三约束（构建无 secret + 运行可本地化 + 规模/测试/维护达标）**

| 层级 | 候选 | 规模 | 测试 | 备注 |
|---|---|---|---|---|
| 首选 | **DuckDuckGo** | ~90 万行 | 1608+116 | 唯一"50 万行级 + 零 secret + 离线/本地 server + 超厚测试"四项全满 |
| 备选 1 | **Thunderbird（K-9）** | ~32 万行 | 603+0 | 需本地 IMAP/SMTP（Docker），MIME 解析是 Jazzer 理想目标 |
| 备选 2 | **Element 经典版**（或 **Element X**，~39 万行、885+1） | ~36 万行 | 416+151 | 需本地 Synapse（官方 CI 已示范）；X 更现代但迭代快 |

**满足但有大代价**

- **OsmAnd**（~72 万行，运行满分）：无自动构建 CI、需 7 个 sibling 仓库 + ivy 私服、测试薄——构建可复现性是最大问号。
- **Organic Maps**（C++ 核心 ~49 万行）：NDK/CMake 全量编译，且核心逻辑在 native 层，Jazzer 覆盖不到，Android 壳太薄。

**明确排除**

- **Signal**：构建/规模/测试全优，但运行硬约束（手机号 + 官方服务器，无法本地化）不可绕。
- **Firefox Android**：GitHub repo 已归档，迁入 mozilla-central 后走 mach/bootstrap 自研工具链。
- **Lawnchair**：测试 0/0，体量大头是 vendored AOSP 代码，Launcher 形态不适于 Kea2。
- **VLC / Wikipedia / Nextcloud / Mihon**：规模不达 >20 万行门槛（Nextcloud 另需自建服务端）；其中 VLC（12 万行、离线、应用层免 NDK）与 Wikipedia（14 万行、工程素质好）是规模门槛放宽后的第一候补。

## 4. 推荐

**首选：DuckDuckGo（duckduckgo/Android）**

参照价值所在：
- 本档唯一同时命中"~90 万行超大型 + 构建零 secret（F-Droid 可复现构建背书）+ 核心场景本地 HTTP server 可控 + 1608 个存量单测"四个条件的候选；与上一档推荐（Markor 4 万行 / Amaze 10 万行 / AnkiDroid 20 万行）形成 5→10→20→90 万行的完整规模梯度。
- 三条技术线都有落点：Kea2 可围绕书签/标签/历史/Fire Button/隐私仪表盘写 stateful property（本地 DB + UI 双通道 oracle）；Jazzer 有大量纯 Kotlin 解析/规则模块（tracker list、autoconsent、URL 处理）；静态分析有 167 个子模块的组件暴露面。
- 浏览器形态天然提供"输入不可信"的攻击面叙事，fuzzing 动机比工具类 app 更强。

**备选：Thunderbird（K-9 Mail）**——若希望 Jazzer 环节更有戏（MIME/邮件解析是经典 fuzz 目标，历史上漏洞密集），且能接受 Docker 起本地 IMAP/SMTP 的一次性环境成本。**Element 经典版 / Element X**——若想要"本地服务端 + 富状态同步"场景，官方 CI 已给出本地 Synapse 的成熟模式。

## 5. 风险与注意事项

1. **DDG 的两个构建注意点**：clone 必须 `--recursive`（子模块含 content-scope-scripts，缺失会构建失败）；勿裸跑 `assemblePlayRelease`/`assembleInternalRelease`（会触发 DuckSans 专有字体校验而失败），debug/fdroid 变体无此问题。DDG 子模块多、Gradle 配置重，首次全量构建与单测耗时以小时计，练手环境需备好磁盘与内存。
2. **DDG 运行面的边界**：WebView 渲染本身依赖设备/模拟器的 WebView 实现，Kea2 驱动 WebView 内部页面元素的能力有限——property 应主要写在原生 UI 层（书签/标签/设置/隐私仪表盘），页面内容交互靠本地 HTTP server 返回固定页面保证确定性。
3. **Thunderbird/Element 的"本地服务端"成本**：虽然满足"本地可控环境"字面约束，但 Dovecot/Synapse 的 Docker 化是一次性环境工程，且账号配置要在 Kea2 探索前脚本化（可用其 androidTest/CI 中的已有模式复用）。Element 经典版处于维护模式，报 bug 的闭环预期应调低（或以 Element X 替代，承担其快速迭代的 API 漂移）。
4. **OsmAnd 的构建证据缺口**：无自动 CI 背书，文档（钉 JDK 11）与 AGP 8.7.3 的要求（JDK 17）存在表面矛盾，实际首次构建很可能要踩坑；若选用，先用 F-Droid 的构建配方（free flavor）作为基线。
5. **代码行数口径**：均为 GitHub languages 字节数 ÷38 的估算；mono-repo/ vendored 代码会显著虚高（Lawnchair 最典型，firefox-android 旧 repo 含 Fenix+Focus+android-components 三个项目）。精确规模建议克隆后以 tokei/cloc 按模块复核，尤其 DDG 的 90 万行含代码生成与多模块样板。
6. **CI "action_required" 不等于红**：Signal/Thunderbird/Lawnchair 部分 fork PR 的 run 显示 action_required（等待维护者批准），判断绿红时应以 main/develop 分支的 run 为准（本报告已按此口径）。

## 6. 数据来源清单

- GitHub REST API（2026-08-29 查询，`gh` 认证）：`/repos/{owner}/{repo}`（star/pushed_at/open_issues/default_branch/archived）、`/languages`（代码量）、`/git/trees/{branch}?recursive=1`（测试文件统计，全部未截断）、`/actions/runs` 与 `/actions/workflows/{file}/runs`（CI 状态）
- DuckDuckGo：https://github.com/duckduckgo/Android ｜ app/build.gradle ｜ .github/workflows/ci.yml / build-debug-apk.yaml / build-fdroid-apk.yml ｜ README.md ｜ F-Droid https://f-droid.org/packages/com.duckduckgo.mobile.android/
- Thunderbird：https://github.com/thunderbird/thunderbird-android ｜ .github/workflows/build-android.yml / quality-checks.yml ｜ app-k9mail/build.gradle.kts / app-thunderbird/build.gradle.kts
- Element 经典版：https://github.com/element-hq/element-android ｜ .github/workflows/build.yml / tests.yml（本地 Synapse）
- Element X：https://github.com/element-hq/element-x-android ｜ .github/workflows/build.yml
- Signal：https://github.com/signalapp/Signal-Android ｜ .github/workflows/android.yml ｜ app/build.gradle.kts ｜ reproducible-builds/
- OsmAnd：https://github.com/osmandapp/Osmand ｜ .github/workflows/build-debug-apk.yml ｜ build.gradle / OsmAnd/build.gradle ｜ F-Droid OsmAnd~ https://f-droid.org/packages/net.osmand.plus/
- Organic Maps：https://github.com/organicmaps/organicmaps ｜ .github/workflows/android-check.yaml / android-sdk.yaml
- Firefox Android：https://github.com/mozilla-mobile/firefox-android ｜ README.md（归档公告）
- VLC：https://github.com/videolan/vlc-android ｜ README.md（Build 章节）
- Wikipedia：https://github.com/wikimedia/apps-android-wikipedia ｜ .github/workflows/android.yml / android_pr.yml
- Nextcloud：https://github.com/nextcloud/android ｜ .github/workflows/check.yml / assembleFlavors.yml / unit-tests.yml
- Lawnchair：https://github.com/LawnchairLauncher/lawnchair ｜ .github/workflows/ci.yml
- Mihon：https://github.com/mihonapp/mihon ｜ .github/workflows/build.yml

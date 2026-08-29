# DDG Android debug APK 构建配方

> 2026-08-29 验证通过（issue #2）。基线 commit：`85df593e228606710d54e153aeb2031047542905`（2026-08-29，`develop` 分支 HEAD）。产物：`app/build/outputs/apk/internal/debug/duckduckgo-5.294.0-internal-debug.apk`（205MB，`com.duckduckgo.mobile.android.debug`，versionName 5.294.0，minSdk 28 / targetSdk 36）。

## 环境需求

- OS：Linux（本机 Ubuntu 24.04 x86_64 验证）。
- 磁盘：约 10G——clone 后 526M，构建后仓库 3.1G（含 node_modules 与 build 产物），Gradle 缓存 6.5G，JDK 21 约 350M。
- 内存：15G 机器实测可行。`gradle.properties` 默认 `-Xmx6g` + `org.gradle.parallel=true`，构建期间不要同时跑模拟器。
- Node.js + npm：v24.7.0 / 11.5.1 验证通过（JS 资产是构建输入，见下）。
- Android SDK：`ANDROID_HOME` 指向本机 SDK，含 platform `android-36`、build-tools（aapt 等）；licenses 需接受（`yes | sdkmanager --licenses`）。
- JDK：**构建必须用 JDK 21 跑 Gradle daemon**（Metro gradle plugin 要求 JVM runtime ≥ 21）；系统默认 java 17 会在配置阶段失败。Kotlin 代码本身 target 17。

## 构建步骤

```bash
# 1. clone（必须 --recursive；在 fuzz_test 仓库之外）
git clone --recursive https://github.com/duckduckgo/Android.git ~/project/duckduckgo-android

# 2. 安装 JS 资产（app/build.gradle 的 sourceSets 直接引用 node_modules 下的
#    @duckduckgo/autofill/dist、privacy-dashboard/build/app、content-scope-scripts/build/android/pages）
cd ~/project/duckduckgo-android
npm install

# 3. 准备 JDK 21（如系统已有 JDK 21 可跳过）
mkdir -p ~/project/toolchains && cd ~/project/toolchains
curl -sSL -o jdk21.tar.gz "https://api.adoptium.net/v3/binary/latest/21/ga/linux/x64/jdk/hotspot/normal/eclipse"
tar xzf jdk21.tar.gz && mv jdk-21* jdk-21 && rm jdk21.tar.gz

# 4. 构建 internal debug 变体
cd ~/project/duckduckgo-android
JAVA_HOME=~/project/toolchains/jdk-21 ./gradlew assembleInternalDebug
```

产物：`app/build/outputs/apk/internal/debug/duckduckgo-<version>-internal-debug.apk`。

## 变体选择

- flavor 维度 `store`：`internal` / `fdroid` / `play` × build type `debug` / `release`。
- **`fdroidDebug` 不存在**：`app/build.gradle` 的 `variantFilter` 显式排除了它。可用的 debug 变体是 `internalDebug` 和 `playDebug`，选 `internalDebug`（DDG 内部渠道、默认可调试配置）。
- **不要碰 release 变体**（`assemblePlayRelease` / `assembleInternalRelease`）：DuckSans 专有字体 AAR 托管在 GitHub Packages，需要 `ducksans.gpr.user/key` 凭证。无凭证时 debug 构建自动回落到占位字体（零配置可用），release 路径无此保障。

## 耗时参考（本机实测）

- 冷构建（含全部依赖下载，~6.5G Gradle 缓存）：约 45–60 分钟。
- 依赖缓存就绪后的全量编译：13m37s（3755 tasks，2099 命中缓存）。

## 已知坑

1. **Gradle wrapper 下载超时**：`gradle/wrapper/gradle-wrapper.properties` 里 `networkTimeout=10000`，慢网络下下载 130M 的 gradle-8.14.4-bin.zip 必超时。解法：手工 `curl -C -` 续传到 `~/.gradle/wrapper/dists/gradle-8.14.4-bin/<hash>/gradle-8.14.4-bin.zip`，按 wrapper properties 里的 `distributionSha256Sum` 校验后再跑 `./gradlew`（wrapper 校验通过会自动解压）。
2. **JDK 17 跑 daemon 报 Metro 错**：`dev.zacsweers.metro:gradle-plugin` 要求 JVM runtime ≥ 21，错误出现在根项目配置阶段（`Could not resolve all artifacts for configuration 'classpath'`）。必须 `JAVA_HOME` 指到 JDK 21。
3. **content-scope-scripts 不是 git 子模块**：`--recursive` 只拉两个子模块（`httpsupgrade-impl/src/main/cpp/bloom_cpp`、`submodules/privacy-grade`）；content-scope-scripts / autofill / privacy-dashboard 都是 npm 依赖，`npm install` 不可省。
4. **Develocity 插件**：`settings.gradle` 挂了 DDG 的 Develocity server，未认证时只影响 build scan 上传，不影响构建。
5. DDG 仓库全程保持原样：构建产生的 `node_modules/`、`build/` 均被其 `.gitignore` 覆盖，`git status` 干净；harness 代码不落 DDG 仓库。

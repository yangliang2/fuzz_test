# 针对 Android 应用的模糊测试（Fuzzing）能力调研

> 调研日期：2026-08-28。本文所有关键结论均标注一手来源（官方文档、源码仓库、AOSP、工具官方 GitHub/文档、原始论文）；未采用二手博客转述。部分一手来源（Google 官方博客、工具官方仓库的 README）本身是对官方实践的陈述，已在文中注明其性质。

## 1. 概述

Android 是一个多层栈系统，"fuzzing Android 应用"实际上对应多个截然不同的技术问题，工具成熟度差异极大：

- **Native 层（C/C++ 库、media codec、协议解析器）**：最成熟。AOSP 构建系统原生集成 LLVM libFuzzer（`cc_fuzz`），配合 ASan/HWASan/UBSan 做内存错误检测，Android 依赖的大量开源库（libvpx、libwebp、skia 依赖等）已在 OSS-Fuzz 中长期持续 fuzz。
- **内核/驱动层**：成熟但门槛高。syzkaller 官方支持 Android 设备与 Cuttlefish 虚拟设备，syzbot 持续覆盖 Android Common Kernel（ACK）。Binder 内核驱动这类强状态目标则需要定制 harness（Google 2025 年公开了基于 LKL 的方案）。
- **Binder IPC / 系统服务层**：半成熟。学术界有 FANS（USENIX Security 2020）、Chizpurfle（ISSRE 2017）、BinderCracker（AsiaCCS 2016）等灰盒/接口感知工具，开源工程有 BinderFuzzy，但均需要针对目标做适配，没有开箱即用的官方方案。
- **Java/Kotlin 应用层**：分两种情况。脱离设备 fuzz Java 库代码（字节码插桩、JVM 上运行）由 Jazzer 覆盖，很成熟；但 Jazzer 官方不支持 Android runtime（ART），在应用进程内做覆盖率引导 fuzzing 仍属研究/定制领域（如 Chizpurfle 的动态二进制插桩、ittiam 的 android_jazzer fork 用于 fuzz AOSP framework Java 代码）。
- **GUI / Intent / 组件间交互层**：可用但 oracle 弱。从官方 Monkey 到 model-based 的 APE（ICSE 2019）、ComboDroid（ICSE 2020）、Fastbot（字节跳动开源）、Kea2（property-based，FSE 2026），再到 2023 年以来的 LLM/VLM 驱动探索（GPTDroid、LLMDroid、VLM-Fuzz 等），这一代工具主要发现崩溃类问题，对非崩溃的功能性 bug 依赖人工编写 property 或差分测试。
- **Intent fuzzing**：经典工作是 2014 年的 Intent Fuzzer（Sasnauskas & Regehr），近年没有显著的工具演进，多数能力被并入 GUI 测试工具或 AOSP 的组件测试。

## 2. 分层能力矩阵

| 层次 | 典型攻击面 | 工具成熟度 | 代表工具/方案 | 反馈/插桩方式 | 关键来源 |
|---|---|---|---|---|---|
| Native 库 / codec / 协议解析 | libvpx、libwebp、libheif、libexif、media framework、NFC/BT 栈 | **高** | AOSP `cc_fuzz` + libFuzzer；OSS-Fuzz | SanitizerCoverage（编译期）、ASan/HWASan/UBSan | [AOSP libFuzzer 文档](https://source.android.com/docs/security/test/libfuzzer) |
| Linux 内核 / 驱动 | syscall、Binder 驱动、vendor 驱动 | **高（syscall）/ 中（状态型驱动）** | syzkaller + syzbot；LKL Binder fuzzer | KCOV；LKL 用户态内核 + libprotobuf-mutator | [syzkaller Android 文档](https://github.com/google/syzkaller/blob/master/docs/linux/setup_linux-host_android-device_arm-kernel.md)、[Android OffSec: Binder Fuzzing](https://androidoffsec.withgoogle.com/posts/binder-fuzzing/) |
| Binder IPC / 系统服务 | system_server 服务、native system services、vendor 定制服务 | **中** | FANS、Chizpurfle、BinderCracker、BinderFuzzy | 接口模型抽取 + 灰盒（动态二进制插桩）/ 黑盒 | [FANS (USENIX Sec'20)](https://www.usenix.org/conference/usenixsecurity20/presentation/liu)、[fantastic_beasts (Chizpurfle)](https://github.com/dessertlab/fantastic_beasts)、[BinderFuzzy](https://github.com/ChickenHook/BinderFuzzy) |
| HAL | HIDL/AIDL HAL 实现 | **中低** | AOSP VTS、定制 `cc_fuzz` harness | 编译期插桩，需自写 harness | [AOSP Security testing](https://source.android.com/docs/security/test/fuzz-sanitize) |
| Java/Kotlin 库代码（离设备） | 解析、序列化、业务逻辑库 | **高** | Jazzer（+ JUnit 5 / cifuzz / OSS-Fuzz） | JVM 字节码插桩（JaCoCo 式 edge coverage） | [Jazzer](https://github.com/CodeIntelligenceTesting/jazzer) |
| Java framework / app 进程内（ART） | framework Java 服务、app 代码 | **低（需定制）** | android_jazzer fork；动态插桩方案 | fork 改造 / DBI | [ittiam-systems/android_jazzer](https://github.com/ittiam-systems/android_jazzer)、[Jazzer issue #865](https://github.com/CodeIntelligenceTesting/jazzer/issues/865) |
| GUI / 应用整体行为 | Activity 跳转、输入控件、崩溃与逻辑 bug | **中（崩溃）/ 低（功能 bug）** | Monkey、APE、ComboDroid、Fastbot、Kea2、LLM 工具 | GUI model / RL / property / LLM 决策；一般无代码级覆盖率 | [APE (ICSE'19)](https://cs.nju.edu.cn/changxu/1_publications/19/ICSE19_02.pdf)、[Fastbot_Android](https://github.com/bytedance/Fastbot_Android)、[Kea2](https://github.com/ecnusse/Kea2) |
| Intent / 组件间交互 | exported Activity/Service/Receiver、deeplink | **低（工具老化）** | Intent Fuzzer（2014）、GUI 工具内置能力 | 黑盒 intent 变异 | [Intent Fuzzer, WODA+PERTEA 2014](https://doi.org/10.1145/2632168.2632169) |
| 二进制-only app（闭源 SDK/库） | 第三方 .so、加固 app | **中低** | AFL++ Frida mode（-O）、QEMU mode | Frida Stalker 动态插桩 | [AFL++ frida_mode README](https://github.com/AFLplusplus/AFLplusplus/blob/stable/frida_mode/README.md) |

## 3. 官方 / 一线工具链

### 3.1 AOSP 内建 libFuzzer 集成

**现状**：AOSP 构建系统原生支持 LLVM libFuzzer。fuzz target 用 `cc_fuzz` 模块声明在 `Android.bp` 中，可打包 corpus 目录与 dictionary；设备端用 `SANITIZE_TARGET=hwaddress`（HWASan）构建，host 端用 `SANITIZE_HOST=address`（ASan）构建；产物默认落在 `$ANDROID_PRODUCT_OUT/data/fuzz/<arch>/<name>/` 与 `$ANDROID_HOST_OUT/fuzz/...`，通过 `adb sync data` 推送到设备运行。官方文档还说明了 corpus/dictionary 打包与 libFuzzer 输出的读法。

来源：[Fuzz with libFuzzer | Android Open Source Project](https://source.android.com/docs/security/test/libfuzzer)；总览页 [Security testing（fuzzing、sanitizing 与 exploit 缓解工具汇总）](https://source.android.com/docs/security/test/fuzz-sanitize)。

**Sanitizer 支持**：

- **HWASan**：Android 10+ 且仅 AArch64 硬件；CPU 开销约 2x、代码体积 +40~50%、RAM 开销仅 10~35%（远小于 ASan，可做全系统 sanitization）；检测 ASan 同集 bug 外加 stack-use-after-return；但 tag 只有 256 个取值，单次执行约有 0.4% 漏报概率。来源：[Hardware-assisted AddressSanitizer | AOSP](https://source.android.com/docs/security/test/hwasan)。NDK 应用侧用法见 [developer.android.com HWASan 指南](https://developer.android.com/ndk/guides/hwasan)。
- **ASan / UBSan**：HWASan 与 UBSan 可同时启用（同上来源）。
- **Arm MTE**：作为 HWASan 的硬件化后继，AOSP 有专门文档描述在测试与生产环境启用 MTE 的方式：[Arm Memory Tagging Extension | AOSP](https://source.android.com/docs/security/test/memory-safety/arm-mte)。

**接入方式**：修改 `Android.bp` 增加 `cc_fuzz` → 整机构建并刷机（或 host build）→ `adb` 推送运行；corpus 与 dict 随构建打包。一个实际示例是用该机制 fuzz NFC 栈（[m-y-mo/android_nfc_fuzzer](https://github.com/m-y-mo/android_nfc_fuzzer)，README 明确指向 `cc_fuzz` 构建说明）。

### 3.2 AFL++ 及 Android 支持现状

**现状**：AFL++ 是社区维护的主流 fuzzer，提供 LLVM mode、QEMU mode、Frida mode、Unicorn/Nyx mode 等。Android 不是其一等支持平台，但有三条可行路径：

1. **Frida mode（`-O`，binary-only）**：`frida_mode/README.md` 有专门的 Android 交叉编译小节（基于 Android NDK / standalone toolchain），并链接了 Quarkslab 的 Android 灰盒 fuzzing 教程。社区 issue 证实 afl-fuzz 可以在 arm64 Android 模拟器上直接以 Frida mode 运行（[issue #1884](https://github.com/AFLplusplus/AFLplusplus/issues/1884)）。
2. **源码插桩路径**：对 AOSP 树内目标，需要 patch soong 构建系统（社区 gist 方案），并配合 `SANITIZE_TARGET=hwaddress`（[issue #861](https://github.com/AFLplusplus/AFLplusplus/issues/861)）。
3. **LibAFL 的 Frida 组件**：AFL++ 团队在 discussion 中指出，面向 Android 的跨编译 Frida fuzzing 在 LibAFL 的 `fuzzers/frida_libpng` 示例中"测试较充分"（[discussion #1070](https://github.com/AFLplusplus/AFLplusplus/discussions/1070)）。

来源：[AFLplusplus 仓库](https://github.com/AFLplusplus/AFLplusplus)、[INSTALL.md](https://github.com/AFLplusplus/AFLplusplus/blob/stable/docs/INSTALL.md)、[frida_mode README](https://github.com/AFLplusplus/AFLplusplus/blob/stable/frida_mode/README.md)。

**判断**：AFL++ 在 Android 上的能力真实存在但属"社区支持"级别——需要自己处理交叉编译、部署与稳定性问题，没有官方 CI 背书；生产化程度不如 AOSP 自带的 libFuzzer 路径。

### 3.3 Jazzer 与 Jazzer-Android（Java/Kotlin 层）

**Jazzer 现状**：Code Intelligence 开发的 JVM coverage-guided in-process fuzzer，基于 libFuzzer 引擎，字节码插桩使用 JaCoCo 的 LLVM 风格 edge coverage。官方支持平台为 Linux x86_64、macOS 12+（x86_64/arm64）、Windows x86_64——**不含 Android/ART**。接入方式包括：JUnit 5（`@FuzzTest` + `JAZZER_FUZZ=1` 环境变量切换 fuzz/regression 两种模式）、cifuzz CLI（去重、管理 finding、覆盖率报告）、Bazel `rules_fuzzing`、Docker 镜像，以及通过 OSS-Fuzz 支持 Java/Kotlin 项目。来源：[CodeIntelligenceTesting/jazzer](https://github.com/CodeIntelligenceTesting/jazzer)。

**Android 适用性**：

- 对 app 中可抽出的纯 Java/Kotlin 库代码（解析器、序列化等），可离线用 Jazzer fuzz，这是当前 Java 层最务实的路径。
- Jazzer 官方 issue 明确：不支持在 JUnit4/Android instrumented test 中运行，"只能把 Java 代码当库来 fuzz"（[issue #865](https://github.com/CodeIntelligenceTesting/jazzer/issues/865)）。
- 针对 AOSP framework 的 Java 代码，ittiam 维护了 [android_jazzer](https://github.com/ittiam-systems/android_jazzer) fork，用于在 Android 环境 fuzz framework/系统组件——这是"Jazzer on Android"目前最主要的一手实现，属厂商维护而非上游能力。

### 3.4 OSS-Fuzz 中的 Android 相关项目

- OSS-Fuzz 是 Google 面向开源软件的持续 fuzzing 服务，截至官方文档口径已覆盖 1000+ 项目、修复 1 万以上漏洞与 3.6 万以上 bug（2023-08 数据；GitHub README 已更新到 13000+ 漏洞 / 50000+ bug）。来源：[google/oss-fuzz](https://github.com/google/oss-fuzz)、[OSS-Fuzz 文档](https://google.github.io/oss-fuzz/)、[发布公告](https://opensource.googleblog.com/2016/12/announcing-oss-fuzz-continuous-fuzzing.html)。
- **AOSP 平台本身不在 OSS-Fuzz 中**（projects 目录下无 android 平台项目）；但 Android 依赖的关键开源库大量在列，经 GitHub API 核实包括 boringssl、freetype2、gson、harfbuzz、icu、libavif、libexif、libheif、libvpx、libwebp、okhttp 等。即 OSS-Fuzz 对 Android 的价值主要是"覆盖其开源依赖供应链"。
- 覆盖率与各项目 fuzz 状态可查 [Fuzz Introspector](https://introspector.oss-fuzz.com/)。
- **OSS-Fuzz-Gen**（Google 官方仓库 [google/oss-fuzz-gen](https://github.com/google/oss-fuzz-gen)）：用 LLM 自动生成 fuzz target/harness 的项目，是 LLM × fuzzing 在工业界最主要的一手实践。
- **ClusterFuzzLite**：轻量版 ClusterFuzz，可直接接入 GitHub Actions 等 CI 做 PR 级 fuzzing。来源：[clusterfuzzlite 文档](https://google.github.io/clusterfuzzlite/)。

### 3.5 内核层：syzkaller 与 syzbot

- syzkaller 官方文档提供两条 Android 路径：[物理 arm 设备 fuzzing](https://github.com/google/syzkaller/blob/master/docs/linux/setup_linux-host_android-device_arm-kernel.md) 与 [Cuttlefish/Android 虚拟设备（x86-64 kernel）](https://github.com/google/syzkaller/blob/master/docs/linux/setup_linux-host_android-virtual-device_x86-64-kernel.md)。
- syzbot 持续 fuzz Android Common Kernel（ACK），其 Binder 驱动覆盖率可在 syzbot dashboard 查询；Google Android Offensive Security 团队指出 syzkaller 对 Binder 各 ioctl 主路径覆盖良好，但对需要多客户端精确时序/状态组合的深层逻辑 bug（如 UAF）力不从心（[Binder Fuzzing, 2025-08](https://androidoffsec.withgoogle.com/posts/binder-fuzzing/)）。

### 3.6 Google 官方安全资源

- [Android Offensive Security 官方博客](https://androidoffsec.withgoogle.com/posts/binder-fuzzing/)（2025）：公开的 Binder 内核驱动 fuzzing 实践——基于 Linux Kernel Library（LKL）把内核编译为用户态库，用 protobuf + libprotobuf-mutator 定义多客户端交互"语法"，并加入随机调度器捕捉竞争条件；该 fuzzer 已上游至 [lkl/linux PR #564](https://github.com/lkl/linux/pull/564)，并由此发现 CVE-2023-20938。这是理解"强状态目标为什么需要定制 harness"的最佳一手材料。
- AOSP 安全测试文档体系：[Security testing 总览](https://source.android.com/docs/security/test/fuzz-sanitize)、[HWASan](https://source.android.com/docs/security/test/hwasan)、[MTE](https://source.android.com/docs/security/test/memory-safety/arm-mte)、[libFuzzer](https://source.android.com/docs/security/test/libfuzzer)。

## 4. 面向 Android App 的模糊测试技术与学术工具

### 4.1 GUI fuzzing（应用整体行为）

- **Monkey**（官方）：随机事件流，无模型无 oracle，基线工具。[官方文档](https://developer.android.com/studio/test/other-testing-tools/monkey)。
- **APE**（ICSE 2019）：model-based GUI 测试，通过决策树动态演化 GUI model 的抽象粒度，在模型保真与可探索性间平衡。论文一手 PDF：[cs.nju.edu.cn](https://cs.nju.edu.cn/changxu/1_publications/19/ICSE19_02.pdf)。
- **ComboDroid**（ICSE 2020）：以"use case 组合"生成高质量输入序列，区分 short/long use case，结合 α-ε 探索策略。[ACM DL, DOI 10.1145/3377811.3380428](https://dl.acm.org/doi/10.1145/3377811.3380428)。
- **Fastbot / Fastbot 2.0**（字节跳动开源）：model-based + 机器学习/强化学习的 GUI 遍历工具，工业界大规模使用（字节官方 App 日常测试基础设施）。[bytedance/Fastbot_Android](https://github.com/bytedance/Fastbot_Android)。
- **Kea2**（ECNU，FSE 2026）：在 Fastbot 之上融合 property-based testing——人工编写的 uiautomator2 property 脚本与随机探索交替执行，把 oracle 从"仅崩溃"扩展到业务逻辑性质。[ecnusse/Kea2](https://github.com/ecnusse/Kea2)、[论文 PDF](https://tingsu.github.io/files/fse26-Kea2.pdf)。
- **Humanoid**（2019）：用深度神经网络学习人类交互轨迹指导探索（被后续多篇论文作为 learning-based 基线引用，如 [FuncDroid 相关工作](https://arxiv.org/html/2602.12834v2)）。

### 4.2 Intent fuzzing

- **Intent Fuzzer: Crafting Intents of Death**（Sasnauskas & Regehr，WODA+PERTEA 2014）：针对 exported 组件变异 Intent 的 extras/action/data，观察崩溃与异常。这是该方向被引用最广的原始工作（DOI [10.1145/2632168.2632169](https://doi.org/10.1145/2632168.2632169)，被 [BinderCracker](https://ar5iv.labs.arxiv.org/html/1604.06964) 等后续工作引用）。
- 该方向之后缺乏持续维护的主流工具；现代实践中 intent 覆盖通常由 GUI 测试工具或静态分析（识别 exported 组件）+ 手工 harness 完成。

### 4.3 Binder / 系统服务 fuzzing

- **FANS**（USENIX Security 2020）：自动化接口分析（interface collector / model extractor / dependency inferer / fuzzer 四组件）对 Android native system services 做生成式 fuzzing，报告 30 个 native 漏洞与 138 个 Java 异常。[会议页](https://www.usenix.org/conference/usenixsecurity20/presentation/liu)、[iromise/fans](https://github.com/iromise/fans)。
- **Chizpurfle**（ISSRE 2017 / TOSEM 扩展版 [arXiv:1906.00621](https://arxiv.org/abs/1906.00621)）：针对厂商定制系统服务的灰盒 fuzzer，用动态二进制插桩在商用三星设备上度量覆盖率并引导进化式输入选择；代码在 [dessertlab/fantastic_beasts](https://github.com/dessertlab/fantastic_beasts)。
- **BinderCracker**（AsiaCCS 2016，[arXiv:1604.06964](https://ar5iv.labs.arxiv.org/html/1604.06964)）：较早的系统服务健壮性评估框架，含 transaction 参数感知变异。
- **BinderFuzzy**（开源 App）：安装在设备上直接 fuzz Binder 接口与系统服务的工具，被列入 Kali 工具库。[ChickenHook/BinderFuzzy](https://github.com/ChickenHook/BinderFuzzy)。
- **Google LKL Binder fuzzer**（2025，见 3.6）：针对 Binder **内核驱动**的最新官方实践，已上游 LKL。

### 4.4 LLM / 深度学习辅助（2023–2026）

- **GPTDroid**（ICSE 2023，[arXiv:2305.09434](https://arxiv.org/abs/2305.09434)）：把 GUI 测试建模为与 GPT-3 的问答任务，结合静态 GUI 上下文与动态测试历史选择动作，zero-shot 类人探索。
- **InputBlaster**（[arXiv:2310.15657](https://arxiv.org/html/2310.15657v1)）：用 LLM 生成"非常规文本输入"专门触发 app 崩溃——是最贴近"fuzzing 语义"的 LLM 应用（输入生成而非路径决策）。
- **AutoDroid**（2023）：离线随机探索构建 UI Transition Graph，在线由 LLM 规划动作（被 [arXiv:2504.15917](https://arxiv.org/html/2504.15917v1) 相关工作综述引用）。
- **DroidAgent**（2024，[论文 PDF](https://coinse.github.io/publications/pdfs/Yoon2024aa.pdf)）：intent-driven 的自主 LLM agent 做语义级 GUI 测试。
- **LLMDroid**（FSE 2025，[会议页](https://conf.researchr.org/details/fse-2025/fse-2025-research-papers/99/LLMDroid-Enhancing-Automated-Mobile-App-GUI-Testing-Coverage-with-Large-Language-Mod)）：用 LLM 增强（而非替代）既有自动化 GUI 工具的覆盖率。
- **VLM-Fuzz**（[arXiv:2504.11675](https://arxiv.org/html/2504.11675v1)，EMSE 2026 期刊版）：视觉语言模型辅助的递归 DFS UI 探索。
- **VisionDroid**（[arXiv:2407.03037](https://arxiv.org/html/2407.03037v2)）：多模态 LLM 驱动的视觉 GUI 测试与非崩溃功能 bug 检测。
- **CovAgent**（[arXiv:2601.21253](https://arxiv.org/html/2601.21253v1)，2026）：agentic AI + 动态插桩，目标突破移动 app 测试的"30% 覆盖率魔咒"。
- **OSS-Fuzz-Gen**（见 3.4）：LLM 生成 fuzz harness，通用而非 Android 专属，但直接适用于 Android 的 native 依赖库。

**趋势判断**：2023 年以来学术界的重心从"随机/模型/RL 探索"转向"LLM 做语义决策与输入生成"；工业界（Google）则把 LLM 用在 harness 生成这个 fuzzing 最费人力的环节。两条路线在 Android app 测试中正在汇合（如 CovAgent 同时用 LLM agent 与动态插桩）。

## 5. 工程实践要点

- **CI 接入**：native/库级 fuzz target 用 [ClusterFuzzLite](https://google.github.io/clusterfuzzlite/)（GitHub Actions 等）或自建 libFuzzer 定时任务；Java 库用 Jazzer 的 JUnit 5 模式（`JAZZER_FUZZ=1` fuzz、不设置则跑回归，finding 自动存入 inputs 目录）或 cifuzz；AOSP 平台代码依赖整机构建，通常夜间任务 + 真机 farm。来源：[Jazzer README](https://github.com/CodeIntelligenceTesting/jazzer)、[ClusterFuzzLite 文档](https://google.github.io/clusterfuzzlite/)。
- **设备 vs 模拟器**：HWASan 只能在 AArch64 真机（Android 10+）上运行，模拟器无此能力；ASan host build 适合库级 fuzz target 的快速迭代；syzkaller 官方支持 Cuttlefish/AVD；GUI 工具（Kea2、Fastbot）模拟器与真机均可，真机更接近 OEM 定制行为。来源：[HWASan 文档](https://source.android.com/docs/security/test/hwasan)、[syzkaller Android 文档](https://github.com/google/syzkaller/blob/master/docs/linux/setup_linux-host_android-device_arm-kernel.md)、[Kea2 README](https://github.com/ecnusse/Kea2)。
- **插桩方式选择**：有源码 → SanitizerCoverage（AOSP `cc_fuzz` 默认）/ AFL++ LLVM mode；JVM 字节码 → JaCoCo 式插桩（Jazzer）；无源码二进制 → AFL++ Frida mode（Android 可交叉编译）；闭源系统服务 → 动态二进制插桩（Chizpurfle 路线）。来源：[AOSP libFuzzer](https://source.android.com/docs/security/test/libfuzzer)、[AFL++ frida_mode](https://github.com/AFLplusplus/AFLplusplus/blob/stable/frida_mode/README.md)、[Chizpurfle 论文](https://arxiv.org/abs/1906.00621)。
- **崩溃去重与语料库管理**：libFuzzer 自带 `-merge`（语料蒸馏）、crash 去重依赖栈哈希（ClusterFuzz/ClusterFuzzLite 体系内置去重）；AFL 生态用 afl-cmin/afl-tmin；Jazzer/cifuzz 内置 finding 去重与 inputs 目录管理。来源：[libFuzzer 文档](https://llvm.org/docs/LibFuzzer.html)、[OSS-Fuzz 文档](https://google.github.io/oss-fuzz/)、[Jazzer README](https://github.com/CodeIntelligenceTesting/jazzer)。

## 6. 能力边界与局限

1. **成熟度最高的部分**：native 库/codec/协议解析（AOSP libFuzzer + sanitizer，OSS-Fuzz 依赖覆盖）与内核 syscall fuzzing（syzkaller）。这两层可以做到"开箱即用 + 持续 fuzzing"。
2. **强状态目标仍是硬骨头**：Binder 驱动、系统服务这类目标的 bug 多由多客户端精确时序/状态组合触发，纯覆盖率反馈不足以触达（Google 2025 年 LKL 方案的动机正在于此）；vendor 定制服务基本都要自写接口模型或 harness（FANS、Chizpurfle 均需目标适配）。
3. **App 内 Java/Kotlin 代码的进程内 coverage-guided fuzzing 没有官方方案**：Jazzer 不支持 ART；要么把代码抽成库离线 fuzz，要么用厂商 fork（android_jazzer），要么走动态插桩的定制路线。
4. **GUI 层 oracle 弱**：主流工具以崩溃为主要信号；非崩溃功能 bug 需要 property（Kea2）或差分/视觉判定（VisionDroid），泛化性仍待验证。LLM 工具的成本、稳定性与复现性是工程化障碍。
5. **Intent fuzzing 工具老化**：2014 年的 Intent Fuzzer 后缺少维护良好的通用工具，现代 Android 的权限与组件导出模型变化使老工具直接可用性存疑（本调研未找到 2020 年后的一手 Intent 专用 fuzzer）。
6. **HWASan 自身局限**：仅 AArch64 真机、约 2x CPU 开销、256 tag 导致单次执行约 0.4% 漏报；MTE 是后续方向但依赖硬件普及。
7. **binary-only app fuzzing 性能与稳定性**：Frida mode 可行但吞吐远低于源码插桩，且对加固/混淆 app 需要额外对抗。

## 7. 参考来源列表

**官方文档 / Google 一手来源**

1. AOSP — Fuzz with libFuzzer: https://source.android.com/docs/security/test/libfuzzer
2. AOSP — Security testing（fuzzing/sanitizing 总览）: https://source.android.com/docs/security/test/fuzz-sanitize
3. AOSP — Hardware-assisted AddressSanitizer (HWASan): https://source.android.com/docs/security/test/hwasan
4. AOSP — Arm Memory Tagging Extension (MTE): https://source.android.com/docs/security/test/memory-safety/arm-mte
5. Android Developers — HWASan（NDK 应用）: https://developer.android.com/ndk/guides/hwasan
6. Android Developers — Monkey: https://developer.android.com/studio/test/other-testing-tools/monkey
7. Android Offensive Security Blog — Binder Fuzzing（LKL，2025）: https://androidoffsec.withgoogle.com/posts/binder-fuzzing/
8. Google Open Source Blog — Announcing OSS-Fuzz（2016）: https://opensource.googleblog.com/2016/12/announcing-oss-fuzz-continuous-fuzzing.html

**工具官方仓库 / 文档**

9. LLVM libFuzzer 文档: https://llvm.org/docs/LibFuzzer.html
10. AFLplusplus: https://github.com/AFLplusplus/AFLplusplus （INSTALL: https://github.com/AFLplusplus/AFLplusplus/blob/stable/docs/INSTALL.md ；frida_mode Android 小节: https://github.com/AFLplusplus/AFLplusplus/blob/stable/frida_mode/README.md ；Android 相关 issue #861 / #1884 / discussion #1070）
11. Jazzer: https://github.com/CodeIntelligenceTesting/jazzer （Android 支持讨论: https://github.com/CodeIntelligenceTesting/jazzer/issues/865 ）
12. android_jazzer（ittiam fork）: https://github.com/ittiam-systems/android_jazzer
13. OSS-Fuzz: https://github.com/google/oss-fuzz ；文档: https://google.github.io/oss-fuzz/ ；Fuzz Introspector: https://introspector.oss-fuzz.com/
14. OSS-Fuzz-Gen: https://github.com/google/oss-fuzz-gen
15. ClusterFuzzLite: https://google.github.io/clusterfuzzlite/
16. syzkaller: https://github.com/google/syzkaller （Android 设备: https://github.com/google/syzkaller/blob/master/docs/linux/setup_linux-host_android-device_arm-kernel.md ；Android 虚拟设备: https://github.com/google/syzkaller/blob/master/docs/linux/setup_linux-host_android-virtual-device_x86-64-kernel.md ）
17. Fastbot_Android: https://github.com/bytedance/Fastbot_Android
18. Kea2: https://github.com/ecnusse/Kea2 （论文: https://tingsu.github.io/files/fse26-Kea2.pdf ）
19. BinderFuzzy: https://github.com/ChickenHook/BinderFuzzy
20. FANS 代码: https://github.com/iromise/fans
21. Chizpurfle 代码（fantastic_beasts）: https://github.com/dessertlab/fantastic_beasts
22. android_nfc_fuzzer（cc_fuzz 实践示例）: https://github.com/m-y-mo/android_nfc_fuzzer
23. LKL Binder fuzzer 上游 PR: https://github.com/lkl/linux/pull/564

**原始论文**

24. Intent Fuzzer: Crafting Intents of Death（WODA+PERTEA 2014）: https://doi.org/10.1145/2632168.2632169
25. BinderCracker（AsiaCCS 2016）: https://ar5iv.labs.arxiv.org/html/1604.06964
26. Chizpurfle（ISSRE 2017 / 扩展版 arXiv）: https://arxiv.org/abs/1906.00621
27. FANS（USENIX Security 2020）: https://www.usenix.org/conference/usenixsecurity20/presentation/liu
28. APE（ICSE 2019）: https://cs.nju.edu.cn/changxu/1_publications/19/ICSE19_02.pdf
29. ComboDroid（ICSE 2020）: https://dl.acm.org/doi/10.1145/3377811.3380428
30. GPTDroid（ICSE 2023）: https://arxiv.org/abs/2305.09434
31. InputBlaster（2023）: https://arxiv.org/html/2310.15657v1
32. DroidAgent（2024）: https://coinse.github.io/publications/pdfs/Yoon2024aa.pdf
33. VisionDroid（2024）: https://arxiv.org/html/2407.03037v2
34. LLMDroid（FSE 2025）: https://conf.researchr.org/details/fse-2025/fse-2025-research-papers/99/LLMDroid-Enhancing-Automated-Mobile-App-GUI-Testing-Coverage-with-Large-Language-Mod
35. VLM-Fuzz（2025/EMSE 2026）: https://arxiv.org/html/2504.11675v1
36. CovAgent（2026）: https://arxiv.org/html/2601.21253v1
37. AutoDroid 等 LLM GUI 测试综述参照: https://arxiv.org/html/2504.15917v1

## 附注：调研中的不确定之处

- 广为引用的 Google Security Blog 博文《Fuzzing Android》（2016-08）在本次调研中无法通过任何候选 URL 访问（均返回 404），故正文未引用该文，"Google 内部对 AOSP 做持续 fuzzing"这一说法仅依据 AOSP 官方文档与 Android OffSec 博客的现行表述。
- OSS-Fuzz projects 目录经 GitHub API 抽样核实（首 1000 项），"AOSP 平台本身不在 OSS-Fuzz"的结论基于该样本；项目总数超过单页上限，存在极小概率的遗漏。
- Intent Fuzzer 的 DOI 链接（dl.acm.org）与 ComboDroid 的 ACM 页面存在反爬 403，但 DOI 本身有效。

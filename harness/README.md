# harness/

Jazzer fuzz harness。引用 DDG（`~/project/duckduckgo-android`）的编译产物/源码，DDG 仓库保持原样、不进本 repo git。

风格约定：JUnit4 + mockito-kotlin fake（DDG 测试栈事实标准；不用 MockK），绕过 Anvil/Dagger DI 直接构造类。

见 `docs/validation-plan-ddg-three-layer-fuzzing.md`。

# intent-fuzz/

畸形 Intent 发送脚本：消费 `static-analysis/` 产出的暴露面 JSON，对每个 exported 组件经 adb 发送 50 条畸形 Intent（null extras、类型错乱、超长字符串、畸形 URI、空 action），验证「exported 组件收到畸形 Intent 不得崩溃」的通用不变量。

见 `docs/validation-plan-ddg-three-layer-fuzzing.md`。

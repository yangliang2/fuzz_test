# properties/

Kea2 property 层，解耦为两层：

- `core/` — property 主体，纯 uiautomator2 断言函数，不依赖 Kea2 API。
- `kea2_bindings/` — Kea2 装饰器，只做调度绑定。

解耦目的：对冲 Kea2 学术团队单点维护 + 非标准许可证风险。

见 `docs/validation-plan-ddg-three-layer-fuzzing.md`。

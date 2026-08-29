# fuzz_test

Android 应用层模糊测试（fuzzing）技术路线研究与验证项目。

## Layout

- `harness/` — Jazzer fuzz harness（引用 `~/project/duckduckgo-android`，DDG 仓库不进本 repo）
- `properties/` — Kea2 property（`core/` 纯 uiautomator2 断言 + `kea2_bindings/` 调度绑定）
- `static-analysis/` — 暴露面盘点脚本 + 输出 JSON
- `intent-fuzz/` — 畸形 Intent 发送脚本
- `test-pages/` — privacy-test-pages 本地服务脚本
- `scripts/` — 环境脚本（`kea2-avd.sh`：专用 AVD 创建/启动，见 `docs/kea2-avd.md`）

## Agent skills

### Issue tracker

Issues and specs live as GitHub issues, managed via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage labels are used as-is (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

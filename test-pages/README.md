# test-pages/

DDG 官方 [privacy-test-pages](https://github.com/duckduckgo/privacy-test-pages) 的本地服务脚本：`python3 -m http.server` 起服务，模拟器经 `10.0.2.2` 访问；tracker 测试域名（`bad.third-party.site` 等）经 adb 改模拟器 hosts 指向本机，为 tracker 拦截 oracle 提供确定性基准。HTTPS/HSTS 类页面本轮不用。

见 `docs/validation-plan-ddg-three-layer-fuzzing.md`。

# 本地 privacy-test-pages 服务

DDG 官方 [privacy-test-pages](https://github.com/duckduckgo/privacy-test-pages) 在本地起 HTTP 服务，模拟器经 `10.0.2.2`（QEMU user networking 中宿主 loopback 的别名）访问；tracker 测试域名经模拟器 hosts 指向 `10.0.2.2`，使 DDG 的 tracker 拦截 oracle 获得确定性基准（不依赖公网，拦截结果只由 blocklist 决定）。

- 服务只绑 `127.0.0.1:8800`（默认端口避开常用的 8000/8080；模拟器经 10.0.2.2 仍可到达）。
- 本轮只用纯 HTTP 页面；HTTPS/HSTS 类页面（`privacy-protections/https-upgrades/`、`storage-partitioning/` 等）不用。
- 域名清单取自仓库 README "Test domains" 一节：`first-party.site`、`good/allowlisted/broken/bad.third-party.site`、`www.search-company.site`、`convert.ad-company.site` 等，全部指向 `10.0.2.2`。

## 前置条件

- 模拟器为可 root 镜像（`google_apis`，非 `google_apis_playstore`——playstore 镜像是 production build，`adb root` 拒绝，hosts 无法写入）。`scripts/kea2-avd.sh` 建的 `Kea2_Test` 即此镜像。
- `python3`、`git`、`curl` 可用。

## 命令

```bash
test-pages/serve.sh start [--port N]  # 幂等 clone（test-pages/privacy-test-pages/）+ 后台起服务，起后自检首页
test-pages/serve.sh hosts             # tracker 测试域名写入模拟器 /system/etc/hosts（adb root + remount，幂等合并）并校验解析
test-pages/serve.sh status            # 服务 / clone / 模拟器 hosts 状态
test-pages/serve.sh stop              # 停止服务
test-pages/serve.sh update            # git pull 更新本地 clone
```

一次完整拉起：

```bash
scripts/kea2-avd.sh boot
test-pages/serve.sh start
test-pages/serve.sh hosts
```

之后模拟器内 DDG 打开 `http://bad.third-party.site:8800/privacy-protections/request-blocking/` 即可验证：`bad.third-party.site` 的子资源请求应被 DDG 拦截，`good.third-party.site` 的应放行。

## 冒烟页（确定性 oracle）

`serve.sh start` 会把 `test-pages/smoke.html` 拷为服务根下的 `/_smoke.html`：页面从 `www.first-party.site` 加载，分别嵌入 `good.third-party.site` 与 `bad.third-party.site` 的子资源。验证方法：在浏览器里打开 `http://www.first-party.site:8800/_smoke.html`，看服务日志（`test-pages/.serve.log`）：

- `/_smoke/good.js` 有命中（200/404 均可）→ 非 tracker 放行；
- `/_smoke/tracker.js` 无命中 → tracker 域名被拦截。

2026-08-30 实测（API 34 google_apis 模拟器 + DDG 5.294.0 internal debug）：Chrome 两者皆命中；DDG 仅 `good.js` 命中，`tracker.js` 被拦截，oracle 基准成立。

## 手动等价命令

```bash
git clone --depth 1 https://github.com/duckduckgo/privacy-test-pages.git test-pages/privacy-test-pages
python3 -m http.server 8800 --bind 127.0.0.1 -d test-pages/privacy-test-pages &
adb root && adb remount
adb shell cat /system/etc/hosts   # 追加：10.0.2.2 bad.third-party.site（等域名行）后 push 回去
adb shell ping -c 1 bad.third-party.site   # 应解析到 10.0.2.2
```

注意：宿主机若配置了 `http_proxy`，`curl` 自检需 `--noproxy 127.0.0.1`（脚本已内置）；模拟器侧流量走 QEMU user networking，不经宿主代理。

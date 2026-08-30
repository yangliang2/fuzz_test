# Kea2 专用 AVD

Fastbot 已知坑：手势导航会把滑动事件误判为返回手势，Kea2/Fastbot 必须使用**三键导航**。因此使用专用 AVD `Kea2_Test`，与既有 `Calendar_Test` 互不污染。

## 规格

| 项 | 值 |
| --- | --- |
| 名称 | `Kea2_Test` |
| API / ABI | 34 / x86_64（`google_apis` 镜像，见下） |
| 设备 profile | pixel_6 |
| RAM | 4096 MB（要求 2G 以上） |
| 导航 | 三键导航（`navigation_mode=0`，boot 时强制） |

镜像用 `google_apis` 而非 `google_apis_playstore`：playstore 镜像是 production build，`adb root` 会被 adbd 拒绝，无法写模拟器 hosts（issue #5 的 tracker 测试域名需要，见 `docs/test-pages.md`）。镜像未安装时先执行：

```bash
sdkmanager "system-images;android-34;google_apis;x86_64"
```

## 命令

```bash
scripts/kea2-avd.sh create            # 幂等创建 AVD（存在则跳过，RAM 强制为 4096MB）
scripts/kea2-avd.sh boot              # 启动、等待 boot 完成、强制三键导航（后台保持运行）
scripts/kea2-avd.sh boot --headless   # 无窗口模式（CI / 远程）
scripts/kea2-avd.sh status            # 查看配置与当前导航模式
scripts/kea2-avd.sh stop              # 关闭
```

三键导航通过两种方式双保险：`settings put secure navigation_mode 0`（重启后保留）+ 禁用 `navbar.gestural` overlay / 启用 `navbar.threebutton` overlay。`boot` 子命令会校验 `navigation_mode == 0`，不符即报错。

## 手动等价命令

```bash
avdmanager create avd --name Kea2_Test --device pixel_6 \
  -k "system-images;android-34;google_apis;x86_64" --force
sed -i 's/^hw.ramSize=.*/hw.ramSize=4096/' ~/.android/avd/Kea2_Test.avd/config.ini
emulator -avd Kea2_Test -no-snapshot-save &
adb wait-for-device
adb shell settings put secure navigation_mode 0
```

#!/usr/bin/env bash
# Kea2 专用 AVD 的创建与启动脚本（issue #3）。
#
# 规格：API 34 / x86_64 / pixel_6 / RAM 4096MB / 三键导航。
# Fastbot 已知坑：手势导航会把滑动事件误判为返回手势，必须强制三键导航。
#
# 用法：
#   scripts/kea2-avd.sh create            # 幂等创建 AVD
#   scripts/kea2-avd.sh boot [--headless] # 启动并等待 boot 完成，强制三键导航后保持运行
#   scripts/kea2-avd.sh stop              # 关闭正在运行的该 AVD
#   scripts/kea2-avd.sh status            # 打印该 AVD 的配置与导航模式
set -euo pipefail

AVD_NAME="Kea2_Test"
DEVICE="pixel_6"
# google_apis（非 playstore）镜像：playstore 是 production build，adb root 拒绝，
# 无法写模拟器 hosts（issue #5 的 tracker 测试域名需要）
IMAGE="system-images;android-34;google_apis;x86_64"
RAM_MB=4096
BOOT_TIMEOUT_S=240

SDK="${ANDROID_HOME:-$HOME/Android/Sdk}"
AVDMANAGER="$SDK/cmdline-tools/latest/bin/avdmanager"
EMULATOR="$SDK/emulator/emulator"
ADB="$SDK/platform-tools/adb"
AVD_INI="$HOME/.android/avd/$AVD_NAME.avd/config.ini"

adb_shell() {
  "$ADB" shell "$@" | tr -d '\r'
}

# 正在运行的模拟器的 AVD 名；无模拟器则输出空。
# 新版 emulator 用 ro.boot.qemu.avd_name，旧版用 ro.kernel.qemu.avd_name，两个都查。
running_avd() {
  "$ADB" devices | grep -q '^emulator-' || return 0
  local name
  name="$(adb_shell getprop ro.boot.qemu.avd_name)"
  [[ -n "$name" ]] || name="$(adb_shell getprop ro.kernel.qemu.avd_name)"
  echo "$name"
}

# 若正在运行的是别的 AVD（如 Calendar_Test），报错返回非零——绝不触碰既有 AVD。
# 正常时把运行中的 AVD 名（未运行则为空）写入 RUNNING_AVD。
checked_running_avd() {
  RUNNING_AVD="$(running_avd)"
  if [[ -n "$RUNNING_AVD" && "$RUNNING_AVD" != "$AVD_NAME" ]]; then
    echo "ERROR: running emulator is '$RUNNING_AVD', not '$AVD_NAME'; refusing to touch it" >&2
    return 1
  fi
}

create() {
  if "$AVDMANAGER" list avd 2>/dev/null | grep -q "Name: $AVD_NAME\$"; then
    echo "AVD '$AVD_NAME' already exists, skipping create"
  else
    # 回答 avdmanager 的 custom hardware profile 提示
    echo no | "$AVDMANAGER" create avd --name "$AVD_NAME" --device "$DEVICE" -k "$IMAGE" --force
  fi
  # 2G 以上 RAM：Kea2/Fastbot 长跑需要余量，默认 2048MB 偏小
  if grep -q '^hw\.ramSize\s*=' "$AVD_INI"; then
    sed -i "s/^hw\.ramSize\s*=.*/hw.ramSize=$RAM_MB/" "$AVD_INI"
  else
    echo "hw.ramSize=$RAM_MB" >> "$AVD_INI"
  fi
  echo "created: $AVD_NAME ($DEVICE, $IMAGE, RAM=${RAM_MB}MB)"
}

wait_boot() {
  "$ADB" wait-for-device
  local waited=0
  until [[ "$(adb_shell getprop sys.boot_completed)" == "1" ]]; do
    sleep 2
    waited=$((waited + 2))
    if (( waited >= BOOT_TIMEOUT_S )); then
      echo "ERROR: boot not completed after ${BOOT_TIMEOUT_S}s" >&2
      return 1
    fi
  done
}

force_three_button_nav() {
  # 三键导航 = navigation_mode 0（1=两键，2=手势）。写入 secure settings，重启后保留。
  adb_shell settings put secure navigation_mode 0 >/dev/null
  # 部分镜像上 settings 不够，双保险：禁用手势导航栏 overlay，启用三键 overlay
  adb_shell cmd overlay disable com.android.internal.systemui.navbar.gestural >/dev/null 2>&1 || true
  adb_shell cmd overlay enable com.android.internal.systemui.navbar.threebutton >/dev/null 2>&1 || true
  local mode
  mode="$(adb_shell settings get secure navigation_mode)"
  if [[ "$mode" != "0" ]]; then
    echo "ERROR: navigation_mode=$mode, expected 0" >&2
    return 1
  fi
  echo "three-button nav OK (navigation_mode=0)"
}

boot() {
  # -writable-system：adb remount 需要（dm-verity 关闭），写模拟器 hosts 用（issue #5）
  local -a args=(-avd "$AVD_NAME" -no-snapshot-save -writable-system)
  [[ "${1:-}" == "--headless" ]] && args+=(-no-window)
  checked_running_avd
  if [[ -n "$RUNNING_AVD" ]]; then
    echo "emulator already running, reusing it"
  else
    "$EMULATOR" "${args[@]}" >/dev/null 2>&1 &
    echo "emulator starting (pid $!)..."
    wait_boot
  fi
  force_three_button_nav
  echo "ready: $(adb_shell getprop ro.product.model), API $(adb_shell getprop ro.build.version.sdk)"
}

stop() {
  checked_running_avd
  if [[ -n "$RUNNING_AVD" ]]; then
    "$ADB" emu kill
    echo "stopped"
  else
    echo "'$AVD_NAME' is not running"
  fi
}

status() {
  grep -E '^(hw\.ramSize|image\.sysdir\.1)\s*=' "$AVD_INI" 2>/dev/null || echo "AVD '$AVD_NAME' not found"
  checked_running_avd
  if [[ -n "$RUNNING_AVD" ]]; then
    echo "navigation_mode=$(adb_shell settings get secure navigation_mode)  (0=三键)"
  else
    echo "emulator not running"
  fi
}

case "${1:-}" in
  create) create ;;
  boot) boot "${2:-}" ;;
  stop) stop ;;
  status) status ;;
  *) echo "usage: $0 {create|boot [--headless]|stop|status}" >&2; exit 2 ;;
esac

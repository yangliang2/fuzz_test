#!/usr/bin/env bash
# privacy-test-pages 本地服务脚本（issue #5）。
#
# clone DDG 官方 privacy-test-pages，用 python3 -m http.server 本地起服务；
# 模拟器经 10.0.2.2 访问宿主机；tracker 测试域名经模拟器 hosts 指向 10.0.2.2，
# 使 tracker 拦截 oracle 获得确定性基准。HTTPS/HSTS 类页面本轮不用（纯 HTTP）。
#
# 用法：
#   test-pages/serve.sh start [--port N]  # 幂等 clone + 后台起服务（一条命令）
#   test-pages/serve.sh stop              # 停止服务
#   test-pages/serve.sh status            # 服务与模拟器 hosts 状态
#   test-pages/serve.sh hosts             # 把 tracker 测试域名写入模拟器 hosts（需 adb root）
#   test-pages/serve.sh update            # git pull 更新本地 clone
set -euo pipefail

# 默认端口避开常用的 8000/8080，减少与宿主机其它服务的冲突
PORT=8800
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PAGES_DIR="$SCRIPT_DIR/privacy-test-pages"
REPO_URL="https://github.com/duckduckgo/privacy-test-pages.git"
PID_FILE="$SCRIPT_DIR/.serve.pid"
LOG_FILE="$SCRIPT_DIR/.serve.log"

SDK="${ANDROID_HOME:-$HOME/Android/Sdk}"
ADB="$SDK/platform-tools/adb"

# 模拟器 hosts 指向 10.0.2.2（QEMU user networking 中宿主 loopback 的别名）。
# 域名清单取自 privacy-test-pages README "Test domains" 一节。
HOSTS_MARKER="# privacy-test-pages (issue #5)"
HOSTS_DOMAINS=(
  first-party.site www.first-party.site
  third-party.site
  good.third-party.site
  allowlisted.third-party.site
  broken.third-party.site
  bad.third-party.site
  search-company.site www.search-company.site
  ad-company.site www.ad-company.site
  convert.ad-company.site
  publisher-company.site www.publisher-company.site
  payment-company.site www.payment-company.site
)

adb_shell() {
  "$ADB" shell "$@" | tr -d '\r'
}

server_pid() {
  [[ -f "$PID_FILE" ]] || return 0
  local pid
  pid="$(cat "$PID_FILE")"
  # 校验 /proc cmdline：PID 复用时不会把无关进程当成 http.server
  if kill -0 "$pid" 2>/dev/null && grep -aq 'http\.server' "/proc/$pid/cmdline" 2>/dev/null; then
    echo "$pid"
  fi
}

clone_repo() {
  if [[ -d "$PAGES_DIR/.git" ]]; then
    return 0
  fi
  echo "cloning $REPO_URL ..."
  rm -rf "$PAGES_DIR"
  git clone --depth 1 "$REPO_URL" "$PAGES_DIR"
}

start() {
  local port_arg=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --port)
        [[ $# -ge 2 ]] || { echo "usage: $0 start [--port N]" >&2; exit 2; }
        PORT="$2"; port_arg=1; shift 2 ;;
      *) echo "usage: $0 start [--port N]" >&2; exit 2 ;;
    esac
  done
  clone_repo
  local pid
  pid="$(server_pid)"
  if [[ -n "$pid" ]]; then
    # 复用已在跑的服务：以其实际端口为准，显式 --port 与之不符时提示
    local actual_port
    actual_port="$(tr '\0' '\n' <"/proc/$pid/cmdline" | grep -A1 '^http.server$' | tail -1)"
    if [[ -n "$port_arg" && "$PORT" != "$actual_port" ]]; then
      echo "NOTE: server already running on port $actual_port, ignoring --port $PORT" >&2
    fi
    PORT="$actual_port"
    echo "server already running (pid $pid), reusing it"
  else
    nohup python3 -m http.server "$PORT" --bind 127.0.0.1 -d "$PAGES_DIR" \
      >"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
    sleep 1
    pid="$(server_pid)"
    if [[ -z "$pid" ]]; then
      echo "ERROR: server failed to start (port $PORT busy?), see $LOG_FILE:" >&2
      tail -3 "$LOG_FILE" >&2
      rm -f "$PID_FILE"
      return 1
    fi
  fi
  # 冒烟页拷进服务根目录（clone 目录整体被 gitignore，拷入不污染上游）
  cp "$SCRIPT_DIR/smoke.html" "$PAGES_DIR/_smoke.html"
  # 起服务后立即自检：本机 127.0.0.1 能取到首页（--noproxy：宿主机可能配了 http_proxy）
  curl -fsS --noproxy 127.0.0.1 -o /dev/null "http://127.0.0.1:$PORT/index.html"
  echo "serving $PAGES_DIR at http://127.0.0.1:$PORT (pid $pid)"
  echo "emulator URL: http://10.0.2.2:$PORT/"
  echo "smoke page:   http://www.first-party.site:$PORT/_smoke.html (需先跑 '$0 hosts')"
}

stop() {
  local pid
  pid="$(server_pid)"
  if [[ -n "$pid" ]]; then
    kill "$pid"
    rm -f "$PID_FILE"
    echo "stopped (pid $pid)"
  else
    echo "server not running"
    rm -f "$PID_FILE"
  fi
}

# 生成要写入模拟器 /system/etc/hosts 的行。
render_hosts_block() {
  echo "$HOSTS_MARKER"
  printf '10.0.2.2 %s\n' "${HOSTS_DOMAINS[@]}"
}

# adb root 失败（playstore 等 production 镜像）时仍会 exit 0，必须查输出。
adb_root() {
  local out
  out="$("$ADB" root 2>&1)"
  if [[ "$out" == *"cannot run as root"* ]]; then
    echo "ERROR: adb root refused (production build image? need google_apis, not playstore)" >&2
    return 1
  fi
  "$ADB" wait-for-device
}

hosts() {
  "$ADB" get-state >/dev/null 2>&1 || { echo "ERROR: no emulator/device connected" >&2; return 1; }
  # 需要 adb root（google_apis 镜像支持，playstore 镜像不支持）+ 可写 system 分区
  adb_root
  # 首次 remount 关闭 verity 后需要重启才生效（"Now reboot your device ..."）
  if "$ADB" remount 2>&1 | grep -qi 'reboot'; then
    echo "remount needs a reboot to take effect, rebooting..."
    "$ADB" reboot
    "$ADB" wait-for-device
    local waited=0
    until [[ "$(adb_shell getprop sys.boot_completed)" == "1" ]]; do
      sleep 2; waited=$((waited + 2))
      (( waited < 240 )) || { echo "ERROR: boot not completed after 240s" >&2; return 1; }
    done
    adb_root
    "$ADB" remount >/dev/null
  fi
  # 幂等合并：先剔除此前的标记块，再追加新块
  local current merged
  current="$(adb_shell cat /system/etc/hosts)"
  merged="$(printf '%s\n' "$current" | awk -v m="$HOSTS_MARKER" '
    $0 == m {skip = 1; next}
    skip && /^10\.0\.2\.2 / {next}
    {skip = 0; print}
  ')"
  # 临时文件放 mktemp，失败也不留残渣
  local hosts_new
  hosts_new="$(mktemp)"
  trap 'rm -f "$hosts_new"' RETURN
  {
    printf '%s\n' "$merged"
    render_hosts_block
  } > "$hosts_new"
  printf 'new hosts:\n'; tail -n $(( ${#HOSTS_DOMAINS[@]} + 1 )) "$hosts_new"
  "$ADB" push "$hosts_new" /system/etc/hosts >/dev/null
  # 校验：bad.third-party.site 应解析到 10.0.2.2
  local resolved
  resolved="$(adb_shell ping -c 1 -W 2 bad.third-party.site | grep -oE '\([0-9.]+\)' | head -1 | tr -d '()')"
  if [[ "$resolved" != "10.0.2.2" ]]; then
    echo "ERROR: bad.third-party.site resolves to '$resolved', expected 10.0.2.2" >&2
    return 1
  fi
  echo "hosts OK: bad.third-party.site -> $resolved"
}

status() {
  local pid
  pid="$(server_pid)"
  if [[ -n "$pid" ]]; then
    echo "server running (pid $pid), http://127.0.0.1:$PORT / emulator http://10.0.2.2:$PORT"
  else
    echo "server not running"
  fi
  if [[ -d "$PAGES_DIR/.git" ]]; then
    echo "clone: $(git -C "$PAGES_DIR" log -1 --format='%h %cs' 2>/dev/null)"
  else
    echo "clone: missing (run '$0 start' to clone)"
  fi
  if "$ADB" get-state >/dev/null 2>&1; then
    # toybox grep 的 -F 需要 -e 传 pattern；且经 adb shell 会远端二次分词，
    # marker 里的空格/# 必须整体引号包好，否则 # 被当成注释
    if adb_shell "grep -q -F -e '$HOSTS_MARKER' /system/etc/hosts" 2>/dev/null; then
      echo "emulator hosts: privacy-test-pages block present"
    else
      echo "emulator hosts: NOT configured (run '$0 hosts')"
    fi
  else
    echo "emulator: not connected"
  fi
}

update() {
  [[ -d "$PAGES_DIR/.git" ]] || { echo "ERROR: no clone yet, run '$0 start' first" >&2; return 1; }
  git -C "$PAGES_DIR" pull --ff-only
}

case "${1:-}" in
  start) shift; start "$@" ;;
  stop) stop ;;
  status) status ;;
  hosts) hosts ;;
  update) update ;;
  *) echo "usage: $0 {start [--port N]|stop|status|hosts|update}" >&2; exit 2 ;;
esac

#!/usr/bin/env bash
# Stop ajazz-dock and leave the panel dark.
#
#   ./stop-dock.sh          # graceful: blank the LCD, sleep the device, exit
#   ./stop-dock.sh -f       # SIGKILL if it will not go quietly (leaves it lit)
#
# SIGTERM is what the runner listens for; it clears every key, sleeps the
# panel, then exits. A plain `pkill -9` skips all of that and leaves the last
# page's icons glowing on a dock nothing is driving.
set -uo pipefail

proj="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pattern="\-m ajazz_dock"
force=0
[ "${1:-}" = "-f" ] && force=1

pids=$(pgrep -f "$pattern" || true)
if [ -z "$pids" ]; then
  echo "ajazz-dock 没有在跑。"

  # A LaunchAgent would just restart it, so say so rather than let the user
  # wonder why it came back.
  if launchctl print "gui/$(id -u)/com.patricksun.ajazz-dock" >/dev/null 2>&1; then
    echo "注意: 开机自启的 agent 还装着，它会把进程拉起来。"
    echo "      要彻底停掉: ./tools/uninstall_autostart_macos.sh"
  fi
  exit 0
fi

echo "找到进程: $(echo "$pids" | tr '\n' ' ')"

if [ "$force" = "1" ]; then
  kill -9 $pids 2>/dev/null || true
  echo "已强制结束（LCD 上的图标会留着）。"
  exit 0
fi

kill -TERM $pids 2>/dev/null || true

# Give it room to blank the panel and sleep the device before checking.
for _ in $(seq 1 20); do
  sleep 0.25
  pgrep -f "$pattern" >/dev/null || { echo "已停止，面板已熄灭。"; break; }
done

if pgrep -f "$pattern" >/dev/null; then
  echo "20 次检查后仍在运行 —— 用 ./stop-dock.sh -f 强制结束。" >&2
  exit 1
fi

if launchctl print "gui/$(id -u)/com.patricksun.ajazz-dock" >/dev/null 2>&1; then
  echo "注意: 开机自启的 agent 还装着，它会重新拉起进程。"
  echo "      要彻底停掉: ./tools/uninstall_autostart_macos.sh"
fi

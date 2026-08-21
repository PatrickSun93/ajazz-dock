#!/usr/bin/env bash
# Remove the login item created by tools/install_autostart_macos.sh.
#
#   ./tools/uninstall_autostart_macos.sh
set -euo pipefail

label="com.patricksun.ajazz-dock"
plist="$HOME/Library/LaunchAgents/$label.plist"

if launchctl print "gui/$(id -u)/$label" >/dev/null 2>&1; then
  launchctl bootout "gui/$(id -u)/$label"
  echo "已停止并卸载 agent: $label"
else
  echo "agent 未在运行。"
fi

if [ -f "$plist" ]; then
  rm -f "$plist"
  echo "已删除 plist: $plist"
else
  echo "plist 不存在，无需清理。"
fi
echo "（开机自启已取消。已在跑的进程不受影响，除非上面停掉了它。）"

#!/usr/bin/env bash
# Make ajazz-dock start at every login (current user), via a LaunchAgent.
#
#   ./tools/install_autostart_macos.sh
#   ./tools/install_autostart_macos.sh settings.macos.json
#   PYTHON=/opt/homebrew/bin/python3 ./tools/install_autostart_macos.sh
#
# This is the macOS counterpart of tools/install_autostart.ps1. A LaunchAgent
# (not a LaunchDaemon) is the right choice for the same reason the Windows side
# uses the Startup folder rather than a Service: agents run inside your login
# session, so they can launch apps into your desktop. A daemon runs before
# login with no session to talk to.
#
# Two things this handles that a naive plist does not:
#
#   1. PATH. launchd does not read your shell profile, so a bare plist gets a
#      minimal PATH -- no homebrew, no ~/.local/bin, meaning `claude` and
#      friends silently vanish from `shell` actions. PATH is set explicitly.
#
#   2. The device not being ready at login. KeepAlive restarts the runner if it
#      exits, so a dock plugged in after login still gets picked up instead of
#      staying dark until you notice.
set -euo pipefail

proj="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config="${1:-settings.macos.json}"
python_bin="${PYTHON:-$proj/.venv/bin/python}"

label="com.patricksun.ajazz-dock"
plist="$HOME/Library/LaunchAgents/$label.plist"

if [ ! -x "$python_bin" ]; then
  echo "python 找不到: $python_bin" >&2
  echo "提示: python3 -m venv .venv && ./.venv/bin/pip install -e ." >&2
  exit 1
fi
if [ ! -f "$proj/$config" ]; then
  echo "配置找不到: $proj/$config" >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$label</string>

  <key>ProgramArguments</key>
  <array>
    <string>$python_bin</string>
    <string>-u</string>
    <string>-m</string>
    <string>ajazz_dock</string>
    <string>$config</string>
  </array>

  <key>WorkingDirectory</key>
  <string>$proj</string>

  <!-- launchd gives a minimal PATH; without this, \`claude\`, \`osascript\`
       lookups and homebrew binaries disappear from shell actions. -->
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin</string>
  </dict>

  <key>RunAtLoad</key>
  <true/>

  <!-- Restart on exit, so a dock plugged in after login gets picked up. -->
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>10</integer>

  <key>StandardOutPath</key>
  <string>$proj/dock.log</string>
  <key>StandardErrorPath</key>
  <string>$proj/dock.log</string>
</dict>
</plist>
PLIST

# bootout first so a re-run replaces the running agent instead of erroring.
launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$plist"

echo "已安装 —— ajazz-dock 会在每次登录时自动启动。"
echo "  plist:  $plist"
echo "  配置:   $proj/$config"
echo "  日志:   $proj/dock.log"
echo "  查状态: launchctl print gui/$(id -u)/$label | head -20"
echo "  看日志: tail -f $proj/dock.log"
echo "  卸载:   ./tools/uninstall_autostart_macos.sh"
echo
echo "注意: 若配置里用到 keys 类动作（发送快捷键），需要在"
echo "「系统设置 > 隐私与安全性 > 辅助功能」里授权，且授权对象是这个"
echo "launchd 进程本身，不是你的终端。当前的 settings.macos.json 没有用"
echo "keys 动作，所以不需要授权。"

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
#
#   3. Nothing in this plist points at the external volume. On a removable
#      volume, TCC refuses *launchd itself* the accesses it would make on the
#      job's behalf -- the WorkingDirectory chdir, and opening StandardOutPath
#      -- and the job dies with EX_CONFIG before the program ever runs, log
#      empty. The spawned process reads the volume fine; it is launchd's own
#      accesses that are denied. So bash does the cd and the redirect, and the
#      plist only ever names paths on the internal disk.
#      (com.patrick.personalagent.scheduler, on the same volume, gets away
#      with it the same way: no WorkingDirectory, script cds itself.)
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
    <string>/bin/bash</string>
    <string>-c</string>
    <string>cd "$proj" &amp;&amp; exec "$python_bin" -u -m ajazz_dock "$config" &gt;&gt; "$proj/dock.log" 2&gt;&amp;1</string>
  </array>

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

  <!-- Internal disk only. This catches failures from before bash gets to set
       up its own redirect into the project's dock.log. -->
  <key>StandardOutPath</key>
  <string>$HOME/Library/Logs/ajazz-dock-launchd.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/Library/Logs/ajazz-dock-launchd.log</string>
</dict>
</plist>
PLIST

# bootout first so a re-run replaces the running agent instead of erroring.
launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$plist"

# A LaunchAgent whose files live on an external volume hits TCC: launchd-spawned
# processes cannot read /Volumes/... until the binary is granted Full Disk
# Access, and a background process cannot raise the consent prompt -- so it just
# dies with EX_CONFIG and an empty log. Check for it rather than let the user
# hunt for a silent failure.
sleep 4
if ! pgrep -f "\-m ajazz_dock" >/dev/null 2>&1 && [[ "$proj" == /Volumes/* ]]; then
  real=$("$python_bin" -c 'import os,sys;print(os.path.realpath(sys.executable))' 2>/dev/null)
  app="${real%/bin/*}/Resources/Python.app"
  echo
  echo "⚠️  agent 起不来 —— 项目在外置盘，解释器没有「完全磁盘访问权限」。"
  echo
  echo "   TCC 是按可执行文件授权的。/bin/bash 若已授权，它能 cd 进外置盘、"
  echo "   也能写日志（所以 plist 看着没毛病），但 python 自己读不了外置盘上的"
  echo "   .py 和 site-packages —— 于是进程起来了却一行输出都没有，"
  echo "   或者直接 exit 78。"
  echo
  echo "   解决：系统设置 > 隐私与安全性 > 完全磁盘访问权限 > 点 + ，添加"
  [ -d "$app" ] && echo "     $app" || echo "     $real"
  echo "   （Finder 里按 Cmd+Shift+G 粘贴这个路径就能选到）"
  echo "   加完重新跑这个脚本。"
  echo
  echo "   不想授权就手动起（终端关掉也会继续跑，但重启电脑要再来一次）："
  echo "     cd $proj && nohup ./.venv/bin/python -u -m ajazz_dock $config >> dock.log 2>&1 &"
  exit 1
fi

echo "已安装 —— ajazz-dock 会在每次登录时自动启动。"
echo "  plist:  $plist"
echo "  配置:   $proj/$config"
echo "  日志:   $proj/dock.log"
echo "  启动日志: $HOME/Library/Logs/ajazz-dock-launchd.log（launchd 自己的报错）"
echo "  查状态: launchctl print gui/$(id -u)/$label | head -20"
echo "  看日志: tail -f $proj/dock.log"
echo "  卸载:   ./tools/uninstall_autostart_macos.sh"
echo
echo "注意: 若配置里用到 keys 类动作（发送快捷键），需要在"
echo "「系统设置 > 隐私与安全性 > 辅助功能」里授权，且授权对象是这个"
echo "launchd 进程本身，不是你的终端。当前的 settings.macos.json 没有用"
echo "keys 动作，所以不需要授权。"

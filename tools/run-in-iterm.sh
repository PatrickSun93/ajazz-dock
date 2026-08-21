#!/usr/bin/env bash
# Open ONE new iTerm window, cd to a folder, and run a command there.
# Used by the dock's `shell` actions -- both for per-project Claude Code
# launchers and for anything whose output you need to SEE (devstack status,
# a dev server). A bare `shell` action would swallow all of that.
#
#   ./tools/run-in-iterm.sh /path/to/project
#   ./tools/run-in-iterm.sh /path/to/project "npm run dev"
#
# Default command is Claude Code with permissions skipped -- same as the
# $CLAUDE shorthand in ~/bin/claude-sessions.sh.
set -euo pipefail

dir="${1:?usage: run-in-iterm.sh <dir> [command]}"
cmd="${2:-claude --dangerously-skip-permissions}"

[ -d "$dir" ] || { echo "no such dir: $dir" >&2; exit 1; }

# Escape backslashes then double-quotes for embedding in an AppleScript string.
esc() { printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'; }

osascript <<APPLESCRIPT
tell application "iTerm"
  activate
  set w to (create window with default profile)
  tell current session of w
    write text "cd \"$(esc "$dir")\" && $(esc "$cmd")"
  end tell
end tell
APPLESCRIPT

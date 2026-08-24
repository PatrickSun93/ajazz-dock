#!/usr/bin/env bash
# Close the Claude Code session running in a given project directory.
#
#   ./tools/close-claude-session.sh /path/to/project
#   ./tools/close-claude-session.sh --all      # every session except protected
#   ./tools/close-claude-session.sh --list     # show what is running, touch nothing
#   ./tools/close-claude-session.sh -f <dir>   # SIGKILL if it will not go quietly
#
# Sessions are matched by working directory, read via lsof -d cwd, because the
# command line is identical across all of them.
#
# ── Two things this refuses to kill ─────────────────────────────────────────
#
#   1. Anything under personalAgent-wsl. It is the mail/calendar agent, it runs
#      silently in the background, and nothing tells you when it is not running
#      -- so a stray kill costs a batch of unprocessed mail before anyone
#      notices. devstack.sh carves out the same exception for the same reason.
#
#   2. The VS Code extension's helper process, whose argv points into
#      .vscode/extensions. It shares the `claude` process name with real
#      terminal sessions but closing it just breaks the editor integration.
set -uo pipefail

PROTECTED_DIRS=(
  "/Volumes/externalssd/devitems/ai-agents/personalAgent-wsl"
)

force=0
if [ "${1:-}" = "-f" ]; then
  force=1
  shift
fi
target="${1:-}"

if [ -z "$target" ]; then
  echo "用法: close-claude-session.sh [-f] <目录> | --all | --list" >&2
  exit 2
fi

is_protected() {
  local dir="$1" guard
  for guard in "${PROTECTED_DIRS[@]}"; do
    case "$dir" in
      "$guard"|"$guard"/*) return 0 ;;
    esac
  done
  return 1
}

cwd_of() {
  lsof -a -p "$1" -d cwd -Fn 2>/dev/null | grep '^n' | cut -c2- | head -1
}

# Emits "pid<TAB>cwd" for each real terminal session.
sessions() {
  local pid args dir
  for pid in $(pgrep -x claude 2>/dev/null); do
    args=$(ps -o args= -p "$pid" 2>/dev/null)
    case "$args" in
      *.vscode/extensions/*) continue ;;   # editor helper, not a session
    esac
    dir=$(cwd_of "$pid")
    [ -n "$dir" ] && printf '%s\t%s\n' "$pid" "$dir"
  done
}

if [ "$target" = "--list" ]; then
  found=0
  while IFS=$'\t' read -r pid dir; do
    found=1
    if is_protected "$dir"; then
      printf "  pid %-7s %s   [受保护，不会被关闭]\n" "$pid" "$dir"
    else
      printf "  pid %-7s %s\n" "$pid" "$dir"
    fi
  done < <(sessions)
  [ "$found" = "0" ] && echo "  没有正在运行的 Claude Code 会话。"
  exit 0
fi

signal=TERM
[ "$force" = "1" ] && signal=KILL

closed=0
skipped=0
while IFS=$'\t' read -r pid dir; do
  if [ "$target" != "--all" ]; then
    # Match the directory itself or anything beneath it.
    case "$dir" in
      "$target"|"$target"/*) ;;
      *) continue ;;
    esac
  fi

  if is_protected "$dir"; then
    echo "跳过（受保护）: $dir"
    skipped=$((skipped + 1))
    continue
  fi

  if kill -"$signal" "$pid" 2>/dev/null; then
    echo "已关闭 pid $pid  $dir"
    closed=$((closed + 1))
  else
    echo "关闭失败 pid $pid  $dir" >&2
  fi
done < <(sessions)

if [ "$closed" = "0" ] && [ "$skipped" = "0" ]; then
  if [ "$target" = "--all" ]; then
    echo "没有可关闭的会话。"
  else
    echo "该目录下没有正在运行的会话: $target"
  fi
fi
exit 0

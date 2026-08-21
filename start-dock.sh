#!/usr/bin/env bash
# Launch ajazz-dock on macOS, logging to dock.log.
#
#   ./start-dock.sh                       # uses settings.macos.json
#   ./start-dock.sh other-settings.json
#
# PYTHON can override the interpreter:
#   PYTHON=/opt/homebrew/bin/python3 ./start-dock.sh
set -euo pipefail

proj="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$proj"

python_bin="${PYTHON:-$proj/.venv/bin/python}"
config="${1:-settings.macos.json}"

if [ ! -x "$python_bin" ]; then
  echo "python not found: $python_bin" >&2
  echo "hint: python3 -m venv .venv && ./.venv/bin/pip install -e ." >&2
  exit 1
fi

exec "$python_bin" -u -m ajazz_dock "$config" >> "$proj/dock.log" 2>&1

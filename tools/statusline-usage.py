#!/usr/bin/env python3
"""
Claude Code statusline hook that also publishes rate-limit data for the dock.

Claude Code invokes this once per turn with a JSON blob on stdin. Since 2.1.x
that blob carries `rate_limits` for Pro/Max subscribers -- the same numbers
/usage shows, with no API call. That is the only place those figures exist
outside /usage itself; nothing is written to disk otherwise, which is why the
dock previously had to estimate them from token totals.

So this does two jobs:
  1. prints one status line for the terminal
  2. writes the rate limits to RATE_LIMITS for ajazz-dock to read

Deliberately stdlib-only and run under /usr/bin/python3: it must not depend on
the external SSD, which is not always mounted, and it runs on every turn.

Install: copy to ~/.claude/ (NOT run from the repo -- that lives on an external
volume which is not always mounted, and a statusline that fails takes the
terminal's status line with it), then in ~/.claude/settings.json:

    "statusLine": {
      "type": "command",
      "command": "/usr/bin/python3 /Users/<you>/.claude/statusline-usage.py"
    }

Field names confirmed against Claude Code 2.1.241:
    rate_limits.five_hour = {"used_percentage": 6, "resets_at": <epoch>}
    rate_limits.seven_day = {"used_percentage": 39, "resets_at": <epoch>}
They are undocumented, hence the fallback spellings in _pct().
"""

from __future__ import annotations

import json
import os
import sys
import time

HOME = os.path.expanduser("~")
RATE_LIMITS = os.path.join(HOME, ".claude", "rate-limits.json")
# Full payload, kept so the schema can be inspected when Claude Code changes it.
LAST_PAYLOAD = os.path.join(HOME, ".claude", "statusline-last.json")


def _write_atomic(path: str, data: dict) -> None:
    """Rename into place -- the dock may read this at any moment."""
    tmp = f"{path}.tmp{os.getpid()}"
    try:
        with open(tmp, "w") as handle:
            json.dump(data, handle, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _pct(entry) -> float | None:
    """Pull a used-percentage out of a rate-limit entry, whatever it is called.

    The field name is not documented and has moved around between versions, so
    accept the plausible spellings rather than pin one.
    """
    if not isinstance(entry, dict):
        return None
    # Confirmed against Claude Code 2.1.241: used_percentage, already 0..100.
    # Take it literally -- guessing the scale would read a genuine 1% as 100%.
    value = entry.get("used_percentage")
    if isinstance(value, (int, float)):
        return float(value)

    # Undocumented field that has moved between versions, so keep fallbacks.
    # Only these get scale-guessed, and only 0..1 exclusive of 1 -- same
    # reasoning: a bare 1 is far likelier to mean one percent than all of it.
    for key in ("utilization", "used_pct", "used_percent",
                "percent_used", "percentage", "usage_percent", "pct"):
        value = entry.get(key)
        if isinstance(value, (int, float)):
            return value * 100 if 0 <= value < 1 else float(value)
    used, limit = entry.get("used"), entry.get("limit")
    if isinstance(used, (int, float)) and isinstance(limit, (int, float)) and limit:
        return 100.0 * used / limit
    return None


def _resets_at(entry) -> str | None:
    if not isinstance(entry, dict):
        return None
    for key in ("resets_at", "reset_at", "resets", "reset", "resetsAt"):
        value = entry.get(key)
        if isinstance(value, (str, int, float)):
            return str(value)
    return None


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (ValueError, OSError):
        payload = {}

    if payload:
        _write_atomic(LAST_PAYLOAD, payload)

    limits = payload.get("rate_limits") or {}
    five, week = limits.get("five_hour"), limits.get("seven_day")
    snapshot = {
        "captured_at": time.time(),
        "five_hour": {"pct_used": _pct(five), "resets_at": _resets_at(five),
                      "raw": five},
        "seven_day": {"pct_used": _pct(week), "resets_at": _resets_at(week),
                      "raw": week},
        "available": bool(limits),
    }
    _write_atomic(RATE_LIMITS, snapshot)

    # ---- the visible status line ----
    bits = []
    model = (payload.get("model") or {}).get("display_name")
    if model:
        bits.append(model)

    for label, entry in (("5h", snapshot["five_hour"]),
                         ("7d", snapshot["seven_day"])):
        pct = entry["pct_used"]
        if pct is not None:
            bits.append(f"{label} {100 - pct:.0f}% left")

    workspace = payload.get("workspace") or {}
    cwd = workspace.get("current_dir") or payload.get("cwd")
    if cwd:
        bits.append(os.path.basename(cwd.rstrip("/")))

    print(" · ".join(bits) if bits else "claude")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

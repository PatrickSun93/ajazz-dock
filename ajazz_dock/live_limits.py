"""
Real rate-limit figures, published by the Claude Code statusline hook.

Since Claude Code 2.1.x the JSON it hands its statusline command on stdin
carries a `rate_limits` block for Pro/Max subscribers -- the same numbers
/usage prints, with no API call. ~/.claude/statusline-usage.py captures that
into RATE_LIMITS every turn.

This is the difference between reporting a quota and estimating one. Everything
in claude_usage.py works backwards from token totals against a hand-calibrated
denominator; these are the actual percentages. So the strip prefers these and
falls back to the estimate only when they are missing or stale -- no hook
installed, an older Claude Code, a Console account rather than a subscription,
or simply no session open recently enough to have refreshed the file.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime

RATE_LIMITS = os.path.expanduser("~/.claude/rate-limits.json")

# A snapshot only refreshes while some Claude Code session is taking turns.
# Past this it describes a window that has probably moved on, and a stale
# percentage shown as current is worse than an honest estimate.
MAX_AGE_SECONDS = 30 * 60


def _parse_reset(value) -> float | None:
    """Accept an ISO 8601 string or an epoch number, in seconds or millis."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Anything this large is milliseconds -- year 33658 in seconds.
        return float(value) / 1000 if value > 1e11 else float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        pass
    try:
        number = float(text)
    except ValueError:
        return None
    return number / 1000 if number > 1e11 else number


def read() -> dict | None:
    """Latest snapshot, or None if absent, unreadable, stale, or empty.

    Returns {"five_hour": {...}, "seven_day": {...}, "age": seconds} where each
    window carries pct_used, pct_left, reset (epoch) and seconds_left.
    """
    try:
        with open(RATE_LIMITS) as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None

    if not data.get("available"):
        return None

    captured = data.get("captured_at")
    if not isinstance(captured, (int, float)):
        return None
    age = time.time() - captured
    if age > MAX_AGE_SECONDS:
        return None

    now = time.time()
    out: dict = {"age": age}
    for key in ("five_hour", "seven_day"):
        entry = data.get(key) or {}
        pct_used = entry.get("pct_used")
        if not isinstance(pct_used, (int, float)):
            out[key] = None
            continue
        reset = _parse_reset(entry.get("resets_at"))
        out[key] = {
            "pct_used": float(pct_used),
            "pct_left": max(0.0, min(100.0, 100.0 - float(pct_used))),
            "reset": reset,
            "seconds_left": max(0.0, reset - now) if reset else None,
        }
    if out.get("five_hour") is None and out.get("seven_day") is None:
        return None
    return out

"""
Real rate-limit figures, published by the Claude Code statusline hook.

Since Claude Code 2.1.x the JSON it hands its statusline command on stdin
carries a `rate_limits` block for Pro/Max subscribers -- the same numbers
/usage prints, with no API call. ~/.claude/statusline-usage.py captures that
into RATE_LIMITS every turn.

This is the difference between reporting a quota and estimating one, and the
gap is not small. Measured 2026-08-28: the real weekly figure was 31% left
while the token estimate said 56%. Every candidate proxy -- output tokens,
output plus cache writes, total tokens, message count -- drifted 0.6-0.8x
against a calibration taken four days earlier, and the weekly denominator
itself moves (a promo altered it by roughly the 1.5x the drift showed). The
weighting is not published and the quota is not constant, so no local sum
reproduces it.

That is why a stale snapshot is preferred over a fresh estimate: an hour-old
real number is close, and the estimate is not merely imprecise but biased
toward *overstating* what remains -- the direction that gets you cut off
mid-task. The estimate is a last resort for hosts with no hook at all.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime

RATE_LIMITS = os.path.expanduser("~/.claude/rate-limits.json")

# A snapshot only refreshes while some Claude Code session is taking turns.
# Past this it is reported as stale rather than dropped: an old real figure
# still beats the estimate, which cannot be trusted at all (see below).
STALE_AFTER_SECONDS = 30 * 60

# Eventually it is describing a window that has certainly rolled over. A 5h
# window cannot outlive this, so nothing older is worth showing.
MAX_AGE_SECONDS = 6 * 3600


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
    out: dict = {"age": age, "stale": age > STALE_AFTER_SECONDS}
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

"""
Token usage read out of Claude Code's local session logs.

Claude Code appends one JSON object per message to
~/.claude/projects/<slug>/<session>.jsonl. Assistant messages carry a `usage`
block; summing those is the only local record of consumption -- there is no
rollup file and no subscription quota on disk, so this reports absolute
tokens, never "percent of limit".

The 5h bucket is the one that matters: Claude Code's rate limit is a rolling
five-hour window, so that number is what predicts getting cut off.
"""

from __future__ import annotations

import glob
import json
import math
import os
import time
from datetime import datetime

LOGS = os.path.expanduser("~/.claude/projects/*/*.jsonl")

# Only open recently-touched files. There are hundreds of old sessions and a
# full scan costs seconds we do not have on a status refresh.
SCAN_DAYS = 8

WINDOWS = ("5h", "today", "7d", "week")

WINDOW_SECONDS = 5 * 3600

# There is no quota anywhere on disk -- not in the logs, not in ~/.claude, and
# the CLI has no `usage` subcommand. /usage reads it live from the API and
# never writes it down. So a percentage needs a baseline the user supplies.
DEFAULT_LIMIT_OUT = 2_500_000

# The real cap is weekly, not the 5h window. Calibrated 2026-08-24 against a
# /usage reading of "Current week (all models) 37% used": 10.31M output tokens
# had been spent into that 37%, so 100% lands near 27.9M. Recalibrate the same
# way whenever /usage disagrees -- output tokens are a proxy for whatever
# Anthropic actually weighs, not the weighing itself.
DEFAULT_WEEK_LIMIT_OUT = 27_900_000

# Weeks roll on a fixed 7-day cadence. This is a real observed reset instant;
# every later one is this plus a multiple of 7 days.
DEFAULT_WEEK_ANCHOR = "2026-08-28T17:00:00"
WEEK_SECONDS = 7 * 86400


def _empty() -> dict[str, int]:
    return {"in": 0, "out": 0, "cache_w": 0, "cache_r": 0, "msgs": 0}


def _window_starts(week_start: float) -> dict[str, float]:
    now = time.time()
    midnight = datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0).timestamp()
    return {"5h": now - 5 * 3600, "today": midnight, "7d": now - 7 * 86400,
            "week": week_start}


def _active_window_start(times: list[float]) -> float | None:
    """Start of the 5h window that is currently open.

    A window opens on a message, lasts five hours, then lapses; the next
    message after it lapses opens a fresh one. Walking forward from the oldest
    message reproduces that chain. Returns None when the last window already
    lapsed -- i.e. the next message starts from zero.
    """
    if not times:
        return None
    times = sorted(times)
    start = times[0]
    i = 0
    while True:
        end = start + WINDOW_SECONDS
        following = None
        while i < len(times):
            if times[i] >= end:
                following = times[i]
                break
            i += 1
        if following is None:
            break
        start = following
    return start if start + WINDOW_SECONDS > time.time() else None


def week_bounds(anchor_iso: str = DEFAULT_WEEK_ANCHOR) -> tuple[float, float]:
    """(start, reset) of the weekly quota period containing right now.

    The anchor is one real reset instant; periods repeat every 7 days from it,
    forwards and backwards, so any anchor from any week gives the same answer.
    """
    try:
        anchor = datetime.fromisoformat(anchor_iso).timestamp()
    except ValueError:
        anchor = datetime.fromisoformat(DEFAULT_WEEK_ANCHOR).timestamp()
    now = time.time()
    periods = math.ceil((now - anchor) / WEEK_SECONDS)
    reset = anchor + periods * WEEK_SECONDS
    return reset - WEEK_SECONDS, reset


def collect(limit_out: int = DEFAULT_LIMIT_OUT,
            week_limit_out: int = DEFAULT_WEEK_LIMIT_OUT,
            week_anchor: str = DEFAULT_WEEK_ANCHOR) -> dict:
    """Scan the logs once. Costs about half a second on a few hundred files."""
    week_start, week_reset = week_bounds(week_anchor)
    starts = _window_starts(week_start)
    buckets = {name: _empty() for name in WINDOWS}
    models: dict[str, int] = {}
    stamps: list[tuple[float, int]] = []
    cutoff = time.time() - SCAN_DAYS * 86400

    for path in glob.glob(LOGS):
        try:
            if os.path.getmtime(path) < cutoff:
                continue
        except OSError:
            continue
        try:
            with open(path, errors="ignore") as handle:
                for line in handle:
                    # Cheap reject before the JSON parse -- most lines are
                    # user turns and tool results with no usage block at all.
                    if '"usage"' not in line:
                        continue
                    try:
                        record = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    message = record.get("message") or {}
                    usage = message.get("usage")
                    stamp = record.get("timestamp")
                    if not usage or not stamp:
                        continue
                    try:
                        when = datetime.fromisoformat(
                            stamp.replace("Z", "+00:00")).timestamp()
                    except ValueError:
                        continue

                    values = {
                        "in": usage.get("input_tokens") or 0,
                        "out": usage.get("output_tokens") or 0,
                        "cache_w": usage.get("cache_creation_input_tokens") or 0,
                        "cache_r": usage.get("cache_read_input_tokens") or 0,
                    }
                    model = message.get("model") or "?"
                    models[model] = models.get(model, 0) + values["out"]
                    stamps.append((when, values['out']))

                    for name, start in starts.items():
                        if when >= start:
                            bucket = buckets[name]
                            for key, value in values.items():
                                bucket[key] += value
                            bucket["msgs"] += 1
        except OSError:
            continue

    for bucket in buckets.values():
        bucket["total"] = (bucket["in"] + bucket["out"]
                           + bucket["cache_w"] + bucket["cache_r"])

    start = _active_window_start([t for t, _ in stamps])
    now = time.time()
    if start is None:
        # Nothing in the last five hours: the next message opens a fresh window.
        window = {
            "open": False, "start": None, "reset": None,
            "seconds_left": WINDOW_SECONDS, "out": 0, "msgs": 0,
            "limit": limit_out, "pct_left": 100.0,
        }
    else:
        inside = [out for when, out in stamps if when >= start]
        used = sum(inside)
        pct_left = 100.0 if limit_out <= 0 else max(
            0.0, min(100.0, 100.0 * (1 - used / limit_out)))
        window = {
            "open": True, "start": start, "reset": start + WINDOW_SECONDS,
            "seconds_left": max(0.0, start + WINDOW_SECONDS - now),
            "out": used, "msgs": len(inside),
            "limit": limit_out, "pct_left": pct_left,
        }
    wb = buckets["week"]
    week_pct_left = 100.0 if week_limit_out <= 0 else max(
        0.0, min(100.0, 100.0 * (1 - wb["out"] / week_limit_out)))
    week = {
        "start": week_start, "reset": week_reset,
        "seconds_left": max(0.0, week_reset - now),
        "out": wb["out"], "msgs": wb["msgs"],
        "limit": week_limit_out, "pct_left": week_pct_left,
    }
    return {"buckets": buckets, "models": models,
            "window": window, "week": week}


def fmt(n: int) -> str:
    """Compact enough to fit on a 95px LCD tile."""
    if n >= 1_000_000_000:
        return f"{n / 1e9:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1e6:.1f}M"
    if n >= 1_000:
        return f"{n / 1e3:.0f}k"
    return str(n)

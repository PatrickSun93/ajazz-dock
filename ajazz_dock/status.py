"""
The three status slots (16, 17, 18).

The AKP153E has three display-only slots above the 15 keys -- a strip the
device never sends input for. `set_image` addresses them exactly like a key,
so they make a decent little dashboard.

Threading: the updater thread only *computes* tiles. It never touches the
device. Rendered images land in a pending dict that the runner's main loop
drains, so every HID write still happens on one thread -- reading and writing
the same hidapi handle from two threads is not worth the risk for a status
readout that can wait 100ms.

Config shape:

    "status": {
      "refresh": 60,
      "slots": {
        "16": { "type": "claude_usage", "window": "5h" },
        "17": { "type": "claude_usage", "window": "today" },
        "18": { "type": "page" }
      }
    }
"""

from __future__ import annotations

import threading
import time
import traceback
from typing import Any, Callable, Mapping

from PIL import Image, ImageDraw, ImageFont

from . import claude_usage, live_limits

SLOT_MIN, SLOT_MAX = 16, 18
SIZE = 256

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    r"C:\Windows\Fonts\segoeuib.ttf",
]

GROUND = (14, 16, 20)
VALUE_INK = (255, 255, 255)
SUB_INK = (150, 162, 175)

# Accent per usage window, so the three tiles are told apart at a glance.
WINDOW_ACCENT = {
    "5h":    (0x1F, 0x7A, 0x8C),
    "today": (0x2E, 0x6B, 0x4F),
    "7d":    (0x6B, 0x4A, 0x8C),
}
WINDOW_LABEL = {"5h": "5H", "today": "今日", "7d": "7天"}
DEFAULT_ACCENT = (0x44, 0x50, 0x5C)


def _font(px: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, px)
        except OSError:
            continue
    return ImageFont.load_default()


def _centered(draw, text, font, center_y: int, fill) -> None:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text(((SIZE - (right - left)) / 2 - left,
               center_y - (bottom - top) / 2 - top), text, font=font, fill=fill)


def render(label: str, value: str, sub: str, accent) -> Image.Image:
    """A tile: coloured band naming the metric, big number, small footnote."""
    img = Image.new("RGB", (SIZE, SIZE), GROUND)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, SIZE - 1, 46], fill=tuple(accent))
    _centered(draw, label, _font(34), 23, VALUE_INK)

    # Shrink the headline until it clears the margins -- "12.0M" overflows at
    # the size "2.0M" wants.
    px = 82
    font = _font(px)
    while px > 30:
        left, _, right, _ = draw.textbbox((0, 0), value, font=font)
        if (right - left) <= SIZE - 28:
            break
        px -= 4
        font = _font(px)
    _centered(draw, value, font, 130, VALUE_INK)

    if sub:
        _centered(draw, sub, _font(30), 205, SUB_INK)
    return img


# ---- providers ----------------------------------------------------------
# Each returns (label, value, sub, accent) or None to leave the slot alone.

def _provider_claude_usage(spec: Mapping[str, Any], ctx: Mapping[str, Any]):
    data = ctx.get("usage")
    if not data:
        return None
    window = str(spec.get("window", "5h"))
    bucket = data["buckets"].get(window)
    if not bucket:
        return None
    metric = str(spec.get("metric", "out"))
    value = claude_usage.fmt(bucket.get(metric, 0))
    label = spec.get("label") or WINDOW_LABEL.get(window, window)
    sub = spec.get("sub")
    if sub is None:
        sub = f"{claude_usage.fmt(bucket['msgs'])} 条"
    accent = spec.get("accent") or WINDOW_ACCENT.get(window, DEFAULT_ACCENT)
    if isinstance(accent, str):
        accent = tuple(int(accent.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    return label, value, sub, accent


def _provider_page(spec: Mapping[str, Any], ctx: Mapping[str, Any]):
    pages = ctx.get("pages") or []
    index = ctx.get("page_index", 0)
    if not pages:
        return None
    name = str(pages[index].get("name", index + 1))
    accent = spec.get("accent") or DEFAULT_ACCENT
    if isinstance(accent, str):
        accent = tuple(int(accent.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    return spec.get("label", "页"), name, f"{index + 1}/{len(pages)}", accent


def _provider_clock(spec: Mapping[str, Any], ctx: Mapping[str, Any]):
    accent = spec.get("accent") or DEFAULT_ACCENT
    if isinstance(accent, str):
        accent = tuple(int(accent.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    return (spec.get("label", "时间"), time.strftime("%H:%M"),
            time.strftime("%m-%d"), accent)


def _accent(spec, fallback):
    accent = spec.get("accent") or fallback
    if isinstance(accent, str):
        accent = tuple(int(accent.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    return accent


# Percentage bands. These colour the band, so the strip reads without
# actually parsing the number.
PCT_OK, PCT_WARN, PCT_LOW = (0x2E, 0x6B, 0x4F), (0xB0, 0x7A, 0x1E), (0xA8, 0x37, 0x22)
# A snapshot nobody has refreshed lately. Greyed so it does not read as current.
STALE_BAND = (0x4A, 0x50, 0x58)


def _age_note(live: Mapping[str, Any]) -> str:
    minutes = int(live.get("age", 0) // 60)
    return f"{minutes // 60}小时前" if minutes >= 60 else f"{minutes}分钟前"


def _band(pct: float):
    return PCT_OK if pct >= 50 else PCT_WARN if pct >= 20 else PCT_LOW


def _provider_claude_pct(spec: Mapping[str, Any], ctx: Mapping[str, Any]):
    """Share of the 5h quota left.

    Prefers the real figure published by the statusline hook. Falls back to the
    token estimate against a hand-set baseline, and marks it with ~ so a guess
    is never mistaken for the real thing.
    """
    snapshot = ctx.get("live") or {}
    live = snapshot.get("five_hour")
    if live:
        stale = snapshot.get("stale")
        # A lapsed window means the quota came back; saying 80% would be wrong
        # in the one direction that matters.
        if stale and live.get("seconds_left") == 0:
            return (spec.get("label", "5H"), "?", "窗口已过", STALE_BAND)
        if stale:
            return (spec.get("label", "5H"), f"{live['pct_left']:.0f}%",
                    _age_note(snapshot), STALE_BAND)
        sub = (time.strftime("%H:%M", time.localtime(live["reset"]))
               if live.get("reset") else "实时")
        return (spec.get("label", "5H"), f"{live['pct_left']:.0f}%",
                spec.get("sub", sub), _accent(spec, _band(live["pct_left"])))

    data = ctx.get("usage")
    if not data or "window" not in data:
        return None
    window = data["window"]
    pct = window["pct_left"]
    sub = f"~{claude_usage.fmt(window['out'])}/{claude_usage.fmt(window['limit'])}"
    return (spec.get("label", "5H~"), f"{pct:.0f}%", spec.get("sub", sub),
            _accent(spec, _band(pct)))


def _fmt_left(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes >= 60:
        return f"{minutes // 60}h{minutes % 60:02d}"
    return f"{minutes}分"


def _provider_claude_reset(spec: Mapping[str, Any], ctx: Mapping[str, Any]):
    """Time left on the current 5h window."""
    snapshot = ctx.get("live") or {}
    live = snapshot.get("five_hour")
    if live and live.get("seconds_left") is not None:
        left = live["seconds_left"]
        if snapshot.get("stale"):
            if left == 0:
                return spec.get("label", "重置"), "已过", _age_note(snapshot), STALE_BAND
            return (spec.get("label", "重置"), _fmt_left(left),
                    _age_note(snapshot), STALE_BAND)
        band = PCT_LOW if left <= 1800 else _accent(spec, (0x1F, 0x7A, 0x8C))
        return (spec.get("label", "重置"), _fmt_left(left),
                time.strftime("%H:%M", time.localtime(live["reset"])), band)

    data = ctx.get("usage")
    if not data or "window" not in data:
        return None
    window = data["window"]
    label = spec.get("label", "重置")
    if not window["open"]:
        return label, "空闲", "窗口未开", _accent(spec, DEFAULT_ACCENT)
    minutes = int(window["seconds_left"] // 60)
    value = _fmt_left(window["seconds_left"])
    # Under 30 minutes the reset is the thing you are waiting for, so flag it.
    band = PCT_LOW if minutes <= 30 else _accent(spec, (0x1F, 0x7A, 0x8C))
    sub = time.strftime("%H:%M", time.localtime(window["reset"]))
    return label, value, spec.get("sub", sub), band


def _provider_claude_week_pct(spec: Mapping[str, Any], ctx: Mapping[str, Any]):
    """Share of the weekly quota left -- the cap that actually binds.

    /usage reports a weekly figure and a session figure; the weekly one is what
    runs out. The baseline is calibrated against a real /usage reading rather
    than guessed (see claude_usage.DEFAULT_WEEK_LIMIT_OUT).
    """
    snapshot = ctx.get("live") or {}
    live = snapshot.get("seven_day")
    if live:
        # A weekly window outlives any staleness we tolerate, so the figure is
        # still meaningful -- just flag how old it is.
        if snapshot.get("stale"):
            return (spec.get("label", "本周"), f"{live['pct_left']:.0f}%",
                    _age_note(snapshot), STALE_BAND)
        sub = (time.strftime("%m-%d %H:%M", time.localtime(live["reset"]))
               if live.get("reset") else "实时")
        return (spec.get("label", "本周"), f"{live['pct_left']:.0f}%",
                spec.get("sub", sub), _accent(spec, _band(live["pct_left"])))

    data = ctx.get("usage")
    if not data or "week" not in data:
        return None
    week = data["week"]
    pct = week["pct_left"]
    band = _band(pct)
    sub = f"~{claude_usage.fmt(week['out'])}/{claude_usage.fmt(week['limit'])}"
    # One decimal place. Against a ~28M denominator a whole percent is about
    # half a day of work, so an integer reading sits still long enough to look
    # broken.
    return (spec.get("label", "本周"), f"{pct:.1f}%", spec.get("sub", sub),
            _accent(spec, band))


def _provider_claude_week_reset(spec: Mapping[str, Any], ctx: Mapping[str, Any]):
    """Time until the weekly quota rolls over."""
    data = ctx.get("usage")
    if not data or "week" not in data:
        return None
    week = data["week"]
    left = week["seconds_left"]
    if left >= 86400:
        days, hours = int(left // 86400), int((left % 86400) // 3600)
        value = f"{days}天{hours}h" if hours else f"{days}天"
    else:
        hours, minutes = int(left // 3600), int((left % 3600) // 60)
        value = f"{hours}h{minutes:02d}" if hours else f"{minutes}分"
    # Under a day the reset is close enough to plan around.
    band = PCT_WARN if left < 86400 else (0x1F, 0x7A, 0x8C)
    sub = time.strftime("%m-%d %H:%M", time.localtime(week["reset"]))
    return spec.get("label", "重置"), value, spec.get("sub", sub), _accent(spec, band)


PROVIDERS: dict[str, Callable] = {
    "claude_week_pct": _provider_claude_week_pct,
    "claude_week_reset": _provider_claude_week_reset,
    "claude_pct": _provider_claude_pct,
    "claude_reset": _provider_claude_reset,
    "claude_usage": _provider_claude_usage,
    "page": _provider_page,
    "clock": _provider_clock,
}

# Which providers need the (comparatively slow) log scan.
NEEDS_USAGE = {"claude_usage", "claude_pct", "claude_reset",
               "claude_week_pct", "claude_week_reset"}


class StatusUpdater:
    """Computes status tiles on a timer. The runner drains `take()`."""

    def __init__(self, config: Mapping[str, Any] | None):
        config = config or {}
        raw_slots = config.get("slots") or {}
        self.slots: dict[int, dict] = {}
        for key, spec in raw_slots.items():
            slot = int(key)
            if not SLOT_MIN <= slot <= SLOT_MAX:
                print(f"[status] 忽略槽 {slot}（有效范围 {SLOT_MIN}..{SLOT_MAX}）")
                continue
            self.slots[slot] = dict(spec)

        self.refresh = max(5, int(config.get("refresh", 60)))
        self.limit = int(config.get("limit", claude_usage.DEFAULT_LIMIT_OUT))
        self.week_limit = int(config.get("week_limit",
                                         claude_usage.DEFAULT_WEEK_LIMIT_OUT))
        self.week_anchor = str(config.get("week_anchor",
                                          claude_usage.DEFAULT_WEEK_ANCHOR))
        self._lock = threading.Lock()
        self._pending: dict[int, Image.Image] = {}
        self._last: dict[int, tuple] = {}
        self._ctx: dict[str, Any] = {}
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.slots)

    def start(self) -> None:
        if not self.enabled or self._thread:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def set_context(self, **kwargs) -> None:
        """Feed in what the providers need (current page, etc.) and re-render."""
        with self._lock:
            self._ctx.update(kwargs)
        self._wake.set()

    def invalidate(self) -> None:
        """Forget what was last drawn, so the next render repaints every slot.

        Used after a reconnect: the device came back blank, but the cache still
        believes the old tiles are on screen.
        """
        with self._lock:
            self._last.clear()
        self._wake.set()

    def take(self) -> dict[int, Image.Image]:
        """Hand the runner whatever is ready. Called from the main loop."""
        with self._lock:
            pending, self._pending = self._pending, {}
        return pending

    # ---- internals ------------------------------------------------------

    def _loop(self) -> None:
        wants_usage = any(
            spec.get("type") in NEEDS_USAGE for spec in self.slots.values())
        last_scan = 0.0
        while not self._stop.is_set():
            try:
                now = time.time()
                if wants_usage and now - last_scan >= self.refresh:
                    with self._lock:
                        self._ctx["usage"] = claude_usage.collect(self.limit, self.week_limit, self.week_anchor)
                    last_scan = now
                snapshot = live_limits.read()
                with self._lock:
                    self._ctx["live"] = snapshot
                self._render_all()
            except Exception:
                print("[status] 刷新失败:")
                traceback.print_exc()
            self._wake.wait(timeout=self._next_delay())
            self._wake.clear()

    def _next_delay(self) -> float:
        """Sleep until the next thing that would change the display.

        Normally that is just the refresh interval, but when the 5h window is
        about to lapse, the numbers all change at that instant -- so land just
        after it rather than up to a full interval late.
        """
        delay = min(self.refresh, 5.0)
        with self._lock:
            usage = self._ctx.get("usage")
        window = (usage or {}).get("window") or {}
        if window.get("open") and window.get("seconds_left") is not None:
            left = float(window["seconds_left"])
            if 0 < left < self.refresh:
                delay = min(delay, left + 2)
        return max(1.0, delay)

    def _render_all(self) -> None:
        with self._lock:
            ctx = dict(self._ctx)
        for slot, spec in self.slots.items():
            provider = PROVIDERS.get(spec.get("type"))
            if provider is None:
                continue
            try:
                result = provider(spec, ctx)
            except Exception:
                print(f"[status] 槽 {slot} provider 出错:")
                traceback.print_exc()
                continue
            if result is None:
                continue
            # Re-rendering an identical tile would repaint the strip for no
            # reason, and every repaint is an HID round trip.
            if self._last.get(slot) == result:
                continue
            self._last[slot] = result
            image = render(*result)
            with self._lock:
                self._pending[slot] = image

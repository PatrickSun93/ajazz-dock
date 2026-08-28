"""
Child lock.

The dock sits on a desk within reach of small hands, and its keys stop
services, kill agent sessions, and quit applications. This makes the panel
inert until an unlock sequence is entered.

Why a key sequence and not a long press: the device reports presses only --
there is no release event in the input frame (see device.py) -- so there is
nothing to time a hold against. A sequence is the only gesture the hardware
can actually distinguish.

While locked the panel shows the same tile on every key, so which keys matter
is not visible; the unlock code is a sequence of *positions*, and identical
tiles give nothing away. Presses are matched against a sliding window, so a
burst of random presses followed by the right sequence still unlocks -- which
is exactly the situation this exists for.

Config:

    "lock": {
      "code": [1, 5, 9],       // key ids, in order
      "image": "icons/locked.png",
      "idle_minutes": 10,      // 0 disables auto-lock
      "start_locked": false
    }
"""

from __future__ import annotations

import time
from typing import Any, Mapping, Sequence


class ChildLock:
    def __init__(self, config: Mapping[str, Any] | None):
        config = config or {}
        self.code: list[int] = [int(k) for k in (config.get("code") or [])]
        self.image: str = config.get("image") or "icons/locked.png"
        self.idle_seconds: float = max(0.0, float(config.get("idle_minutes", 0)) * 60)
        # Show the step order on the unlock keys. On by default: this guards
        # against small hands, and an adult who cannot get back in is the more
        # likely failure. Set false to make every key look identical.
        self.hint: bool = bool(config.get("hint", True))
        self.hint_image: str = config.get("hint_image") or "icons/lock_%d.png"
        self.locked: bool = bool(config.get("start_locked", False)) and self.configured

        self._buffer: list[int] = []
        self._last_press: float = time.time()

    @property
    def configured(self) -> bool:
        """A lock with no code could never be opened, so treat it as absent."""
        return len(self.code) > 0

    # ---- state ----------------------------------------------------------

    def lock(self) -> None:
        if not self.configured:
            print("[lock] 没有配置解锁序列（lock.code），拒绝上锁 —— 否则就锁死了")
            return
        self.locked = True
        self._buffer.clear()

    def unlock(self) -> None:
        self.locked = False
        self._buffer.clear()
        self._last_press = time.time()

    def note_activity(self) -> None:
        self._last_press = time.time()

    def should_auto_lock(self) -> bool:
        if self.locked or not self.configured or not self.idle_seconds:
            return False
        return (time.time() - self._last_press) >= self.idle_seconds

    # ---- input ----------------------------------------------------------

    def feed(self, key: int) -> bool:
        """Consume a press while locked. True means it just unlocked.

        Matching is a sliding window rather than a strict prefix: a child
        mashing keys would otherwise poison the buffer and leave the adult
        unable to enter the code without an explicit reset.
        """
        self._buffer.append(int(key))
        if len(self._buffer) > len(self.code):
            self._buffer = self._buffer[-len(self.code):]
        if self._buffer == self.code:
            self.unlock()
            return True
        return False

    def step_of(self, key: int) -> int | None:
        """Which press this key is, 1-based. First occurrence if repeated."""
        try:
            return self.code.index(int(key)) + 1
        except ValueError:
            return None

    def tile_for(self, key: int) -> str:
        """Icon to show on `key` while locked."""
        if not self.hint:
            return self.image
        step = self.step_of(key)
        if step is None or not (1 <= step <= 9):
            return self.image
        return self.hint_image % step

    @property
    def progress(self) -> int:
        """How many leading code digits the recent presses already satisfy.

        Under sliding-window matching there is no single "position", so report
        the longest prefix the tail of the buffer currently satisfies.
        """
        for n in range(len(self.code), 0, -1):
            if self._buffer[-n:] == self.code[:n]:
                return n
        return 0

    def describe(self) -> str:
        bits = [f"序列 {'-'.join(str(k) for k in self.code)}"]
        if self.idle_seconds:
            bits.append(f"空闲 {self.idle_seconds / 60:g} 分钟自动上锁")
        return ", ".join(bits)

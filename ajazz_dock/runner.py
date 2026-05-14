"""
Ajazz AKP153E host runner.

Loads settings.json (JSONC), pushes per-key images, listens for key presses,
dispatches configured actions. Config is hot-reloaded on file change.

Usage:
    python -m ajazz_dock                       # uses ./settings.json
    python -m ajazz_dock path\\to\\other.json   # custom path

Env knobs:
    DOCK_SKIP_INIT=1     skip init handshake (device already awake)
    DOCK_SKIP_IMAGES=1   skip image push (debug input only)
    DOCK_DEBUG=1         dump unrecognized HID input frames
"""

from __future__ import annotations

import os
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Mapping, Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from . import actions
from .config import Config
from .device import KEYS, DockDevice


def _push_images(dock: DockDevice, key_map: Mapping[int, Mapping[str, Any]],
                 prev: Mapping[int, Optional[str]]) -> dict:
    """Push images for any key whose `image` field changed, then flush once.

    STP is a batch-commit, not per-image — sending it after every BAT confuses
    the device and suppresses subsequent key-press frames.
    """
    new_state: dict = {}
    pushed = 0
    for key in range(1, KEYS + 1):
        spec = key_map.get(key) or {}
        image = spec.get("image")
        new_state[key] = image
        if image == prev.get(key):
            continue
        try:
            if image:
                dock.set_image(key, image)
            else:
                dock.clear_key(key)
            pushed += 1
        except Exception:
            print(f"[image] key {key} failed:")
            traceback.print_exc()
    if pushed:
        try:
            dock.flush()
        except Exception:
            print("[image] flush failed:")
            traceback.print_exc()
    return new_state


class _ReloadHandler(FileSystemEventHandler):
    def __init__(self, target: Path, on_change):
        self._target = target.resolve()
        self._on_change = on_change
        self._last = 0.0

    def on_modified(self, event):
        try:
            if Path(event.src_path).resolve() != self._target:
                return
        except OSError:
            return
        # Editors often fire multiple modify events for one save; debounce.
        now = time.time()
        if now - self._last < 0.3:
            return
        self._last = now
        self._on_change()


def main(config_path: str = "settings.json") -> int:
    path = Path(config_path)
    if not path.exists():
        print(f"config not found: {path}")
        print("hint: copy settings.example.json to settings.json")
        return 1

    try:
        cfg = Config(path)
    except ValueError as e:
        print(f"[config] {e}")
        return 1

    reload_event = threading.Event()
    handler = _ReloadHandler(path, reload_event.set)
    observer = Observer()
    observer.schedule(handler, str(path.parent or "."), recursive=False)
    observer.start()

    image_state: dict = {k: None for k in range(1, KEYS + 1)}

    skip_init = os.environ.get("DOCK_SKIP_INIT") == "1"
    skip_images = os.environ.get("DOCK_SKIP_IMAGES") == "1"

    try:
        dock = DockDevice()
        if not skip_init:
            dock.init()
        try:
            data = cfg.snapshot()
            brightness = data.get("brightness")
            if brightness is not None and not skip_images:
                dock.set_brightness(int(brightness))
            if not skip_images:
                image_state = _push_images(dock, data.get("keys") or {}, image_state)

            flags = []
            if skip_init: flags.append("no-init")
            if skip_images: flags.append("no-images")
            extra = f"  [{', '.join(flags)}]" if flags else ""
            print(f"ajazz-dock ready. {KEYS} keys, config={path}, watching for changes.{extra}")

            while True:
                if reload_event.is_set():
                    reload_event.clear()
                    try:
                        data = cfg.load()
                        if data.get("brightness") is not None:
                            dock.set_brightness(int(data["brightness"]))
                        image_state = _push_images(
                            dock, data.get("keys") or {}, image_state
                        )
                        print(f"[config] reloaded {path}")
                    except Exception:
                        print("[config] reload failed:")
                        traceback.print_exc()

                key = dock.read_key(timeout_ms=100)
                if key is None:
                    continue

                spec = (cfg.snapshot().get("keys") or {}).get(key)
                if not spec:
                    print(f"key {key:>2}  (unbound)")
                    continue

                action = spec.get("action")
                if not action:
                    print(f"key {key:>2}  (no action)")
                    continue

                print(f"key {key:>2}  -> {action.get('type')}")
                actions.run(action)
        finally:
            dock.close()
    except KeyboardInterrupt:
        print("\nbye")
        return 0
    finally:
        observer.stop()
        observer.join()


def cli() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else "settings.json"
    return main(arg)


if __name__ == "__main__":
    raise SystemExit(cli())

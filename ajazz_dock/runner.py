"""
Ajazz AKP153E host runner.

Loads settings.json (JSONC), pushes per-key images, listens for key presses,
dispatches configured actions. Config is hot-reloaded on file change.

Supports multiple pages: a `page` action switches the active page, re-pushing
that page's 15 images. See config.py for the config shape.

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
import signal
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Mapping, Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from . import actions, status
from .config import Config
from .device import KEYS, DockDevice, DockDisconnected


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


def _resolve_page(target: Any, current: int, pages: list) -> int:
    """Map a `page` action target to a page index.

    target may be "next" / "prev", a page name, or an integer index.
    next/prev wrap around. Unknown targets leave the page unchanged.
    """
    total = len(pages)
    if isinstance(target, bool):
        target = "next"
    if isinstance(target, int):
        return max(0, min(total - 1, target))

    s = str(target).strip().lower()
    if s in ("next", "", "+1"):
        return (current + 1) % total
    if s in ("prev", "previous", "-1"):
        return (current - 1) % total
    if s.lstrip("-").isdigit():
        return max(0, min(total - 1, int(s)))
    for i, page in enumerate(pages):
        if str(page.get("name", "")).lower() == s:
            return i
    print(f"[page] unknown target {target!r}")
    return current


class _ReloadHandler(FileSystemEventHandler):
    """Fire on_change when the watched config file is written.

    Handles in-place writes (on_modified) and atomic saves — many editors
    write a temp file and rename it over the target, which surfaces as
    on_created or on_moved rather than on_modified.
    """

    def __init__(self, target: Path, on_change):
        self._target = target.resolve()
        self._on_change = on_change
        self._last = 0.0

    def _maybe_fire(self, path: str) -> None:
        try:
            if Path(path).resolve() != self._target:
                return
        except OSError:
            return
        # Editors often fire multiple events for one save; debounce.
        now = time.time()
        if now - self._last < 0.3:
            return
        self._last = now
        self._on_change()

    def on_modified(self, event):
        self._maybe_fire(event.src_path)

    def on_created(self, event):
        self._maybe_fire(event.src_path)

    def on_moved(self, event):
        self._maybe_fire(event.dest_path)


_shutdown = threading.Event()


def _install_signal_handlers() -> None:
    """Ask the loop to stop, rather than dying where it stands.

    Without this a SIGTERM leaves the last page's icons lit on a dock nothing
    is driving any more -- it looks running when it is not.
    """
    def handler(signum, _frame):
        print(f"\n[dock] 收到信号 {signum}，正在收尾…")
        _shutdown.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError):
            pass  # not the main thread, or the platform disallows it


def _park(dock: DockDevice) -> None:
    """Blank the panel and put it to sleep on the way out."""
    try:
        dock.clear_all()
        dock.flush()
        dock.sleep()
    except Exception:
        pass  # already gone; nothing useful left to do


def _reconnect(attempts: int = 0) -> Optional[DockDevice]:
    """Wait for the dock to come back, backing off up to 30s between tries.

    hidapi reports an unplug, a sleeping device, or a USB re-enumeration as a
    plain read/write error. Dying on that would mean a dock that goes quiet for
    a second stays dark until someone notices, so keep trying instead. Returns
    None only on Ctrl-C.
    """
    delay = 1.0
    while True:
        attempts += 1
        try:
            dock = DockDevice()
            print(f"[device] 已重连（第 {attempts} 次尝试）")
            return dock
        except KeyboardInterrupt:
            return None
        except Exception as exc:
            if attempts == 1 or attempts % 10 == 0:
                print(f"[device] 等待设备回来… ({exc})")
            try:
                time.sleep(delay)
            except KeyboardInterrupt:
                return None
            delay = min(30.0, delay * 1.6)


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

    _shutdown.clear()
    _install_signal_handlers()

    reload_event = threading.Event()
    handler = _ReloadHandler(path, reload_event.set)
    observer = Observer()
    observer.schedule(handler, str(path.parent or "."), recursive=False)
    observer.start()

    image_state: dict = {k: None for k in range(1, KEYS + 1)}
    current_page = 0

    skip_init = os.environ.get("DOCK_SKIP_INIT") == "1"
    skip_images = os.environ.get("DOCK_SKIP_IMAGES") == "1"

    try:
        dock = DockDevice()
        if not skip_init:
            dock.init()
        try:
            data = cfg.snapshot()
            pages = data["pages"]
            brightness = data.get("brightness")
            if brightness is not None and not skip_images:
                dock.set_brightness(int(brightness))
            if not skip_images:
                image_state = _push_images(dock, pages[current_page]["keys"], image_state)

            status_cfg = data.get("status")
            updater = status.StatusUpdater(status_cfg)
            if updater.enabled and not skip_images:
                updater.set_context(pages=pages, page_index=current_page)
                updater.start()

            flags = []
            if skip_init: flags.append("no-init")
            if skip_images: flags.append("no-images")
            if updater.enabled: flags.append(f"status:{len(updater.slots)}")
            extra = f"  [{', '.join(flags)}]" if flags else ""
            print(f"ajazz-dock ready. {KEYS} keys, {len(pages)} page(s), "
                  f"config={path}, watching for changes.{extra}")

            while not _shutdown.is_set():
                if reload_event.is_set():
                    reload_event.clear()
                    try:
                        data = cfg.load()
                        pages = data["pages"]
                        current_page = min(current_page, len(pages) - 1)
                        if data.get("brightness") is not None:
                            dock.set_brightness(int(data["brightness"]))
                        image_state = _push_images(
                            dock, pages[current_page]["keys"], image_state
                        )
                        new_status = data.get("status")
                        if new_status != status_cfg:
                            # Slot set or interval changed -- the old thread's
                            # cached tiles no longer apply, so start over.
                            updater.stop()
                            status_cfg = new_status
                            updater = status.StatusUpdater(status_cfg)
                            if updater.enabled:
                                updater.start()
                        updater.set_context(pages=pages, page_index=current_page)
                        print(f"[config] reloaded {path} "
                              f"({len(pages)} page(s), on '{pages[current_page]['name']}')")
                    except Exception:
                        print("[config] reload failed:")
                        traceback.print_exc()

                try:
                    ready = updater.take()
                    if ready:
                        for slot, tile in ready.items():
                            dock.set_image(slot, tile)
                        dock.flush()

                    key = dock.read_key(timeout_ms=100)
                except DockDisconnected as exc:
                    print(f"[device] 连接断开: {exc}")
                    try:
                        dock.close()
                    except Exception:
                        pass
                    replacement = _reconnect()
                    if replacement is None:
                        raise KeyboardInterrupt
                    dock = replacement
                    if not skip_init:
                        dock.init()
                    if not skip_images:
                        if data.get("brightness") is not None:
                            dock.set_brightness(int(data["brightness"]))
                        # The device came back blank, so both caches are lying.
                        image_state = {k: None for k in range(1, KEYS + 1)}
                        image_state = _push_images(
                            dock, pages[current_page]["keys"], image_state)
                        updater.invalidate()
                    continue
                if key is None:
                    continue

                spec = (pages[current_page]["keys"]).get(key)
                if not spec:
                    print(f"key {key:>2}  (unbound)")
                    continue

                action = spec.get("action")
                if not action:
                    print(f"key {key:>2}  (no action)")
                    continue

                if action.get("type") == "page":
                    new_page = _resolve_page(
                        action.get("target", "next"), current_page, pages
                    )
                    if new_page != current_page:
                        current_page = new_page
                        image_state = _push_images(
                            dock, pages[current_page]["keys"], image_state
                        )
                        updater.set_context(pages=pages, page_index=current_page)
                        print(f"key {key:>2}  -> page '{pages[current_page]['name']}' "
                              f"({current_page + 1}/{len(pages)})")
                    continue

                print(f"key {key:>2}  -> {action.get('type')}")
                actions.run(action)
        finally:
            try:
                updater.stop()
            except NameError:
                pass
            _park(dock)
            dock.close()
    except KeyboardInterrupt:
        print("\nbye")
        return 0
    except DockDisconnected as exc:
        print(f"[device] 放弃: {exc}")
        return 1
    finally:
        observer.stop()
        observer.join()


def cli() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else "settings.json"
    return main(arg)


if __name__ == "__main__":
    raise SystemExit(cli())

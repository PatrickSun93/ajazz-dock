"""
Action dispatcher for dock keys.

Each action is a dict from settings.json; `run(action)` executes it. Macros
are sequences of the same dict shape, with an optional `delay` step.

Action types:
    url    target: "https://..."           open in the default browser
    app    target: <see backend>           launch an application
           args:   ["..."]                  optional
    keys   target: "ctrl+shift+f"          send a hotkey combo
    text   target: "hello world"           type literal text
    shell  target: "echo hi"               subprocess.Popen(shell=True)
    macro  steps:  [ {action...}, {delay: 0.5}, ... ]

`url`, `app`, `keys` and `text` are platform-specific and live in a backend
module (backend_darwin.py / backend_win32.py) picked at import time. `shell`
and `macro` are platform-neutral and stay here.

All actions run on a background thread so the HID read loop never blocks
on a slow Popen / browser launch.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
import traceback
from typing import Any, Mapping

if sys.platform == "darwin":
    from . import backend_darwin as _backend
elif sys.platform == "win32":
    from . import backend_win32 as _backend
else:
    _backend = None
    _BACKEND_ERROR = (
        f"no action backend for platform {sys.platform!r} "
        "(supported: darwin, win32) -- only 'shell' and 'macro' will work"
    )


def _need_backend(kind: str):
    if _backend is None:
        raise RuntimeError(f"cannot run {kind!r} action: {_BACKEND_ERROR}")
    return _backend


def _run_url(action: Mapping[str, Any]) -> None:
    _need_backend("url").run_url(action)


def _run_app(action: Mapping[str, Any]) -> None:
    _need_backend("app").run_app(action)


def _run_keys(action: Mapping[str, Any]) -> None:
    _need_backend("keys").run_keys(action)


def _run_text(action: Mapping[str, Any]) -> None:
    _need_backend("text").run_text(action)


def _run_shell(action: Mapping[str, Any]) -> None:
    subprocess.Popen(action["target"], shell=True, close_fds=True)


def _run_macro(action: Mapping[str, Any]) -> None:
    for step in action.get("steps", []):
        if "delay" in step:
            time.sleep(float(step["delay"]))
            continue
        _dispatch_sync(step)


_HANDLERS = {
    "url": _run_url,
    "app": _run_app,
    "keys": _run_keys,
    "text": _run_text,
    "shell": _run_shell,
    "macro": _run_macro,
}


def _dispatch_sync(action: Mapping[str, Any]) -> None:
    t = action.get("type")
    handler = _HANDLERS.get(t)
    if handler is None:
        raise ValueError(f"unknown action type: {t!r}")
    handler(action)


def run(action: Mapping[str, Any]) -> None:
    """Fire-and-forget. Errors are logged but never propagated."""
    def _go():
        try:
            _dispatch_sync(action)
        except Exception:
            traceback.print_exc()

    threading.Thread(target=_go, daemon=True).start()

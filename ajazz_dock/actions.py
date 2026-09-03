"""
Action dispatcher for dock keys.

Each action is a dict from the config; `run(action)` executes it. Macros
are sequences of the same dict shape, with an optional `delay` step.

Action types:
    url    target: "https://..."           open in the default browser
    app    target: <see backend>           launch an application
           args:   ["..."]                  optional
    keys   target: "ctrl+shift+f"          send a hotkey combo
    text   target: "hello world"           type literal text
    shell  target: "echo hi"               subprocess.Popen(shell=True)
    macro  steps:  [ {action...}, {delay: 0.5}, ... ]

`url`, `app`, `keys` and `text` are platform-specific and live in the
`backends` package, which picks the module for this host at import time.
`shell` and `macro` are platform-neutral and stay here.

All actions run on a background thread so the HID read loop never blocks
on a slow Popen / browser launch.
"""

from __future__ import annotations

import subprocess
import threading
import time
import traceback
from typing import Any, Mapping

from .backends import require as _backend


def _run_url(action: Mapping[str, Any]) -> None:
    _backend("url").run_url(action)


def _run_app(action: Mapping[str, Any]) -> None:
    _backend("app").run_app(action)


def _run_keys(action: Mapping[str, Any]) -> None:
    _backend("keys").run_keys(action)


def _run_text(action: Mapping[str, Any]) -> None:
    _backend("text").run_text(action)


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

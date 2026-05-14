"""
Action dispatcher for dock keys.

Each action is a dict from config.yaml; `run(action)` executes it. Macros
are sequences of the same dict shape, with an optional `delay` step.

Action types:
    url    target: "https://..."           os.startfile (default browser)
    app    target: "C:\\\\path\\\\app.exe"      subprocess.Popen
           args:   ["..."]                  optional
    keys   target: "ctrl+shift+f"          keyboard.send (hotkey)
    text   target: "hello world"           keyboard.write (typed)
    shell  target: "cmd /c echo hi"        subprocess.Popen(shell=True)
    macro  steps:  [ {action...}, {delay: 0.5}, ... ]

All actions run on a background thread so the HID read loop never blocks
on a slow Popen / browser launch.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
import traceback
from typing import Any, Mapping

import keyboard


def _run_url(action: Mapping[str, Any]) -> None:
    os.startfile(action["target"])


def _run_app(action: Mapping[str, Any]) -> None:
    target = action["target"]
    args = action.get("args") or []
    subprocess.Popen([target, *args], close_fds=True)


def _run_keys(action: Mapping[str, Any]) -> None:
    keyboard.send(action["target"])


def _run_text(action: Mapping[str, Any]) -> None:
    keyboard.write(action["target"])


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

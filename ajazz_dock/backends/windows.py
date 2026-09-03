"""
Windows action backend (sys.platform == "win32").

url    -> os.startfile           (default browser / shell association)
app    -> subprocess.Popen
keys   -> keyboard.send          (the `keyboard` package, Win32 hooks)
text   -> keyboard.write
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Mapping

# Imported lazily so that merely importing the package on a machine without
# the `keyboard` package (or without the privileges it wants) does not fail.
_keyboard_mod = None


def _keyboard():
    global _keyboard_mod
    if _keyboard_mod is None:
        import keyboard
        _keyboard_mod = keyboard
    return _keyboard_mod


def run_url(action: Mapping[str, Any]) -> None:
    os.startfile(action["target"])


def run_app(action: Mapping[str, Any]) -> None:
    target = action["target"]
    args = action.get("args") or []
    subprocess.Popen([target, *args], close_fds=True)


def run_keys(action: Mapping[str, Any]) -> None:
    _keyboard().send(action["target"])


def run_text(action: Mapping[str, Any]) -> None:
    _keyboard().write(action["target"])

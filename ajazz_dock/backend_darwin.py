"""
macOS action backend.

url    -> `open <url>`                      (default browser)
app    -> `open -a` / `open -b` / direct exec, see _run_app
keys   -> pynput Controller (needs Accessibility permission)
text   -> pynput Controller.type

Accessibility: the first time a `keys` or `text` action fires, macOS asks to
grant the *host terminal* (or the python binary) control of your computer under
System Settings > Privacy & Security > Accessibility. Until that is granted the
keystrokes are silently dropped -- no exception is raised.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Iterable, Mapping, Sequence

# pynput is imported lazily: importing it pulls in pyobjc and, on some setups,
# probes the accessibility API. Nothing else in the package should pay that
# cost just to load a config.
_kb = None
_Key = None


def _keyboard():
    global _kb, _Key
    if _kb is None:
        from pynput.keyboard import Controller, Key
        _kb, _Key = Controller(), Key
    return _kb, _Key


def _modifiers(Key):
    return {
        "cmd": Key.cmd, "command": Key.cmd, "win": Key.cmd, "windows": Key.cmd,
        "ctrl": Key.ctrl, "control": Key.ctrl,
        "alt": Key.alt, "option": Key.alt, "opt": Key.alt,
        "shift": Key.shift,
    }


def _specials(Key):
    named = {
        "enter": "enter", "return": "enter", "tab": "tab", "esc": "esc",
        "escape": "esc", "space": "space", "backspace": "backspace",
        "delete": "delete", "del": "delete", "up": "up", "down": "down",
        "left": "left", "right": "right", "home": "home", "end": "end",
        "pageup": "page_up", "pagedown": "page_down",
        "capslock": "caps_lock", "insert": "insert",
    }
    out = {k: getattr(Key, v) for k, v in named.items() if hasattr(Key, v)}
    for n in range(1, 21):
        f = getattr(Key, f"f{n}", None)
        if f is not None:
            out[f"f{n}"] = f
    return out


def _parse_combo(combo: str):
    """'cmd+shift+4' -> ([Key.cmd, Key.shift], '4')."""
    _, Key = _keyboard()
    mods_map, spec_map = _modifiers(Key), _specials(Key)
    parts = [p.strip().lower() for p in str(combo).split("+") if p.strip()]
    if not parts:
        raise ValueError(f"empty key combo: {combo!r}")

    mods, main = [], None
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        if part in mods_map and not last:
            mods.append(mods_map[part])
        elif last:
            main = spec_map.get(part, part)
        else:
            raise ValueError(f"unknown modifier {part!r} in {combo!r}")
    if main is None:
        raise ValueError(f"no main key in combo: {combo!r}")
    if isinstance(main, str) and len(main) != 1:
        raise ValueError(f"unknown key {main!r} in {combo!r}")
    return mods, main


# ---- handlers -----------------------------------------------------------

def run_url(action: Mapping[str, Any]) -> None:
    subprocess.Popen(["open", action["target"]], close_fds=True)


def run_app(action: Mapping[str, Any]) -> None:
    """Launch a macOS app.

    target may be
      - an app name or .app path   -> `open -a`   ("Obsidian", "/Applications/X.app")
      - a bundle id                -> `open -b`   ("com.apple.Terminal")
      - a plain executable path    -> exec directly ("/usr/bin/open", "~/bin/foo")
    `args` is forwarded either way.
    """
    target = os.path.expanduser(str(action["target"]))
    args: Sequence[str] = action.get("args") or []

    is_bundle_path = target.endswith(".app") or target.endswith(".app/")
    looks_like_path = "/" in target
    is_bundle_id = not looks_like_path and "." in target and not is_bundle_path

    if is_bundle_path or (not looks_like_path and not is_bundle_id):
        cmd = ["open", "-a", target.rstrip("/")]
    elif is_bundle_id:
        cmd = ["open", "-b", target]
    else:
        subprocess.Popen([target, *args], close_fds=True)
        return

    if args:
        cmd += ["--args", *args]
    subprocess.Popen(cmd, close_fds=True)


def run_keys(action: Mapping[str, Any]) -> None:
    kb, _ = _keyboard()
    mods, main = _parse_combo(action["target"])
    with _held(kb, mods):
        kb.press(main)
        kb.release(main)


def run_text(action: Mapping[str, Any]) -> None:
    kb, _ = _keyboard()
    kb.type(action["target"])


class _held:
    """Hold a list of modifier keys for the duration of a block."""

    def __init__(self, kb, keys: Iterable):
        self._kb, self._keys = kb, list(keys)

    def __enter__(self):
        for k in self._keys:
            self._kb.press(k)
        return self

    def __exit__(self, *exc):
        for k in reversed(self._keys):
            self._kb.release(k)

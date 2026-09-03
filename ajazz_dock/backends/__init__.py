"""
Per-platform action backends.

Only four action types differ by host -- `url`, `app`, `keys` and `text`.
`shell` and `macro` are platform-neutral and stay in actions.py. Every
backend module exposes the same four functions under the same names, so
actions.py dispatches without ever branching on sys.platform itself:

    darwin.py    macOS      open / open -a / pynput
    windows.py   Windows    os.startfile / Popen / keyboard

Adding a host means adding a module here and one line to _MODULES. The
import is lazy in the sense that only the current platform's module is
loaded -- importing this package on macOS never touches `keyboard`, and on
Windows never touches pynput/pyobjc.
"""

from __future__ import annotations

import importlib
import sys
from types import ModuleType
from typing import Optional

# sys.platform -> module name in this package.
_MODULES = {
    "darwin": "darwin",
    "win32": "windows",
}

UNSUPPORTED = (
    f"no action backend for platform {sys.platform!r} "
    f"(supported: {', '.join(sorted(_MODULES))}) "
    "-- only 'shell' and 'macro' actions will work"
)

_backend: Optional[ModuleType] = None
if sys.platform in _MODULES:
    _backend = importlib.import_module(f".{_MODULES[sys.platform]}", __name__)


def current() -> Optional[ModuleType]:
    """The backend for this host, or None if the platform has none."""
    return _backend


def require(kind: str) -> ModuleType:
    """The backend for this host, or a clear error naming the action.

    Raised rather than returned so a config written for the other platform
    fails loudly on the key that needs it, instead of silently doing nothing.
    """
    if _backend is None:
        raise RuntimeError(f"cannot run {kind!r} action: {UNSUPPORTED}")
    return _backend


__all__ = ["current", "require", "UNSUPPORTED"]

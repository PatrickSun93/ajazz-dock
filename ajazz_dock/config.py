"""
JSONC config loader for the dock.

We accept JSON-with-comments (JSONC, like Windows Terminal's settings.json):
  - // line comments and /* block comments */
  - trailing commas in arrays and objects

Public API:
    Config(path)            — thread-safe holder, hot-reloadable
    Config.snapshot()       — returns the current parsed dict
    Config.load()           — re-reads from disk
    load_jsonc(path)        — one-shot parse
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any


# Strip // line comments and /* block comments */ while preserving them inside
# string literals. Then strip trailing commas before } or ].
_COMMENT_OR_STRING = re.compile(
    r'"(?:\\.|[^"\\])*"'      # double-quoted string
    r"|//[^\n]*"              # // line comment
    r"|/\*.*?\*/",            # /* block comment */
    re.DOTALL,
)
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def _strip_jsonc(text: str) -> str:
    def repl(m: re.Match) -> str:
        s = m.group(0)
        return s if s.startswith('"') else ""
    no_comments = _COMMENT_OR_STRING.sub(repl, text)
    return _TRAILING_COMMA.sub(r"\1", no_comments)


def load_jsonc(path: Path) -> dict:
    raw = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(_strip_jsonc(raw))
    except json.JSONDecodeError as e:
        raise ValueError(f"{path}: invalid JSON ({e.msg} at line {e.lineno} col {e.colno})") from e


def _int_keys(mapping: dict | None) -> dict:
    """Coerce a {keyId: spec} map's keys to int (JSON object keys are strings)."""
    return {int(k): v for k, v in (mapping or {}).items()}


def _normalize(data: dict) -> dict:
    """Drop $schema and resolve the config into a uniform list of pages.

    Three input shapes are accepted:
      - `pages`: [ {name, keys}, ... ]   multi-page
      - `keys`: {...}                     single page (legacy / simple setups)
    A top-level `shared` map is merged into every page, so navigation keys
    only need to be defined once. On a key-id clash, `shared` wins.

    Output always has `data["pages"]` = [ {"name": str, "keys": {int: spec}} ].
    """
    data.pop("$schema", None)
    shared = _int_keys(data.get("shared"))

    raw_pages = data.get("pages")
    if raw_pages:
        pages = []
        for i, page in enumerate(raw_pages):
            keys = _int_keys(page.get("keys"))
            pages.append({
                "name": page.get("name") or f"page {i + 1}",
                "keys": {**keys, **shared},
            })
    else:
        pages = [{"name": "main", "keys": {**_int_keys(data.get("keys")), **shared}}]

    data["pages"] = pages
    return data


class Config:
    """Thread-safe holder. Callers grab snapshot() once per use."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {}
        self.load()

    def load(self) -> dict:
        data = _normalize(load_jsonc(self.path))
        with self._lock:
            self._data = data
        return data

    def snapshot(self) -> dict:
        with self._lock:
            return self._data

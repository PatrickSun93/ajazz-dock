#!/usr/bin/env python3
"""
Extract app icons from macOS apps into icons/. The macOS counterpart of
tools/extract_icons.ps1.

    ./.venv/bin/python tools/extract_icons_macos.py            # everything below
    ./.venv/bin/python tools/extract_icons_macos.py chrome zed # only these

Uses NSWorkspace.iconForFile_, which returns whatever the Finder shows. That
works for apps whose artwork lives in Assets.car (Shottr, Rectangle) as well
as classic .icns bundles, and -- unlike AppleScript's `path to application` --
never pops a "where is it?" dialog for an app that isn't installed.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from AppKit import NSBitmapImageRep, NSWorkspace
from PIL import Image

OUT_SIZE = 256
ICONS = Path(__file__).resolve().parent.parent / "icons"

# output name -> application name
APPS = {
    "chrome": "Google Chrome",
    "claudeapp": "Claude",
    "notion": "Notion",
    "obsidian": "Obsidian",
    "vscode": "Visual Studio Code",
    "antigravity": "Antigravity",
    "zed": "Zed",
    "docker": "Docker",
    "iterm": "iTerm",
    "finder": "Finder",
    "githubdesktop": "GitHub Desktop",
    "discord": "Discord",
    "wechat": "WeChat",
    "futu": "富途牛牛",
    "moomoo": "moomoo",
    "shottr": "Shottr",
    "rectangle": "Rectangle",
    "stats": "Stats",
    "tailscale": "Tailscale",
    "xcode": "Xcode",
    "ollama": "Ollama",
    "chatbox": "Chatbox",
    "codex": "Codex",
    "safari": "Safari",
    "zen": "Zen",
    "iina": "IINA",
    "koodoreader": "Koodo Reader",
    "neatreader": "NeatReader",
    "unarchiver": "The Unarchiver",
    "activitymonitor": "Activity Monitor",
    "anaconda": "Anaconda-Navigator",
    "notepadnext": "Notepadnext",
    "sqlitestudio": "SQLiteStudio",
    "mysqlworkbench": "MySQLWorkbench",
    "terminalapp": "Terminal",
}

# Extra icons taken from a filesystem path rather than an app (folders, etc.)
PATHS = {
    "folder": "/Volumes/externalssd/devitems",
}


def _png_bytes(image, size: int = 512) -> bytes | None:
    """Rasterize the icon to PNG.

    iconForFile_ hands back an NSImage backed by NSISIconImageRep, which is a
    resolution-independent rep -- there is no NSBitmapImageRep to grab. Setting
    a size and asking for the TIFF representation forces a render (the system
    obliges at 2x, so size=512 yields 1024x1024), which then converts cleanly.
    """
    image.setSize_((size, size))
    tiff = image.TIFFRepresentation()
    if not tiff:
        return None
    rep = NSBitmapImageRep.imageRepWithData_(tiff)
    if rep is None:
        return None
    data = rep.representationUsingType_properties_(4, None)  # 4 = NSPNGFileType
    return bytes(data) if data else None


def _save(name: str, source_path: str, ws) -> str:
    image = ws.iconForFile_(source_path)
    if image is None:
        return "FAIL  (no icon)"
    raw = _png_bytes(image)
    if not raw:
        return "FAIL  (no bitmap rep)"
    img = Image.open(io.BytesIO(raw)).convert("RGBA")
    img.thumbnail((OUT_SIZE, OUT_SIZE), Image.LANCZOS)
    ICONS.mkdir(exist_ok=True)
    img.save(ICONS / f"{name}.png")
    return f"OK    {img.size[0]}x{img.size[1]}"


def main(argv: list[str]) -> int:
    want = set(argv)
    ws = NSWorkspace.sharedWorkspace()
    ok = skipped = failed = 0

    for name, app in APPS.items():
        if want and name not in want:
            continue
        path = ws.fullPathForApplication_(app)
        if not path:
            print(f"SKIP  {name:<16} (未安装: {app})")
            skipped += 1
            continue
        result = _save(name, path, ws)
        print(f"{result:<14} {name + '.png':<20} <- {app}")
        ok += result.startswith("OK")
        failed += result.startswith("FAIL")

    for name, path in PATHS.items():
        if want and name not in want:
            continue
        if not Path(path).exists():
            print(f"SKIP  {name:<16} (路径不存在: {path})")
            skipped += 1
            continue
        result = _save(name, path, ws)
        print(f"{result:<14} {name + '.png':<20} <- {path}")
        ok += result.startswith("OK")
        failed += result.startswith("FAIL")

    print(f"\n{ok} 成功, {skipped} 跳过, {failed} 失败  ->  {ICONS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

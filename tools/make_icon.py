"""
Generate a simple labeled tile icon for keys with no natural app icon
(hotkeys, web shortcuts, etc.).

Usage:
    python tools/make_icon.py <out.png> <label> [#hexcolor]

Example:
    python tools/make_icon.py icons/snip.png SNIP "#3b82f6"
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = 256
# macOS first, then Windows -- whichever exists. The macOS faces carry CJK,
# which the Windows ones do not, so a Chinese label renders on either host.
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
]


def _font(px: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, px)
    return ImageFont.load_default()


def make(out: str, label: str, color: str = "#3b82f6") -> None:
    img = Image.new("RGB", (SIZE, SIZE), color)
    draw = ImageDraw.Draw(img)

    # Shrink the font until the label fits with margins.
    px = 130
    font = _font(px)
    while px > 24:
        l, t, r, b = draw.textbbox((0, 0), label, font=font)
        if (r - l) <= SIZE - 36 and (b - t) <= SIZE - 36:
            break
        px -= 6
        font = _font(px)

    l, t, r, b = draw.textbbox((0, 0), label, font=font)
    draw.text(
        ((SIZE - (r - l)) / 2 - l, (SIZE - (b - t)) / 2 - t),
        label, fill="white", font=font,
    )
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    print(f"wrote {out}  ({label!r}, {color})")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)
    make(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "#3b82f6")

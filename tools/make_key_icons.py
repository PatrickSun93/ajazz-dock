#!/usr/bin/env python3
"""
Generate the tile icons that settings.macos.json needs for keys with no app
bundle to steal artwork from -- folders, project shortcuts, dev-stack controls,
web links.

    ./.venv/bin/python tools/make_key_icons.py            # all
    ./.venv/bin/python tools/make_key_icons.py dir_brain  # just these

Each tile is a vertical gradient with an SF Symbol stencilled in white and a
short label underneath. SF Symbols come from the system via NSImage, so this
only runs on macOS 11+; the Windows side keeps using tools/make_icon.py.

Colour encodes the page, so the dock reads at a glance:
    amber  = folders (P2)      orange = Claude Code sessions (P3)
    teal   = dev stack (P4)    red    = destructive       slate = local services
    brand  = web links (P5)
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from AppKit import NSImage, NSImageSymbolConfiguration, NSBitmapImageRep
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

SIZE = 256
SYMBOL_FRAC = 0.44          # symbol height as a fraction of the tile
SYMBOL_CENTER_Y = 0.40      # where the symbol's midline sits
LABEL_TOP_Y = 0.74
LABEL_PX = 46

# pyobjc does not export these enum names; the raw values follow NSFontWeight.
WEIGHT_SEMIBOLD, SCALE_LARGE = 6, 3

ICONS_DIR = Path(__file__).resolve().parent.parent / "icons"
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"

AMBER = ("#F0A93C", "#B26A15")   # P2 folders
CC    = ("#EE8A5E", "#B03F22")   # P3 Claude Code sessions
CC_HI = ("#E8724A", "#992F16")   # P3 the "open everything" key
TEAL  = ("#2AA9A0", "#0E6A72")   # P4 dev stack
STOP  = ("#E8613D", "#96280E")   # P4 destructive
SLATE = ("#6B8AA6", "#33485C")   # P4 local services

# name -> (SF Symbol, label, gradient)
ICONS: dict[str, tuple[str, str, tuple[str, str]]] = {
    # ---- P2 folders ----
    "dir_devitems":  ("externaldrive.fill",                    "devitems", AMBER),
    "dir_engloop":   ("point.3.connected.trianglepath.dotted", "EngLoop",  AMBER),
    "dir_palearn":   ("chart.line.uptrend.xyaxis",             "palearn",  AMBER),
    "dir_picron":    ("clock.arrow.circlepath",                "PiCron",   AMBER),
    "dir_resume":    ("doc.text.fill",                         "简历",      AMBER),
    "dir_nodetex":   ("cube.fill",                             "nodeTex",  AMBER),
    "dir_brain":     ("brain.head.profile",                    "二脑",      AMBER),
    "dir_downloads": ("arrow.down.circle.fill",                "下载",      AMBER),
    "dir_desktop":   ("desktopcomputer",                       "桌面",      AMBER),
    "dir_aiagents":  ("cpu.fill",                              "agents",   AMBER),
    "dir_trading":   ("chart.bar.fill",                        "交易",      AMBER),
    "dir_webapps":   ("globe",                                 "web",      AMBER),

    # ---- P3 Claude Code sessions ----
    "cc_all":        ("square.grid.3x3.fill",                  "全开",      CC_HI),
    "cc_nodetex":    ("cube.fill",                             "nodeTex",  CC),
    "cc_palearn":    ("chart.line.uptrend.xyaxis",             "palearn",  CC),
    "cc_resume":     ("doc.text.fill",                         "简历",      CC),
    "cc_picron":     ("clock.arrow.circlepath",                "PiCron",   CC),
    "cc_pagent":     ("envelope.fill",                         "pAgent",   CC),
    "cc_devitems":   ("externaldrive.fill",                    "根",        CC),
    "cc_engloop":    ("point.3.connected.trianglepath.dotted", "EngLoop",  CC),
    "cc_sched":      ("calendar.badge.clock",                  "定时",      CC),
    "cc_shipflow":   ("shippingbox.fill",                      "shipflow", CC),
    "cc_brain":      ("brain.head.profile",                    "二脑",      CC),

    # Base for the page-6 "close everything" key. Same symbol as cc_all so the
    # two pages line up, but the label has to say 全关, not 全开 -- reusing
    # cc_all directly would put "open all" on the key that closes them.
    "_base_close_all": ("square.grid.3x3.fill",                 "全关",      CC_HI),

    # ---- P4 dev stack ----
    "stack_start":   ("play.fill",                             "启动",      TEAL),
    "stack_status":  ("waveform.path.ecg",                     "状态",      TEAL),
    "stack_stop":    ("stop.fill",                             "停止",      STOP),
    "svc_bus":       ("network",                               "9969",     SLATE),
    "svc_chart":     ("chart.xyaxis.line",                     "8502",     SLATE),
    "svc_3000":      ("server.rack",                           "3000",     SLATE),
    "svc_devsrv":    ("hammer.fill",                           "dev",      SLATE),

    # ---- P5 web ----
    "web_notebooklm": ("text.book.closed.fill", "NotebkLM", ("#5B8DEF", "#2C5AA8")),
    "web_gemini":     ("sparkles",              "Gemini",   ("#9B7EE0", "#5B3FA8")),
    "web_vercel":     ("triangle.fill",         "Vercel",   ("#555555", "#0A0A0A")),
    "web_youtube":    ("play.rectangle.fill",   "YouTube",  ("#F0524A", "#A81410")),
    "web_bilibili":   ("tv.fill",               "B站",       ("#4FC3E8", "#0077A8")),
    "web_hn":         ("newspaper.fill",        "HN",       ("#FF8A3D", "#C24E08")),
    "web_supabase":   ("bolt.fill",             "Supabase", ("#4FD99A", "#1F8A5A")),
}


def _hex(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def gradient(top: str, bottom: str) -> Image.Image:
    """Vertical gradient. One-pixel column stretched, so it costs nothing."""
    c1, c2 = _hex(top), _hex(bottom)
    strip = Image.new("RGB", (1, SIZE))
    draw = ImageDraw.Draw(strip)
    for y in range(SIZE):
        t = y / (SIZE - 1)
        draw.point((0, y), tuple(round(a + (b - a) * t) for a, b in zip(c1, c2)))
    return strip.resize((SIZE, SIZE), Image.BILINEAR)


def symbol(name: str, point_size: int = 200) -> Image.Image | None:
    """Render an SF Symbol to RGBA. It comes out black on transparent."""
    image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
    if image is None:
        return None
    config = NSImageSymbolConfiguration.configurationWithPointSize_weight_scale_(
        point_size, WEIGHT_SEMIBOLD, SCALE_LARGE)
    image = image.imageWithSymbolConfiguration_(config)
    rep = NSBitmapImageRep.imageRepWithData_(image.TIFFRepresentation())
    if rep is None:
        return None
    data = rep.representationUsingType_properties_(4, None)  # 4 = NSPNGFileType
    return Image.open(io.BytesIO(bytes(data))).convert("RGBA")


def tile(out: Path, sym_name: str, label: str, grad: tuple[str, str]) -> str:
    canvas = gradient(*grad).convert("RGBA")

    glyph = symbol(sym_name)
    if glyph is None:
        status = f"符号缺失({sym_name})"
    else:
        target = int(SIZE * SYMBOL_FRAC)
        glyph.thumbnail((target, target), Image.LANCZOS)
        # Use the glyph's alpha as a stencil and stamp it white, so it reads
        # against the coloured ground instead of staying black-on-colour.
        white = Image.new("RGBA", glyph.size, (255, 255, 255, 255))
        white.putalpha(glyph.getchannel("A"))
        canvas.alpha_composite(
            white,
            ((SIZE - glyph.width) // 2, int(SIZE * SYMBOL_CENTER_Y) - glyph.height // 2),
        )
        status = "OK"

    draw = ImageDraw.Draw(canvas)
    px = LABEL_PX
    font = ImageFont.truetype(FONT, px)
    while px > 18:
        l, t, r, b = draw.textbbox((0, 0), label, font=font)
        if (r - l) <= SIZE - 24:
            break
        px -= 3
        font = ImageFont.truetype(FONT, px)
    l, t, r, b = draw.textbbox((0, 0), label, font=font)
    draw.text(((SIZE - (r - l)) / 2 - l, int(SIZE * LABEL_TOP_Y) - t),
              label, font=font, fill=(255, 255, 255, 244))

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out)
    return status


# Close tiles reuse the page-3 session artwork, dimmed with a red cross badge:
# whatever symbol opens a session on page 3 closes it on page 6, so the two
# pages read as the same map. At 95px only the badge can carry the difference.
#
# personalAgent and its scheduler are deliberately absent. The mail/calendar
# agent runs silently, and nothing signals that it stopped -- you find out by
# noticing a batch of unprocessed mail. No key, no accident.
CLOSE_OF = {
    "close_all": "_base_close_all",
    "close_nodetex": "cc_nodetex",
    "close_palearn": "cc_palearn",
    "close_resume": "cc_resume",
    "close_picron": "cc_picron",
    "close_devitems": "cc_devitems",
    "close_engloop": "cc_engloop",
    "close_shipflow": "cc_shipflow",
    "close_brain": "cc_brain",
}

BADGE_RED = (198, 42, 32)


def close_tile(out: Path, source: Path) -> str:
    if not source.exists():
        return f"源图标缺失({source.name})"
    img = Image.open(source)
    if img.mode != "RGB":
        img = img.convert("RGBA")
        img = Image.alpha_composite(
            Image.new("RGBA", img.size, (0, 0, 0, 255)), img).convert("RGB")
    img = img.resize((SIZE, SIZE), Image.LANCZOS)
    img = ImageEnhance.Brightness(img).enhance(0.5)

    draw = ImageDraw.Draw(img)
    radius = int(SIZE * 0.235)
    # Top-right, not bottom-right: the source tiles carry their label along the
    # bottom, and a badge down there covers the one word telling you which
    # session the key closes.
    margin = int(SIZE * 0.045)
    cx = SIZE - radius - margin
    cy = radius + margin
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                 fill=BADGE_RED, outline=(255, 255, 255), width=int(SIZE * 0.022))
    arm = int(radius * 0.44)
    width = int(SIZE * 0.045)
    draw.line([cx - arm, cy - arm, cx + arm, cy + arm], fill="white", width=width)
    draw.line([cx - arm, cy + arm, cx + arm, cy - arm], fill="white", width=width)

    img.save(out)
    return "OK"


def main(argv: list[str]) -> int:
    want = set(argv)
    made = failed = 0
    for name, (sym_name, label, grad) in ICONS.items():
        if want and name not in want:
            continue
        status = tile(ICONS_DIR / f"{name}.png", sym_name, label, grad)
        if status == "OK":
            made += 1
        else:
            failed += 1
            print(f"  ⚠ {name}: {status}")
    for name, src in CLOSE_OF.items():
        if want and name not in want:
            continue
        status = close_tile(ICONS_DIR / f"{name}.png", ICONS_DIR / f"{src}.png")
        if status == "OK":
            made += 1
        else:
            failed += 1
            print(f"  ⚠ {name}: {status}")

    # The base tile is scaffolding, not a key image.
    scaffold = ICONS_DIR / "_base_close_all.png"
    if scaffold.exists() and not want:
        scaffold.unlink()
        made -= 1

    print(f"{made} 个图标已生成" + (f", {failed} 个符号名无效" if failed else "")
          + f"  ->  {ICONS_DIR}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

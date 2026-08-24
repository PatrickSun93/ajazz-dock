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
from PIL import Image, ImageDraw, ImageFont

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

    # ---- P4 dev stack ----
    "stack_start":   ("play.fill",                             "启动",      TEAL),
    "stack_status":  ("waveform.path.ecg",                     "状态",      TEAL),
    "stack_stop":    ("stop.fill",                             "停止",      STOP),
    "svc_bus":       ("network",                               "9969",     SLATE),
    "svc_chart":     ("chart.xyaxis.line",                     "8502",     SLATE),
    "svc_3000":      ("server.rack",                           "3000",     SLATE),
    "svc_devsrv":    ("hammer.fill",                           "dev",      SLATE),

    # Service control. EngLoop gets two stop keys because its stop.sh has two
    # modes: graceful waits up to 660s for agents to finish their round, and
    # --now kills the tmux sessions outright. The second exists for the
    # 2026-08-09 broadcast storm -- when you are burning quota there is no
    # time to wait out a polite shutdown, so it needs its own key.
    "svc_eng_stop":  ("point.3.connected.trianglepath.dotted", "Eng停",   STOP),
    "svc_eng_kill":  ("exclamationmark.octagon.fill",          "止损",     ("#D8452C", "#7A1B08")),
    "svc_chart_stop": ("chart.xyaxis.line",                    "图停",     STOP),

    # Child lock. Every key shows this tile while locked, so the panel gives
    # away nothing about which positions the unlock sequence uses.
    "locked":        ("lock.fill",                             "已锁",     ("#4A5058", "#1C2026")),
    "lock_now":      ("lock.fill",                             "上锁",     ("#5E6670", "#2C333B")),

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
    print(f"{made} 个图标已生成" + (f", {failed} 个符号名无效" if failed else "")
          + f"  ->  {ICONS_DIR}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

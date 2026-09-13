#!/usr/bin/env python3
"""App icons for the Home Screen install.

Deliberately not wired into rebuild.py. These are static assets that change
only when the mark does, and putting them in a dependency set would make every
engine rebuild re-encode four PNGs to produce the same bytes.

Run by hand after editing anything below:

    python3 icons.py ../docs

The maskable variant is the same mark at 60% of the canvas, because Android
crops a maskable icon to whatever shape the launcher uses and only the inner
80% circle is guaranteed to survive. The others are drawn edge to edge.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

GLYPH = "物"
PAPER = (250, 247, 240)
INK = (122, 92, 46)
FACES = [
    "/System/Library/Fonts/Supplemental/Hiragino Sans GB W6.otf",
    "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
]


def face(px):
    for path in FACES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, px)
            except OSError:
                continue
    raise SystemExit("no CJK face found; edit FACES")


def icon(size, scale, radius=0):
    img = Image.new("RGB", (size, size), PAPER)
    d = ImageDraw.Draw(img)
    if radius:
        d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=PAPER)
    f = face(int(size * scale))
    # anchor="mm" centres on the glyph's own ink box rather than its advance
    # width, which for a full-width CJK glyph is the difference between centred
    # and visibly low-left.
    d.text((size / 2, size / 2), GLYPH, font=f, fill=INK, anchor="mm")
    return img


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "../docs").resolve()
    out.mkdir(parents=True, exist_ok=True)
    jobs = [
        ("icon-192.png", 192, 0.66, 0),
        ("icon-512.png", 512, 0.66, 0),
        ("icon-maskable-512.png", 512, 0.48, 0),
        # iOS applies its own corner radius and no transparency, so this one is
        # square and opaque on purpose.
        ("apple-touch-icon.png", 180, 0.66, 0),
    ]
    for name, size, scale, radius in jobs:
        icon(size, scale, radius).save(out / name, "PNG", optimize=True)
        print(f"  {out / name}")


if __name__ == "__main__":
    main()

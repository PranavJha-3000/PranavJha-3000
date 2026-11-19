#!/usr/bin/env python3
"""Turn assets/portrait.webp into data/portrait.txt, a character halftone the hero draws as text.

Run once locally (needs: pip install pillow). CI only reads the .txt, so it never needs PIL.
    python scripts/make_portrait.py [cols] [rows]
"""
import sys
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent
COLS = int(sys.argv[1]) if len(sys.argv) > 1 else 120
ROWS = int(sys.argv[2]) if len(sys.argv) > 2 else 72
RAMP = " .'`,:;-~+=*%#@"  # light to dark; ASCII only, so every glyph exists in the mono subset

orig = Image.open(ROOT / "assets/portrait.webp").convert("L").crop((150, 40, 1150, 1040))  # square on head and collar
src = Image.blend(orig, ImageOps.equalize(orig), 0.5)  # lift the flat skin tones so eyes and glasses read
src = ImageOps.autocontrast(src, cutoff=1).filter(ImageFilter.UnsharpMask(radius=3, percent=160, threshold=2))
im = src.resize((COLS, ROWS), Image.LANCZOS)  # cells are 1.67x taller than wide, so a square crop keeps proportions
bg = orig.resize((COLS, ROWS), Image.LANCZOS).load()  # the flat cream paper stays blank
px = im.load()
lines = []
for y in range(ROWS):
    row = ""
    for x in range(COLS):
        if bg[x, y] > 226:
            row += " "
            continue
        dark = (1 - px[x, y] / 255) ** 0.75
        row += RAMP[min(len(RAMP) - 1, int(dark * len(RAMP)))]
    lines.append(row.rstrip())
(ROOT / "data/portrait.txt").write_text("\n".join(lines) + "\n", "utf-8")
print(f"{COLS}x{ROWS}, {sum(len(l) for l in lines)} chars")

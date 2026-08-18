"""Render a synthetic 'menu' image for pipeline smoke tests.

Not part of the eval set — just proves server + client + scoring end to end
before real photos exist.
"""

import pathlib

from PIL import Image, ImageDraw

OUT = pathlib.Path(__file__).resolve().parent.parent / "eval/photos/smoke.png"

LINES = [
    ("CAFE ORDO", 44),
    ("", 20),
    ("Masala Dosa ............ 120", 30),
    ("Veg Fried Rice ......... 180", 30),
    ("Paneer Tikka ........... 240", 30),
    ("Filter Coffee ........... 40", 30),
]

img = Image.new("RGB", (900, 500), "#f5f0e6")
d = ImageDraw.Draw(img)
y = 40
for text, size in LINES:
    d.text((70, y), text, fill="#222222", font_size=size)
    y += size + 24
OUT.parent.mkdir(parents=True, exist_ok=True)
img.save(OUT)
print(f"wrote {OUT}")

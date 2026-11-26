#!/usr/bin/env python3
"""Draw assets/face.json over the avatar so you can check it after swapping in your own picture.

Writes geometry-check.png (or the path you give): upper lids in red, lower lids in blue, irises
in green, hair regions in yellow with an arrow for the strand direction, the water line in cyan.
Open it, adjust the points in assets/face.json, run again.

usage: tools/check_geometry.py [OUT.png] [--zoom 3]
"""
import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out", nargs="?", default="geometry-check.png")
    ap.add_argument("--zoom", type=int, default=3)
    args = ap.parse_args()
    geo = json.loads((ROOT / "assets" / "face.json").read_text())
    im = Image.open(ROOT / "assets" / geo["source"]).convert("RGB")
    K = args.zoom
    im = im.resize((im.width * K, im.height * K), Image.BICUBIC)
    d = ImageDraw.Draw(im)
    pts = lambda ps: [(x * K, y * K) for x, y in ps]
    for e in geo["eyes"]:
        d.line(pts(e["upper"]), fill=(255, 40, 40), width=2)
        d.line(pts(e["lower"]), fill=(40, 120, 255), width=2)
        x, y, r = e["iris"]
        d.ellipse([(x - r) * K, (y - r) * K, (x + r) * K, (y + r) * K], outline=(0, 230, 0), width=2)
    for h in geo.get("hair", []):
        d.polygon(pts(h["polygon"]), outline=(255, 210, 0), width=2)
        (rx, ry), (dx, dy) = h["root"], h["direction"]
        n = math.hypot(dx, dy) or 1
        ex, ey = rx + dx / n * 60, ry + dy / n * 60
        d.line([(rx * K, ry * K), (ex * K, ey * K)], fill=(255, 210, 0), width=3)
        d.ellipse([ex * K - 5, ey * K - 5, ex * K + 5, ey * K + 5], fill=(255, 210, 0))
    wy = geo["water"]["top"] * K
    d.line([(0, wy), (im.width, wy)], fill=(0, 220, 220), width=2)
    im.save(args.out)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

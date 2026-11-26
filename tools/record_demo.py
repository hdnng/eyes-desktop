#!/usr/bin/env python3
"""Record the demo images in demo/ on a virtual screen (needs Xvfb and xdotool).

Starts Xvfb, runs eyes.py on it, steers the pointer along a scripted path (across the screen,
through the hair, two clicks on the water, close to an eye), grabs frames, draws the pointer on
them (screen grabs leave it out) and writes:

  demo/face.gif          the whole screen, scaled down
  demo/eye-closeup.gif   one eye at 1:1, so the glyphs can be read
  demo/face-dark.png     a still at full size

usage: tools/record_demo.py [--theme dark|light] [--seconds 8] [--fps 10] [--prefix face]
       tools/record_demo.py --still-only --theme light --prefix face-light
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageGrab

ROOT = Path(__file__).resolve().parent.parent
W, H = 1920, 1080


def pointer_path(t, T):
    """Where the pointer is at time t of a T-second demo, and whether to click."""
    keys = [(0.00, 160, 160), (0.14, 1760, 200), (0.22, 1700, 120),          # across the top
            (0.30, 200, 260), (0.38, 760, 120),                              # through the hair
            (0.48, 960, 1000), (0.56, 1300, 980),                            # down to the water
            (0.68, 1500, 450), (0.80, 1560, 470),                            # right up to an eye
            (0.90, 300, 900), (1.00, 960, 540)]
    u = t / T
    for (u0, x0, y0), (u1, x1, y1) in zip(keys, keys[1:]):
        if u0 <= u <= u1:
            k = (u - u0) / (u1 - u0)
            k = k * k * (3 - 2 * k)
            return x0 + (x1 - x0) * k, y0 + (y1 - y0) * k
    return keys[-1][1:]


CLICKS = (0.50, 0.58)       # fractions of the demo when the pointer clicks the water


def draw_pointer(im, x, y, scale=1.0):
    s = 1.6 * scale
    arrow = [(0, 0), (0, 17), (4, 13), (7, 20), (10, 19), (7, 12), (12, 12)]
    d = ImageDraw.Draw(im)
    d.polygon([(x + px * s, y + py * s) for px, py in arrow], fill=(255, 255, 255), outline=(0, 0, 0))


def to_gif(frames, path, fps):
    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=32) for f in frames]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=int(1000 / fps), loop=0,
                optimize=True, disposal=1)
    print(f"wrote {path} ({path.stat().st_size // 1024} KB, {len(frames)} frames)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--theme", default="dark")
    ap.add_argument("--scene", default="face")
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--fps", type=float, default=10.0)
    ap.add_argument("--prefix", default="face")
    ap.add_argument("--closeup", default="1240,330,700,260", help="x,y,w,h of the 1:1 close-up")
    ap.add_argument("--still-only", action="store_true")
    ap.add_argument("--display", default=":97")
    ap.add_argument("--gif-width", type=int, default=800, help="width of the full-screen GIF")
    args = ap.parse_args()
    out = ROOT / "demo"
    out.mkdir(exist_ok=True)
    env = dict(os.environ, DISPLAY=args.display)
    xvfb = subprocess.Popen(["Xvfb", args.display, "-screen", "0", f"{W}x{H}x24"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    app = subprocess.Popen([sys.executable, str(ROOT / "eyes.py"), "--theme", args.theme, "--scene", args.scene],
                           env=env)
    try:
        time.sleep(5)
        move = lambda x, y: subprocess.run(["xdotool", "mousemove", str(int(x)), str(int(y))], env=env)
        grab = lambda: ImageGrab.grab(xdisplay=args.display).convert("RGB")
        if args.still_only:
            move(1500, 300)
            time.sleep(1.5)
            im = grab()
            draw_pointer(im, 1500, 300)
            im.save(out / f"{args.prefix}.png", optimize=True)
            print(f"wrote demo/{args.prefix}.png")
            return
        cx, cy, cw, ch = (int(v) for v in args.closeup.split(","))
        full, close = [], []
        n = int(args.seconds * args.fps)
        clicked = set()
        t0 = time.monotonic()
        for i in range(n):
            t = i / args.fps
            x, y = pointer_path(t, args.seconds)
            move(x, y)
            for c in CLICKS:
                if c not in clicked and t / args.seconds >= c:
                    subprocess.run(["xdotool", "click", "1"], env=env)
                    clicked.add(c)
            while time.monotonic() - t0 < t + 0.5 / args.fps:
                time.sleep(0.005)
            im = grab()
            if i == int(n * 0.68):
                still = im.copy()
                draw_pointer(still, x, y)
                still.save(out / f"{args.prefix}-{args.theme}.png", optimize=True)
            draw_pointer(im, x, y)
            full.append(im.resize((args.gif_width, args.gif_width * H // W), Image.LANCZOS))
            c = im.crop((cx, cy, cx + cw, cy + ch))
            close.append(c)
        to_gif(full, out / f"{args.prefix}.gif", args.fps)
        to_gif(close, out / "eye-closeup.gif", args.fps)
    finally:
        app.terminate()
        app.wait(5)
        xvfb.terminate()


if __name__ == "__main__":
    main()

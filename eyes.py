#!/usr/bin/env python3
"""eyes-desktop: the ASCII eye from github.com/hdnng/hdnng as a live wallpaper that watches the mouse.

The profile card can only play a scripted routine (GitHub runs no scripts), so here the same
eye is driven by the real pointer instead. While the mouse rests it falls back to the card's
own routine: glances, squints and blinks.

The ASCII layers in assets/eye.json are rendered at startup at whatever scale fits the
monitor, so the glyphs stay sharp on any resolution. Only the small region around the eye
opening is recomposed per frame, and only when something visibly changed.

Needs an X11 session (Ubuntu on Xorg) to read the pointer anywhere on screen. On Wayland the
window still runs, but the pointer is only seen over X windows, so the eye mostly idles.

usage: eyes.py [--theme dark|light] [--size 0.6] [--monitor primary|N] [--window]
"""
import argparse
import json
import math
import os
import random
import signal
import sys
import time
from pathlib import Path

import tkinter as tk
from PIL import Image, ImageDraw, ImageFont, ImageTk
from Xlib import display as xdisplay

ROOT = Path(__file__).resolve().parent
DEFAULTS = dict(theme="dark", size=0.6, position=[0.5, 0.5], monitor="primary", fps=30,
                idle_after=8.0, background=None, font=None)
THEMES = {  # same palette as the profile card
    "dark": dict(bg="#0f2027", art="#9fd8e6", value="#7ee0c8"),
    "light": dict(bg="#f6f8fa", art="#203a43", value="#0a7d6c"),
}
FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
         "/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf",
         "/usr/share/fonts/dejavu/DejaVuSansMono-Bold.ttf"]

# ---------------------------------------------------------------- idle routine (from build_card.py)
EYE_T = 14.0
GLANCES = [(0.0, 0, 0, 0, None), (1.4, 34, -2, 0.18, None), (2.8, 33, -6, 0.22, None),
           (3.15, 33, -2, 0.22, None), (3.5, 33, 2, 0.25, None), (3.85, 33, 6, 0.28, None),
           (4.6, 0, 0, 0, None), (6.0, -30, -9, 0, None), (7.3, -26, 8, 0.1, None),
           (8.5, 31, 0, 0, None), (8.85, 0, 0, 0, None), (11.2, 10, -3, 0, 0.9),
           (12.3, -8, 2, 0, 0.9), (13.3, 0, 0, 0, 0.7)]
IDLE_BLINKS = [4.5, 9.9, 10.26]
PUPIL = [(0, 1.0), (5.9, 1.0), (6.5, 1.2), (7.3, 1.2), (7.9, 1.0), (8.4, 1.0), (8.7, 0.8),
         (10.8, 0.8), (11.8, 1.0)]
GAZE_X, GAZE_UP, GAZE_DOWN = 34.0, 9.0, 8.0     # how far the iris travels, in art px


def ease(s):
    s = min(max(s, 0.0), 1.0)
    return s * s * (3 - 2 * s)


def snap(s):
    s = min(max(s, 0.0), 1.0)
    return 1 - (1 - s) ** 3


def glance_at(t):
    x, y, q = GLANCES[0][1:4]
    for (t1, x1, y1, q1, move) in GLANCES[1:]:
        if t >= t1:
            dur = move or 0.05 + math.hypot(x1 - x, y1 - y) * 0.0025
            k = (ease if move else snap)((t - t1) / dur)
            x, y, q = x + (x1 - x) * k, y + (y1 - y) * k, q + (q1 - q) * k
    return x, y, q


def pupil_at(t):
    for (t0, a), (t1, b) in zip(PUPIL, PUPIL[1:]):
        if t0 <= t < t1:
            return a + (b - a) * ease((t - t0) / (t1 - t0))
    return PUPIL[-1][1]


def blink_amount(d):
    """Lid closure added by a blink that started d seconds ago (0 .. 1)."""
    if 0 <= d < 0.07:
        return ease(d / 0.07)
    if 0.07 <= d < 0.12:
        return 1.0
    if 0.12 <= d < 0.32:
        return 1 - ease((d - 0.12) / 0.2)
    return 0.0


def rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


# ---------------------------------------------------------------- rendering
class EyeArt:
    """The eye's layers rendered for one scale and theme, and the per-frame compositor."""

    def __init__(self, eye, scale, colors, font_path):
        self.e, self.S = eye, scale
        self.bg, self.art, self.value = rgb(colors["bg"]), rgb(colors["art"]), rgb(colors["value"])
        self.font = ImageFont.truetype(font_path, max(1, round(eye["font_size"] * scale)))
        cw, ch, S = eye["cell_w"], eye["cell_h"], scale
        self.size = (round(eye["cols"] * cw * S), round(eye["rows"] * ch * S))

        base = self.mask(dict(col=0, row=0, rows=eye["base"]))[0]
        self.base = Image.new("RGB", self.size, self.bg)
        self.base.paste(self.art, (0, 0), base)

        # dynamic region: the opening plus everything a lid frame can cover, in screen px
        pts = list(eye["opening"]) + [p for lid in eye["lids"] for p in lid["poly"]]
        x0, y0 = min(p[0] for p in pts) * S, min(p[1] for p in pts) * S
        x1, y1 = max(p[0] for p in pts) * S, max(p[1] for p in pts) * S
        for lid in eye["lids"]:
            m, (mx, my) = self.mask(lid["text"])
            x0, y0 = min(x0, mx), min(y0, my)
            x1, y1 = max(x1, mx + m.width), max(y1, my + m.height)
        pad = 4
        self.box = (max(0, int(x0) - pad), max(0, int(y0) - pad),
                    min(self.size[0], int(x1) + pad), min(self.size[1], int(y1) + pad))
        ux, uy = self.box[:2]
        usize = (self.box[2] - ux, self.box[3] - uy)
        self.base_u = self.base.crop(self.box)

        def poly_mask(poly):
            m = Image.new("L", usize, 0)
            ImageDraw.Draw(m).polygon([(x * S - ux, y * S - uy) for x, y in poly], fill=255)
            return m

        def placed(spr):
            m, (mx, my) = self.mask(spr)
            out = Image.new("L", usize, 0)
            out.paste(m, (round(mx - ux), round(my - uy)))
            return out

        self.opening = poly_mask(eye["opening"])
        self.lid_levels = [lid["c"] for lid in eye["lids"]]
        self.lids = [(poly_mask(lid["poly"]), placed(lid["text"])) for lid in eye["lids"]]
        self.iris, ipos = self.mask(eye["iris"])
        self.iris_pos = (ipos[0] - ux, ipos[1] - uy)
        self.pupil, ppos = self.mask(eye["pupil"])
        self.pupil_pos = (ppos[0] - ux, ppos[1] - uy)
        self.glint, gpos = self.mask(eye["glint"])
        self.glint_pos = (gpos[0] - ux, gpos[1] - uy)
        self.center = (eye["iris_center"][0] * S - ux, eye["iris_center"][1] * S - uy)

    def mask(self, spr):
        """Render a sprite {col, row, rows} to an L mask; returns (mask, top-left in px)."""
        e, S = self.e, self.S
        cw, ch = e["cell_w"] * S, e["cell_h"] * S
        cols = max((len(r) for r in spr["rows"]), default=1)
        m = Image.new("L", (max(1, math.ceil(cols * cw)), max(1, math.ceil(len(spr["rows"]) * ch + 2))), 0)
        d = ImageDraw.Draw(m)
        for r, row in enumerate(spr["rows"]):
            y = (r + e["baseline"]) * ch
            for c, char in enumerate(row):
                if char != " ":
                    d.text((c * cw, y), char, font=self.font, fill=255, anchor="ls")
        return m, (spr["col"] * cw, spr["row"] * ch)

    def lid_frame(self, c):
        levels = self.lid_levels
        if c < levels[0] / 2:
            return None
        return min(range(len(levels)), key=lambda k: abs(levels[k] - c))

    def compose(self, gx, gy, pupil, lid, light):
        """The dynamic region for a gaze of (gx, gy) art px, pupil scale and lid frame index."""
        S, e = self.S, self.e
        dx, dy = gx * S, gy * S
        cx, cy = self.center[0] + dx, self.center[1] + dy
        inner = self.base_u.copy()
        d = ImageDraw.Draw(inner)
        r = (e["r_iris"] + 1) * S
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=self.bg)
        inner.paste(self.value, (round(self.iris_pos[0] + dx), round(self.iris_pos[1] + dy)), self.iris)
        rp = e["r_pupil"] * S * pupil
        d.ellipse([cx - rp, cy - rp, cx + rp, cy + rp], fill=self.bg)
        gdx, gdy = 0.35 * dx, 0.35 * dy             # catchlights lag behind the iris
        if light:                                   # ink pupil, catchlights cut out of it
            w, h = self.pupil.size
            m = self.pupil.resize((max(1, round(w * pupil)), max(1, round(h * pupil))))
            ox = self.center[0] + (self.pupil_pos[0] - self.center[0]) * pupil + dx
            oy = self.center[1] + (self.pupil_pos[1] - self.center[1]) * pupil + dy
            inner.paste(self.art, (round(ox), round(oy)), m)
            gc = (self.center[0] + gdx, self.center[1] + gdy)
            win, dot = e["glint_shape"]["window"], e["glint_shape"]["dot"]
            d.polygon([(gc[0] + x * S, gc[1] + y * S) for x, y in win], fill=self.bg)
            rr = dot[2] * S
            d.ellipse([gc[0] + dot[0] * S - rr, gc[1] + dot[1] * S - rr,
                       gc[0] + dot[0] * S + rr, gc[1] + dot[1] * S + rr], fill=self.bg)
        else:                                       # dark pupil, catchlights drawn in ink
            inner.paste(self.art, (round(self.glint_pos[0] + gdx), round(self.glint_pos[1] + gdy)), self.glint)
        frame = Image.composite(inner, self.base_u, self.opening)
        if lid is not None:
            poly, text = self.lids[lid]
            frame.paste(self.bg, None, poly)
            frame.paste(self.art, None, text)
        return frame


# ---------------------------------------------------------------- the wallpaper window
def get_monitors(d):
    try:
        if d.has_extension("RANDR"):
            res = d.xrandr_get_monitors(d.screen().root, is_active=True)
            mons = [dict(x=m.x, y=m.y, w=m.width_in_pixels, h=m.height_in_pixels, primary=bool(m.primary))
                    for m in res.monitors]
            if mons:
                return mons
    except Exception:
        pass
    s = d.screen()
    return [dict(x=0, y=0, w=s.width_in_pixels, h=s.height_in_pixels, primary=True)]


class App:
    def __init__(self, cfg, window_mode):
        self.cfg, self.window_mode = cfg, window_mode
        self.eye = json.loads((ROOT / "assets" / "eye.json").read_text())
        self.colors = dict(THEMES[cfg["theme"]])
        if cfg.get("background"):
            self.colors["bg"] = cfg["background"]
        self.light = cfg["theme"] == "light"
        self.font = cfg.get("font") or next((f for f in FONTS if os.path.exists(f)), None)
        if not self.font:
            sys.exit("No DejaVu Sans Mono font found; install fonts-dejavu-core or set \"font\" in config.json")

        self.x = xdisplay.Display()
        self.root = tk.Tk(className="eyes-desktop")
        self.root.title("eyes-desktop")
        self.root.configure(bg=self.colors["bg"])
        if not window_mode:
            self.root.wm_attributes("-type", "desktop")   # sit below every app window
        self.canvas = tk.Canvas(self.root, bg=self.colors["bg"], highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.root.bind("<Escape>", lambda e: self.root.quit())
        signal.signal(signal.SIGTERM, lambda *a: self.root.quit())
        signal.signal(signal.SIGINT, lambda *a: self.root.quit())

        now = time.monotonic()
        self.gaze = [0.0, 0.0]
        self.jit, self.jit_target, self.next_jit = [0.0, 0.0], [0.0, 0.0], now
        self.pupil = 1.0
        self.last_ptr, self.last_move = None, -1e9
        self.idle_start = now
        self.blinks, self.last_blink = [], now
        self.next_blink = now + random.uniform(2.5, 6.0)
        self.prev_target = (0.0, 0.0)
        self.last_key, self.last_tick, self.next_check = None, now, now + 3
        self.mons = None
        self.layout()

    # -- geometry
    def pick_monitor(self, mons):
        want = self.cfg["monitor"]
        if isinstance(want, int) and 0 <= want < len(mons):
            return mons[want]
        return next((m for m in mons if m["primary"]), mons[0])

    def layout(self):
        if self.window_mode:
            w, h = 1280, 720
            self.mons = [dict(x=0, y=0, w=w, h=h, primary=True)]
            self.root.geometry(f"{w}x{h}")
        else:
            self.mons = get_monitors(self.x)
            w = max(m["x"] + m["w"] for m in self.mons)
            h = max(m["y"] + m["h"] for m in self.mons)
            self.root.geometry(f"{w}x{h}+0+0")
        mon = self.pick_monitor(self.mons)
        e = self.eye
        aw, ah = e["cols"] * e["cell_w"], e["rows"] * e["cell_h"]
        S = min(self.cfg["size"] * mon["h"] / ah, 0.92 * mon["w"] / aw)
        self.art = EyeArt(e, S, self.colors, self.font)
        W, H = self.art.size
        px, py = self.cfg["position"]
        ox = round(min(max(mon["x"] + px * mon["w"] - W / 2, mon["x"]), mon["x"] + mon["w"] - W))
        oy = round(min(max(mon["y"] + py * mon["h"] - H / 2, mon["y"]), mon["y"] + mon["h"] - H))
        self.mon, self.origin = mon, (ox, oy)
        self.base_photo = ImageTk.PhotoImage(self.art.base)
        ux, uy = self.art.box[:2]
        self.dyn_photo = ImageTk.PhotoImage(self.art.base_u)
        self.canvas.delete("all")
        self.canvas.create_image(ox, oy, image=self.base_photo, anchor="nw")
        self.canvas.create_image(ox + ux, oy + uy, image=self.dyn_photo, anchor="nw")
        self.eye_screen = (ox + e["iris_center"][0] * S, oy + e["iris_center"][1] * S)
        self.last_key = None

    def screen_offset(self):
        """Where the canvas sits on the X screen (only differs from 0,0 in --window mode)."""
        return (self.root.winfo_rootx(), self.root.winfo_rooty()) if self.window_mode else (0, 0)

    # -- behaviour
    def blink(self, now):
        self.blinks.append(now)
        self.last_blink = now
        if random.random() < 0.15:                 # sometimes a double blink
            self.blinks.append(now + 0.36)

    def tick(self):
        now = time.monotonic()
        dt, self.last_tick = min(now - self.last_tick, 0.1), now

        try:
            p = self.x.screen().root.query_pointer()
            ptr = (p.root_x, p.root_y)
        except Exception:
            ptr = self.last_ptr
        if ptr is not None and ptr != self.last_ptr:
            if self.last_ptr is not None:
                self.last_move = now
            self.last_ptr = ptr
        idle = now - self.last_move > self.cfg["idle_after"]
        if not idle:
            self.idle_start = now

        if idle:
            t = (now - self.idle_start) % EYE_T
            tx, ty, squint = glance_at(t)
            pupil_target = pupil_at(t)
            for b in IDLE_BLINKS:                   # the routine's own blinks
                if abs(t - b) < dt / 2 + 1e-3 and now - self.last_blink > 0.3:
                    self.blink(now)
        else:
            sx, sy = self.screen_offset()
            vx = ptr[0] - (self.eye_screen[0] + sx)
            vy = ptr[1] - (self.eye_screen[1] + sy)
            nx, ny = vx / (0.5 * self.mon["w"]), vy / (0.5 * self.mon["h"])
            tx = GAZE_X * math.tanh(1.8 * nx)
            ty = (GAZE_UP if ny < 0 else GAZE_DOWN) * math.tanh(1.8 * ny)
            k = math.hypot(tx / GAZE_X, ty / (GAZE_UP if ty < 0 else GAZE_DOWN))
            if k > 1:
                tx, ty = tx / k, ty / k
            near = math.hypot(nx, ny)               # 0 on the pupil .. ~1 at the screen edge
            squint = 0.3 * max(0.0, 1 - near / 0.18)     # mouse right on the eye: suspicious squint
            pupil_target = 0.8 + 0.4 * min(near, 1.0)    # close: narrow, far: wide

        # big jumps come with a blink, like real eyes
        if math.hypot(tx - self.prev_target[0], ty - self.prev_target[1]) > 25 and now - self.last_blink > 1.5:
            self.blink(now)
        self.prev_target = (tx, ty)
        if now >= self.next_blink:
            self.blink(now)
            self.next_blink = now + random.uniform(2.5, 6.5)

        k = 1 - math.exp(-dt * 18)                  # quick, saccade-like follow
        self.gaze[0] += (tx - self.gaze[0]) * k
        self.gaze[1] += (ty - self.gaze[1]) * k
        if now >= self.next_jit:                    # tiny fixational jitter, never frozen
            self.jit_target = [random.uniform(-1.3, 1.3), random.uniform(-0.9, 0.9)]
            self.next_jit = now + random.uniform(0.35, 0.6)
        kj = 1 - math.exp(-dt * 50)
        self.jit = [j + (t - j) * kj for j, t in zip(self.jit, self.jit_target)]
        self.pupil += (pupil_target - self.pupil) * (1 - math.exp(-dt * 3))

        gx, gy = self.gaze[0] + self.jit[0], self.gaze[1] + self.jit[1]
        c = 0.9 * squint + 0.004 * max(gy, 0)
        self.blinks = [b for b in self.blinks if now - b < 0.4]
        for b in self.blinks:
            c += (1 - c) * blink_amount(now - b)
        lid = self.art.lid_frame(c)

        S = self.art.S
        key = (round(gx * S), round(gy * S), round(self.pupil * 40), lid)
        if key != self.last_key:
            self.last_key = key
            self.dyn_photo.paste(self.art.compose(gx, gy, self.pupil, lid, self.light))

        if now >= self.next_check and not self.window_mode:   # monitor plugged in or resolution changed
            self.next_check = now + 3
            mons = get_monitors(self.x)
            if mons != self.mons:
                self.layout()

        spent = time.monotonic() - now
        self.root.after(max(1, int(1000 / self.cfg["fps"] - spent * 1000)), self.tick)

    def run(self):
        self.root.after(0, self.tick)
        self.root.mainloop()


def load_config(args):
    cfg = dict(DEFAULTS)
    path = Path(args.config) if args.config else ROOT / "config.json"
    if path.exists():
        cfg.update(json.loads(path.read_text()))
    for k in ("theme", "size", "fps"):
        if getattr(args, k) is not None:
            cfg[k] = getattr(args, k)
    if args.monitor is not None:
        cfg["monitor"] = int(args.monitor) if args.monitor.isdigit() else args.monitor
    if cfg["theme"] not in THEMES:
        sys.exit(f"theme must be one of {', '.join(THEMES)}")
    return cfg


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--theme", choices=list(THEMES))
    ap.add_argument("--size", type=float, help="eye height as a fraction of the monitor height (default 0.6)")
    ap.add_argument("--monitor", help="'primary' or a monitor index")
    ap.add_argument("--fps", type=int)
    ap.add_argument("--config", help="path to a config.json")
    ap.add_argument("--window", action="store_true", help="run in a normal 1280x720 window, for trying it out")
    args = ap.parse_args()
    if os.environ.get("XDG_SESSION_TYPE") == "wayland":
        print("warning: Wayland session - the pointer is only visible over X windows, so the eye will mostly "
              "play its idle routine. Log in with 'Ubuntu on Xorg' for full mouse tracking.", file=sys.stderr)
    if not os.environ.get("DISPLAY"):
        sys.exit("No X display (DISPLAY is not set).")
    App(load_config(args), args.window).run()


if __name__ == "__main__":
    main()

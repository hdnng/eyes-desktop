"""Scene 'face': the GitHub avatar redrawn in ASCII, alive.

Every frame the avatar is resampled through a displacement field and turned into glyphs:

  eyes      the inside of each eye opening is warped so the iris slides towards the pointer
            (lids stay put), the pupil swells or narrows, and the upper lid slides down to
            squint and blink, with a dark lash line on its edge
  water     the water in the lower half sways, and rings spread from clicks and from the
            pointer gliding over it
  hair      drifts slowly
  stars     the white specks in the hair twinkle
  light     a soft glow follows the pointer across the face

Geometry (eye ellipses, water line...) is in avatar pixels in assets/face.json.
"""
import json
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from ascii_render import GlyphSet, TiledCanvas, dither_for, SUB_X, SUB_Y
from behaviour import Follower

ROOT = Path(__file__).resolve().parent
GAZE_U, GAZE_V = 0.30, 0.25        # largest iris travel, as a fraction of the eye's half axes


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def prepare(path):
    """The avatar as float greyscale with its tones spread out and its lines sharpened."""
    im = ImageOps.equalize(Image.open(path).convert("L"))
    im = im.filter(ImageFilter.UnsharpMask(radius=8, percent=180, threshold=0))
    a = np.asarray(im, np.float32) / 255
    lo, hi = np.percentile(a, [1, 99])
    return np.clip((a - lo) / (hi - lo), 0, 1)


def find_stars(path, bottom, limit):
    """Small bright specks on dark ground in the hair: (x, y) in avatar px."""
    a = np.asarray(Image.open(path).convert("L"), np.float32) / 255
    local = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.BoxBlur(5)), np.float32) / 255
    score = (a - local) * (a > 0.6)
    score[bottom:] = 0
    stars = []
    for _ in range(limit):
        y, x = np.unravel_index(score.argmax(), score.shape)
        if score[y, x] < 0.25:
            break
        stars.append((int(x), int(y)))
        score[max(0, y - 10):y + 11, max(0, x - 10):x + 11] = 0
    return stars


def sample(img, X, Y):
    """Bilinear sample of img at float coordinates (clamped at the border)."""
    h, w = img.shape
    X = np.clip(X, 0, w - 1.001)
    Y = np.clip(Y, 0, h - 1.001)
    x0, y0 = X.astype(np.int32), Y.astype(np.int32)
    fx, fy = X - x0, Y - y0
    a, b = img[y0, x0], img[y0, x0 + 1]
    c, d = img[y0 + 1, x0], img[y0 + 1, x0 + 1]
    return (a + (b - a) * fx) * (1 - fy) + (c + (d - c) * fx) * fy


class FaceScene:
    def __init__(self, cfg, colors, font, canvas):
        self.cfg, self.font, self.canvas = cfg, font, canvas
        self.geo = json.loads((ROOT / "assets" / "face.json").read_text())
        src_path = ROOT / "assets" / self.geo["source"]
        self.src = prepare(src_path)
        self.size = self.src.shape[0]
        self.light = cfg["theme"] == "light"
        # tone curve, as a lookup table: an S-curve for contrast around the skin's mid greys.
        # Dark theme draws bright parts dense; light theme draws dark parts dense.
        x = np.linspace(0, 1, 256, dtype=np.float32)
        sig = lambda v: 1 / (1 + np.exp(-7 * (v - 0.5)))
        sc = lambda v: (sig(v) - sig(0)) / (sig(1) - sig(0))
        self.tone = (sc(1 - x) ** 1.1 if self.light else sc(x) ** 1.3).astype(np.float32)
        self.fx = dict(dict(water=True, ripples=True, hair=True, stars=True, glow=True), **cfg.get("effects", {}))
        st = self.geo["stars"]
        self.stars = find_stars(src_path, st["bottom"], st["max"]) if self.fx["stars"] else []
        self.star_phase = [(random.uniform(0, 6.3), random.uniform(1.6, 4.5)) for _ in self.stars]
        self.eyes = self.geo["eyes"]
        self.follow = [Follower() for _ in self.eyes]
        self.ripples = []
        self.last_wake = 0.0
        self.bands, self.next_amb, self.last_sig = [], 0.0, None
        self.eye_cache = [None] * len(self.eyes)

        bg, art, value = rgb(colors["bg"]), rgb(colors["art"]), rgb(colors["value"])
        hi = (255, 255, 255) if not self.light else rgb("#0969da")
        # colour ids: 0 art, 1 iris, 2-4 pointer glow, 5 twinkling star
        self.bg = bg
        self.palette = [art, value, mix(art, hi, 0.25), mix(art, hi, 0.5), mix(art, hi, 0.75),
                        (255, 255, 255) if not self.light else rgb("#0969da")]

    # ------------------------------------------------------------ layout
    def layout(self, mon):
        cfg, n = self.cfg, self.size
        side = min(cfg.get("face_size", 0.92) * mon["h"], mon["h"], 0.96 * mon["w"])
        cw = max(3, round(cfg.get("cell", 5) * mon["h"] / 1080))
        ch = 2 * cw
        self.cols, self.rows = int(side // cw), int(side // ch)
        W, H = self.cols * cw, self.rows * ch
        px, py = cfg["position"]
        ox = round(min(max(mon["x"] + px * mon["w"] - W / 2, mon["x"]), mon["x"] + mon["w"] - W))
        oy = round(min(max(mon["y"] + py * mon["h"] - H / 2, mon["y"]), mon["y"] + mon["h"] - H))
        self.origin, self.px_size = (ox, oy), (W, H)

        self.gs = GlyphSet(self.font, cw, ch)
        fh, fw = self.rows * SUB_Y, self.cols * SUB_X
        xs = (np.arange(fw, dtype=np.float32) + 0.5) / fw * n - 0.5
        ys = (np.arange(fh, dtype=np.float32) + 0.5) / fh * n - 0.5
        self.X0, self.Y0 = np.meshgrid(xs, ys)
        self.dither = dither_for((fh, fw)).astype(np.float32)
        # fade the square's edges into the background
        u = np.minimum(xs, n - 1 - xs) / n
        v = np.minimum(ys, n - 1 - ys) / n
        self.vignette = (smoothstep(0.0, 0.07, v)[:, None] * smoothstep(0.0, 0.07, u)[None, :]).astype(np.float32)
        # cell centres in avatar px, for colouring
        cx = (np.arange(self.cols, dtype=np.float32) + 0.5) / self.cols * n
        cy = (np.arange(self.rows, dtype=np.float32) + 0.5) / self.rows * n
        self.CX, self.CY = np.meshgrid(cx, cy)

        wat = self.geo["water"]
        self.water_r0 = int(np.searchsorted(ys, wat["top"]))
        self.water_w = smoothstep(wat["top"], wat["full"], self.Y0[self.water_r0:]).astype(np.float32)
        self.hair_r1 = int(np.searchsorted(ys, self.geo["hair"]["bottom"]))
        self.hair_w = (1 - ys[:self.hair_r1] / self.geo["hair"]["bottom"]).astype(np.float32)[:, None]

        # per eye: a window of whole cells around it (cell slices and feature slices)
        self.eye_cells, self.eye_win = [], []
        for e in self.eyes:
            r = max(e["a"], e["b"]) + 4
            cells = self.cell_rect(e["center"][0] - r, e["center"][1] - r - 12, e["center"][0] + r, e["center"][1] + r)
            self.eye_cells.append(cells)
            self.eye_win.append(self.feat(cells))
        self.star_cells = [(min(self.rows - 1, int(y / n * self.rows)), min(self.cols - 1, int(x / n * self.cols)))
                           for x, y in self.stars]

        self.tiles = TiledCanvas(self.canvas, self.gs, self.rows, self.cols, ox, oy, self.bg, self.palette)
        s = W / n
        self.scale = s
        self.eye_screen = [(ox + e["center"][0] * s, oy + e["center"][1] * s) for e in self.eyes]
        self.focus = (ox + W / 2, oy + 0.55 * H)
        # the still picture; animated row bands are recomputed on top of it
        allw = (slice(None), slice(None))
        self.I0 = self.to_ink(sample(self.src, self.X0, self.Y0), allw)
        self.G0 = self.gs.glyphs(self.I0, self.dither)
        self.Xa, self.Ya = self.X0.copy(), self.Y0.copy()
        self.I, self.G = self.I0.copy(), self.G0.copy()
        self.bands, self.next_amb, self.last_sig = [], 0.0, None
        self.eye_cache = [None] * len(self.eyes)

    def cell_rect(self, x0, y0, x1, y1):
        """Cells covering an avatar-px rectangle, as (row slice, col slice)."""
        n = self.size
        r0, r1 = max(0, int(y0 / n * self.rows)), min(self.rows, int(math.ceil(y1 / n * self.rows)))
        c0, c1 = max(0, int(x0 / n * self.cols)), min(self.cols, int(math.ceil(x1 / n * self.cols)))
        return slice(r0, max(r0, r1)), slice(c0, max(c0, c1))

    @staticmethod
    def feat(cells):
        rs, cs = cells
        return slice(rs.start * SUB_Y, rs.stop * SUB_Y), slice(cs.start * SUB_X, cs.stop * SUB_X)

    def to_ink(self, B, win):
        return self.tone[(np.clip(B, 0, 1) * 255).astype(np.uint8)] * self.vignette[win]

    def to_src(self, x, y):
        return (x - self.origin[0]) / self.scale, (y - self.origin[1]) / self.scale

    # ------------------------------------------------------------ interaction
    def click(self, x, y, now):
        sx, sy = self.to_src(x, y)
        if 0 <= sx < self.size and 0 <= sy < self.size:
            self.ripples.append((sx, sy, now, 4.0))

    def wake(self, beh, now):
        """Small rings behind the pointer while it glides over the water."""
        if not (self.fx["ripples"] and beh.moved and beh.ptr and beh.on_desktop) or now - self.last_wake < 0.12:
            return
        sx, sy = self.to_src(*beh.ptr)
        if 0 <= sx < self.size and self.geo["water"]["top"] <= sy < self.size:
            self.ripples.append((sx, sy, now, 1.6))
            self.last_wake = now

    # ------------------------------------------------------------ one frame
    def ambient(self, now):
        """Water, ripples and hair: the slow-moving part, recomputed at a lower rate and only
        for the bands of rows they touch. Returns the feature-row bands that changed."""
        fh = self.X0.shape[0]
        to_row = lambda y: int(min(max(y / self.size * fh, 0), fh))
        want = []
        if self.fx["hair"] and self.hair_r1 > 0:
            want.append((0, self.hair_r1))
        if self.fx["water"] and self.water_r0 < fh:
            want.append((self.water_r0, fh))
        rip = []
        for (rx, ry, t0, amp) in self.ripples:
            age = now - t0
            radius, width = 55.0 * age, 14.0 + 6.0 * age
            ya, yb = to_row(ry - radius - 2 * width), to_row(ry + radius + 2 * width) + 1
            if ya < yb:
                want.append((ya, yb))
                rip.append((rx, ry, age, amp, radius, width, ya, yb))
        # align to whole cell rows and merge
        want = sorted((a - a % SUB_Y, min(fh, b + (-b) % SUB_Y)) for a, b in want)
        bands = []
        for a, b in want:
            if bands and a <= bands[-1][1]:
                bands[-1] = (bands[-1][0], max(bands[-1][1], b))
            else:
                bands.append((a, b))
        # rows animated last time but not now go back to the still picture
        dirty = list(bands)
        for a, b in self.bands:
            covered = np.zeros(b - a, bool)
            for c, d in bands:
                lo, hi = max(a, c), min(b, d)
                if lo < hi:
                    covered[lo - a:hi - a] = True
            if not covered.all():
                idx = np.nonzero(~covered)[0] + a
                self.Xa[idx], self.Ya[idx] = self.X0[idx], self.Y0[idx]
                self.I[idx] = self.I0[idx]
                rows = np.unique(idx // SUB_Y)
                self.G[rows] = self.G0[rows]
                dirty.append((int(idx.min()), int(idx.max()) + 1))
        self.bands = bands

        t = now
        for a, b in bands:
            X, Y = self.X0[a:b].copy(), self.Y0[a:b].copy()
            shade = np.zeros_like(X)                  # light and shadow on the water's surface
            lo = max(a, self.water_r0)
            if self.fx["water"] and lo < b:
                sl = slice(lo - a, b - a)
                wy, wx = self.Y0[lo:b], self.X0[lo:b]
                w = self.water_w[lo - self.water_r0:b - self.water_r0]
                X[sl] += w * (0.8 * np.sin(0.09 * wy + 1.3 * t) + 0.5 * np.sin(0.05 * wy - 0.04 * wx + 0.8 * t))
                Y[sl] += w * 0.5 * np.sin(0.07 * wx + 1.1 * t)
                shade[sl] += w * 0.07 * np.sin(0.11 * wy - 0.03 * wx + 1.7 * t) * np.sin(0.05 * wx + 0.6 * t)
            for (rx, ry, age, amp, radius, width, ya, yb) in rip:
                lo, hi = max(a, ya), min(b, yb)
                if lo >= hi:
                    continue
                dx, dy = self.X0[lo:hi] - rx, self.Y0[lo:hi] - ry
                dist = np.sqrt(dx * dx + dy * dy) + 1e-3
                off = dist - radius
                wave = amp * math.exp(-1.2 * age) * np.sin(0.35 * off) * np.exp(-(off / width) ** 2)
                if self.water_r0 > lo:              # calmer outside the water
                    wave[:self.water_r0 - lo] *= 0.3
                X[lo - a:hi - a] += wave * dx / dist
                Y[lo - a:hi - a] += wave * dy / dist
                shade[lo - a:hi - a] -= 0.09 * wave       # dark troughs, bright crests
            hi = min(b, self.hair_r1)
            if self.fx["hair"] and a < hi:
                X[:hi - a] += 1.4 * self.hair_w[a:hi] * np.sin(0.5 * t + 0.025 * self.Y0[a:hi])
            self.Xa[a:b], self.Ya[a:b] = X, Y
            win = (slice(a, b), slice(None))
            self.I[a:b] = self.to_ink(sample(self.src, X, Y) + shade, win)
            self.G[a // SUB_Y:b // SUB_Y] = self.gs.glyphs(self.I[a:b], self.dither[a:b])
        return dirty

    def frame(self, now, dt, beh):
        self.wake(beh, now)
        self.ripples = [r for r in self.ripples if now - r[2] < 3.0][-24:]
        changed = False
        if now >= self.next_amb:
            dirty = self.ambient(now)
            rate = self.cfg.get("ambient_fps", 8) if not self.ripples else 20
            self.next_amb = now + 1.0 / rate
            for k, (ws, _) in enumerate(self.eye_win):   # bands crossing an eye wiped its patch
                if any(a < ws.stop and ws.start < b for a, b in dirty):
                    self.eye_cache[k] = None
            changed = changed or bool(dirty)

        for k, (e, win, cells) in enumerate(zip(self.eyes, self.eye_win, self.eye_cells)):
            th = math.radians(e["angle"])
            tx, ty, squint = beh.target(self.eye_screen[k], th)
            nx, ny = self.follow[k].step((tx, ty), dt, beh.jit)
            c = beh.lid(squint, ny, now)
            # quantised so tiny changes that would not move a glyph skip the work
            key = (round(nx * 40), round(ny * 30), round(c * 30), round(beh.pupil * 30))
            cache = self.eye_cache[k]
            if cache is not None and cache[0] == key:
                continue
            X, Y = self.Xa[win].copy(), self.Ya[win].copy()
            d = self.warp_eye(e, X, Y, nx, ny, c, beh.pupil)
            patch = sample(self.src, X, Y)
            if d is not None:
                patch *= d
            self.I[win] = self.to_ink(patch, win)
            self.G[cells] = self.gs.glyphs(self.I[win], self.dither[win])
            self.eye_cache[k] = (key, self.iris_cells(e, cells, nx, ny, c))
            changed = True

        glow_key = None
        if self.fx["glow"] and beh.ptr is not None and beh.on_desktop:
            sx, sy = self.to_src(*beh.ptr)
            R = 0.2 * self.size
            if -R < sx < self.size + R and -R < sy < self.size + R:
                glow_key = (round(sx / 2), round(sy / 2))
        star_key = tuple(self.star_level(now, ph, per) for ph, per in self.star_phase)
        sig = (glow_key, star_key)
        if not changed and sig == self.last_sig:
            return                                   # nothing visible changed
        self.last_sig = sig

        glyphs = self.G.copy()
        colors = np.zeros((self.rows, self.cols), np.uint8)
        for cells, (key, iris) in zip(self.eye_cells, self.eye_cache):
            colors[cells][iris] = 1
        if glow_key is not None:
            self.glow(beh.ptr, glyphs, colors)
        self.twinkle(star_key, glyphs, colors)
        self.tiles.show(glyphs, colors)

    def warp_eye(self, e, X, Y, nx, ny, c, pupil):
        """Warp one eye's window (X, Y modified in place). Returns a darkening factor for the
        lash line, or None."""
        cx, cy = e["center"]
        a, b = e["a"], e["b"]
        th = math.radians(e["angle"])
        co, si = math.cos(th), math.sin(th)
        x, y = X.copy(), Y.copy()
        dx, dy = x - cx, y - cy
        u = dx * co + dy * si
        v = -dx * si + dy * co
        dn = np.sqrt((u / a) ** 2 + (v / b) ** 2)
        inside = dn < 1
        if not inside.any():
            return None
        half = b * np.sqrt(np.clip(1 - (u / a) ** 2, 0, 1))
        edge = -half + 2 * half * c                        # where the upper lid's rim is now
        lid = inside & (v < edge)

        # gaze: slide the eye's contents, fading out towards the rim
        w = 1 - smoothstep(0.5, 1.0, dn)
        gu, gv = nx * GAZE_U * a, ny * GAZE_V * b
        us, vs = u - gu * w, v - gv * w
        # pupil: radial zoom around the iris centre
        ix, iy, ir = e["iris"]
        iu = (ix - cx) * co + (iy - cy) * si
        iv = -(ix - cx) * si + (iy - cy) * co
        pu, pv = us - iu, vs - iv
        rho = np.sqrt(pu * pu + pv * pv)
        f = 1 + (1 / pupil - 1) * (1 - np.clip(rho / ir, 0, 1)) ** 2
        us, vs = iu + pu * f, iv + pv * f
        # lid: skin from above the eye, stretched down over the opening
        lid_v = -half - (edge - v) * 0.7 - 1.5
        us = np.where(lid, u, us)
        vs = np.where(lid, lid_v, vs)
        X[...] = np.where(inside, cx + us * co - vs * si, x)
        Y[...] = np.where(inside, cy + us * si + vs * co, y)
        if c < 0.08:
            return None
        rim = inside & (np.abs(v - edge) < 1.8)            # lashes along the moving lid
        return np.where(rim, 0.25, 1.0).astype(np.float32)

    def iris_cells(self, e, cells, nx, ny, c):
        """Which cells of an eye's window show the (moved) iris, for tinting."""
        cx, cy = e["center"]
        a, b = e["a"], e["b"]
        th = math.radians(e["angle"])
        co, si = math.cos(th), math.sin(th)
        gu, gv = nx * GAZE_U * a, ny * GAZE_V * b
        ix, iy, ir = e["iris"]
        mx, my = ix + gu * co - gv * si, iy + gu * si + gv * co
        CX, CY = self.CX[cells], self.CY[cells]
        dx, dy = CX - cx, CY - cy
        u = dx * co + dy * si
        v = -dx * si + dy * co
        half = b * np.sqrt(np.clip(1 - (u / a) ** 2, 0, 1))
        opened = ((u / a) ** 2 + (v / b) ** 2 < 0.9) & (v > -half + 2 * half * c + 1)
        return opened & ((CX - mx) ** 2 + (CY - my) ** 2 < (ir * 0.95) ** 2)

    def glow(self, ptr, glyphs, colors):
        """A soft light around the pointer: denser glyphs and brighter colours nearby."""
        sx, sy = self.to_src(*ptr)
        R = 0.2 * self.size
        cells = self.cell_rect(sx - R, sy - R, sx + R, sy + R)
        if cells[0].start >= cells[0].stop or cells[1].start >= cells[1].stop:
            return
        win = self.feat(cells)
        d2 = ((self.X0[win] - sx) ** 2 + (self.Y0[win] - sy) ** 2) / (R * R)
        g = np.clip(1 - d2, 0, 1) ** 2
        ink = self.I[win]
        ink = ink + (1 - ink) * 0.3 * g * self.vignette[win]
        glyphs[cells] = self.gs.glyphs(ink, self.dither[win])
        cg = np.clip(1 - ((self.CX[cells] - sx) ** 2 + (self.CY[cells] - sy) ** 2) / (R * R), 0, 1) ** 2
        lvl = np.digitize(cg, [0.12, 0.35, 0.65])          # 0..3
        sub = colors[cells]
        pick = (sub == 0) & (lvl > 0)
        sub[pick] = (1 + lvl[pick]).astype(np.uint8)

    @staticmethod
    def star_level(now, ph, per):
        s = math.sin(now * 2 * math.pi / per + ph)
        return 2 if s > 0.85 else 1 if s > 0.55 else 0

    def twinkle(self, levels, glyphs, colors):
        gi = self.gs.index
        for (r, c), lv in zip(self.star_cells, levels):
            if not lv:
                continue
            glyphs[r, c] = gi["*"] if lv == 2 else gi["+"]
            colors[r, c] = 5
            if lv == 2:                                     # little cross arms at full shine
                for cc in (c - 1, c + 1):
                    if 0 <= cc < self.cols:
                        glyphs[r, cc] = gi["-"]
                        colors[r, cc] = 5

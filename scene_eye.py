"""Scene 'eye': the single ASCII eye of the profile card (assets/eye.json), as before."""
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageTk

from behaviour import CARD_X, CARD_UP, CARD_DOWN, Follower

ROOT = Path(__file__).resolve().parent


def rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


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



class EyeScene:
    def __init__(self, cfg, colors, font, canvas):
        self.cfg, self.colors, self.font, self.canvas = cfg, colors, font, canvas
        self.eye = json.loads((ROOT / "assets" / "eye.json").read_text())
        self.light = cfg["theme"] == "light"
        self.follow = Follower()

    def layout(self, mon):
        e = self.eye
        aw, ah = e["cols"] * e["cell_w"], e["rows"] * e["cell_h"]
        S = min(self.cfg["size"] * mon["h"] / ah, 0.92 * mon["w"] / aw)
        self.art = EyeArt(e, S, self.colors, self.font)
        W, H = self.art.size
        px, py = self.cfg["position"]
        ox = round(min(max(mon["x"] + px * mon["w"] - W / 2, mon["x"]), mon["x"] + mon["w"] - W))
        oy = round(min(max(mon["y"] + py * mon["h"] - H / 2, mon["y"]), mon["y"] + mon["h"] - H))
        self.base_photo = ImageTk.PhotoImage(self.art.base)
        ux, uy = self.art.box[:2]
        self.dyn_photo = ImageTk.PhotoImage(self.art.base_u)
        self.canvas.create_image(ox, oy, image=self.base_photo, anchor="nw")
        self.canvas.create_image(ox + ux, oy + uy, image=self.dyn_photo, anchor="nw")
        self.focus = (ox + e["iris_center"][0] * S, oy + e["iris_center"][1] * S)
        self.last_key = None

    def click(self, x, y, now):
        pass

    def frame(self, now, dt, beh):
        tx, ty, squint = beh.target(self.focus, 0.0)
        nx, ny = self.follow.step((tx, ty), dt, beh.jit)
        gx, gy = nx * CARD_X, ny * (CARD_UP if ny < 0 else CARD_DOWN)
        lid = self.art.lid_frame(beh.lid(squint, ny, now))
        S = self.art.S
        key = (round(gx * S), round(gy * S), round(beh.pupil * 40), lid)
        if key != self.last_key:
            self.last_key = key
            self.dyn_photo.paste(self.art.compose(gx, gy, beh.pupil, lid, self.light))

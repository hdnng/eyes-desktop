"""Fast picture -> ASCII rendering with numpy.

Each character cell is split into 2x3 sub-cells. A cell's six ink values are quantised to a few
levels and looked up in a table that holds, for every combination, the glyph whose own 2x3
coverage (measured from the real font) matches best. Matching shape as well as density keeps
edges such as lash lines and hair strands readable.

Glyphs are drawn from a pre-rendered atlas, so turning a grid of glyph ids into pixels is one
numpy gather. Work is done per tile, and only for tiles whose glyphs or colours changed.
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont

GLYPHS = " .`',:;\"-_~^!|/\\()[]{}<>?=+*rcszvunxoaeLJTYVli17IkhbdpqXZOQ08&%#$BMW@"
SUB_X, SUB_Y = 2, 3          # sub-cells per character cell
LEVELS = 5                   # quantisation levels per sub-cell (5**6 = 15625 table entries)
BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) / 16


class GlyphSet:
    """A monospace font rendered at one cell size: glyph atlas plus the sub-cell lookup table."""

    def __init__(self, font_path, cw, ch):
        self.cw, self.ch = cw, ch
        font = ImageFont.truetype(font_path, max(4, round(cw / 0.602)))
        asc, desc = font.getmetrics()
        base = (ch - (asc + desc)) / 2 + asc
        tiles = []
        for g in GLYPHS:
            im = Image.new("L", (cw, ch), 0)
            if g != " ":
                adv = font.getlength(g)
                ImageDraw.Draw(im).text(((cw - adv) / 2, base), g, font=font, fill=255, anchor="ls")
            tiles.append(np.asarray(im, np.uint8))
        self.atlas = np.stack(tiles)                                    # (n, ch, cw)

        # 2x3 coverage of every glyph, scaled so the densest glyph is about 1
        a = self.atlas.astype(np.float32) / 255
        ys = np.linspace(0, ch, SUB_Y + 1).round().astype(int)
        xs = np.linspace(0, cw, SUB_X + 1).round().astype(int)
        feat = np.stack([a[:, ys[j]:ys[j + 1], xs[i]:xs[i + 1]].mean(axis=(1, 2))
                         for j in range(SUB_Y) for i in range(SUB_X)], axis=1)      # (n, 6)
        feat /= max(feat.mean(axis=1).max(), 1e-6)

        # lookup table: every quantised 6-vector -> best glyph (shape and overall density)
        n = SUB_X * SUB_Y
        q = np.indices((LEVELS,) * n).reshape(n, -1).T[:, ::-1].astype(np.float32) / (LEVELS - 1)
        # density decides first; shape (the centred pattern) picks among glyphs of similar density
        qm, fm = q.mean(1, keepdims=True), feat.mean(1, keepdims=True)
        d = (((q - qm)[:, None, :] - (feat - fm)[None, :, :]) ** 2).sum(-1)
        d += 8.0 * n * (qm - fm.T) ** 2
        self.lut = d.argmin(1).astype(np.int16)
        self.weights = (LEVELS ** np.arange(n)).astype(np.int32)
        self.index = {g: i for i, g in enumerate(GLYPHS)}

    def glyphs(self, ink, dither):
        """ink: (rows*3, cols*2) array in 0..1 -> (rows, cols) glyph ids."""
        q = np.clip((ink * (LEVELS - 1) + dither).astype(np.int32), 0, LEVELS - 1)
        r, c = ink.shape[0] // SUB_Y, ink.shape[1] // SUB_X
        q = q.reshape(r, SUB_Y, c, SUB_X).transpose(0, 2, 1, 3).reshape(r, c, SUB_X * SUB_Y)
        return self.lut[q @ self.weights]


def dither_for(shape):
    """Static ordered dither (no flicker between frames), in quantisation-step units."""
    h, w = shape
    return np.tile(BAYER4, (h // 4 + 1, w // 4 + 1))[:h, :w]


class TiledCanvas:
    """A glyph grid shown on a Tk canvas as a mosaic of PhotoImages; only changed tiles repaint."""

    def __init__(self, canvas, gs, rows, cols, x0, y0, bg, palette, tile=(6, 12)):
        from PIL import ImageTk
        self.ImageTk = ImageTk
        self.canvas, self.gs = canvas, gs
        self.rows, self.cols, self.tr, self.tc = rows, cols, tile[0], tile[1]
        self.bg = np.array(bg, np.float32)
        self.set_palette(palette)
        self.prev = None
        self.photos = {}
        for ty in range(0, rows, self.tr):
            for tx in range(0, cols, self.tc):
                h = min(self.tr, rows - ty) * gs.ch
                w = min(self.tc, cols - tx) * gs.cw
                ph = ImageTk.PhotoImage(Image.new("RGB", (w, h), tuple(int(v) for v in bg)))
                canvas.create_image(x0 + tx * gs.cw, y0 + ty * gs.ch, image=ph, anchor="nw")
                self.photos[(ty, tx)] = ph

    def set_palette(self, palette):
        """palette: (k, 3) colours; a cell's colour id picks one. Pre-colours the whole atlas:
        catlas[colour, glyph] is a finished (ch, cw, 3) tile, so painting is a single gather."""
        pal = np.asarray(palette, np.float32)
        a = self.gs.atlas.astype(np.float32)[None, :, :, :, None] / 255          # (1, n, ch, cw, 1)
        bg = self.bg[None, None, None, None, :]
        self.catlas = (bg + a * (pal[:, None, None, None, :] - bg)).round().astype(np.uint8)
        self.prev = None                                              # force a full repaint

    def show(self, glyphs, colors):
        """Repaint the tiles whose glyphs or colour ids changed. Returns how many repainted."""
        gs = self.gs
        if self.prev is None:
            changed = np.ones(glyphs.shape, bool)
        else:
            changed = (glyphs != self.prev[0]) | (colors != self.prev[1])
        self.prev = (glyphs.copy(), colors.copy())
        # which tiles hold a change: one reduction instead of a check per tile
        R = -(-self.rows // self.tr) * self.tr
        C = -(-self.cols // self.tc) * self.tc
        pad = np.zeros((R, C), bool)
        pad[:self.rows, :self.cols] = changed
        hot = pad.reshape(R // self.tr, self.tr, C // self.tc, self.tc).any(axis=(1, 3))
        n = 0
        for i, j in zip(*np.nonzero(hot)):
            ty, tx = int(i) * self.tr, int(j) * self.tc
            ph = self.photos[(ty, tx)]
            g = glyphs[ty:ty + self.tr, tx:tx + self.tc]
            c = colors[ty:ty + self.tr, tx:tx + self.tc]
            r, k = g.shape
            px = self.catlas[c, g].transpose(0, 2, 1, 3, 4).reshape(r * gs.ch, k * gs.cw, 3)
            ph.paste(Image.fromarray(px))
            n += 1
        return n

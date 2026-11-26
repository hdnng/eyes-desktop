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


class XImageCanvas:
    """Draws the glyph grid straight onto a Tk widget's X window with libX11's XPutImage.

    The whole frame lives in one numpy buffer that an XImage points at; each frame only the
    changed rectangles are sent, runs of neighbouring changed tiles merged into one request.
    Much cheaper than Tk photo images. Raises on init if libX11 or a 24-bit TrueColor visual is
    not available; callers fall back to TiledCanvas then."""

    def __init__(self, widget, gs, rows, cols, x0, y0, bg, palette, tile=(3, 8)):
        import ctypes
        import ctypes.util
        self.ct = ctypes
        lib = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
        P, I, U = ctypes.c_void_p, ctypes.c_int, ctypes.c_uint
        lib.XOpenDisplay.restype = P
        lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        lib.XDefaultScreen.argtypes = [P]
        lib.XDefaultVisual.restype = P
        lib.XDefaultVisual.argtypes = [P, I]
        lib.XDefaultDepth.argtypes = [P, I]
        lib.XCreateGC.restype = P
        lib.XCreateGC.argtypes = [P, ctypes.c_ulong, ctypes.c_ulong, P]
        lib.XCreateImage.restype = ctypes.POINTER(_XImage)
        lib.XCreateImage.argtypes = [P, P, U, I, I, P, U, U, I, I]
        lib.XPutImage.argtypes = [P, ctypes.c_ulong, P, ctypes.POINTER(_XImage), I, I, I, I, U, U]
        lib.XFlush.argtypes = [P]
        lib.XFreeGC.argtypes = [P, P]
        lib.XCloseDisplay.argtypes = [P]
        self.lib = lib
        self.dpy = lib.XOpenDisplay(None)
        if not self.dpy:
            raise RuntimeError("cannot open X display")
        scr = lib.XDefaultScreen(self.dpy)
        if lib.XDefaultDepth(self.dpy, scr) != 24:
            raise RuntimeError("needs a 24-bit display")
        widget.update_idletasks()
        self.win = widget.winfo_id()
        self.gc = lib.XCreateGC(self.dpy, self.win, 0, None)
        self.gs, self.rows, self.cols, self.tr, self.tc = gs, rows, cols, tile[0], tile[1]
        self.x0, self.y0 = x0, y0
        self.H, self.W = rows * gs.ch, cols * gs.cw
        self.bg = np.array(bg, np.float32)
        self.buf = np.empty((self.H, self.W, 4), np.uint8)
        self.buf[...] = (bg[2], bg[1], bg[0], 0)
        self.img = lib.XCreateImage(self.dpy, lib.XDefaultVisual(self.dpy, scr), 24, 2, 0,
                                    self.buf.ctypes.data, self.W, self.H, 32, self.W * 4)
        im = self.img.contents
        if not (im.bits_per_pixel == 32 and im.byte_order == 0 and im.red_mask == 0xFF0000
                and im.green_mask == 0xFF00 and im.blue_mask == 0xFF):
            self.close()
            raise RuntimeError("unsupported pixel format")
        self.set_palette(palette)
        # Tk clears exposed areas to the background in its idle redraw; repaint after it
        self.widget = widget
        widget.bind("<Expose>", lambda e: self.later_expose())
        widget.bind("<Map>", lambda e: self.later_expose())

    def set_palette(self, palette):
        pal = np.asarray(palette, np.float32)[:, ::-1]                  # RGB -> BGR
        a = self.gs.atlas.astype(np.float32)[None, :, :, :, None] / 255
        bg = self.bg[::-1][None, None, None, None, :]
        bgr = (bg + a * (pal[:, None, None, None, :] - bg)).round().astype(np.uint8)
        self.catlas = np.concatenate([bgr, np.zeros(bgr.shape[:-1] + (1,), np.uint8)], axis=-1)
        self.prev = None

    def later_expose(self):
        self.widget.after_idle(self.expose)
        self.widget.after(60, self.expose)

    def expose(self):
        """Tk repainted the window background: send the whole frame again."""
        if self.dpy and self.img:
            self.put(0, 0, self.W, self.H)
            self.lib.XFlush(self.dpy)

    def put(self, x, y, w, h):
        self.lib.XPutImage(self.dpy, self.win, self.gc, self.img, x, y, self.x0 + x, self.y0 + y, w, h)

    def show(self, glyphs, colors):
        gs = self.gs
        if self.prev is None:
            changed = np.ones(glyphs.shape, bool)
        else:
            changed = (glyphs != self.prev[0]) | (colors != self.prev[1])
        self.prev = (glyphs.copy(), colors.copy())
        R = -(-self.rows // self.tr) * self.tr
        C = -(-self.cols // self.tc) * self.tc
        pad = np.zeros((R, C), bool)
        pad[:self.rows, :self.cols] = changed
        hot = pad.reshape(R // self.tr, self.tr, C // self.tc, self.tc).any(axis=(1, 3))
        n = 0
        for i in np.nonzero(hot.any(1))[0]:
            row = hot[i]
            # runs of neighbouring changed tiles in this tile row
            edges = np.diff(np.concatenate([[0], row.view(np.int8), [0]]))
            for a, b in zip(np.nonzero(edges == 1)[0], np.nonzero(edges == -1)[0]):
                r0, r1 = i * self.tr, min(self.rows, (i + 1) * self.tr)
                c0, c1 = a * self.tc, min(self.cols, b * self.tc)
                g, c = glyphs[r0:r1, c0:c1], colors[r0:r1, c0:c1]
                px = self.catlas[c, g].transpose(0, 2, 1, 3, 4).reshape((r1 - r0) * gs.ch, (c1 - c0) * gs.cw, 4)
                y, x = r0 * gs.ch, c0 * gs.cw
                self.buf[y:y + px.shape[0], x:x + px.shape[1]] = px
                self.put(x, y, px.shape[1], px.shape[0])
                n += 1
        if n:
            self.lib.XFlush(self.dpy)
        return n

    def close(self):
        if getattr(self, "img", None):
            self.img.contents.data = None        # the pixels belong to numpy, not to Xlib
            self.img = None
        if getattr(self, "gc", None):
            self.lib.XFreeGC(self.dpy, self.gc)
            self.gc = None
        if getattr(self, "dpy", None):
            self.lib.XCloseDisplay(self.dpy)
            self.dpy = None


def _ximage_struct():
    import ctypes
    I, UL = ctypes.c_int, ctypes.c_ulong

    class XImage(ctypes.Structure):
        _fields_ = [("width", I), ("height", I), ("xoffset", I), ("format", I),
                    ("data", ctypes.c_void_p), ("byte_order", I), ("bitmap_unit", I),
                    ("bitmap_bit_order", I), ("bitmap_pad", I), ("depth", I),
                    ("bytes_per_line", I), ("bits_per_pixel", I),
                    ("red_mask", UL), ("green_mask", UL), ("blue_mask", UL)]
    return XImage


_XImage = _ximage_struct()


def make_canvas(widget, *args, **kw):
    """The fastest glyph canvas this display supports."""
    import os
    if widget is None:
        return BufferCanvas(widget, *args, **kw)
    if os.environ.get("EYES_RENDERER") != "tk":
        try:
            return XImageCanvas(widget, *args, **kw)
        except Exception as exc:                                       # pragma: no cover
            print(f"note: direct X drawing unavailable ({exc}); using Tk images", flush=True)
    return TiledCanvas(widget, *args, **kw)


class BufferCanvas:
    """No window at all: keeps the rendered frame in memory (for still snapshots)."""

    def __init__(self, widget, gs, rows, cols, x0, y0, bg, palette, tile=None):
        self.gs, self.rows, self.cols, self.x0, self.y0 = gs, rows, cols, x0, y0
        self.bg = np.array(bg, np.float32)
        self.set_palette(palette)

    def set_palette(self, palette):
        pal = np.asarray(palette, np.float32)
        a = self.gs.atlas.astype(np.float32)[None, :, :, :, None] / 255
        bg = self.bg[None, None, None, None, :]
        self.catlas = (bg + a * (pal[:, None, None, None, :] - bg)).round().astype(np.uint8)

    def show(self, glyphs, colors):
        gs = self.gs
        px = self.catlas[colors, glyphs].transpose(0, 2, 1, 3, 4)
        self.image = Image.fromarray(px.reshape(self.rows * gs.ch, self.cols * gs.cw, 3))
        return 1

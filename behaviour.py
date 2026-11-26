"""Where the eyes look, how wide the pupils are and when the lids blink.

Shared by both scenes. Gaze is normalised: (-1..1, -1..1) along an eye's own axes, x towards
the outer corner on screen-right, y down. While the pointer rests, the profile card's own
routine (from hdnng/hdnng scripts/build_card.py) takes over.
"""
import math
import random

EYE_T = 14.0
# (time, dx, dy, squint 0-1, move seconds or None for a quick saccade); dx/dy in the card's art px
GLANCES = [(0.0, 0, 0, 0, None), (1.4, 34, -2, 0.18, None), (2.8, 33, -6, 0.22, None),
           (3.15, 33, -2, 0.22, None), (3.5, 33, 2, 0.25, None), (3.85, 33, 6, 0.28, None),
           (4.6, 0, 0, 0, None), (6.0, -30, -9, 0, None), (7.3, -26, 8, 0.1, None),
           (8.5, 31, 0, 0, None), (8.85, 0, 0, 0, None), (11.2, 10, -3, 0, 0.9),
           (12.3, -8, 2, 0, 0.9), (13.3, 0, 0, 0, 0.7)]
IDLE_BLINKS = [4.5, 9.9, 10.26]
PUPIL = [(0, 1.0), (5.9, 1.0), (6.5, 1.2), (7.3, 1.2), (7.9, 1.0), (8.4, 1.0), (8.7, 0.8),
         (10.8, 0.8), (11.8, 1.0)]
CARD_X, CARD_UP, CARD_DOWN = 34.0, 9.0, 8.0     # the card's largest glance, in its art px


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
    return x / CARD_X, y / (CARD_UP if y < 0 else CARD_DOWN), q


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


class Behaviour:
    def __init__(self, idle_after, now):
        self.idle_after = idle_after
        self.ptr, self.last_move, self.idle_start = None, -1e9, now
        self.moved = False
        self.on_desktop = True          # pointer over the wallpaper itself (not an app window)
        self.idle, self.t = True, 0.0
        self.routine = (0.0, 0.0, 0.0)
        self.blinks, self.last_blink = [], now
        self.next_blink = now + random.uniform(2.5, 6.0)
        self.pupil, self.prev_main = 1.0, (0.0, 0.0)
        self.jit, self.jit_target, self.next_jit = [0.0, 0.0], [0.0, 0.0], now
        self.screen = (1920, 1080)

    def blink(self, now):
        self.blinks.append(now)
        self.last_blink = now
        if random.random() < 0.15:                 # sometimes a double blink
            self.blinks.append(now + 0.36)

    def update(self, now, dt, ptr, screen, focus):
        """ptr: pointer in scene coordinates (or None); screen: (w, h) of the monitor;
        focus: the scene point that stands for 'the face', used for pupils and jump blinks."""
        self.screen = screen
        self.moved = ptr is not None and self.ptr is not None and ptr != self.ptr
        if self.moved:
            self.last_move = now
        if ptr is not None:
            self.ptr = ptr
        self.idle = now - self.last_move > self.idle_after
        if not self.idle:
            self.idle_start = now

        if self.idle:
            self.t = (now - self.idle_start) % EYE_T
            self.routine = glance_at(self.t)
            pupil_target = pupil_at(self.t)
            for b in IDLE_BLINKS:
                if abs(self.t - b) < dt / 2 + 1e-3 and now - self.last_blink > 0.3:
                    self.blink(now)
        else:
            pupil_target = 0.8 + 0.4 * min(self.nearness(focus), 1.0)   # close: narrow, far: wide

        main = self.target(focus, 0.0)[:2]
        if math.hypot(main[0] - self.prev_main[0], main[1] - self.prev_main[1]) > 0.75 \
                and now - self.last_blink > 1.5:   # big jumps come with a blink, like real eyes
            self.blink(now)
        self.prev_main = main
        if now >= self.next_blink:
            self.blink(now)
            self.next_blink = now + random.uniform(2.5, 6.5)
        self.blinks = [b for b in self.blinks if now - b < 0.4]

        if now >= self.next_jit:                    # tiny fixational jitter, never frozen
            self.jit_target = [random.uniform(-0.04, 0.04), random.uniform(-0.1, 0.1)]
            self.next_jit = now + random.uniform(0.35, 0.6)
        kj = 1 - math.exp(-dt * 50)
        self.jit = [j + (t - j) * kj for j, t in zip(self.jit, self.jit_target)]
        self.pupil += (pupil_target - self.pupil) * (1 - math.exp(-dt * 3))

    def nearness(self, point):
        """Pointer distance from a point, as a fraction of half the screen (0 = on it)."""
        if self.ptr is None:
            return 1.0
        w, h = self.screen
        return math.hypot((self.ptr[0] - point[0]) / (0.5 * w), (self.ptr[1] - point[1]) / (0.5 * h))

    def target(self, center, angle):
        """Gaze target (nx, ny, squint) for an eye at `center` whose long axis is tilted by
        `angle` radians."""
        if self.idle or self.ptr is None:
            return self.routine
        w, h = self.screen
        vx, vy = self.ptr[0] - center[0], self.ptr[1] - center[1]
        u = vx * math.cos(angle) + vy * math.sin(angle)
        v = -vx * math.sin(angle) + vy * math.cos(angle)
        nx, ny = math.tanh(1.8 * u / (0.5 * w)), math.tanh(1.8 * v / (0.5 * h))
        k = math.hypot(nx, ny)
        if k > 1:
            nx, ny = nx / k, ny / k
        squint = 0.3 * max(0.0, 1 - self.nearness(center) / 0.18)   # pointer right on it: squint
        return nx, ny, squint

    def lid(self, squint, ny, now):
        """Upper lid closure 0 (open) .. 1 (shut): squint, a downward look, blinks."""
        c = 0.9 * squint + 0.12 * max(ny, 0.0)
        for b in self.blinks:
            c += (1 - c) * blink_amount(now - b)
        return min(c, 1.0)


class Follower:
    """One eye's smoothed gaze: quick, saccade-like steps towards the target, plus jitter."""

    def __init__(self):
        self.x = self.y = 0.0

    def step(self, target, dt, jitter):
        k = 1 - math.exp(-dt * 18)
        self.x += (target[0] - self.x) * k
        self.y += (target[1] - self.y) * k
        return self.x + jitter[0], self.y + jitter[1]

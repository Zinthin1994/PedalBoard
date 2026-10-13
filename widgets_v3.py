"""PedalBoard v3 visuals.

Tk's canvas can't anti-alias, so every shape here is rendered with PIL at 3x and
scaled down, then placed on a canvas as an image. Widgets are canvas items (not
child windows), so enclosures, shadows and cables composite cleanly on the board.
Each widget exposes the same small interface the v2 app logic uses
(set_value / value / on / show / push / configure ...).
"""
import math
import tkinter as tk
import tkinter.font as tkfont

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageTk

SS = 3                      # supersampling factor
LZ = Image.LANCZOS

BG = "#141417"
TEXT = "#ececf0"
DIM = "#8b8b96"
GOLD = "#e0b44c"
TITLE_FONT = ("Bahnschrift SemiBold", 15)
LOGO_FONT = ("Bahnschrift SemiBold", 22)
LABEL_FONT = ("Bahnschrift SemiBold", 8)
VALUE_FONT = ("Bahnschrift", 8)
SMALL_FONT = ("Segoe UI", 7)

_cache = {}


# --------------------------------------------------------------------------- colour helpers

def rgb(c):
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def hexc(t):
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, v))) for v in t[:3])


def mix(a, b, t):
    ra, rb = rgb(a), rgb(b)
    return hexc([ra[i] + (rb[i] - ra[i]) * t for i in range(3)])


def shade(c, f):
    """f < 1 darkens, f > 1 lightens towards white."""
    return mix(c, "#000000", 1 - f) if f <= 1 else mix(c, "#ffffff", f - 1)


def lum(c):
    r, g, b = rgb(c)
    return 0.299 * r + 0.587 * g + 0.114 * b


def is_light(c):
    return lum(c) > 140


# --------------------------------------------------------------------------- render helpers

def _vgrad(w, h, top, bot):
    a = np.array(rgb(top), dtype=np.float32)
    b = np.array(rgb(bot), dtype=np.float32)
    t = np.linspace(0, 1, max(h, 1), dtype=np.float32)[:, None, None]
    arr = np.broadcast_to(a + (b - a) * t, (h, w, 3)).astype(np.uint8)
    return Image.fromarray(np.ascontiguousarray(arr), "RGB")


def _layer(size, color, alpha_mask):
    lay = Image.new("RGBA", size, color)
    lay.putalpha(alpha_mask)
    return lay


def _ellipse_mask(size, box):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).ellipse(box, fill=255)
    return m


def _photo(key, render):
    p = _cache.get(key)
    if p is None:
        p = ImageTk.PhotoImage(render())
        _cache[key] = p
    return p


def _noise(img, amount, seed=0):
    arr = np.asarray(img).astype(np.int16)
    n = np.random.default_rng(seed).normal(0, amount, arr.shape[:2] + (1,))
    arr[..., :3] = np.clip(arr[..., :3] + n, 0, 255)
    return Image.fromarray(arr.astype(np.uint8), img.mode)


def _screw(r=4.5):
    s = int(r * 2 + 4) * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    c, R = s / 2, r * SS
    body = _vgrad(s, s, "#d9d9e0", "#55555d").convert("RGBA")
    body.putalpha(_ellipse_mask((s, s), [c - R, c - R, c + R, c + R]))
    img.alpha_composite(body)
    d = ImageDraw.Draw(img)
    d.ellipse([c - R, c - R, c + R, c + R], outline=(30, 30, 34, 255), width=SS)
    d.line([(c - R * 0.6, c + R * 0.35), (c + R * 0.6, c - R * 0.35)], fill=(40, 40, 46, 255), width=int(1.4 * SS))
    return img.resize((s // SS, s // SS), LZ)


def enclosure_image(w, h, color, pad=14, jack_y=46, seed=0):
    """Powder-coated pedal: drop shadow, side jacks, gradient body, bevel, corner screws."""
    W, H = w + 2 * pad, h + 2 * pad
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh = Image.new("L", (W, H), 0)
    ImageDraw.Draw(sh).rounded_rectangle([pad + 2, pad + 6, pad + w - 2, pad + h + 6], 14, fill=200)
    out.alpha_composite(_layer((W, H), (0, 0, 0, 255), sh.filter(ImageFilter.GaussianBlur(8))))

    # jacks poking out of both sides
    jk = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(jk)
    for x0 in (pad - 10, pad + w - 4):
        y0 = pad + jack_y - 8
        d.rounded_rectangle([x0 * SS, y0 * SS, (x0 + 14) * SS, (y0 + 16) * SS], 3 * SS,
                            fill=(150, 150, 158, 255), outline=(40, 40, 44, 255), width=SS)
        d.rectangle([x0 * SS, (y0 + 3) * SS, (x0 + 14) * SS, (y0 + 5) * SS], fill=(215, 215, 222, 255))
    out.alpha_composite(jk.resize((W, H), LZ))

    body = _noise(_vgrad(w, h, shade(color, 1.16), shade(color, 0.72)).convert("RGBA"), 2.2, seed)
    body.putalpha(_rr_mask(w, h, 14))
    bev = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bev)
    bd.rounded_rectangle([SS, SS, w * SS - SS - 1, h * SS - SS - 1], 13 * SS, outline=(255, 255, 255, 80), width=2 * SS)
    ramp = Image.fromarray((np.linspace(255, 0, h * SS)[:, None] * np.ones((1, w * SS))).astype(np.uint8), "L")
    bev.putalpha(Image.fromarray(np.minimum(np.asarray(bev.getchannel("A")), np.asarray(ramp))))
    bd2 = ImageDraw.Draw(bev)
    bd2.rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], 14 * SS, outline=(0, 0, 0, 150), width=SS)
    body.alpha_composite(bev.resize((w, h), LZ))
    scr = _screw()
    o = scr.size[0] // 2
    for sx, sy in ((11, 11), (w - 11, 11), (11, h - 11), (w - 11, h - 11)):
        body.alpha_composite(scr, (sx - o, sy - o))
    out.alpha_composite(body, (pad, pad))
    return out


def _rr_mask(w, h, r):
    m = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], r * SS, fill=255)
    return m.resize((w, h), LZ)


def panel_image(w, h, top="#2c2f36", bot="#1b1d22", screws=True):
    """Rack-style side panel."""
    img = _noise(_vgrad(w, h, top, bot).convert("RGBA"), 2.0, 7)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w - 1, h - 1], outline=(0, 0, 0, 255))
    d.line([(1, 1), (w - 2, 1)], fill=(255, 255, 255, 40))
    if screws:
        s = _screw(4)
        o = s.size[0] // 2
        for sx, sy in ((10, 10), (w - 10, 10), (10, h - 10), (w - 10, h - 10)):
            img.alpha_composite(s, (sx - o, sy - o))
    return img


def board_tile():
    def render():
        t = Image.new("RGB", (256, 256), rgb("#18181c"))
        t = _noise(t, 6.0, 3).filter(ImageFilter.GaussianBlur(0.7))
        return _noise(t, 2.0, 4)
    k = ("tile",)
    if k not in _cache:
        _cache[k] = render()
    return _cache[k]


def _bezier(p0, p1, p2, p3, n=48):
    pts = []
    for i in range(n + 1):
        t = i / n
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
        pts.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return pts


def draw_cable(bg, p0, p1, p2, p3, color=(14, 14, 16)):
    """Anti-aliased patch cable with plugs, composited into bg (RGB) in place."""
    pts = _bezier(p0, p1, p2, p3)
    xs = [p[0] for p in pts] + [p0[0], p3[0]]
    ys = [p[1] for p in pts]
    x0, y0 = int(min(xs)) - 24, int(min(ys)) - 14
    x1, y1 = int(max(xs)) + 24, int(max(ys)) + 14
    w, h = x1 - x0, y1 - y0
    lay = Image.new("RGBA", (w * 2, h * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    sp = [((x - x0) * 2, (y - y0 + 4) * 2) for x, y in pts]
    d.line(sp, fill=(0, 0, 0, 110), width=16, joint="curve")              # shadow
    p = [((x - x0) * 2, (y - y0) * 2) for x, y in pts]
    d.line(p, fill=color + (255,), width=12, joint="curve")
    d.line([(x - 2, y - 3) for x, y in p], fill=(80, 80, 90, 150), width=3, joint="curve")
    for (px, py), dirn in ((p0, 1), (p3, -1)):                          # plugs
        cx, cy = (px - x0) * 2, (py - y0) * 2
        a, b = cx + dirn * 6, cx + dirn * 34
        d.rounded_rectangle([min(a, b), cy - 9, max(a, b), cy + 9], 6, fill=(25, 25, 28, 255))
        a, b = cx, cx + dirn * 14
        d.rounded_rectangle([min(a, b), cy - 7, max(a, b), cy + 7], 3, fill=(185, 185, 192, 255))
        d.line([(min(a, b), cy - 4), (max(a, b), cy - 4)], fill=(240, 240, 245, 255), width=2)
    lay = lay.resize((w, h), LZ)
    region = bg.crop((x0, y0, x1, y1)).convert("RGBA")
    region.alpha_composite(lay)
    bg.paste(region.convert("RGB"), (x0, y0))


# --------------------------------------------------------------------------- sprites

def knob_photo(size, n, accent, track=(0, 0, 0, 120)):
    q = int(round(max(0.0, min(1.0, n)) * 100))
    return _photo(("knob", size, q, accent, track), lambda: _render_knob(size, q / 100.0, accent, track))


def _knob_base(size):
    key = ("knobbase", size)
    if key in _cache:
        return _cache[key]
    S = (size + 22) * SS
    c, r = S / 2, size / 2 * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sh = _ellipse_mask((S, S), [c - r, c - r + 3 * SS, c + r, c + r + 4 * SS]).filter(ImageFilter.GaussianBlur(3 * SS))
    img.alpha_composite(_layer((S, S), (0, 0, 0, 200), sh))
    skirt = _vgrad(S, S, "#4a4a53", "#0e0e11").convert("RGBA")
    skirt.putalpha(_ellipse_mask((S, S), [c - r, c - r, c + r, c + r]))
    img.alpha_composite(skirt)
    d = ImageDraw.Draw(img)
    for k in range(36):
        a = 2 * math.pi * k / 36
        d.line([(c + math.cos(a) * r * 0.80, c + math.sin(a) * r * 0.80),
                (c + math.cos(a) * r * 0.97, c + math.sin(a) * r * 0.97)], fill=(95, 95, 106, 255), width=SS)
    rc = r * 0.68
    cap = _vgrad(S, S, "#75757f", "#1d1d21").convert("RGBA")
    cap.putalpha(_ellipse_mask((S, S), [c - rc, c - rc, c + rc, c + rc]))
    img.alpha_composite(cap)
    hl = _ellipse_mask((S, S), [c - rc * 0.75, c - rc * 0.9, c + rc * 0.35, c - rc * 0.1]).filter(
        ImageFilter.GaussianBlur(2 * SS))
    img.alpha_composite(_layer((S, S), (255, 255, 255, 70), hl))
    d = ImageDraw.Draw(img)
    d.ellipse([c - r, c - r, c + r, c + r], outline=(0, 0, 0, 220), width=SS)
    d.ellipse([c - rc, c - rc, c + rc, c + rc], outline=(0, 0, 0, 160), width=SS)
    _cache[key] = img
    return img


def _render_knob(size, n, accent, track):
    img = _knob_base(size).copy()
    S = img.size[0]
    c, r = S / 2, size / 2 * SS
    R = r + 7 * SS
    box = [c - R, c - R, c + R, c + R]
    d = ImageDraw.Draw(img)
    d.arc(box, 135, 405, fill=track, width=3 * SS)
    if n > 0.005:
        end = 135 + 270 * n
        if lum(accent) > 60:
            glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
            ImageDraw.Draw(glow).arc(box, 135, end, fill=rgb(accent) + (170,), width=7 * SS)
            img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(2.5 * SS)))
            d = ImageDraw.Draw(img)
        d.arc(box, 135, end, fill=rgb(shade(accent, 1.15)) + (255,), width=3 * SS)
    th = math.radians(135 + 270 * n)
    ct, st = math.cos(th), math.sin(th)
    a, b = r * 0.22, r * 0.9
    wdt = max(2, int(r * 0.12))
    d.line([(c + ct * a, c + st * a), (c + ct * b, c + st * b)], fill=(250, 250, 252, 255), width=wdt)
    for rr in (a, b):
        d.ellipse([c + ct * rr - wdt / 2, c + st * rr - wdt / 2, c + ct * rr + wdt / 2, c + st * rr + wdt / 2],
                  fill=(250, 250, 252, 255))
    return img.resize((S // SS, S // SS), LZ)


def footswitch_photo(size=56, pressed=False):
    return _photo(("fs", size, pressed), lambda: _render_footswitch(size, pressed))


def _render_footswitch(size, pressed):
    S = (size + 8) * SS
    c = S / 2
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    R = size * 0.46 * SS
    off = (2 if pressed else 4) * SS
    sh = _ellipse_mask((S, S), [c - R, c - R + off, c + R, c + R + off]).filter(ImageFilter.GaussianBlur(3 * SS))
    img.alpha_composite(_layer((S, S), (0, 0, 0, 210), sh))
    hexm = Image.new("L", (S, S), 0)
    ImageDraw.Draw(hexm).polygon([(c + R * math.cos(math.pi / 6 + k * math.pi / 3),
                                   c + R * math.sin(math.pi / 6 + k * math.pi / 3)) for k in range(6)], fill=255)
    nut = _vgrad(S, S, "#c4c4cc", "#4c4c54").convert("RGBA")
    nut.putalpha(hexm)
    img.alpha_composite(nut)
    rd = size * 0.31 * SS
    dome = _vgrad(S, S, "#d8d8de" if pressed else "#fafafd", "#5c5c66" if pressed else "#70707a").convert("RGBA")
    dome.putalpha(_ellipse_mask((S, S), [c - rd, c - rd, c + rd, c + rd]))
    img.alpha_composite(dome)
    hl = _ellipse_mask((S, S), [c - rd * 0.6, c - rd * 0.85, c + rd * 0.35, c - rd * 0.15]).filter(
        ImageFilter.GaussianBlur(2 * SS))
    img.alpha_composite(_layer((S, S), (255, 255, 255, 140), hl))
    d = ImageDraw.Draw(img)
    d.ellipse([c - rd, c - rd, c + rd, c + rd], outline=(40, 40, 46, 255), width=SS)
    return img.resize((S // SS, S // SS), LZ)


def led_photo(color, on, size=24):
    return _photo(("led", color, on, size), lambda: _render_led(color, on, size))


def _render_led(color, on, size):
    S = size * SS
    c = S / 2
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    r = S * 0.2
    if on:
        g = _ellipse_mask((S, S), [c - r * 2.2, c - r * 2.2, c + r * 2.2, c + r * 2.2]).filter(
            ImageFilter.GaussianBlur(S * 0.12))
        img.alpha_composite(_layer((S, S), rgb(color) + (200,), g))
    d = ImageDraw.Draw(img)
    d.ellipse([c - r - SS, c - r - SS, c + r + SS, c + r + SS], fill=(20, 20, 22, 255))
    core = shade(color, 1.35) if on else shade(color, 0.3)
    d.ellipse([c - r, c - r, c + r, c + r], fill=rgb(core) + (255,))
    d.ellipse([c - r * 0.55, c - r * 0.7, c - r * 0.05, c - r * 0.25], fill=(255, 255, 255, 170 if on else 70))
    return img.resize((size, size), LZ)


def pill_photo(w, h, fill, outline=None):
    return _photo(("pill", w, h, fill, outline), lambda: _render_pill(w, h, fill, outline))


def _render_pill(w, h, fill, outline):
    W, H = w * SS, h * SS
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    base = _vgrad(W, H, shade(fill, 1.12), shade(fill, 0.9)).convert("RGBA")
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, W - 1, H - 1], H // 2, fill=255)
    base.putalpha(m)
    img.alpha_composite(base)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, W - 1, H - 1], H // 2, outline=rgb(outline or shade(fill, 0.6)) + (255,), width=SS)
    return img.resize((w, h), LZ)


def treadle_photo(w, h, pos):
    q = int(round(max(0.0, min(1.0, pos)) * 60))
    return _photo(("treadle", w, h, q), lambda: _render_treadle(w, h, q / 60.0))


def _render_treadle(w, h, pos):
    W, H = w * SS, h * SS
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    by = H - 30 * SS                           # base
    base = _vgrad(W, 18 * SS, "#3a3a40", "#121214").convert("RGBA")
    m = Image.new("L", base.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([8 * SS, 0, W - 8 * SS, 18 * SS - 1], 6 * SS, fill=255)
    base.putalpha(m)
    img.alpha_composite(base, (0, by))
    cx, cy = W / 2, by - 6 * SS
    d.polygon([(cx - 12 * SS, by + 2 * SS), (cx + 12 * SS, by + 2 * SS), (cx, cy)], fill=(70, 70, 78, 255))
    L, T = W - 26 * SS, 22 * SS                # treadle plate
    plate = _vgrad(L, T, "#4b4b54", "#18181c").convert("RGBA")
    pm = Image.new("L", (L, T), 0)
    ImageDraw.Draw(pm).rounded_rectangle([0, 0, L - 1, T - 1], 7 * SS, fill=255)
    pd = ImageDraw.Draw(plate)
    for x in range(14 * SS, L - 10 * SS, 9 * SS):      # rubber ribs
        pd.rectangle([x, 3 * SS, x + 4 * SS, 8 * SS], fill=(20, 20, 23))
    pd.line([(6 * SS, SS), (L - 6 * SS, SS)], fill=(200, 200, 210), width=SS)
    plate.putalpha(pm)
    ang = -(pos - 0.5) * 26
    rot = plate.rotate(ang, resample=Image.BICUBIC, expand=True)
    sh = Image.new("L", rot.size, 0)
    sh.paste(rot.getchannel("A"))
    sh = sh.filter(ImageFilter.GaussianBlur(4 * SS))
    shadow = _layer(rot.size, (0, 0, 0, 160), sh)
    px, py = int(cx - rot.size[0] / 2), int(cy - rot.size[1] / 2 - 4 * SS)
    img.alpha_composite(shadow, (px, py + 6 * SS))
    img.alpha_composite(rot, (px, py))
    return img.resize((w, h), LZ)


def tuner_image(w, h, cents, color, active):
    W, H = w * SS, h * SS
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy, R = W / 2, H - 6 * SS, min(W / 2 - 8 * SS, H - 14 * SS)
    box = [cx - R, cy - R, cx + R, cy + R]
    dim = 0.35 if not active else 1.0
    zones = [(-50, -15, "#ff453a"), (-15, -5, "#ffd60a"), (-5, 5, "#32d74b"), (5, 15, "#ffd60a"), (15, 50, "#ff453a")]
    for a, b, col in zones:
        d.arc(box, 270 + a * 0.9, 270 + b * 0.9, fill=rgb(shade(col, dim)) + (255,), width=4 * SS)
    for c in range(-50, 51, 10):
        th = math.radians(270 + c * 0.9)
        r0 = R - (14 if c % 50 == 0 else 9) * SS
        d.line([(cx + math.cos(th) * r0, cy + math.sin(th) * r0),
                (cx + math.cos(th) * (R - 5 * SS), cy + math.sin(th) * (R - 5 * SS))],
               fill=(150, 150, 160, int(255 * dim)), width=SS)
    if active and cents is not None:
        th = math.radians(270 + max(-50, min(50, cents)) * 0.9)
        d.line([(cx, cy), (cx + math.cos(th) * (R - 3 * SS), cy + math.sin(th) * (R - 3 * SS))],
               fill=rgb(color) + (255,), width=2 * SS)
    d.ellipse([cx - 5 * SS, cy - 5 * SS, cx + 5 * SS, cy + 5 * SS], fill=(200, 200, 208, 255))
    return img.resize((w, h), LZ)


# --------------------------------------------------------------------------- canvas widgets

class _Item:
    """Base: registers wheel handler for the item under the mouse."""

    @staticmethod
    def wheel_map(cv):
        if not hasattr(cv, "_wheel_map"):
            cv._wheel_map = {}
        return cv._wheel_map

    def _cursor(self, cv, item, cursor):
        cv.tag_bind(item, "<Enter>", lambda e: cv.configure(cursor=cursor))
        cv.tag_bind(item, "<Leave>", lambda e: cv.configure(cursor=""))


class CKnob(_Item):
    def __init__(self, cv, x, y, label, vmin, vmax, default, command, fmt="{:.2f}", log=False,
                 accent="#4fc3f7", text=TEXT, vtext=DIM, size=44, step=None, tags=()):
        self.cv, self.size = cv, size
        self.vmin, self.vmax, self.default = vmin, vmax, default
        self.command, self.fmt, self.log, self.step, self.accent = command, fmt, log, step, accent
        self.value = default
        self._drag = None
        half = (size + 22) / 2
        self.img = cv.create_image(x, y, image=knob_photo(size, self._norm(default), accent), tags=tags)
        self.lab = cv.create_text(x, y - half - 1, text=label.upper(), fill=text, font=LABEL_FONT, tags=tags)
        self.val = cv.create_text(x, y + half - 1, text="", fill=vtext, font=VALUE_FONT, tags=tags)
        cv.tag_bind(self.img, "<ButtonPress-1>", self._press)
        cv.tag_bind(self.img, "<B1-Motion>", self._motion)
        cv.tag_bind(self.img, "<Double-Button-1>", lambda e: self.set_value(self.default, notify=True))
        self._cursor(cv, self.img, "sb_v_double_arrow")
        self.wheel_map(cv)[self.img] = self._wheel
        self._draw()

    def _norm(self, v):
        if self.log:
            return math.log(v / self.vmin) / math.log(self.vmax / self.vmin)
        return (v - self.vmin) / (self.vmax - self.vmin)

    def _denorm(self, n):
        n = min(1.0, max(0.0, n))
        v = self.vmin * (self.vmax / self.vmin) ** n if self.log else self.vmin + n * (self.vmax - self.vmin)
        if self.step:
            v = round(v / self.step) * self.step
        return v

    def set_value(self, v, notify=False):
        v = self._denorm(self._norm(v))
        changed = v != self.value
        self.value = v
        self._draw()
        if notify and changed:
            self.command(v)

    def _press(self, e):
        self._drag = (e.y, self._norm(self.value))

    def _motion(self, e):
        if self._drag:
            y0, n0 = self._drag
            scale = 600.0 if e.state & 0x0001 else 150.0
            self.set_value(self._denorm(n0 + (y0 - e.y) / scale), notify=True)

    def _wheel(self, e):
        if self.step:
            v = self.value + (self.step if e.delta > 0 else -self.step)
            self.set_value(min(self.vmax, max(self.vmin, v)), notify=True)
            return
        step = 0.01 if e.state & 0x0001 else 0.04
        self.set_value(self._denorm(self._norm(self.value) + (step if e.delta > 0 else -step)), notify=True)

    def _draw(self):
        self.cv.itemconfigure(self.img, image=knob_photo(self.size, self._norm(self.value), self.accent))
        self.cv.itemconfigure(self.val, text=self.fmt.format(self.value))


class CFootswitch(_Item):
    def __init__(self, cv, x, y, command, led="#ff3b30", size=56, momentary=False, label="", tags=()):
        self.cv, self.command, self.led, self.size, self.momentary = cv, command, led, size, momentary
        self.on = False
        self.led_item = cv.create_image(x, y - size / 2 - 14, image=led_photo(led, False), tags=tags)
        self.sw = cv.create_image(x, y, image=footswitch_photo(size), tags=tags)
        self.txt = cv.create_text(x, y, text=label, fill="#2a2a30", font=("Bahnschrift SemiBold", 7), tags=tags)
        self._label = label
        for it in (self.sw, self.txt):
            cv.tag_bind(it, "<ButtonPress-1>", self._press)
            cv.tag_bind(it, "<ButtonRelease-1>", self._release)
            self._cursor(cv, it, "hand2")

    @property
    def label(self):
        return self._label

    @label.setter
    def label(self, v):
        self._label = v
        self.cv.itemconfigure(self.txt, text=v)

    def _press(self, e):
        self.cv.itemconfigure(self.sw, image=footswitch_photo(self.size, True))
        if self.momentary:
            self.command(1)
        else:
            self.set_value(not self.on, notify=True)

    def _release(self, e):
        self.cv.itemconfigure(self.sw, image=footswitch_photo(self.size, False))

    def set_value(self, on, notify=False):
        self.on = bool(on)
        self.cv.itemconfigure(self.led_item, image=led_photo(self.led, self.on))
        if notify:
            self.command(1 if self.on else 0)

    def set_led(self, color):
        self.led = color
        self.cv.itemconfigure(self.led_item, image=led_photo(self.led, self.on))


class CSegmented(_Item):
    ROW_H = 24

    @staticmethod
    def rows(options, max_w=10 ** 6):
        """Greedy wrap of the pill row into lines no wider than max_w."""
        f = tkfont.Font(font=LABEL_FONT)
        out, cur, cw = [], [], 0
        for i, o in enumerate(options):
            w = f.measure(o) + 16
            if cur and cw + 3 + w > max_w:
                out.append(cur)
                cur, cw = [], 0
            cur.append((i, o, w))
            cw += w + (3 if len(cur) > 1 else 0)
        if cur:
            out.append(cur)
        return out

    def __init__(self, cv, x, y, options, command, on_fill, on_text, off_fill, off_text, h=20, tags=(),
                 max_w=10 ** 6):
        self.cv, self.command = cv, command
        self.colors = (on_fill, on_text, off_fill, off_text)
        self.items = [None] * len(options)
        for r, row in enumerate(self.rows(options, max_w)):
            total = sum(w for _, _, w in row) + 3 * (len(row) - 1)
            cx = x - total / 2
            ry = y + r * self.ROW_H
            for i, o, w in row:
                img = cv.create_image(cx + w / 2, ry, tags=tags)
                txt = cv.create_text(cx + w / 2, ry, text=o, font=LABEL_FONT, tags=tags)
                for it in (img, txt):
                    cv.tag_bind(it, "<Button-1>", lambda e, i=i: self.set_value(i, notify=True))
                    self._cursor(cv, it, "hand2")
                self.items[i] = (img, txt, w, h)
                cx += w + 3
        self.index = 0
        self.set_value(0)

    def set_value(self, i, notify=False):
        self.index = int(round(i))
        on_f, on_t, off_f, off_t = self.colors
        for j, (img, txt, w, h) in enumerate(self.items):
            sel = j == self.index
            self.cv.itemconfigure(img, image=pill_photo(int(w), h, on_f if sel else off_f))
            self.cv.itemconfigure(txt, fill=on_t if sel else off_t)
        if notify:
            self.command(self.index)


class CButton(_Item):
    def __init__(self, cv, x, y, text, command, fill="#3a3a42", fg=TEXT, h=22, w=None, font=LABEL_FONT, tags=()):
        self.cv, self.command, self.fill, self.fg, self.h, self.font = cv, command, fill, fg, h, font
        f = tkfont.Font(font=font)
        self.w = w or f.measure(text) + 22
        self.img = cv.create_image(x, y, image=pill_photo(self.w, h, fill), tags=tags)
        self.txt = cv.create_text(x, y, text=text, fill=fg, font=font, tags=tags)
        for it in (self.img, self.txt):
            cv.tag_bind(it, "<Button-1>", lambda e: self.command())
            cv.tag_bind(it, "<Enter>", lambda e: self._hover(True))
            cv.tag_bind(it, "<Leave>", lambda e: self._hover(False))

    def _hover(self, on):
        self.cv.configure(cursor="hand2" if on else "")
        self.cv.itemconfigure(self.img, image=pill_photo(self.w, self.h, shade(self.fill, 1.18) if on else self.fill))


class CWah(_Item):
    """Wah treadle: drag up/down or scroll (up = toe). Interface: .active, .show(pos, freq)."""

    def __init__(self, cv, x, y, command, w=196, h=112, text=TEXT, tags=()):
        self.cv, self.command, self.w, self.h = cv, command, w, h
        self.pos, self.freq, self.active = 0.5, 0.0, True
        self._drag = None
        self.img = cv.create_image(x, y + h / 2, image=treadle_photo(w, h, 0.5), tags=tags)
        self.ftxt = cv.create_text(x, y + 12, text="", fill=text, font=("Bahnschrift SemiBold", 12), tags=tags)
        self.heel = cv.create_text(x - w / 2 + 14, y + h - 4, text="HEEL", fill=text, font=SMALL_FONT,
                                   anchor="w", tags=tags)
        self.toe = cv.create_text(x + w / 2 - 14, y + h - 4, text="TOE", fill=text, font=SMALL_FONT,
                                  anchor="e", tags=tags)
        cv.tag_bind(self.img, "<ButtonPress-1>", lambda e: setattr(self, "_drag", (e.y, self.pos)))
        cv.tag_bind(self.img, "<B1-Motion>", self._motion)
        self._cursor(cv, self.img, "sb_v_double_arrow")
        self.wheel_map(cv)[self.img] = self._wheel

    def show(self, pos, freq):
        if abs(pos - self.pos) > 0.004 or abs(freq - self.freq) > 1:
            self.pos, self.freq = pos, freq
            self.cv.itemconfigure(self.img, image=treadle_photo(self.w, self.h, pos))
            self.cv.itemconfigure(self.ftxt, text=f"{freq:.0f} Hz")

    def _motion(self, e):
        if self._drag and self.active:
            y0, p0 = self._drag
            self.command(min(1.0, max(0.0, p0 + (y0 - e.y) / 110.0)))

    def _wheel(self, e):
        if self.active:
            self.command(min(1.0, max(0.0, self.pos + (0.05 if e.delta > 0 else -0.05))))


class CMeter:
    """Segmented LED ladder meter. Interface: push(peak)."""
    N = 20

    def __init__(self, cv, x, y, h=120, label="", tags=()):
        self.cv = cv
        self.level = self.hold = 0.0
        seg = h / self.N
        self.segs = []
        cv.create_rectangle(x - 8, y - 3, x + 8, y + h + 3, fill="#0b0b0d", outline="#000", tags=tags)
        for i in range(self.N):
            frac = (i + 1) / self.N
            col = "#ff453a" if frac > 0.92 else "#ffd60a" if frac > 0.75 else "#32d74b"
            y1 = y + h - i * seg
            it = cv.create_rectangle(x - 5, y1 - seg + 1.5, x + 5, y1 - 0.5, fill=shade(col, 0.22), outline="",
                                     tags=tags)
            self.segs.append((it, col, False))
        if label:
            cv.create_text(x, y + h + 12, text=label, fill=DIM, font=SMALL_FONT, tags=tags)

    def push(self, peak):
        db = 20 * math.log10(peak) if peak > 1e-6 else -120
        n = min(1.0, max(0.0, (db + 60) / 60))
        self.level = max(n, self.level - 0.035)
        self.hold = max(n, self.hold - 0.006)
        lit = int(round(self.level * self.N))
        hold = min(self.N - 1, int(self.hold * self.N))
        for i, (it, col, was) in enumerate(self.segs):
            on = i < lit or (i == hold and self.hold > 0.02)
            if on != was:
                self.cv.itemconfigure(it, fill=col if on else shade(col, 0.22))
                self.segs[i] = (it, col, on)


NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


class CTuner:
    """Needle tuner. Interface: show(freq, active=True)."""

    def __init__(self, cv, x, y, w=150, h=84, tags=()):
        self.cv, self.w, self.h = cv, w, h
        self.img = cv.create_image(x, y + h / 2, tags=tags)
        self.note = cv.create_text(x, y + h - 36, text="", font=("Bahnschrift SemiBold", 22), fill=TEXT, tags=tags)
        self.info = cv.create_text(x, y + h + 10, text="", font=SMALL_FONT, fill=DIM, tags=tags)
        self._photo = None
        self.show(None, active=False)

    def show(self, freq, active=True):
        if not active:
            self._render(None, DIM, False)
            self.cv.itemconfigure(self.note, text="OFF", fill=DIM)
            self.cv.itemconfigure(self.info, text="press T or the switch")
            return
        if freq is None:
            self._render(None, DIM, True)
            self.cv.itemconfigure(self.note, text="–", fill=DIM)
            self.cv.itemconfigure(self.info, text="play a single string")
            return
        midi = 69 + 12 * math.log2(freq / 440.0)
        near = int(round(midi))
        cents = (midi - near) * 100
        col = "#32d74b" if abs(cents) < 5 else "#ffd60a" if abs(cents) < 15 else "#ff453a"
        self._render(cents, col, True)
        self.cv.itemconfigure(self.note, text=NOTE_NAMES[near % 12], fill=col)
        self.cv.itemconfigure(self.info, text=f"{freq:.1f} Hz   {cents:+.0f}¢   octave {near // 12 - 1}")

    def _render(self, cents, color, active):
        self._photo = ImageTk.PhotoImage(tuner_image(self.w, self.h, cents, color, active))
        self.cv.itemconfigure(self.img, image=self._photo)


class CCheck:
    """Canvas checkbox bound to a BooleanVar."""

    def __init__(self, cv, x, y, text, var, command=None, fg=TEXT, tags=()):
        self.cv, self.var, self.command, self.text = cv, var, command, text
        self.item = cv.create_text(x, y, text="", fill=fg, font=("Segoe UI", 8), tags=tags)
        cv.tag_bind(self.item, "<Button-1>", self._click)
        cv.tag_bind(self.item, "<Enter>", lambda e: cv.configure(cursor="hand2"))
        cv.tag_bind(self.item, "<Leave>", lambda e: cv.configure(cursor=""))
        self._draw()

    def _click(self, e):
        self.var.set(not self.var.get())
        self._draw()
        if self.command:
            self.command()

    def _draw(self):
        self.cv.itemconfigure(self.item, text=("☑ " if self.var.get() else "☐ ") + self.text)


class CText:
    """Adapter so v2 code can .configure(text=, fg=) / .cget('text') a canvas text item."""

    def __init__(self, cv, item):
        self.cv, self.item = cv, item

    def configure(self, text=None, fg=None, **_):
        if text is not None:
            self.cv.itemconfigure(self.item, text=text)
        if fg is not None:
            self.cv.itemconfigure(self.item, fill=fg)

    config = configure

    def cget(self, k):
        return self.cv.itemcget(self.item, "text" if k == "text" else "fill")


class CBar:
    """Adapter for the looper progress bar (v2 calls delete / create_rectangle / ['width'])."""

    def __init__(self, cv, x, y, w, h=7, tags=()):
        self.cv, self.x, self.y, self.w, self.h, self.tags = cv, x, y, w, h, tags
        cv.create_image(x + w / 2, y + h / 2, image=pill_photo(int(w), h, "#101012"), tags=tags)
        self.fill = None

    def __getitem__(self, k):
        return self.w if k == "width" else None

    def delete(self, _):
        if self.fill is not None:
            self.cv.delete(self.fill)
            self.fill = None

    def create_rectangle(self, x0, y0, x1, y1, fill="", outline=""):
        if x1 - x0 >= 2:
            self.fill = self.cv.create_rectangle(self.x + 1, self.y + 1, self.x + x1 - 1, self.y + self.h - 1,
                                                 fill=fill, outline="", tags=self.tags)


class ClipLed:
    """Adapter: v2 calls clip_led.configure(bg=..., fg=...)."""

    def __init__(self, cv, x, y, tags=()):
        self.cv = cv
        self.led = cv.create_image(x - 18, y, image=led_photo("#ff453a", False, 20), tags=tags)
        cv.create_text(x + 4, y, text="CLIP", fill=DIM, font=LABEL_FONT, tags=tags)
        self.on = None

    def configure(self, bg=None, **_):
        on = bg == "#ff3b30"
        if on != self.on:
            self.on = on
            self.cv.itemconfigure(self.led, image=led_photo("#ff453a", on, 20))


class PillButton(tk.Canvas):
    """Stand-alone rounded button widget. Supports configure(text=, bg=, fg=) and cget('text')."""

    def __init__(self, parent, text, command, bg="#3a3a42", fg=TEXT, font=("Bahnschrift SemiBold", 9),
                 h=28, minw=0):
        pbg = parent.cget("bg")
        super().__init__(parent, height=h + 2, bg=pbg, highlightthickness=0, bd=0)
        self._text, self._bg, self._fg, self._font, self._h, self._minw = text, bg, fg, font, h, minw
        self.command = command
        self._hover = False
        self.img = self.create_image(0, 0, anchor="nw")
        self.txt = self.create_text(0, 0, text=text, fill=fg, font=font)
        self.bind("<Button-1>", lambda e: self.command())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.configure(cursor="hand2")
        self._layout()

    def _layout(self):
        w = max(self._minw, tkfont.Font(font=self._font).measure(self._text) + 26)
        tk.Canvas.configure(self, width=w)
        fill = shade(self._bg, 1.15) if self._hover else self._bg
        self.itemconfigure(self.img, image=pill_photo(w, self._h, fill))
        self.coords(self.img, 0, 1)
        self.coords(self.txt, w / 2, self._h / 2 + 1)
        self.itemconfigure(self.txt, text=self._text, fill=self._fg)

    def _set_hover(self, on):
        self._hover = on
        self._layout()

    def configure(self, cnf=None, **kw):
        mine = False
        if "text" in kw:
            self._text = kw.pop("text")
            mine = True
        if "bg" in kw and getattr(self, "_h", None):
            self._bg = kw.pop("bg")
            mine = True
        if "fg" in kw:
            self._fg = kw.pop("fg")
            mine = True
        if kw or cnf:
            tk.Canvas.configure(self, cnf, **kw)
        if mine:
            self._layout()

    config = configure

    def cget(self, key):
        if key == "text":
            return self._text
        return tk.Canvas.cget(self, key)

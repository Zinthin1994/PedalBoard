"""Tk widgets for PedalBoard v2: knobs, footswitches, wah treadle, meters, tuner."""
import math
import tkinter as tk

BG = "#16161a"
PANEL = "#202026"
TEXT = "#e8e8ea"
DIM = "#8a8a94"
ACCENT = "#4fc3f7"


def _rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def shade(c, f):
    """f < 1 darkens, f > 1 lightens towards white."""
    r, g, b = _rgb(c)
    if f <= 1:
        r, g, b = (int(v * f) for v in (r, g, b))
    else:
        t = f - 1
        r, g, b = (int(v + (255 - v) * t) for v in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def is_light(c):
    r, g, b = _rgb(c)
    return 0.299 * r + 0.587 * g + 0.114 * b > 140


class Knob(tk.Canvas):
    """Drag up/down (Shift = fine), mouse wheel, double-click resets."""

    def __init__(self, parent, label, vmin, vmax, default, command, fmt="{:.2f}", log=False,
                 color=ACCENT, bg=PANEL, size=44, text=TEXT, step=None):
        self.size = size
        super().__init__(parent, width=size + 24, height=size + 36, bg=bg, highlightthickness=0,
                         cursor="sb_v_double_arrow")
        self.label, self.vmin, self.vmax = label, vmin, vmax
        self.default, self.command, self.fmt, self.log = default, command, fmt, log
        self.color, self.text, self.step = color, text, step
        self.track = shade(bg, 0.7) if is_light(bg) else shade(bg, 1.35)
        self.value = default
        self._drag = None
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Double-Button-1>", lambda e: self.set_value(self.default, notify=True))
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
            self.command(self.value)

    def _press(self, e):
        self._drag = (e.y, self._norm(self.value))

    def _motion(self, e):
        if self._drag:
            y0, n0 = self._drag
            scale = 600.0 if e.state & 0x0001 else 150.0
            self.set_value(self._denorm(n0 + (y0 - e.y) / scale), notify=True)

    def _wheel(self, e):
        n = self._norm(self.value)
        if self.step:
            v = self.value + (self.step if e.delta > 0 else -self.step)
            self.set_value(min(self.vmax, max(self.vmin, v)), notify=True)
            return
        step = 0.01 if e.state & 0x0001 else 0.04
        self.set_value(self._denorm(n + (step if e.delta > 0 else -step)), notify=True)

    def _draw(self):
        self.delete("all")
        w = int(self["width"])
        s = self.size
        cx, cy = w / 2, 15 + s / 2
        r = s / 2
        self.create_text(cx, 6, text=self.label.upper(), fill=self.text, font=("Segoe UI", 7, "bold"))
        self.create_arc(cx - r, cy - r, cx + r, cy + r, start=-45, extent=270,
                        style="arc", width=4, outline=self.track)
        n = self._norm(self.value)
        if n > 0.003:
            self.create_arc(cx - r, cy - r, cx + r, cy + r, start=225, extent=-270 * n,
                            style="arc", width=4, outline=self.color)
        ri = r - 6
        self.create_oval(cx - ri, cy - ri, cx + ri, cy + ri, fill="#2c2c33", outline="#111")
        ang = math.radians(225 - 270 * n)
        self.create_line(cx, cy, cx + (ri - 3) * math.cos(ang), cy - (ri - 3) * math.sin(ang),
                         fill="white", width=3, capstyle="round")
        self.create_text(cx, cy + r + 9, text=self.fmt.format(self.value), fill=self.text,
                         font=("Segoe UI", 7))


class Footswitch(tk.Canvas):
    """Stomp switch with status LED. Click toggles (or calls command on press if momentary)."""

    def __init__(self, parent, command, bg=PANEL, led="#ff3b30", size=64, label="", momentary=False):
        super().__init__(parent, width=size, height=size, bg=bg, highlightthickness=0, cursor="hand2")
        self.command, self.led, self.size, self.label = command, led, size, label
        self.momentary = momentary
        self.on = False
        self.bind("<ButtonPress-1>", self._click)
        self._draw()

    def _click(self, e):
        if self.momentary:
            self.command(1)
        else:
            self.set_value(not self.on, notify=True)

    def set_value(self, on, notify=False):
        self.on = bool(on)
        self._draw()
        if notify:
            self.command(1 if self.on else 0)

    def set_led(self, color):
        self.led = color
        self._draw()

    def _draw(self):
        self.delete("all")
        s = self.size
        cx = s / 2
        off = shade(self.led, 0.3)
        if self.on:
            self.create_oval(cx - 10, 1, cx + 10, 21, outline=self.led)
        self.create_oval(cx - 6, 5, cx + 6, 17, fill=self.led if self.on else off, outline="#000")
        r = s * 0.3
        cy = s - r - 4
        self.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#9a9aa2", outline="#55555c", width=2)
        self.create_oval(cx - r + 6, cy - r + 6, cx + r - 6, cy + r - 6, fill="#c9c9d0", outline="#7a7a82")
        if self.label:
            self.create_text(cx, cy, text=self.label, fill="#222", font=("Segoe UI", 7, "bold"))


class Segmented(tk.Frame):
    def __init__(self, parent, options, command, bg=PANEL, on_bg=ACCENT, on_fg="#111",
                 off_bg="#34343c", off_fg=TEXT):
        super().__init__(parent, bg=bg)
        self.command = command
        self.colors = (on_bg, on_fg, off_bg, off_fg)
        self.buttons = []
        self.index = 0
        for i, opt in enumerate(options):
            b = tk.Label(self, text=opt, padx=5, pady=1, font=("Segoe UI", 7, "bold"), cursor="hand2")
            b.pack(side="left", padx=1)
            b.bind("<Button-1>", lambda e, i=i: self.set_value(i, notify=True))
            self.buttons.append(b)
        self.set_value(0)

    def set_value(self, i, notify=False):
        self.index = int(round(i))
        on_bg, on_fg, off_bg, off_fg = self.colors
        for j, b in enumerate(self.buttons):
            b.configure(bg=on_bg if j == self.index else off_bg, fg=on_fg if j == self.index else off_fg)
        if notify:
            self.command(self.index)


class WahPedal(tk.Canvas):
    """Side view of a wah treadle. Drag up/down or scroll to rock it (up = toe)."""

    def __init__(self, parent, command, bg, width=200, height=130):
        super().__init__(parent, width=width, height=height, bg=bg, highlightthickness=0,
                         cursor="sb_v_double_arrow")
        self.W, self.H = width, height
        self.command = command
        self.pos, self.freq = 0.5, 0.0
        self.active = True
        self._drag = None
        self.bind("<ButtonPress-1>", lambda e: setattr(self, "_drag", (e.y, self.pos)))
        self.bind("<B1-Motion>", self._motion)
        self.bind("<MouseWheel>", self._wheel)
        self._draw()

    def show(self, pos, freq):
        if abs(pos - self.pos) > 0.002 or abs(freq - self.freq) > 1:
            self.pos, self.freq = pos, freq
            self._draw()

    def _motion(self, e):
        if self._drag and self.active:
            y0, p0 = self._drag
            self.command(min(1.0, max(0.0, p0 + (y0 - e.y) / 110.0)))

    def _wheel(self, e):
        if self.active:
            self.command(min(1.0, max(0.0, self.pos + (0.05 if e.delta > 0 else -0.05))))

    def _draw(self):
        self.delete("all")
        W = self.W
        cx, cy = W / 2, self.H - 46
        half = W / 2 - 18
        self.create_polygon(14, cy + 24, W - 14, cy + 24, W - 22, cy + 36, 22, cy + 36,
                            fill="#0d0d10", outline="#333")
        self.create_polygon(cx - 10, cy + 24, cx + 10, cy + 24, cx, cy, fill="#444")
        th = math.radians((self.pos - 0.5) * 26)
        ct, st = math.cos(th), math.sin(th)
        pts = []
        for x, y in ((-half, -8), (half, -8), (half, 6), (-half, 6)):
            pts += [cx + x * ct - y * st, cy + x * st + y * ct]
        self.create_polygon(*pts, fill="#2a2a30", outline="#5a5a64", width=2)
        k = -half + 14
        while k < half - 10:
            self.create_line(cx + k * ct + 8 * st, cy + k * st - 8 * ct,
                             cx + (k + 6) * ct + 8 * st, cy + (k + 6) * st - 8 * ct, fill="#777", width=2)
            k += 14
        self.create_text(16, self.H - 4, text="HEEL", fill=DIM, font=("Segoe UI", 7), anchor="sw")
        self.create_text(W - 16, self.H - 4, text="TOE", fill=DIM, font=("Segoe UI", 7), anchor="se")
        self.create_rectangle(14, 6, W - 14, 13, fill="#2c2c33", outline="")
        self.create_rectangle(14, 6, 14 + (W - 28) * self.pos, 13, fill="#d9b44a", outline="")
        if self.freq:
            self.create_text(cx, 28, text=f"{self.freq:.0f} Hz", fill=TEXT, font=("Segoe UI", 11, "bold"))


class Meter(tk.Canvas):
    def __init__(self, parent, bg=PANEL, label="", height=130):
        super().__init__(parent, width=22, height=height, bg=bg, highlightthickness=0)
        self.level = self.hold = 0.0
        self.label = label
        self.h = height - 14

    def push(self, peak):
        db = 20 * math.log10(peak) if peak > 1e-6 else -120
        n = min(1.0, max(0.0, (db + 60) / 60))
        self.level = max(n, self.level - 0.04)
        self.hold = max(n, self.hold - 0.01)
        self.delete("all")
        h = self.h
        self.create_rectangle(5, 2, 17, 2 + h, fill="#0d0d10", outline="#333")
        color = "#ff3b30" if self.level > 0.95 else "#ffcc00" if self.level > 0.8 else "#34c759"
        self.create_rectangle(6, 2 + h * (1 - self.level), 16, 2 + h, fill=color, outline="")
        hy = 2 + h * (1 - self.hold)
        self.create_line(6, hy, 16, hy, fill="white")
        self.create_text(11, h + 9, text=self.label, fill=DIM, font=("Segoe UI", 7))


NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


class TunerDisplay(tk.Canvas):
    def __init__(self, parent, bg=PANEL, width=150):
        super().__init__(parent, width=width, height=96, bg=bg, highlightthickness=0)
        self.W = width
        self.show(None)

    def show(self, freq, active=True):
        self.delete("all")
        W = self.W
        cx = W / 2
        if not active:
            self.create_text(cx, 40, text="TUNER OFF", fill=DIM, font=("Segoe UI", 10, "bold"))
            self.create_text(cx, 62, text="press T or the switch", fill=DIM, font=("Segoe UI", 7))
            return
        for c in range(-50, 51, 10):
            x = cx + c * (W / 2 - 10) / 50
            self.create_line(x, 70, x, 76 if c % 50 else 80, fill=DIM)
        if freq is None:
            self.create_text(cx, 34, text="–", fill=DIM, font=("Segoe UI", 26, "bold"))
            return
        midi = 69 + 12 * math.log2(freq / 440.0)
        near = int(round(midi))
        cents = (midi - near) * 100
        name = NOTE_NAMES[near % 12]
        octv = near // 12 - 1
        color = "#34c759" if abs(cents) < 5 else "#ffcc00" if abs(cents) < 15 else "#ff3b30"
        self.create_text(cx, 32, text=name, fill=color, font=("Segoe UI", 28, "bold"))
        self.create_text(cx + 30, 40, text=str(octv), fill=DIM, font=("Segoe UI", 9))
        x = cx + max(-50, min(50, cents)) * (W / 2 - 10) / 50
        self.create_polygon(x, 66, x - 6, 56, x + 6, 56, fill=color)
        self.create_text(cx, 90, text=f"{freq:.1f} Hz   {cents:+.0f}¢", fill=TEXT, font=("Segoe UI", 8))


def detect_pitch(x, sr, fmin=60.0, fmax=1200.0):
    """YIN pitch estimate (Hz) of the most recent samples, or None."""
    import numpy as np
    N = 4096 if sr <= 50000 else 8192
    x = np.asarray(x[-N:], dtype=np.float64)
    x = x - x.mean()
    if np.sqrt(np.mean(x * x)) < 0.002:
        return None
    W = N // 2
    tmin, tmax = int(sr / fmax), min(int(sr / fmin), W - 1)
    size = 1 << int(np.ceil(np.log2(N + W)))
    r = np.fft.irfft(np.fft.rfft(x, size) * np.conj(np.fft.rfft(x[:W], size)), size)[:tmax + 2]
    c = np.concatenate(([0.0], np.cumsum(x * x)))
    e0 = c[W]
    tau = np.arange(tmax + 2)
    et = c[tau + W] - c[tau]
    d = e0 + et - 2 * r
    d[0] = 0
    cm = np.cumsum(d[1:])
    dn = np.ones_like(d)
    dn[1:] = d[1:] * np.arange(1, len(d)) / np.maximum(cm, 1e-12)
    cand = np.where(dn[tmin:tmax] < 0.15)[0]
    if len(cand):
        t = cand[0] + tmin
        while t + 1 < tmax and dn[t + 1] < dn[t]:
            t += 1
    else:
        t = int(np.argmin(dn[tmin:tmax])) + tmin
        if dn[t] > 0.35:
            return None
    if 1 <= t < len(dn) - 1:
        a, b, cc = dn[t - 1], dn[t], dn[t + 1]
        den = a - 2 * b + cc
        t = t + (0.5 * (a - cc) / den if abs(den) > 1e-12 else 0.0)
    return sr / t

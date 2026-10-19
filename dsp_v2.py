"""PedalBoard v2 DSP: a chain of modular, numba-compiled pedals.

Each pedal type owns a slice of the flat parameter array P (PST floats; P[0] is
its on/off switch), two state slices in S (SST floats each: left / right
channel) and an optional slice of the shared delay-line memory MEM.

The signal starts mono (left buffer). The first active stereo pedal splits it
into L/R; mono pedals placed after that run once per channel with separate
state, so stereo width is preserved.
"""
import math

import numpy as np
from numba import njit

PST = 16      # params per pedal
SST = 64      # state floats per pedal per channel

# ---- pedal type ids (order = default chain order) ----
T_GATE = 0
T_COMP = 1
T_BOOST = 2
T_OCTAVE = 3
T_WAH = 4
T_ENVF = 5
T_SWELL = 6
T_FUZZ = 7
T_OD = 8
T_DIST = 9
T_EQ = 10
T_PITCH = 11
T_RING = 12
T_CRUSH = 13
T_PHASER = 14
T_UNIVIBE = 15
T_TREM = 16
T_VIBRATO = 17
T_CHORUS = 18
T_FLANGER = 19
T_ROTARY = 20
T_PAN = 21
T_DELAY = 22
T_REVERB = 23
T_LOOPER = 24
T_AMP = 25
T_MGATE = 26
T_DROP = 27
T_HM2 = 28
T_MZONE = 29
T_TBOOST = 30
T_DOUBLER = 31
T_DRUMS = 32
T_CUT = 33
N_TYPES = 34

# 0 = mono, 1 = stereo (crossfaded bypass), 2 = stereo, handles its own bypass (tails)
KIND = np.array([0] * 18 + [1, 1, 1, 1, 2, 2, 2] + [0] + [0, 0, 0, 0, 0, 1, 2] + [0], dtype=np.int64)
S_DRUM_STEP = 20

# ---- global params / state ----
G_IN_GAIN = 0
G_CAB = 1          # 0 off, 1 basic filter cab, 2 impulse response
G_MASTER = 2
G_MUTE = 3
G_IR_LEN = 4       # taps of the loaded impulse response (0 = none)
G_CABPOS = 5       # 0 = cabinet at the very end of the chain, 1 = right after the AMP slot
#                    (only matters for non-linear / modulated blocks after the amp; linear ones commute)
N_G = 6

IR_SECONDS = 0.0215   # longest IR used (cab IRs carry almost everything in ~20 ms)

GS_PEAK_IN = 0
GS_PEAK_OUT = 1
GS_CLIPS = 2
GS_MASTER = 3
GS_CAB_L = 4      # 9 floats: mix + 8 filter states
GS_CAB_R = 13
GS_IR_W = 22      # IR history write index
N_GS = 24

# state slots other code reads
S_WAH_POS = 3
S_LOOP_LEN = 1
S_LOOP_POS = 2
S_LOOP_HAS = 5
S_LOOP_EFF = 6

LN2 = math.log(2.0)
TWO_PI = 2.0 * math.pi
LOOP_SECONDS = 60.0


# --------------------------------------------------------------------------- helpers

@njit(cache=True)
def _op(t, sr):
    """One-pole smoothing coefficient for time constant t seconds."""
    return math.exp(-1.0 / (max(t, 1e-6) * sr))


@njit(cache=True)
def _svf(x, g, k, ic1, ic2):
    """Trapezoidal SVF. Returns (band, low, ic1', ic2'); high = x - k*band - low."""
    a1 = 1.0 / (1.0 + g * (g + k))
    a2 = g * a1
    a3 = g * a2
    v3 = x - ic2
    v1 = a1 * ic1 + a2 * v3
    v2 = ic2 + a2 * ic1 + a3 * v3
    return v1, v2, 2.0 * v1 - ic1, 2.0 * v2 - ic2


@njit(cache=True)
def _g(fc, sr):
    return math.tan(math.pi * min(fc, 0.45 * sr) / sr)


@njit(cache=True)
def _G1(fc, sr):
    """Coefficient for the 1-pole TPT filter."""
    g = _g(fc, sr)
    return g / (1.0 + g)


@njit(cache=True)
def _F(x, hard):
    """Antiderivative of tanh (hard=0) or clip (hard=1), for ADAA."""
    ax = abs(x)
    if hard == 0:
        return ax + math.log1p(math.exp(-2.0 * ax)) - LN2
    if ax <= 1.0:
        return 0.5 * x * x
    return ax - 0.5


@njit(cache=True)
def _f(x, hard):
    if hard == 0:
        return math.tanh(x)
    return min(1.0, max(-1.0, x))


@njit(cache=True)
def _adaa(u, xp, Fp, hard):
    """First-order antiderivative anti-aliased clipper. Returns (y, Fu)."""
    Fu = _F(u, hard)
    du = u - xp
    if abs(du) > 1e-6:
        return (Fu - Fp) / du, Fu
    return _f(0.5 * (u + xp), hard), Fu


@njit(cache=True)
def _rd(buf, off, size, w, d):
    """Read buf[off:off+size] d samples (fractional) behind write index w."""
    rp = w - d
    while rp < 0.0:
        rp += size
    i0 = int(rp)
    fr = rp - i0
    if i0 >= size:
        i0 -= size
    i1 = i0 + 1
    if i1 >= size:
        i1 = 0
    return buf[off + i0] * (1.0 - fr) + buf[off + i1] * fr


@njit(cache=True)
def rv_sizes(sr):
    """Reverb memory layout: (predelay, allpass, line) segment sizes."""
    sc = int(math.ceil(sr / 48000.0))
    return int(0.2 * sr) + 2, 1024 * sc, 4096 * sc


def mem_sizes(sr):
    """Delay memory per pedal type (per channel for mono pedals)."""
    m = np.zeros(N_TYPES, dtype=np.int64)
    m[T_VIBRATO] = int(0.03 * sr)
    m[T_PITCH] = int(0.12 * sr)
    m[T_CHORUS] = int(0.05 * sr)
    m[T_FLANGER] = 2 * int(0.025 * sr)
    m[T_ROTARY] = 2 * int(0.02 * sr)
    m[T_DELAY] = 2 * int(2.1 * sr)
    pre, ap, ln = rv_sizes(sr)
    m[T_REVERB] = pre + 4 * ap + 8 * ln
    m[T_LOOPER] = 2 * int(LOOP_SECONDS * sr)
    m[T_MGATE] = 16384                 # holds the clean input block (gate key)
    m[T_DROP] = int(0.12 * sr)
    m[T_DOUBLER] = int(0.06 * sr)
    return m


# --------------------------------------------------------------------------- mono pedals
# signature: (x, n, p, s, mem, sr) - process x[:n] in place. s[0] is reserved.

@njit(cache=True)
def gate(x, n, p, s, mem, sr):
    thr = p[1]
    ea, er = _op(0.0005, sr), _op(0.08, sr)
    ga, gr = _op(0.001, sr), _op(p[2], sr)
    env, g, op = s[1], s[2], s[3] > 0.5
    for i in range(n):
        a = abs(x[i])
        c = ea if a > env else er
        env = c * env + (1.0 - c) * a
        if op:
            if env < thr * 0.5:
                op = False
        elif env > thr:
            op = True
        t = 1.0 if op else 0.0
        c = ga if t > g else gr
        g = c * g + (1.0 - c) * t
        x[i] *= g
    s[1], s[2], s[3] = env, g, 1.0 if op else 0.0


@njit(cache=True)
def comp(x, n, p, s, mem, sr):
    sus = p[1]
    thr = -12.0 - 36.0 * sus
    slope = 1.0 - 1.0 / (2.0 + 8.0 * sus)
    makeup = -thr * slope * 0.6
    level, blend = p[3], p[4]
    ea, er = _op(p[2], sr), _op(0.2, sr)
    env = s[1]
    for i in range(n):
        a = abs(x[i])
        c = ea if a > env else er
        env = c * env + (1.0 - c) * a
        over = 20.0 * math.log10(env + 1e-9) - thr
        if over <= -3.0:
            gr = 0.0
        elif over < 3.0:
            gr = slope * (over + 3.0) ** 2 / 12.0     # soft knee
        else:
            gr = slope * over
        y = x[i] * 10.0 ** ((makeup - gr) / 20.0) * level
        x[i] += blend * (y - x[i])
    s[1] = env


@njit(cache=True)
def boost(x, n, p, s, mem, sr):
    gain, bass, treb = p[1], p[2], p[3]
    Gl, Gh = _G1(250.0, sr), _G1(2500.0, sr)
    s1, s2 = s[1], s[2]
    for i in range(n):
        v = (x[i] - s1) * Gl
        lo = v + s1
        s1 = lo + v
        v = (x[i] - s2) * Gh
        l2 = v + s2
        s2 = l2 + v
        hi = x[i] - l2
        x[i] = (x[i] + (bass - 1.0) * lo + (treb - 1.0) * hi) * gain
    s[1], s[2] = s1, s2


@njit(cache=True)
def octave(x, n, p, s, mem, sr):
    dry, sub1, sub2, up = p[1], p[2], p[3], p[4]
    gt, g1, g2 = _g(600.0, sr), _g(250.0, sr), _g(160.0, sr)
    ea, er = _op(0.005, sr), _op(0.08, sr)
    Gdc = _G1(60.0, sr)
    if s[5] == 0.0:
        s[5] = 1.0
    if s[6] == 0.0:
        s[6] = 1.0
    t1, t2, env, st, ff1, ff2 = s[1], s[2], s[3], s[4], s[5], s[6]
    a1, a2, b1, b2, dc = s[7], s[8], s[9], s[10], s[11]
    for i in range(n):
        xi = x[i]
        _, tr, t1, t2 = _svf(xi, gt, 1.4, t1, t2)
        a = abs(xi)
        c = ea if a > env else er
        env = c * env + (1.0 - c) * a
        h = env * 0.15 + 1e-4
        if st == 0.0 and tr > h:          # flip-flop divider on rising edges
            st = 1.0
            ff1 = -ff1
            if ff1 > 0.0:
                ff2 = -ff2
        elif st == 1.0 and tr < -h:
            st = 0.0
        _, l1, a1, a2 = _svf(ff1 * env, g1, 1.0, a1, a2)
        _, l2, b1, b2 = _svf(ff2 * env, g2, 1.0, b1, b2)
        v = (a - dc) * Gdc                 # full-wave rectifier -> octave up
        lp = v + dc
        dc = lp + v
        x[i] = dry * xi + 1.5 * (sub1 * l1 + sub2 * l2 + up * (a - lp))
    s[1], s[2], s[3], s[4], s[5], s[6] = t1, t2, env, st, ff1, ff2
    s[7], s[8], s[9], s[10], s[11] = a1, a2, b1, b2, dc


@njit(cache=True)
def wah(x, n, p, s, mem, sr):
    mode = int(p[1] + 0.5)
    fmin = max(p[4], 50.0)
    ratio = max(p[5], fmin * 1.05) / fmin
    k = 1.0 / max(p[3], 0.5)
    pa = _op(0.020 if mode == 0 else 0.006, sr)
    ea, er = _op(0.003, sr), _op(0.15, sr)
    sens = 2.0 * 10.0 ** (p[6] * 2.0)
    inc = TWO_PI * p[7] / sr
    lvl = p[8] * 2.0
    manual = min(1.0, max(0.0, p[2]))
    w1, w2, pos, env, ph = s[1], s[2], s[3], s[4], s[5]
    for i in range(n):
        a = abs(x[i])
        c = ea if a > env else er
        env = c * env + (1.0 - c) * a
        if mode == 0:
            t = manual
        elif mode == 1:
            t = min(1.0, env * sens)
        else:
            ph += inc
            if ph > TWO_PI:
                ph -= TWO_PI
            t = 0.5 - 0.5 * math.cos(ph)
        pos = t + pa * (pos - t)
        bp, _, w1, w2 = _svf(x[i], _g(fmin * ratio ** pos, sr), k, w1, w2)
        x[i] = k * bp * lvl
    s[1], s[2], s[3], s[4], s[5] = w1, w2, pos, env, ph


@njit(cache=True)
def envf(x, n, p, s, mem, sr):
    sens = 2.0 * 10.0 ** (p[1] * 2.0)
    k = 1.0 / max(p[2], 0.5)
    fmin = 180.0
    ratio = max(p[3], 400.0) / fmin
    mode = int(p[4] + 0.5)
    down = p[5] > 0.5
    ea, er, pa = _op(0.002, sr), _op(0.12, sr), _op(0.004, sr)
    f1, f2, env, pos = s[1], s[2], s[3], s[4]
    for i in range(n):
        a = abs(x[i])
        c = ea if a > env else er
        env = c * env + (1.0 - c) * a
        t = min(1.0, env * sens)
        if down:
            t = 1.0 - t
        pos = t + pa * (pos - t)
        bp, lp, f1, f2 = _svf(x[i], _g(fmin * ratio ** pos, sr), k, f1, f2)
        if mode == 0:
            x[i] = lp
        elif mode == 1:
            x[i] = 2.0 * k * bp
        else:
            x[i] = x[i] - k * bp - lp
    s[1], s[2], s[3], s[4] = f1, f2, env, pos


@njit(cache=True)
def swell(x, n, p, s, mem, sr):
    thr = 10.0 ** ((-30.0 - 40.0 * p[1]) / 20.0)
    step = 1.0 / (max(p[2], 0.01) * sr)
    ea, er, gr = _op(0.001, sr), _op(0.03, sr), _op(0.05, sr)
    env, g = s[1], s[2]
    for i in range(n):
        a = abs(x[i])
        c = ea if a > env else er
        env = c * env + (1.0 - c) * a
        if env > thr:
            g = min(1.0, g + step)
        else:
            g *= gr
        x[i] *= g * g        # squared ramp sounds like a volume knob roll-in
    s[1], s[2] = env, g


@njit(cache=True)
def fuzz(x, n, p, s, mem, sr):
    gain, bias, lvl = p[1], p[2], p[4] * 0.4
    Gh, Gdc = _G1(120.0, sr), _G1(15.0, sr)
    gt = _g(400.0 * 20.0 ** p[3], sr)
    dz = bias * 2.0
    hp_s, xp, Fp, dc, t1, t2 = s[1], s[2], s[3], s[4], s[5], s[6]
    for i in range(n):
        v = (x[i] - hp_s) * Gh
        lp = v + hp_s
        hp_s = lp + v
        u = (x[i] - lp) * gain
        au = abs(u) - dz                  # dead zone -> starved, sputtery fuzz
        u = (au if au > 0.0 else 0.0) * (1.0 if u >= 0.0 else -1.0) + bias * 0.5
        y, Fp = _adaa(u, xp, Fp, 0)
        xp = u
        v = (y - dc) * Gdc
        lp = v + dc
        dc = lp + v
        _, lo, t1, t2 = _svf(y - lp, gt, 1.2, t1, t2)
        x[i] = lo * lvl
    s[1], s[2], s[3], s[4], s[5], s[6] = hp_s, xp, Fp, dc, t1, t2


@njit(cache=True)
def od(x, n, p, s, mem, sr):
    drive, lvl = p[1], p[3] * 1.2
    Gh, Gdc = _G1(720.0, sr), _G1(20.0, sr)
    gt = _g(700.0 * 10.0 ** (p[2] * 0.95), sr)
    hp_s, xp, Fp, dc, t1, t2 = s[1], s[2], s[3], s[4], s[5], s[6]
    for i in range(n):
        v = (x[i] - hp_s) * Gh
        lp = v + hp_s
        hp_s = lp + v
        u = (x[i] - lp) * drive + 0.1
        y, Fp = _adaa(u, xp, Fp, 0)
        xp = u
        v = (y - dc) * Gdc
        l2 = v + dc
        dc = l2 + v
        y = 0.5 * x[i] + 0.5 * (y - l2)    # Tube-Screamer style clean+clipped sum
        _, lo, t1, t2 = _svf(y, gt, 1.41, t1, t2)
        x[i] = lo * lvl
    s[1], s[2], s[3], s[4], s[5], s[6] = hp_s, xp, Fp, dc, t1, t2


@njit(cache=True)
def dist(x, n, p, s, mem, sr):
    drive, A, lvl = p[1], p[3], p[4] * 0.22
    Gh, Gdc = _G1(100.0, sr), _G1(20.0, sr)
    gt = _g(800.0 * 10.0 ** p[2], sr)
    gm = _g(750.0, sr)
    km = 1.0 / (0.7 * A)
    hp_s, xp, Fp, dc, t1, t2, m1, m2 = s[1], s[2], s[3], s[4], s[5], s[6], s[7], s[8]
    for i in range(n):
        v = (x[i] - hp_s) * Gh
        lp = v + hp_s
        hp_s = lp + v
        u = (x[i] - lp) * drive + 0.05
        y, Fp = _adaa(u, xp, Fp, 1)
        xp = u
        v = (y - dc) * Gdc
        lp = v + dc
        dc = lp + v
        _, lo, t1, t2 = _svf(y - lp, gt, 1.41, t1, t2)
        bp, _, m1, m2 = _svf(lo, gm, km, m1, m2)
        x[i] = (lo + km * (A * A - 1.0) * bp) * lvl
    s[1], s[2], s[3], s[4], s[5], s[6], s[7], s[8] = hp_s, xp, Fp, dc, t1, t2, m1, m2


# amp models:        clean   crunch  lead    metal   plexi   blackf  chime   modern
AMP_IN_HP = (60.0, 90.0, 150.0, 210.0, 80.0, 70.0, 100.0, 180.0)      # input coupling (tightness)
AMP_GMIN = (1.0, 2.0, 6.0, 12.0, 3.0, 1.0, 2.0, 8.0)
AMP_GMAX = (14.0, 80.0, 500.0, 1400.0, 150.0, 9.0, 45.0, 900.0)
AMP_STAGES = (1, 2, 3, 4, 2, 1, 2, 4)                                  # cascaded triode stages
AMP_SG = (1.0, 5.0, 8.0, 6.0, 6.0, 1.0, 3.5, 6.5)                      # gain between stages
AMP_BIAS = (0.08, 0.15, 0.2, 0.12, 0.12, 0.06, 0.2, 0.1)               # stage asymmetry (even harmonics)
AMP_LP = (7500.0, 6000.0, 5000.0, 4600.0, 6500.0, 8500.0, 8000.0, 5200.0)   # per-stage Miller roll-off
AMP_OUT = (0.22, 0.12, 0.1, 0.09, 0.11, 0.25, 0.13, 0.13)           # roughly level-matched to bypass
# tone stack voicing: corner frequencies of the bass shelf / mid bell / treble shelf (Hz), the fixed
# bass / mid / treble contours (dB, negative = cut) and how soft the power amp is (sag)
AMP_FB = (120.0, 120.0, 120.0, 120.0, 100.0, 100.0, 160.0, 90.0)
AMP_FM = (650.0, 650.0, 650.0, 650.0, 750.0, 500.0, 900.0, 520.0)
AMP_FT = (2800.0, 2800.0, 2800.0, 2800.0, 3200.0, 3500.0, 3800.0, 3000.0)
AMP_MIDC = (0.0, 0.0, 0.0, 0.0, 6.0, -8.0, 3.0, -8.0)
AMP_BASSC = (0.0, 0.0, 0.0, 0.0, -4.0, 1.0, -7.0, 3.0)
AMP_TREBC = (0.0, 0.0, 0.0, 0.0, 2.5, 3.0, 5.0, 2.0)
AMP_SAGK = (0.4, 0.4, 0.4, 0.4, 0.4, 0.2, 0.5, 0.9)
# amp state: 1 input hp, 2..17 four stages x (xp, Fp, coupling, lowpass),
# 20..25 tone stack, 26..27 presence, 28 sag, 29..30 depth


@njit(cache=True)
def amp(x, n, p, s, mem, sr):
    """Tube amp: cascaded asymmetric triode stages -> passive-style tone stack
    (bass shelf, mid bell, treble shelf) -> saggy power amp -> presence."""
    model = min(7, max(0, int(p[1] + 0.5)))
    nst = AMP_STAGES[model]
    G = AMP_GMIN[model] * (AMP_GMAX[model] / AMP_GMIN[model]) ** p[2]
    sg, bias = AMP_SG[model], AMP_BIAS[model]
    sagk = AMP_SAGK[model]
    Ghp, Gcc, Glp = _G1(AMP_IN_HP[model], sr), _G1(25.0, sr), _G1(AMP_LP[model], sr)
    Ab = 10.0 ** ((p[3] - 0.5) * 24.0 / 40.0 + AMP_BASSC[model] / 40.0)
    Am = 10.0 ** ((p[4] - 0.5) * 24.0 / 40.0 + AMP_MIDC[model] / 40.0)
    At = 10.0 ** ((p[5] - 0.5) * 24.0 / 40.0 + AMP_TREBC[model] / 40.0)
    Ap = 10.0 ** (p[6] * 12.0 / 40.0)
    gb, kb = _g(AMP_FB[model], sr) / math.sqrt(Ab), 1.0 / 0.7
    gm, km = _g(AMP_FM[model], sr), 1.0 / (0.8 * Am)
    gt, kt = _g(AMP_FT[model], sr) * math.sqrt(At), 1.0 / 0.7
    gp, kp = _g(4000.0, sr) * math.sqrt(Ap), 1.0 / 0.7
    out = p[7] * AMP_OUT[model]
    Ad = 10.0 ** (p[8] * 12.0 / 40.0)                       # depth: power-amp low resonance
    gd, kd = _g(90.0, sr), 1.0 / (1.0 * Ad)
    ea, er = _op(0.01, sr), _op(0.2, sr)
    hp_s, sag, d1, d2 = s[1], s[28], s[29], s[30]
    b1, b2, m1, m2, t1, t2, q1, q2 = s[20], s[21], s[22], s[23], s[24], s[25], s[26], s[27]
    for i in range(n):
        v = (x[i] - hp_s) * Ghp
        l = v + hp_s
        hp_s = l + v
        u = (x[i] - l) * G
        for k in range(nst):
            b = 2 + 4 * k
            uu = u + bias
            y, Fu = _adaa(uu, s[b], s[b + 1], 0)
            s[b], s[b + 1] = uu, Fu
            v = (y - s[b + 2]) * Gcc          # coupling cap strips the bias DC
            l = v + s[b + 2]
            s[b + 2] = l + v
            y -= l
            v = (y - s[b + 3]) * Glp
            l = v + s[b + 3]
            s[b + 3] = l + v
            u = l * (sg if k < nst - 1 else 1.0)
        bp, lp, b1, b2 = _svf(u, gb, kb, b1, b2)                 # bass: low shelf
        u = u + kb * (Ab - 1.0) * bp + (Ab * Ab - 1.0) * lp
        bp, lp, m1, m2 = _svf(u, gm, km, m1, m2)                 # mid: bell
        u = u + km * (Am * Am - 1.0) * bp
        bp, lp, t1, t2 = _svf(u, gt, kt, t1, t2)                 # treble: high shelf
        u = At * At * u + kt * (1.0 - At) * At * bp + (1.0 - At * At) * lp
        a = abs(u)                                               # power amp sag
        c = ea if a > sag else er
        sag = c * sag + (1.0 - c) * a
        y = math.tanh(1.5 * u / (1.0 + sagk * sag))
        bp, lp, d1, d2 = _svf(y, gd, kd, d1, d2)                 # depth
        y = y + kd * (Ad * Ad - 1.0) * bp
        bp, lp, q1, q2 = _svf(y, gp, kp, q1, q2)                 # presence
        y = Ap * Ap * y + kp * (1.0 - Ap) * Ap * bp + (1.0 - Ap * Ap) * lp
        x[i] = y * out
    s[1], s[28], s[29], s[30] = hp_s, sag, d1, d2
    s[20], s[21], s[22], s[23], s[24], s[25], s[26], s[27] = b1, b2, m1, m2, t1, t2, q1, q2


EQ_FREQS = (100.0, 250.0, 630.0, 1600.0, 4000.0, 8000.0)


@njit(cache=True)
def eq(x, n, p, s, mem, sr):
    for b in range(6):
        A = p[1 + b]
        if abs(A - 1.0) < 1e-4:
            s[1 + 2 * b] = 0.0
            s[2 + 2 * b] = 0.0
            continue
        g = _g(EQ_FREQS[b], sr)
        k = 1.0 / (1.1 * A)
        m = k * (A * A - 1.0)
        c1, c2 = s[1 + 2 * b], s[2 + 2 * b]
        for i in range(n):
            bp, _, c1, c2 = _svf(x[i], g, k, c1, c2)
            x[i] += m * bp
        s[1 + 2 * b], s[2 + 2 * b] = c1, c2
    lvl = p[7]
    for i in range(n):
        x[i] *= lvl


@njit(cache=True)
def pitch(x, n, p, s, mem, sr):
    ratio = 2.0 ** ((p[1] + p[2] / 100.0) / 12.0)     # fractional = whammy glide
    mix = p[3]
    size = len(mem)
    W = 0.05 * sr
    dph = (1.0 - ratio) / W
    w, ph = int(s[1]), s[2]
    for i in range(n):
        mem[w] = x[i]
        ph += dph
        ph -= math.floor(ph)
        ph2 = ph + 0.5
        ph2 -= math.floor(ph2)
        a = math.sin(math.pi * ph)
        b = math.sin(math.pi * ph2)
        y = (_rd(mem, 0, size, w, 2.0 + ph * W) * a * a +
             _rd(mem, 0, size, w, 2.0 + ph2 * W) * b * b)
        w += 1
        if w >= size:
            w = 0
        x[i] += mix * (y - x[i])
    s[1], s[2] = w, ph


@njit(cache=True)
def ring(x, n, p, s, mem, sr):
    inc = TWO_PI * p[1] / sr
    mix = p[2]
    ph = s[1]
    for i in range(n):
        ph += inc
        if ph > TWO_PI:
            ph -= TWO_PI
        x[i] += mix * (x[i] * math.sin(ph) * 1.4 - x[i])
    s[1] = ph


@njit(cache=True)
def crush(x, n, p, s, mem, sr):
    step = 2.0 / 2.0 ** round(p[1])
    ds = max(1, int(round(p[2])))
    mix = p[3]
    cnt, held = s[1], s[2]
    for i in range(n):
        if cnt <= 0.0:
            held = math.floor(x[i] / step + 0.5) * step
            cnt = ds
        cnt -= 1.0
        x[i] += mix * (held - x[i])
    s[1], s[2] = cnt, held


@njit(cache=True)
def phaser(x, n, p, s, mem, sr):
    inc = TWO_PI * p[1] / sr
    depth, fb, mix = p[2], p[3], p[4]
    ph, last = s[1], s[2]
    for i in range(n):
        ph += inc
        if ph > TWO_PI:
            ph -= TWO_PI
        G = _G1(200.0 * 2.0 ** (depth * 4.0 * (0.5 - 0.5 * math.cos(ph))), sr)
        v_in = x[i] + fb * last
        for k in range(6):
            st = s[3 + k]
            v = (v_in - st) * G
            lp = v + st
            s[3 + k] = lp + v
            v_in = 2.0 * lp - v_in
        last = v_in
        x[i] += mix * (v_in - x[i])
    s[1], s[2] = ph, last


UV_FREQS = (180.0, 420.0, 1000.0, 2300.0)


@njit(cache=True)
def univibe(x, n, p, s, mem, sr):
    inc = TWO_PI * p[1] / sr
    inten = p[2]
    vib = p[3] > 0.5
    ph = s[1]
    for i in range(n):
        ph += inc
        if ph > TWO_PI:
            ph -= TWO_PI
        lamp = (0.5 - 0.5 * math.cos(ph)) ** 1.6       # skewed lamp/LDR response
        m = 2.0 ** (inten * 1.8 * lamp)
        v_in = x[i]
        for k in range(4):
            G = _G1(UV_FREQS[k] * m, sr)
            st = s[2 + k]
            v = (v_in - st) * G
            lp = v + st
            s[2 + k] = lp + v
            v_in = 2.0 * lp - v_in
        y = v_in if vib else 0.5 * (x[i] + v_in) * 1.3
        x[i] = y * (1.0 - 0.12 * inten * lamp)
    s[1] = ph


@njit(cache=True)
def trem(x, n, p, s, mem, sr):
    inc = TWO_PI * p[1] / sr
    depth = p[2]
    k = 1.0 + 19.0 * p[3] * p[3]
    nk = 1.0 / math.tanh(k)
    ph = s[1]
    for i in range(n):
        ph += inc
        if ph > TWO_PI:
            ph -= TWO_PI
        lfo = math.tanh(k * math.sin(ph)) * nk
        x[i] *= 1.0 - depth * (0.5 - 0.5 * lfo)
    s[1] = ph


@njit(cache=True)
def vibrato(x, n, p, s, mem, sr):
    inc = TWO_PI * p[1] / sr
    span = p[2] * 0.005 * sr
    size = len(mem)
    w, ph = int(s[1]), s[2]
    for i in range(n):
        mem[w] = x[i]
        ph += inc
        if ph > TWO_PI:
            ph -= TWO_PI
        x[i] = _rd(mem, 0, size, w, 2.0 + span * (0.5 - 0.5 * math.cos(ph)))
        w += 1
        if w >= size:
            w = 0
    s[1], s[2] = w, ph


# --------------------------------------------------------------------------- stereo pedals
# signature: (L, R, n, p, s, mem, sr)

@njit(cache=True)
def chorus(L, R, n, p, s, mem, sr):
    inc = TWO_PI * p[1] / sr
    span = p[2] * 0.008 * sr
    base = 0.007 * sr
    mix = p[3]
    norm = 1.0 / (1.0 + 0.5 * mix)
    size = len(mem)
    w, ph = int(s[1]), s[2]
    for i in range(n):
        mem[w] = 0.5 * (L[i] + R[i])
        ph += inc
        if ph > TWO_PI:
            ph -= TWO_PI
        tl = _rd(mem, 0, size, w, base + span * (0.5 - 0.5 * math.cos(ph)))
        tr = _rd(mem, 0, size, w, base + span * (0.5 - 0.5 * math.cos(ph + 2.1)))
        L[i] = (L[i] + mix * tl) * norm
        R[i] = (R[i] + mix * tr) * norm
        w += 1
        if w >= size:
            w = 0
    s[1], s[2] = w, ph


@njit(cache=True)
def flanger(L, R, n, p, s, mem, sr):
    inc = TWO_PI * p[1] / sr
    span = p[2] * 0.004 * sr
    fb = p[3]
    base = p[4] * 0.001 * sr
    mix = p[5]
    size = len(mem) // 2
    w, ph = int(s[1]), s[2]
    for i in range(n):
        ph += inc
        if ph > TWO_PI:
            ph -= TWO_PI
        dl = 1.0 + base + span * (0.5 - 0.5 * math.cos(ph))
        dr = 1.0 + base + span * (0.5 - 0.5 * math.cos(ph + 1.5708))
        tl = _rd(mem, 0, size, w, dl)
        tr = _rd(mem, size, size, w, dr)
        mem[w] = L[i] + fb * tl
        mem[size + w] = R[i] + fb * tr
        L[i] = (L[i] * (1.0 - mix) + tl * mix) * 1.3
        R[i] = (R[i] * (1.0 - mix) + tr * mix) * 1.3
        w += 1
        if w >= size:
            w = 0
    s[1], s[2] = w, ph


@njit(cache=True)
def rotary(L, R, n, p, s, mem, sr):
    fast = p[1] > 0.5
    drv = p[2]
    bal = p[3]
    mix = p[4]
    gh, gd = min(1.0, 2.0 * bal), min(1.0, 2.0 * (1.0 - bal))
    th = 6.7 if fast else 0.8
    td = 5.8 if fast else 0.65
    ah, ad = _op(0.7, sr), _op(3.0, sr)
    gx = _g(800.0, sr)
    size = len(mem) // 2
    hd, dd = 0.0012 * sr, 0.0006 * sr
    ph, pd, fh, fd, w, c1, c2 = s[1], s[2], s[3], s[4], int(s[5]), s[6], s[7]
    for i in range(n):
        fh = th + ah * (fh - th)
        fd = td + ad * (fd - td)
        ph += TWO_PI * fh / sr
        pd += TWO_PI * fd / sr
        if ph > TWO_PI:
            ph -= TWO_PI
        if pd > TWO_PI:
            pd -= TWO_PI
        m = 0.5 * (L[i] + R[i])
        if drv > 0.0:
            m = math.tanh(m * (1.0 + 8.0 * drv)) / (1.0 + 2.0 * drv)
        bp, lo, c1, c2 = _svf(m, gx, 1.41, c1, c2)
        mem[w] = m - 1.41 * bp - lo         # horn gets the highs
        mem[size + w] = lo                  # drum gets the lows
        hl = _rd(mem, 0, size, w, 2.0 + hd * (1.0 + 0.6 * math.sin(ph)))
        hr = _rd(mem, 0, size, w, 2.0 + hd * (1.0 + 0.6 * math.cos(ph)))
        dl = _rd(mem, size, size, w, 2.0 + dd * (1.0 + 0.3 * math.sin(pd)))
        dr = _rd(mem, size, size, w, 2.0 + dd * (1.0 + 0.3 * math.cos(pd)))
        ol = gh * hl * (0.65 + 0.35 * math.cos(ph)) + gd * dl * (0.85 + 0.15 * math.cos(pd))
        orr = gh * hr * (0.65 - 0.35 * math.sin(ph)) + gd * dr * (0.85 - 0.15 * math.sin(pd))
        L[i] += mix * (ol * 1.2 - L[i])
        R[i] += mix * (orr * 1.2 - R[i])
        w += 1
        if w >= size:
            w = 0
    s[1], s[2], s[3], s[4], s[5], s[6], s[7] = ph, pd, fh, fd, w, c1, c2


@njit(cache=True)
def pan(L, R, n, p, s, mem, sr):
    inc = TWO_PI * p[1] / sr
    depth = p[2]
    ph = s[1]
    for i in range(n):
        ph += inc
        if ph > TWO_PI:
            ph -= TWO_PI
        ang = (depth * math.sin(ph) + 1.0) * 0.25 * math.pi
        L[i] *= math.cos(ang) * 1.41421356
        R[i] *= math.sin(ang) * 1.41421356
    s[1] = ph


@njit(cache=True)
def _idle(on, s, slot, n, sr, mem):
    """Tails bookkeeping: returns True when the pedal can be skipped entirely."""
    if on:
        s[slot] = 0.0
        return False
    if s[slot] > 15.0 * sr:
        return True
    s[slot] += n
    if s[slot] > 15.0 * sr:
        mem[:] = 0.0                       # tail long gone - clear for next use
        return True
    return False


@njit(cache=True)
def delay(L, R, n, p, s, mem, sr):
    on = p[0] > 0.5
    if _idle(on, s, 7, n, sr, mem):
        return
    size = len(mem) // 2
    tgt = min(p[1] * sr, size - 8.0)
    fb, mix, mode = p[2], p[3], int(p[5] + 0.5)
    analog = mode == 1
    fc = 1000.0 * 12.0 ** p[4]
    if analog:
        fc *= 0.5
    Gl = _G1(fc, sr)
    at, ax = _op(0.15, sr), _op(0.01, sr)
    minc = TWO_PI * 0.4 / sr
    send_t = 1.0 if on else 0.0
    w, dsm, send, l1, l2, mph = int(s[1]), s[2], s[3], s[4], s[5], s[6]
    if dsm == 0.0:
        dsm = tgt
    for i in range(n):
        dsm = tgt + at * (dsm - tgt)
        d = dsm
        if analog:
            mph += minc
            if mph > TWO_PI:
                mph -= TWO_PI
            d += 0.0006 * sr * math.sin(mph)
        wl = _rd(mem, 0, size, w, d)
        wr = _rd(mem, size, size, w, d)
        v = (wl - l1) * Gl
        fl = v + l1
        l1 = fl + v
        v = (wr - l2) * Gl
        fr = v + l2
        l2 = fr + v
        if analog:
            fl = math.tanh(fl)
            fr = math.tanh(fr)
        send = send_t + ax * (send - send_t)
        inp = 0.5 * (L[i] + R[i]) * send
        if mode == 2:                        # ping-pong
            mem[w] = inp + fb * fr
            mem[size + w] = fb * fl
        else:
            mem[w] = inp + fb * fl
            mem[size + w] = inp + fb * fr
        L[i] += mix * wl
        R[i] += mix * wr
        w += 1
        if w >= size:
            w = 0
    s[1], s[2], s[3], s[4], s[5], s[6] = w, dsm, send, l1, l2, mph


RV_LINES = (1123.0, 1327.0, 1559.0, 1801.0, 2081.0, 2357.0, 2621.0, 2957.0)
RV_AP = (142.0, 107.0, 379.0, 277.0)
RV_SIGN = (1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0)


@njit(cache=True)
def reverb(L, R, n, p, s, mem, sr):
    """8-line feedback delay network with input diffusion and damping."""
    on = p[0] > 0.5
    if _idle(on, s, 8, n, sr, mem):
        return
    pre, ap, ln = rv_sizes(sr)
    mode = int(p[5] + 0.5)
    scale = (0.45, 1.0, 0.7)[mode] * sr / 48000.0
    gap = 0.75 if mode == 2 else 0.65
    t60 = max(p[1], 0.1)
    mix = p[3]
    pd = min(p[4] * sr, pre - 2.0)
    damp = math.exp(-TWO_PI * 1500.0 * 8.0 ** p[2] / sr)
    ax = _op(0.01, sr)
    send_t = 1.0 if on else 0.0
    o_ap = pre
    o_ln = pre + 4 * ap
    lens = np.empty(8)
    gains = np.empty(8)
    for j in range(8):
        lens[j] = min(RV_LINES[j] * scale, ln - 2.0)
        gains[j] = 10.0 ** (-3.0 * lens[j] / (sr * t60))
    apl = np.empty(4)
    for j in range(4):
        apl[j] = min(RV_AP[j] * scale, ap - 2.0)
    outs = np.empty(8)
    wp, wa, wl, send = int(s[1]), int(s[2]), int(s[3]), s[4]
    for i in range(n):
        send = send_t + ax * (send - send_t)
        mem[wp] = 0.5 * (L[i] + R[i]) * send
        xin = _rd(mem, 0, pre, wp, pd)
        for j in range(4):                       # Schroeder allpass diffusers
            off = o_ap + j * ap
            v = _rd(mem, off, ap, wa, apl[j])
            y = -gap * xin + v
            mem[off + wa] = xin + gap * y
            xin = y
        tot = 0.0
        for j in range(8):
            o = _rd(mem, o_ln + j * ln, ln, wl, lens[j])
            lp = (1.0 - damp) * o + damp * s[10 + j]
            s[10 + j] = lp
            outs[j] = lp * gains[j]
            tot += outs[j]
        tot *= 0.25                              # Householder: 2/N
        for j in range(8):
            mem[o_ln + j * ln + wl] = outs[j] - tot + xin * RV_SIGN[j]
        wetl = outs[0] - outs[2] + outs[4] - outs[6] + 0.5 * (outs[1] + outs[5])
        wetr = outs[1] - outs[3] + outs[5] - outs[7] + 0.5 * (outs[2] + outs[6])
        L[i] += mix * wetl * 0.8
        R[i] += mix * wetr * 0.8
        wp += 1
        if wp >= pre:
            wp = 0
        wa += 1
        if wa >= ap:
            wa = 0
        wl += 1
        if wl >= ln:
            wl = 0
    s[1], s[2], s[3], s[4] = wp, wa, wl, send


@njit(cache=True)
def looper(L, R, n, p, s, mem, sr):
    """Commands (p[1]): 0 stop, 1 record, 2 play, 3 overdub. p[3] bumps = clear.
    s: 1 length, 2 pos, 3 last cmd, 4 last clear, 5 has loop, 6 effective mode."""
    size = len(mem) // 2
    cmd = int(p[1] + 0.5)
    lvl = p[2]
    length, pos, last, has, eff = int(s[1]), int(s[2]), int(s[3]), s[5] > 0.5, int(s[6])
    if p[3] != s[4]:
        s[4] = p[3]
        length, pos, has, eff = 0, 0, False, 0
        last = cmd
    if cmd != last:
        if eff == 1 and not has:                 # closing the first recording
            length = max(pos, 1)
            has = True
            pos = 0
        if cmd == 1:
            eff = 3 if has else 1
            if not has:
                pos = 0
        else:
            eff = cmd if has else 0
        last = cmd
    if eff != 0:
        for i in range(n):
            if eff == 1:
                mem[pos] = L[i]
                mem[size + pos] = R[i]
                pos += 1
                if pos >= size:                  # memory full: close the loop
                    length, has, pos, eff = size, True, 0, 2
                    break
            else:
                pl, pr = mem[pos], mem[size + pos]
                if eff == 3:
                    mem[pos] = pl * 0.98 + L[i]
                    mem[size + pos] = pr * 0.98 + R[i]
                L[i] += pl * lvl
                R[i] += pr * lvl
                pos += 1
                if pos >= length:
                    pos = 0
    s[1], s[2], s[3], s[5], s[6] = length, pos, last, 1.0 if has else 0.0, eff


# --------------------------------------------------------------------------- metal pack

@njit(cache=True)
def _bell(x, g, k, A, c1, c2):
    """SVF peaking EQ; k must be 1/(Q*A)."""
    bp, _, c1, c2 = _svf(x, g, k, c1, c2)
    return x + k * (A * A - 1.0) * bp, c1, c2


@njit(cache=True)
def _lshelf(x, g, k, A, c1, c2):
    """SVF low shelf; g must be tan(pi fc/sr)/sqrt(A)."""
    bp, lp, c1, c2 = _svf(x, g, k, c1, c2)
    return x + k * (A - 1.0) * bp + (A * A - 1.0) * lp, c1, c2


@njit(cache=True)
def _hshelf(x, g, k, A, c1, c2):
    """SVF high shelf; g must be tan(pi fc/sr)*sqrt(A)."""
    bp, lp, c1, c2 = _svf(x, g, k, c1, c2)
    return A * A * x + k * (1.0 - A) * A * bp + (1.0 - A * A) * lp, c1, c2


@njit(cache=True)
def mgate(x, n, p, s, mem, sr):
    """Decimator-style gate. run_chain copies the clean guitar block into mem, so the
    detector hears your picking while the gain is applied wherever this pedal sits
    (after the amp) - tight stops without choking sustained notes."""
    thr = p[1]
    ea, er = _op(0.0002, sr), _op(0.012, sr)
    ga, gr = _op(0.0003, sr), _op(p[2], sr)
    hold_n = 0.02 * sr
    env, g, op, hold = s[1], s[2], s[3] > 0.5, s[4]
    for i in range(n):
        a = abs(mem[i])
        c = ea if a > env else er
        env = c * env + (1.0 - c) * a
        if env > thr:
            op = True
            hold = hold_n
        elif op:
            if env < thr * 0.6:
                hold -= 1.0
                if hold <= 0.0:
                    op = False
            else:
                hold = hold_n
        t = 1.0 if op else 0.0
        c = ga if t > g else gr
        g = c * g + (1.0 - c) * t
        x[i] *= g
    s[1], s[2], s[3], s[4] = env, g, 1.0 if op else 0.0, hold


@njit(cache=True)
def drop(x, n, p, s, mem, sr):
    """Drop tuner: dual-grain delay-line pitch shifter, fully wet by default.
    TIGHT uses short grains (less delay), SMOOTH longer ones (less warble on chords)."""
    ratio = 2.0 ** (p[1] / 12.0)
    mix = p[2]
    W = (0.022 if p[3] < 0.5 else 0.045) * sr
    size = len(mem)
    dph = (1.0 - ratio) / W
    w, ph = int(s[1]), s[2]
    for i in range(n):
        mem[w] = x[i]
        ph += dph
        ph -= math.floor(ph)
        ph2 = ph + 0.5
        ph2 -= math.floor(ph2)
        a = math.sin(math.pi * ph)
        b = math.sin(math.pi * ph2)
        y = (_rd(mem, 0, size, w, 2.0 + ph * W) * a * a +
             _rd(mem, 0, size, w, 2.0 + ph2 * W) * b * b)
        w += 1
        if w >= size:
            w = 0
        x[i] += mix * (y - x[i])
    s[1], s[2] = w, ph


@njit(cache=True)
def hm2(x, n, p, s, mem, sr):
    """'Swedish chainsaw' (HM-2 style): two clipping stages, then big resonant
    peaks at ~95 Hz and ~1.35 kHz. Everything on full = the classic buzzsaw."""
    gain = 10.0 ** ((15.0 + 40.0 * p[1]) / 20.0)
    Al = 10.0 ** (p[2] * 18.0 / 40.0)
    Ah = 10.0 ** (p[3] * 18.0 / 40.0)
    As = 10.0 ** (-6.0 / 40.0)
    lvl = p[4] * 0.045
    Gh, Gdc = _G1(70.0, sr), _G1(15.0, sr)
    gl, kl = _g(95.0, sr), 1.0 / (0.9 * Al)
    gh, kh = _g(1350.0, sr), 1.0 / (1.4 * Ah)
    gs, ks = _g(450.0, sr), 1.0 / (0.8 * As)
    glp = _g(7000.0, sr)
    hp_s, xp1, Fp1, dc1, xp2, Fp2, dc2 = s[1], s[2], s[3], s[4], s[5], s[6], s[7]
    l1, l2, h1, h2, f1, f2, c1, c2 = s[8], s[9], s[10], s[11], s[12], s[13], s[14], s[15]
    for i in range(n):
        v = (x[i] - hp_s) * Gh
        lp = v + hp_s
        hp_s = lp + v
        u = (x[i] - lp) * gain
        y, Fp1 = _adaa(u, xp1, Fp1, 0)
        xp1 = u
        v = (y - dc1) * Gdc
        lp = v + dc1
        dc1 = lp + v
        u = (y - lp) * 6.0
        y, Fp2 = _adaa(u, xp2, Fp2, 1)
        xp2 = u
        v = (y - dc2) * Gdc
        lp = v + dc2
        dc2 = lp + v
        y -= lp
        y, l1, l2 = _bell(y, gl, kl, Al, l1, l2)
        y, h1, h2 = _bell(y, gh, kh, Ah, h1, h2)
        y, c1, c2 = _bell(y, gs, ks, As, c1, c2)
        _, y, f1, f2 = _svf(y, glp, 1.2, f1, f2)
        x[i] = y * lvl
    s[1], s[2], s[3], s[4], s[5], s[6], s[7] = hp_s, xp1, Fp1, dc1, xp2, Fp2, dc2
    s[8], s[9], s[10], s[11], s[12], s[13], s[14], s[15] = l1, l2, h1, h2, f1, f2, c1, c2


@njit(cache=True)
def mzone(x, n, p, s, mem, sr):
    """'Metal Core' (Metal Zone style): mid-pushed two-stage hard clipping, then a
    3-band EQ with a sweepable middle."""
    gain = 10.0 ** ((10.0 + 50.0 * p[1]) / 20.0)
    Al, Ah, Am = 10.0 ** (p[2] / 40.0), 10.0 ** (p[3] / 40.0), 10.0 ** (p[4] / 40.0)
    lvl = p[6] * 0.15
    Gh, Gdc = _G1(100.0, sr), _G1(15.0, sr)
    Ap = 10.0 ** (10.0 / 40.0)
    gp, kp = _g(1000.0, sr), 1.0 / (0.8 * Ap)
    glp = _g(6000.0, sr)
    gls, kls = _g(100.0, sr) / math.sqrt(Al), 1.0 / 0.7
    ghs, khs = _g(3500.0, sr) * math.sqrt(Ah), 1.0 / 0.7
    gm, km = _g(p[5], sr), 1.0 / (1.2 * Am)
    hp_s, p1, p2, xp1, Fp1, dc1, xp2, Fp2, dc2 = s[1], s[2], s[3], s[4], s[5], s[6], s[7], s[8], s[9]
    f1, f2, a1, a2, b1, b2, m1, m2 = s[10], s[11], s[12], s[13], s[14], s[15], s[16], s[17]
    for i in range(n):
        v = (x[i] - hp_s) * Gh
        lp = v + hp_s
        hp_s = lp + v
        y, p1, p2 = _bell(x[i] - lp, gp, kp, Ap, p1, p2)
        u = y * gain
        y, Fp1 = _adaa(u, xp1, Fp1, 1)
        xp1 = u
        v = (y - dc1) * Gdc
        lp = v + dc1
        dc1 = lp + v
        u = (y - lp) * 8.0
        y, Fp2 = _adaa(u, xp2, Fp2, 1)
        xp2 = u
        v = (y - dc2) * Gdc
        lp = v + dc2
        dc2 = lp + v
        y -= lp
        _, y, f1, f2 = _svf(y, glp, 1.2, f1, f2)
        y, a1, a2 = _lshelf(y, gls, kls, Al, a1, a2)
        y, b1, b2 = _hshelf(y, ghs, khs, Ah, b1, b2)
        y, m1, m2 = _bell(y, gm, km, Am, m1, m2)
        x[i] = y * lvl
    s[1], s[2], s[3], s[4], s[5], s[6], s[7], s[8], s[9] = hp_s, p1, p2, xp1, Fp1, dc1, xp2, Fp2, dc2
    s[10], s[11], s[12], s[13], s[14], s[15], s[16], s[17] = f1, f2, a1, a2, b1, b2, m1, m2


@njit(cache=True)
def tboost(x, n, p, s, mem, sr):
    """Tight boost: cuts the low end before the amp so palm mutes stay tight."""
    gh = _g(p[1], sr)
    gain = p[2]
    At = p[3]
    gt, kt = _g(2500.0, sr) * math.sqrt(At), 1.0 / 0.7
    h1, h2, t1, t2 = s[1], s[2], s[3], s[4]
    for i in range(n):
        bp, lp, h1, h2 = _svf(x[i], gh, 1.414, h1, h2)
        y = (x[i] - 1.414 * bp - lp) * gain
        y, t1, t2 = _hshelf(y, gt, kt, At, t1, t2)
        x[i] = y
    s[1], s[2], s[3], s[4] = h1, h2, t1, t2


@njit(cache=True)
def cut(x, n, p, s, mem, sr):
    """High-pass + low-pass filter, 12 or 24 dB/oct: trims flub below and fizz above."""
    gh, gl = _g(p[1], sr), _g(p[2], sr)
    steep = p[3] > 0.5
    k1 = 1.848 if steep else 1.414     # 4th-order Butterworth = two sections, Q 0.541 and 1.307
    k2 = 0.765
    h1, h2, h3, h4, l1, l2, l3, l4 = s[1], s[2], s[3], s[4], s[5], s[6], s[7], s[8]
    for i in range(n):
        bp, lp, h1, h2 = _svf(x[i], gh, k1, h1, h2)
        v = x[i] - k1 * bp - lp
        if steep:
            bp, lp, h3, h4 = _svf(v, gh, k2, h3, h4)
            v = v - k2 * bp - lp
        bp, lp, l1, l2 = _svf(v, gl, k1, l1, l2)
        v = lp
        if steep:
            bp, lp, l3, l4 = _svf(v, gl, k2, l3, l4)
            v = lp
        x[i] = v
    s[1], s[2], s[3], s[4], s[5], s[6], s[7], s[8] = h1, h2, h3, h4, l1, l2, l3, l4


@njit(cache=True)
def doubler(L, R, n, p, s, mem, sr):
    """Fake double-tracking: two slightly different, slowly drifting takes panned apart."""
    base = max(p[1] * sr, 0.006 * sr)
    var = p[2]
    ga, gb = 0.5 * (1.0 + p[3]), 0.5 * (1.0 - p[3])
    size = len(mem)
    i1, i2 = TWO_PI * 0.37 / sr, TWO_PI * 0.83 / sr
    i3, i4 = TWO_PI * 0.29 / sr, TWO_PI * 0.61 / sr
    w, a1, a2, a3, a4 = int(s[1]), s[2], s[3], s[4], s[5]
    for i in range(n):
        mem[w] = 0.5 * (L[i] + R[i])
        a1 += i1
        a2 += i2
        a3 += i3
        a4 += i4
        if a1 > TWO_PI:
            a1 -= TWO_PI
        if a2 > TWO_PI:
            a2 -= TWO_PI
        if a3 > TWO_PI:
            a3 -= TWO_PI
        if a4 > TWO_PI:
            a4 -= TWO_PI
        m1 = var * (0.6 * math.sin(a1) + 0.4 * math.sin(a2))
        m2 = var * (0.6 * math.sin(a3) + 0.4 * math.sin(a4))
        va = _rd(mem, 0, size, w, 2.0 + (0.0015 + 0.001 * m1) * sr)
        vb = _rd(mem, 0, size, w, base + 0.0025 * m2 * sr)
        L[i] = ga * va + gb * vb
        R[i] = gb * va + ga * vb
        w += 1
        if w >= size:
            w = 0
    s[1], s[2], s[3], s[4], s[5] = w, a1, a2, a3, a4


# 16-step patterns: CLICK, ROCK, METAL (double kick), GALLOP, BLAST
DR_KICK = np.array([
    [0] * 16,
    [1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0],
    [1] * 16,
    [1, 0, 1, 1] * 4,
    [1, 0] * 8], dtype=np.float64)
DR_SNARE = np.array([
    [0] * 16,
    [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
    [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
    [0, 1] * 8], dtype=np.float64)
DR_HAT = np.array([
    [0] * 16,
    [1, 0, 0.6, 0] * 4,
    [1, 0, 0, 0] * 4,
    [1, 0, 0, 0] * 4,
    [0.7, 0] * 8], dtype=np.float64)
DR_CLICK = np.array([
    [2, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0],
    [0] * 16, [0] * 16, [0] * 16, [0] * 16], dtype=np.float64)


@njit(cache=True)
def drums(L, R, n, p, s, mem, sr):
    """Synthesised drum machine / metronome, mixed into the signal."""
    if p[0] < 0.5:
        s[1], s[2], s[S_DRUM_STEP] = 0.0, -1.0, -1.0
        return
    pat = min(4, max(0, int(p[2] + 0.5)))
    steplen = 60.0 / max(p[1], 20.0) / 4.0 * sr
    vol = p[3]
    tight = pat >= 2
    kdec = _op(0.09 if tight else 0.25, sr)
    fdec, kcd = _op(0.03, sr), _op(0.004, sr)
    sdec, stdec, hdec, cdec = _op(0.13, sr), _op(0.06, sr), _op(0.035, sr), _op(0.025, sr)
    gbp, ghh = _g(2800.0, sr), _g(7000.0, sr)
    cnt, step = s[1], int(s[2])
    kph, kenv, kf, kcl = s[3], s[4], s[5], s[6]
    senv, sten, sph, henv = s[7], s[8], s[9], s[10]
    cenv, cf, cph = s[11], s[12], s[13]
    seed = int(s[14])
    b1, b2, h1, h2 = s[15], s[16], s[17], s[18]
    for i in range(n):
        cnt -= 1.0
        if cnt <= 0.0:
            cnt += steplen
            step = (step + 1) % 16
            if DR_KICK[pat, step] > 0.0:
                kenv, kf, kcl, kph = 1.0, 160.0, 1.0, 0.0
            if DR_SNARE[pat, step] > 0.0:
                senv, sten = 1.0, 1.0
            if DR_HAT[pat, step] > 0.0:
                henv = DR_HAT[pat, step]
            cl = DR_CLICK[pat, step]
            if cl > 0.0:
                cenv = 1.0
                cf = 1600.0 if cl > 1.5 else 1000.0
        seed = (seed * 1664525 + 1013904223) & 0xFFFFFFFF
        nz = seed / 2147483648.0 - 1.0
        kf = 48.0 + fdec * (kf - 48.0)
        kph += TWO_PI * kf / sr
        if kph > TWO_PI:
            kph -= TWO_PI
        kick = math.sin(kph) * kenv + nz * kcl * 0.3
        kenv *= kdec
        kcl *= kcd
        bp, _, b1, b2 = _svf(nz, gbp, 1.4, b1, b2)
        sph += TWO_PI * 190.0 / sr
        if sph > TWO_PI:
            sph -= TWO_PI
        snare = bp * senv * 1.5 + math.sin(sph) * sten * 0.6
        senv *= sdec
        sten *= stdec
        bp, lp, h1, h2 = _svf(nz, ghh, 1.0, h1, h2)
        hat = (nz - bp - lp) * henv
        henv *= hdec
        cph += TWO_PI * cf / sr
        if cph > TWO_PI:
            cph -= TWO_PI
        click = math.sin(cph) * cenv
        cenv *= cdec
        out = vol * (0.8 * kick + 0.45 * snare + 0.18 * hat + 0.4 * click)
        L[i] += out
        R[i] += out
    s[1], s[2], s[S_DRUM_STEP] = cnt, step, step
    s[3], s[4], s[5], s[6] = kph, kenv, kf, kcl
    s[7], s[8], s[9], s[10] = senv, sten, sph, henv
    s[11], s[12], s[13], s[14] = cenv, cf, cph, seed
    s[15], s[16], s[17], s[18] = b1, b2, h1, h2


# --------------------------------------------------------------------------- chain

@njit(cache=True)
def _mono(t, x, n, p, s, mem, sr):
    if t == T_GATE:
        gate(x, n, p, s, mem, sr)
    elif t == T_COMP:
        comp(x, n, p, s, mem, sr)
    elif t == T_BOOST:
        boost(x, n, p, s, mem, sr)
    elif t == T_OCTAVE:
        octave(x, n, p, s, mem, sr)
    elif t == T_WAH:
        wah(x, n, p, s, mem, sr)
    elif t == T_ENVF:
        envf(x, n, p, s, mem, sr)
    elif t == T_SWELL:
        swell(x, n, p, s, mem, sr)
    elif t == T_FUZZ:
        fuzz(x, n, p, s, mem, sr)
    elif t == T_OD:
        od(x, n, p, s, mem, sr)
    elif t == T_DIST:
        dist(x, n, p, s, mem, sr)
    elif t == T_EQ:
        eq(x, n, p, s, mem, sr)
    elif t == T_PITCH:
        pitch(x, n, p, s, mem, sr)
    elif t == T_RING:
        ring(x, n, p, s, mem, sr)
    elif t == T_CRUSH:
        crush(x, n, p, s, mem, sr)
    elif t == T_PHASER:
        phaser(x, n, p, s, mem, sr)
    elif t == T_UNIVIBE:
        univibe(x, n, p, s, mem, sr)
    elif t == T_TREM:
        trem(x, n, p, s, mem, sr)
    elif t == T_VIBRATO:
        vibrato(x, n, p, s, mem, sr)
    elif t == T_AMP:
        amp(x, n, p, s, mem, sr)
    elif t == T_MGATE:
        mgate(x, n, p, s, mem, sr)
    elif t == T_DROP:
        drop(x, n, p, s, mem, sr)
    elif t == T_HM2:
        hm2(x, n, p, s, mem, sr)
    elif t == T_MZONE:
        mzone(x, n, p, s, mem, sr)
    elif t == T_TBOOST:
        tboost(x, n, p, s, mem, sr)
    elif t == T_CUT:
        cut(x, n, p, s, mem, sr)


@njit(cache=True)
def _stereo(t, L, R, n, p, s, mem, sr):
    if t == T_CHORUS:
        chorus(L, R, n, p, s, mem, sr)
    elif t == T_FLANGER:
        flanger(L, R, n, p, s, mem, sr)
    elif t == T_ROTARY:
        rotary(L, R, n, p, s, mem, sr)
    elif t == T_PAN:
        pan(L, R, n, p, s, mem, sr)
    elif t == T_DELAY:
        delay(L, R, n, p, s, mem, sr)
    elif t == T_REVERB:
        reverb(L, R, n, p, s, mem, sr)
    elif t == T_LOOPER:
        looper(L, R, n, p, s, mem, sr)
    elif t == T_DOUBLER:
        doubler(L, R, n, p, s, mem, sr)
    elif t == T_DRUMS:
        drums(L, R, n, p, s, mem, sr)


@njit(cache=True)
def _cab(x, n, on, st, sr):
    """Rough 1x12 speaker cabinet. st: [mix, 8 filter states]."""
    g1, g2, g3, g4 = _g(80.0, sr), _g(110.0, sr), _g(4000.0, sr), _g(5500.0, sr)
    k1, k2, k3, k4 = 1.0 / 0.707, 1.0 / 1.5, 1.0 / 0.9, 1.0 / 0.6
    ax = _op(0.01, sr)
    tgt = 1.0 if on else 0.0
    mix = st[0]
    if not on and mix < 1e-5:
        st[0] = 0.0
        return
    c1, c2, c3, c4, c5, c6, c7, c8 = st[1], st[2], st[3], st[4], st[5], st[6], st[7], st[8]
    for i in range(n):
        xi = x[i]
        bp, lp, c1, c2 = _svf(xi, g1, k1, c1, c2)
        h = xi - k1 * bp - lp
        bp, lp, c3, c4 = _svf(h, g2, k2, c3, c4)
        h += 0.5 * k2 * bp
        _, h, c5, c6 = _svf(h, g3, k3, c5, c6)
        _, h, c7, c8 = _svf(h, g4, k4, c7, c8)
        mix = tgt + ax * (mix - tgt)
        x[i] = xi + mix * (h - xi)
    st[0], st[1], st[2], st[3], st[4], st[5], st[6], st[7], st[8] = mix, c1, c2, c3, c4, c5, c6, c7, c8


@njit(cache=True, fastmath=True)
def _fir(x, n, hrev, ln, hist, M, w):
    """Direct-form convolution with a time-reversed IR. hist holds every sample
    twice (at w and w+M) so the last ln samples are always one contiguous run."""
    for i in range(n):
        hist[w] = x[i]
        hist[w + M] = x[i]
        base = w + M - ln + 1
        acc = 0.0
        for k in range(ln):
            acc += hrev[k] * hist[base + k]
        x[i] = acc
        w += 1
        if w >= M:
            w = 0
    return w


@njit(cache=True)
def _cab_stage(L, R, n, stereo, G, GS, IR, HIST, sr):
    """The speaker cabinet: OFF, the basic filter cab, or the loaded impulse response."""
    cab_mode = int(G[G_CAB] + 0.5)
    irlen = int(G[G_IR_LEN])
    M = len(HIST) // 4
    if cab_mode == 2 and 0 < irlen <= M:
        w = int(GS[GS_IR_W])
        w2 = _fir(L, n, IR, irlen, HIST[0:2 * M], M, w)
        if stereo:
            _fir(R, n, IR, irlen, HIST[2 * M:4 * M], M, w)
        else:
            R[:n] = L[:n]
        GS[GS_IR_W] = w2
    else:
        cab_on = cab_mode >= 1          # IR mode without an IR falls back to the basic cab
        _cab(L, n, cab_on, GS[GS_CAB_L:GS_CAB_L + 9], sr)
        if stereo:
            _cab(R, n, cab_on, GS[GS_CAB_R:GS_CAB_R + 9], sr)
        else:
            R[:n] = L[:n]


@njit(cache=True, nogil=True)     # releases the GIL so the UI can't stall the DSP
def run_chain(L, R, n, order, nord, P, S, MEM, MEMOFF, MEMLEN, G, GS, dryL, dryR, wasst,
              IR, HIST, sr):
    """Process one block. L holds the mono input on entry; L/R hold the output on exit."""
    gain = G[G_IN_GAIN]
    pk = GS[GS_PEAK_IN]
    for i in range(n):
        a = abs(L[i])
        if a > pk:
            pk = a
        L[i] *= gain
    GS[GS_PEAK_IN] = pk
    ko, kl = MEMOFF[T_MGATE], MEMLEN[T_MGATE]       # clean-guitar key for the metal gate
    if n <= kl:
        MEM[ko:ko + n] = L[:n]
        MEM[ko + kl:ko + kl + n] = L[:n]

    ax = _op(0.01, sr)
    stereo = False
    cab_at = nord                      # the cabinet runs just before this slot (nord = after the last)
    if G[G_CABPOS] > 0.5:
        for j in range(nord):
            if order[j] == T_AMP:
                cab_at = j + 1
    cab_done = False
    for j in range(nord):
        if j == cab_at:
            _cab_stage(L, R, n, stereo, G, GS, IR, HIST, sr)
            cab_done = True
        t = order[j]
        p = P[t * PST:(t + 1) * PST]
        sb = t * 2 * SST
        sL = S[sb:sb + SST]
        sR = S[sb + SST:sb + 2 * SST]
        mo, ml = MEMOFF[t], MEMLEN[t]
        kind = KIND[t]
        if kind == 2:
            if not stereo:
                R[:n] = L[:n]
                stereo = True
            _stereo(t, L, R, n, p, sL, MEM[mo:mo + ml], sr)
            continue
        on = p[0] > 0.5
        mix = sL[0]
        if not on and mix < 1e-5:
            sL[0] = 0.0
            wasst[t] = 0
            continue
        tgt = 1.0 if on else 0.0
        if kind == 1:
            if not stereo:
                R[:n] = L[:n]
                stereo = True
            dryL[:n] = L[:n]
            dryR[:n] = R[:n]
            _stereo(t, L, R, n, p, sL, MEM[mo:mo + ml], sr)
        else:
            memL = MEM[mo:mo + ml]
            memR = MEM[mo + ml:mo + 2 * ml]
            dryL[:n] = L[:n]
            _mono(t, L, n, p, sL, memL, sr)
            if stereo:
                if wasst[t] == 0:                 # first stereo block: clone L state
                    sR[:] = sL[:]
                    memR[:] = memL[:]
                    wasst[t] = 1
                dryR[:n] = R[:n]
                _mono(t, R, n, p, sR, memR, sr)
            else:
                wasst[t] = 0
        for i in range(n):
            mix = tgt + ax * (mix - tgt)
            L[i] = dryL[i] + mix * (L[i] - dryL[i])
            if stereo:
                R[i] = dryR[i] + mix * (R[i] - dryR[i])
        sL[0] = mix

    if not cab_done:
        _cab_stage(L, R, n, stereo, G, GS, IR, HIST, sr)
    if not stereo:
        R[:n] = L[:n]

    mt = 0.0 if G[G_MUTE] > 0.5 else G[G_MASTER]
    m = GS[GS_MASTER]
    am = _op(0.005, sr)
    po, clips = GS[GS_PEAK_OUT], GS[GS_CLIPS]
    for i in range(n):
        m = mt + am * (m - mt)
        l = L[i] * m
        r = R[i] * m
        if abs(l) > 1.0 or abs(r) > 1.0:
            clips += 1.0
            l = min(1.0, max(-1.0, l))
            r = min(1.0, max(-1.0, r))
        a = max(abs(l), abs(r))
        if a > po:
            po = a
        L[i] = l
        R[i] = r
    GS[GS_MASTER], GS[GS_PEAK_OUT], GS[GS_CLIPS] = m, po, clips

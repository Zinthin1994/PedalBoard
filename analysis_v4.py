"""Signal analysis for PedalBoard v4: spectra, per-block metering, signal-flow rules, tone matching.

Everything here runs off the audio thread. A `Probe` is a second, stream-less AudioEngine that renders
a test signal through a copy of the board, so the app can measure what each block does without
touching the live audio.
"""
import copy
import math
import os

import numpy as np

import dsp_v2 as D
import irlib_v4 as IRL
from pedals_v2 import BY_KEY

FLOOR_DB = -120.0
BLOCK = 512

# ------------------------------------------------------------------------------------ test signals


def _pluck(freq, dur, sr, damp=0.996, amp=0.3, seed=0):
    """Karplus-Strong plucked string, vectorised with a recursive filter."""
    from scipy.signal import lfilter
    n, period = int(dur * sr), max(2, int(round(sr / freq)))
    exc = np.zeros(n)
    exc[:period] = np.random.default_rng(seed + int(freq)).uniform(-1.0, 1.0, period)
    a = np.zeros(period + 2)
    a[0] = 1.0
    a[period] = -0.5 * damp
    a[period + 1] = -0.5 * damp
    return lfilter([1.0], a, exc) * amp


def test_riff(sr, kind="chug"):
    """A short synthetic guitar part (DI level, peaks ~ -12 dBFS) for measuring a board.

    chug  - palm-muted E power chords then two open chords: low-mid heavy, good for gain/tightness
    open  - sustained chord arpeggio: clean-tone and spectral balance
    """
    if kind == "open":
        notes = [82.4, 123.5, 164.8, 207.7, 246.9, 329.6]
        parts = []
        for i, f in enumerate(notes * 2):
            x = _pluck(f, 1.1, sr, damp=0.998, amp=0.22, seed=i)
            parts.append(np.concatenate((np.zeros(int(i * 0.28 * sr)), x)))
        n = max(len(p) for p in parts)
        sig = sum(np.pad(p, (0, n - len(p))) for p in parts)
    else:
        chug = lambda f, d, g: _pluck(f, d, sr, damp=g, amp=0.17) + _pluck(f * 1.498, d, sr, damp=g, amp=0.13)  # noqa: E731
        segs = []
        for i in range(8):
            segs.append(chug(82.4 if i % 4 != 3 else 98.0, 0.25, 0.985))
        segs.append(chug(110.0, 1.0, 0.998))
        segs.append(chug(98.0, 1.0, 0.998))
        sig = np.concatenate(segs)
    sig = sig + np.random.default_rng(0).normal(0.0, 0.0002, len(sig))
    return sig * (0.25 / max(np.abs(sig).max(), 1e-9))


# ------------------------------------------------------------------------------------ spectra

_LOGF = np.geomspace(30.0, 16000.0, 240)


def spectrum_db(x, sr, tilt=3.0, nfft=8192):
    """Power spectrum of the last nfft samples, smoothed to 1/6 octave, in dB.

    tilt compensates dB/octave around 1 kHz so that pink-ish material (guitars) looks flat. Returns
    (log-spaced frequencies, dB) or None for silence.
    """
    x = np.asarray(x, dtype=np.float64)
    if len(x) < nfft:
        x = np.pad(x, (nfft - len(x), 0))
    x = x[-nfft:]
    w = np.hanning(nfft)
    p = np.abs(np.fft.rfft(x * w)) ** 2 / np.sum(w ** 2)
    return _smooth_log(p, sr, nfft, tilt)


def _smooth_log(p, sr, nfft, tilt):
    f = np.fft.rfftfreq(nfft, 1.0 / sr)
    cs = np.concatenate(([0.0], np.cumsum(p)))
    lo = np.searchsorted(f, _LOGF * 2 ** (-1 / 12.0))
    hi = np.maximum(np.searchsorted(f, _LOGF * 2 ** (1 / 12.0)), lo + 1)
    hi = np.minimum(hi, len(p))
    lo = np.minimum(lo, hi - 1)
    avg = (cs[hi] - cs[lo]) / np.maximum(hi - lo, 1)
    db = 10.0 * np.log10(avg + 1e-14)
    db = db + tilt * np.log2(_LOGF / 1000.0)
    if db.max() < FLOOR_DB + 10:
        return None
    return _LOGF, db


def welch_db(x, sr, tilt=3.0, nfft=8192):
    """Long-signal version of spectrum_db (averaged over frames; quiet frames ignored)."""
    x = np.asarray(x, dtype=np.float64)
    if len(x) < nfft:
        x = np.pad(x, (0, nfft - len(x)))
    hop = nfft // 2
    w = np.hanning(nfft)
    starts = np.arange(0, len(x) - nfft + 1, hop)
    cs = np.concatenate(([0.0], np.cumsum(x * x)))
    e = np.sqrt((cs[starts + nfft] - cs[starts]) / nfft)           # per-frame RMS, no frames materialised
    keep = starts[e > 0.12 * e.max()] if e.max() > 0 else starts
    if len(keep) == 0:
        return None
    acc = np.zeros(nfft // 2 + 1)
    ar = np.arange(nfft)
    for i in range(0, len(keep), 64):                              # chunked so long files stay small in memory
        idx = keep[i:i + 64]
        frames = x[idx[:, None] + ar[None, :]]
        acc += np.sum(np.abs(np.fft.rfft(frames * w, axis=1)) ** 2, axis=0)
    p = acc / len(keep) / np.sum(w ** 2)
    return _smooth_log(p, sr, nfft, tilt)


def level_db(x):
    x = np.asarray(x)
    if len(x) == 0:
        return FLOOR_DB, FLOOR_DB
    rms = math.sqrt(float(np.mean(x * x)) + 1e-18)
    pk = float(np.abs(x).max()) + 1e-9
    return 20 * math.log10(rms), 20 * math.log10(pk)


def read_audio(path, sr):
    """Read any audio file soundfile / scipy understands, as mono float at sr."""
    try:
        import soundfile as sf
        data, rate = sf.read(path, always_2d=True, dtype="float64")
    except Exception:   # noqa: BLE001
        from scipy.io import wavfile
        rate, data = wavfile.read(path)
        data = data.astype(np.float64)
        if data.dtype.kind in "iu":
            data = data / np.iinfo(data.dtype).max
        if data.ndim == 1:
            data = data[:, None]
    mono = data.mean(axis=1)
    if rate != sr:
        from scipy.signal import resample_poly
        g = math.gcd(int(rate), int(sr))
        mono = resample_poly(mono, sr // g, rate // g)
    return mono


# ------------------------------------------------------------------------------------ probe engine


class Probe:
    """A stream-less copy of the audio engine used to measure the board offline."""

    def __init__(self, sr=48000):
        import engine_v2
        self.eng = engine_v2.AudioEngine(compile_only=True)
        if sr != self.eng.sr:
            self.eng._alloc(sr)
        self.sr = sr

    # ---- configuration
    def sync_from(self, src):
        e = self.eng
        if src.sr != e.sr:
            e._alloc(src.sr)
            self.sr = src.sr
        e.P[:] = src.P
        e.G[:] = src.G
        e.values = copy.deepcopy(src.values)
        n = min(len(e.IR), len(src.IR))
        e.IR[:n] = src.IR[:n]
        e.chain = (src.chain[0].copy(), src.chain[1])
        self.neutralise()

    def neutralise(self):
        e = self.eng
        e.P[D.T_LOOPER * D.PST] = 0.0
        e.P[D.T_DRUMS * D.PST] = 0.0
        e.G[D.G_MUTE] = 0.0
        e.G[D.G_MASTER] = 1.0

    def set_board(self, keys):
        self.eng.set_board(keys)

    # ---- rendering
    def render(self, sig, upto=None, cab=True, skip=0):
        """Run sig through the first `upto` blocks (None = all). Returns (L, R) without the first
        `skip` samples (warm-up for filters / sag)."""
        e = self.eng
        order, nord = e.chain
        if upto is not None:
            e.chain = (order, min(upto, nord))
        saved = e.G[D.G_CAB]
        if not cab:
            e.G[D.G_CAB] = 0.0
        e.reset()
        n = len(sig)
        outL, outR = np.zeros(n), np.zeros(n)
        try:
            for i in range(0, n, BLOCK):
                m = min(BLOCK, n - i)
                e.L[:m] = sig[i:i + m]
                e._run(m)
                outL[i:i + m] = e.L[:m]
                outR[i:i + m] = e.R[:m]
        finally:
            e.chain = (order, nord)
            e.G[D.G_CAB] = saved
        return outL[skip:], outR[skip:]

    def stage_report(self, sig, board):
        """Per-block measurements: for each block in `board` the level and spectrum entering and
        leaving it (cab included once it is in the path). Returns a list of dicts."""
        e = self.eng
        cabmode = int(e.G[D.G_CAB] + 0.5)
        cabpos = e.G[D.G_CABPOS] > 0.5
        has_amp = "amp" in board
        skip = int(0.4 * self.sr)
        rows = []
        gain = float(e.G[D.G_IN_GAIN])
        prev = np.asarray(sig) * gain
        prev_spec = welch_db(prev[skip:], self.sr)
        in_rms, in_pk = level_db(prev[skip:])
        for j, key in enumerate(board):
            end_cab = (not cabpos or not has_amp)
            # in "end" mode the cab applies to the last block only; in "amp" mode it follows the amp slot
            use_cab = cabmode > 0 and (not end_cab or j == len(board) - 1)
            L, R = self.render(sig, upto=j + 1, cab=use_cab, skip=skip)
            x = 0.5 * (L + R)
            rms, pk = level_db(x)
            on = bool(e.values[key]["on"])
            rows.append(dict(key=key, on=on, in_rms=in_rms, in_pk=in_pk, out_rms=rms, out_pk=pk,
                             spec_in=prev_spec, spec_out=welch_db(x, self.sr),
                             clipped=pk > 0.0))
            in_rms, in_pk, prev_spec = rms, pk, rows[-1]["spec_out"]
        return rows


# ------------------------------------------------------------------------------------ signal-flow rules

GAIN_STAGES = {"fuzz", "od", "dist", "hm2", "mzone", "amp"}
HIGH_GAIN = {"dist", "hm2", "mzone"}
TIME_FX = {"delay", "reverb", "chorus", "flanger", "phaser", "rotary", "univibe", "doubler", "pan"}
PITCH_FX = {"pitch", "octave", "drop", "ring"}


def flow_warnings(board, values, glob, cabpos, peak_in=0.0, clips=0.0, running=False):
    """Rule-based review of the chain. Returns [(severity, title, text)], severity in
    {'bad', 'warn', 'tip'}, most important first."""
    out = []
    idx = {k: i for i, k in enumerate(board)}

    def on(k):
        return k in idx and bool(values.get(k, {}).get("on"))

    amp = idx.get("amp")
    amp_on = on("amp")
    if amp_on and int(glob.get("cab", 0)) == 0:
        out.append(("bad", "Amp without a cabinet",
                    "The amp's power-amp output is meant to drive a speaker. Without cabinet simulation the "
                    "5-10 kHz region stays full of fizzy distortion harmonics. Turn the CABINET to IR."))
    if amp_on and int(glob.get("cab", 0)) == 1:
        out.append(("tip", "Basic cab in use",
                    "BASIC is a coarse filter model of a 1x12. An IR (the synthesized library or a real "
                    ".wav) gives a far more convincing speaker/mic response."))
    if running and peak_in > 0.89:
        out.append(("bad", "Input is clipping",
                    "The interface input is peaking near 0 dBFS, which clips before the signal ever reaches the "
                    "pedals. Lower the interface's input gain, or the guitar volume. Aim for peaks around -12 dBFS."))
    if clips and running:
        out.append(("warn", "Output clipped",
                    "The output reached digital full scale. Lower MASTER or the last gain/level control; "
                    "clipping here is harsh digital distortion, not tube-style saturation."))

    for k in ("mgate",):
        if on(k) and amp is not None and idx[k] < amp:
            out.append(("warn", "Metal Gate before the amp",
                        "The Metal Gate is designed to sit AFTER the amp: it keys from your clean input but "
                        "mutes the amplified hiss and noise. Before the amp there is nothing to remove yet."))
    if on("tboost") and amp is not None and idx["tboost"] > amp:
        out.append(("warn", "Tight Boost after the amp",
                    "A tight boost works by cutting lows (high-pass) BEFORE the gain stages, so the preamp "
                    "doesn't saturate on bass and the palm-muted riffs stay articulate. After the amp it is "
                    "just an EQ + level change."))
    if on("gate") and any(idx.get(g, -1) < idx["gate"] and on(g) for g in HIGH_GAIN | {"amp"}):
        out.append(("warn", "Noise Gate after gain stages",
                    "A gate placed after distortion sees a much louder, already-compressed noise floor, "
                    "so it needs a very high threshold and chops sustain. Move it before the gain, or use the "
                    "Metal Gate after the amp."))
    gain_idx = [idx[g] for g in GAIN_STAGES if on(g)]
    first_gain = min(gain_idx) if gain_idx else None
    last_gain = max(gain_idx) if gain_idx else None
    if first_gain is not None:
        for k in TIME_FX:
            if on(k) and idx[k] < last_gain and k != "doubler":
                out.append(("tip", f"{BY_KEY[k].title.title()} before gain",
                            "Modulation and time effects ahead of distortion get distorted too: repeats and "
                            "reverb tails turn to mush, and chorus/phaser changes how hard the gain stage is "
                            "hit. It is a valid sound (e.g. phaser into fuzz), but the usual order is "
                            "gain -> modulation -> delay -> reverb."))
                break
        for k in PITCH_FX:
            if on(k) and idx[k] > first_gain:
                out.append(("warn", f"{BY_KEY[k].title.title()} after distortion",
                            "Pitch trackers and octavers need a clean, simple waveform. After distortion the "
                            "harmonics confuse the tracking (glitches, warbling). Put pitch effects first."))
                break
        if on("comp") and idx["comp"] > first_gain:
            out.append(("tip", "Compressor after gain",
                        "A compressor after a distortion lifts the noise floor and flattens the dynamics that "
                        "the gain stage already compressed. Before the gain it evens out picking instead."))
    stages = [g for g in ("fuzz", "od", "dist", "hm2", "mzone") if on(g)]
    if len(stages) >= 2:
        out.append(("tip", "Stacked gain pedals",
                    "Multiple gain pedals in series compress and add noise. Often one pedal drives the amp "
                    "(low drive, high level, like a Tube-Screamer boost) rather than all of them clipping."))
    if amp_on and not any(on(g) for g in ("gate", "mgate")) and \
            (values["amp"].get("model", 0) >= 2 or values["amp"].get("gain", 0) > 0.6):
        out.append(("tip", "No noise gate with a high-gain amp",
                    "High gain amplifies pickup hum and hiss between notes. A noise gate (before the gain) or "
                    "the Metal Gate (after the amp) keeps the silences silent."))
    if amp_on and not cabpos and int(glob.get("cab", 0)) > 0 and \
            any(on(k) and idx[k] > amp for k in ("comp", "phaser", "chorus", "flanger", "trem", "univibe", "rotary")):
        out.append(("tip", "Cabinet is at the end of the chain",
                    "Compressors and modulation placed after the amp react to the full-band amp signal, including "
                    "the fizz a speaker would have removed. Set PLACEMENT to 'after amp' to feed them the "
                    "speaker-filtered sound, as when you record a mic'd cab and add effects afterwards. "
                    "(Delay and reverb are linear, so their order relative to the cab makes no audible difference.)"))
    order = {"bad": 0, "warn": 1, "tip": 2}
    out.sort(key=lambda r: order[r[0]])
    return out


# ------------------------------------------------------------------------------------ tone matching

TONE_BANDS = np.geomspace(80.0, 9000.0, 40)


def curve_on_bands(spec):
    """Resample a (freq, dB) spectrum onto TONE_BANDS and remove the average level."""
    f, db = spec
    v = np.interp(np.log2(TONE_BANDS), np.log2(f), db)
    return v - v.mean()


def _band_error(a, b):
    w = np.ones_like(a)
    w[TONE_BANDS < 110] = 0.5
    w[TONE_BANDS > 7000] = 0.6
    return float(np.sqrt(np.sum(w * (a - b) ** 2) / np.sum(w)))


MATCH_PARAMS = [("amp", "bass", 0.0, 1.0), ("amp", "mid", 0.0, 1.0), ("amp", "treble", 0.0, 1.0),
                ("amp", "presence", 0.0, 1.0), ("amp", "depth", 0.0, 1.0),
                ("cut", "hpf", 30.0, 220.0), ("cut", "lpf", 3200.0, 12000.0)] + \
               [("eq", b, -9.0, 9.0) for b in ("b100", "b250", "b630", "b1k6", "b4k", "b8k")]


def match_tone(probe, target, sig, fit_gain=False, progress=None, seed=1, maxiter=14):
    """Fit amp tone controls, a low/high cut, a graphic EQ and the cabinet so that the board's output
    spectrum matches `target` (a TONE_BANDS curve from curve_on_bands).

    probe must already be synced to the board with 'amp', 'cut' and 'eq' present. Returns a dict with
    the fitted 'values' (per pedal), the chosen 'cab' spec, and the error before / after (dB RMS).

    While searching, the cabinet is applied to the rendered output with an FFT convolution (much faster
    than the real-time FIR); the reported 'after' error is re-measured through the real chain.
    """
    from scipy.optimize import differential_evolution
    from scipy.signal import fftconvolve
    e = probe.eng
    sr = probe.sr
    skip = int(0.3 * sr)
    sig = np.asarray(sig)
    params = list(MATCH_PARAMS)
    if fit_gain:
        params.append(("amp", "gain", 0.15, 0.95))
    order, nord = e.chain
    has_amp = D.T_AMP in order[:nord] and bool(e.values["amp"]["on"])
    params = [p for p in params if has_amp or p[0] != "amp"]
    cab_spec = dict(cab=IRL.CAB_NAMES[0], mic="DYNAMIC", pos=0.2, dist=0.2, blend=0.0, room=0.0)
    cur = {"ir": None}

    def spec_error(x):
        spec = welch_db(x, sr)
        return 99.0 if spec is None else _band_error(curve_on_bands(spec), target)

    def render_err(exact=False):
        if exact:
            e.G[D.G_CAB] = 2.0
            L, R = probe.render(sig, skip=skip)
            return spec_error(0.5 * (L + R))
        e.G[D.G_CAB] = 0.0
        L, R = probe.render(sig)
        x = fftconvolve(0.5 * (L + R), cur["ir"])[:len(L)]
        return spec_error(x[skip:])

    def set_cab(spec):
        e.set_ir(IRL.make_cab(sr=sr, **spec), "probe")       # also normalises the level like the live engine
        cur["ir"] = e.IR[:int(e.G[D.G_IR_LEN])][::-1].copy()

    def set_vals(x):
        for (k, n, lo, hi), v in zip(params, x):
            e.set(k, n, float(v))

    for k in ("amp", "eq", "cut"):
        e.set(k, "on", 1)
    set_cab(cab_spec)
    x0 = np.array([e.values[k][n] for (k, n, lo, hi) in params], dtype=float)
    before = render_err(exact=True)

    # 1) pick the cabinet / mic that gets closest with the current tone controls
    best = (render_err(), dict(cab_spec))
    n_cabs = len(IRL.CAB_NAMES) * len(IRL.MICS)
    done = 0
    for cab in IRL.CAB_NAMES:
        for mic in IRL.MICS:
            spec = dict(cab_spec, cab=cab, mic=mic)
            set_cab(spec)
            err = render_err()
            if err < best[0]:
                best = (err, spec)
            done += 1
            if progress:
                progress(0.1 * done / n_cabs, f"trying cabinets… {done}/{n_cabs}")
    cab_spec = best[1]
    set_cab(cab_spec)

    # 2) differential evolution over the tone controls
    count = [0]
    total = (maxiter + 1) * 6 * len(params)

    def cost(x):
        set_vals(x)
        count[0] += 1
        if progress and count[0] % 40 == 0:
            frac = min(1.0, count[0] / total)
            progress(0.1 + 0.9 * frac, f"fitting tone… {int(100 * frac)}%")
        return render_err()

    bounds = [(lo, hi) for (_, _, lo, hi) in params]
    res = differential_evolution(cost, bounds, maxiter=maxiter, popsize=6, tol=1e-3, seed=seed, polish=False,
                                 init="sobol", updating="immediate",
                                 x0=np.clip(x0, [b[0] for b in bounds], [b[1] for b in bounds]))
    set_vals(res.x)
    after = render_err(exact=True)
    values = {}
    for (k, n, lo, hi), v in zip(params, res.x):
        values.setdefault(k, {})[n] = float(v)
    for k in ("amp", "eq", "cut"):
        values.setdefault(k, {})["on"] = 1
    return dict(values=values, cab=cab_spec, before=before, after=after)

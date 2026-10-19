"""Test helpers for PedalBoard v4: a synthetic guitar part, an offline (stream-less) engine and spectrum maths."""
import math

import numpy as np

import dsp_v2 as D

FLOOR_DB = -120.0
BLOCK = 512
_LOGF = np.geomspace(30.0, 16000.0, 240)


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
    """Palm-muted E power chords then two open chords (DI level, peaks ~ -12 dBFS)."""
    chug = lambda f, d, g: _pluck(f, d, sr, damp=g, amp=0.17) + _pluck(f * 1.498, d, sr, damp=g, amp=0.13)  # noqa: E731
    segs = [chug(82.4 if i % 4 != 3 else 98.0, 0.25, 0.985) for i in range(8)]
    segs.append(chug(110.0, 1.0, 0.998))
    segs.append(chug(98.0, 1.0, 0.998))
    sig = np.concatenate(segs)
    sig = sig + np.random.default_rng(0).normal(0.0, 0.0002, len(sig))
    return sig * (0.25 / max(np.abs(sig).max(), 1e-9))


def welch_db(x, sr, tilt=3.0, nfft=8192):
    """Averaged power spectrum smoothed to 1/6 octave, in dB (quiet frames ignored). Returns (freqs, dB)."""
    x = np.asarray(x, dtype=np.float64)
    if len(x) < nfft:
        x = np.pad(x, (0, nfft - len(x)))
    hop = nfft // 2
    w = np.hanning(nfft)
    starts = np.arange(0, len(x) - nfft + 1, hop)
    cs = np.concatenate(([0.0], np.cumsum(x * x)))
    e = np.sqrt((cs[starts + nfft] - cs[starts]) / nfft)
    keep = starts[e > 0.12 * e.max()] if e.max() > 0 else starts
    if len(keep) == 0:
        return None
    acc = np.zeros(nfft // 2 + 1)
    ar = np.arange(nfft)
    for i in range(0, len(keep), 64):
        idx = keep[i:i + 64]
        frames = x[idx[:, None] + ar[None, :]]
        acc += np.sum(np.abs(np.fft.rfft(frames * w, axis=1)) ** 2, axis=0)
    p = acc / len(keep) / np.sum(w ** 2)
    f = np.fft.rfftfreq(nfft, 1.0 / sr)
    cs = np.concatenate(([0.0], np.cumsum(p)))
    lo = np.searchsorted(f, _LOGF * 2 ** (-1 / 12.0))
    hi = np.maximum(np.searchsorted(f, _LOGF * 2 ** (1 / 12.0)), lo + 1)
    hi = np.minimum(hi, len(p))
    lo = np.minimum(lo, hi - 1)
    avg = (cs[hi] - cs[lo]) / np.maximum(hi - lo, 1)
    db = 10.0 * np.log10(avg + 1e-14) + tilt * np.log2(_LOGF / 1000.0)
    return _LOGF, db


def level_db(x):
    """(RMS dB, peak dB) of a signal."""
    x = np.asarray(x)
    if len(x) == 0:
        return FLOOR_DB, FLOOR_DB
    return 20 * math.log10(math.sqrt(float(np.mean(x * x)) + 1e-18)), 20 * math.log10(float(np.abs(x).max()) + 1e-9)


class Probe:
    """A stream-less copy of the audio engine: renders a signal through the board offline."""

    def __init__(self, sr=48000):
        import engine_v2
        self.eng = engine_v2.AudioEngine(compile_only=True)
        if sr != self.eng.sr:
            self.eng._alloc(sr)
        self.sr = sr

    def render(self, sig, skip=0):
        """Run sig through the whole chain; returns (L, R) without the first `skip` samples."""
        e = self.eng
        e.reset()
        n = len(sig)
        outL, outR = np.zeros(n), np.zeros(n)
        for i in range(0, n, BLOCK):
            m = min(BLOCK, n - i)
            e.L[:m] = sig[i:i + m]
            e._run(m)
            outL[i:i + m] = e.L[:m]
            outR[i:i + m] = e.R[:m]
        return outL[skip:], outR[skip:]

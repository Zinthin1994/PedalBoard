"""Offline checks for PedalBoard v4: amp voicings, cabinet library, level matching and cabinet placement."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import probe_v4 as A  # noqa: E402
import dsp_v2 as D  # noqa: E402
import irlib_v4 as IRL  # noqa: E402
from pedals_v2 import PEDALS  # noqa: E402

SR = 48000
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def fresh_probe(board, **vals):
    pr = A.Probe(SR)
    e = pr.eng
    for p in PEDALS:
        e.set(p.key, "on", 0)
    for k in board:
        e.set(k, "on", 1)
    for k, d in vals.items():
        for n, v in d.items():
            e.set(k, n, v)
    e.set_board(board)
    return pr


def hf_ratio(x):
    """Energy above 6 kHz relative to 300 Hz-3 kHz (dB)."""
    s = np.abs(np.fft.rfft(x[SR // 2:SR // 2 + 32768] * np.hanning(32768))) ** 2
    f = np.fft.rfftfreq(32768, 1 / SR)
    return 10 * np.log10(s[f > 6000].sum() / s[(f > 300) & (f < 3000)].sum() + 1e-12)


def main():
    riff = A.test_riff(SR, "chug")
    check("test riff level", abs(20 * np.log10(np.abs(riff).max()) + 12.04) < 0.1)

    # ---- amp voicings: finite, bounded, distinct
    pr = fresh_probe(["amp"], amp={"gain": 0.6})
    pr.eng.G[D.G_CAB] = 0
    outs = []
    for m in range(8):
        pr.eng.set("amp", "model", m)
        L, _ = pr.render(riff, skip=SR // 4)
        rms, pk = A.level_db(L)
        outs.append(L)
        check(f"amp voicing {m} finite / level", np.isfinite(L).all() and -45 < rms < -10 and pk < 3,
              f"rms {rms:.1f} dB peak {pk:.1f} dB")
    spec = [A.welch_db(o, SR)[1] for o in outs]
    for m in (4, 5, 6, 7):
        d = min(np.sqrt(np.mean((spec[m] - spec[j]) ** 2)) for j in range(8) if j != m)
        check(f"new amp voicing {m} is distinct from every other", d > 1.5, f"nearest neighbour {d:.1f} dB")

    # ---- cabinet library
    for name in IRL.CAB_NAMES:
        h = IRL.make_cab(name, sr=SR)
        check(f"cab '{name}' valid", np.isfinite(h).all() and len(h) == int(IRL.IR_MS * 1e-3 * SR) and h.std() > 0)
    base = IRL.make_cab("4x12 Closed British", "DYNAMIC", 0.0, 0.0, sr=SR)

    def tilt(h):
        m = np.abs(np.fft.rfft(h, 8192))
        f = np.fft.rfftfreq(8192, 1 / SR)
        return 20 * np.log10(m[(f > 4000) & (f < 8000)].mean() / m[(f > 300) & (f < 1000)].mean())
    check("cab: cone edge darker than cap", tilt(IRL.make_cab("4x12 Closed British", "DYNAMIC", 1.0, 0.0, sr=SR))
          < tilt(base) - 2, f"{tilt(base):.1f} -> "
          f"{tilt(IRL.make_cab('4x12 Closed British', 'DYNAMIC', 1.0, 0.0, sr=SR)):.1f} dB")
    lows = lambda h: np.abs(np.fft.rfft(h, 8192))[(np.fft.rfftfreq(8192, 1 / SR) > 80) & (np.fft.rfftfreq(8192, 1 / SR) < 200)].mean()  # noqa: E731
    check("cab: proximity effect (close has more bass)",
          lows(IRL.make_cab("4x12 Closed British", "RIBBON", 0.2, 0.0, sr=SR)) >
          1.15 * lows(IRL.make_cab("4x12 Closed British", "RIBBON", 0.2, 1.0, sr=SR)))
    check("cab: room adds energy after the direct sound",
          np.abs(IRL.make_cab("2x12 Warm Dark", room=0.8, sr=SR)[300:]).sum() >
          2 * np.abs(IRL.make_cab("2x12 Warm Dark", room=0.0, sr=SR)[300:]).sum())

    # ---- engine IR installation + level matching
    from engine_v2 import AudioEngine
    e = AudioEngine(compile_only=True)
    levels = []
    for name in IRL.CAB_NAMES:
        e.set_ir(IRL.make_cab(name, sr=SR), name)
        r = e.ir_response()
        levels.append(np.mean(r[1][(r[0] > 300) & (r[0] < 3000)]))
    check("cab levels matched (300 Hz-3 kHz within 1.5 dB)", max(levels) - min(levels) < 1.5,
          f"spread {max(levels) - min(levels):.2f} dB")

    # ---- cabinet placement: linear blocks commute with the cab, non-linear ones do not
    def placed(board, **vals):
        pr = fresh_probe(board, **vals)
        pr.eng.set_ir(IRL.make_cab("4x12 Closed British", sr=SR), "t")
        pr.eng.G[D.G_CAB] = 2
        outs = []
        for pos in (0, 1):
            pr.eng.G[D.G_CABPOS] = pos
            outs.append(pr.render(riff, skip=SR // 2)[0])
        return outs
    a, b = placed(["amp", "reverb"], amp={"model": 1, "gain": 0.5}, reverb={"mode": 1, "mix": 0.6, "decay": 2.0})
    check("cab placement: reverb is linear, so order makes no difference", np.abs(a - b).max() < 0.01 * np.abs(a).max(),
          f"max diff {np.abs(a - b).max():.2g}")
    a, b = placed(["amp", "dist"], amp={"model": 1, "gain": 0.5}, dist={"drive": 30})
    check("cab placement: a distortion after the amp does depend on it", np.abs(a - b).max() > 0.05 * np.abs(a).max(),
          f"max diff {np.abs(a - b).max():.2g}")
    check("cab placement output finite", np.isfinite(a).all() and np.isfinite(b).all())

    # ---- Low/High Cut still sits cleanly in the chain with the cab
    pr = fresh_probe(["cut", "amp"], amp={"model": 1, "gain": 0.5}, cut={"hpf": 400})
    pr.eng.set_ir(IRL.make_cab("4x12 Closed British", sr=SR), "t")
    pr.eng.G[D.G_CAB] = 2
    L, _ = pr.render(riff, skip=SR // 2)
    check("cut + amp + cab renders finite output", np.isfinite(L).all() and np.abs(L).max() > 1e-3)

    print(f"\n{sum(RESULTS)}/{len(RESULTS)} checks passed")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())

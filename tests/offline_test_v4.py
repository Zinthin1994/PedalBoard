"""Offline checks for PedalBoard v4: amp voicings, cabinet library + placement, analysis, flow rules, matching."""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import analysis_v4 as A  # noqa: E402
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

    # ---- per-block report
    pr = fresh_probe(["gate", "od", "amp", "delay"], od={"drive": 20})
    pr.eng.set_ir(IRL.make_cab("1x12 Open-back Vintage", sr=SR), "t")
    pr.eng.G[D.G_CAB], pr.eng.G[D.G_CABPOS] = 2, 1
    t0 = time.time()
    rows = pr.stage_report(riff, ["gate", "od", "amp", "delay"])
    check("stage report rows", len(rows) == 4 and all(r["spec_out"] is not None for r in rows),
          f"{(time.time() - t0) * 1000:.0f} ms")
    crest = lambda r: r["out_pk"] - r["out_rms"]  # noqa: E731
    check("overdrive lowers the crest factor (clipping / compression)", crest(rows[1]) < crest(rows[0]) - 1,
          f"{crest(rows[0]):.1f} -> {crest(rows[1]):.1f} dB")

    # ---- flow rules
    vals = {p.key: {"on": 1} for p in PEDALS}
    vals["amp"].update(model=3, gain=0.8)
    titles = [w[1] for w in A.flow_warnings(["mgate", "amp", "tboost", "delay"], vals, {"cab": 0}, False)]
    check("flow: amp without cab", "Amp without a cabinet" in titles)
    check("flow: metal gate before amp", "Metal Gate before the amp" in titles)
    check("flow: tight boost after amp", "Tight Boost after the amp" in titles)
    good = A.flow_warnings(["gate", "tboost", "amp", "mgate", "delay"], vals, {"cab": 2}, True)
    check("flow: a sensible chain has no problems", not [w for w in good if w[0] in ("bad", "warn")],
          str([w[1] for w in good]))

    # ---- tone matching on a known target
    pr = fresh_probe(["amp", "cut", "eq"], amp={"model": 1, "gain": 0.5})
    pr.eng.G[D.G_CABPOS] = 1
    pr.eng.set_ir(IRL.make_cab("2x12 Warm Dark", "RIBBON", 0.4, 0.4, sr=SR), "tgt")
    pr.eng.G[D.G_CAB] = 2
    pr.eng.set("amp", "bass", 0.85)
    pr.eng.set("amp", "treble", 0.2)
    pr.eng.set("amp", "mid", 0.7)
    pr.eng.set("cut", "lpf", 4200)
    L, R = pr.render(riff, skip=int(0.3 * SR))
    target = A.curve_on_bands(A.welch_db(0.5 * (L + R), SR))
    pr2 = fresh_probe(["amp", "cut", "eq"], amp={"model": 1, "gain": 0.5})
    pr2.eng.G[D.G_CABPOS] = 1
    t0 = time.time()
    res = A.match_tone(pr2, target, riff)
    dt = time.time() - t0
    check("tone match reduces spectral error a lot", res["after"] < 0.4 * res["before"] and res["after"] < 2.5,
          f"{res['before']:.2f} -> {res['after']:.2f} dB RMS in {dt:.0f} s, cab {res['cab']['cab']} / {res['cab']['mic']}")

    print(f"\n{sum(RESULTS)}/{len(RESULTS)} checks passed")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())

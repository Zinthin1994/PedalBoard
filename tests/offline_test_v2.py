"""Offline test for PedalBoard v2: every pedal alone + some full boards.
Checks finite output, no clipping blow-ups, CPU headroom, writes WAVs to tests/out_v2/."""
import os
import sys
import time
import wave

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import dsp_v2 as D  # noqa: E402
from engine_v2 import AudioEngine  # noqa: E402
from pedals_v2 import PEDALS  # noqa: E402

SR = 48000
BLOCK = 128
OUT = os.path.join(os.path.dirname(__file__), "out_v2")


def pluck(freq, dur, amp=0.3):
    n, period = int(dur * SR), int(SR / freq)
    line = np.random.default_rng(int(freq)).uniform(-1, 1, period)
    out = np.zeros(n)
    for i in range(n):
        j = i % period
        out[i] = line[j]
        line[j] = 0.996 * 0.5 * (line[j] + line[(j + 1) % period])
    return out * amp


def riff():
    notes = [82.4, 110.0, 146.8, 196.0, 110.0, 164.8, 82.4, 98.0]
    sig = np.concatenate([pluck(f, 0.5) for f in notes] + [np.zeros(SR)])
    return sig + np.random.default_rng(0).normal(0, 0.0003, len(sig))


def render(eng, sig, hook=None):
    eng.reset()
    outL, outR = np.zeros(len(sig)), np.zeros(len(sig))
    t0 = time.perf_counter()
    for i in range(0, len(sig) - BLOCK + 1, BLOCK):
        if hook:
            hook(eng, i)
        eng.L[:BLOCK] = sig[i:i + BLOCK]
        eng._run(BLOCK)
        outL[i:i + BLOCK] = eng.L[:BLOCK]
        outR[i:i + BLOCK] = eng.R[:BLOCK]
    return outL, outR, time.perf_counter() - t0


def write_wav(path, L, R):
    data = (np.clip(np.stack([L, R], 1), -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


def configure(eng, board, **vals):
    for p in PEDALS:
        eng.set(p.key, "on", 0)
    for k in board:
        eng.set(k, "on", 1)
    for k, d in vals.items():
        for name, v in d.items():
            eng.set(k, name, v)
    eng.set_board(board)


def _peak_hz(x):
    seg = x[SR // 2:SR // 2 + 16384] * np.hanning(16384)
    return np.fft.rfftfreq(16384, 1 / SR)[np.argmax(np.abs(np.fft.rfft(seg)))]


def metal_checks(eng, sig):
    """Behavioural checks for the metal pack."""
    ok = True
    eng.set_global(cab=0)
    t = np.arange(2 * SR) / SR
    sine = 0.2 * np.sin(2 * np.pi * 220 * t)

    # drop tuner lands on the right pitch for each tuning
    for idx, semis in enumerate([-1, -2, -3, -4, -5, -7]):
        configure(eng, ["drop"], drop={"semis": idx, "mix": 1.0, "quality": 1})
        L, _, _ = render(eng, sine)
        want = 220 * 2 ** (semis / 12)
        got = _peak_hz(L)
        good = abs(got - want) / want < 0.06
        ok &= good
        print(f"    drop {semis:+d} st: {got:6.1f} Hz (want {want:6.1f}) {'ok' if good else 'BAD'}")

    # metal gate after a high-gain amp: loud while playing, silent in the gaps
    burst = np.zeros(2 * SR)
    burst[:SR // 2] = sine[:SR // 2]
    burst += np.random.default_rng(9).normal(0, 0.0005, len(burst))      # pickup hiss
    for gate_on in (0, 1):
        configure(eng, ["amp", "mgate"] if gate_on else ["amp"], amp={"model": 3, "gain": 0.8})
        L, _, _ = render(eng, burst)
        play = np.sqrt(np.mean(L[SR // 8:SR // 2] ** 2))
        gap = np.sqrt(np.mean(L[SR:] ** 2))
        print(f"    metal amp {'+ gate' if gate_on else 'no gate'}: playing {20*np.log10(play):6.1f} dB, "
              f"gap {20*np.log10(gap + 1e-12):7.1f} dB")
        if gate_on:
            ok &= gap < 1e-4 and play > 0.02

    # drums: onsets at the right tempo
    configure(eng, ["drums"], drums={"bpm": 120, "pattern": 0, "vol": 0.8})
    L, _, _ = render(eng, np.zeros(2 * SR))
    env = np.abs(L)
    on = np.where((env[1:] > 0.1) & (np.convolve(env, np.ones(480), "full")[:len(env) - 1] / 480 < 0.02))[0]
    beats = [on[0]] if len(on) else []
    for o in on[1:]:
        if o - beats[-1] > SR // 10:
            beats.append(o)
    iv = np.diff(beats) / SR if len(beats) > 2 else np.array([0])
    print(f"    drums 120 bpm click: {len(beats)} beats in 2 s, interval {iv.mean():.3f} s (want 0.500)")
    ok &= abs(iv.mean() - 0.5) < 0.01

    # chainsaw: the two HM-2 resonances stick out when Low/High are up
    configure(eng, ["hm2"], hm2={"dist": 0.8, "low": 1.0, "high": 1.0})
    L, _, _ = render(eng, sig)
    S = np.abs(np.fft.rfft(L[: 4 * SR]))
    f = np.fft.rfftfreq(4 * SR, 1 / SR)
    band = lambda a, b: 20 * np.log10(np.sqrt(np.mean(S[(f >= a) & (f < b)] ** 2)) + 1e-12)
    print(f"    chainsaw bands: 80-120 {band(80, 120):.1f}  300-600 {band(300, 600):.1f}  "
          f"1.2-1.5k {band(1200, 1500):.1f}  dB")
    ok &= band(1200, 1500) > band(300, 600) and band(80, 120) > band(300, 600)

    # tight boost removes lows
    lo = 0.2 * np.sin(2 * np.pi * 60 * t)
    configure(eng, ["tboost"], tboost={"tight": 400, "gain": 0})
    L, _, _ = render(eng, lo)
    cut = 20 * np.log10(np.sqrt(np.mean(L[SR:] ** 2)) / np.sqrt(np.mean(lo[SR:] ** 2)))
    print(f"    tight boost @400 Hz: 60 Hz attenuated {cut:.1f} dB")
    ok &= cut < -15
    eng.set_global(cab=1)
    return ok


def main():
    os.makedirs(OUT, exist_ok=True)
    t = time.perf_counter()
    eng = AudioEngine()
    print(f"engine ready in {time.perf_counter() - t:.1f}s")
    sig = riff()
    dur = len(sig) / SR
    ok = True

    def check(name, L, R, el):
        nonlocal ok
        fin = bool(np.all(np.isfinite(L)) and np.all(np.isfinite(R)))
        peak = max(np.abs(L).max(), np.abs(R).max())
        rms = np.sqrt(np.mean(L ** 2))
        width = np.sqrt(np.mean((L - R) ** 2)) / (rms + 1e-12)
        cpu = 100 * el / dur
        good = fin and peak <= 1.0 and rms > 1e-4 and cpu < 20
        ok &= good
        print(f"{'ok ' if good else 'BAD'} {name:16s} peak={peak:5.3f} rms={rms:6.4f} "
              f"stereo={width:4.2f} cpu={cpu:5.2f}%")
        write_wav(os.path.join(OUT, name + ".wav"), L, R)

    configure(eng, [])
    check("dry", *render(eng, sig))
    for p in PEDALS:
        if p.key == "looper":
            continue
        configure(eng, [p.key])
        hook = None
        if p.key == "wah":
            def hook(e, i):
                e.set("wah", "pos", 0.5 - 0.5 * np.cos(2 * np.pi * i / SR))
        check(p.key, *render(eng, sig, hook))

    # looper: record 2 s, then play while input continues
    configure(eng, ["looper"])

    def loop_hook(e, i):
        if i == 0:
            e.set("looper", "cmd", 1)
        elif i == 2 * SR // BLOCK * BLOCK:
            e.set("looper", "cmd", 2)
    L, R, el = render(eng, sig, loop_hook)
    length = eng.pedal_state("looper", D.S_LOOP_LEN)
    print(f"    looper length={length / SR:.2f}s has={eng.pedal_state('looper', D.S_LOOP_HAS)}")
    ok &= abs(length / SR - 2.0) < 0.01
    check("looper", L, R, el)

    # amp channels
    for model, name in enumerate(["clean", "crunch", "lead"]):
        configure(eng, ["amp"], amp={"model": model, "gain": 0.7})
        check("amp_" + name, *render(eng, sig))

    # cabinet IR: a unit impulse must reproduce the uncabbed signal exactly
    import tempfile
    from engine_v2 import write_wav as ww
    tmp = tempfile.mkdtemp()
    delta = np.zeros((512, 1))
    delta[0] = 1.0
    ww(os.path.join(tmp, "delta.wav"), delta, SR)
    configure(eng, ["od"])
    eng.set_global(cab=0)
    ref, _, _ = render(eng, sig)
    eng.load_ir(os.path.join(tmp, "delta.wav"))
    eng.set_global(cab=2)
    got, _, _ = render(eng, sig)
    err = np.max(np.abs(ref - got))            # v4: IRs are level-matched on their 300 Hz-3 kHz mean (delta = 0 dB)
    print(f"    IR delta identity max err = {err:.2e}")
    ok &= err < 1e-5
    # realistic-length IR (decaying filtered noise) for CPU cost
    rng = np.random.default_rng(5)
    n_ir = 4096
    cab = rng.normal(0, 1, n_ir) * np.exp(-np.arange(n_ir) / 300.0)
    cab = np.convolve(cab, np.ones(6) / 6, mode="same")
    ww(os.path.join(tmp, "cab.wav"), cab[:, None] * 0.5, 44100)       # also exercises resampling
    eng.load_ir(os.path.join(tmp, "cab.wav"))
    print(f"    IR loaded: {int(eng.G[D.G_IR_LEN])} taps")
    check("ir_cab", *render(eng, sig))
    eng.set_global(cab=1)
    eng.clear_ir()

    # file player through the board
    configure(eng, ["dist"])
    ww(os.path.join(tmp, "di.wav"), sig[:, None], SR)
    eng.load_player(os.path.join(tmp, "di.wav"))
    eng.player_mode, eng.player_playing, eng.player_vol = "through", True, 1.0
    eng.reset()
    eng.L[:BLOCK] = 0.0
    chunk = eng._player_chunk(BLOCK)
    print(f"    player chunk ok: {chunk.shape}, pos={eng.player_pos}")
    ok &= chunk.shape == (BLOCK, 2) and eng.player_pos == BLOCK
    eng.player_playing = False

    ok &= metal_checks(eng, sig)

    boards = {
        "board_hendrix": (["fuzz", "univibe", "reverb"], {}),
        "board_metal": (["gate", "dist", "eq", "delay", "reverb"],
                        {"dist": {"drive": 40, "mid": -6}, "gate": {"thresh": -50}}),
        "board_ambient": (["swell", "chorus", "delay", "reverb", "trem"],
                          {"delay": {"time": 600, "fb": 0.6}, "reverb": {"decay": 8, "mix": 0.6}}),
        "board_everything": ([p.key for p in PEDALS], {}),
    }
    for name, (board, vals) in boards.items():
        configure(eng, board, **vals)
        check(name, *render(eng, sig))
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

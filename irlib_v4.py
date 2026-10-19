"""Synthesized guitar-cabinet impulse responses for PedalBoard v4.

A real cab IR is the combined impulse response of a speaker, its enclosure and a microphone at a
particular spot. These are *models* of that chain, built from a magnitude response and turned into a
minimum-phase FIR (the cepstral method), so they are license-clean and fully adjustable:

    speaker/cab   resonance high-pass (f0, Q), cone-breakup presence peaks, voice-coil low-pass
    microphone    type voicing (dynamic / ribbon / condenser) and proximity effect
    position      cap (bright, forward) -> cone edge (dark, warm)
    distance      close (bassy, proximity effect) -> far (thinner, less air)
    blend         adds a second (ribbon) mic with a small delay: real phase interaction/comb filtering
    room          early reflections (2-20 ms) from a small room

They are not captures of any specific commercial cabinet. Real IR files (.wav) still load alongside.
"""
import numpy as np

IR_MS = 21.0

# name -> voicing.  hp = (f0 Hz, order, resonance dB), lp = (fc Hz, order),
# bumps = (centre Hz, gain dB, width in octaves)
CABS = {
    "1x12 Open-back Vintage": dict(
        short="Loose lows, mid-forward, gentle top. Cleans and edge-of-breakup.",
        hp=(95.0, 2, 1.5), lp=(5200.0, 4), seed=1,
        bumps=[(130, 2.0, 0.7), (2300, 5.0, 0.45), (3700, 2.0, 0.35), (1100, -1.5, 0.6)],
        desc="A single 12\" in an open-backed combo. Loose lows (the back wave leaks out), a mid-forward "
             "voice and a gentle top end. The classic clean / edge-of-breakup box."),
    "2x12 Open-back Chime": dict(
        short="Bright and glassy. Jangle, cleans, chimey crunch.",
        hp=(85.0, 2, 1.0), lp=(6600.0, 4), seed=2,
        bumps=[(1300, 1.5, 0.7), (2900, 6.0, 0.4), (5200, 2.5, 0.3), (400, -1.0, 0.6)],
        desc="Two 12\"s, open back, bright alnico-style top. Glassy and articulate: jangle, cleans, "
             "chimey crunch."),
    "4x12 Closed British": dict(
        short="Tight 100 Hz thump, upper-mid push, steep top roll-off.",
        hp=(78.0, 2, 4.0), lp=(5000.0, 5), seed=3,
        bumps=[(105, 2.5, 0.5), (1900, 3.5, 0.45), (3500, 4.5, 0.3), (700, -1.5, 0.5)],
        desc="Four 12\"s in a sealed cabinet: tight, punchy low-end with the speaker-resonance thump "
             "around 100 Hz, a 'greenback'-style upper-mid push and a steep roll-off above 5 kHz."),
    "4x12 Closed Modern": dict(
        short="Scooped low-mids, aggressive 2.5-4 kHz bite. High gain.",
        hp=(72.0, 2, 3.0), lp=(5600.0, 5), seed=4,
        bumps=[(110, 2.0, 0.5), (650, -2.5, 0.5), (2600, 5.0, 0.35), (4300, 4.0, 0.3), (3300, -2.0, 0.12)],
        desc="Sealed 4x12 with a scooped low-mid and an aggressive 2.5-4 kHz bite - the modern high-gain "
             "cabinet. Tight, cutting and a little fizzy if you leave the top end unchecked."),
    "1x10 Small Combo": dict(
        short="Thin bass, nasal mids, dark top. Lo-fi and blues.",
        hp=(125.0, 2, 1.0), lp=(4700.0, 4), seed=5,
        bumps=[(1800, 3.5, 0.5), (3000, 1.5, 0.4), (350, -1.0, 0.5)],
        desc="A small 10\" combo: little bass, a nasal midrange and a dark top. Great for lo-fi, "
             "blues and 'recorded in a bedroom' tones."),
    "2x12 Warm Dark": dict(
        short="Creamy and dark. Tames fizz; smooth leads.",
        hp=(88.0, 2, 1.5), lp=(4300.0, 3), seed=6,
        bumps=[(160, 2.5, 0.7), (2000, 3.0, 0.6), (3200, 0.5, 0.4)],
        desc="Two 12\"s voiced dark and creamy - ceramic-magnet warmth with the top rolled off early. "
             "Smooth for leads and jazz; tames harsh fizz from high-gain amps."),
}
CAB_NAMES = list(CABS)

MICS = ["DYNAMIC", "RIBBON", "CONDENSER"]
MIC_DESC = {
    "DYNAMIC": "Dynamic (SM57-style): presence bump around 5-6 kHz, tight low end. The default for guitar.",
    "RIBBON": "Ribbon (R-121-style): rolls the top off gently and thickens 150-250 Hz; strong proximity effect.",
    "CONDENSER": "Condenser: extended, flat response with some air above 10 kHz - the most 'hi-fi' option.",
}


def _smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _bump(f, f0, db, width):
    return db * np.exp(-0.5 * (np.log2(np.maximum(f, 1.0) / f0) / width) ** 2)


def _hp_db(f, f0, order):
    return -10.0 * np.log10(1.0 + (f0 / np.maximum(f, 1.0)) ** (2 * order))


def _lp_db(f, f0, order):
    return -10.0 * np.log10(1.0 + (np.maximum(f, 1.0) / f0) ** (2 * order))


def response_db(f, cab, mic, pos, dist):
    """Magnitude (dB) of speaker + enclosure + microphone at frequencies f (Hz)."""
    c = CABS[cab]
    f0, order, res = c["hp"]
    db = _hp_db(f, f0, order) + _bump(f, f0 * 1.15, res, 0.25)
    db += _lp_db(f, *c["lp"])
    for (fc, g, w) in c["bumps"]:
        db += _bump(f, fc, g, w)
    rng = np.random.default_rng(c["seed"])           # cone breakup: small, repeatable irregularities
    nodes = np.geomspace(1000.0, 6500.0, 36)
    ripple = np.interp(np.log2(np.maximum(f, 1.0)), np.log2(nodes), rng.normal(0.0, 1.0, nodes.size))
    db += 1.1 * ripple * _smooth((np.log2(np.maximum(f, 1.0) / 900.0)) / 0.8)
    db += 0.7 * np.sin(2 * np.pi * 7.0 * np.log2(np.maximum(f, 1.0) / 100.0) + c["seed"]) \
        * np.exp(-0.5 * (np.log2(np.maximum(f, 1.0) / 450.0) / 1.4) ** 2)   # cabinet box modes

    # microphone
    prox = {"DYNAMIC": 5.0, "RIBBON": 9.0, "CONDENSER": 3.0}[mic]
    if mic == "DYNAMIC":
        db += _bump(f, 5800.0, 3.5, 0.45) + _bump(f, 3200.0, 1.5, 0.4) + _hp_db(f, 70.0, 2) + _lp_db(f, 14000.0, 2)
    elif mic == "RIBBON":
        db += _lp_db(f, 6500.0, 1) + _bump(f, 190.0, 2.0, 0.8) + _bump(f, 3000.0, -1.0, 0.5) + _hp_db(f, 45.0, 2)
    else:
        db += _bump(f, 11000.0, 3.0, 0.6) + _bump(f, 3500.0, 0.8, 0.5) + _hp_db(f, 35.0, 2)

    # position: cap -> edge darkens the top, adds a touch of low-mid
    db += -pos * 8.0 * _smooth(np.log2(np.maximum(f, 1.0) / 1500.0) / 2.6)
    db += pos * 1.5 * np.exp(-0.5 * (np.log2(np.maximum(f, 1.0) / 180.0) / 1.2) ** 2)
    # distance: proximity effect (bass boost close in) and a little air loss far away
    db += prox * (1.0 - dist) / (1.0 + (np.maximum(f, 1.0) / 220.0) ** 2)
    db += -2.5 * dist * _smooth(np.log2(np.maximum(f, 1.0) / 4000.0) / 1.6)
    return db


def _min_phase(mag, n):
    """Minimum-phase impulse response with the given rfft magnitude (length n/2+1)."""
    cep = np.fft.irfft(np.log(np.maximum(mag, 1e-6)), n)
    w = np.zeros(n)
    w[0] = 1.0
    w[1:n // 2] = 2.0
    w[n // 2] = 1.0
    return np.fft.irfft(np.exp(np.fft.rfft(cep * w)), n)


def _single(cab, mic, pos, dist, sr, n=8192):
    f = np.fft.rfftfreq(n, 1.0 / sr)
    return _min_phase(10.0 ** (response_db(f, cab, mic, pos, dist) / 20.0), n)


def room_kernel(sr, amount, seed=11):
    """Early reflections of a small room (2-20 ms) - sparse, darkened taps."""
    n = int(IR_MS * 1e-3 * sr)
    k = np.zeros(n)
    k[0] = 1.0
    if amount <= 0.0:
        return k
    rng = np.random.default_rng(seed)
    times = np.sort(rng.uniform(1.6e-3, 19.5e-3, 16))
    for t in times:
        i = int(t * sr)
        a = amount * 0.42 * np.exp(-t / 0.011) * rng.uniform(0.5, 1.0) * (1 if rng.random() < 0.6 else -1)
        for j, wgt in enumerate((0.3, 0.4, 0.3)):          # soften each reflection (walls absorb highs)
            if i + j < n:
                k[i + j] += a * wgt
    return k


def make_cab(cab, mic="DYNAMIC", pos=0.2, dist=0.2, blend=0.0, room=0.0, sr=48000):
    """Build the impulse response (float array, ~21 ms) for the given cabinet settings."""
    cab = cab if cab in CABS else CAB_NAMES[0]
    h = _single(cab, mic, pos, dist, sr)
    if blend > 0.0:
        hb = _single(cab, "RIBBON", min(1.0, pos + 0.45), min(1.0, dist + 0.25), sr)
        d = int(0.00022 * sr)                              # ~7.5 cm extra path -> a real comb filter
        hb = np.concatenate((np.zeros(d), hb))[:len(h)]
        h = (1.0 - 0.45 * blend) * h + 0.9 * blend * hb
    n = int(IR_MS * 1e-3 * sr)
    h = h[:n].copy()
    if room > 0.0:
        h = np.convolve(h, room_kernel(sr, room))[:n]
    return h


def apply_room(h, room, sr):
    """Add early reflections to any impulse response (used for loaded .wav IRs)."""
    if room <= 0.0:
        return h
    n = int(IR_MS * 1e-3 * sr)
    return np.convolve(h[:n], room_kernel(sr, room))[:n]

"""Pedal catalogue for PedalBoard v2: names, colours, knobs and how UI values map to DSP values.

Param order matters: the n-th Param of a pedal is P[base + n] in dsp_v2 (P[base] is on/off).
"""
import dsp_v2 as D


def db(v):
    return 10.0 ** (v / 20.0)


def bell(v):            # dB -> amplitude used by the SVF bell filters
    return 10.0 ** (v / 40.0)


def ms(v):
    return v / 1000.0


class Param:
    def __init__(self, name, label, lo, hi, default, fmt="{:.2f}", log=False, conv=float,
                 choices=None, hidden=False, step=None):
        self.name, self.label, self.lo, self.hi, self.default = name, label, lo, hi, default
        self.fmt, self.log, self.conv, self.choices = fmt, log, conv, choices
        self.hidden, self.step = hidden, step


def Choice(name, label, options, default=0):
    return Param(name, label, 0, len(options) - 1, default, choices=options)


class Pedal:
    def __init__(self, key, tid, title, color, category, desc, params, ink="#111", text="#111"):
        self.key, self.tid, self.title, self.color = key, tid, title, color
        self.category, self.desc, self.params = category, desc, params
        self.ink = ink          # knob arc colour
        self.text = text        # label colour on the enclosure


PEDALS = [
    Pedal("gate", D.T_GATE, "NOISE GATE", "#4a4f57", "Dynamics", "Silences hum and hiss between notes", [
        Param("thresh", "Thresh", -80, -20, -60, "{:.0f} dB", conv=db),
        Param("release", "Release", 20, 500, 80, "{:.0f} ms", log=True, conv=ms),
    ], ink="#9ccc65", text="#e8e8ea"),
    Pedal("drop", D.T_DROP, "DROP TUNER", "#4527a0", "Metal",
          "Plays you in a lower tuning without retuning the guitar", [
              Param("semis", "Tuning", 0, 5, 1, choices=["Eb", "D", "C#", "C", "B", "A"],
                    conv=lambda i: [-1, -2, -3, -4, -5, -7][int(round(i))]),
              Param("mix", "Mix", 0, 1, 1.0),
              Choice("quality", "Grain", ["TIGHT", "SMOOTH"]),
          ], ink="#b39ddb", text="#ede7f6"),
    Pedal("comp", D.T_COMP, "COMPRESSOR", "#1e88e5", "Dynamics", "Evens out dynamics, adds sustain", [
        Param("sustain", "Sustain", 0, 1, 0.5),
        Param("attack", "Attack", 1, 50, 10, "{:.0f} ms", log=True, conv=ms),
        Param("level", "Level", -12, 12, 0, "{:+.0f} dB", conv=db),
        Param("blend", "Blend", 0, 1, 1.0),
    ], text="#fff"),
    Pedal("boost", D.T_BOOST, "CLEAN BOOST", "#cfd8dc", "Gain", "Clean volume boost with bass/treble", [
        Param("gain", "Gain", 0, 24, 8, "{:+.0f} dB", conv=db),
        Param("bass", "Bass", -12, 12, 0, "{:+.0f} dB", conv=db),
        Param("treble", "Treble", -12, 12, 0, "{:+.0f} dB", conv=db),
    ]),
    Pedal("tboost", D.T_TBOOST, "TIGHT BOOST", "#2e7d32", "Metal",
          "Boost with a bass cut - put it before the amp for tight chugs", [
              Param("tight", "Tight", 40, 800, 300, "{:.0f} Hz", log=True),
              Param("gain", "Boost", 0, 24, 8, "{:+.0f} dB", conv=db),
              Param("tone", "Tone", -12, 12, 2, "{:+.0f} dB", conv=bell),
          ], ink="#a5d6a7", text="#e8f5e9"),
    Pedal("octave", D.T_OCTAVE, "OCTAVER", "#7e57c2", "Pitch", "Analog-style sub octaves + octave up", [
        Param("dry", "Dry", 0, 1, 1.0),
        Param("sub1", "Oct -1", 0, 1, 0.7),
        Param("sub2", "Oct -2", 0, 1, 0.0),
        Param("up", "Oct +1", 0, 1, 0.0),
    ], text="#fff"),
    Pedal("wah", D.T_WAH, "WAH", "#1d1d22", "Filter", "Cry-baby wah: rock it, let it follow picking, or sweep", [
        Choice("mode", "Mode", ["MANUAL", "AUTO", "LFO"]),
        Param("pos", "Position", 0, 1, 0.5, hidden=True),
        Param("q", "Reso", 1.5, 15, 5.0, "Q {:.1f}", log=True),
        Param("fmin", "Heel", 150, 800, 350, "{:.0f} Hz", log=True),
        Param("fmax", "Toe", 1000, 4000, 2200, "{:.0f} Hz", log=True),
        Param("sens", "Sens", 0, 1, 0.5),
        Param("rate", "Rate", 0.1, 8, 1.5, "{:.2f} Hz", log=True),
        Param("level", "Level", 0, 2, 1.0),
    ], ink="#d9b44a", text="#d9b44a"),
    Pedal("envf", D.T_ENVF, "ENVELOPE FILTER", "#00897b", "Filter", "Funky auto-filter driven by your picking", [
        Param("sens", "Sens", 0, 1, 0.5),
        Param("q", "Reso", 0.7, 12, 4.0, "Q {:.1f}", log=True),
        Param("range", "Range", 500, 4000, 2000, "{:.0f} Hz", log=True),
        Choice("mode", "Filter", ["LP", "BP", "HP"]),
        Choice("dir", "Sweep", ["UP", "DOWN"]),
    ], text="#fff"),
    Pedal("swell", D.T_SWELL, "VOLUME SWELL", "#90a4ae", "Dynamics", "Fades each note in - violin / pad swells", [
        Param("sens", "Sens", 0, 1, 0.5),
        Param("attack", "Attack", 50, 2000, 400, "{:.0f} ms", log=True, conv=ms),
    ]),
    Pedal("fuzz", D.T_FUZZ, "FUZZ", "#c62828", "Gain", "Vintage fuzz; raise Bias for a gated, sputtery fuzz", [
        Param("fuzz", "Fuzz", 20, 60, 40, "{:.0f} dB", conv=db),
        Param("bias", "Bias", 0, 1, 0.15),
        Param("tone", "Tone", 0, 1, 0.5),
        Param("level", "Level", 0, 1, 0.5),
    ], text="#fff"),
    Pedal("od", D.T_OD, "OVERDRIVE", "#43a047", "Gain", "Mid-hump tube-screamer style drive", [
        Param("drive", "Drive", 0, 40, 15, "{:.0f} dB", conv=db),
        Param("tone", "Tone", 0, 1, 0.5),
        Param("level", "Level", 0, 1, 0.6),
    ]),
    Pedal("dist", D.T_DIST, "DISTORTION", "#e8711a", "Gain", "High-gain hard-clipping distortion with mid control", [
        Param("drive", "Drive", 0, 50, 25, "{:.0f} dB", conv=lambda v: db(v + 12)),
        Param("tone", "Tone", 0, 1, 0.5),
        Param("mid", "Mid", -12, 12, 0, "{:+.0f} dB", conv=bell),
        Param("level", "Level", 0, 1, 0.5),
    ]),
    Pedal("hm2", D.T_HM2, "CHAINSAW", "#1a1a1a", "Metal",
          "HM-2 style Swedish death metal buzzsaw - crank everything", [
              Param("dist", "Dist", 0, 1, 0.8),
              Param("low", "Low", 0, 1, 1.0),
              Param("high", "High", 0, 1, 1.0),
              Param("level", "Level", 0, 1, 0.5),
          ], ink="#ff7043", text="#ff8a65"),
    Pedal("mzone", D.T_MZONE, "METAL CORE", "#212121", "Metal",
          "Metal Zone style high gain with a sweepable middle", [
              Param("dist", "Dist", 0, 1, 0.6),
              Param("low", "Low", -15, 15, 4, "{:+.0f} dB"),
              Param("high", "High", -15, 15, 2, "{:+.0f} dB"),
              Param("mid", "Middle", -15, 15, -4, "{:+.0f} dB"),
              Param("freq", "Mid Freq", 200, 5000, 800, "{:.0f} Hz", log=True),
              Param("level", "Level", 0, 1, 0.5),
          ], ink="#ef5350", text="#eceff1"),
    Pedal("eq", D.T_EQ, "GRAPHIC EQ", "#b0bec5", "Filter", "6-band graphic equalizer", [
        Param("b100", "100", -12, 12, 0, "{:+.0f}", conv=bell),
        Param("b250", "250", -12, 12, 0, "{:+.0f}", conv=bell),
        Param("b630", "630", -12, 12, 0, "{:+.0f}", conv=bell),
        Param("b1k6", "1.6k", -12, 12, 0, "{:+.0f}", conv=bell),
        Param("b4k", "4k", -12, 12, 0, "{:+.0f}", conv=bell),
        Param("b8k", "8k", -12, 12, 0, "{:+.0f}", conv=bell),
        Param("level", "Level", -12, 12, 0, "{:+.0f} dB", conv=db),
    ]),
    Pedal("amp", D.T_AMP, "AMP", "#3e2723", "Amp", "Tube amp: clean / crunch / lead channels with tone stack", [
        Choice("model", "Channel", ["CLEAN", "CRUNCH", "LEAD", "METAL"], default=1),
        Param("gain", "Gain", 0, 1, 0.5),
        Param("bass", "Bass", 0, 1, 0.5),
        Param("mid", "Middle", 0, 1, 0.5),
        Param("treble", "Treble", 0, 1, 0.5),
        Param("presence", "Presence", 0, 1, 0.3),
        Param("master", "Master", -24, 12, 0, "{:+.0f} dB", conv=db),
        Param("depth", "Depth", 0, 1, 0.3),
    ], ink="#ffb74d", text="#ffcc80"),
    Pedal("mgate", D.T_MGATE, "METAL GATE", "#263238", "Metal",
          "Put it AFTER the amp: listens to your clean guitar, silences the high-gain noise", [
              Param("thresh", "Thresh", -80, -20, -55, "{:.0f} dB", conv=db),
              Param("release", "Release", 5, 300, 40, "{:.0f} ms", log=True, conv=ms),
          ], ink="#4dd0e1", text="#b2ebf2"),
    Pedal("pitch", D.T_PITCH, "PITCH SHIFTER", "#ad1457", "Pitch", "Harmonizer / whammy-style pitch shift", [
        Param("semis", "Semitones", -12, 12, 12, "{:+.0f}", step=1),
        Param("cents", "Detune", -50, 50, 0, "{:+.0f} ct"),
        Param("mix", "Mix", 0, 1, 0.5),
    ], text="#fff"),
    Pedal("ring", D.T_RING, "RING MOD", "#5d4037", "Synth", "Metallic, bell-like ring modulation", [
        Param("freq", "Freq", 30, 2000, 440, "{:.0f} Hz", log=True),
        Param("mix", "Mix", 0, 1, 0.5),
    ], ink="#ffcc80", text="#ffcc80"),
    Pedal("crush", D.T_CRUSH, "BIT CRUSHER", "#37474f", "Synth", "Lo-fi bit depth + sample-rate reduction", [
        Param("bits", "Bits", 2, 16, 8, "{:.0f} bit", step=1),
        Param("ds", "Downsample", 1, 32, 4, "x{:.0f}", log=True, step=1),
        Param("mix", "Mix", 0, 1, 1.0),
    ], ink="#80deea", text="#80deea"),
    Pedal("phaser", D.T_PHASER, "PHASER", "#ff9800", "Modulation", "6-stage swirling phaser", [
        Param("rate", "Rate", 0.05, 5, 0.5, "{:.2f} Hz", log=True),
        Param("depth", "Depth", 0, 1, 0.7),
        Param("fb", "Feedback", 0, 0.9, 0.5),
        Param("mix", "Mix", 0, 1, 0.5),
    ]),
    Pedal("univibe", D.T_UNIVIBE, "UNI-VIBE", "#6a1b9a", "Modulation", "Throbbing 60s photocell chorus/vibrato", [
        Param("rate", "Speed", 0.3, 10, 2.0, "{:.2f} Hz", log=True),
        Param("intensity", "Intensity", 0, 1, 0.7),
        Choice("mode", "Mode", ["CHORUS", "VIBRATO"]),
    ], ink="#ce93d8", text="#fff"),
    Pedal("trem", D.T_TREM, "TREMOLO", "#00acc1", "Modulation", "Volume pulsing - smooth to choppy", [
        Param("rate", "Rate", 0.5, 15, 5.0, "{:.1f} Hz", log=True),
        Param("depth", "Depth", 0, 1, 0.6),
        Param("shape", "Shape", 0, 1, 0.3),
    ]),
    Pedal("vibrato", D.T_VIBRATO, "VIBRATO", "#26a69a", "Modulation", "Pure pitch vibrato", [
        Param("rate", "Rate", 0.5, 10, 5.0, "{:.1f} Hz", log=True),
        Param("depth", "Depth", 0, 1, 0.4),
    ]),
    Pedal("chorus", D.T_CHORUS, "CHORUS", "#29b6f6", "Modulation", "Lush stereo chorus", [
        Param("rate", "Rate", 0.1, 5, 0.8, "{:.2f} Hz", log=True),
        Param("depth", "Depth", 0, 1, 0.5),
        Param("mix", "Mix", 0, 1, 0.6),
    ]),
    Pedal("flanger", D.T_FLANGER, "FLANGER", "#8e24aa", "Modulation", "Jet-plane stereo flanger", [
        Param("rate", "Rate", 0.05, 5, 0.25, "{:.2f} Hz", log=True),
        Param("depth", "Depth", 0, 1, 0.7),
        Param("fb", "Feedback", -0.9, 0.9, 0.6),
        Param("manual", "Manual", 0.3, 5, 1.5, "{:.1f} ms", log=True),
        Param("mix", "Mix", 0, 1, 0.5),
    ], ink="#e1bee7", text="#fff"),
    Pedal("rotary", D.T_ROTARY, "ROTARY", "#795548", "Modulation", "Leslie rotating speaker (slow/fast)", [
        Choice("speed", "Speed", ["SLOW", "FAST"]),
        Param("drive", "Drive", 0, 1, 0.2),
        Param("balance", "Horn/Drum", 0, 1, 0.5),
        Param("mix", "Mix", 0, 1, 1.0),
    ], ink="#ffe0b2", text="#ffe0b2"),
    Pedal("pan", D.T_PAN, "AUTO-PAN", "#9ccc65", "Modulation", "Sweeps the sound left-right (stereo)", [
        Param("rate", "Rate", 0.1, 8, 1.0, "{:.2f} Hz", log=True),
        Param("depth", "Depth", 0, 1, 0.8),
    ]),
    Pedal("doubler", D.T_DOUBLER, "DOUBLER", "#37474f", "Metal",
          "Sounds like two guitars tracked left and right - huge rhythm tone", [
              Param("time", "Time", 8, 40, 18, "{:.0f} ms", conv=ms),
              Param("var", "Variation", 0, 1, 0.5),
              Param("width", "Width", 0, 1, 1.0),
          ], ink="#90caf9", text="#e3f2fd"),
    Pedal("delay", D.T_DELAY, "DELAY", "#3949ab", "Time", "Digital / analog / ping-pong delay with tap tempo", [
        Param("time", "Time", 20, 2000, 400, "{:.0f} ms", log=True, conv=ms),
        Param("fb", "Feedback", 0, 0.95, 0.35),
        Param("mix", "Mix", 0, 1, 0.35),
        Param("tone", "Tone", 0, 1, 0.6),
        Choice("mode", "Mode", ["DIGITAL", "ANALOG", "PING-PONG"]),
    ], ink="#c5cae9", text="#fff"),
    Pedal("reverb", D.T_REVERB, "REVERB", "#263238", "Time", "Room / hall / plate reverb", [
        Param("decay", "Decay", 0.3, 10, 2.5, "{:.1f} s", log=True),
        Param("tone", "Tone", 0, 1, 0.5),
        Param("mix", "Mix", 0, 1, 0.3),
        Param("predelay", "Pre-delay", 0, 150, 20, "{:.0f} ms", conv=ms),
        Choice("mode", "Space", ["ROOM", "HALL", "PLATE"], default=1),
    ], ink="#80cbc4", text="#80cbc4"),
    Pedal("looper", D.T_LOOPER, "LOOPER", "#212121", "Utility", "60-second loop recorder with overdub", [
        Param("cmd", "Cmd", 0, 3, 0, hidden=True),
        Param("level", "Loop Lvl", 0, 1.5, 1.0),
        Param("clear", "Clear", 0, 1e9, 0, hidden=True),
    ], ink="#ef5350", text="#ef5350"),
    Pedal("drums", D.T_DRUMS, "DRUM MACHINE", "#3e2723", "Utility",
          "Metronome and drum beats to practise riffs - the switch starts/stops it", [
              Param("bpm", "BPM", 40, 300, 120, "{:.0f}", step=1),
              Choice("pattern", "Pattern", ["CLICK", "ROCK", "METAL", "GALLOP", "BLAST"]),
              Param("vol", "Volume", 0, 1, 0.5),
          ], ink="#ffab40", text="#ffe0b2"),
]

BY_KEY = {p.key: p for p in PEDALS}
CATEGORIES = ["Metal", "Dynamics", "Gain", "Amp", "Filter", "Pitch", "Modulation", "Time", "Synth", "Utility"]


def defaults(key):
    vals = {"on": 0}
    for prm in BY_KEY[key].params:
        vals[prm.name] = prm.default
    return vals

"""PedalBoard v2 - a full pedalboard for the Focusrite Scarlett Solo.

25 pedals you can add, remove and re-order, stereo effects, tuner, looper,
presets and MIDI expression / program-change support.

Run:  pythonw app_v2.py   (or double-click "PedalBoard v2.bat")
"""
import json
import math
import os
import sys
import time
import tkinter as tk
from collections import deque
from tkinter import messagebox, simpledialog, ttk

from widgets_v2 import (BG, DIM, TEXT, Footswitch, Knob, Meter, Segmented, TunerDisplay,
                        WahPedal, detect_pitch, is_light, shade)

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(HERE, "settings_v2.json")
PRESETS_FILE = os.path.join(HERE, "presets_v2.json")

PW = 214            # pedal panel width
SIDE = "#2b2e34"    # side column colour

INPUT_CHOICES = ["Input 1 (Mic/XLR)", "Input 2 (Inst)", "Mix 1+2"]
INPUT_CHANNELS = [0, 1, -1]
RATES = [44100, 48000, 88200, 96000]
BUFFERS = [32, 64, 128, 256, 512, 1024]
MIDI_TARGETS = ["Wah position", "Volume", "Whammy (pitch)"]
PLAYER_MODES = ["Backing track", "Through pedals (re-amp)"]
REC_DIR = os.path.join(os.path.expanduser("~"), "Music", "PedalBoard")
SKIP_RESTORE = {("looper", "cmd"), ("looper", "clear")}

DEFAULT_BOARD = ["gate", "comp", "wah", "od", "dist", "chorus", "delay", "reverb", "looper"]

BUILTIN_PRESETS = {
    "Clean": {"board": ["gate", "comp", "reverb"],
              "values": {"comp": {"sustain": 0.3}, "reverb": {"mode": 0, "mix": 0.25, "decay": 1.2}}},
    "Clean Chorus": {"board": ["gate", "comp", "chorus", "delay", "reverb"],
                     "values": {"comp": {"sustain": 0.35}, "delay": {"time": 380, "mix": 0.22, "fb": 0.3},
                                "reverb": {"mix": 0.3}}},
    "Blues Drive": {"board": ["gate", "comp", "od", "reverb"],
                    "values": {"comp": {"sustain": 0.25}, "od": {"drive": 18, "tone": 0.45, "level": 0.7},
                               "reverb": {"mode": 0, "mix": 0.25}}},
    "Classic Rock": {"board": ["gate", "boost", "dist", "delay", "reverb"],
                     "values": {"boost": {"gain": 4}, "dist": {"drive": 18, "mid": 2},
                                "delay": {"time": 350, "mix": 0.18, "fb": 0.25}, "reverb": {"mix": 0.2}}},
    "Metal": {"board": ["gate", "dist", "eq", "delay", "reverb"],
              "values": {"gate": {"thresh": -48}, "dist": {"drive": 42, "tone": 0.55, "mid": -5},
                         "eq": {"b100": 3, "b630": -4, "b4k": 2},
                         "delay": {"on": 0, "time": 420, "mix": 0.15}, "reverb": {"mode": 0, "mix": 0.15}}},
    "Hendrix": {"board": ["wah", "fuzz", "univibe", "reverb"],
                "values": {"wah": {"on": 0}, "fuzz": {"fuzz": 38, "bias": 0.1, "tone": 0.6},
                           "univibe": {"rate": 1.8, "intensity": 0.75}, "reverb": {"mode": 0, "mix": 0.2}}},
    "Gilmour Lead": {"board": ["gate", "comp", "fuzz", "delay", "reverb"],
                     "values": {"comp": {"sustain": 0.4}, "fuzz": {"fuzz": 42, "bias": 0.0, "tone": 0.45},
                                "delay": {"time": 480, "fb": 0.4, "mix": 0.3},
                                "reverb": {"decay": 3.5, "mix": 0.3}}},
    "Funk": {"board": ["comp", "envf", "phaser", "reverb"],
             "values": {"comp": {"sustain": 0.6}, "envf": {"sens": 0.55, "q": 5},
                        "phaser": {"rate": 0.3, "mix": 0.4}, "reverb": {"mode": 0, "mix": 0.15}}},
    "Wah Funk-Rock": {"board": ["gate", "wah", "od", "delay"],
                      "values": {"od": {"drive": 20}, "delay": {"time": 300, "mix": 0.15}}},
    "Ambient Swells": {"board": ["swell", "chorus", "delay", "reverb"],
                       "values": {"swell": {"attack": 700}, "delay": {"time": 650, "fb": 0.55, "mix": 0.45},
                                  "reverb": {"decay": 7, "mix": 0.55}}},
    "Surf": {"board": ["trem", "reverb"],
             "values": {"trem": {"rate": 6, "depth": 0.5}, "reverb": {"mode": 2, "decay": 2.5, "mix": 0.45,
                                                                       "predelay": 0}}},
    "80s Shred": {"board": ["gate", "comp", "dist", "chorus", "delay", "reverb"],
                  "values": {"dist": {"drive": 32}, "chorus": {"mix": 0.4},
                             "delay": {"time": 420, "mix": 0.25}}},
    "Leslie Organ-ish": {"board": ["comp", "octave", "rotary", "reverb"],
                         "values": {"octave": {"sub1": 0.5, "up": 0.4}, "rotary": {"drive": 0.3},
                                    "reverb": {"mode": 0, "mix": 0.2}}},
    "Lo-Fi Synth": {"board": ["gate", "octave", "envf", "crush"],
                    "values": {"octave": {"dry": 0.3, "sub1": 0.8}, "envf": {"q": 6},
                               "crush": {"bits": 6, "ds": 6, "mix": 0.5}}},
    "Harmony Lead": {"board": ["gate", "dist", "pitch", "delay", "reverb"],
                     "values": {"pitch": {"semis": 12, "mix": 0.35}, "delay": {"time": 400, "mix": 0.2}}},
    "Jet Flanger": {"board": ["gate", "dist", "flanger", "reverb"],
                    "values": {"dist": {"drive": 22}, "reverb": {"mix": 0.2}}},
    "Amp: Clean + Chorus": {"board": ["comp", "amp", "chorus", "delay", "reverb"],
                            "values": {"comp": {"sustain": 0.3}, "amp": {"model": 0, "gain": 0.35, "treble": 0.6},
                                       "delay": {"time": 380, "mix": 0.2}, "reverb": {"mix": 0.25}}},
    "Amp: British Crunch": {"board": ["gate", "amp", "reverb"],
                            "values": {"amp": {"model": 1, "gain": 0.6, "mid": 0.65, "presence": 0.4},
                                       "reverb": {"mode": 0, "mix": 0.2}}},
    "Amp: Boosted Lead": {"board": ["gate", "od", "amp", "delay", "reverb"],
                          "values": {"gate": {"thresh": -52}, "od": {"drive": 2, "tone": 0.5, "level": 0.9},
                                     "amp": {"model": 2, "gain": 0.65, "bass": 0.45, "mid": 0.6},
                                     "delay": {"time": 440, "mix": 0.22}, "reverb": {"mix": 0.22}}},
    "Metal: Modern High-Gain": {"board": ["tboost", "amp", "mgate", "eq", "delay", "reverb"],
                                "values": {"tboost": {"tight": 350, "gain": 6},
                                           "amp": {"model": 3, "gain": 0.7, "bass": 0.55, "mid": 0.4,
                                                   "treble": 0.55, "presence": 0.5, "depth": 0.5},
                                           "mgate": {"thresh": -55},
                                           "eq": {"b630": -3, "b4k": 1},
                                           "delay": {"on": 0, "time": 380, "mix": 0.15},
                                           "reverb": {"mode": 0, "mix": 0.12}}},
    "Metal: Djent": {"board": ["tboost", "amp", "mgate", "eq", "doubler", "reverb"],
                     "values": {"tboost": {"tight": 500, "gain": 10, "tone": 3},
                                "amp": {"model": 3, "gain": 0.6, "bass": 0.4, "mid": 0.55, "treble": 0.6,
                                        "presence": 0.6, "depth": 0.35},
                                "mgate": {"thresh": -50, "release": 15},
                                "eq": {"b250": -3, "b1k6": 2}, "reverb": {"mode": 0, "mix": 0.1}}},
    "Metal: Swedish Death": {"board": ["hm2", "amp", "mgate", "reverb"],
                             "values": {"hm2": {"dist": 0.85, "low": 1.0, "high": 1.0, "level": 0.6},
                                        "amp": {"model": 1, "gain": 0.45, "mid": 0.5},
                                        "mgate": {"thresh": -52}, "reverb": {"mode": 0, "mix": 0.15}}},
    "Metal: Thrash": {"board": ["mzone", "amp", "mgate", "delay"],
                      "values": {"mzone": {"dist": 0.55, "low": 6, "high": 3, "mid": -8, "freq": 700},
                                 "amp": {"model": 2, "gain": 0.4},
                                 "mgate": {"thresh": -52, "release": 25},
                                 "delay": {"on": 0, "time": 300, "mix": 0.12}}},
    "Metal: Drop C Riffs": {"board": ["drop", "tboost", "amp", "mgate", "doubler"],
                            "values": {"drop": {"semis": 3, "quality": 1},
                                       "tboost": {"tight": 300, "gain": 8},
                                       "amp": {"model": 3, "gain": 0.65, "mid": 0.45, "depth": 0.45},
                                       "mgate": {"thresh": -55}}},
    "Metal: Shred Lead": {"board": ["comp", "tboost", "amp", "mgate", "delay", "reverb"],
                          "values": {"comp": {"sustain": 0.4},
                                     "tboost": {"tight": 250, "gain": 10},
                                     "amp": {"model": 2, "gain": 0.75, "mid": 0.65},
                                     "mgate": {"thresh": -60, "release": 80},
                                     "delay": {"time": 420, "fb": 0.35, "mix": 0.25},
                                     "reverb": {"mix": 0.25}}},
    "Practice: Metal Drums": {"board": ["tboost", "amp", "mgate", "drums"],
                              "values": {"amp": {"model": 3, "gain": 0.65},
                                         "drums": {"on": 0, "bpm": 140, "pattern": 2, "vol": 0.5}}},
    "Amp: Modern Metal": {"board": ["gate", "od", "amp", "eq"],
                          "values": {"gate": {"thresh": -46}, "od": {"drive": 0, "tone": 0.6, "level": 0.9},
                                     "amp": {"model": 2, "gain": 0.8, "mid": 0.35, "bass": 0.6, "presence": 0.5},
                                     "eq": {"b100": 2, "b630": -3}}},
}


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


def small_btn(parent, text, cmd, bg, fg, font=("Segoe UI", 8, "bold"), padx=4):
    b = tk.Label(parent, text=text, bg=bg, fg=fg, cursor="hand2", font=font, padx=padx)
    b.bind("<Button-1>", lambda e: cmd())
    return b


class App:
    def __init__(self, root, engine_mod):
        self.root = root
        self.E = engine_mod
        import dsp_v2
        import pedals_v2
        self.D = dsp_v2
        self.PD = pedals_v2

        self.settings = load_json(SETTINGS_FILE, {})
        self.user_presets = load_json(PRESETS_FILE, {})
        self.engine = engine_mod.AudioEngine()
        self.board = [k for k in self.settings.get("board", DEFAULT_BOARD) if k in pedals_v2.BY_KEY]
        self.panels = {}
        self.controls = {}
        self.cols = 0
        self.extras = {}
        self.taps = []
        self.tuner_on = False
        self.tuner_hist = deque(maxlen=3)
        self.tick_n = 0
        self.midi_port = None
        self.midi_cc = self.settings.get("midi_cc")
        self.midi_learning = False
        self.midi_dirty = False
        self.pending_preset = None
        self.pending_status = None
        self.expr_vol = 1.0
        g = self.settings.get("global", {})
        self.glob = {"in_gain_db": g.get("in_gain_db", 0.0), "master_db": g.get("master_db", 0.0),
                     "cab": g.get("cab", 1)}

        root.title("PedalBoard v2 - Scarlett Solo")
        root.configure(bg=BG)
        root.geometry(self.settings.get("geometry", "1290x880"))
        root.minsize(900, 600)

        self._style()
        self._build_header()
        self._build_audio_bar()
        self._build_status()
        self._build_main()

        vals = self.settings.get("values")
        if vals:
            self._apply_values(vals)
        else:
            for k in self.board:
                self.engine.set(k, "on", 1 if k == "gate" else 0)
        ir = self.settings.get("ir_path")
        if ir and os.path.exists(ir):
            try:
                self.engine.load_ir(ir)
                self.ir_lbl.configure(text=self.engine.ir_name, fg=TEXT)
            except Exception:   # noqa: BLE001
                pass
        if self.glob["cab"] == 2 and not self.engine.ir_name:
            self.glob["cab"] = 1
        self._apply_globals()
        self._set_board(self.board)
        self._sync_controls()
        self._populate_audio(initial=True)
        self._bind_keys()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._tick()
        if self.settings.get("autostart", True) and self.audio_found:
            root.after(300, self.start_audio)

    # ================================================================ layout
    def _style(self):
        st = ttk.Style()
        st.theme_use("clam")
        st.configure("TCombobox", fieldbackground="#2a2a30", background="#2a2a30",
                     foreground=TEXT, arrowcolor=TEXT, bordercolor="#444")
        st.map("TCombobox", fieldbackground=[("readonly", "#2a2a30")],
               foreground=[("readonly", TEXT)], selectbackground=[("readonly", "#2a2a30")],
               selectforeground=[("readonly", TEXT)])
        self.root.option_add("*TCombobox*Listbox.background", "#2a2a30")
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        st.configure("TCheckbutton", background=BG, foreground=TEXT)
        st.map("TCheckbutton", background=[("active", BG)])
        st.configure("Side.TCheckbutton", background=SIDE, foreground=TEXT)
        st.map("Side.TCheckbutton", background=[("active", SIDE)])
        st.configure("Vertical.TScrollbar", background="#34343c", troughcolor=BG, arrowcolor=TEXT)
        self.root.bind_class("TCombobox", "<<ComboboxSelected>>", lambda e: self.root.focus_set(), add="+")

    def _btn(self, parent, text, cmd, bg="#34343c", fg=TEXT):
        b = tk.Label(parent, text=text, bg=bg, fg=fg, padx=10, pady=4, cursor="hand2",
                     font=("Segoe UI", 9, "bold"))
        b.bind("<Button-1>", lambda e: cmd())
        return b

    def _build_header(self):
        f = tk.Frame(self.root, bg=BG)
        f.pack(fill="x", padx=14, pady=(10, 2))
        tk.Label(f, text="PEDALBOARD", bg=BG, fg=TEXT, font=("Segoe UI Black", 18)).pack(side="left")
        tk.Label(f, text=" v2", bg=BG, fg="#d9b44a", font=("Segoe UI Black", 12)).pack(side="left", pady=(6, 0))
        self.add_btn = tk.Menubutton(f, text="＋ ADD PEDAL", bg="#d9b44a", fg="#111", activebackground="#e8c65c",
                                     font=("Segoe UI", 9, "bold"), relief="flat", padx=10, pady=4, cursor="hand2")
        self.add_menu = tk.Menu(self.add_btn, tearoff=0, bg="#2a2a30", fg=TEXT, activebackground="#d9b44a",
                                activeforeground="#111")
        self.add_btn["menu"] = self.add_menu
        self.add_btn.pack(side="left", padx=(18, 0))
        self._btn(f, "Clear board", self.clear_board).pack(side="left", padx=6)
        self._btn(f, "Delete", self.delete_preset).pack(side="right", padx=(4, 0))
        self._btn(f, "Save As…", self.save_preset).pack(side="right", padx=(4, 0))
        self.preset_var = tk.StringVar()
        self.preset_box = ttk.Combobox(f, textvariable=self.preset_var, state="readonly", width=24)
        self.preset_box.pack(side="right")
        self.preset_box.bind("<<ComboboxSelected>>", lambda e: self.load_preset(self.preset_var.get()))
        tk.Label(f, text="Preset ", bg=BG, fg=DIM).pack(side="right")
        self._refresh_presets()

    def _build_audio_bar(self):
        f = tk.Frame(self.root, bg=BG)
        f.pack(fill="x", padx=14, pady=2)

        def lab(t, c):
            tk.Label(f, text=t, bg=BG, fg=DIM, font=("Segoe UI", 8)).grid(row=0, column=c, sticky="w", padx=3)

        s = self.settings
        self.api_var, self.in_var, self.out_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.ch_var = tk.StringVar(value=INPUT_CHOICES[s.get("in_choice", 1)])
        self.sr_var = tk.StringVar(value=str(s.get("samplerate", 48000)))
        self.bs_var = tk.StringVar(value=str(s.get("blocksize", 256)))
        self.excl_var = tk.BooleanVar(value=s.get("exclusive", True))

        lab("Driver", 0)
        self.api_box = ttk.Combobox(f, textvariable=self.api_var, state="readonly", width=15)
        self.api_box.grid(row=1, column=0, padx=3)
        self.api_box.bind("<<ComboboxSelected>>", lambda e: self._populate_devices())
        lab("Input device", 1)
        self.in_box = ttk.Combobox(f, textvariable=self.in_var, state="readonly", width=28)
        self.in_box.grid(row=1, column=1, padx=3)
        lab("Output device", 2)
        self.out_box = ttk.Combobox(f, textvariable=self.out_var, state="readonly", width=28)
        self.out_box.grid(row=1, column=2, padx=3)
        lab("Guitar plugged into", 3)
        ttk.Combobox(f, textvariable=self.ch_var, values=INPUT_CHOICES, state="readonly",
                     width=16).grid(row=1, column=3, padx=3)
        lab("Rate", 4)
        ttk.Combobox(f, textvariable=self.sr_var, values=[str(r) for r in RATES], state="readonly",
                     width=6).grid(row=1, column=4, padx=3)
        lab("Buffer", 5)
        ttk.Combobox(f, textvariable=self.bs_var, values=[str(b) for b in BUFFERS], state="readonly",
                     width=5).grid(row=1, column=5, padx=3)
        self.excl_chk = ttk.Checkbutton(f, text="WASAPI exclusive", variable=self.excl_var)
        self.excl_chk.grid(row=1, column=6, padx=6)
        self._btn(f, "Rescan", self.rescan).grid(row=1, column=7, padx=3)
        self.power_btn = self._btn(f, "  START  ", self.toggle_audio, bg="#2e7d32", fg="white")
        self.power_btn.grid(row=1, column=8, padx=(8, 0))

        m = tk.Frame(self.root, bg=BG)
        m.pack(fill="x", padx=14, pady=(2, 4))
        tk.Label(m, text="MIDI controller:", bg=BG, fg=DIM, font=("Segoe UI", 8)).pack(side="left", padx=3)
        self.midi_var = tk.StringVar()
        self.midi_box = ttk.Combobox(m, textvariable=self.midi_var, state="readonly", width=28)
        self.midi_box.pack(side="left", padx=3)
        self.midi_box.bind("<<ComboboxSelected>>", lambda e: self.open_midi())
        tk.Label(m, text="expression pedal controls", bg=BG, fg=DIM, font=("Segoe UI", 8)).pack(side="left", padx=3)
        self.midi_target = tk.StringVar(value=s.get("midi_target", MIDI_TARGETS[0]))
        ttk.Combobox(m, textvariable=self.midi_target, values=MIDI_TARGETS, state="readonly",
                     width=15).pack(side="left", padx=3)
        self._btn(m, "Learn CC", self.midi_learn).pack(side="left", padx=3)
        self.midi_lbl = tk.Label(m, bg=BG, fg=DIM, font=("Segoe UI", 8))
        self.midi_lbl.pack(side="left", padx=6)
        self._populate_midi()

        # transport: file player + recorder
        t = tk.Frame(self.root, bg="#1f1f25")
        t.pack(fill="x", padx=14, pady=(0, 4))
        tk.Label(t, text="PLAYER", bg="#1f1f25", fg=TEXT, font=("Segoe UI", 8, "bold")).pack(side="left", padx=(8, 4))
        self._btn(t, "Open WAV…", self.open_player_file).pack(side="left", padx=2, pady=3)
        self.play_btn = self._btn(t, "▶", self.toggle_player, bg="#2e7d32", fg="white")
        self.play_btn.pack(side="left", padx=2)
        self.player_lbl = tk.Label(t, text="no file", bg="#1f1f25", fg=DIM, font=("Segoe UI", 8), width=22,
                                   anchor="w")
        self.player_lbl.pack(side="left", padx=4)
        self.ptime_lbl = tk.Label(t, text="", bg="#1f1f25", fg=DIM, font=("Consolas", 8), width=11)
        self.ptime_lbl.pack(side="left")
        self.pmode_var = tk.StringVar(value=s.get("player_mode", PLAYER_MODES[0]))
        cb = ttk.Combobox(t, textvariable=self.pmode_var, values=PLAYER_MODES, state="readonly", width=21)
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", self._player_settings)
        self.loop_var = tk.BooleanVar(value=s.get("player_loop", True))
        ttk.Checkbutton(t, text="Loop", variable=self.loop_var, command=self._player_settings).pack(side="left", padx=4)
        tk.Label(t, text="Vol", bg="#1f1f25", fg=DIM, font=("Segoe UI", 8)).pack(side="left")
        self.pvol_var = tk.DoubleVar(value=s.get("player_vol", 0.7))
        ttk.Scale(t, from_=0.0, to=1.5, variable=self.pvol_var, length=90,
                  command=self._player_settings).pack(side="left", padx=4)
        self._btn(t, "Folder", self.open_rec_folder).pack(side="right", padx=(2, 8))
        self.rec_time = tk.Label(t, text="", bg="#1f1f25", fg=DIM, font=("Consolas", 9), width=6)
        self.rec_time.pack(side="right")
        self.rec_btn = self._btn(t, "● REC", self.toggle_record, bg="#4a1c1c", fg="#ff6b6b")
        self.rec_btn.pack(side="right", padx=2)
        tk.Label(t, text="RECORDER", bg="#1f1f25", fg=TEXT, font=("Segoe UI", 8, "bold")).pack(side="right", padx=4)
        self._player_settings()

    def _build_status(self):
        f = tk.Frame(self.root, bg="#0f0f12")
        f.pack(fill="x", side="bottom")
        self.status = tk.Label(f, text="Stopped", bg="#0f0f12", fg=TEXT, anchor="w", font=("Segoe UI", 9))
        self.status.pack(fill="x", padx=10, pady=(4, 0))
        tk.Label(f, bg="#0f0f12", fg=DIM, anchor="w", font=("Segoe UI", 8), justify="left",
                 text="Guitar → INST jack (input 2), INST on · DIRECT MONITOR OFF · gain halo green, not red.   "
                      "Keys: 1-9 stomp pedal # · W wah · ↑/↓ rock wah · T tuner · L looper rec/play/dub · "
                      "K looper stop · ◀ ▶ reorder · ✕ remove").pack(fill="x", padx=10, pady=(0, 6))

    def _build_main(self):
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill="both", expand=True, padx=8, pady=4)

        # ---- left column: input + tuner
        left = tk.Frame(main, bg=SIDE, width=170)
        left.pack(side="left", fill="y", padx=(0, 6))
        tk.Label(left, text="INPUT", bg=SIDE, fg=TEXT, font=("Segoe UI Black", 12)).pack(pady=(8, 2))
        row = tk.Frame(left, bg=SIDE)
        row.pack()
        self.in_meter = Meter(row, bg=SIDE, label="IN", height=110)
        self.in_meter.pack(side="left", padx=4)
        self.gain_knob = Knob(row, "Gain", -12, 24, 0.0, lambda v: self._set_glob("in_gain_db", v),
                              fmt="{:+.0f} dB", color="#9ccc65", bg=SIDE, size=48)
        self.gain_knob.pack(side="left")
        tk.Frame(left, bg="#444", height=1).pack(fill="x", padx=10, pady=10)
        tk.Label(left, text="TUNER", bg=SIDE, fg=TEXT, font=("Segoe UI Black", 12)).pack()
        self.tuner = TunerDisplay(left, bg=SIDE, width=150)
        self.tuner.pack(padx=8, pady=4)
        self.tuner.show(None, active=False)
        self.tuner_mute = tk.BooleanVar(value=self.settings.get("tuner_mute", True))
        ttk.Checkbutton(left, text="Mute while tuning", variable=self.tuner_mute, style="Side.TCheckbutton",
                        command=self._apply_mute).pack()
        self.tuner_sw = Footswitch(left, lambda v: self.set_tuner(bool(v)), bg=SIDE, led="#4fc3f7")
        self.tuner_sw.pack(pady=4)

        # ---- right column: output
        right = tk.Frame(main, bg=SIDE, width=150)
        right.pack(side="right", fill="y", padx=(6, 0))
        tk.Label(right, text="OUTPUT", bg=SIDE, fg=TEXT, font=("Segoe UI Black", 12)).pack(pady=(8, 2))
        row = tk.Frame(right, bg=SIDE)
        row.pack()
        col = tk.Frame(row, bg=SIDE)
        col.pack(side="left")
        self.master_knob = Knob(col, "Master", -30, 12, 0.0, lambda v: self._set_glob("master_db", v),
                                fmt="{:+.0f} dB", color="#9ccc65", bg=SIDE, size=48)
        self.master_knob.pack()
        self.clip_led = tk.Label(col, text="CLIP", bg="#2a2a30", fg="#555", font=("Segoe UI", 8, "bold"), padx=6)
        self.clip_led.pack(pady=6)
        self.out_meter = Meter(row, bg=SIDE, label="OUT", height=110)
        self.out_meter.pack(side="left", padx=4)
        tk.Frame(right, bg="#444", height=1).pack(fill="x", padx=10, pady=10)
        tk.Label(right, text="CABINET", bg=SIDE, fg=TEXT, font=("Segoe UI", 9, "bold")).pack()
        tk.Label(right, text="speaker voicing for\nheadphones / monitors", bg=SIDE, fg=DIM,
                 font=("Segoe UI", 7)).pack()
        self.cab_sw = Segmented(right, ["OFF", "BASIC", "IR"], lambda i: self._set_cab(i), bg=SIDE,
                                on_bg="#34c759", on_fg="#111")
        self.cab_sw.pack(pady=(6, 4))
        small_btn(right, "Load IR…", self.load_ir, "#34343c", TEXT, padx=8).pack(pady=2)
        self.ir_lbl = tk.Label(right, text="no IR loaded", bg=SIDE, fg=DIM, font=("Segoe UI", 7),
                               wraplength=130)
        self.ir_lbl.pack(pady=(2, 0))
        tk.Label(right, text="IRs: free cab impulse\nresponses (.wav) online", bg=SIDE, fg=DIM,
                 font=("Segoe UI", 7)).pack(pady=(6, 0))

        # ---- centre: scrollable board
        mid = tk.Frame(main, bg=BG)
        mid.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(mid, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_resize)
        self.empty_lbl = tk.Label(self.inner, text="Your board is empty - click ＋ ADD PEDAL or pick a preset.",
                                  bg=BG, fg=DIM, font=("Segoe UI", 11))
        self.root.bind_all("<MouseWheel>", self._board_wheel, add="+")

    def _board_wheel(self, e):
        if isinstance(e.widget, (Knob, WahPedal)):
            return
        if str(e.widget).startswith(str(self.canvas)):
            self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")

    def _on_resize(self, e):
        cols = max(1, (e.width - 4) // (PW + 12))
        if cols != self.cols:
            self.cols = cols
            self._regrid()

    # ================================================================ pedal panels
    def _panel(self, key):
        if key in self.panels:
            return self.panels[key]
        ped = self.PD.BY_KEY[key]
        c, txt, ink = ped.color, ped.text, ped.ink
        light = is_light(c)
        f = tk.Frame(self.inner, bg=c, highlightthickness=1, highlightbackground=shade(c, 0.6))
        tk.Frame(f, bg=c, width=PW, height=0).pack()

        top = tk.Frame(f, bg=c)
        top.pack(fill="x", padx=4, pady=(4, 0))
        badge = tk.Label(top, text="", bg=shade(c, 0.7 if light else 1.5), fg="#111" if not light else "#fff",
                         font=("Segoe UI", 7, "bold"), width=2)
        badge.pack(side="left")
        btn_bg = shade(c, 0.82) if light else shade(c, 1.3)
        small_btn(top, "✕", lambda: self.remove_pedal(key), btn_bg, txt).pack(side="right", padx=1)
        small_btn(top, "▶", lambda: self.move_pedal(key, 1), btn_bg, txt).pack(side="right", padx=1)
        small_btn(top, "◀", lambda: self.move_pedal(key, -1), btn_bg, txt).pack(side="right", padx=1)
        tk.Label(f, text=ped.title, bg=c, fg=txt, font=("Segoe UI Black", 12)).pack()
        tk.Label(f, text=ped.desc, bg=c, fg=txt, font=("Segoe UI", 7), wraplength=PW - 16,
                 justify="center").pack(padx=6)

        if key == "wah":
            wp = WahPedal(f, lambda v: self.set_param("wah", "pos", v), bg=c, width=PW - 14, height=118)
            wp.pack(pady=(2, 0))
            self.extras["wah_pedal"] = wp

        seg_on_bg = "#111" if light else txt
        seg_off_bg = shade(c, 0.78) if light else shade(c, 1.35)
        for prm in ped.params:
            if prm.choices:
                seg = Segmented(f, prm.choices, lambda i, n=prm.name: self.set_param(key, n, i), bg=c,
                                on_bg=seg_on_bg, on_fg=c if light else "#111", off_bg=seg_off_bg,
                                off_fg=txt)
                seg.pack(pady=(5, 0))
                self.controls[(key, prm.name)] = seg

        grid = tk.Frame(f, bg=c)
        grid.pack(pady=(4, 0))
        knobs = [prm for prm in ped.params if not prm.choices and not prm.hidden]
        for i, prm in enumerate(knobs):
            k = Knob(grid, prm.label, prm.lo, prm.hi, prm.default,
                     lambda v, n=prm.name: self.set_param(key, n, v), fmt=prm.fmt, log=prm.log,
                     color=ink, bg=c, text=txt, step=prm.step)
            k.grid(row=i // 3, column=i % 3)
            self.controls[(key, prm.name)] = k

        if key == "delay":
            small_btn(f, "TAP TEMPO", self.tap_tempo, "#111" if light else txt, c,
                      padx=10).pack(pady=(4, 0))
        if key == "looper":
            self._looper_controls(f, ped)
        else:
            sw = Footswitch(f, lambda v: self.set_param(key, "on", v), bg=c)
            sw.pack(side="bottom", pady=(4, 6))
            self.controls[(key, "on")] = sw
        f.badge = badge
        self.panels[key] = f
        self._sync_panel(key)
        return f

    def _looper_controls(self, f, ped):
        c = ped.color
        st = tk.Label(f, text="EMPTY", bg=c, fg=DIM, font=("Segoe UI", 11, "bold"))
        st.pack(pady=(4, 0))
        bar = tk.Canvas(f, width=PW - 30, height=8, bg="#333", highlightthickness=0)
        bar.pack(pady=3)
        row = tk.Frame(f, bg=c)
        row.pack(side="bottom", pady=(4, 6))
        small_btn(row, "STOP", self.looper_stop, "#444", TEXT, padx=8).pack(side="left", padx=4)
        main = Footswitch(row, lambda v: self.looper_press(), bg=c, led="#ff3b30", momentary=True, label="REC")
        main.pack(side="left", padx=4)
        small_btn(row, "CLEAR", self.looper_clear, "#444", TEXT, padx=8).pack(side="left", padx=4)
        self.extras["looper"] = (st, bar, main)

    def _regrid(self):
        for k, p in self.panels.items():
            if k not in self.board:
                p.grid_forget()
        if not self.board:
            self.empty_lbl.grid(row=0, column=0, padx=20, pady=40)
        else:
            self.empty_lbl.grid_forget()
        cols = max(1, self.cols)
        for i, k in enumerate(self.board):
            p = self._panel(k)
            p.grid(row=i // cols, column=i % cols, padx=6, pady=6, sticky="n")
            p.badge.configure(text=str(i + 1))
        self._rebuild_add_menu()

    def _rebuild_add_menu(self):
        m = self.add_menu
        m.delete(0, "end")
        for cat in self.PD.CATEGORIES:
            sub = tk.Menu(m, tearoff=0, bg="#2a2a30", fg=TEXT, activebackground="#d9b44a",
                          activeforeground="#111")
            for ped in self.PD.PEDALS:
                if ped.category == cat:
                    on_board = ped.key in self.board
                    sub.add_command(label=f"{ped.title.title()}  –  {ped.desc}",
                                    command=lambda k=ped.key: self.add_pedal(k),
                                    state="disabled" if on_board else "normal")
            m.add_cascade(label=cat, menu=sub)

    # ================================================================ board ops
    def _set_board(self, keys):
        self.board = list(keys)
        self.engine.set_board(self.board)
        self._regrid()

    def add_pedal(self, key):
        if key in self.board:
            return
        order = [p.key for p in self.PD.PEDALS]
        idx = len(self.board)
        for i, k in enumerate(self.board):      # natural slot: before the first pedal that comes later
            if order.index(k) > order.index(key):
                idx = i
                break
        self.board.insert(idx, key)
        if key not in ("looper", "drums"):      # don't start the drums by surprise
            self.set_param(key, "on", 1)
            self._sync_panel(key)
        self._set_board(self.board)
        self.root.after(50, lambda: self._scroll_to(key))

    def _scroll_to(self, key):
        p = self.panels.get(key)
        h = self.inner.winfo_height()
        if p and h > 0:
            self.canvas.yview_moveto(max(0.0, (p.winfo_y() - 10) / h))

    def remove_pedal(self, key):
        if key in self.board:
            self.board.remove(key)
            self._set_board(self.board)

    def move_pedal(self, key, d):
        i = self.board.index(key)
        j = i + d
        if 0 <= j < len(self.board):
            self.board[i], self.board[j] = self.board[j], self.board[i]
            self._set_board(self.board)

    def clear_board(self):
        if self.board and messagebox.askyesno("Clear board", "Remove all pedals from the board?",
                                              parent=self.root):
            self._set_board([])

    # ================================================================ params / presets
    def set_param(self, key, name, value):
        self.engine.set(key, name, value)

    def _set_glob(self, name, v):
        self.glob[name] = v
        self._apply_globals()

    # ---- cabinet IR
    def _set_cab(self, i):
        if i == 2 and not self.engine.ir_name:
            self.load_ir()
            if not self.engine.ir_name:
                self.cab_sw.set_value(self.glob["cab"])
                return
        self._set_glob("cab", i)

    def load_ir(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(parent=self.root, title="Load cabinet impulse response",
                                          filetypes=[("WAV files", "*.wav"), ("All files", "*.*")],
                                          initialdir=self.settings.get("ir_dir") or os.path.expanduser("~"))
        if not path:
            return
        self._load_ir_path(path, show_errors=True)

    def _load_ir_path(self, path, show_errors=False):
        try:
            self.engine.load_ir(path)
        except Exception as e:   # noqa: BLE001
            if show_errors:
                messagebox.showerror("Impulse response", f"Couldn't load that file:\n{e}", parent=self.root)
            return
        self.settings["ir_dir"] = os.path.dirname(path)
        self.ir_lbl.configure(text=self.engine.ir_name, fg=TEXT)
        self._set_glob("cab", 2)

    # ---- file player / recorder
    def open_player_file(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(parent=self.root, title="Open audio file (WAV)",
                                          filetypes=[("WAV files", "*.wav"), ("All files", "*.*")],
                                          initialdir=self.settings.get("player_dir") or REC_DIR)
        if not path:
            return
        try:
            self.engine.load_player(path)
        except Exception as e:   # noqa: BLE001
            messagebox.showerror("Player", f"Couldn't open that file:\n{e}\n\nOnly WAV files are supported.",
                                 parent=self.root)
            return
        self.settings["player_dir"] = os.path.dirname(path)
        self.player_lbl.configure(text=os.path.basename(path), fg=TEXT)

    def toggle_player(self):
        e = self.engine
        if e.player_data is None:
            self.open_player_file()
            if e.player_data is None:
                return
        if not e.running:
            self.status.configure(text="Start audio before playing a file.")
            return
        e.player_playing = not e.player_playing

    def _player_settings(self, *_):
        e = self.engine
        e.player_loop = bool(self.loop_var.get())
        e.player_mode = "through" if self.pmode_var.get() == PLAYER_MODES[1] else "backing"
        e.player_vol = float(self.pvol_var.get())

    def toggle_record(self):
        e = self.engine
        if e.rec_out is None:
            if not e.running:
                self.status.configure(text="Start audio before recording.")
                return
            e.rec_start()
            return
        os.makedirs(REC_DIR, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H-%M-%S")
        out = os.path.join(REC_DIR, f"PedalBoard {stamp}.wav")
        di = os.path.join(REC_DIR, f"PedalBoard {stamp} (DI).wav")

        def done(err):   # runs on the saver thread; _tick shows it
            self.pending_status = (f"Recording save failed: {err}" if err
                                   else f"Saved recording to {out} (+ clean DI copy)")
        e.rec_stop(out, di, done)
        self.status.configure(text="Saving recording…")

    def open_rec_folder(self):
        os.makedirs(REC_DIR, exist_ok=True)
        os.startfile(REC_DIR)

    def _apply_globals(self):
        g = self.glob
        self.engine.set_global(in_gain_db=g["in_gain_db"], cab=g["cab"])
        vol = max(self.expr_vol, 1e-4)
        self.engine.set_global(master_db=g["master_db"] + 20 * math.log10(vol))
        self.gain_knob.set_value(g["in_gain_db"])
        self.master_knob.set_value(g["master_db"])
        self.cab_sw.set_value(g["cab"])

    def _apply_mute(self):
        self.engine.set_global(mute=1 if (self.tuner_on and self.tuner_mute.get()) else 0)

    def _apply_values(self, values):
        for key in self.PD.BY_KEY:
            base = self.PD.defaults(key)
            base.update(values.get(key, {}))
            for name, v in base.items():
                if (key, name) in SKIP_RESTORE:
                    continue
                self.engine.set(key, name, v)

    def _sync_panel(self, key):
        for (k, name), w in self.controls.items():
            if k == key:
                w.set_value(self.engine.values[key][name])

    def _sync_controls(self):
        for (k, name), w in self.controls.items():
            w.set_value(self.engine.values[k][name])

    def _all_presets(self):
        return {**BUILTIN_PRESETS, **self.user_presets}

    def _refresh_presets(self):
        self.preset_box["values"] = list(self._all_presets())

    def load_preset(self, name):
        p = self._all_presets().get(name)
        if not p:
            return
        board = [k for k in p.get("board", []) if k in self.PD.BY_KEY]
        vals = {}
        for k in board:
            vals[k] = {"on": 0 if k in ("looper", "drums") else 1}
        for k, d in p.get("values", {}).items():
            vals.setdefault(k, {}).update(d)
        self._apply_values(vals)
        self._set_board(board)
        self._sync_controls()
        self.preset_var.set(name)

    def save_preset(self):
        name = simpledialog.askstring("Save preset", "Preset name:", parent=self.root)
        if not name:
            return
        vals = {k: {n: v for n, v in d.items() if (k, n) not in SKIP_RESTORE}
                for k, d in self.engine.values.items() if k in self.board}
        self.user_presets[name] = {"board": list(self.board), "values": vals}
        save_json(PRESETS_FILE, self.user_presets)
        self._refresh_presets()
        self.preset_var.set(name)

    def delete_preset(self):
        name = self.preset_var.get()
        if name in self.user_presets:
            del self.user_presets[name]
            save_json(PRESETS_FILE, self.user_presets)
            self._refresh_presets()
            self.preset_var.set("")
        elif name:
            messagebox.showinfo("Preset", "Built-in presets can't be deleted.", parent=self.root)

    # ================================================================ special controls
    def tap_tempo(self):
        now = time.monotonic()
        if self.taps and now - self.taps[-1] > 2.5:
            self.taps = []
        self.taps.append(now)
        self.taps = self.taps[-4:]
        if len(self.taps) >= 2:
            iv = [b - a for a, b in zip(self.taps, self.taps[1:])]
            ms = min(2000, max(20, 1000 * sum(iv) / len(iv)))
            self.controls[("delay", "time")].set_value(ms, notify=True)

    def _loop_state(self):
        D = self.D
        return (int(self.engine.pedal_state("looper", D.S_LOOP_EFF)),
                self.engine.pedal_state("looper", D.S_LOOP_HAS) > 0.5)

    def looper_press(self):
        if "looper" not in self.board:
            return
        eff, has = self._loop_state()
        if not self.engine.running:
            self.status.configure(text="Start audio before using the looper.")
            return
        cmd = {0: 2 if has else 1, 1: 2, 2: 3, 3: 2}[eff]
        self.set_param("looper", "cmd", cmd)

    def looper_stop(self):
        self.set_param("looper", "cmd", 0)

    def looper_clear(self):
        self.set_param("looper", "cmd", 0)
        self.set_param("looper", "clear", self.engine.values["looper"]["clear"] + 1)

    def set_tuner(self, on):
        self.tuner_on = on
        self.tuner_sw.set_value(on)
        self.tuner_hist.clear()
        self.tuner.show(None, active=on)
        self._apply_mute()

    # ================================================================ audio devices
    def _populate_audio(self, initial=False):
        E = self.E
        apis = E.host_apis()
        self.api_box["values"] = apis
        sug = E.suggest_config()
        self.audio_found = sug["found"]
        saved = self.settings.get("audio") if initial else None
        cfg = sug
        if saved and saved.get("hostapi") in apis:
            if saved.get("input") in [d[1] for d in E.devices_for(saved["hostapi"], "input")]:
                cfg = saved
                self.audio_found = self.audio_found or E.is_focusrite(saved.get("input", ""))
        self.api_var.set(cfg["hostapi"])
        self._populate_devices(cfg.get("input"), cfg.get("output"))
        if not sug["found"]:
            self.status.configure(text="Scarlett not detected - plug it in and press Rescan "
                                       "(install Focusrite Control for the ASIO driver). "
                                       "You can still pick another device.")

    def _populate_devices(self, want_in=None, want_out=None):
        E = self.E
        api = self.api_var.get()
        ins = [d[1] for d in E.devices_for(api, "input")]
        outs = [d[1] for d in E.devices_for(api, "output")]
        self.in_box["values"] = ins
        self.out_box["values"] = outs

        def pick(names, want):
            if want in names:
                return want
            foc = [n for n in names if E.is_focusrite(n)]
            return foc[0] if foc else (names[0] if names else "")

        self.in_var.set(pick(ins, want_in))
        self.out_var.set(pick(outs, want_out))
        self.out_box.configure(state="disabled" if api == "ASIO" else "readonly")
        self.excl_chk.configure(state="normal" if api == "Windows WASAPI" else "disabled")

    def rescan(self):
        if self.engine.running:
            self.stop_audio()
        try:
            self.E.rescan()
        except Exception as e:   # noqa: BLE001
            messagebox.showerror("Rescan", str(e), parent=self.root)
        self._populate_audio()
        self._populate_midi()
        if self.audio_found:
            self.status.configure(text="Scarlett found - press START.")

    def toggle_audio(self):
        if self.engine.running:
            self.stop_audio()
        else:
            self.start_audio()

    def start_audio(self):
        self.status.configure(text="Starting audio…")
        self.root.update_idletasks()
        try:
            desc = self.engine.start(
                self.api_var.get(), self.in_var.get(), self.out_var.get(),
                INPUT_CHANNELS[INPUT_CHOICES.index(self.ch_var.get())],
                int(self.sr_var.get()), int(self.bs_var.get()), self.excl_var.get())
        except Exception as e:   # noqa: BLE001
            self.status.configure(text="Audio failed to start - see message.")
            messagebox.showerror("Audio", f"{e}\n\nTips: close other apps using the Scarlett "
                                          "(DAWs, browsers in ASIO/exclusive mode), try a larger buffer, "
                                          "or switch the driver to Windows WASAPI.", parent=self.root)
            return
        self.status.configure(text="● Running  " + desc)
        self.power_btn.configure(text="  STOP  ", bg="#c62828")

    def stop_audio(self):
        self.engine.stop()
        self.engine.player_playing = False
        self.status.configure(text="Stopped")
        self.power_btn.configure(text="  START  ", bg="#2e7d32")
        if self.engine.rec_out is not None:      # don't lose a take when audio stops
            self.toggle_record()

    # ================================================================ MIDI
    def _populate_midi(self):
        try:
            import mido
            mido.set_backend("mido.backends.rtmidi")
            names = mido.get_input_names()
            self._mido = mido
        except Exception:   # noqa: BLE001 - MIDI is optional
            self.midi_box["values"] = ["(MIDI support not installed)"]
            self.midi_box.current(0)
            self.midi_box.configure(state="disabled")
            return
        self.midi_box["values"] = ["(none)"] + names
        want = self.settings.get("midi_port")
        if want in names:
            self.midi_var.set(want)
            self.open_midi()
        else:
            self.midi_var.set("(none)")
        self._midi_label()

    def open_midi(self):
        if self.midi_port is not None:
            self.midi_port.close()
            self.midi_port = None
        name = self.midi_var.get()
        if name and name != "(none)":
            try:
                self.midi_port = self._mido.open_input(name, callback=self._midi_msg)
            except Exception as e:   # noqa: BLE001
                messagebox.showerror("MIDI", str(e), parent=self.root)
        self._midi_label()

    def midi_learn(self):
        if self.midi_port is None:
            messagebox.showinfo("MIDI", "Pick your MIDI pedal/controller first.", parent=self.root)
            return
        self.midi_learning = True
        self._midi_label()

    def _midi_label(self):
        if self.midi_port is None:
            t = ""
        elif self.midi_learning:
            t = "Move the expression pedal now…"
        elif self.midi_cc is not None:
            t = f"Expression = CC {self.midi_cc} · Program Change selects presets"
        else:
            t = "No CC assigned - press Learn CC"
        self.midi_lbl.configure(text=t)

    def _midi_msg(self, msg):   # MIDI thread: only touch the engine + flags
        if msg.type == "program_change":
            self.pending_preset = msg.program
            return
        if msg.type != "control_change":
            return
        if self.midi_learning:
            self.midi_cc = msg.control
            self.midi_learning = False
            self.midi_dirty = True
        if msg.control != self.midi_cc:
            return
        v = msg.value / 127.0
        target = self.midi_target.get()
        if target == MIDI_TARGETS[0]:
            self.engine.set("wah", "pos", v)
        elif target == MIDI_TARGETS[1]:
            self.expr_vol = v
            self.midi_dirty = True
        else:
            self.engine.set("pitch", "semis", v * 12.0)
            self.midi_dirty = True

    # ================================================================ keyboard
    def _bind_keys(self):
        def guard(fn):
            def h(e):
                if isinstance(e.widget, (tk.Entry, ttk.Entry)):
                    return
                fn()
            return h

        def stomp(i):
            if i < len(self.board):
                k = self.board[i]
                if k == "looper":
                    self.looper_press()
                    return
                v = 0 if self.engine.values[k]["on"] else 1
                self.set_param(k, "on", v)
                self.controls[(k, "on")].set_value(v)

        def wah_toggle():
            if "wah" in self.board:
                stomp(self.board.index("wah"))

        def nudge(d):
            self.set_param("wah", "pos", min(1.0, max(0.0, self.engine.values["wah"]["pos"] + d)))

        b = self.root.bind_all
        for i in range(9):
            b(f"<KeyPress-{i + 1}>", guard(lambda i=i: stomp(i)))
        b("<KeyPress-w>", guard(wah_toggle))
        b("<KeyPress-Up>", guard(lambda: nudge(0.05)))
        b("<KeyPress-Down>", guard(lambda: nudge(-0.05)))
        b("<KeyPress-t>", guard(lambda: self.set_tuner(not self.tuner_on)))
        b("<KeyPress-l>", guard(self.looper_press))
        b("<KeyPress-k>", guard(self.looper_stop))

    # ================================================================ periodic UI refresh
    def _tick(self):
        self.tick_n += 1
        pin, pout, clips = self.engine.read_meters()
        self.in_meter.push(pin)
        self.out_meter.push(pout)
        self.clip_led.configure(bg="#ff3b30" if clips else "#2a2a30", fg="white" if clips else "#555")

        # footswitch LEDs follow engine state (keys / MIDI / presets)
        for k in self.board:
            sw = self.controls.get((k, "on"))
            if sw is not None and sw.on != bool(self.engine.values[k]["on"]):
                sw.set_value(self.engine.values[k]["on"])

        wp = self.extras.get("wah_pedal")
        if wp is not None and "wah" in self.board:
            v = self.engine.values["wah"]
            manual = int(v["mode"]) == 0
            wp.active = manual
            pos = v["pos"] if (manual or not self.engine.running) else \
                self.engine.pedal_state("wah", self.D.S_WAH_POS)
            fmax = max(v["fmax"], v["fmin"] * 1.05)
            wp.show(pos, v["fmin"] * (fmax / v["fmin"]) ** pos)

        lp = self.extras.get("looper")
        if lp is not None and "looper" in self.board:
            st, bar, main = lp
            eff, has = self._loop_state()
            text, col, lab = {0: ("STOPPED" if has else "EMPTY", DIM, "PLAY" if has else "REC"),
                              1: ("● RECORDING", "#ff3b30", "PLAY"),
                              2: ("▶ PLAYING", "#34c759", "DUB"),
                              3: ("● OVERDUB", "#ff9800", "PLAY")}[eff]
            if st.cget("text") != text:
                st.configure(text=text, fg=col)
                main.label = lab
                main.set_led(col if eff else "#ff3b30")
                main.set_value(eff != 0)
            length = self.engine.pedal_state("looper", self.D.S_LOOP_LEN)
            pos = self.engine.pedal_state("looper", self.D.S_LOOP_POS)
            bar.delete("all")
            w = int(bar["width"])
            if eff == 1:
                frac = min(1.0, pos / (self.D.LOOP_SECONDS * self.engine.sr))
            else:
                frac = pos / length if length > 0 else 0
            bar.create_rectangle(0, 0, w * frac, 8, fill=col if eff else "#666", outline="")

        if self.tuner_on and self.tick_n % 3 == 0 and self.engine.running:
            f = detect_pitch(self.engine.tuner_snapshot(), self.engine.sr)
            if f:
                self.tuner_hist.append(f)
                self.tuner.show(sorted(self.tuner_hist)[len(self.tuner_hist) // 2])
            else:
                self.tuner_hist.clear()
                self.tuner.show(None)

        if self.pending_status:
            self.status.configure(text=self.pending_status)
            self.pending_status = None
            self.hold_status = self.tick_n + 150      # keep the message up ~5 s
        if self.tick_n % 5 == 0:          # transport displays
            e = self.engine
            playing = e.player_playing
            if self.play_btn.cget("text") != ("■" if playing else "▶"):
                self.play_btn.configure(text="■" if playing else "▶", bg="#c62828" if playing else "#2e7d32")
            cur, tot = e.player_progress()
            self.ptime_lbl.configure(text=f"{int(cur // 60)}:{int(cur % 60):02d} / {int(tot // 60)}:{int(tot % 60):02d}"
                                     if tot else "")
            if e.rec_out is not None:
                sec = e.rec_seconds()
                self.rec_btn.configure(text="■ STOP", bg="#c62828", fg="white")
                self.rec_time.configure(text=f"{int(sec // 60)}:{int(sec % 60):02d}", fg="#ff6b6b")
            elif self.rec_btn.cget("text") != "● REC":
                self.rec_btn.configure(text="● REC", bg="#4a1c1c", fg="#ff6b6b")
                self.rec_time.configure(text="")

        if self.midi_dirty:
            self.midi_dirty = False
            self._midi_label()
            self._apply_globals()
            if "pitch" in self.board:
                self._sync_panel("pitch")
        if self.pending_preset is not None:
            names = list(self._all_presets())
            if self.pending_preset < len(names):
                self.load_preset(names[self.pending_preset])
            self.pending_preset = None

        e = self.engine
        if e.running and self.tick_n % 15 == 0 and self.tick_n > getattr(self, "hold_status", 0):
            health = f"  |  dropouts {e.xruns} · slow blocks {e.late} · worst {e.max_ms:.1f} ms"
            if e.xruns or e.late:
                health += "  (crackling? raise Buffer)"
            self.status.configure(text="● Running  " + e.description + health)
        elif self.engine.stream is not None and not self.engine.running:
            self.stop_audio()
            self.status.configure(text="Audio stream stopped unexpectedly (device unplugged?)")
        self.root.after(33, self._tick)

    def on_close(self):
        vals = {k: {n: v for n, v in d.items() if (k, n) not in SKIP_RESTORE}
                for k, d in self.engine.values.items()}
        self.settings.update({
            "board": list(self.board),
            "values": vals,
            "global": dict(self.glob),
            "audio": {"hostapi": self.api_var.get(), "input": self.in_var.get(), "output": self.out_var.get()},
            "in_choice": INPUT_CHOICES.index(self.ch_var.get()),
            "samplerate": int(self.sr_var.get()),
            "blocksize": int(self.bs_var.get()),
            "exclusive": bool(self.excl_var.get()),
            "midi_port": self.midi_var.get() if self.midi_port is not None else None,
            "midi_cc": self.midi_cc,
            "midi_target": self.midi_target.get(),
            "tuner_mute": bool(self.tuner_mute.get()),
            "ir_path": self.engine.ir_path,
            "player_mode": self.pmode_var.get(),
            "player_loop": bool(self.loop_var.get()),
            "player_vol": float(self.pvol_var.get()),
            "geometry": self.root.geometry(),
        })
        save_json(SETTINGS_FILE, self.settings)
        self.engine.stop()
        if self.midi_port is not None:
            self.midi_port.close()
        self.root.destroy()


def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:   # noqa: BLE001
        pass
    root = tk.Tk()
    root.configure(bg=BG)
    root.title("PedalBoard v2")
    splash = tk.Label(root, text="PEDALBOARD v2\n\nloading pedals…\n(first launch compiles the DSP, ~30 s)",
                      bg=BG, fg=TEXT, font=("Segoe UI", 14), padx=60, pady=60)
    splash.pack()
    root.update()
    import engine_v2
    splash.destroy()
    App(root, engine_v2)
    root.mainloop()


if __name__ == "__main__":
    sys.exit(main())

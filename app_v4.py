"""PedalBoard v4 - v3's board plus a real cabinet section, more amps and two switchable boards.

  * Cabinet: synthesized speaker/mic library (or your own IR files), mic type / position / distance /
    blend / room, placeable right after the amp.  Cab settings are stored in presets.
  * 8 amp voicings and a set of complete rigs (presets: "Rig: ...").
  * BOARDS A / B: two complete boards to flip between; both are remembered between sessions.
  * Auto input level and a latency read-out.

Run:  pythonw app_v4.py   (PedalBoard.bat does this through launch.py)
"""
import copy
import json
import math
import os
import sys
import time
import traceback
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import numpy as np

import app_v2
import app_v3
import irlib_v4 as IRL
import rigs_v4
import updater
import widgets_v3 as W
from widgets_v3 import (BG, DIM, GOLD, TEXT, CButton, CKnob, CMeter, CSegmented, CText, CTuner, CCheck,
                        CFootswitch, ClipLed, PillButton)

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_V4 = os.path.join(HERE, "settings_v4.json")
IR_DIR = os.path.join(HERE, "irs")
LOG_FILE = os.path.join(HERE, "pedalboard-error.log")
app_v2.SETTINGS_FILE = SETTINGS_V4
updater.Updater.check_async = lambda self: None      # v4 is a separate version: never auto-update over it
VERSION4 = "4.0.0"

SIDE_L = 178
SIDE_R = 216
MIC_SHORT = ["DYN", "RIB", "COND"]
DEFAULT_CAB = rigs_v4.cab("4x12 Closed British", "DYNAMIC", 0.2, 0.2, 0.0, 0.05)
PANEL_H = 590          # the side panels scroll (mouse wheel) if the window is shorter than this


def log_error(where):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {where}\n{traceback.format_exc()}\n")
    except OSError:
        pass


class App(app_v3.App):
    def __init__(self, root, engine_mod):
        self.cab = dict(DEFAULT_CAB)
        self.ab = {"cur": "A", "A": None, "B": None}
        self._board_text = None
        self._cab_job = None
        self.auto = None
        super().__init__(root, engine_mod)
        self._init_v4()

    # ================================================================ setup
    def _init_v4(self):
        s = self.settings
        root = self.root
        root.title(f"PedalBoard {VERSION4}")
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(s.get("geometry") or f"{min(1480, sw - 30)}x{min(1010, sh - 120)}+10+0")
        root.minsize(1000, 640)
        os.makedirs(IR_DIR, exist_ok=True)
        readme = os.path.join(IR_DIR, "README.txt")
        if not os.path.exists(readme):
            with open(readme, "w", encoding="utf-8") as f:
                f.write("Drop cabinet impulse responses (.wav) in this folder and they appear in the CABINET "
                        "model menu under 'My IRs'.\nShort mono files (under ~20 ms) work best; longer ones "
                        "are trimmed.\n")
        cab = dict(DEFAULT_CAB)
        saved = s.get("cab_v4")
        if saved:
            cab.update(saved)
        elif s.get("ir_path") and os.path.exists(s["ir_path"]):
            cab["cab"] = "file:" + s["ir_path"]               # carry a v3 IR over
        self.cab = cab
        self.glob.setdefault("cabpos", 1)
        self.apply_cab()
        self._load_boards()
        self._update_ab_buttons()

    # ================================================================ presets / state
    def _all_presets(self):
        builtin = {n: {**p, "cab": rigs_v4.PRESET_CABS[n]} if n in rigs_v4.PRESET_CABS else p
                   for n, p in app_v2.BUILTIN_PRESETS.items()}
        return {**builtin, **self.user_presets, **rigs_v4.RIGS}   # this order keeps MIDI program numbers

    def load_preset(self, name):
        p = self._all_presets().get(name)
        super().load_preset(name)
        if p:
            self.apply_cab(rigs_v4.with_cab(p)["cab"])          # every preset sets its cabinet

    def save_preset(self):
        name = simpledialog.askstring("Save preset", "Preset name:", parent=self.root)
        if not name:
            return
        vals = {k: {n: v for n, v in d.items() if (k, n) not in app_v2.SKIP_RESTORE}
                for k, d in self.engine.values.items() if k in self.board}
        self.user_presets[name] = {"board": list(self.board), "values": vals, "cab": dict(self.cab)}
        app_v2.save_json(app_v2.PRESETS_FILE, self.user_presets)
        self._refresh_presets()
        self.preset_var.set(name)

    def capture_state(self):
        return {"board": list(self.board), "preset": self.preset_var.get(),
                "values": {k: {n: v for n, v in d.items() if (k, n) not in app_v2.SKIP_RESTORE}
                           for k, d in copy.deepcopy(self.engine.values).items()},
                "glob": {k: self.glob[k] for k in ("in_gain_db", "master_db")}, "cab": dict(self.cab)}

    def restore_state(self, st):
        self._apply_values(st["values"])
        self._set_board(st["board"])
        self.glob.update(st.get("glob", {}))
        self._apply_globals()
        self._sync_controls()
        self.preset_var.set(st.get("preset", ""))
        self.apply_cab(st.get("cab"))

    # ---- BOARDS: two complete boards (pedals, order, settings, amp, cab, levels) to flip between
    def ab_switch(self, which):
        if which == self.ab["cur"]:
            return
        self.ab[self.ab["cur"]] = self.capture_state()
        fresh = self.ab[which] is None
        if fresh:
            self.ab[which] = copy.deepcopy(self.ab[self.ab["cur"]])      # start the new board from this one
        self.ab["cur"] = which
        self.restore_state(copy.deepcopy(self.ab[which]))
        self._update_ab_buttons()
        self.status.configure(text=f"Board {which} - started as a copy of the other board; change it, then flip "
                                   "between A and B." if fresh else f"Board {which}")
        self.hold_status = self.tick_n + 100

    def _update_ab_buttons(self):
        for k, b in (("A", self.ab_a), ("B", self.ab_b)):
            on = self.ab["cur"] == k
            b.configure(bg=GOLD if on else "#3a3a42", fg="#111" if on else TEXT)
        self._update_board_label()

    def _update_board_label(self):
        def name(k):
            if k == self.ab["cur"]:
                n = self.preset_var.get()
            elif self.ab[k] is None:
                return "empty"
            else:
                n = self.ab[k].get("preset", "")
            n = n or "custom"
            return n if len(n) <= 24 else n[:23] + "…"
        text = f"A: {name('A')}     B: {name('B')}"
        if text != self._board_text:
            self._board_text = text
            self.board_lbl.configure(text=text)

    def _load_boards(self):
        """Restore both boards saved at the last close. The live board is the current slot."""
        saved = self.settings.get("boards_v4") or {}
        cur = saved.get("cur") if saved.get("cur") in ("A", "B") else "A"
        other = "B" if cur == "A" else "A"
        st = saved.get(other)
        ok = isinstance(st, dict) and isinstance(st.get("board"), list) and isinstance(st.get("values"), dict)
        mine = saved.get(cur)
        if (not self.preset_var.get() and isinstance(mine, dict) and mine.get("board") == self.board
                and mine.get("preset") in self._all_presets()):
            self.preset_var.set(mine["preset"])                 # the board is unchanged since that preset
        self.ab = {"cur": cur, cur: self.capture_state(), other: st if ok else None}

    def _save_boards(self):
        try:
            self.ab[self.ab["cur"]] = self.capture_state()
            self.settings["boards_v4"] = json.loads(json.dumps(
                self.ab, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
        except Exception:   # noqa: BLE001
            log_error("save boards")

    # ================================================================ header / tone bar
    def _build_header(self):
        f = tk.Frame(self.root, bg=BG)
        f.pack(fill="x", padx=16, pady=(12, 6))
        tk.Label(f, text="PEDALBOARD", bg=BG, fg=TEXT, font=W.LOGO_FONT).pack(side="left")
        tk.Label(f, text=" v4", bg=BG, fg=GOLD, font=("Bahnschrift SemiBold", 13)).pack(side="left", pady=(8, 0))
        self.add_menu = tk.Menu(self.root, tearoff=0, bg="#24242a", fg=TEXT, activebackground=GOLD,
                                activeforeground="#111", font=("Segoe UI", 9))
        add = PillButton(f, "＋  ADD PEDAL", lambda: self.add_menu.tk_popup(add.winfo_rootx(),
                                                                          add.winfo_rooty() + add.winfo_height()),
                         bg=GOLD, fg="#111")
        add.pack(side="left", padx=(22, 6))
        PillButton(f, "Clear board", self.clear_board).pack(side="left", padx=3)
        self.audio_toggle = PillButton(f, "⚙  Audio & MIDI  ▴", self.toggle_audio_panel)
        self.audio_toggle.pack(side="left", padx=3)
        self.update_btn = PillButton(f, "Update", lambda: None)     # kept so v3 code that touches it works
        PillButton(f, "Delete", self.delete_preset).pack(side="right", padx=(4, 0))
        PillButton(f, "Save As…", self.save_preset).pack(side="right", padx=(4, 0))
        PillButton(f, "▶", lambda: self.step_preset(1), minw=34).pack(side="right", padx=(4, 0))
        self.preset_var = tk.StringVar()
        self.preset_box = ttk.Combobox(f, textvariable=self.preset_var, state="readonly", width=26,
                                       font=("Segoe UI", 10))
        self.preset_box.pack(side="right", padx=4)
        self.preset_box.bind("<<ComboboxSelected>>", lambda e: self.load_preset(self.preset_var.get()))
        PillButton(f, "◀", lambda: self.step_preset(-1), minw=34).pack(side="right")
        tk.Label(f, text="PRESET  ", bg=BG, fg=DIM, font=("Bahnschrift SemiBold", 9)).pack(side="right")
        self._refresh_presets()

        # ---- boards bar: two boards to flip between, latency chip
        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill="x", padx=16, pady=(0, 6))
        self.tonebar = bar
        tk.Label(bar, text="BOARDS  ", bg=BG, fg=DIM, font=("Bahnschrift SemiBold", 9)).pack(side="left")
        self.ab_a = PillButton(bar, "A", lambda: self.ab_switch("A"), minw=34)
        self.ab_a.pack(side="left", padx=(0, 2))
        self.ab_b = PillButton(bar, "B", lambda: self.ab_switch("B"), minw=34)
        self.ab_b.pack(side="left", padx=(0, 10))
        self.board_lbl = tk.Label(bar, text="", bg=BG, fg=DIM, font=("Segoe UI", 9))
        self.board_lbl.pack(side="left", padx=4)
        self.lat_chip = tk.Label(bar, text="", bg=BG, fg=DIM, font=("Bahnschrift SemiBold", 9))
        self.lat_chip.pack(side="right", padx=(10, 0))

    # ================================================================ main area
    def _build_main(self):
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill="both", expand=True, padx=12, pady=(2, 8))
        left = tk.Canvas(main, width=SIDE_L, bg=BG, highlightthickness=0)
        left.pack(side="left", fill="y")
        right = tk.Canvas(main, width=SIDE_R, bg=BG, highlightthickness=0)
        right.pack(side="right", fill="y")
        for cv in (left, right):
            cv.bind("<Configure>", lambda e, cv=cv: self._side_bg(cv, e.width, e.height))
        mid = tk.Frame(main, bg=BG)
        mid.pack(side="left", fill="both", expand=True, padx=10)
        self.canvas = tk.Canvas(mid, bg="#18181c", highlightthickness=0)
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_resize)
        self.root.bind_all("<MouseWheel>", self._board_wheel, add="+")

        h1 = ("Bahnschrift SemiBold", 13)
        small = W.SMALL_FONT
        # ---- input, level, tuner, latency
        cx = SIDE_L / 2
        left.create_text(cx, 28, text="INPUT", fill=TEXT, font=h1)
        self.in_meter = CMeter(left, 42, 54, h=112, label="IN")
        self.gain_knob = CKnob(left, 112, 108, "Gain", -12, 24, 0.0, lambda v: self._set_glob("in_gain_db", v),
                               fmt="{:+.0f} dB", accent="#8bd450", size=48)
        CButton(left, 112, 184, "AUTO LEVEL", self.auto_level_start, fill="#2e5b3a", h=20)
        left.create_line(18, 204, SIDE_L - 18, 204, fill="#3a3d45")
        left.create_text(cx, 224, text="TUNER", fill=TEXT, font=h1)
        self.tuner = CTuner(left, cx, 242, w=150, h=84)
        self.tuner_mute = tk.BooleanVar(value=self.settings.get("tuner_mute", True))
        CCheck(left, cx, 358, "Mute while tuning", self.tuner_mute, command=self._apply_mute)
        self.tuner_sw = CFootswitch(left, cx, 428, lambda v: self.set_tuner(bool(v)), led="#4fc3f7")
        left.create_line(18, 468, SIDE_L - 18, 468, fill="#3a3d45")
        left.create_text(cx, 486, text="LATENCY", fill=TEXT, font=h1)
        self.lat_main = left.create_text(cx, 510, text="audio stopped", fill=DIM, font=("Bahnschrift SemiBold", 11))
        self.lat_sub = left.create_text(cx, 548, text="", fill=DIM, font=small, width=SIDE_L - 24,
                                        justify="center")
        self.left_cv = left

        # ---- output + cabinet
        cx = SIDE_R / 2
        right.create_text(cx, 28, text="OUTPUT", fill=TEXT, font=h1)
        self.master_knob = CKnob(right, 84, 108, "Master", -30, 12, 0.0, lambda v: self._set_glob("master_db", v),
                                 fmt="{:+.0f} dB", accent="#8bd450", size=48)
        self.out_meter = CMeter(right, 166, 54, h=112, label="OUT")
        self.clip_led = ClipLed(right, 90, 176)
        right.create_line(18, 200, SIDE_R - 18, 200, fill="#3a3d45")
        right.create_text(cx, 216, text="CABINET", fill=TEXT, font=h1)
        self.cab_sw = CSegmented(right, cx, 240, ["OFF", "BASIC", "IR"], lambda i: self._set_cab(i),
                                 on_fill="#32d74b", on_text="#111", off_fill="#34343c", off_text=TEXT)
        self.cab_btn = CButton(right, cx, 268, "", self.cab_menu, fill="#3a3a42", w=SIDE_R - 24, h=24)
        self.ir_lbl = CText(right, right.create_text(cx, 286, text="", fill=DIM, font=small, width=SIDE_R - 30,
                                                     justify="center", anchor="n"))
        right.create_text(cx, 330, text="MICROPHONE", fill=DIM, font=W.LABEL_FONT)
        self.mic_seg = CSegmented(right, cx, 348, MIC_SHORT, lambda i: self._cab_set("mic", IRL.MICS[i]),
                                  on_fill="#32d74b", on_text="#111", off_fill="#34343c", off_text=TEXT)
        self.cab_knobs = {}
        for i, (nm, lab) in enumerate((("pos", "Pos"), ("dist", "Dist"), ("blend", "Blend"), ("room", "Room"))):
            kx = cx + (i - 1.5) * 52
            self.cab_knobs[nm] = CKnob(right, kx, 410, lab, 0.0, 1.0, self.cab[nm],
                                       lambda v, n=nm: self._cab_set(n, v), fmt="{:.2f}", accent="#32d74b", size=34)
        right.create_text(cx, 462, text="PLACEMENT", fill=DIM, font=W.LABEL_FONT)
        self.place_seg = CSegmented(right, cx, 480, ["AT END", "AFTER AMP"], lambda i: self._cab_set("place", i),
                                    on_fill="#32d74b", on_text="#111", off_fill="#34343c", off_text=TEXT)
        right.create_text(cx, 506, text="CABINET RESPONSE", fill=DIM, font=W.LABEL_FONT)
        self.ir_plot_box = (14, 516, SIDE_R - 14, 574)
        for cv in (left, right):
            cv.configure(scrollregion=(0, 0, cv.winfo_reqwidth(), PANEL_H), yscrollincrement=20)
        self.right_cv = right

    def _side_bg(self, cv, w, h):
        super()._side_bg(cv, w, max(h, PANEL_H))

    def _board_wheel(self, e):
        w = e.widget
        if w is getattr(self, "left_cv", None) or w is getattr(self, "right_cv", None):
            cur = w.find_withtag("current")
            if not (cur and cur[0] in getattr(w, "_wheel_map", {})):       # not over a knob: scroll the panel
                w.yview_scroll(-1 if e.delta > 0 else 1, "units")
                return
        super()._board_wheel(e)

    # ================================================================ cabinet
    def _apply_globals(self):
        super()._apply_globals()
        self.engine.set_global(cabpos=self.glob.get("cabpos", 1))

    def _set_cab(self, i):
        self.cab["mode"] = int(i)
        self.apply_cab()

    def _cab_set(self, name, value):
        if name == "place":
            value = int(value)
        self.cab[name] = value
        if name == "place":
            self.apply_cab(rebuild=False)
            return
        if self.cab["mode"] == 2:
            if self._cab_job:
                self.root.after_cancel(self._cab_job)
            self._cab_job = self.root.after(25, self._rebuild_ir)
        self._sync_cab_ui(redraw_knobs=False)

    def _pick_cab(self, name):
        self.cab["cab"] = name
        self.cab["mode"] = 2
        self.apply_cab()

    def _cab_label(self, c=None):
        c = c or self.cab
        n = c["cab"]
        return os.path.basename(n[5:]) if n.startswith("file:") else n

    def _ir_source(self, c):
        c = dict(c)
        E = self.E
        if c["cab"].startswith("file:"):
            path = c["cab"][5:]

            def src(sr):
                h = E.read_wav(path, sr)[:, 0]
                nz = np.nonzero(np.abs(h) > 1e-4 * max(np.abs(h).max(), 1e-12))[0]
                h = h[nz[0]:] if len(nz) else h
                return IRL.apply_room(h, c["room"], sr)
        else:
            def src(sr):
                return IRL.make_cab(c["cab"], c["mic"], c["pos"], c["dist"], c["blend"], c["room"], sr=sr)
        return src

    def apply_cab(self, spec=None, rebuild=True):
        if spec is not None:
            self.cab = {**DEFAULT_CAB, **spec}
        c = self.cab
        self.glob["cab"] = int(c["mode"])
        self.glob["cabpos"] = int(c.get("place", 1))
        if c["mode"] == 2 and rebuild:
            self._rebuild_ir()
        self._apply_globals()
        self._sync_cab_ui()

    def _rebuild_ir(self):
        self._cab_job = None
        c = self.cab
        try:
            src = self._ir_source(c)
            self.engine.set_ir(src(self.engine.sr), self._cab_label(c), source=src)
        except Exception as e:   # noqa: BLE001
            self.status.configure(text=f"Cabinet IR failed ({e}) - using the basic cabinet.")
            self.cab["mode"] = 1
            self.glob["cab"] = 1
            self._apply_globals()
        self._sync_cab_ui(redraw_knobs=False)

    def _sync_cab_ui(self, redraw_knobs=True):
        c = self.cab
        self.cab_sw.set_value(c["mode"])
        right = self.right_cv
        right.itemconfigure(self.cab_btn.txt, text=self._cab_label(c)[:30] + "  ▾")
        is_file = c["cab"].startswith("file:")
        if c["mode"] == 2:
            if is_file:
                desc = "Your IR file. Mic, position, distance and blend don't apply; Room still does."
            else:
                desc = IRL.CABS[c["cab"]]["short"] if c["cab"] in IRL.CABS else ""
        elif c["mode"] == 1:
            desc = "Coarse filter model of a 1x12. Pick IR for the full speaker + mic simulation."
        else:
            desc = "No speaker simulation: raw amp output (fizzy). Use this only with a real cabinet / amp."
        self.ir_lbl.configure(text=desc)
        self.mic_seg.set_value(IRL.MICS.index(c["mic"]) if c["mic"] in IRL.MICS else 0)
        self.place_seg.set_value(int(c.get("place", 1)))
        if redraw_knobs:
            for n, k in self.cab_knobs.items():
                k.set_value(c[n])
        self._draw_ir_plot()

    def _draw_ir_plot(self):
        cv = self.right_cv
        cv.delete("irplot")
        x0, y0, x1, y1 = self.ir_plot_box
        cv.create_rectangle(x0, y0, x1, y1, fill="#0d0d10", outline="#2a2a30", tags="irplot")
        for f in (100, 1000, 10000):
            x = x0 + (math.log(f / 40.0) / math.log(12000.0 / 40.0)) * (x1 - x0)
            cv.create_line(x, y0, x, y1, fill="#202026", tags="irplot")
            cv.create_text(x + 2, y1 - 6, text=f"{f // 1000}k" if f >= 1000 else str(f), fill="#5a5a66",
                           font=("Bahnschrift", 6), anchor="w", tags="irplot")
        if self.cab["mode"] != 2:
            cv.create_text((x0 + x1) / 2, (y0 + y1) / 2, text="no IR in use", fill="#5a5a66", font=W.SMALL_FONT,
                           tags="irplot")
            return
        r = self.engine.ir_response()
        if r is None:
            return
        f, db = r
        ref = np.mean(db[(f > 300) & (f < 3000)])
        pts = []
        for fx, d in zip(f, db):
            x = x0 + (math.log(fx / 40.0) / math.log(12000.0 / 40.0)) * (x1 - x0)
            y = y0 + (y1 - y0) * (0.5 - (d - ref) / 48.0)
            pts += [x, min(y1 - 1, max(y0 + 1, y))]
        cv.create_line(*pts, fill="#32d74b", width=2, tags="irplot")

    def cab_menu(self):
        m = tk.Menu(self.root, tearoff=0, bg="#24242a", fg=TEXT, activebackground=GOLD, activeforeground="#111",
                    font=("Segoe UI", 9))
        syn = tk.Menu(m, tearoff=0, bg="#24242a", fg=TEXT, activebackground=GOLD, activeforeground="#111",
                      font=("Segoe UI", 9))
        for n in IRL.CAB_NAMES:
            syn.add_command(label=n, command=lambda n=n: self._pick_cab(n))
        m.add_cascade(label="Synthesized cabinets", menu=syn)
        files = self._ir_files()
        if files:
            mine = tk.Menu(m, tearoff=0, bg="#24242a", fg=TEXT, activebackground=GOLD, activeforeground="#111",
                           font=("Segoe UI", 9))
            for p in files:
                mine.add_command(label=os.path.basename(p), command=lambda p=p: self._pick_cab("file:" + p))
            m.add_cascade(label="My IRs", menu=mine)
        m.add_separator()
        m.add_command(label="Load IR file…", command=self.load_ir)
        m.add_command(label="Open IRs folder", command=lambda: os.startfile(IR_DIR))
        m.tk_popup(self.right_cv.winfo_rootx() + 20, self.right_cv.winfo_rooty() + 290)

    def _ir_files(self):
        out = []
        for d in (IR_DIR, self.settings.get("ir_dir")):
            if d and os.path.isdir(d):
                out += [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.lower().endswith(".wav")]
        seen, uniq = set(), []
        for p in out:
            if p not in seen:
                seen.add(p)
                uniq.append(p)
        return uniq[:60]

    def _load_ir_path(self, path, show_errors=False):
        try:
            self.E.read_wav(path, self.engine.sr)
        except Exception as e:   # noqa: BLE001
            if show_errors:
                messagebox.showerror("Impulse response", f"Couldn't load that file:\n{e}", parent=self.root)
            return
        self.settings["ir_dir"] = os.path.dirname(path)
        self._pick_cab("file:" + path)

    # ================================================================ audio helpers
    def auto_level_start(self):
        if not self.engine.running:
            self.status.configure(text="Start audio first, then press AUTO LEVEL and play.")
            return
        self.engine.raw_peak = 0.0
        self.auto = {"end": self.tick_n + 140, "peak": 0.0}
        self.status.configure(text="AUTO LEVEL: strum your loudest chords for 4 seconds…")
        self.hold_status = self.tick_n + 200

    def _auto_level_tick(self):
        a = self.auto
        a["peak"] = max(a["peak"], self.engine.raw_peak)
        if self.tick_n < a["end"]:
            return
        self.auto = None
        pk = a["peak"]
        if pk < 0.003:
            msg = "AUTO LEVEL: no signal heard - is the guitar on the INST input (Direct Monitor off)?"
        else:
            pk_db = 20.0 * math.log10(pk)
            g = min(24.0, max(-12.0, -12.0 - pk_db))
            self.gain_knob.set_value(g, notify=True)
            msg = (f"AUTO LEVEL: input peaked at {pk_db:.1f} dBFS → software gain set to {g:+.0f} dB "
                   f"(peaks ≈ -12 dBFS, the level the pedals and amp are designed for).")
            if pk_db > -3:
                msg += "  The interface input is hot - lower its gain."
            elif pk_db < -40:
                msg += "  Very quiet input - raise the interface gain for less noise."
        self.status.configure(text=msg)
        self.hold_status = self.tick_n + 300

    def _latency_update(self):
        e = self.engine
        cv = self.left_cv
        info = e.latency_info() if e.running else None
        if info is None:
            cv.itemconfigure(self.lat_main, text="audio stopped", fill=DIM)
            cv.itemconfigure(self.lat_sub, text="")
            self.lat_chip.configure(text="")
            return
        inp, out, buf = info
        tot = inp + out
        if tot < 12:
            word, col = "excellent", "#5dd36b"
        elif tot < 20:
            word, col = "good", "#9ccc65"
        elif tot < 30:
            word, col = "noticeable", "#ffb03a"
        else:
            word, col = "high", "#ff5d52"
        api = self.api_var.get()
        tip = f"buffer {buf:.1f} ms · driver in {inp:.1f} / out {out:.1f} ms\n"
        if api != "ASIO":
            if "ASIO" in self.E.host_apis():
                tip += "ASIO is available - select it as the Driver for lower latency."
            else:
                tip += ("Windows driver (" + api.replace("Windows ", "") + "). Installing the Focusrite driver "
                        "adds ASIO and typically halves this.")
        else:
            tip += "ASIO - the lowest latency this interface offers. Smaller Buffer = lower still."
        cv.itemconfigure(self.lat_main, text=f"{tot:.0f} ms  {word}", fill=col)
        cv.itemconfigure(self.lat_sub, text=tip, fill=DIM)
        self.lat_chip.configure(text=f"latency {tot:.0f} ms", fg=col)

    # ================================================================ periodic
    def _tick(self):
        try:
            self._tick4()
        except Exception:   # noqa: BLE001
            log_error("tick4")
        super()._tick()

    def _tick4(self):
        n = self.tick_n
        if self.auto:
            self._auto_level_tick()
        if n % 15 == 0:
            self._latency_update()
            self._update_board_label()

    def on_close(self):
        self.settings["cab_v4"] = dict(self.cab)
        self._save_boards()
        super().on_close()


def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:   # noqa: BLE001
        pass
    if not os.path.exists(SETTINGS_V4):
        for old in ("settings_v3.json", "settings_v2.json"):
            p = os.path.join(HERE, old)
            if os.path.exists(p):
                try:
                    with open(p, encoding="utf-8") as f:
                        d = json.load(f)
                    d.pop("geometry", None)
                    d.setdefault("global", {})["cab"] = 2
                    with open(SETTINGS_V4, "w", encoding="utf-8") as f:
                        json.dump(d, f, indent=2)
                except (OSError, ValueError):
                    pass
                break
    root = tk.Tk()
    root.configure(bg=BG)
    root.title("PedalBoard v4")
    splash = tk.Label(root, text="PEDALBOARD v4\n\nloading pedals…", bg=BG, fg=TEXT,
                      font=("Bahnschrift SemiBold", 16), padx=80, pady=70)
    splash.pack()
    root.update()
    import engine_v2
    splash.destroy()
    App(root, engine_v2)
    root.mainloop()


if __name__ == "__main__":
    sys.exit(main())

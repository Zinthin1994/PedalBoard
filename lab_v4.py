"""Tone Lab for PedalBoard v4: spectrum view, per-block chain inspector, flow check, learn / glossary and
reference-tone matching. The audio and board logic stays in app_v4.App; this file is the presentation."""
import math
import tkinter as tk
from tkinter import filedialog, ttk

import numpy as np

import irlib_v4 as IRL
import tonehelp_v4 as H
from pedals_v2 import BY_KEY
from widgets_v3 import BG, DIM, GOLD, TEXT, PillButton

PANEL = "#1b1b20"
FIELD = "#23232a"
BANDS = [(20, 80, "SUB"), (80, 250, "BASS"), (250, 500, "MUD / BODY"), (500, 2000, "MIDS"),
         (2000, 5000, "PRESENCE"), (5000, 8000, "FIZZ"), (8000, 16000, "AIR")]
GRID_F = [50, 100, 200, 500, 1000, 2000, 5000, 10000]
SEV_COLOR = {"bad": "#ff5d52", "warn": "#ffb03a", "tip": "#6cb8ff"}
SEV_LABEL = {"bad": "PROBLEM", "warn": "CHECK", "tip": "TIP"}


def band_name(f):
    for lo, hi, name in BANDS:
        if lo <= f < hi:
            return name
    return ""


def fmt_hz(f):
    return f"{f / 1000:.1f} kHz" if f >= 1000 else f"{f:.0f} Hz"


class SpectrumView(tk.Canvas):
    """Log-frequency spectrum plot with named bands. set_curves() takes dicts with keys
    name, f, db, color and optional width / dash."""
    FMIN, FMAX = 30.0, 16000.0
    RANGE = 66.0

    def __init__(self, parent, height=120, show_bands=True, **kw):
        super().__init__(parent, height=height, bg="#101013", highlightthickness=1,
                         highlightbackground="#2a2a30", **kw)
        self.curves = []
        self.top = None
        self.show_bands = show_bands
        self.message = ""
        self._hover = None
        self.bind("<Configure>", lambda e: self._grid())
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda e: self._motion(None))
        self.after_idle(self._grid)

    def _x(self, f):
        w = max(self.winfo_width(), 50)
        return (math.log2(max(f, 1.0) / self.FMIN) / math.log2(self.FMAX / self.FMIN)) * (w - 2) + 1

    def _f_at(self, x):
        w = max(self.winfo_width(), 50)
        return self.FMIN * (self.FMAX / self.FMIN) ** (min(max((x - 1) / (w - 2), 0.0), 1.0))

    def _grid(self):
        self.delete("grid")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 60 or h < 40:
            return
        if self.show_bands:
            for i, (lo, hi, name) in enumerate(BANDS):
                x0, x1 = self._x(max(lo, self.FMIN)), self._x(min(hi, self.FMAX))
                self.create_rectangle(x0, 0, x1, h, fill="#15151a" if i % 2 else "#121216", outline="", tags="grid")
                if h >= 90:
                    self.create_text((x0 + x1) / 2, 9, text=name, fill="#4a4a55", font=("Bahnschrift", 7),
                                     tags="grid")
        for f in GRID_F:
            x = self._x(f)
            self.create_line(x, 0, x, h, fill="#26262d", tags="grid")
            self.create_text(x + 2, h - 8, text=f"{f // 1000}k" if f >= 1000 else str(f), fill="#6a6a76",
                             font=("Bahnschrift", 7), anchor="w", tags="grid")
        for k in range(1, 6):
            y = h * k / 6
            self.create_line(0, y, w, y, fill="#1d1d23", tags="grid")
        self.tag_lower("grid")
        self.draw()

    def set_curves(self, curves, message=""):
        self.curves = [c for c in curves if c.get("f") is not None]
        self.message = message
        self.draw()

    def draw(self):
        self.delete("curve")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 60 or h < 40:
            return
        main = [c["db"] for c in self.curves if not c.get("aux")]
        if main:
            tgt = float(max(np.max(d) for d in main)) + 6.0
            self.top = tgt if self.top is None else 0.8 * self.top + 0.2 * tgt
        top = self.top if self.top is not None else 0.0
        for c in self.curves:
            f, db = c["f"], c["db"]
            if c.get("aux"):                        # aux curves are scaled to the main curves' top
                db = db - np.max(db) + top - 8.0
            pts = []
            for fx, d in zip(f, db):
                pts += [self._x(fx), min(h - 1, max(1, (top - d) / self.RANGE * (h - 16) + 10))]
            if len(pts) >= 4:
                self.create_line(*pts, fill=c["color"], width=c.get("width", 2), dash=c.get("dash"),
                                 tags="curve", smooth=False)
        if self.message:
            self.create_text(w - 8, 8, text=self.message, fill="#7a7a86", font=("Segoe UI", 8), anchor="ne",
                             tags="curve")
        self.create_text(w - 8, h - 5, text="grey = input   gold = output   blue = reference", fill="#4a4a55",
                         font=("Segoe UI", 7), anchor="se", tags="curve")
        if self._hover is not None:
            self._draw_hover()

    def _motion(self, e):
        self._hover = e.x if e is not None else None
        self.delete("hover")
        if e is not None:
            self._draw_hover()

    def _draw_hover(self):
        self.delete("hover")
        x = self._hover
        h = self.winfo_height()
        f = self._f_at(x)
        self.create_line(x, 0, x, h, fill="#555560", tags="hover")
        txt = f"{fmt_hz(f)}  ·  {band_name(f).lower()}"
        for c in self.curves:
            if c.get("aux") or c.get("name") is None:
                continue
            v = float(np.interp(math.log2(f), np.log2(c["f"]), c["db"]))
            txt += f"   {c['name']} {v:+.0f} dB"
        right = x < self.winfo_width() / 2
        self.create_text(x + (8 if right else -8), 22, text=txt, fill=TEXT, font=("Bahnschrift", 8),
                         anchor="w" if right else "e", tags="hover")


class ToneLab(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("PedalBoard Tone Lab")
        self.configure(bg=BG)
        self.geometry(app.settings.get("lab_geometry", "1240x760"))
        self.minsize(900, 560)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.selected = None
        self._build()

    # ------------------------------------------------------------------ layout
    def _build(self):
        st = ttk.Style()
        st.configure("Lab.Treeview", background=FIELD, fieldbackground=FIELD, foreground=TEXT, rowheight=22,
                     borderwidth=0, font=("Segoe UI", 9))
        st.configure("Lab.Treeview.Heading", background="#2c2c34", foreground=TEXT, font=("Bahnschrift SemiBold", 8),
                     relief="flat")
        st.map("Lab.Treeview", background=[("selected", "#3b3b46")], foreground=[("selected", "#fff")])
        st.configure("TNotebook", background=BG, borderwidth=0)
        st.configure("TNotebook.Tab", background="#24242a", foreground=TEXT, padding=(14, 5),
                     font=("Bahnschrift SemiBold", 9))
        st.map("TNotebook.Tab", background=[("selected", "#3a3a44")])

        paned = tk.PanedWindow(self, orient="horizontal", bg=BG, sashwidth=5, sashrelief="flat", bd=0)
        paned.pack(fill="both", expand=True, padx=8, pady=8)
        left = tk.Frame(paned, bg=BG)
        right = tk.Frame(paned, bg=BG)
        paned.add(left, minsize=420)
        paned.add(right, minsize=420)

        tk.Label(left, text="SPECTRUM", bg=BG, fg=TEXT, font=("Bahnschrift SemiBold", 11)).pack(anchor="w")
        self.spec = SpectrumView(left, height=300)
        self.spec.pack(fill="both", expand=True, pady=(4, 6))
        row = tk.Frame(left, bg=BG)
        row.pack(fill="x")
        self.v_in = tk.BooleanVar(value=True)
        self.v_out = tk.BooleanVar(value=True)
        self.v_ref = tk.BooleanVar(value=True)
        self.v_cab = tk.BooleanVar(value=False)
        self.v_tilt = tk.BooleanVar(value=True)
        for text, var, col in (("Input", self.v_in, "#8b8b96"), ("Output", self.v_out, GOLD),
                               ("Reference", self.v_ref, "#4fc3f7"), ("Cab response", self.v_cab, "#32d74b"),
                               ("3 dB/oct tilt", self.v_tilt, TEXT)):
            tk.Checkbutton(row, text=text, variable=var, bg=BG, fg=col, selectcolor="#24242a", activebackground=BG,
                           activeforeground=col, font=("Segoe UI", 9), command=self.app.spectrum_options_changed
                           ).pack(side="left", padx=(0, 10))
        row2 = tk.Frame(left, bg=BG)
        row2.pack(fill="x", pady=(6, 0))
        tk.Label(row2, text="Source", bg=BG, fg=DIM, font=("Segoe UI", 9)).pack(side="left")
        self.src_var = tk.StringVar(value="auto")
        for text, val in (("Auto (live when running)", "auto"), ("Test riff (offline)", "riff")):
            tk.Radiobutton(row2, text=text, variable=self.src_var, value=val, bg=BG, fg=TEXT, selectcolor="#24242a",
                           activebackground=BG, activeforeground=TEXT, font=("Segoe UI", 9),
                           command=self.app.spectrum_options_changed).pack(side="left", padx=6)
        self.legend = tk.Label(left, text="", bg=BG, fg=DIM, font=("Segoe UI", 9), justify="left", anchor="w",
                               wraplength=520)
        self.legend.pack(fill="x", pady=(8, 0))

        self.nb = ttk.Notebook(right)
        self.nb.pack(fill="both", expand=True)
        self._chain_tab()
        self._learn_tab()
        self._match_tab()

    # ---- chain / flow
    def _chain_tab(self):
        f = tk.Frame(self.nb, bg=BG)
        self.nb.add(f, text="  Chain  ")
        top = tk.Frame(f, bg=BG)
        top.pack(fill="x", pady=(8, 4), padx=4)
        tk.Label(top, text="Test signal", bg=BG, fg=DIM, font=("Segoe UI", 9)).pack(side="left")
        self.riff_var = tk.StringVar(value="Palm-muted chugs")
        ttk.Combobox(top, textvariable=self.riff_var, values=["Palm-muted chugs", "Open chords"], state="readonly",
                     width=17).pack(side="left", padx=6)
        PillButton(top, "Analyze chain", self.app.analyze_chain, bg=GOLD, fg="#111").pack(side="left", padx=4)
        PillButton(top, "Whole chain", self._whole_chain).pack(side="left", padx=4)
        tk.Label(top, text="select a block to see its spectrum before / after", bg=BG, fg=DIM,
                 font=("Segoe UI", 8)).pack(side="left", padx=8)
        cols = ("n", "block", "state", "inl", "outl", "delta", "peak", "note")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", style="Lab.Treeview", height=9,
                                 selectmode="browse")
        for c, t, w, a in (("n", "#", 28, "center"), ("block", "BLOCK", 130, "w"), ("state", "STATE", 52, "center"),
                           ("inl", "IN RMS", 64, "e"), ("outl", "OUT RMS", 66, "e"), ("delta", "Δ GAIN", 62, "e"),
                           ("peak", "PEAK", 64, "e"), ("note", "NOTE", 230, "w")):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor=a, stretch=(c == "note"))
        self.tree.pack(fill="x", padx=4)
        self.tree.bind("<<TreeviewSelect>>", self._row_selected)
        for tag, col in (("hot", "#ff8a80"), ("off", "#6a6a76"), ("big", "#ffd180")):
            self.tree.tag_configure(tag, foreground=col)
        tk.Label(f, text="FLOW CHECK", bg=BG, fg=TEXT, font=("Bahnschrift SemiBold", 11)).pack(anchor="w", padx=4,
                                                                                                  pady=(12, 2))
        box = tk.Frame(f, bg=BG)
        box.pack(fill="both", expand=True, padx=4)
        self.flow = tk.Text(box, bg=PANEL, fg=TEXT, wrap="word", bd=0, padx=10, pady=8, font=("Segoe UI", 9),
                            highlightthickness=0, height=10)
        sb = ttk.Scrollbar(box, orient="vertical", command=self.flow.yview)
        self.flow.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.flow.pack(side="left", fill="both", expand=True)
        for sev, col in SEV_COLOR.items():
            self.flow.tag_configure(sev, foreground=col, font=("Bahnschrift SemiBold", 9))
        self.flow.tag_configure("title", font=("Segoe UI", 10, "bold"))
        self.flow.configure(state="disabled")

    def set_flow(self, warnings):
        t = self.flow
        t.configure(state="normal")
        t.delete("1.0", "end")
        if not warnings:
            t.insert("end", "No issues found.\n", "tip")
            t.insert("end", "The chain order and levels follow normal signal-flow practice.")
        for sev, title, text in warnings:
            t.insert("end", f"{SEV_LABEL[sev]}  ", sev)
            t.insert("end", f"{title}\n", "title")
            t.insert("end", f"{text}\n\n")
        t.configure(state="disabled")

    def set_report(self, rows, board, values):
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(rows):
            d = r["out_rms"] - r["in_rms"]
            tags = []
            note = ""
            if not r["on"]:
                tags.append("off")
                note = "bypassed"
            elif r["out_pk"] > 0.0:
                tags.append("hot")
                note = "peaks above 0 dBFS (digital clipping risk)"
            elif d > 12:
                tags.append("big")
                note = "large level increase - watch the next stage"
            elif d < -12:
                tags.append("big")
                note = "large level reduction"
            elif abs(d) < 0.3:
                note = "little level change"
            self.tree.insert("", "end", iid=r["key"], values=(
                i + 1, BY_KEY[r["key"]].title.title(), "ON" if r["on"] else "off",
                f"{r['in_rms']:.1f}", f"{r['out_rms']:.1f}", f"{d:+.1f}", f"{r['out_pk']:+.1f}", note), tags=tags)

    def _whole_chain(self):
        self.tree.selection_remove(*self.tree.selection())
        self.app.lab_block_selected(None)

    def _row_selected(self, _e=None):
        sel = self.tree.selection()
        if sel:
            self.select_block(sel[0])

    def select_block(self, key):
        self.selected = key
        self.app.lab_block_selected(key)
        self.show_help(key, switch=False)

    # ---- learn
    def _learn_tab(self):
        f = tk.Frame(self.nb, bg=BG)
        self.nb.add(f, text="  Learn  ")
        top = tk.Frame(f, bg=BG)
        top.pack(fill="x", padx=4, pady=(8, 4))
        tk.Label(top, text="Block", bg=BG, fg=DIM, font=("Segoe UI", 9)).pack(side="left")
        self.help_var = tk.StringVar()
        self.help_box = ttk.Combobox(top, textvariable=self.help_var, state="readonly", width=24)
        self.help_box.pack(side="left", padx=6)
        self.help_box.bind("<<ComboboxSelected>>", lambda e: self._help_pick())
        box = tk.Frame(f, bg=BG)
        box.pack(fill="both", expand=True, padx=4)
        self.learn = tk.Text(box, bg=PANEL, fg=TEXT, wrap="word", bd=0, padx=12, pady=10, font=("Segoe UI", 10),
                             highlightthickness=0)
        sb = ttk.Scrollbar(box, orient="vertical", command=self.learn.yview)
        self.learn.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.learn.pack(side="left", fill="both", expand=True)
        self.learn.tag_configure("h1", font=("Bahnschrift SemiBold", 14), foreground=GOLD)
        self.learn.tag_configure("h2", font=("Bahnschrift SemiBold", 9), foreground="#8bd3ff", spacing1=10)
        self.learn.tag_configure("term", font=("Segoe UI", 10, "bold"), foreground=TEXT)
        self.learn.tag_configure("dim", foreground=DIM)
        self.fill_help_choices()
        self.show_help(None, switch=False)

    def fill_help_choices(self):
        keys = list(self.app.board)
        names = ["(glossary)"] + [BY_KEY[k].title.title() for k in keys]
        self._help_keys = [None] + keys
        self.help_box["values"] = names
        if self.selected in keys:
            self.help_box.current(1 + keys.index(self.selected))
        elif not self.help_var.get():
            self.help_box.current(0)

    def _help_pick(self):
        i = self.help_box.current()
        self.show_help(self._help_keys[i] if 0 <= i < len(self._help_keys) else None, switch=False)

    def show_help(self, key, switch=True):
        if switch:
            self.nb.select(1)
        if key is not None:
            self.selected = key
        if key is not None and key not in self._help_keys:
            self.fill_help_choices()
        if key in self._help_keys:
            self.help_box.current(self._help_keys.index(key))
        t = self.learn
        t.configure(state="normal")
        t.delete("1.0", "end")
        if key is not None:
            ped = BY_KEY[key]
            t.insert("end", f"{ped.title.title()}\n", "h1")
            h = H.PEDAL_HELP.get(key)
            if h:
                t.insert("end", "WHAT IT DOES\n", "h2")
                t.insert("end", h["role"] + "\n")
                t.insert("end", "WHERE IT GOES\n", "h2")
                t.insert("end", h["place"] + "\n")
                t.insert("end", "TECHNIQUE\n", "h2")
                t.insert("end", h["notes"] + "\n")
            params = [(p, H.PARAM_HELP[(key, p.name)]) for p in ped.params if (key, p.name) in H.PARAM_HELP]
            if params:
                t.insert("end", "CONTROLS\n", "h2")
                for p, txt in params:
                    t.insert("end", f"{p.label}: ", "term")
                    t.insert("end", txt + "\n")
            t.insert("end", "\n")
        t.insert("end", "Glossary\n", "h1")
        for term, text in H.GLOSSARY:
            t.insert("end", term + "\n", "term")
            t.insert("end", text + "\n\n")
        t.insert("end", "Cabinet library\n", "h1")
        t.insert("end", "Synthesized speaker + enclosure + microphone models (not captures of specific commercial "
                        "cabs). Real .wav IRs load alongside them.\n\n", "dim")
        for name, c in IRL.CABS.items():
            t.insert("end", name + "\n", "term")
            t.insert("end", c["desc"] + "\n\n")
        for name, text in IRL.MIC_DESC.items():
            t.insert("end", name.title() + " mic\n", "term")
            t.insert("end", text + "\n\n")
        t.configure(state="disabled")
        t.yview_moveto(0)

    # ---- match
    def _match_tab(self):
        f = tk.Frame(self.nb, bg=BG)
        self.nb.add(f, text="  Match a tone  ")
        pad = dict(padx=8)
        tk.Label(f, text="Match a reference recording", bg=BG, fg=GOLD, font=("Bahnschrift SemiBold", 13)).pack(
            anchor="w", pady=(10, 2), **pad)
        tk.Label(f, bg=BG, fg=TEXT, justify="left", anchor="w", wraplength=480, font=("Segoe UI", 9),
                 text="Load a song or isolated guitar clip. PedalBoard measures its long-term spectrum (1/6 octave) "
                      "and fits the cabinet / mic, the amp's bass-mid-treble-presence-depth, a low/high cut and "
                      "a 6-band EQ so that your board's output spectrum lands on it. Everything runs offline "
                      "against your own signal chain.\n\nMatching only equalizes the SPECTRUM - gain, pick "
                      "attack and playing style are yours. A full mix includes bass and drums, so an isolated "
                      "guitar track (or a section with guitars only) gives far better results.").pack(
            fill="x", pady=(0, 8), **pad)
        r = tk.Frame(f, bg=BG)
        r.pack(fill="x", **pad)
        PillButton(r, "Load reference…", self.load_reference).pack(side="left")
        PillButton(r, "Clear", self.app.clear_reference).pack(side="left", padx=6)
        self.ref_lbl = tk.Label(r, text="no reference loaded", bg=BG, fg=DIM, font=("Segoe UI", 9))
        self.ref_lbl.pack(side="left", padx=8)
        r2 = tk.Frame(f, bg=BG)
        r2.pack(fill="x", pady=(10, 0), **pad)
        self.fit_gain = tk.BooleanVar(value=False)
        tk.Checkbutton(r2, text="also fit amp GAIN (changes the amount of distortion)", variable=self.fit_gain,
                       bg=BG, fg=TEXT, selectcolor="#24242a", activebackground=BG, activeforeground=TEXT,
                       font=("Segoe UI", 9)).pack(side="left")
        r3 = tk.Frame(f, bg=BG)
        r3.pack(fill="x", pady=(10, 0), **pad)
        self.match_btn = PillButton(r3, "Match my tone to it", self.app.start_match, bg=GOLD, fg="#111")
        self.match_btn.pack(side="left")
        self.match_prog = ttk.Progressbar(r3, length=200, mode="determinate", maximum=1.0)
        self.match_prog.pack(side="left", padx=10)
        self.match_lbl = tk.Label(f, text="", bg=BG, fg=DIM, font=("Segoe UI", 9), justify="left", anchor="w",
                                  wraplength=480)
        self.match_lbl.pack(fill="x", pady=8, **pad)
        tk.Label(f, bg=BG, fg=DIM, justify="left", anchor="w", wraplength=480, font=("Segoe UI", 8),
                 text="Your previous sound is kept in slot B of the A/B switch, so you can compare the "
                      "match with what you had.").pack(fill="x", **pad)

    def load_reference(self):
        path = filedialog.askopenfilename(
            parent=self, title="Reference recording",
            filetypes=[("Audio", "*.wav *.flac *.ogg *.mp3 *.aiff"), ("All files", "*.*")],
            initialdir=self.app.settings.get("ref_dir") or None)
        if path:
            self.app.load_reference(path)

    def set_reference_label(self, text, ok=False):
        self.ref_lbl.configure(text=text, fg="#5dd36b" if ok else DIM)

    def set_match_state(self, frac, text, busy):
        self.match_prog["value"] = frac
        self.match_lbl.configure(text=text)
        self.match_btn.configure(text="Matching…" if busy else "Match my tone to it")

    def close(self):
        self.app.settings["lab_geometry"] = self.geometry()
        self.app.lab_closed()
        self.destroy()

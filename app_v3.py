"""PedalBoard v3 - same engine, pedals and features as v2, redesigned visuals.

Everything on the board (enclosures, knobs, switches, patch cables) is rendered
anti-aliased with PIL and drawn on one canvas. App logic is inherited from v2;
this file only replaces how things look.

Run:  pythonw app_v3.py   (or double-click "PedalBoard v3.bat")
"""
import math
import os
import shutil
import sys
import time
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

import app_v2
import pcaudio_v3
import updater
import widgets_v3 as W
from version import VERSION
from widgets_v3 import (BG, DIM, GOLD, TEXT, CBar, CButton, CCheck, CFootswitch, CKnob, CMeter, CSegmented,
                        CText, CTuner, CWah, ClipLed, PillButton, is_light, mix, shade)

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_V3 = os.path.join(HERE, "settings_v3.json")
app_v2.SETTINGS_FILE = SETTINGS_V3          # v3 keeps its own settings; presets are shared with v2

PW = 224          # pedal body width
GAP_X = 44        # room for patch cables between pedals
GAP_Y = 40
MARGIN = 30
PAD = 14          # enclosure shadow padding
JACK_Y = 46
SIDE_W = 178


class PedalView:
    """One pedal drawn on the board canvas; all items share the tag pv_<key>."""

    def __init__(self, app, key):
        self.app, self.key = app, key
        cv = app.canvas
        ped = app.PD.BY_KEY[key]
        c, txt = ped.color, ped.text
        light = is_light(c)
        self.tag = "pv_" + key
        tg = (self.tag, "pedal")
        self.x = self.y = 0
        self.knobs = []

        choices = [p for p in ped.params if p.choices]
        knobs = [p for p in ped.params if not p.choices and not p.hidden]
        y = 76
        wah_y = None
        if key == "wah":
            wah_y = y
            y += 120
        seg_ys = []
        for prm in choices:
            seg_ys.append(y + 10)
            y += 2 + CSegmented.ROW_H * len(CSegmented.rows(prm.choices, PW - 24))
        rows = math.ceil(len(knobs) / 3)
        knob_y0 = y + 42
        y += rows * 92
        extra_y = y
        if key in ("delay", "drums"):
            y += 34
        if key == "looper":
            y += 42
        sw_y = y + 60
        self.h = y + 104

        self.photo = W._photo(("enc", key, self.h),
                              lambda: W.enclosure_image(PW, self.h, c, PAD, JACK_Y, seed=ped.tid))
        cv.create_image(-PAD, -PAD, image=self.photo, anchor="nw", tags=tg)

        badge_fill = shade(c, 0.72) if light else shade(c, 1.45)
        self.badge_img = cv.create_image(34, 14, image=W.pill_photo(24, 16, badge_fill), tags=tg)
        self.badge_txt = cv.create_text(34, 14, text="", font=("Bahnschrift SemiBold", 8),
                                        fill="#fff" if light else "#111", tags=tg)
        bfill = shade(c, 0.8) if light else shade(c, 1.28)
        for i, (sym, cmd) in enumerate((("◀", lambda: app.move_pedal(key, -1)),
                                        ("▶", lambda: app.move_pedal(key, 1)),
                                        ("✕", lambda: app.remove_pedal(key)))):
            CButton(cv, PW - 80 + i * 23, 14, sym, cmd, fill=bfill, fg=txt, h=16, w=21,
                    font=("Segoe UI Symbol", 7), tags=tg)
        cv.create_text(PW / 2, 36, text=ped.title, fill=txt, font=W.TITLE_FONT, tags=tg)
        cv.create_text(PW / 2, 52, text=ped.desc, fill=mix(txt, c, 0.28), font=W.SMALL_FONT, width=PW - 30,
                       justify="center", anchor="n", tags=tg)

        if wah_y is not None:
            app.extras["wah_pedal"] = CWah(cv, PW / 2, wah_y, lambda v: app.set_param("wah", "pos", v),
                                           w=PW - 20, h=112, text=txt, tags=tg)
        on_fill = "#111" if light else txt
        off_fill = shade(c, 0.82) if light else shade(c, 1.3)
        for prm, sy in zip(choices, seg_ys):
            seg = CSegmented(cv, PW / 2, sy, prm.choices, lambda i, n=prm.name: app.set_param(key, n, i),
                             on_fill=on_fill, on_text=c, off_fill=off_fill, off_text=txt, tags=tg,
                             max_w=PW - 24)
            app.controls[(key, prm.name)] = seg
        vtext = mix(txt, c, 0.25)
        for i, prm in enumerate(knobs):
            r, j = divmod(i, 3)
            m = min(3, len(knobs) - r * 3)
            kx = PW / 2 + (j - (m - 1) / 2) * 70
            k = CKnob(cv, kx, knob_y0 + r * 92, prm.label, prm.lo, prm.hi, prm.default,
                      lambda v, n=prm.name: app.set_param(key, n, v), fmt=prm.fmt, log=prm.log,
                      accent=ped.ink, text=txt, vtext=vtext, step=prm.step, tags=tg)
            app.controls[(key, prm.name)] = k
            self.knobs.append(k)
        if key == "delay":
            CButton(cv, PW / 2, extra_y + 14, "TAP TEMPO", app.tap_tempo, fill=on_fill, fg=c, h=22, tags=tg)
        if key == "drums":
            CButton(cv, PW / 2, extra_y + 14, "TAP TEMPO", app.tap_drums, fill=on_fill, fg=c, h=22, tags=tg)
        if key == "looper":
            st = cv.create_text(PW / 2, extra_y + 10, text="EMPTY", fill=DIM, font=("Bahnschrift SemiBold", 12),
                                tags=tg)
            bar = CBar(cv, 26, extra_y + 26, PW - 52, tags=tg)
            main = CFootswitch(cv, PW / 2, sw_y, lambda v: app.looper_press(), momentary=True, label="REC", tags=tg)
            CButton(cv, PW / 2 - 70, sw_y, "STOP", app.looper_stop, fill="#3a3a42", tags=tg)
            CButton(cv, PW / 2 + 70, sw_y, "CLEAR", app.looper_clear, fill="#3a3a42", tags=tg)
            app.extras["looper"] = (CText(cv, st), bar, main)
        else:
            sw = CFootswitch(cv, PW / 2, sw_y, lambda v: app.set_param(key, "on", v), tags=tg)
            app.controls[(key, "on")] = sw

    def set_number(self, n):
        self.app.canvas.itemconfigure(self.badge_txt, text=str(n))

    def move_to(self, x, y):
        self.app.canvas.move(self.tag, x - self.x, y - self.y)
        self.x, self.y = x, y

    def destroy(self):
        cv = self.app.canvas
        wm = getattr(cv, "_wheel_map", {})
        for k in self.knobs:
            wm.pop(k.img, None)
        cv.delete(self.tag)
        for ck in [ck for ck in self.app.controls if ck[0] == self.key]:
            del self.app.controls[ck]
        if self.key == "wah":
            self.app.extras.pop("wah_pedal", None)
        if self.key == "looper":
            self.app.extras.pop("looper", None)


class App(app_v2.App):
    def __init__(self, root, engine_mod):
        self.cols = 0
        self.board_w = 0
        self._layout_job = None
        self.bg_photo = None
        self.side_photos = {}
        super().__init__(root, engine_mod)
        root.title(f"PedalBoard {VERSION} - Scarlett Solo")
        if self.settings.get("audio_collapsed") and self.audio_found:
            self.toggle_audio_panel()
        self.updater = updater.Updater()
        self._upd_state = None
        self.updater.check_async()          # once per launch, like PlayVault

    # ---------------------------------------------------------------- updates
    def _update_ui(self):
        u = self.updater
        state = (u.status, u.progress)
        if state == self._upd_state:
            return
        self._upd_state = state
        b = self.update_btn
        if u.status == "available":
            b.configure(text=f"⬆  Update to {u.latest}")
            b.pack(side="left", padx=3)
        elif u.status == "downloading":
            b.configure(text=f"Downloading… {u.progress}%")
        elif u.status == "installing":
            b.configure(text="Installing…")
        elif u.status == "ready":
            b.configure(text="Restart to finish update")
            if messagebox.askyesno("PedalBoard update", f"PedalBoard {u.latest} is installed.\n\n"
                                   "Restart PedalBoard now to use it?", parent=self.root):
                self.restart_for_update()
        elif u.status == "error" and b.winfo_ismapped():
            b.configure(text="Update failed - retry")
            self.status.configure(text=f"Update failed: {u.error}")
            u.status = "available" if u.latest else "error"
            self._upd_state = None

    def update_clicked(self):
        u = self.updater
        if u.status == "ready":
            self.restart_for_update()
            return
        if u.status not in ("available", "error"):
            return
        notes = (u.notes or "").strip()
        if messagebox.askyesno("PedalBoard update",
                               f"Update PedalBoard {VERSION} → {u.latest}?\n\n{notes[:800]}\n\n"
                               "Your settings, presets and recordings are kept, and the current "
                               "version is backed up first.", parent=self.root):
            u.install_async()

    def restart_for_update(self):
        self.on_close()
        updater.restart()

    # ---------------------------------------------------------------- chrome
    def _btn(self, parent, text, cmd, bg="#3a3a42", fg=TEXT):
        return PillButton(parent, text, cmd, bg=bg, fg=fg)

    def _style(self):
        super()._style()
        self.root.configure(bg=BG)
        st = ttk.Style()
        st.configure("TCombobox", fieldbackground="#24242a", background="#24242a", bordercolor="#3a3a42",
                     lightcolor="#24242a", darkcolor="#24242a", arrowsize=14)
        st.configure("Vertical.TScrollbar", background="#2a2a30", troughcolor="#141417", bordercolor="#141417",
                     arrowcolor=DIM, lightcolor="#2a2a30", darkcolor="#2a2a30")

    def _build_header(self):
        f = tk.Frame(self.root, bg=BG)
        f.pack(fill="x", padx=16, pady=(12, 6))
        tk.Label(f, text="PEDALBOARD", bg=BG, fg=TEXT, font=W.LOGO_FONT).pack(side="left")
        tk.Label(f, text=" v3", bg=BG, fg=GOLD, font=("Bahnschrift SemiBold", 13)).pack(side="left", pady=(8, 0))
        self.add_menu = tk.Menu(self.root, tearoff=0, bg="#24242a", fg=TEXT, activebackground=GOLD,
                                activeforeground="#111", font=("Segoe UI", 9))
        add = PillButton(f, "＋  ADD PEDAL", lambda: self.add_menu.tk_popup(add.winfo_rootx(),
                                                                          add.winfo_rooty() + add.winfo_height()),
                         bg=GOLD, fg="#111")
        add.pack(side="left", padx=(22, 6))
        PillButton(f, "Clear board", self.clear_board).pack(side="left", padx=3)
        self.audio_toggle = PillButton(f, "⚙  Audio & MIDI  ▴", self.toggle_audio_panel)
        self.audio_toggle.pack(side="left", padx=3)
        self.update_btn = PillButton(f, "Update", self.update_clicked, bg="#2e7d32", fg="white")   # shown when needed

        PillButton(f, "Delete", self.delete_preset).pack(side="right", padx=(4, 0))
        PillButton(f, "Save As…", self.save_preset).pack(side="right", padx=(4, 0))
        PillButton(f, "▶", lambda: self.step_preset(1), minw=34).pack(side="right", padx=(4, 0))
        self.preset_var = tk.StringVar()
        self.preset_box = ttk.Combobox(f, textvariable=self.preset_var, state="readonly", width=24,
                                       font=("Segoe UI", 10))
        self.preset_box.pack(side="right", padx=4)
        self.preset_box.bind("<<ComboboxSelected>>", lambda e: self.load_preset(self.preset_var.get()))
        PillButton(f, "◀", lambda: self.step_preset(-1), minw=34).pack(side="right")
        tk.Label(f, text="PRESET  ", bg=BG, fg=DIM, font=("Bahnschrift SemiBold", 9)).pack(side="right")
        self._refresh_presets()

    def tap_drums(self):
        now = time.monotonic()
        taps = [t for t in getattr(self, "drum_taps", []) if now - t < 2.5] + [now]
        self.drum_taps = taps[-4:]
        if len(self.drum_taps) >= 2:
            iv = [b - a for a, b in zip(self.drum_taps, self.drum_taps[1:])]
            bpm = min(300, max(40, 60.0 / (sum(iv) / len(iv))))
            self.controls[("drums", "bpm")].set_value(bpm, notify=True)

    def _tick(self):
        sw = self.controls.get(("drums", "on"))
        if sw is not None:
            step = self.engine.pedal_state("drums", self.D.S_DRUM_STEP)
            on_beat = self.engine.running and self.engine.values["drums"]["on"] and step >= 0 and int(step) % 4 == 0
            col = "#ffd60a" if on_beat else "#ff3b30"
            if sw.led != col:
                sw.set_led(col)
        if hasattr(self, "updater"):
            self._update_ui()
        super()._tick()

    def step_preset(self, d):
        names = list(self._all_presets())
        if not names:
            return
        cur = self.preset_var.get()
        i = names.index(cur) + d if cur in names else 0
        self.load_preset(names[i % len(names)])

    def _build_audio_bar(self):
        before = set(self.root.pack_slaves())
        super()._build_audio_bar()
        new = [w for w in self.root.pack_slaves() if w not in before]   # device row, MIDI row, transport
        self.transport = new[-1]
        self.audio_panel = tk.Frame(self.root, bg=BG)
        self.audio_panel.pack(fill="x", before=new[0])
        for w in new[:-1]:
            w.pack_forget()
            w.pack(in_=self.audio_panel, fill="x", padx=14, pady=2)
            w.lift(self.audio_panel)        # created before the container, so raise them above it
        self.transport.pack_configure(padx=16, pady=(4, 6))
        self.audio_open = True
        self._build_pc_audio()

    # ---------------------------------------------------------------- PC audio (virtual cable)
    def _build_pc_audio(self):
        """Second row under the player: route anything playing on the PC into the output."""
        self.tap = pcaudio_v3.PCAudioTap()
        self.tap.vol = float(self.settings.get("tap_vol", 0.8))
        row = tk.Frame(self.transport.master, bg="#1f1f25")
        row.pack(fill="x", padx=16, pady=(0, 6), after=self.transport)
        tk.Label(row, text="PC AUDIO", bg="#1f1f25", fg=TEXT, font=("Segoe UI", 8, "bold")).pack(side="left", padx=(8, 4))
        self.tap_btn = self._btn(row, "Off", self.toggle_tap)
        self.tap_btn.pack(side="left", padx=2, pady=3)
        self.tap_lbl = tk.Label(row, text="play anything on this PC and hear it here, mixed with your guitar",
                                bg="#1f1f25", fg=DIM, font=("Segoe UI", 8), anchor="w")
        self.tap_lbl.pack(side="left", padx=6)
        self.tapvol_var = tk.DoubleVar(value=self.tap.vol)
        ttk.Scale(row, from_=0.0, to=1.5, variable=self.tapvol_var, length=90,
                  command=lambda *_: setattr(self.tap, "vol", float(self.tapvol_var.get()))).pack(side="right", padx=8)
        tk.Label(row, text="Vol", bg="#1f1f25", fg=DIM, font=("Segoe UI", 8)).pack(side="right")
        self.engine.tap = self.tap
        self.root.after(300, self._tap_tick)

    def toggle_tap(self):
        if self.tap.running:
            self.tap.stop()
            self._tap_view()
            return
        try:
            self.tap.start(self.engine.sr)
        except Exception as e:   # noqa: BLE001
            messagebox.showerror("PC audio", str(e), parent=self.root)
            return
        self._tap_view()
        if not self.settings.get("tap_help_seen"):
            self.settings["tap_help_seen"] = True
            messagebox.showinfo("PC audio", "Now tell Windows to play your music into the cable:\n\n"
                                "Settings > System > Sound > Volume mixer, then set the Output device of "
                                "your browser / music app to “CABLE Input (VB-Audio Virtual Cable)”.\n\n"
                                "The music then plays only through PedalBoard (and your Scarlett's outputs). "
                                "The dot lights up green when sound arrives.", parent=self.root)

    def _tap_view(self):
        on = self.tap.running
        self.tap_btn.configure(text="On" if on else "Off", bg="#2e7d32" if on else "#3a3a42")
        self.tap_lbl.configure(text=f"listening to {self.tap.device_name}" if on else
                               "play anything on this PC and hear it here, mixed with your guitar")

    def _tap_tick(self):
        t = self.tap
        if t.running:
            if t.sr != self.engine.sr:                     # audio restarted at another sample rate
                try:
                    t.start(self.engine.sr)
                except Exception:   # noqa: BLE001
                    t.stop()
                    self._tap_view()
            live = t.peak > 0.002
            self.tap_lbl.configure(fg="#5dd36b" if live else DIM,
                                   text=f"{'● ' if live else '○ '}listening to {t.device_name}"
                                   + ("" if live else " - no sound yet, check the Volume mixer output"))
        self.root.after(300, self._tap_tick)

    def toggle_audio_panel(self):
        if self.audio_open:
            self.audio_panel.pack_forget()
            self.audio_toggle.configure(text="⚙  Audio & MIDI  ▾")
        else:
            self.audio_panel.pack(fill="x", before=self.transport)
            self.audio_toggle.configure(text="⚙  Audio & MIDI  ▴")
        self.audio_open = not self.audio_open

    # ---------------------------------------------------------------- main area
    def _build_main(self):
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill="both", expand=True, padx=12, pady=(2, 8))
        left = tk.Canvas(main, width=SIDE_W, bg=BG, highlightthickness=0)
        left.pack(side="left", fill="y")
        right = tk.Canvas(main, width=SIDE_W, bg=BG, highlightthickness=0)
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

        cx = SIDE_W / 2
        h1 = ("Bahnschrift SemiBold", 13)
        # ---- input + tuner
        left.create_text(cx, 28, text="INPUT", fill=TEXT, font=h1)
        self.in_meter = CMeter(left, 42, 54, h=112, label="IN")
        self.gain_knob = CKnob(left, 112, 108, "Gain", -12, 24, 0.0, lambda v: self._set_glob("in_gain_db", v),
                               fmt="{:+.0f} dB", accent="#8bd450", size=48)
        left.create_line(18, 200, SIDE_W - 18, 200, fill="#3a3d45")
        left.create_text(cx, 222, text="TUNER", fill=TEXT, font=h1)
        self.tuner = CTuner(left, cx, 240, w=150, h=84)
        self.tuner_mute = tk.BooleanVar(value=self.settings.get("tuner_mute", True))
        CCheck(left, cx, 356, "Mute while tuning", self.tuner_mute, command=self._apply_mute)
        self.tuner_sw = CFootswitch(left, cx, 430, lambda v: self.set_tuner(bool(v)), led="#4fc3f7")

        # ---- output + cabinet
        right.create_text(cx, 28, text="OUTPUT", fill=TEXT, font=h1)
        self.master_knob = CKnob(right, 70, 108, "Master", -30, 12, 0.0, lambda v: self._set_glob("master_db", v),
                                 fmt="{:+.0f} dB", accent="#8bd450", size=48)
        self.out_meter = CMeter(right, 140, 54, h=112, label="OUT")
        self.clip_led = ClipLed(right, 76, 176)
        right.create_line(18, 200, SIDE_W - 18, 200, fill="#3a3d45")
        right.create_text(cx, 222, text="CABINET", fill=TEXT, font=h1)
        right.create_text(cx, 242, text="speaker voicing for headphones", fill=DIM, font=W.SMALL_FONT)
        self.cab_sw = CSegmented(right, cx, 270, ["OFF", "BASIC", "IR"], lambda i: self._set_cab(i),
                                 on_fill="#32d74b", on_text="#111", off_fill="#34343c", off_text=TEXT)
        CButton(right, cx, 302, "Load IR…", self.load_ir, fill="#3a3a42")
        self.ir_lbl = CText(right, right.create_text(cx, 328, text="no IR loaded", fill=DIM, font=W.SMALL_FONT,
                                                     width=SIDE_W - 30, justify="center"))
        right.create_text(cx, 360, text="free cabinet IRs (.wav)\nare easy to find online", fill=DIM,
                          font=W.SMALL_FONT, justify="center")

    def _side_bg(self, cv, w, h):
        if w < 10 or h < 10:
            return
        ph = ImageTk.PhotoImage(W.panel_image(w, h))
        self.side_photos[str(cv)] = ph
        cv.delete("bg")
        cv.create_image(0, 0, image=ph, anchor="nw", tags="bg")
        cv.tag_lower("bg")

    def _board_wheel(self, e):
        w = e.widget
        if isinstance(w, tk.Canvas):
            wm = getattr(w, "_wheel_map", None)
            cur = w.find_withtag("current")
            if wm and cur and cur[0] in wm:
                wm[cur[0]](e)
                return
            if w is self.canvas:
                self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")

    def _on_resize(self, e):
        if abs(e.width - self.board_w) < 4:
            return
        self.board_w = e.width
        if self._layout_job:
            self.root.after_cancel(self._layout_job)
        self._layout_job = self.root.after(60, self._layout)

    # ---------------------------------------------------------------- pedals on the board
    def _panel(self, key):
        if key not in self.panels:
            self.panels[key] = PedalView(self, key)
            self._sync_panel(key)
        return self.panels[key]

    def _regrid(self):
        for k in [k for k in self.panels if k not in self.board]:
            self.panels.pop(k).destroy()
        for k in self.board:
            self._panel(k)
        self._layout()
        self._rebuild_add_menu()

    def _layout(self):
        self._layout_job = None
        cv = self.canvas
        Wd = max(self.board_w or cv.winfo_width(), PW + 2 * MARGIN)
        cols = max(1, int((Wd - 2 * MARGIN + GAP_X) // (PW + GAP_X)))
        total = cols * PW + (cols - 1) * GAP_X
        x0 = (Wd - total) / 2
        pos = {}
        y = MARGIN
        for r in range(0, len(self.board), cols):
            row = self.board[r:r + cols]
            for j, k in enumerate(row):
                pos[k] = (x0 + j * (PW + GAP_X), y)
            y += max(self.panels[k].h for k in row) + GAP_Y
        Hd = max(int(y + MARGIN), cv.winfo_height(), 200)
        for i, k in enumerate(self.board):
            v = self.panels[k]
            v.move_to(*pos[k])
            v.set_number(i + 1)

        bg = Image.new("RGB", (int(Wd), Hd))
        tile = W.board_tile()
        for tx in range(0, int(Wd), tile.size[0]):
            for ty in range(0, Hd, tile.size[1]):
                bg.paste(tile, (tx, ty))
        jacks = [((pos[k][0] - 4, pos[k][1] + JACK_Y), (pos[k][0] + PW + 4, pos[k][1] + JACK_Y)) for k in self.board]
        if jacks:
            (ix, iy), _ = jacks[0]
            W.draw_cable(bg, (ix - 70, iy + 50), (ix - 40, iy + 50), (ix - 40, iy), (ix, iy))
            for (_, o), (i, _) in zip(jacks, jacks[1:]):
                if abs(o[1] - i[1]) < 1:        # same row: short sagging patch cable
                    W.draw_cable(bg, o, (o[0] + GAP_X * 0.45, o[1] + 26), (i[0] - GAP_X * 0.45, i[1] + 26), i)
                else:                           # row wrap: runs under the board
                    W.draw_cable(bg, o, (o[0] + 60, o[1] + 140), (i[0] - 60, i[1] - 140), i)
            _, (ox, oy) = jacks[-1]
            W.draw_cable(bg, (ox, oy), (ox + 40, oy), (ox + 40, oy + 50), (ox + 70, oy + 50))
        self.bg_photo = ImageTk.PhotoImage(bg)
        cv.delete("boardbg", "empty")
        cv.create_image(0, 0, image=self.bg_photo, anchor="nw", tags="boardbg")
        cv.tag_lower("boardbg")
        if not self.board:
            cv.create_text(Wd / 2, 120, text="Your board is empty — click ＋ ADD PEDAL or pick a preset.",
                           fill=DIM, font=("Bahnschrift", 13), tags="empty")
        cv.configure(scrollregion=(0, 0, Wd, Hd))

    def _scroll_to(self, key):
        v = self.panels.get(key)
        sr = self.canvas.cget("scrollregion").split()
        if v and len(sr) == 4 and float(sr[3]) > 0:
            self.canvas.yview_moveto(max(0.0, (v.y - 20) / float(sr[3])))

    def on_close(self):
        self.settings["audio_collapsed"] = not self.audio_open
        self.settings["tap_vol"] = float(self.tapvol_var.get())
        self.tap.stop()
        super().on_close()


def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:   # noqa: BLE001
        pass
    v2_settings = os.path.join(HERE, "settings_v2.json")
    if not os.path.exists(SETTINGS_V3) and os.path.exists(v2_settings):
        shutil.copyfile(v2_settings, SETTINGS_V3)          # first run: start from your v2 setup
    root = tk.Tk()
    root.configure(bg=BG)
    root.title("PedalBoard v3")
    splash = tk.Label(root, text="PEDALBOARD v3\n\nloading pedals…", bg=BG, fg=TEXT,
                      font=("Bahnschrift SemiBold", 16), padx=80, pady=70)
    splash.pack()
    root.update()
    import engine_v2
    splash.destroy()
    app = App(root, engine_v2)
    info = updater.confirm()          # started fine: the update (if any) is kept
    if info:
        app.status.configure(text=f"Updated to PedalBoard {info.get('to')}.")
        app.hold_status = app.tick_n + 300
    root.mainloop()


if __name__ == "__main__":
    sys.exit(main())

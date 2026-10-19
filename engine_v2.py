"""Audio I/O for PedalBoard v2: duplex stream on the Scarlett running the dsp_v2 chain."""
import os

os.environ.setdefault("SD_ENABLE_ASIO", "1")   # must precede the sounddevice import

import gc
import sys
import threading
import time as _time
from math import gcd

import numpy as np
import sounddevice as sd

import dsp_v2 as D
from pedals_v2 import BY_KEY, PEDALS, defaults

# Python hands the GIL between threads every 5 ms by default - longer than a whole
# audio buffer. Switch far more often so the audio callback never waits on the UI.
sys.setswitchinterval(0.0005)

# WDM-KS before WASAPI: on the Scarlett, WASAPI exclusive ran at the wrong clock (scratchy)
API_PREFERENCE = ["ASIO", "Windows WDM-KS", "Windows WASAPI", "Windows DirectSound", "MME"]
TUNER_LEN = 8192


def read_wav(path, sr):
    """Load a WAV (8/16/24/32-bit int or float) as float64 (frames, 2) at sample rate sr."""
    from scipy.io import wavfile
    from scipy.signal import resample_poly
    rate, data = wavfile.read(path)
    if data.dtype == np.uint8:
        data = (data.astype(np.float64) - 128.0) / 128.0
    elif data.dtype == np.int16:
        data = data / 32768.0
    elif data.dtype == np.int32:
        data = data / 2147483648.0
    else:
        data = data.astype(np.float64)
    if data.ndim == 1:
        data = data[:, None]
    data = data[:, :2]
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    if rate != sr:
        g = gcd(int(rate), int(sr))
        data = resample_poly(data, sr // g, rate // g, axis=0)
    return np.ascontiguousarray(data, dtype=np.float64)


def write_wav(path, data, sr):
    from scipy.io import wavfile
    wavfile.write(path, int(sr), np.asarray(data, dtype=np.float32))


def is_focusrite(name):
    n = name.lower()
    return "focusrite" in n or "scarlett" in n


def rescan():
    """Re-initialise PortAudio so newly plugged-in interfaces show up."""
    sd._terminate()
    sd._initialize()


def host_apis():
    names = [h["name"] for h in sd.query_hostapis()]
    return sorted(names, key=lambda n: API_PREFERENCE.index(n) if n in API_PREFERENCE else 99)


def devices_for(hostapi_name, kind):
    apis = sd.query_hostapis()
    out = []
    for i, d in enumerate(sd.query_devices()):
        if apis[d["hostapi"]]["name"] != hostapi_name:
            continue
        ch = d["max_input_channels"] if kind == "input" else d["max_output_channels"]
        if ch > 0:
            out.append((i, d["name"], ch))
    return out


def find_device(hostapi_name, kind, name):
    for idx, n, _ in devices_for(hostapi_name, kind):
        if n == name:
            return idx
    return None


def suggest_config():
    """Pick the Scarlett if connected (ASIO first), else the system defaults."""
    apis = host_apis()
    for api in apis:
        ins = [d for d in devices_for(api, "input") if is_focusrite(d[1])]
        outs = [d for d in devices_for(api, "output") if is_focusrite(d[1])]
        if ins and outs:
            return {"hostapi": api, "input": ins[0][1], "output": outs[0][1], "found": True}
    api = "Windows WASAPI" if "Windows WASAPI" in apis else apis[0]
    info = next(h for h in sd.query_hostapis() if h["name"] == api)
    ins, outs = devices_for(api, "input"), devices_for(api, "output")
    din, dout = info["default_input_device"], info["default_output_device"]
    in_name = sd.query_devices(din)["name"] if din >= 0 else (ins[0][1] if ins else "")
    out_name = sd.query_devices(dout)["name"] if dout >= 0 else (outs[0][1] if outs else "")
    return {"hostapi": api, "input": in_name, "output": out_name, "found": False}


def warmup():
    """Compile (or load cached) DSP before the UI and audio start."""
    AudioEngine(compile_only=True)


class AudioEngine:
    def __init__(self, compile_only=False):
        self.P = np.zeros(D.N_TYPES * D.PST)
        self.S = np.zeros(D.N_TYPES * 2 * D.SST)
        self.G = np.zeros(D.N_G)
        self.GS = np.zeros(D.N_GS)
        self.wasst = np.zeros(D.N_TYPES, dtype=np.int64)
        self.L = np.zeros(16384)
        self.R = np.zeros(16384)
        self.dryL = np.zeros(16384)
        self.dryR = np.zeros(16384)
        self.tuner_buf = np.zeros(TUNER_LEN)
        self.tuner_w = 0
        self.raw_peak = 0.0                      # peak of the raw input since the UI last reset it
        self.stream = None
        self.xruns = 0
        self.late = 0
        self.max_ms = 0.0
        self.frames_total = 0
        self.in_channel = 1
        self.sr = 48000
        self.description = ""
        self.values = {p.key: defaults(p.key) for p in PEDALS}
        self.chain = (np.zeros(D.N_TYPES, dtype=np.int64), 0)
        self.ir_path = None
        self.ir_name = ""
        self.ir_source = None        # callable(sr) -> impulse response array, for generated cabinets
        # file player: "backing" mixes into the output, "through" feeds the pedals (re-amping)
        self.player_path = None
        self.player_data = None
        self.player_pos = 0
        self.player_playing = False
        self.player_loop = True
        self.player_mode = "backing"
        self.player_vol = 0.7
        self.tap = None              # optional PCAudioTap, see pcaudio_v3.py
        self.rec_out = None          # lists of blocks while recording
        self.rec_di = None
        self.rec_frames = 0
        self._alloc(48000)
        for key, vals in self.values.items():
            for name, v in vals.items():
                self.set(key, name, v)
        self.set_global(in_gain_db=0.0, cab=1, master_db=0.0, mute=0)
        self.set_board([p.key for p in PEDALS])
        self._run(256)                       # triggers JIT compile / cache load
        self.reset()
        if compile_only:
            return
        self.set_board([])

    # ---- memory / state
    def _alloc(self, sr):
        sizes = D.mem_sizes(sr)
        off = np.zeros(D.N_TYPES, dtype=np.int64)
        total = 0
        for t in range(D.N_TYPES):
            off[t] = total
            total += sizes[t] * (2 if D.KIND[t] == 0 else 1)
        self.MEM = np.zeros(max(total, 1))
        self.MEMOFF = off
        self.MEMLEN = sizes
        self.sr = sr
        self.irM = int(D.IR_SECONDS * sr) + 1
        self.IR = np.zeros(self.irM)
        self.HIST = np.zeros(4 * self.irM)
        self.G[D.G_IR_LEN] = 0
        if self.ir_source is not None:       # regenerate a synthesized cabinet for the new rate
            try:
                self.set_ir(self.ir_source(sr), self.ir_name, source=self.ir_source)
            except Exception:   # noqa: BLE001
                self.clear_ir()
        elif self.ir_path:                   # re-resample files for the new rate
            try:
                self.load_ir(self.ir_path)
            except Exception:   # noqa: BLE001
                self.clear_ir()
        if self.player_path:
            try:
                self.load_player(self.player_path)
            except Exception:   # noqa: BLE001
                self.player_path = self.player_data = None

    def reset(self):
        self.S[:] = 0.0
        self.MEM[:] = 0.0
        self.HIST[:] = 0.0
        self.wasst[:] = 0
        self.GS[:] = 0.0
        self.GS[D.GS_MASTER] = self.G[D.G_MASTER]
        self.S[D.T_WAH * 2 * D.SST + D.S_WAH_POS] = 0.5
        self.S[D.T_DRUMS * 2 * D.SST + 2] = -1.0      # drums start on step 0
        # keep the looper's clear counter in sync so a reset doesn't look like a clear
        self.S[D.T_LOOPER * 2 * D.SST + 4] = self.P[D.T_LOOPER * D.PST + 3]

    # ---- parameters
    def set(self, key, name, value):
        self.values[key][name] = value
        ped = BY_KEY[key]
        base = ped.tid * D.PST
        if name == "on":
            self.P[base] = float(value)
            return
        for i, prm in enumerate(ped.params):
            if prm.name == name:
                self.P[base + 1 + i] = prm.conv(value)
                return

    # ---- cabinet impulse response
    def load_ir(self, path):
        self.set_ir(read_wav(path, self.sr)[:, 0], os.path.basename(path))
        self.ir_path = path

    def set_ir(self, h, name, source=None):
        """Install an impulse response (float array at the engine's sample rate)."""
        h = np.asarray(h, dtype=np.float64)
        nz = np.nonzero(np.abs(h) > 1e-4 * np.abs(h).max())[0] if len(h) else []
        if len(nz) == 0:
            raise ValueError("The impulse response is silent.")
        h = h[nz[0]:]                                 # drop leading silence (= latency)
        n = min(len(h), self.irM)
        h = h[:n].copy()
        fade = max(1, n // 10)
        h[n - fade:] *= np.linspace(1.0, 0.0, fade)   # avoid a truncation click
        # level-match cabinets by their average response over the guitar's core range (300 Hz - 3 kHz),
        # so swapping cabs changes tone, not loudness
        mag = np.abs(np.fft.rfft(h, 8192))
        f = np.fft.rfftfreq(8192, 1.0 / self.sr)
        band = (f >= 300.0) & (f <= 3000.0)
        h *= 1.0 / np.exp(np.mean(np.log(mag[band] + 1e-9)))
        self.G[D.G_IR_LEN] = 0                        # stop using it while we swap
        self.IR[:] = 0.0
        self.IR[:n] = h[::-1]
        self.G[D.G_IR_LEN] = n
        self.ir_path = None
        self.ir_name = name
        self.ir_source = source

    def ir_response(self, points=256):
        """Magnitude response (dB) of the installed IR on a log frequency axis, or None."""
        n = int(self.G[D.G_IR_LEN])
        if n <= 0:
            return None
        h = self.IR[:n][::-1]
        mag = np.abs(np.fft.rfft(h, 8192))
        f = np.fft.rfftfreq(8192, 1.0 / self.sr)
        fx = np.geomspace(40.0, 12000.0, points)
        return fx, 20.0 * np.log10(np.interp(fx, f, mag) + 1e-9)

    def clear_ir(self):
        self.G[D.G_IR_LEN] = 0
        self.ir_path = None
        self.ir_name = ""
        self.ir_source = None

    # ---- file player
    def load_player(self, path):
        data = read_wav(path, self.sr)
        self.player_playing = False
        self.player_data = data
        self.player_pos = 0
        self.player_path = path

    def player_progress(self):
        d = self.player_data
        if d is None or len(d) == 0:
            return 0.0, 0.0
        return self.player_pos / self.sr, len(d) / self.sr

    def _player_chunk(self, frames):
        d = self.player_data
        if d is None or not self.player_playing or len(d) == 0:
            return None
        out = np.zeros((frames, 2))
        got = 0
        while got < frames:
            k = min(frames - got, len(d) - self.player_pos)
            out[got:got + k] = d[self.player_pos:self.player_pos + k]
            got += k
            self.player_pos += k
            if self.player_pos >= len(d):
                self.player_pos = 0
                if not self.player_loop:
                    self.player_playing = False
                    break
        return out * self.player_vol

    # ---- recorder
    def rec_start(self):
        self.rec_frames = 0
        self.rec_di = []
        self.rec_out = []

    def rec_seconds(self):
        return self.rec_frames / self.sr

    def rec_stop(self, out_path, di_path, done=None):
        """Stop recording and write both WAVs on a background thread."""
        out, di, sr = self.rec_out, self.rec_di, self.sr
        self.rec_out = self.rec_di = None

        def work():
            err = None
            try:
                if out:
                    write_wav(out_path, np.concatenate(out), sr)
                    write_wav(di_path, np.concatenate(di), sr)
            except Exception as e:   # noqa: BLE001
                err = e
            if done:
                done(err)
        threading.Thread(target=work, daemon=True).start()

    def set_global(self, in_gain_db=None, cab=None, master_db=None, mute=None, cabpos=None):
        if in_gain_db is not None:
            self.G[D.G_IN_GAIN] = 10 ** (in_gain_db / 20)
        if cab is not None:
            self.G[D.G_CAB] = float(cab)
        if cabpos is not None:
            self.G[D.G_CABPOS] = float(cabpos)
        if master_db is not None:
            self.G[D.G_MASTER] = 10 ** (master_db / 20)
        if mute is not None:
            self.G[D.G_MUTE] = float(mute)

    def set_board(self, keys):
        arr = np.zeros(D.N_TYPES, dtype=np.int64)
        for i, k in enumerate(keys):
            arr[i] = BY_KEY[k].tid
        self.chain = (arr, len(keys))          # swapped atomically for the audio thread

    def pedal_state(self, key, slot):
        return self.S[BY_KEY[key].tid * 2 * D.SST + slot]

    def read_meters(self):
        gs = self.GS
        pin, pout, clips = gs[D.GS_PEAK_IN], gs[D.GS_PEAK_OUT], gs[D.GS_CLIPS]
        gs[D.GS_PEAK_IN] = gs[D.GS_PEAK_OUT] = gs[D.GS_CLIPS] = 0.0
        return pin, pout, clips

    def tuner_snapshot(self):
        w = self.tuner_w
        return np.concatenate((self.tuner_buf[w:], self.tuner_buf[:w]))

    def latency_info(self):
        """Driver-reported latencies in ms: (input, output, buffer) or None when stopped."""
        s = self.stream
        if s is None:
            return None
        try:
            bs = s.blocksize or 0
            return s.latency[0] * 1000.0, s.latency[1] * 1000.0, 1000.0 * bs / s.samplerate
        except Exception:   # noqa: BLE001
            return None

    @property
    def running(self):
        return self.stream is not None and self.stream.active

    # ---- stream
    def start(self, hostapi, in_name, out_name, in_channel, samplerate, blocksize, exclusive=True):
        self.stop()
        if hostapi == "ASIO":
            out_name = in_name
        in_idx = find_device(hostapi, "input", in_name)
        out_idx = find_device(hostapi, "output", out_name)
        if in_idx is None or out_idx is None:
            raise RuntimeError("Selected audio device not found - is the Scarlett plugged in? Try Rescan.")
        max_in = sd.query_devices(in_idx)["max_input_channels"]
        max_out = sd.query_devices(out_idx)["max_output_channels"]
        if in_channel >= 0:
            self.in_channel = min(in_channel, max_in - 1)
            n_in = self.in_channel + 1
        else:
            self.in_channel = -1
            n_in = min(2, max_in)
        n_out = min(2, max_out)

        dev_sr = int(sd.query_devices(in_idx)["default_samplerate"])
        rates = [samplerate] + ([dev_sr] if dev_sr != samplerate else [])
        attempts = []
        if hostapi == "Windows WASAPI":
            if exclusive:
                attempts += [("exclusive", sd.WasapiSettings(exclusive=True), r) for r in rates]
            attempts.append(("shared", sd.WasapiSettings(auto_convert=True), samplerate))
        else:
            attempts += [("", None, r) for r in rates]

        errors = []
        for label, extra, sr in attempts:
            if sr != self.sr:
                self._alloc(sr)
            self.reset()
            self.xruns = 0
            self.late = 0
            self.max_ms = 0.0
            gc.collect()
            gc.freeze()          # keep startup objects out of future GC passes (shorter pauses)
            try:
                stream = sd.Stream(
                    device=(in_idx, out_idx), samplerate=sr, blocksize=blocksize,
                    channels=(n_in, n_out), dtype="float32", latency="low",
                    extra_settings=(extra, extra) if extra else None,
                    callback=self._callback, dither_off=True)
                stream.start()
            except Exception as e:   # noqa: BLE001 - report every failed attempt
                errors.append(f"{hostapi} {label} @ {sr} Hz: {e}")
                continue
            # Some drivers accept a rate but actually clock the device at another one
            # (seen: WASAPI exclusive on a Scarlett at 44.1 kHz). In/out then drift and
            # it sounds scratchy - measure the real rate and reject a mismatch.
            _time.sleep(0.15)
            f0, t0 = self.frames_total, _time.perf_counter()
            _time.sleep(0.5)
            real = (self.frames_total - f0) / (_time.perf_counter() - t0)
            if abs(real - sr) / sr > 0.03:
                stream.stop()
                stream.close()
                errors.append(f"{hostapi} {label} @ {sr} Hz: device actually ran at ~{real:.0f} Hz")
                continue
            self.stream = stream
            lat = (stream.latency[0] + stream.latency[1]) * 1000.0
            mode = f" ({label})" if label else ""
            self.description = (f"{hostapi}{mode} | {int(stream.samplerate)} Hz | "
                                f"buffer {blocksize} | round-trip ~{lat:.1f} ms")
            return self.description
        raise RuntimeError("Could not open audio stream:\n" + "\n".join(errors))

    def stop(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:   # noqa: BLE001
                pass
            self.stream = None

    def _run(self, n):
        order, nord = self.chain
        D.run_chain(self.L, self.R, n, order, nord, self.P, self.S, self.MEM, self.MEMOFF,
                    self.MEMLEN, self.G, self.GS, self.dryL, self.dryR, self.wasst, self.IR,
                    self.HIST, float(self.sr))

    def _callback(self, indata, outdata, frames, time, status):
        t0 = _time.perf_counter()
        try:
            self._process(indata, outdata, frames, status)
        finally:
            ms = (_time.perf_counter() - t0) * 1000.0
            if ms > self.max_ms:
                self.max_ms = ms
            if ms > 0.8 * 1000.0 * frames / self.sr:     # used >80% of the buffer's time
                self.late += 1

    def _process(self, indata, outdata, frames, status):
        self.frames_total += frames
        if status:
            self.xruns += 1
        if frames > len(self.L):
            outdata.fill(0)
            return
        L = self.L
        if self.in_channel >= 0:
            L[:frames] = indata[:, self.in_channel]
        else:
            L[:frames] = indata.mean(axis=1)
        # tuner ring buffer (raw input)
        if frames <= TUNER_LEN:
            w = self.tuner_w
            k = min(frames, TUNER_LEN - w)
            self.tuner_buf[w:w + k] = L[:k]
            if k < frames:
                self.tuner_buf[:frames - k] = L[k:frames]
            self.tuner_w = (w + frames) % TUNER_LEN
        pk = float(np.abs(L[:frames]).max()) if frames else 0.0
        if pk > self.raw_peak:
            self.raw_peak = pk
        rec_di = self.rec_di
        if rec_di is not None:
            rec_di.append(L[:frames].astype(np.float32))
        chunk = self._player_chunk(frames)
        if chunk is not None and self.player_mode == "through":
            L[:frames] += chunk.mean(axis=1)          # re-amp a recorded DI through the board
        self._run(frames)
        tap = self.tap
        if tap is not None:                           # PC audio (virtual cable) mixes in after the pedals
            t = tap.read(frames)
            if t is not None:
                L[:frames] += t[:, 0]
                self.R[:frames] += t[:, 1]
                np.clip(L[:frames], -1.0, 1.0, out=L[:frames])
                np.clip(self.R[:frames], -1.0, 1.0, out=self.R[:frames])
        if chunk is not None and self.player_mode == "backing":
            L[:frames] += chunk[:, 0]
            self.R[:frames] += chunk[:, 1]
            np.clip(L[:frames], -1.0, 1.0, out=L[:frames])
            np.clip(self.R[:frames], -1.0, 1.0, out=self.R[:frames])
        outdata[:, 0] = L[:frames]
        if outdata.shape[1] > 1:
            outdata[:, 1] = self.R[:frames]
        rec_out = self.rec_out
        if rec_out is not None:
            self.rec_frames += frames
            rec_out.append(np.stack((L[:frames], self.R[:frames]), axis=1).astype(np.float32))

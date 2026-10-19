"""PC audio tap - lets anything playing on the PC come out of the pedalboard.

Windows is told to play the music into a virtual cable (VB-Cable's "CABLE Input"); this opens the
other end ("CABLE Output") as a second input stream and the engine mixes it into the output next
to the guitar. The two devices run on different clocks, so the ring buffer is read at a slightly
adjusted rate to keep its fill level steady instead of slowly under- or over-running.
"""
import numpy as np
import sounddevice as sd

CABLE_HINTS = ("CABLE Output",)         # capture side of VB-Cable
TARGET_S = 0.09                          # buffer fill to hold (music latency doesn't matter)
CAPACITY_S = 1.0
MAX_ADJ = 0.01                           # +-1 % resample ratio is inaudible


def find_device(hint=None):
    """Return (index, name) of the capture device to use, or None."""
    hints = (hint,) if hint else CABLE_HINTS
    wasapi = next((i for i, h in enumerate(sd.query_hostapis()) if h["name"] == "Windows WASAPI"), None)
    best = None
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] < 1 or not any(h.lower() in d["name"].lower() for h in hints):
            continue
        if d["hostapi"] == wasapi:
            return i, d["name"]
        best = best or (i, d["name"])
    return best


class PCAudioTap:
    def __init__(self):
        self.stream = None
        self.sr = 0
        self.vol = 0.8
        self.peak = 0.0                  # recent input peak (for the signal light)
        self.underruns = 0
        self.device_name = ""
        self._buf = None
        self._cap = 0
        self._w = 0                      # absolute frame counters
        self._r = 0
        self._frac = 0.0
        self._primed = False

    @property
    def running(self):
        return self.stream is not None

    def start(self, sr, device_hint=None):
        self.stop()
        dev = find_device(device_hint)
        if dev is None:
            raise RuntimeError("No virtual cable found.\n\nInstall VB-Cable (vb-audio.com/Cable) - "
                               "it adds the 'CABLE Input' / 'CABLE Output' devices this uses.")
        idx, name = dev
        self.sr = int(sr)
        self._cap = int(CAPACITY_S * self.sr)
        self._buf = np.zeros((self._cap, 2), dtype=np.float32)
        self._w = self._r = 0
        self._frac = 0.0
        self._primed = False
        self.peak = 0.0
        extra = None
        if sd.query_hostapis(sd.query_devices(idx)["hostapi"])["name"] == "Windows WASAPI":
            extra = sd.WasapiSettings(auto_convert=True)      # let Windows match our sample rate
        ch = min(2, sd.query_devices(idx)["max_input_channels"])
        self.stream = sd.InputStream(device=idx, samplerate=self.sr, channels=ch, dtype="float32",
                                     blocksize=0, latency="high", extra_settings=extra,
                                     callback=self._on_input)
        self.stream.start()
        self.device_name = name

    def stop(self):
        s, self.stream = self.stream, None
        if s is not None:
            try:
                s.stop()
                s.close()
            except Exception:   # noqa: BLE001
                pass
        self.peak = 0.0

    # ---- capture thread
    def _on_input(self, indata, frames, time, status):
        n = len(indata)
        if n == 0 or self._buf is None:
            return
        self.peak = max(float(np.abs(indata).max()), self.peak * 0.9)
        x = indata if indata.shape[1] == 2 else np.repeat(indata[:, :1], 2, axis=1)
        if n > self._cap:
            x, n = x[-self._cap:], self._cap
        over = self._w + n - self._r - self._cap
        if over > 0:                                          # reader fell behind: drop the oldest
            self._r += over
        i = self._w % self._cap
        k = min(n, self._cap - i)
        self._buf[i:i + k] = x[:k]
        if k < n:
            self._buf[:n - k] = x[k:]
        self._w += n

    # ---- audio thread (called from the engine callback)
    def read(self, frames):
        """Return (frames, 2) float64 to mix in, or None while there's nothing to play."""
        buf = self._buf
        if buf is None or self.stream is None:
            return None
        target = int(TARGET_S * self.sr)
        avail = self._w - self._r
        if not self._primed:
            if avail < target:
                return None
            self._primed = True
        # read a touch faster when the buffer is filling up, slower when it's draining
        ratio = 1.0 + max(-MAX_ADJ, min(MAX_ADJ, (avail - target) / self.sr * 0.5))
        need = frames * ratio + self._frac + 2
        if avail < need:
            self.underruns += 1
            self._primed = False
            return None
        pos = self._frac + np.arange(frames) * ratio
        i0 = pos.astype(np.int64)
        f = (pos - i0)[:, None]
        idx = (self._r + i0) % self._cap
        out = buf[idx] * (1.0 - f) + buf[(idx + 1) % self._cap] * f
        end = self._frac + frames * ratio
        adv = int(end)
        self._frac = end - adv
        self._r += adv
        return out * self.vol

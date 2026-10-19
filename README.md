# PedalBoard v4

A guitar pedalboard for Windows, built for the Focusrite Scarlett Solo - v3's board (33 effects, amp sim,
looper, drum machine, recorder, presets, PC-audio mixing) plus tools for **finding and understanding a tone**.

v4 lives in its own folder (`PedalBoard_v4`) and its own settings (`settings_v4.json`, seeded from your v3
settings on first run). v3 is untouched. Auto-update is disabled in v4.

## What's new

**Amps and cabinets**
- 8 amp voicings: CLEAN, CRUNCH, LEAD, METAL (unchanged, bit-identical to v3) + PLEXI, BLACKFACE, CHIME, MODERN.
  Each voicing sets gain structure, tone-stack frequencies, a fixed bass/mid/treble contour and power-amp sag.
- Cabinet library: 6 synthesized speaker + enclosure models, 3 microphone types, and Position (cap -> edge),
  Distance (proximity effect), Blend (second ribbon mic, real comb filtering) and Room (early reflections).
  Your own `.wav` IRs also work (`irs/` folder or *Load IR...*). The cab response is plotted live.
  These are *models*, not captures of specific commercial cabinets.
- Placement: cabinet *after the amp* or *at the end*. This only changes the sound for non-linear / modulated
  blocks after the amp (compressor, modulation, distortion); delay, reverb and EQ are linear and commute.
- Cab settings are saved in presets. 11 complete rigs (`Rig: ...`) appear at the end of the preset list.

**Learn / explore**
- Live spectrum strip (input vs output, 1/6-octave, named bands, hover read-out). With audio stopped it
  analyses a built-in test riff through your board, so it works without a guitar.
- **Tone Lab** window:
  - *Chain*: renders a test guitar through every block - level in/out, gain change, peak, and the spectrum
    before/after the selected block. Plus the **flow check** (rule-based review of pedal order, levels, cab).
  - *Learn*: what each block does, where it goes, technique, controls, glossary, cabinet/mic notes.
    The (i) on every pedal opens its page.
  - *Match a tone*: load a recording; PedalBoard fits cabinet/mic, amp tone controls, low/high cut and a
    6-band EQ so your board's output spectrum lands on it (offline, ~1 min). Your previous sound goes to B.
- A/B compare, named Snapshots, **Auto level** (sets input gain for ~-12 dBFS peaks), latency read-out with
  ASIO guidance.

## Running

1. Python 3.12 and `pip install -r requirements.txt`.
2. Guitar into the Scarlett's INST input (input 2), Direct Monitor off.
3. Double-click `PedalBoard.bat` (starts `launch.py` -> `app_v4.py`).

## Tests

    python tests/offline_test_v4.py     # amps, cabs, placement, analysis, flow rules, tone matching
    python tests/offline_test_v2.py     # every pedal alone + full boards (from v2)

## Code layout (v4 additions)

| File | What |
|---|---|
| `app_v4.py` | the app: cabinet panel, tone bar, A/B, snapshots, analyzer plumbing, matching |
| `lab_v4.py` | Tone Lab window + the spectrum view |
| `analysis_v4.py` | spectra, offline `Probe` engine, per-block report, flow rules, tone matcher |
| `irlib_v4.py` | synthesized cabinet / mic / room impulse responses |
| `rigs_v4.py`, `tonehelp_v4.py` | built-in rigs; learn-tab text |
| `dsp_v2.py`, `engine_v2.py`, `pedals_v2.py` | core engine (v4 adds amp voicings, cab placement, IR tools, analyzer taps) |

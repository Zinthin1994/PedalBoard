# PedalBoard v4

A guitar pedalboard for Windows, built for the Focusrite Scarlett Solo - v3's board (34 effects, amp sim,
looper, drum machine, recorder, presets, PC-audio mixing) plus a proper cabinet section, more amps and two
switchable boards.

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
- Every preset sets its cabinet: the built-in presets each have a matching cab (`rigs_v4.PRESET_CABS`), presets
  you save store the cab you're using, and an older preset without one gets a cab to suit its amp / pedals.
  Boards with an amp put the cab right after it; boards without one put it at the end.
- 12 extra presets with the new amp voicings and cabs (Blackface Clean, Plexi Crunch, Modern High-Gain, ...)
  appear at the end of the preset list, so MIDI program numbers of the older presets don't move.

**Boards**
- **BOARDS A / B** (under the header): two complete boards - pedals, order, every setting, amp, cabinet, input
  and master level - that you flip between with one click. The first click on B copies the board you are on;
  change it (or load a preset into it), then switch freely. Both boards are remembered when you close the app.
- **Auto level** (left panel): sets the input gain for ~-12 dBFS peaks. A latency read-out with ASIO guidance
  sits next to it.

## Running

1. Python 3.12 and `pip install -r requirements.txt`.
2. Guitar into the Scarlett's INST input (input 2), Direct Monitor off.
3. Double-click `PedalBoard.bat` (starts `launch.py` -> `app_v4.py`).

## Tests

    python tests/offline_test_v4.py     # amp voicings, cabs, level matching, placement
    python tests/offline_test_v2.py     # every pedal alone + full boards (from v2)

## Code layout (v4 additions)

| File | What |
|---|---|
| `app_v4.py` | the app: cabinet panel, BOARDS A/B, auto level, latency card |
| `irlib_v4.py` | synthesized cabinet / mic / room impulse responses |
| `rigs_v4.py` | cabinets for the built-in presets, v4's extra presets, default cab for presets without one |
| `dsp_v2.py`, `engine_v2.py`, `pedals_v2.py` | core engine (v4 adds amp voicings, cab placement and IR tools) |
| `tests/probe_v4.py` | offline engine + test riff used by the tests |

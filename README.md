# PedalBoard

A guitar pedalboard for Windows, built for the Focusrite Scarlett Solo: 33 effects
you can add, remove and re-order, plus an amp simulator, cabinet IRs, tuner, looper,
drum machine, recorder and presets.

**Pedals:** noise gate, metal gate, compressor, volume swell, clean boost, tight boost,
overdrive, distortion, fuzz, Chainsaw (HM-2 style), Metal Core (Metal Zone style),
amp (clean / crunch / lead / metal), wah, envelope filter, graphic EQ, octaver,
pitch shifter, drop tuner, ring mod, bit crusher, phaser, uni-vibe, tremolo, vibrato,
chorus, flanger, rotary, auto-pan, doubler, delay, reverb, looper, drum machine.

## Running

1. Install Python 3.12 and the requirements: `pip install -r requirements.txt`
2. Plug the guitar into the Scarlett's INST input (input 2), turn **Direct Monitor off**.
3. Double-click `PedalBoard.bat`.

The first launch compiles the DSP (a few seconds); after that it starts quickly.

On the Scarlett with Windows' own driver, use **Windows WDM-KS** (picked automatically) -
WASAPI exclusive can run the device at the wrong sample rate, which sounds scratchy.
Installing Focusrite Control adds the ASIO driver for lower latency.

## Updates

PedalBoard checks this repo's latest GitHub release when it opens. If there is a newer
one, an **Update** button appears: it downloads `PedalBoard.zip`, verifies its SHA-256
checksum, backs up the current files and installs. Settings, presets and recordings are
kept. If the new version fails to start, the previous one is restored automatically.

Publishing a release: bump `VERSION` in `version.py`, commit, then
`python tools/make_release.py` and attach `dist/PedalBoard.zip` to a GitHub release
tagged `v<version>`.

## Code layout

| File | What |
|---|---|
| `dsp_v2.py` | all effects (numba-compiled, per-sample) |
| `pedals_v2.py` | pedal catalogue: names, knobs, ranges |
| `engine_v2.py` | audio I/O, IR loader, player, recorder |
| `app_v2.py` | app logic (presets, MIDI, looper, keys) |
| `app_v3.py`, `widgets_v3.py` | the UI |
| `pcaudio_v3.py` | PC audio tap: captures a virtual cable so any PC sound mixes into the output |
| `updater.py`, `launch.py`, `version.py` | self-update |
| `tests/offline_test_v2.py` | offline DSP tests |

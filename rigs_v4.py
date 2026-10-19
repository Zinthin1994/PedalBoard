"""Presets for PedalBoard v4: the cabinet for every built-in preset, plus v4's extra presets.

A preset's 'cab' entry is the cabinet model, mic, position, distance, blend, room and 'place'
(1 = cabinet right after the amp, 0 = at the end of the chain). Boards with an amp put the cab right after
it, so anything after the amp - modulation, delay, the drum machine - is not filtered by the speaker.
Boards without an amp play "pedals straight into a speaker", so the cab goes at the end.
"""


def cab(name, mic="DYNAMIC", pos=0.2, dist=0.2, blend=0.0, room=0.0, mode=2, place=1):
    return {"mode": mode, "cab": name, "mic": mic, "pos": pos, "dist": dist, "blend": blend, "room": room,
            "place": place}


V_1X12, V_CHIME, V_BRIT, V_MODERN, V_SMALL, V_DARK = (
    "1x12 Open-back Vintage", "2x12 Open-back Chime", "4x12 Closed British", "4x12 Closed Modern",
    "1x10 Small Combo", "2x12 Warm Dark")

# Cabinets for the presets that came with v2/v3 (those presets have no cab of their own).
PRESET_CABS = {
    # pedals only - the cab is the speaker the pedals play into
    "Clean": cab(V_1X12, "DYNAMIC", 0.2, 0.25, 0.0, 0.12, place=0),
    "Clean Chorus": cab(V_CHIME, "DYNAMIC", 0.25, 0.3, 0.0, 0.15, place=0),
    "Blues Drive": cab(V_1X12, "DYNAMIC", 0.3, 0.2, 0.2, 0.12, place=0),
    "Classic Rock": cab(V_BRIT, "DYNAMIC", 0.25, 0.2, 0.25, 0.1, place=0),
    "Metal": cab(V_MODERN, "DYNAMIC", 0.3, 0.15, 0.0, 0.05, place=0),
    "Hendrix": cab(V_BRIT, "DYNAMIC", 0.3, 0.3, 0.2, 0.2, place=0),
    "Gilmour Lead": cab(V_BRIT, "DYNAMIC", 0.35, 0.3, 0.35, 0.15, place=0),
    "Funk": cab(V_CHIME, "DYNAMIC", 0.2, 0.2, 0.0, 0.1, place=0),
    "Wah Funk-Rock": cab(V_1X12, "DYNAMIC", 0.25, 0.2, 0.15, 0.1, place=0),
    "Ambient Swells": cab(V_CHIME, "CONDENSER", 0.35, 0.4, 0.0, 0.25, place=0),
    "Surf": cab(V_CHIME, "DYNAMIC", 0.15, 0.3, 0.0, 0.2, place=0),
    "80s Shred": cab(V_BRIT, "DYNAMIC", 0.25, 0.2, 0.2, 0.1, place=0),
    "Leslie Organ-ish": cab(V_DARK, "CONDENSER", 0.3, 0.5, 0.0, 0.3, place=0),
    "Lo-Fi Synth": cab(V_SMALL, "RIBBON", 0.4, 0.4, 0.0, 0.2, place=0),
    "Harmony Lead": cab(V_BRIT, "DYNAMIC", 0.3, 0.25, 0.25, 0.12, place=0),
    "Jet Flanger": cab(V_BRIT, "DYNAMIC", 0.25, 0.2, 0.0, 0.1, place=0),
    # with the amp - cab right after it
    "Amp: Clean + Chorus": cab(V_1X12, "DYNAMIC", 0.15, 0.25, 0.0, 0.12),
    "Amp: British Crunch": cab(V_BRIT, "DYNAMIC", 0.2, 0.2, 0.2, 0.1),
    "Amp: Boosted Lead": cab(V_BRIT, "DYNAMIC", 0.3, 0.25, 0.2, 0.12),
    "Amp: Modern Metal": cab(V_MODERN, "DYNAMIC", 0.3, 0.2, 0.0, 0.05),
    "Metal: Modern High-Gain": cab(V_MODERN, "DYNAMIC", 0.3, 0.2, 0.0, 0.05),
    "Metal: Djent": cab(V_MODERN, "DYNAMIC", 0.15, 0.1, 0.0, 0.0),
    "Metal: Swedish Death": cab(V_BRIT, "DYNAMIC", 0.2, 0.15, 0.0, 0.05),
    "Metal: Thrash": cab(V_MODERN, "DYNAMIC", 0.25, 0.2, 0.0, 0.05),
    "Metal: Drop C Riffs": cab(V_MODERN, "DYNAMIC", 0.3, 0.2, 0.0, 0.05),
    "Metal: Shred Lead": cab(V_BRIT, "DYNAMIC", 0.3, 0.25, 0.3, 0.15),
    "Practice: Metal Drums": cab(V_MODERN, "DYNAMIC", 0.3, 0.2, 0.0, 0.05),
}

# Cab for each amp voicing: CLEAN, CRUNCH, LEAD, METAL, PLEXI, BLACKFACE, CHIME, MODERN
_AMP_CAB = (V_1X12, V_BRIT, V_BRIT, V_MODERN, V_BRIT, V_1X12, V_CHIME, V_MODERN)
_DRIVEN = {"od", "dist", "fuzz", "boost", "tboost", "hm2", "mzone"}


def default_cab(board, values):
    """A sensible cabinet for a preset saved without one (e.g. made in v3)."""
    if "amp" in board:
        model = int((values.get("amp") or {}).get("model", 1))
        return cab(_AMP_CAB[min(7, max(0, model))], "DYNAMIC", 0.25, 0.2, 0.0, 0.08)
    if _DRIVEN & set(board):
        return cab(V_BRIT, "DYNAMIC", 0.25, 0.2, 0.0, 0.1, place=0)
    return cab(V_1X12, "DYNAMIC", 0.2, 0.25, 0.0, 0.12, place=0)


def with_cab(preset):
    """The preset with a cab entry (its own, or a matching default)."""
    if preset.get("cab"):
        return preset
    return {**preset, "cab": default_cab(preset.get("board", []), preset.get("values", {}))}


# v4's own presets: complete signal paths - pedals, amp voicing, cabinet and mic.
RIGS = {
    "Blackface Clean": {
        "board": ["comp", "amp", "chorus", "delay", "reverb"],
        "values": {"comp": {"sustain": 0.25, "blend": 0.7},
                   "amp": {"model": 5, "gain": 0.35, "bass": 0.45, "mid": 0.55, "treble": 0.6, "presence": 0.25,
                           "master": 0},
                   "chorus": {"on": 0, "mix": 0.4}, "delay": {"on": 0, "time": 380, "mix": 0.18, "fb": 0.28},
                   "reverb": {"mode": 2, "decay": 1.8, "mix": 0.3}},
        "cab": cab(V_1X12, "DYNAMIC", 0.15, 0.2, 0.0, 0.12)},
    "Chime Jangle": {
        "board": ["comp", "amp", "delay", "reverb"],
        "values": {"comp": {"sustain": 0.3},
                   "amp": {"model": 6, "gain": 0.5, "bass": 0.4, "mid": 0.55, "treble": 0.65, "presence": 0.4},
                   "delay": {"time": 360, "mix": 0.22, "fb": 0.3}, "reverb": {"mode": 1, "mix": 0.25}},
        "cab": cab(V_CHIME, "CONDENSER", 0.1, 0.3, 0.0, 0.15)},
    "Plexi Crunch": {
        "board": ["gate", "amp", "delay", "reverb"],
        "values": {"gate": {"thresh": -58},
                   "amp": {"model": 4, "gain": 0.5, "bass": 0.5, "mid": 0.6, "treble": 0.6, "presence": 0.45},
                   "delay": {"on": 0, "time": 400, "mix": 0.15}, "reverb": {"mode": 0, "mix": 0.18}},
        "cab": cab(V_BRIT, "DYNAMIC", 0.2, 0.2, 0.3, 0.1)},
    "Plexi Cranked Lead": {
        "board": ["gate", "od", "amp", "delay", "reverb"],
        "values": {"gate": {"thresh": -54}, "od": {"drive": 1, "tone": 0.55, "level": 0.9},
                   "amp": {"model": 4, "gain": 0.85, "bass": 0.45, "mid": 0.62, "treble": 0.55, "presence": 0.4},
                   "delay": {"time": 430, "mix": 0.22, "fb": 0.35}, "reverb": {"mix": 0.22, "decay": 2.5}},
        "cab": cab(V_BRIT, "DYNAMIC", 0.3, 0.3, 0.2, 0.12)},
    "Hot-Rodded British": {
        "board": ["gate", "tboost", "amp", "eq", "delay", "reverb"],
        "values": {"gate": {"thresh": -52}, "tboost": {"tight": 220, "gain": 7, "tone": 3},
                   "amp": {"model": 2, "gain": 0.7, "bass": 0.5, "mid": 0.58, "treble": 0.55, "presence": 0.45},
                   "eq": {"b630": 1, "b1k6": 1, "b4k": -1}, "delay": {"on": 0, "time": 420, "mix": 0.18},
                   "reverb": {"mode": 0, "mix": 0.15}},
        "cab": cab(V_BRIT, "DYNAMIC", 0.25, 0.25, 0.0, 0.1)},
    "Modern High-Gain": {
        "board": ["gate", "tboost", "amp", "mgate", "eq", "reverb"],
        "values": {"gate": {"on": 0}, "tboost": {"tight": 380, "gain": 8, "tone": 3},
                   "amp": {"model": 7, "gain": 0.65, "bass": 0.55, "mid": 0.45, "treble": 0.55, "presence": 0.5,
                           "depth": 0.5},
                   "mgate": {"thresh": -55, "release": 30}, "eq": {"b250": -2, "b1k6": 2, "b4k": 1},
                   "reverb": {"mode": 0, "mix": 0.1}},
        "cab": cab(V_MODERN, "DYNAMIC", 0.3, 0.2, 0.0, 0.05)},
    "Djent Rhythm": {
        "board": ["tboost", "amp", "mgate", "eq", "doubler", "reverb"],
        "values": {"tboost": {"tight": 520, "gain": 10, "tone": 3},
                   "amp": {"model": 7, "gain": 0.55, "bass": 0.4, "mid": 0.55, "treble": 0.6, "presence": 0.55,
                           "depth": 0.35},
                   "mgate": {"thresh": -50, "release": 15}, "eq": {"b250": -3, "b1k6": 2, "b4k": 1},
                   "doubler": {"on": 0}, "reverb": {"mode": 0, "mix": 0.08}},
        "cab": cab(V_MODERN, "DYNAMIC", 0.15, 0.1, 0.0, 0.0)},
    "Modern Lead": {
        "board": ["comp", "tboost", "amp", "mgate", "delay", "reverb"],
        "values": {"comp": {"sustain": 0.4}, "tboost": {"tight": 260, "gain": 9},
                   "amp": {"model": 7, "gain": 0.75, "bass": 0.45, "mid": 0.6, "treble": 0.5, "presence": 0.4,
                           "depth": 0.3},
                   "mgate": {"thresh": -58, "release": 90}, "delay": {"time": 440, "mix": 0.25, "fb": 0.38},
                   "reverb": {"mode": 1, "mix": 0.25, "decay": 3.0}},
        "cab": cab(V_DARK, "RIBBON", 0.2, 0.25, 0.35, 0.15)},
    "Warm Blues": {
        "board": ["comp", "od", "amp", "reverb"],
        "values": {"comp": {"sustain": 0.2, "blend": 0.8}, "od": {"drive": 9, "tone": 0.45, "level": 0.7},
                   "amp": {"model": 5, "gain": 0.6, "bass": 0.5, "mid": 0.55, "treble": 0.45, "presence": 0.2},
                   "reverb": {"mode": 2, "decay": 1.6, "mix": 0.22}},
        "cab": cab(V_DARK, "RIBBON", 0.2, 0.25, 0.0, 0.15)},
    "Dark Doom": {
        "board": ["tboost", "amp", "mgate", "reverb"],
        "values": {"tboost": {"tight": 120, "gain": 6, "tone": -2},
                   "amp": {"model": 3, "gain": 0.6, "bass": 0.65, "mid": 0.45, "treble": 0.35, "presence": 0.2,
                           "depth": 0.7},
                   "mgate": {"thresh": -55, "release": 120}, "reverb": {"mode": 1, "decay": 4.5, "mix": 0.3}},
        "cab": cab(V_BRIT, "RIBBON", 0.5, 0.2, 0.0, 0.15)},
    "Bedroom Lo-Fi": {
        "board": ["comp", "amp", "reverb"],
        "values": {"comp": {"sustain": 0.4}, "amp": {"model": 1, "gain": 0.45, "mid": 0.55, "treble": 0.4},
                   "reverb": {"mode": 0, "mix": 0.2}},
        "cab": cab(V_SMALL, "RIBBON", 0.5, 0.6, 0.0, 0.35)},
    "Ambient Clean": {
        "board": ["comp", "amp", "chorus", "delay", "reverb"],
        "values": {"comp": {"sustain": 0.3}, "amp": {"model": 5, "gain": 0.25, "treble": 0.55, "presence": 0.2},
                   "chorus": {"rate": 0.4, "depth": 0.5, "mix": 0.5},
                   "delay": {"time": 560, "fb": 0.5, "mix": 0.4, "mode": 1},
                   "reverb": {"mode": 1, "decay": 7, "mix": 0.5}},
        "cab": cab(V_1X12, "CONDENSER", 0.1, 0.35, 0.0, 0.2)},
}

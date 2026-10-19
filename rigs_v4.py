"""Built-in rigs for PedalBoard v4: complete signal paths - pedals, amp voicing, cabinet and mic.

Each rig is a normal preset plus a 'cab' entry (cab model, mic, position, distance, blend, room, and
'place': 1 = cabinet right after the amp, 0 = at the end of the chain).
"""


def cab(name, mic="DYNAMIC", pos=0.2, dist=0.2, blend=0.0, room=0.0, mode=2, place=1):
    return {"mode": mode, "cab": name, "mic": mic, "pos": pos, "dist": dist, "blend": blend, "room": room,
            "place": place}


RIGS = {
    "Rig: Blackface Clean": {
        "board": ["comp", "amp", "chorus", "delay", "reverb"],
        "values": {"comp": {"sustain": 0.25, "blend": 0.7},
                   "amp": {"model": 5, "gain": 0.35, "bass": 0.45, "mid": 0.55, "treble": 0.6, "presence": 0.25,
                           "master": 0},
                   "chorus": {"on": 0, "mix": 0.4}, "delay": {"on": 0, "time": 380, "mix": 0.18, "fb": 0.28},
                   "reverb": {"mode": 2, "decay": 1.8, "mix": 0.3}},
        "cab": cab("1x12 Open-back Vintage", "DYNAMIC", 0.15, 0.2, 0.0, 0.12)},
    "Rig: Chime Jangle": {
        "board": ["comp", "amp", "delay", "reverb"],
        "values": {"comp": {"sustain": 0.3},
                   "amp": {"model": 6, "gain": 0.5, "bass": 0.4, "mid": 0.55, "treble": 0.65, "presence": 0.4},
                   "delay": {"time": 360, "mix": 0.22, "fb": 0.3}, "reverb": {"mode": 1, "mix": 0.25}},
        "cab": cab("2x12 Open-back Chime", "CONDENSER", 0.1, 0.3, 0.0, 0.15)},
    "Rig: Plexi Crunch": {
        "board": ["gate", "amp", "delay", "reverb"],
        "values": {"gate": {"thresh": -58},
                   "amp": {"model": 4, "gain": 0.5, "bass": 0.5, "mid": 0.6, "treble": 0.6, "presence": 0.45},
                   "delay": {"on": 0, "time": 400, "mix": 0.15}, "reverb": {"mode": 0, "mix": 0.18}},
        "cab": cab("4x12 Closed British", "DYNAMIC", 0.2, 0.2, 0.3, 0.1)},
    "Rig: Plexi Cranked Lead": {
        "board": ["gate", "od", "amp", "delay", "reverb"],
        "values": {"gate": {"thresh": -54}, "od": {"drive": 1, "tone": 0.55, "level": 0.9},
                   "amp": {"model": 4, "gain": 0.85, "bass": 0.45, "mid": 0.62, "treble": 0.55, "presence": 0.4},
                   "delay": {"time": 430, "mix": 0.22, "fb": 0.35}, "reverb": {"mix": 0.22, "decay": 2.5}},
        "cab": cab("4x12 Closed British", "DYNAMIC", 0.3, 0.3, 0.2, 0.12)},
    "Rig: Hot-Rodded British": {
        "board": ["gate", "tboost", "amp", "eq", "delay", "reverb"],
        "values": {"gate": {"thresh": -52}, "tboost": {"tight": 220, "gain": 7, "tone": 3},
                   "amp": {"model": 2, "gain": 0.7, "bass": 0.5, "mid": 0.58, "treble": 0.55, "presence": 0.45},
                   "eq": {"b630": 1, "b1k6": 1, "b4k": -1}, "delay": {"on": 0, "time": 420, "mix": 0.18},
                   "reverb": {"mode": 0, "mix": 0.15}},
        "cab": cab("4x12 Closed British", "DYNAMIC", 0.25, 0.25, 0.0, 0.1)},
    "Rig: Modern High-Gain": {
        "board": ["gate", "tboost", "amp", "mgate", "eq", "reverb"],
        "values": {"gate": {"on": 0}, "tboost": {"tight": 380, "gain": 8, "tone": 3},
                   "amp": {"model": 7, "gain": 0.65, "bass": 0.55, "mid": 0.45, "treble": 0.55, "presence": 0.5,
                           "depth": 0.5},
                   "mgate": {"thresh": -55, "release": 30}, "eq": {"b250": -2, "b1k6": 2, "b4k": 1},
                   "reverb": {"mode": 0, "mix": 0.1}},
        "cab": cab("4x12 Closed Modern", "DYNAMIC", 0.3, 0.2, 0.0, 0.05)},
    "Rig: Djent Rhythm": {
        "board": ["tboost", "amp", "mgate", "eq", "doubler", "reverb"],
        "values": {"tboost": {"tight": 520, "gain": 10, "tone": 3},
                   "amp": {"model": 7, "gain": 0.55, "bass": 0.4, "mid": 0.55, "treble": 0.6, "presence": 0.55,
                           "depth": 0.35},
                   "mgate": {"thresh": -50, "release": 15}, "eq": {"b250": -3, "b1k6": 2, "b4k": 1},
                   "doubler": {"on": 0}, "reverb": {"mode": 0, "mix": 0.08}},
        "cab": cab("4x12 Closed Modern", "DYNAMIC", 0.15, 0.1, 0.0, 0.0)},
    "Rig: Modern Lead": {
        "board": ["comp", "tboost", "amp", "mgate", "delay", "reverb"],
        "values": {"comp": {"sustain": 0.4}, "tboost": {"tight": 260, "gain": 9},
                   "amp": {"model": 7, "gain": 0.75, "bass": 0.45, "mid": 0.6, "treble": 0.5, "presence": 0.4,
                           "depth": 0.3},
                   "mgate": {"thresh": -58, "release": 90}, "delay": {"time": 440, "mix": 0.25, "fb": 0.38},
                   "reverb": {"mode": 1, "mix": 0.25, "decay": 3.0}},
        "cab": cab("2x12 Warm Dark", "RIBBON", 0.2, 0.25, 0.35, 0.15)},
    "Rig: Warm Blues": {
        "board": ["comp", "od", "amp", "reverb"],
        "values": {"comp": {"sustain": 0.2, "blend": 0.8}, "od": {"drive": 9, "tone": 0.45, "level": 0.7},
                   "amp": {"model": 5, "gain": 0.6, "bass": 0.5, "mid": 0.55, "treble": 0.45, "presence": 0.2},
                   "reverb": {"mode": 2, "decay": 1.6, "mix": 0.22}},
        "cab": cab("2x12 Warm Dark", "RIBBON", 0.2, 0.25, 0.0, 0.15)},
    "Rig: Dark Doom": {
        "board": ["tboost", "amp", "mgate", "reverb"],
        "values": {"tboost": {"tight": 120, "gain": 6, "tone": -2},
                   "amp": {"model": 3, "gain": 0.6, "bass": 0.65, "mid": 0.45, "treble": 0.35, "presence": 0.2,
                           "depth": 0.7},
                   "mgate": {"thresh": -55, "release": 120}, "reverb": {"mode": 1, "decay": 4.5, "mix": 0.3}},
        "cab": cab("2x12 Warm Dark", "RIBBON", 0.35, 0.15, 0.2, 0.2)},
    "Rig: Bedroom Lo-Fi": {
        "board": ["comp", "amp", "reverb"],
        "values": {"comp": {"sustain": 0.4}, "amp": {"model": 1, "gain": 0.45, "mid": 0.55, "treble": 0.4},
                   "reverb": {"mode": 0, "mix": 0.2}},
        "cab": cab("1x10 Small Combo", "RIBBON", 0.5, 0.6, 0.0, 0.35)},
    "Rig: Ambient Clean": {
        "board": ["comp", "amp", "chorus", "delay", "reverb"],
        "values": {"comp": {"sustain": 0.3}, "amp": {"model": 5, "gain": 0.25, "treble": 0.55, "presence": 0.2},
                   "chorus": {"rate": 0.4, "depth": 0.5, "mix": 0.5},
                   "delay": {"time": 560, "fb": 0.5, "mix": 0.4, "mode": 1},
                   "reverb": {"mode": 1, "decay": 7, "mix": 0.5}},
        "cab": cab("1x12 Open-back Vintage", "CONDENSER", 0.1, 0.35, 0.0, 0.2)},
}

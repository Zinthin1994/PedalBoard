"""Reference text for the Learn tab: what each block is, where it belongs and what its controls really do.

Written in proper terminology on purpose - PedalBoard v4 is meant for exploring and learning.
"""

GLOSSARY = [
    ("Gain staging", "Managing level through a chain so every stage runs where you want it: clean stages "
     "with headroom, distortion stages deliberately saturated. A pedal's output level sets how hard the next "
     "stage is driven."),
    ("Headroom", "How far a signal can rise before it clips. Digitally 0 dBFS is the hard ceiling; a healthy "
     "guitar DI peaks around -12 dBFS, leaving ~12 dB of headroom."),
    ("Clipping / saturation", "Flattening the waveform peaks. Soft clipping (tube-like, tanh) rounds them off and "
     "mostly adds low-order harmonics; hard clipping (diodes / digital) squares them and adds more odd, "
     "harsher harmonics."),
    ("Even vs. odd harmonics", "Symmetric clipping makes odd harmonics (3rd, 5th: hollow, aggressive). "
     "Asymmetric clipping (a biased tube stage) adds even harmonics (2nd, 4th: warm, fuller, 'octave-ish')."),
    ("Tone stack", "The passive bass/mid/treble network in an amp. It only cuts (it is a set of filters in a "
     "divider), so its settings interact: turning the mids down makes the bass and treble seem louder."),
    ("Presence", "A high-frequency control in the power amp's negative-feedback loop. Less feedback at the top "
     "end = more bite and air, and it reacts to how hard the amp is driven."),
    ("Sag", "The supply voltage dipping under heavy load, which compresses and softens the power amp: attack "
     "feels 'springy', notes bloom. Tube-rectified amps sag more than solid-state ones."),
    ("Depth / resonance", "Boosts the power amp and speaker's low-frequency resonance, giving chugs their "
     "'thump' around 80-120 Hz."),
    ("Cabinet / IR", "The speaker + enclosure + microphone. It removes the harsh <80 Hz and >5 kHz content, "
     "adds the speaker's resonances and the mic's colour. An IR (impulse response) captures all that as a "
     "filter you convolve with the signal. In a real signal chain you NEVER hear a preamp without this."),
    ("Proximity effect", "A directional mic placed close to the source boosts lows. Moving the mic away "
     "thins the sound; a ribbon shows it the most."),
    ("Cap vs. edge", "Mic over the centre of the speaker cone (the dust cap) sounds bright and focused; toward "
     "the edge it gets darker and warmer."),
    ("Comb filtering", "Two copies of a signal with a small delay (two mics, or a reflection) cancel at "
     "regular frequency intervals, giving the hollow, phasey tone seen in the Mic Blend."),
    ("Linear vs. non-linear order", "Linear, time-invariant blocks (EQ, filters, delay, reverb, a cabinet IR) can be "
     "reordered without changing the sound. Non-linear ones (distortion, compression, gates) and modulated ones "
     "(chorus, phaser, tremolo) cannot: they react to what is in front of them. That is why pedal ORDER matters "
     "for gain and modulation but not between a delay and a reverb."),
    ("Cabinet placement", "'After amp' puts the speaker simulation right behind the amp block, so compressors, "
     "modulation and other non-linear effects behind it work on the speaker-filtered sound (like adding pedals "
     "to a recorded, mic'd cab). 'At end' filters everything last, so those effects see the raw, fizzier amp "
     "output. Delay / reverb are linear and sound the same either way."),
    ("Noise gate", "Mutes the signal when it falls below a threshold. Put it BEFORE the gain stages (so it "
     "sees the clean envelope) or use the Metal Gate after the amp, keyed from the clean input."),
    ("Dynamics: attack / release", "How quickly a compressor or gate reacts (attack) and lets go (release). "
     "Short attack squashes the pick transient; long attack lets it through for 'snap'."),
    ("Q (resonance)", "The sharpness of a filter's peak. High Q = narrow and ringing (wah, envelope filter); "
     "low Q = broad and gentle."),
    ("Wet / dry", "The balance between the processed (wet) and untouched (dry) signal. Parallel mixes keep the "
     "pick attack of the dry signal."),
    ("Latency", "The delay between playing and hearing. Under ~10 ms feels instant; ~20 ms is noticeable; "
     "above ~30 ms the guitar feels detached. It comes from the buffer size plus the driver."),
    ("Sample rate / buffer", "48 kHz means 48,000 measurements per second. The buffer is how many samples are "
     "processed per block; smaller buffers = lower latency but more risk of dropouts."),
]

# per pedal: role (what it is / does), place (where in the chain), notes (technique)
PEDAL_HELP = {
    "gate": dict(
        role="Downward expander / gate with an envelope follower and hold. Reduces the signal to silence when the "
             "input falls below THRESH, then re-opens as soon as you play.",
        place="First in the chain, ahead of the gain stages, so it reads the clean envelope.",
        notes="Set THRESH just above the hum/hiss floor when you're not playing. A fast RELEASE is tight but can "
              "chop note tails; a slow release is gentler for cleaner tones."),
    "drop": dict(
        role="Real-time pitch shifter that transposes the whole input down by a fixed interval (Eb ... A) so you "
             "can play drop tunings without retuning.",
        place="First, before everything - pitch tracking prefers a clean, unprocessed signal.",
        notes="TIGHT grain is more accurate on palm mutes; SMOOTH sounds more natural on sustained chords."),
    "comp": dict(
        role="Feed-forward compressor: reduces the gap between loud and quiet by attenuating peaks, then makes "
             "up the gain. SUSTAIN sets the amount of compression.",
        place="Before gain stages for cleans (evens out picking); lightly after the amp for leads. Rarely after "
              "heavy distortion.",
        notes="Slow ATTACK preserves the pick transient; BLEND mixes in the uncompressed signal "
              "(parallel compression)."),
    "boost": dict(
        role="Clean gain stage with a bass/treble shelving EQ. Used to push the next stage harder, or to "
             "raise level for solos.",
        place="In front of an amp or drive pedal as a 'pusher', or last for a solo boost.",
        notes="Adding gain before a distortion increases saturation; adding it after only raises volume."),
    "tboost": dict(
        role="Boost with a high-pass filter (TIGHT) at its front - a Tube-Screamer-style 'tightening' trick. "
             "Cutting bass before the gain stages stops the preamp saturating on low-end mud.",
        place="Immediately before the amp's preamp / distortion.",
        notes="Higher TIGHT frequencies give a tighter, chuggier low end (400-600 Hz for fast palm mutes in drop "
              "tunings is common). TONE adds presence."),
    "cut": dict(
        role="Steep high-pass and low-pass filters (12 or 24 dB/oct). The surgical tool for flubby lows and "
             "fizzy highs.",
        place="After the amp/cab to clean up the final sound; before a drive to tighten the input.",
        notes="Guitar fundamentals start at ~82 Hz (low E) - going much above 100 Hz thins the guitar. Fizz "
              "typically lives above 6 kHz."),
    "octave": dict(
        role="Analog-style octaver: a divider generates square-ish sub-octaves; an up-octave comes from "
             "full-wave rectification.",
        place="First, on a single clean note - it tracks monophonically.",
        notes="Chords confuse an octaver. Play single notes and keep the signal clean."),
    "wah": dict(
        role="Resonant band-pass filter whose centre frequency sweeps between HEEL and TOE. Q (RESO) sets the "
             "peak's sharpness.",
        place="Before distortion (classic: wah -> fuzz), or after for a different, more vocal sound.",
        notes="Manual mode = treadle, Auto = envelope-follower sweeps with your picking, LFO = rhythmic sweep."),
    "envf": dict(
        role="Envelope filter (auto-wah): the filter cutoff follows the level of your playing; SENS sets how "
             "far it opens.",
        place="Before distortion; compress first for consistent triggering.",
        notes="UP/DOWN sets sweep direction; BP gives the classic 'quack', LP is smoother and funkier."),
    "swell": dict(
        role="Auto volume swell: attenuates the attack and fades each note in, like a violin bow.",
        place="Before delay/reverb for pad-like textures.",
        notes="Long ATTACK + lots of reverb = ambient pads."),
    "fuzz": dict(
        role="Vintage-style fuzz: huge gain into hard asymmetric clipping with a bias control. Spiky, "
             "gated and harmonically dense.",
        place="First or directly after a wah; fuzz pedals dislike buffered or processed signals ahead of them.",
        notes="BIAS starves the circuit - high settings get sputtery and gated."),
    "od": dict(
        role="Mid-hump soft-clipping overdrive (Tube Screamer type). Rolls off lows before clipping, boosts "
             "around 700 Hz, then soft-clips.",
        place="In front of the amp as a boost (low DRIVE, high LEVEL), or alone for a bluesy crunch.",
        notes="The mid hump and the pre-clipping bass cut are why it 'tightens' high-gain amps."),
    "dist": dict(
        role="Hard-clipping distortion with a passive tone control and mid bell. Symmetric diode-style clipping "
             "-> odd-harmonic, aggressive.",
        place="Before the amp for stacking, or on its own into a clean amp.",
        notes="MID is the signature control: scooped = modern/metal, pushed = vintage rock / cut through a mix."),
    "hm2": dict(
        role="Imitates the Boss HM-2: a heavily mid-scooped, extremely gainy circuit that defined the "
             "Swedish death metal 'buzzsaw'.",
        place="In front of a medium-gain amp channel.",
        notes="Running it with LOW and HIGH near max leaves a deep scoop around 800 Hz - the amp fills the "
              "middle in."),
    "mzone": dict(
        role="High-gain distortion with a 3-band EQ whose middle band has a sweepable frequency (like the "
             "Metal Zone). Extremely flexible and easy to over-scoop.",
        place="Before the amp; keep the amp's own gain moderate.",
        notes="Mid cut at 600-800 Hz + MID FREQ sweep shapes where the 'hole' in the sound sits."),
    "eq": dict(
        role="Six-band graphic EQ (100 Hz - 8 kHz) built from peaking filters.",
        place="After the amp to shape the tone, or before a drive to change which frequencies clip.",
        notes="Boosting before distortion changes the distortion; boosting after only changes the EQ."),
    "amp": dict(
        role="Tube amp model: input stage -> 1-4 cascaded asymmetric triode stages (anti-aliased clipping with "
             "coupling-capacitor filtering and Miller roll-off) -> passive-style tone stack -> sagging power "
             "amp -> PRESENCE and DEPTH. Eight voicings; the voicing sets gain structure, tone-stack "
             "frequencies, mid contour and sag.",
        place="After gain/boost pedals, before modulation and time effects. Always use it with a CABINET.",
        notes="CLEAN/BLACKFACE: headroom and sparkle. CHIME: class-A top-boost jangle. PLEXI: vintage "
              "British crunch. CRUNCH/LEAD: general purpose. METAL/MODERN: tight multi-stage high gain - "
              "turn GAIN down until chords are articulate, then raise the MID."),
    "mgate": dict(
        role="Gate with a sidechain: it opens based on your CLEAN input, but mutes the processed output. So "
             "amp hiss between notes is silenced without chopping decaying notes.",
        place="After the amp.",
        notes="Fast RELEASE (15-40 ms) for djent staccato; slower for lead playing."),
    "pitch": dict(
        role="Pitch shifter / harmonizer (granular). Mixes a transposed copy with the dry sound.",
        place="Before gain for accuracy, or after for dense, strange textures.",
        notes="+12 for octave-up leads, +/-7 or +/-5 for power-chord harmony."),
    "ring": dict(
        role="Ring modulator: multiplies the input by a sine wave, producing sum and difference frequencies "
             "(inharmonic, metallic).",
        place="Anywhere; usually early for predictable results.",
        notes="Low FREQ = tremolo-like; mid FREQ = bell tones; high = radio-like noise."),
    "crush": dict(
        role="Bit crusher: quantizes amplitude to fewer bits (noise, distortion) and reduces the sample "
             "rate (aliasing).",
        place="Late in the chain or parallel for lo-fi.",
        notes="BITS < 8 is gritty; DOWNSAMPLE adds aliasing artefacts."),
    "phaser": dict(
        role="Six-stage all-pass phase shifter: sweeps notches through the spectrum, swirling movement.",
        place="After the amp (or before drive for the 70s sound).",
        notes="FEEDBACK deepens the notches. Slow RATE + moderate DEPTH is classic."),
    "univibe": dict(
        role="Uni-Vibe: photocell-modulated phase stages with an uneven pattern, throbbing between chorus and "
             "phaser.",
        place="Before drive for Hendrix-style, or after for modern tones.",
        notes="VIBRATO mode is pure pitch wobble (wet only)."),
    "trem": dict(
        role="Amplitude modulation: the volume is modulated by an LFO. SHAPE morphs sine -> square.",
        place="After the amp.",
        notes="Match RATE to the tempo for rhythmic tremolo."),
    "vibrato": dict(
        role="Pitch modulation (a modulated short delay with no dry signal). Pure wobble.",
        place="After the amp.",
        notes="Small DEPTH sounds like a slightly drunk tape machine."),
    "chorus": dict(
        role="Modulated short delay (10-30 ms) mixed with dry: a slow detune that thickens and widens. "
             "Stereo.",
        place="After the amp, before delay/reverb.",
        notes="Higher MIX plus slower RATE is lush; fast RATE with deep DEPTH approaches vibrato."),
    "flanger": dict(
        role="Very short modulated delay (0.3-5 ms) with feedback: moving comb filter, 'jet plane'.",
        place="After the amp.",
        notes="Negative FEEDBACK gives a metallic, hollow character."),
    "rotary": dict(
        role="Leslie speaker simulation: a rotating horn and drum creating Doppler pitch shift and tremolo, "
             "with a tube-like drive.",
        place="After overdrive; before reverb.",
        notes="SLOW to FAST ramps like the real motor."),
    "pan": dict(
        role="Auto-panner: sweeps the signal between left and right.",
        place="Late.",
        notes="Best on headphones or a stereo pair."),
    "doubler": dict(
        role="Haas-effect stereo doubler: two slightly different delayed copies panned wide, imitating "
             "'double-tracked' rhythm guitars.",
        place="Late; after the amp and cab.",
        notes="TIME 15-25 ms with moderate VARIATION is the 'two guitars' sound. Collapses to mono-ish if "
              "summed - check it on speakers."),
    "delay": dict(
        role="Feedback delay line: DIGITAL (clean), ANALOG (darkened repeats), PING-PONG (alternates "
             "L/R). TONE darkens each repeat.",
        place="After the amp and gain stages, before reverb.",
        notes="Dotted-eighth timing (TAP TEMPO) is the classic rhythmic delay. Low FEEDBACK = slapback "
              "(~100 ms), high = ambience."),
    "reverb": dict(
        role="Algorithmic reverb with pre-delay and ROOM/HALL/PLATE characters.",
        place="Last in the chain.",
        notes="PRE-DELAY keeps the dry attack clear of the tail; high-gain tones usually want a subtle MIX."),
    "looper": dict(
        role="60-second looper with overdub.",
        place="Last, to record everything before it.",
        notes="REC -> PLAY -> DUB on one switch; STOP and CLEAR have their own buttons."),
    "drums": dict(
        role="Metronome and drum patterns for practice.",
        place="Mixes after the chain.",
        notes="TAP TEMPO to sync with a riff."),
}

PARAM_HELP = {
    ("amp", "gain"): "Preamp drive. Sets how hard the cascaded triode stages are pushed into clipping.",
    ("amp", "bass"): "Low-shelf of the tone stack (corner ~100-160 Hz depending on voicing).",
    ("amp", "mid"): "Peaking band of the tone stack. The most influential tone control with distortion.",
    ("amp", "treble"): "High-shelf of the tone stack (corner ~2.8-3.8 kHz).",
    ("amp", "presence"): "Post-power-amp high-frequency lift (negative-feedback high cut reduction).",
    ("amp", "master"): "Output level after the power-amp model; also scales how hard the sag stage works.",
    ("amp", "depth"): "Adds low-frequency resonance (~90 Hz) - the thump of a loaded speaker.",
    ("od", "drive"): "Gain into the soft clipper, in dB.",
    ("dist", "mid"): "Peaking filter at 750 Hz after clipping. Negative = scooped.",
    ("tboost", "tight"): "High-pass corner placed before the boost / gain stages.",
    ("cut", "hpf"): "High-pass corner frequency.",
    ("cut", "lpf"): "Low-pass corner frequency.",
    ("gate", "thresh"): "Level below which the gate closes (dBFS).",
    ("comp", "sustain"): "Amount of compression (ratio and threshold together).",
}


def pedal_text(key):
    """Formatted multi-line help for one block (used by the Learn tab)."""
    h = PEDAL_HELP.get(key)
    if not h:
        return ""
    return (f"WHAT IT DOES\n{h['role']}\n\nWHERE IT GOES\n{h['place']}\n\nTECHNIQUE\n{h['notes']}\n")

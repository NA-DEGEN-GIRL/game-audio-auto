# Designing usable game sounds

## Effects and ambience

Describe the audible cause: action, material, force, motion, perspective, acoustic space and decay. “A polished game sound” gives little control. A single event should not accidentally become a sequence, soundtrack or voice line. State only useful exclusions. Keep a related set's material, weight, distance and room consistent while allowing natural differences in individual takes.

| Use | Decisions that affect the result | Useful review |
| --- | --- | --- |
| Footsteps / Foley | Surface, footwear/body weight, gait, recording distance; separate contacts if game events trigger each one | Alternating contacts, sequence at actual cadence, no identical repeated accent |
| Impact / weapon | Whoosh/attack, body/material response and tail where needed; choose one combined cue or independently triggered layers | Contact alignment, readability in combat, overlapping tails and voice count |
| UI | Information hierarchy and shared tonal identity; size/duration appropriate to frequency of use | Repeated navigation, confirm/error distinction, fatigue and excessive sharpness |
| Creature / nonverbal bark | Species/size/effort, recognizable vocal identity, no unintended words | Identity across variations, natural onset/breath, no harsh artifacts |
| Ambience | Stable environmental bed plus optional rare events; spatial coverage and time/weather | Several complete cycles, obvious repeated landmarks, seam, stereo image and phase |

For variation sets, independent performances/texture variation usually matter more than large pitch shifts of one take. Use enough variations for the requested cadence and scope. Choose plausible gain/pitch ranges after listening; do not randomize character identity, musical tuning or critical telegraph timing. In-engine anti-repeat, cooldown and concurrency remain metadata until implemented and tested.

A looping environment can use a continuous bed with sparse one-shots on separate timers. Do not bake a conspicuous birdcall or metal clang every few seconds into a short loop unless that repetition is intentional. For long ambience, generate suitable segments and author the continuity locally; do not pretend a 30-second endpoint accepts a longer request.

Local layers can repair a missing transient, resonance or spatial tail without replacing the entire asset. Preserve every layer's source and the mix operation. Check the mix at game playback gain, not just isolated and loud. Do not use universal loudness targets for every effect; attack peak, perceived weight and interaction with other sounds matter.

## Dialogue and barks

Use the requested language and exact intended words. For Korean, check pronunciation of names, spacing-sensitive phrases, numbers, particles and natural sentence endings. Describe acting in the backend's supported controls; do not put explanatory prose into the spoken script accidentally.

Select an ElevenLabs voice from an observed account listing or a user-supplied existing ID. Keep character voice ID, model and relevant settings in the brief. Use v3 for expressive performance, then choose another supported model if the observed consistency/latency need warrants it. Do not assume every voice sounds equally convincing in every language.

For local Qwen:

- `custom` uses a known speaker (Korean Sohee is a starting candidate) and optional acting instruction.
- `design` creates a described voice. For a recurring character, preserve a selected reference rather than independently redesigning every line.
- `clone` uses supplied/authorized reference audio and preferably its exact transcript with the Base model. Preserve/hash the reference. The core clone adapter does not accept acting instructions.

Check consonants, breaths, pace, emotion and character continuity through actual listening. ASR can flag missing/wrong words; it cannot establish natural acting. Do not compress speech into an arbitrary duration without checking intelligibility. For animation timing, align the selected audio afterwards or use a supported alignment tool when needed; no lip-sync or phoneme timing is created by the basic TTS adapter.

## Local finishing

Keep the raw provider file and edit a new revision. Trim unwanted padding without cutting the intended attack or tail. Use short fades where they fix a click; do not soften every transient automatically. Apply EQ, noise repair, gain, limiter or reverb only to address the audible problem, and retain the authoring settings.

The core loop crossfade is a linear boundary blend with a rotated start. It can smooth stationary textures but may produce a perceptible dip, phase change or rhythmic mismatch. Inspect the resulting loop over repeated playback. Music often needs bar/phrase-aware editing rather than this generic crossfade.

For 3D point sources, mono may suit engine spatialization. Stereo can be right for beds, music and designed wide cues. Choose from the target's actual playback model; do not collapse supplied stereo solely for consistency.

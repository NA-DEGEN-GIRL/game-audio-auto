# Character dialogue with Gemini

Default for acted characters/NPCs, policy updated **2026-10-02**. Use Gemini 3.8 Flash TTS for expressive character dialogue and barks, or when explicitly requested. Set `dialogue_role: "character"` for auto routing. Preserve an accepted character’s provider/model/voice explicitly; general narration remains Eleven v3. Respect `only_local`. A missing Gemini key blocks this route for setup instead of silently switching providers. Flash-Lite is an explicit lower-cost alternative; do not silently switch an established voice's synthesis model. Gemini dialogue defaults to density finishing (밀도 강화), with the native performance retained separately.

## Setup

1. Create a project/key in [Google AI Studio](https://aistudio.google.com/api-keys).
2. On the execution host, save the key alone in `.secrets/gemini_api_key` under the shared runtime root. Alternatively use `GEMINI_API_KEY` / `GOOGLE_API_KEY`, or point `GEMINI_API_KEY_FILE` to an existing private file. This runtime checks `GEMINI_API_KEY`, then `GOOGLE_API_KEY`, then the file (the Google SDK's precedence differs). Do not put the key in requests, source, chat, or the browser. `doctor` reports presence, not successful authentication.
3. Use `gemini-voices` for a read-only access check. A successful list is not proof of generation quota; inspect actual rejection before changing account settings or retrying.

Core REST support uses the existing runtime dependencies; no GPU, local model download, ElevenLabs subscription, or additional Google SDK is needed. A Gemini consumer subscription is not this API's credential.

These commands require the updated runtime on the selected execution host. Synchronizing only the skill text to another host does not upgrade its Python runtime; see [execution setup](execution-setup.md).

Ordinary Flash TTS has a free tier. Link Cloud Billing to the key's project when paid capacity is needed. For unpublished scripts, note that free-service inputs/outputs can be used for product improvement, while the paid-service terms differ. Do not require payment without an actual access/quota need. The separate Voice Design creation price is not established by the speech output estimate below.

At the checked date, Flash TTS standard audio output is approximately **$0.00225 per 10 seconds**, plus text input, through 2026-12-31; published 2027 rates double. This is a planning figure, not a cost cap. Runtime `max_credits` is an ElevenLabs unit and cannot cap Gemini; a Gemini request with that field must block rather than pretend to enforce it.

Sources: [API key setup](https://ai.google.dev/gemini-api/docs/api-key), [billing](https://ai.google.dev/gemini-api/docs/billing), [pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.8-flash-tts), [service terms](https://ai.google.dev/gemini-api/terms).

## Design once, direct each line

Keep two separate layers:

| Layer | Store/use |
| --- | --- |
| Character identity | Stable character name, voice design, observed ID/model/language, preview WAV and hash, observed expiry |
| Performance | Exact dialogue text, short situation-specific acting instruction, optional vocal tags, take/job IDs and rendered WAVs |

For a fictional persona, prefer **Voice Design**. Design permanent qualities (age range, timbre, regional accent, baseline cadence) in one or two sentences; do not imitate a named real performer. A design request is a separate remote creation, not a flag that should recreate a voice for every line.

```json
{
  "name": "gregoriya-v1",
  "display_name": "광란의 그레고리야",
  "model": "gemini-3.8-flash-tts",
  "language_code": "ko-KR",
  "gender": "male",
  "prompt": "An adult male dark-fantasy stage jester with a resonant mid-low voice, a light dry rasp, precise Korean diction and measured theatrical cadence. His ordinary delivery is composed, intimate and unsettling."
}
```

```sh
uv run --no-sync python -m game_audio.cli voice-plan .work/voice-design.json
uv run --no-sync python -m game_audio.cli voice-create .work/voice-design.json
uv run --no-sync python -m game_audio.cli voice-show gregoriya-v1
```

Use the returned actual `voice_id` for subsequent dialogue. A prebuilt voice selected from `gemini-voices` is also usable when custom design is unnecessary. Keep accepted and exploratory voices distinct; change the local version name when deliberately redesigning, retaining earlier records.

```json
{
  "name": "gregoriya-warning",
  "kind": "dialogue",
  "dialogue_role": "character",
  "provider": "gemini",
  "model": "gemini-3.8-flash-tts",
  "voice_id": "REPLACE_WITH_OBSERVED_VOICE_ID",
  "language": "ko",
  "prompt": "문을 닫아. <short pause> 아직 우리 공연은 끝나지 않았어.",
  "instruction": "quiet, amused and menacing",
  "dialogue_processing": "auto",
  "purpose": "boss encounter warning",
  "acceptance": ["clear Korean words", "recognizable character", "quiet menace without a different speaker"],
  "playback": {"intent": "once", "spatial": "3d"},
  "export": {"sample_rate": 48000, "channels": "mono", "subtype": "PCM_24"}
}
```

Run `plan`, `generate --async`, then inspect the returned job. Omit duration: delivery controls length. The runtime sends `prompt` as the literal transcript and `instruction` as `speech_metadata.style`, not as spoken direction. Keep momentary vocal events in English angle-bracket tags (`<laugh>`, `<gasp>`, `<short pause>`). Avoid changing age/gender/accent in each acting instruction. Do not repeat a long character biography or "keep identical timbre" instruction on every line.

Default to a natural conversational pace; request slow, deliberate speech only when the scene needs it. For pace comparisons, preserve voice, exact transcript and finishing, then vary only the short instruction. For direction-language comparisons, translate equivalent instructions while keeping spoken language separate. Korean and English directions are audition options, not an established quality ranking; one take per condition still contains generation variability. Use a short instruction such as “자연스러운 대화 속도로, 쉼은 짧게 하고 자음은 또렷하게 발음한다.” Keep source audio at its generated speed.

For a furious one-word outburst, direct onset, vocal intensity and release in the performance. Keep dry dialogue and later reverb/pitch/layer effects separate so room effects cannot mask weak acting or be mistaken for model ability.

For multiple custom characters, synthesize each turn individually and mix locally. Single-request multi-speaker support is limited to two prebuilt voices. Archive the native 24 kHz mono PCM16 WAV; a 48 kHz PCM24 delivery is a conversion, not additional source detail. Seeds are not sent by this adapter.

Sources: [Voice Design](https://ai.google.dev/gemini-api/docs/voice-design), [TTS and acting controls](https://ai.google.dev/gemini-api/docs/speech-generation).

## Preserve identity and handle expiry honestly

The private `.assets/voices/` archive retains the design request, provider response, ID, preview, hashes and actual `expire_time`. Each name is an immutable design version. Keep finished lines and accepted neutral anchors too. The planner checks local profiles by voice ID, rejects expiry and binds the verified profile hash to the job. External IDs need a `gemini-voice ID` lookup for their current metadata. Retain expired records and select a reviewed successor rather than silently replacing the voice.

Google currently documents **one-year TTL** for stored custom voices and **200 stored voices per project**. Prebuilt voices do not expire. No public renewal endpoint or guaranteed reconstruction from the same design prompt is documented. Use the observed timestamp, not a guessed anniversary.

Saved generated WAVs remain useful production assets and comparison anchors. **Do not promise to restore the same voice from those WAVs.** Current Voice Replication requires reference and consent recordings from the same real adult. Synthesized character audio and synthesized consent are not a supported substitute. At expiry, reassess available migration/renewal features; a newly designed voice requires new comparison and approval of identity. This runtime implements prompted voice design, not replication or automatic renewal.

Sources: [Voices API](https://ai.google.dev/api/voices), [Voice Design lifetime](https://ai.google.dev/gemini-api/docs/voice-design#manage-your-voices), [replication requirements](https://ai.google.dev/gemini-api/docs/voice-replication).

## Receipts and useful tests

Both voice creation and synthesis save a receipt before their single POST. Reuse completed files and saved responses. An uncertain submission must be reconciled; do not switch provider, rename the voice, or delete the receipt to force a retry. Read-only inspection is safe, but the same prompt alone cannot prove that a remote voice is the original result.

For an initial audition, design one character and generate three deliveries of the same short sentence (neutral, hushed threat, anger), plus one laugh-led line. Compare identity stability, Korean pronunciation, direction leakage, the requested emotion, and clean starts/tails. Expand only based on the user's feedback. File checks and mock tests do not establish listening quality; keep listening unreviewed until actually heard. The helper `scripts/gemini_character_demo.py` prepares and resumes this bounded test without duplicate jobs.

When speech sounds muffled or overly textured, inspect the native provider WAV before changing the player or applying enhancement. Check the submitted voice ID/style, sample rate, clipping and delivery hashes. First try the same short text with an empty style to separate a bad take or acting direction from the voice design. If the design is deliberately gravelly, breathy or dark, compare a separately versioned clear voice with simpler permanent traits; retain the original identity and label the redesign. Add emotions through short directions after the neutral baseline. Resampling 24 kHz audio to 48 kHz cannot restore missing detail. Automated transcription can check words, but cannot establish pleasant timbre or substitute for the user's listening review.

## Default finish and comparisons

For Gemini dialogue, `dialogue_processing: "auto"` selects **density**: gentle EQ and adaptive 2:1 RMS compression, followed only by negative gain if needed for -1.2 dBTP headroom. The generation job keeps the original `revision` and exposes finished child revisions in `delivery_revisions`, with processing job IDs in `finishing_jobs`. Deliver the finished child and retain the native provider WAV. Other providers' `auto` behavior stays unprocessed. This preference was selected for dialogue consistency, not as a claim that every Gemini take needs the same repair.

Use `dialogue_processing: "none"` when the user asks for an unprocessed take or a controlled source comparison. `density` explicitly requests this finish, including for another dialogue provider when wanted. For an existing performance, use [finish-dialogue](runtime.md#dialogue-density-finishing) rather than regenerating; its low-shelf/presence gains can be adjusted per voice. When comparing to the untreated performance, obtain it from the preserved generation revision.

For a requested alternative, compare the same performance with gentle per-line EQ or small-level/detail enhancement at verified equal loudness. Detail enhancement is a separate local authoring recipe, not a supported `dialogue_processing` enum or `finish-dialogue` preset. Save filter settings, original voice/job/manifest hashes and a new child/import revision with explicit processing provenance. Begin each alternative from the original performance rather than stacking finished presets. Preserve pitch, timing, breaths and dynamic intent; do not apply strong high-frequency boosts or denoising automatically. A low-energy gap is not proof of noise-only audio, and EQ cannot reconstruct unclear phonemes. Keep listening quality unreviewed until actually heard; revert or adjust density when the result harms the performance.

The matched preview level used in an audition is not the production loudness target. Measure the rendered comparison files rather than assuming the normalization filter reached its target; see [review integration](review-integration.md).

## Comparison helper

When the user requests an ElevenLabs comparison too, choose an observed suitable ElevenLabs voice ID and pass `--eleven-voice-id ID` to `prepare`. New batches create four Gemini and four Eleven v3 takes with equivalent words and provider-specific acting syntax. They are different voices, not a controlled same-speaker benchmark. Previously prepared v4 batches retain their saved model. `prepare`/`collect` do not generate; `generate` uses paid APIs when applicable. Repeated `generate` reuses saved jobs and stops at ambiguous submission state.

```sh
uv run --no-sync python scripts/gemini_character_demo.py prepare --directory .work/character-demo --eleven-voice-id OBSERVED_ID
uv run --no-sync python scripts/gemini_character_demo.py generate --directory .work/character-demo
uv run --no-sync python scripts/gemini_character_demo.py collect --directory .work/character-demo --catalog .assets/deliveries/themepark-comparison-20260915/catalog.json
```

After collection, the existing optional loopback player shows these under `/?category=dialogue`, with original and volume-matched previews. Preserve the native audio and note the source-format difference: this adapter receives native WAV from Gemini, while the existing ElevenLabs route receives MP3 before local WAV conversion.

If the provider audio was downloaded but integer export would clip after resampling, the demo collector can finish it locally: import the preserved raw as FLOAT, measure, then apply only enough negative gain for -1 dBFS sample headroom in a new PCM24 edit. It records both local jobs and the original failed export; it does not submit another generation or repair distortion already present in the source.

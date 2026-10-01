# ElevenLabs access and plugin cooperation

For the optional Gemini character-dialogue provider, use [character-voices.md](character-voices.md). It has separate credentials and Voices/TTS APIs; ElevenLabs plugins, voice IDs and credits do not apply to it.

## Access check

Use the current tool inventory or tool search to discover actual ElevenLabs capabilities. Check that the tool supports this kind of audio, returns a playable/local output or downloadable asset, and exposes enough result identity to recover it. A connection UI or installed skill is not an authenticated generation test. Prefer a read-only account/voice query when available; do not spend credits just to test authentication.

The ElevenLabs plugin installed when this skill was authored contains provider skills for `sound-effects`, `text-to-speech`, `music` and `setup-api-key`. Their generation examples use the official SDK/API and `ELEVENLABS_API_KEY`. Installation of these instructions does not remove the key requirement. If a future connector supplies working managed authentication, use it without requesting a redundant local key. Do not extract connector secrets or modify the plugin cache.

Use the installed relevant skill for prompting and supported SDK operations; reconcile stale model/parameter examples against current official API documentation. Keep this game skill's model selection, routing, requested take count, provenance and review workflow around the provider operation. The runtime's guarded API adapter supports standard SFX/TTS/music and is the direct route when the plugin lacks the selected model; advanced plugin operations can be imported as existing files.

## Speech models v4

Selection policy **2026-10-02**: use **`eleven_v3` by default for game dialogue, barks and narration**. V4 support was verified on 2026-10-01 after its 2026-09-28 launch, but availability and newer release do not establish better character fit. Gemini stays explicit-only with its separate density-finishing default.

| Situation | Selection |
| --- | --- |
| New game dialogue with no model preference | Eleven v3 |
| Existing accepted character model/voice | Preserve it, including an accepted v4 character |
| Explicit v4 request | Eleven v4 |
| Realistic NPC, narration or recorded-voice reproduction | V4 may be proposed as an audition; keep v3 until requested or accepted |
| Explicit low-latency v4 request | Eleven v4 Turbo |
| Explicit Gemini request | Gemini 3.8 Flash TTS, density finishing by default |

**Voice Design limitation, checked 2026-10-02:** the official [v4 FAQ](https://elevenlabs.io/docs/overview/capabilities/text-to-speech/eleven-v4) warns that ElevenLabs Voice Design voices can have weaker performance and sound quality on v4 than on earlier models; the [Voice Design help page](https://elevenlabs.io/docs/help-center/product/voices/voice-design/what-is-voice-design) also notes reduced expressiveness. This supports the v3 starting choice for a designed character, but is not a guarantee of universal v3 superiority. Preserve an accepted model on each character. Inspect observed voice metadata/design records rather than infer the source type from a fictional name or an acting prompt. `premade` library voices and Gemini Voice Design are not evidence that this ElevenLabs-specific limitation applies. The CLI's default also selects v3; explicit saved models are never rewritten by policy changes.

The existing `POST /v1/text-to-speech/{voice_id}` route supports these model IDs; the authenticated `GET /v1/models` lists v4 and v4 Turbo with `can_do_text_to_speech: true`. Keep `model_id` explicit. The adapter sends exact text/audio tags, the selected existing voice, `language_code` and a best-effort seed. Repeated seeds do not guarantee identical audio. It remains a single-speaker file-generation adapter, not a live WebSocket or multi-speaker implementation. The runtime's existing request limit is 5,000 characters, although v4's service limit is 10,000.

Use inline directions such as `[whispers]`, `[angry]`, `[laughs]` and punctuation. Do not add SSML `<break>` tags. V4 exposes Stability and Similarity; Style and Speed settings are not supported. These overrides are not currently runtime request fields. Avoid background sound tags for a dry game dialogue asset unless requested. A reused voice ID preserves the selected identity, but a new model may change its realized timbre and accent: compare rather than promise identical sound.

For character acting, diagnose voice selection, spoken wording and delivery directions separately. Generic `[sinister]` or `[angry]` tags do not specify a boss's vocal weight, articulation or pacing. Use concise audible qualities, for example `[low, gravelly voice] [menacing] [slow, deliberate delivery]`, then compare a more explicit direction if needed. Keep directions inside audio-tag brackets; ordinary prose prepended to TTS text may be spoken aloud. A playful selected voice or playful dialogue can still bias the result. Keep the character's voice and spoken words fixed for a prompt comparison; audition a different voice as a separately labeled experiment, not a silent identity replacement.

English descriptive tags with Korean dialogue are a useful experiment, not a proven universal advantage. Check whether prior tags were already English before blaming their language. To compare English and Korean directions, translate the same direction and preserve voice, dialogue, model, seed and postprocessing. One take per condition does not separate language effects from generation variability. Retain dry sources and matched-volume previews; do not present pitch shifts, distortion or reverb as evidence of improved model acting. If v3 suits an established character better, preserve that explicit preference rather than forcing an upgrade.

Distinguish the language of the **spoken script** from the language of its **acting directions**. For multilingual diagnosis, compare translated scripts under equivalent directions with the same provider/voice, and record the language and model. The v4 product guide says cross-language generation prioritizes natural target-language speech over carrying the source accent; that is not proof of a Korean-specific bug or identical character texture. Test in the actual game language. Cross-provider auditions use separately identified voices and finishing: Gemini's density default and different voice identity must be visible rather than described as a same-speaker model benchmark.

The connected speech plugin's checked schema now includes `eleven_v4`. Prefer it for ordinary generation when it supports the requested controls and archival. Use the guarded runtime for API verification and controlled comparisons requiring a recorded seed, exact prior request or durable local jobs; the plugin does not expose seed. Do not modify the plugin cache. Preserve old model labels/receipts, and resume saved jobs without upgrading or automatically retrying them. Older cloned voices can need v4 retraining/verified consent; do not create or retrain a clone for a model test when an existing library voice suffices.

Sources: [launch](https://elevenlabs.io/blog/eleven-v4), [model/product guide](https://elevenlabs.io/docs/eleven-creative/playground/text-to-speech), [speech API](https://elevenlabs.io/docs/api-reference/text-to-speech/convert), [prompting](https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices).

## Music v2.5 model and transport

For default ElevenLabs BGM, select Music v2.5 unless the user names an older version. The official REST model ID is **`music_v2_5`**. The runtime selects it for `auto` music with a key, or explicitly selected ElevenLabs music; write the model explicitly in new requests for clear provenance. Do not rely on the server's omitted-model default.

The connected plugin inventory checked 2026-09-15 exposed only `eleven_music_v1` and `eleven_music_v2`. Those are plugin IDs, not the REST IDs. Use the guarded CLI/API route with the existing private key while that limitation holds. Do not invent an `eleven_music_v2_5` plugin enum, modify the plugin cache, or use v2 as a substitute. A future plugin can be used after its actual schema and result metadata support the selected version. Missing v2.5 access or a rejected request is not permission to switch models or submit another paid take.

The runtime calls `POST https://api.elevenlabs.io/v1/music` with `model_id: "music_v2_5"`, the submitted `prompt` (at most 4100 characters), `music_length_ms` (3000–600000) and `force_instrumental` (true for instrumental BGM). It uses `output_format=auto` and omits seed: this endpoint does not allow seed with a prompt. BPM/key direction belongs in the prompt. Use [the complete runtime request](runtime.md#elevenlabs-bgm-v25), then `plan`, `generate --async`, and the returned job ID; do not create an untracked one-off HTTP script.

Preserve the actual requested model in `remote.json` and the manifest, with any returned song/request ID. Retain the observed model of imported older audio; a new default does not turn a v2 take into v2.5. Model capability and [actual-use eligibility](music.md#eleven-music-eligibility) are separate checks.

## Private key handling

The CLI checks, in order:

1. Process `ELEVENLABS_API_KEY`, then `ELEVEN_API_KEY`.
2. `ELEVENLABS_API_KEY_FILE` if set; otherwise the configured `elevenlabs_key_file`, default `.secrets/elevenlabs_api_key` under the runtime root.

The private file contains the key alone. `doctor` reports only presence/source, not the value. `doctor --online` reads subscription/credit availability. `.secrets/`, `.env*`, settings, logs and generated files are excluded from Git. Never place a key in a request JSON, URL, command argument or transcript. Do not scan unrelated credential files.

If the user already chose a private path, use it; do not force the plugin's example `.env` convention or ask to rotate a valid key. If using an official SDK example directly, supply the key only inside that process. No global environment change is needed.

`key-status requested` records a question already asked; it does not ask the question itself. `key-status declined` also sets `only_local`. `key-status configured` records setup state, while a real read query is the authentication evidence. With mode `auto`, absent keys make CLI generation local-only; it cannot inspect connector-managed authentication. Existing audio import/edit stays local regardless of its original provider.

An invalid/unauthorized key is not a successful capability check. Explain the observed failure once; local work can continue when consistent with the request. If the user explicitly required ElevenLabs, do not relabel a local result as fulfilling that requirement. Do not silently reroute an already submitted job.

## Paid calls and recovery

A request to make a sound covers its requested standard takes. Do not add another credit-confirmation step within that scope. Resolve an actually missing budget or new unrequested spending before doing it. Creating this skill or a benchmark plan is not itself a request to generate paid test sounds.

The adapter saves `remote.json` before its single POST and records request/history/song IDs when returned. It never automatically retries that POST, including after rejection or a lost response. It reads subscription balance before each new take. SFX cost is estimated locally at 40 credits/second and TTS conservatively at one credit/character; these are planning estimates, not server limits. `max_credits` can impose a smaller estimate cap. Current music pricing is not estimated by the adapter, so a music request with `max_credits` blocks until that budget is resolved.

After a timeout/crash, query the saved job and receipt. `resume` reuses downloaded source audio and completed takes; it does not repeat uncertain paid attempts. Use `history` to identify the original result. `recover-history` requires a captured matching history/request ID plus matching text/model (and voice for TTS). If no ID was captured or music needs provider-specific recovery, inspect the provider's existing result and import the verified file. Do not substitute another item with the same prompt or create a replacement automatically.

For plugin calls, preserve a pending receipt before submission (prompt/model, requested count, timestamp, tool name; no secrets), then save returned IDs/file locations. On ambiguous completion, reconcile that same operation through available history/job tools. Do not invoke the CLI as a second generation attempt. A raw file can be preserved through `import` with `transport: "plugin"` and the observed request ID.

## Format and API scope

ElevenLabs SFX descriptions are limited to **450 characters**. Count the actual submitted string before a paid call; keep action, material, perspective and necessary exclusions. The plugin's model schema and cost estimate may omit this constraint and accept an overlong node, while the generation later fails validation. [Official SFX guide](https://elevenlabs.io/docs/eleven-creative/playground/sound-effects).

The core adapter supports standard text SFX, existing-voice TTS and prompt-based music. Voice creation/cloning on ElevenLabs, alignment, isolation, stems, music composition-plan editing and inpainting use a relevant available plugin/SDK operation when requested; they are not implemented CLI flags.

For SFX/TTS the initial core adapter saves MP3 (`mp3_44100_128` compatibility default; configure a permitted higher bitrate such as `mp3_44100_192` after checking the plan). Music requests use the API's `auto` MP3 format. The original is retained alongside the decoded WAV. For a required lossless provider source, select an available plugin/SDK lossless output path and import the correctly decoded file; do not call MP3-to-WAV lossless source generation.

Sources checked 2026-09-15: [SFX API](https://elevenlabs.io/docs/api-reference/text-to-sound-effects/convert), [TTS API](https://elevenlabs.io/docs/api-reference/text-to-speech/convert), [Music API](https://elevenlabs.io/docs/api-reference/music/compose), [Authentication](https://elevenlabs.io/docs/api-reference/authentication).

# ElevenLabs access and plugin cooperation

## Access check

Use the current tool inventory or tool search to discover actual ElevenLabs capabilities. Check that the tool supports this kind of audio, returns a playable/local output or downloadable asset, and exposes enough result identity to recover it. A connection UI or installed skill is not an authenticated generation test. Prefer a read-only account/voice query when available; do not spend credits just to test authentication.

The ElevenLabs plugin installed when this skill was authored contains provider skills for `sound-effects`, `text-to-speech`, `music` and `setup-api-key`. Their generation examples use the official SDK/API and `ELEVENLABS_API_KEY`. Installation of these instructions does not remove the key requirement. If a future connector supplies working managed authentication, use it without requesting a redundant local key. Do not extract connector secrets or modify the plugin cache.

Use the installed relevant skill for prompting and supported SDK operations; reconcile stale model/parameter examples against current official API documentation. Keep this game skill's model selection, routing, requested take count, provenance and review workflow around the provider operation. The runtime's guarded API adapter supports standard SFX/TTS/music and is the direct route when the plugin lacks the selected model; advanced plugin operations can be imported as existing files.

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

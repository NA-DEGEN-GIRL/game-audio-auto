---
name: game-audio
description: Create, edit and review game audio, character dialogue, variations, loops and animation cues, or explain the available options. Default to Gemini for acted characters/NPCs and ElevenLabs for other audio; preserve accepted voices and explicit provider or local choices.
---

# Game Audio

Create sounds that work in the requested game: recognizable actions/materials, useful timing, consistent space and character, and convincing repeated playback. A successful model call alone does not establish those qualities.

## Quick help

For `$game-audio 설명서`, usage/help, or a reminder of available options, read [quick manual](references/quick-manual.ko.md) and give a short Korean guide with the defaults, relevant options and a few request examples. Help alone does not authorize generation, key inspection, network calls or installation. If the same request also asks for actual work, answer the relevant help and continue that authorized work.

## Start with the actual use

Inspect supplied assets and the relevant game/project context. Establish the event, material/action, sonic style, listening distance, duration or timing window, repetition pattern and delivery target. Infer routine choices; ask only about choices that materially change the result. Preserve explicit provider, voice, budget and local-only preferences.

Use one coherent sound brief across a related set. Short action cues usually need a clear onset and a complete decay. Choose dry or spatial recording according to the target game's mixing/reverb, not a universal rule. Do not force an engine or build a viewer for a file request.

## Choose generation and access separately

| Sound | Default | Access / local alternative |
| --- | --- | --- |
| SFX, Foley, UI, impacts, creatures | ElevenLabs Sound Effects v2 | Stable Audio 3 Small SFX; consider Medium for a justified need |
| Ambience | ElevenLabs Sound Effects v2 with loop intent where needed | Stable Audio 3 Small SFX / Medium, then local loop authoring |
| Acted characters, NPCs, bosses and expressive barks | Gemini 3.8 Flash TTS with density finishing | Separate Gemini key required; Qwen3-TTS for selected local work |
| General narration and informational speech | Eleven v3 with an observed, consistent voice ID | Qwen3-TTS; keep speaker/reference consistent |
| BGM | ElevenLabs Music v2.5 | Choose local ACE-Step 1.5 or Stable Audio 3 from the brief and relevant feedback |

For dialogue requiring character/NPC acting, default to **Gemini 3.8 Flash TTS** and **density finishing (밀도 강화)**. Set `dialogue_role: "character"` with `provider: "auto"`, or explicitly select `provider: "gemini", model: "gemini-3.8-flash-tts"`. Ordinary narration uses `dialogue_role: "narration"` and retains the ElevenLabs default. `unspecified` preserves legacy routing; classify the intended use instead of inferring it from prompt keywords. Preserve an accepted character's provider, model and voice explicitly, even when a new general default differs. Voice IDs are provider-specific. Retain the native source and allow unprocessed or alternative finishing; ElevenLabs does not inherit Gemini's density finish. Missing Gemini access calls for its setup, not a silent replacement voice/provider. A missing ElevenLabs key does not block Gemini with its own key; explicit `only_local` blocks both. Read [character-voices.md](references/character-voices.md) for setup, design, acting, finishing and archival.

Use natural conversational pacing unless the scene calls for a deliberate slowdown. Menace or vocal weight alone does not require slow delivery. Keep acting directions short; choose their language from accepted character/project results. Compare equivalent Korean and English directions when requested, without claiming either is universally better. Shape the performed outburst first; add room reverb or other dramatic effects as a separate edit when needed, preserving the source.

For BGM, default to ElevenLabs Music v2.5 when access is available. Under this default, an ordinary BGM creation request covers the requested standard ElevenLabs takes without another provider or credit confirmation. Respect explicit local/model/budget choices. For local work, choose ACE-Step 1.5 or Stable Audio 3 from the brief, controls and relevant feedback; neither must fail before trying the other. Saved local preferences guide local work and do not override the newer ElevenLabs default. Missing access or explicit `only_local` selects the local workflow. Do not switch provider after an uncertain paid submission. See [music.md](references/music.md) for model selection, use evidence and review.

For default or explicitly selected ElevenLabs BGM, use **Music v2.5** unless the user explicitly chooses an older model. Write `provider: "elevenlabs", model: "music_v2_5"` for the runtime API route. A plugin is suitable only if its callable schema explicitly supports v2.5; if it lists only v1/v2, use the existing guarded runtime with the saved key. Do not downgrade to fit an old plugin or copy a stale `music_v2` default from its skill. See [providers.md](references/providers.md#music-v25-model-and-transport) for the route and [runtime.md](references/runtime.md#elevenlabs-bgm-v25) for a complete request.

Read [providers.md](references/providers.md) when checking credentials or using ElevenLabs. Prefer a callable, authenticated ElevenLabs plugin tool that supports the selected model, requested operation and saving its output. Discover the actual tools; never invent an MCP tool name or assume plugin installation proves authentication. The installed ElevenLabs `sound-effects`, `text-to-speech` and `music` skills can provide provider-specific guidance, subject to this game's model and routing choices. Load only the relevant one. They may still require an API key.

If no suitable authenticated plugin tool exists, the bundled runtime makes tracked calls to the same official API using a private key. A plugin-created file can enter the same local workflow through `import`; do not generate it again just to put it in the library. The plugin is optional, not a hard dependency.

For an operation that needs ElevenLabs, if neither authenticated tools nor a usable key is available, ask once for a private local key file, recording `key-status requested`. Local BGM does not need a key question. Do not ask for the secret in chat. If the user declines all remote access, set `only_local`; absent ElevenLabs access, non-character `auto` resolves to local-only. For default or explicitly selected Gemini, check its separate key and follow its setup reference instead. Continue preparation/editing and local work without repeated key questions. A pending promise to save a key is not proof it exists. Explicit `only_local` blocks remote generation through every transport, even a connected plugin.

## Execute and preserve

For selected ElevenLabs dialogue and default narration, use **`eleven_v3`**. Use `eleven_v4` when explicitly requested or already accepted for the current character; realistic NPCs, narration and recorded-voice reproduction are reasons to propose a v4 audition, not to switch automatically. `eleven_v4_turbo` is an explicit latency option. The vendor warns that ElevenLabs Voice Design voices may perform and sound worse with v4; this limitation is not a claim about every library voice or Gemini-designed character. Preserve a character's accepted model and voice over general defaults. Read [speech models](references/providers.md#speech-models-v4) for the decision table, source-type checks and preserved comparisons. New defaults never change a saved job's model or voice.

The skill is linked to a shared runtime. Resolve this skill's real path; `scripts/audioctl.py` locates the runtime through that path and runs its isolated environment. Read [runtime.md](references/runtime.md) for setup, validated specs and commands. Read [local-models.md](references/local-models.md) only when a local backend is needed. Install only that backend; do not silently replace natural sounds with placeholder beeps/noise when inference is unavailable.

For first-time installation or work across Windows and SSH/Linux, read [execution and setup](references/execution-setup.md). Use the same wrapper with `--execution local` or `--execution windows`; inspect the chosen host's doctor/plan and keep that execution host with all job/asset IDs. A registered native runtime is preferred by auto; otherwise the existing SSH-to-Windows bridge remains available. Ask only for missing setup information, never API secrets in chat. For Windows execution from SSH, read [Windows bridge routing](references/windows-bridge.md), upload inputs and rewrite embedded paths before submission.

1. Prepare a bounded request. Match variants to the requested set; the CLI defaults to one take, with no automatic extra paid retries. Local edits of an existing result need no new generation.
2. Generate through one chosen transport, or import supplied/plugin audio. Save provider/model, request IDs, raw codec and prompt/settings. Preserve an uncertain paid submission for reconciliation instead of trying another transport.
3. Use local trim, gain, fades, layer authoring or loop editing to fit the gameplay event. Preserve sources and create a new revision for changes. Conversion to 48 kHz WAV does not recover quality discarded by a compressed source.
4. Inspect measurements and **actually listen** when audio perception is available. Review repetitions and the relevant in-game context. Repair the observed problem and recheck the affected result. See [sound-design.md](references/sound-design.md) and [review-integration.md](references/review-integration.md).
5. Deliver named files and playback metadata, with separate numerical, listening, repetition and integration status. `manifest.json` marks finished export, not listening approval. If actual listening is unavailable, leave it unreviewed and provide playable previews for the user; never claim to have heard a waveform or transcript.

For animated 3D assets, align sounds to observed contacts/actions and clip times. Audio cues are separate from mesh generation. Preserve existing animation and report cue metadata separately from tested engine integration.

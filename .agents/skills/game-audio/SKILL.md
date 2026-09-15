---
name: game-audio
description: Create, edit and review game audio assets, variation sets, loops and animation sound cues. Use ElevenLabs first for music, effects and dialogue, with local ACE-Step, Stable Audio and Qwen alternatives when access is unavailable or requested.
---

# Game Audio

Create sounds that work in the requested game: recognizable actions/materials, useful timing, consistent space and character, and convincing repeated playback. A successful model call alone does not establish those qualities.

## Start with the actual use

Inspect supplied assets and the relevant game/project context. Establish the event, material/action, sonic style, listening distance, duration or timing window, repetition pattern and delivery target. Infer routine choices; ask only about choices that materially change the result. Preserve explicit provider, voice, budget and local-only preferences.

Use one coherent sound brief across a related set. Short action cues usually need a clear onset and a complete decay. Choose dry or spatial recording according to the target game's mixing/reverb, not a universal rule. Do not force an engine or build a viewer for a file request.

## Choose generation and access separately

| Sound | Default with usable ElevenLabs access | Without access / explicit `only_local` |
| --- | --- | --- |
| SFX, Foley, UI, impacts, creatures | ElevenLabs Sound Effects v2 | Stable Audio 3 Small SFX; consider Medium for a justified need |
| Ambience | ElevenLabs Sound Effects v2 with loop intent where needed | Stable Audio 3 Small SFX / Medium, then local loop authoring |
| Dialogue, barks, narration | Eleven v3 with an observed, consistent voice ID | Qwen3-TTS; keep speaker/reference consistent |
| BGM | ElevenLabs Music v2.5 | Choose local ACE-Step 1.5 or Stable Audio 3 from the brief and relevant feedback |

For BGM, default to ElevenLabs Music v2.5 when access is available. Under this default, an ordinary BGM creation request covers the requested standard ElevenLabs takes without another provider or credit confirmation. Respect explicit local/model/budget choices. For local work, choose ACE-Step 1.5 or Stable Audio 3 from the brief, controls and relevant feedback; neither must fail before trying the other. Saved local preferences guide local work and do not override the newer ElevenLabs default. Missing access or explicit `only_local` selects the local workflow. Do not switch provider after an uncertain paid submission. See [music.md](references/music.md) for model selection, use evidence and review.

For default or explicitly selected ElevenLabs BGM, use **Music v2.5** unless the user explicitly chooses an older model. Write `provider: "elevenlabs", model: "music_v2_5"` for the runtime API route. A plugin is suitable only if its callable schema explicitly supports v2.5; if it lists only v1/v2, use the existing guarded runtime with the saved key. Do not downgrade to fit an old plugin or copy a stale `music_v2` default from its skill. See [providers.md](references/providers.md#music-v25-model-and-transport) for the route and [runtime.md](references/runtime.md#elevenlabs-bgm-v25) for a complete request.

Read [providers.md](references/providers.md) when checking credentials or using ElevenLabs. Prefer a callable, authenticated ElevenLabs plugin tool that supports the selected model, requested operation and saving its output. Discover the actual tools; never invent an MCP tool name or assume plugin installation proves authentication. The installed ElevenLabs `sound-effects`, `text-to-speech` and `music` skills can provide provider-specific guidance, subject to this game's model and routing choices. Load only the relevant one. They may still require an API key.

If no suitable authenticated plugin tool exists, the bundled runtime makes tracked calls to the same official API using a private key. A plugin-created file can enter the same local workflow through `import`; do not generate it again just to put it in the library. The plugin is optional, not a hard dependency.

For an operation that needs ElevenLabs, if neither authenticated tools nor a usable key is available, ask once for a private local key file, recording `key-status requested`. Local BGM does not need a key question. Do not ask for the secret in chat. If the user declines/has no key, set `only_local`; while no key is available, `auto` also resolves to local-only. Continue preparation/editing and local work without repeated key questions. A pending promise to save a key is not proof it exists. Explicit `only_local` blocks remote generation through every transport, even a connected plugin.

## Execute and preserve

The skill is linked to a shared runtime. Resolve this skill's real path; `scripts/audioctl.py` locates the runtime through that path and runs its isolated environment. Read [runtime.md](references/runtime.md) for setup, validated specs and commands. Read [local-models.md](references/local-models.md) only when a local backend is needed. Install only that backend; do not silently replace natural sounds with placeholder beeps/noise when inference is unavailable.

1. Prepare a bounded request. Match variants to the requested set; the CLI defaults to one take, with no automatic extra paid retries. Local edits of an existing result need no new generation.
2. Generate through one chosen transport, or import supplied/plugin audio. Save provider/model, request IDs, raw codec and prompt/settings. Preserve an uncertain paid submission for reconciliation instead of trying another transport.
3. Use local trim, gain, fades, layer authoring or loop editing to fit the gameplay event. Preserve sources and create a new revision for changes. Conversion to 48 kHz WAV does not recover quality discarded by a compressed source.
4. Inspect measurements and **actually listen** when audio perception is available. Review repetitions and the relevant in-game context. Repair the observed problem and recheck the affected result. See [sound-design.md](references/sound-design.md) and [review-integration.md](references/review-integration.md).
5. Deliver named files and playback metadata, with separate numerical, listening, repetition and integration status. `manifest.json` marks finished export, not listening approval. If actual listening is unavailable, leave it unreviewed and provide playable previews for the user; never claim to have heard a waveform or transcript.

For animated 3D assets, align sounds to observed contacts/actions and clip times. Audio cues are separate from mesh generation. Preserve existing animation and report cue metadata separately from tested engine integration.

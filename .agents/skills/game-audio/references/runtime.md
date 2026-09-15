# Runtime and requests

The runtime root is four parents above this skill's `scripts/audioctl.py` after resolving its junction/symlink. Run that wrapper with an available Python, or run the following from the runtime root:

```sh
uv sync --locked --python 3.12
uv run --no-sync python -m game_audio.cli doctor
uv run --no-sync python -m game_audio.cli --root /absolute/runtime plan /absolute/request.json
```

Install FFmpeg on PATH (or set `ffmpeg` in `audio-system.local.json`). Core setup installs no model weights. Use `--root` **before** the subcommand; JSON paths and relative audio paths resolve against that root. For another game project, keep this shared runtime and pass absolute source/output paths. Do not synchronize the 3D project's environment.

`src/game_audio/models.py` owns validation and `src/game_audio/cli.py --help`/CLI `--help` owns commands. JSON rejects unknown fields. The settings file is validated by `Settings`; edit the relevant field without replacing other configuration. `doctor` describes local key/backend state, not connector capabilities or listening quality.

## Core operations

| Command after `python -m game_audio.cli` | Effect |
| --- | --- |
| `doctor [--online]` | Local prerequisites; optional read-only account query |
| `mode auto` / `mode only_local` | Persist provider policy |
| `key-status requested` / `declined` / `configured` | Record key setup state without handling a secret |
| `plan request.json` | Validate generation and show provider, count, estimate and blockers; no submission |
| `generate request.json --async` | Start the specified takes and return a job ID |
| `import import.json` | Snapshot existing supplied/plugin audio, export locally and record provenance |
| `edit edit.json [--async]` | Create a revision with trim/gain/fades/loop processing |
| `job JOB_ID` | Inspect progress, outputs or failure |
| `resume JOB_ID [--async]` | Continue the saved job without replacing its provider/request |
| `account`, `voices [--page-token TOKEN]`, `history [--start-after ID]` | Read-only ElevenLabs queries |
| `recover-history JOB_ID --take 1 --history-id ID` | Recover an identified previous result, zero POSTs; then resume |
| `analyze master.wav` | Numerical WAV/PCM inspection, no listening |
| `audition a.wav b.wav --output preview.wav --repeat 3 --target-lufs -18` | Level-matched preview with A/B labels in adjacent JSON |
| `review REVISION --take 1 --spec review.json` | Save actual evidence bound to an audio hash |
| `verify REVISION` | Check source/request/export integrity |
| `benchmark-plan --output .work/bgm-test --duration 30 --variants 2` | Write comparison requests without executing them |
| `adopt-music REVISION --take 1 --purpose exploration --evidence "actual comparative findings"` | Save reviewed provider/model for that purpose |

`generate` without `--async` waits. Prefer async for model work; poll `job` and report meaningful progress. Windows workers start hidden. Job status `completed` means files exported; quality remains in separate review sidecars. A failed partial revision has no completed manifest. A lost worker is reported as interrupted; resume its ID. Do not start a second submission while the first is still running.

## Generation example: a coherent action cue

```json
{
  "name": "wood_door_close",
  "kind": "sfx",
  "prompt": "One heavy wooden door closing, a short hinge creak into a solid low wooden impact and a small metal latch click. Close perspective, restrained room reflection, isolated event with complete decay, no voices or music.",
  "provider": "auto",
  "duration_seconds": 2,
  "variants": 1,
  "purpose": "nearby interior door interaction",
  "acceptance": ["one readable close event", "no cut-off decay", "fits a small wooden room"],
  "playback": {"intent": "once", "spatial": "3d", "avoid_immediate_repeat": true},
  "export": {"sample_rate": 48000, "channels": "mono", "subtype": "PCM_24"}
}
```

Common generation fields: `name`, `kind` (`sfx|ambience|dialogue|music`), `prompt`, `provider`, optional `model`, `duration_seconds`, `variants` (default 1), `seed`, `purpose`, `acceptance`, `playback`, `export`, optional `max_credits`. Non-dialogue needs duration. SFX v2 takes 0.5–30 s; native looping is a request, still requiring listening review.

Dialogue uses exact spoken `prompt`, `language`, and `voice_id` for ElevenLabs. Omit duration; speech controls actual length. Qwen uses `voice_mode` (`custom|design|clone`), `speaker`, `instruction` or `reference_audio`/`reference_text` as applicable. Defaults are Korean and Sohee for local custom voice, not a mandate for every character. For music, `provider: "auto"` selects ElevenLabs `music_v2_5` when a key is available. Explicit local/model choices take precedence. Without a key or in `only_local`, `auto` reuses a saved local choice for its `purpose`; otherwise the agent chooses `ace_step` or `stable_audio` from the brief without asking the user to choose a backend. Saved local preferences do not override the newer ElevenLabs default. Explicit Stable Audio music defaults to `small-music`. Exact `bpm`/`key` fields are currently sent only to ACE-Step. Other music backends receive such direction in the prompt. Seeds are best-effort controls only where sent, not a guarantee of cross-provider reproducibility.

## ElevenLabs BGM v2.5

Use this route for default or explicitly selected ElevenLabs BGM when the plugin lacks v2.5. Save a request such as `.work/bgm-v2_5.json`, adapting the musical brief and duration to the actual task:

```json
{
  "name": "boss_bgm_v2_5",
  "kind": "music",
  "provider": "elevenlabs",
  "model": "music_v2_5",
  "prompt": "Instrumental dark fantasy boss battle. Menacing low strings, dissonant pipe organ, metallic percussion and a distorted music-box motif. Relentless tension at 156 BPM in D minor, grotesque and threatening, no cheerful carnival melody. Leave space for combat sound effects.",
  "duration_seconds": 32,
  "variants": 1,
  "instrumental": true,
  "purpose": "boss battle",
  "acceptance": ["threatening rather than cheerful", "no vocals", "space for combat cues"],
  "playback": {"intent": "loop", "spatial": "2d"},
  "export": {"sample_rate": 48000, "channels": "preserve", "subtype": "PCM_24"}
}
```

```sh
uv run --no-sync python -m game_audio.cli plan .work/bgm-v2_5.json
uv run --no-sync python -m game_audio.cli generate .work/bgm-v2_5.json --async
uv run --no-sync python -m game_audio.cli job JOB_ID
```

`plan` must resolve to `elevenlabs`, `music_v2_5`, transport `api` before submission. Existing key resolution applies. Use already established purpose-specific evidence; the plan records missing use evidence as `unverified` without blocking creation or asserting release permission. A music credit cap that the runtime cannot estimate is a reported blocker. Planning submits nothing; run generation only for the requested takes. The receipt records the model, prompt, returned IDs and original format. Instrumental defaults to true; loop intent still needs musical loop editing/review. Prompt-mode music does not send the local request's seed. Explicit `music_v1`/`music_v2` requests remain available for an intentional older-version comparison; no automatic downgrade occurs.

An ElevenLabs music request (`auto` or `elevenlabs`) can include `music_eligibility_evidence` for an already checked, narrower use (for example a private comparison). This records only that request's purpose, source and date; it does not change global eligibility. See [music.md](music.md#eleven-music-eligibility).

## Import and local editing

```json
{
  "name": "door_from_plugin", "kind": "sfx", "source": "/absolute/plugin-output.mp3",
  "provider": "elevenlabs", "model": "eleven_text_to_sound_v2", "transport": "plugin",
  "request_id": "observed-provider-id", "prompt": "the actual submitted description"
}
```

Use actual metadata or `unknown`; do not invent IDs. `source_sha256` can bind the intended source. Import never uploads or regenerates audio. It preserves the raw input then exports a WAV. FLOAT input exceeding full scale needs `export.subtype: "FLOAT"` before a deliberate gain edit; integer PCM export rejects silent clipping.

```json
{
  "name": "forest_loop", "source": "/absolute/revision/take-001/master.wav",
  "start_seconds": 0.25, "end_seconds": 20.25, "gain_db": -2,
  "loop_crossfade_seconds": 0.15,
  "export": {"sample_rate": 48000, "channels": "preserve", "subtype": "PCM_24"}
}
```

Optional edit fields: `source_sha256`, `parent_revision`, `fade_in_seconds`, `fade_out_seconds`, `notes`, `playback`. The parent is inferred only from an actual matching manifest take. If supplied, `parent_revision` must match it. Omitting playback preserves the parent settings. Timing edits clear an inherited sync anchor for rechecking; a crossfade implies loop intent unless playback was explicitly supplied.

Loop crossfade rotates the start past the overlap and shortens the result by that overlap duration. It is useful for steady ambience; it does not find musical beats or promise seamless rhythm. Other authoring (layer mixing, EQ, denoising, precise beat editing) can use trusted local tools/FFmpeg with explicit source files, recorded operations and a new imported result. Those are not implicit CLI flags.

## Evidence and artifacts

`.assets/jobs/ID.json` stores durable job state. `.assets/audio/NAME/REVISION/` holds the source snapshot/request, provider raw audio and receipts, WAV takes, analysis, review and final `manifest.json`. `.work/` holds disposable-to-the-workflow previews/comparisons, but do not blanket-delete it. Keep `.secrets/`, `.runtime/` and settings private.

Review example fields are `audio_sha256`, `listening`, `method`, `listened_ranges_seconds`, `repetition`, `integration`, `evidence`, `findings`, `untested`. Pass/fail listening decisions require the actual method and listened ranges within the file. Repetition/integration decisions require evidence. A review cannot attach to a different audio hash. Review changes are archived separately and do not change source audio. Never enter a passing value to satisfy the schema if the listening/playback did not happen.

Default delivery is the intended takes, raw source where useful and manifest/playback notes. Request-specific copies to a game's asset folder should retain provenance; verify target import/playback only when that integration is in scope.

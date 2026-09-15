# Isolated local model environments

Install only the backend needed for the user's sound request. The core editing runtime does not contain PyTorch or model weights. ElevenLabs is the default with access. ACE-Step and Stable Audio are equal candidates for local BGM; use local generation when requested or ElevenLabs access is unavailable. A configuration entry alone does not make an uninstalled model runnable. Report setup, completed inference and listening quality separately. Read [music.md](music.md) for local music selection, license conditions and provenance.

From the runtime root:

```sh
uv run --no-sync python scripts/bootstrap_local.py stable_audio --device cuda --plan
uv run --no-sync python scripts/bootstrap_local.py stable_audio --device cuda
uv run --no-sync python scripts/bootstrap_local.py qwen --device cuda
uv run --no-sync python scripts/bootstrap_local.py ace_step --device cuda
```

Each installation line is an alternative, not a required bundle. `--plan` makes no installation changes. A selected install fetches a pinned source commit, creates a separate environment and dependency lock, then registers its Python/project/device in settings. It does not download model weights deliberately; first selected inference may fetch them. Respect provider access/gating and the actual model license.

If an older uv fails on a checkout path containing `#`, use an explicit `--backend-root` outside that path while keeping `--root` pointed at the audio runtime. This puts only optional environments elsewhere and registers them in the original settings. Stable Audio/Qwen are built as wheels before dependency resolution to avoid upstream CUDA-index conflicts; the wheel hash and dependency lock are retained.

For gated Hugging Face models, reuse an existing authorized token location supplied by the user. Set `huggingface_token_file` in private local settings, or use `HF_TOKEN`; the runner passes its value only in the child environment, not requests/logs. A valid token with `403 GatedRepo` still requires that account's model access agreement. Ask for the missing access, not another copy of a token already available. Keep token values out of chat and version control.

| Backend | Initial model choices | Environment facts |
| --- | --- | --- |
| `stable_audio` | `small-sfx` for effects; `small-music` or `medium` for BGM | Pinned source requires Torch 2.7.1; Small supports CPU; Medium requires suitable CUDA/attention setup |
| `qwen` | `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`, `VoiceDesign`, `Base` | Dedicated environment because its Transformers requirements differ from Stable Audio; core runner uses SDPA |
| `ace_step` | `acestep-v15-turbo` initially | Uses the pinned upstream project/lock, checkpoints under its project; optional LM not loaded by core runner |

Pins live in `scripts/bootstrap_local.py`, adapter calls in `scripts/local_runner.py`. The core `uv.lock` does not lock optional ML environments. Their locks are resolved on selected installation and retained under `.runtime/`; inspect/fix installation failures in that isolated environment. Do not claim these are tested model installations merely because the wrappers compile. Stable Medium/FlashAttention2 on the target OS may need a suitable Linux/WSL environment; the bootstrap does not install drivers or guarantee that setup. An explicitly configured external environment is supported via `local_backends`.

Generation records the seed, package versions, model and available backend metadata. Hugging Face cache inventory is labeled as inventory, not proof of which weights ran. For reproducible production assets, record the actual resolved weight revision/hash and preserve it with the receipt; do not infer it from a model alias alone.

ACE-Step turbo uses 8 steps by default and explicit `shift=3.0`, as recommended by the current upstream inference guide; non-turbo retains `shift=1.0`. The runner records these effective parameters in `ace-effective-params.json`. Turbo distills guidance, so increasing CFG does not increase prompt adherence. Keep its combined text conditioning within the installed 256-token limit; see [music prompting](music.md).

`gpu_lock` is a configurable file lock shared across audio inference jobs. If sharing a GPU with the 3D runtime, point this local setting at the **observed** 3D `.assets/.locks/trellis.lock`. Do not hard-code another user's runtime path. Avoid overlapping large models on the same GPU. No local generation starts an engine/viewer.

Routine maintenance uses synthetic audio and mocked API responses. For a selected real-backend check, generate a bounded requested cue, confirm actual model inference and inspect/listen to its result. Do not label a synthesized test sine wave a local AI-generated natural sound. Model download/access, GPU compatibility and quality remain unverified until checked on the actual host.

Official sources checked 2026-09-15: [Stable Audio 3 source](https://github.com/Stability-AI/stable-audio-3), [Qwen3-TTS source](https://github.com/QwenLM/Qwen3-TTS), [ACE-Step 1.5 source](https://github.com/ace-step/ACE-Step-1.5).

# Execution host and first-time setup

**English** | [한국어](execution-setup.ko.md)

## Inspect before installing

When the user asks to install/setup this skill on another computer, inspect the
OS, existing runtime, Python, required tools and (only for a selected model) GPU
and disk capacity. Use the user's existing runtime and authenticated tools when
usable. Ask only for missing choices that affect the requested capability:
installation directory when nonstandard, selected optional model, or credentials.
Do not ask for API secrets in chat. Use a private local key file/environment,
validate through a read-only account check, and report only configured/verified.
Copy a key to another host only with the user's authorization.
When Windows execution is already available, check its doctor before requesting
a new key: the agent can use that existing authenticated route without copying
credentials to Linux.

Install the core first. Model environments and weights are separate, optional
installations selected for the task; a CPU-only server must not be reported as
ready for CUDA generation. Do not change the requested model/provider to make
installation pass. Existing approval to install covers ordinary setup commands;
do not repeatedly ask about prerequisites already authorized.

## Windows and Linux core

Use a full runtime checkout, not a copy of the skill folder. Preserve any
existing checkout, local settings, assets and uncommitted work.

```sh
# In the runtime checkout on either operating system:
uv sync --locked --python 3.12
python .agents/skills/game-audio/scripts/audioctl.py runtime-configure --root /absolute/runtime --execution auto
python .agents/skills/game-audio/scripts/audioctl.py runtime-status
python .agents/skills/game-audio/scripts/audioctl.py --execution local doctor
```

Use an available Python to run the wrapper (`python3` on Linux); use a real
Windows absolute path on Windows. Registration checks the installed virtualenv
and pyproject; it does not install tools or prove generation capability. It stores
only root/execution in `~/.config/codex-skill-runtimes/game-audio.json`
(or `XDG_CONFIG_HOME`), shared across Codex profiles on that host.

Make the skill discoverable in that host's `$CODEX_HOME/skills/game-audio`, or
`~/.codex/skills/game-audio` when unset, by linking the runtime's
`.agents/skills/game-audio` or using the existing managed projection. Inspect an
existing destination before changing it; preserve unrelated skills and local
changes. Verify that the installed instructions and registered runtime support
the same commands. A private native runtime can coexist with a managed SSH
projection; do not edit a generated projection as the source of truth.

Install FFmpeg and the core Python dependencies for import, edits and analysis.
For ElevenLabs, use an already authenticated tool or the runtime's
`.secrets/elevenlabs_api_key` / `ELEVENLABS_API_KEY`; do not copy Windows path
settings or its .venv to Linux. Use `doctor --online` for a read-only validation.
For explicitly requested Gemini, use `.secrets/gemini_api_key` and
`gemini-voices` for its separate read-only access check; see
[character voices](character-voices.md). Both API routes work without a GPU or
downloaded generation models.
Read local-models.md only for a selected ACE-Step, Stable Audio or Qwen backend;
core setup does not download them. CPU support/performance is model-specific.

For an authorized key transfer, copy only the selected provider key files over
the existing encrypted SSH/SCP connection into the native runtime's private
`.secrets` directory. Keep values out of command arguments, terminal output,
archives, generated specs and Git. On Linux restrict the directory to `0700`
and each key file to `0600`; verify ownership and permissions without printing
contents. Inspect and preserve any pre-existing working credentials rather than
blindly replacing the entire directory. Do not transfer an unrelated token or
the Windows settings file as part of this setup.

## Select and pin execution

- `--execution local`: run this machine's registered runtime (or the linked
  checkout if unregistered), including while a Windows bridge is enabled.
- `--execution windows`: from SSH, use the registered Windows bridge; if it is
  unavailable, fail instead of silently running locally. On Windows this runs
  its native runtime.
- `auto`: prefer an explicitly registered native runtime. Without a native
  registration, preserve the existing Windows bridge behavior on SSH; otherwise
  use the linked local checkout. This resolves an installation, not every model's
  capability. Use `doctor` and the operation's plan before choosing the host.

Choose by the requested capability, existing assets and input locations. For
example, keep server audio edits on Linux; choose Windows for a CUDA model that
only Windows has. If local prerequisites are missing, the agent can plan a
Windows execution **before submission** using windows-bridge.md. The wrapper
never retries a failed/uncertain submission on another host or changes provider.

After choosing, use the explicit execution flag for submission, job polling,
resume, inspection and editing of that result. Keep runtime root/host with every
job or asset ID. Each host owns its library and jobs; registering a native
runtime does not migrate Windows history. To move existing work, transfer its
required inputs or export then import, with provenance; never assume an ID refers
to the same files on both machines.

Windows bridge requests need Windows input paths. Follow windows-bridge.md to
upload inputs and fetch results into the SSH project; native Linux requests use
Linux paths directly. The project/coding task itself stays on its original host.
Native Linux jobs can continue without Windows. Windows jobs need the workspace
worker and tunnel to remain available.

## Validate setup

Run status/doctor, then a small deterministic import/edit/export using temporary
fixtures and inspect actual output hashes/files. These checks are not model
inference or quality approval. Test a requested API/model separately within the
authorized scope, preserving paid receipts and avoiding automatic repeat calls.
For API setup, distinguish a successful read-only authentication check from a
successful synthesis. When live generation is authorized, submit a short take
for each requested provider on the explicit native execution route and verify
the completed file/manifest. For Gemini's default density finish, verify the
original revision and its `delivery_revisions` child too; do not infer that a
Windows result proves native Linux execution.

Maintainers: host selection lives in the wrapper, before runtime invocation.
The manager distributes the same wrapper/docs as a lightweight SSH projection.
Registered roots live outside that projection, so document refreshes never
replace native environments or assets. Keep wrapper routing tests and the paired
Korean guide current when changing this contract.
Native runtime code/dependencies are versioned separately: update that installation
deliberately and re-run its smoke checks when a new skill needs newer runtime
commands. A synchronized instruction file is not a runtime upgrade.

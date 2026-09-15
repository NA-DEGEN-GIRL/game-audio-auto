# ElevenLabs-first BGM and comparison

ElevenLabs Music v2.5 is the default for BGM when access is available. A BGM request covers its standard requested takes through this default without a separate provider confirmation. The runtime's `auto` uses ElevenLabs with a key; the agent may also write the resolved provider/model explicitly. Explicit local-only or model choices win. Without cloud access, choose ACE-Step 1.5 or Stable Audio 3 from the brief and local feedback without requiring one to fail first. Selection does not approve the resulting music or loop.

For local work, use ACE-Step's explicit BPM/key controls when they help the composition; choose Stable Audio directly when its arrangement/timbre or relevant feedback suits the brief. These are selection criteria, not universal quality rankings. Start Stable Audio with Small Music unless Medium is justified. If evidence is inconclusive, make a reasonable local choice; compare both when requested or useful within scope. Do not request an ElevenLabs key for an explicitly local-only task. A failed or uncertain cloud submission must be reconciled before any replacement generation.

Check relevant saved user feedback under `.assets/music-feedback/` for the requested purpose. Keep feedback scoped to the actual scene and candidate set; unspecified listened takes/ranges must remain unspecified. A reported style mismatch can guide the next choice without claiming that the alternative passed listening review or that the whole model is inferior.

For ACE-Step, keep the caption concise and put essential mood/instrument direction first. The installed DiT tokenizer truncates the combined instruction, caption and metadata at 256 tokens: an overlong caption can discard trailing BPM/key metadata. Check the actual tokenizer when near that limit; shortening is preferable to silently changing the upstream context limit. For a threatening jester scene, avoid a dense cluster of playful carnival/waltz descriptors unless that sound is intended. These observations do not establish a universal model-quality limitation.

| Candidate | Why test it | What remains to check |
| --- | --- | --- |
| ACE-Step 1.5 (turbo) | First-choice local option with BPM/key/duration controls | Musical quality, prompt fit, stable phrases; capabilities differ between base/SFT/turbo |
| Stable Audio 3 Small Music / Medium | Equally eligible first-choice local music option | Actual arrangement/timbre, access, Medium runtime requirements and applicable commercial-use conditions |
| Eleven Music v2.5 (default with access) | Primary BGM route via the guarded API, or a plugin that supports v2.5 | Account access, cost, use evidence and editing/loop results |

For ElevenLabs music, select `music_v2_5` and follow [model/transport selection](providers.md#music-v25-model-and-transport). Plugin examples using v2 do not override this choice. Existing v2 comparison audio keeps its original model label; generate a new revision only when another take is requested.

The core ACE adapter runs one take without its optional language model; it does not expose ACE cover/lego/extraction workflows. The Stable adapter generates from text; it does not implement stems. A plugin's additional music editing/stems tools may be useful when actually available and requested. Record which operation/model was used.

## Optional repeatable comparison

`benchmark-plan` creates nine request files: three cases × three providers, plus a score template. Its ElevenLabs requests explicitly select `music_v2_5`. It submits **nothing**. Defaults are two 30-second takes per case/provider; change counts to fit the requested trial, and select which files to run. No key means no ElevenLabs test. An unavailable candidate remains marked unavailable rather than being silently replaced.

Cases:

1. Exploration: calm fantasy texture, low fatigue and unobtrusive repeated gameplay.
2. Combat: rhythmic moderate intensity, clear cues without masking effects.
3. Transition: a change in tension and phrase boundaries suitable for authoring an exploration/combat transition.

Use the same brief, duration and take count for the compared models. Compare both raw output and an honestly recorded amount of finishing. Labels in `audition` hide provider names in the audible sequence but are not a full randomized/blinded experiment. Optional loudness matching affects only preview copies; it is not a target for all final music. Seeds do not create equivalent samples across different models. Eleven Music prompt mode does not accept seed.

Listen for timbre/artifacts, style, repeated-play fatigue, recognizable unwanted vocals, harmony/rhythm at the join, useful phrasing, controllability, gameplay masking and the actual time/cost of repair. A numerically small boundary jump cannot prove a musical loop. Test transitions in time and context, including return transitions when the game needs them.

Record original take hashes, provider/model, requested and actual duration, runtime/cost, edit settings, actual listened ranges and findings. `scores.json` is an open results record; explain scores rather than inventing precision. This small trial guides choices for these uses and is not a general quality ranking.

After selecting and reviewing a result, use `adopt-music` with comparative findings if a purpose-specific preference is useful. It requires a hash-bound passing listening review and playback review for loops/sequences. The choice saves both provider and model for the given purpose. Saved local choices apply to `auto` when local-only mode is effective; they do not override the ElevenLabs default with access. Saved cloud choices remain comparison evidence and do not silently pin an old version in new requests. Choosing a provider for one request does not require a fabricated listening/adoption record. Different styles/projects can keep different purpose keys (for example `mygame_exploration`). Explicit local-only mode still blocks cloud requests. Never change a running job's provider.

## Local licenses and provenance

Checked 2026-09-15: [ACE-Step 1.5's official model card](https://huggingface.co/ACE-Step/Ace-Step1.5) declares MIT and allows commercial generated music, without a revenue or platform-count limit. This is not a non-infringement guarantee for every output.

[Stable Audio 3 Small Music's license](https://huggingface.co/stabilityai/stable-audio-3-small-music/blob/main/LICENSE.md) permits limited commercial model use under the Community License, requires registration, and requires another license above USD 1 million annual revenue including applicable affiliates and revenue from other sources. Check the actual intended user/organization when selecting it commercially. These model-use conditions and rights to previously generated audio are distinct; do not assert that existing output ownership automatically disappears when revenue grows.

Once the relevant revenue conditions and model access have been established for a project, reuse that evidence. Revisit it when the organization, revenue situation or intended use materially changes.

For delivered music, preserve the actual model/weight revision or hashes and a dated copy of the relevant license/model-card evidence beside the generation provenance. Record the source URL and snapshot hash. Avoid assuming that a later model update has the same terms.

## Eleven Music eligibility

Check the terms for the actual generation service, model and plan. For ElevenCreative/plugin/API music, the [model-specific terms](https://elevenlabs.io/eleven-music-model-specific-terms) (updated 2026-05-26, checked 2026-09-15) cover v1/v2 model families including minor updates unless separately designated; selecting `music_v2_5` alone does not establish different rights. They exclude Studio Games from Self-Serve plans, including Creator, Pro and Business, and from Enterprise Music Lite. Section 5(g) defines Studio Games as games that are both monetized (sale, advertising or other monetization) and available through more than one platform. It is not a studio-size or USD-1-million revenue test. The public text does not clarify whether platform means an OS, hardware ecosystem or storefront; do not declare Steam-plus-another-store eligible without clarification of that actual release. Full Enterprise Music has broader media rights. A paid subscription alone does not settle this eligibility. A single-platform monetized game is not excluded by that definition alone, but applicable plan eligibility and other terms still matter.

The separate [ElevenMusic website/mobile service terms](https://elevenmusic.io/terms-of-use) were updated 2026-09-11. Sections 1(b)-(c) permit external commercial use of New Songs (generated without incorporating/referencing Uploaded Music or another user's identity): Free requires attribution, Pro does not; digital music streaming distribution requires creation on Pro. Adaptations remain restricted to that service. That public text does not contain the same Studio Games exclusion, and preserves creation-time output rights despite later plan/terms changes, subject to applicable supplemental terms. Its scope is elevenmusic.io and its mobile app. Do not apply it automatically to outputs from the ElevenCreative plugin/API or assume an ElevenLabs Creator plan is this separate service's Pro plan. Do not switch services or regenerate just to reinterpret an existing asset's license.

Preserve the applicable terms URL/date and service route beside the output. Generation and release eligibility are separate: missing release evidence does not block ordinary requested creation or private comparison. Keep unverified rights marked unverified and check the applicable actual-use conditions when making a release/integration decision. Do not repeatedly ask the same licensing question for each take or treat suspected documentation lag as an official confirmation.

In `audio-system.local.json`, `elevenlabs_music_eligible` plus `elevenlabs_music_evidence` records the checked purpose, plan/permission and source/date. These fields record evidence, not a license grant. Do not set them merely because an API key is present or a POST works. Local model licenses/access also require checking the actual model and use. Explain a concrete restriction if it affects the requested candidate and continue applicable alternatives.

For a narrower one-off use already established in the conversation, put `music_eligibility_evidence` in the music request (`auto` or `elevenlabs`) instead of broadening global settings. The plan and saved selection record either that evidence or `unverified`; this is not a generation gate. Record the actual purpose and source/date. A private comparison test record does not approve use in a released game; do not carry it into a release request as release permission.

API model/format details are in [providers.md](providers.md). Current source references: [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5), [Stable Audio 3](https://github.com/Stability-AI/stable-audio-3), [Eleven Music API](https://elevenlabs.io/docs/api-reference/music/compose).

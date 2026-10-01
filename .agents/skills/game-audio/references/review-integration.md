# Review and game integration

Use criteria grounded in the requested purpose. Inspect the actual delivered file, not just a provider preview or an earlier revision.

| Evidence | What it establishes | What it does not establish |
| --- | --- | --- |
| Hash/format/duration/peak/RMS/DC analysis | File identity and bounded numerical properties | Naturalness, acting, material identity, musical continuity |
| Actual listening with method and ranges | Audible findings in the reviewed coverage | Unheard takes, untested repetitions or every gameplay mix |
| Repeated preview at intended cadence | Seam/repetition/fatigue in that preview | Runtime randomization, spatial attenuation or concurrency behavior |
| Actual engine import/playback | Observed target integration behavior | Every platform/device or other engine |

The numerical analyzer reports sample peak, per-channel RMS/DC, near-full-scale sample count, the first/last samples above a -50 dBFS inspection threshold and boundary sample difference. It does not implement true-peak/loudness certification, beat detection or a quality score. Threshold crossing is not guaranteed to be the semantically meaningful contact/attack. `audition --target-lufs` uses FFmpeg preview normalization; do not generalize it into final mix approval.

For short-dialogue or postprocessing A/B tests, measure the rendered preview's actual integrated loudness and true peak; a requested `loudnorm` target alone does not establish matched playback. Prefer one constant gain per clip and a shared achievable loudness target, lowering the common target when peak headroom requires it. This avoids adding a second, unlabelled dynamic processor to an EQ/compression comparison. Keep the old preview and source immutable, use new preview paths, and record achieved levels separately from targets. Equal integrated loudness improves comparison control but does not guarantee identical perceived loudness or establish voice quality.

Review each requested take that will be delivered. Inspect onsets/tails for cuts, unwanted extra events, noise or metallic artifacts, perspective, identity consistency and suitability at the intended gain. Repetition review should include relevant spacing and overlap; BGM/ambience loops need multiple cycles. If the game mixes cues together, evaluate masking at the actual mix level.

Only an audio-capable perception tool or actual listener report establishes listening evidence. Playing/rendering a player for the user is not proof the agent heard it. ASR and spectral images are diagnostic aids. If listening is unavailable, deliver/play a preview, leave `listening: unreviewed` and state what remains for a listener. Do not silently turn user feedback on one take into approval of all variants.

The `review` command stores `audio_sha256`, statuses, method, listened ranges, evidence, findings and untested criteria in a sidecar; prior review records are preserved. New audio revisions begin unreviewed. Status `pass` cannot be inferred from empty warnings. Source hashes protect provenance, not aesthetic quality.

## Playback contract

Use the manifest's `playback` fields for the selected intent, 2D/3D placement, variation no-repeat, pitch/gain ranges, max voices, cooldown, sync anchor and notes. Defaults are neutral starting values. These are suggestions until an actual engine adapter implements them. No engine is chosen for an unknown target.

For requested integration, inspect the project's real events, mixer buses, import settings, asset conventions and target platforms. Preserve working project conventions. Register/trigger the new audio and verify the affected scene or operation. A WAV copying successfully does not establish playback correctness. Choose export sample rate, channel layout and runtime compression from the project's needs.

## 3D animation cues

Observe clip names, duration, contact poses/action times and existing animation events. Bind a sound to the intended action (foot contact, hit, latch or spell release), not an arbitrary evenly spaced time. Record clip identity/hash, event time in seconds, sound take/hash, emitter or attachment when observed, and any offset/cadence decisions. Recheck after animation or audio timing edits.

Keep mesh/rig generation in the 3D workflow; audio-only requests do not authorize regenerating or editing that asset. A cue sheet can be delivered without modifying an unknown engine. Cue metadata, a preview synchronized to animation and an event tested in-engine are different evidence. The core audio runtime does not automatically embed audio in GLB or create a target-engine adapter.

Delivery should identify intended files, why any variants exist, relevant playback settings, and the separate completed/unreviewed checks. Link or render playable audio where supported. Keep detailed receipts in the artifact rather than forcing implementation details into the game's UI.

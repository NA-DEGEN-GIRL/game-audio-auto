import uuid
from pathlib import Path

from .config import load_settings, save_settings
from .jobs import verify_manifest
from .models import GenerateRequest, MusicChoice, Review
from .storage import digest, now, read_json, write_json

CASES = {
    "exploration": "Instrumental fantasy exploration game music, warm woodwinds, soft strings, "
                   "restrained percussion, calm curiosity, steady 90 BPM, no vocals, "
                   "stable texture suitable for a repeating gameplay loop, no dramatic final cadence.",
    "combat": "Instrumental fantasy combat game music, tight percussion and rhythmic low strings, "
              "moderate intensity, clear recurring pulse at 120 BPM, no vocals, "
              "leave space for sound effects, stable texture suitable for a repeating gameplay loop.",
    "transition": "Instrumental fantasy game music, a calm opening developing into moderate tension "
                  "halfway through, strings and restrained percussion at 100 BPM, no vocals, "
                  "clear phrase boundaries suitable for editing exploration into combat.",
}
PROVIDERS = {"ace_step": "acestep-v15-turbo", "stable_audio": "medium", "elevenlabs": "music_v2_5"}


def create_plan(output: Path, duration=30, variants=2):
    if output.exists():
        raise ValueError("Benchmark directory already exists; choose a new path")
    if not 10 <= duration <= 120 or not 1 <= variants <= 5:
        raise ValueError("Initial benchmark uses 10–120 seconds and 1–5 takes per case/provider")
    output.mkdir(parents=True)
    cases = []
    for purpose, prompt in CASES.items():
        for provider, model in PROVIDERS.items():
            request = GenerateRequest(name=f"bgm_{purpose}_{provider}", kind="music", prompt=prompt,
                                      provider=provider, model=model, duration_seconds=duration,
                                      variants=variants, purpose=purpose,
                                      playback={"intent": "sequence" if purpose == "transition" else "loop"},
                                      acceptance=["No unintended vocals", "Fits gameplay without masking cues",
                                                  "Phrase and loop/transition continuity after local editing"])
            file = output / f"{purpose}-{provider}.json"
            write_json(file, request.model_dump())
            cases.append({"purpose": purpose, "provider": provider, "request": str(file),
                          "state": "not_run", "execution": "Select explicitly; this plan submits nothing"})
    result = {"created_at": now(), "duration_seconds": duration, "takes_per_case": variants,
              "cases": cases, "paid_jobs_submitted": 0,
              "criteria": ["timbre and artifacts", "prompt/style fit", "fatigue in repeated playback",
                           "loop seam", "editable phrase/transition", "gameplay masking", "latency/cost"],
              "rules": ["Use identical brief, duration and take count across compared candidates",
                        "Normalize listening previews only; preserve every original",
                        "Seeds are not comparable across providers; Eleven Music prompt mode has no seed",
                        "Record unavailable candidates and actual use eligibility; do not silently substitute"],
              "adoption": "Record comparative findings and a reviewed revision per purpose; no universal winner"}
    write_json(output / "benchmark.json", result)
    write_json(output / "scores.json", {"reviewer": "", "comparison_notes": "", "results": []})
    return result


def adopt(root: Path, purpose: str, revision: Path, take_number: int, evidence: str):
    if not purpose.strip() or not evidence.strip():
        raise ValueError("Adoption requires a purpose and comparative findings")
    manifest = verify_manifest(revision)
    if manifest.get("kind") != "music":
        raise ValueError("Adopt a music revision")
    if not 1 <= take_number <= len(manifest["takes"]):
        raise ValueError("Take number is out of range")
    take = manifest["takes"][take_number - 1]
    review_path = revision / take["review_file"]
    saved_review = read_json(review_path)
    review = Review.model_validate({k: v for k, v in saved_review.items() if k != "recorded_at"})
    if review.audio_sha256 != take["sha256"] or review.listening != "pass":
        raise ValueError("Adoption requires a passing listening review bound to this take")
    if manifest["playback"]["intent"] in ("loop", "sequence") and review.repetition != "pass":
        raise ValueError("Loop/transition adoption requires a passing playback review")
    provider = manifest["generator"]["provider"]
    model = manifest["generator"]["model"]
    if provider not in PROVIDERS:
        raise ValueError("Music provider is not identified; retain provenance through import")
    settings = load_settings(root)
    record = {"purpose": purpose, "provider": provider, "model": model,
              "revision": str(revision), "take": take_number,
              "audio_sha256": take["sha256"], "review_sha256": digest(review_path),
              "comparative_findings": evidence, "adopted_at": now()}
    # One history entry per decision; later choices do not erase evidence.
    decision = root / ".assets/music-decisions" / (uuid.uuid4().hex + ".json")
    write_json(decision, record)
    settings.music_defaults[purpose] = MusicChoice(provider=provider, model=model, evidence_record=str(decision))
    save_settings(root, settings)
    return record

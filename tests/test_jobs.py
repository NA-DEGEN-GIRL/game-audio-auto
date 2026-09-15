import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from game_audio.benchmark import adopt, create_plan
from game_audio.config import load_settings
from game_audio.jobs import get_job, record_review, run_job, saved_raw, submit, verify_manifest
from game_audio.models import EditRequest, GenerateRequest, ImportRequest, Review
from game_audio.storage import digest, job_path, read_json, write_json


def test_plugin_import_and_edit_preserve_source_parent_and_reviews(tmp_path, fixture_audio):
    result = submit(tmp_path, "import", ImportRequest(
        name="forest", source=str(fixture_audio), kind="music", provider="stable_audio", model="small-music",
        transport="plugin", purpose="exploration", playback={"intent": "loop", "sync_anchor_seconds": 0.1}))
    assert result["status"] == "completed"
    parent = Path(result["revision"])
    original = verify_manifest(parent)
    original_hash = digest(parent / "manifest.json")
    source = parent / original["takes"][0]["file"]
    child_job = submit(tmp_path, "edit", EditRequest(name="forest", source=str(source),
                                                    start_seconds=0.1, gain_db=-3))
    assert child_job["status"] == "completed"
    child = Path(child_job["revision"])
    edited = verify_manifest(child)
    assert child != parent and edited["parent"]["revision"] == str(parent)
    assert edited["generator"]["model"] == "small-music" and edited["kind"] == "music"
    assert edited["playback"]["intent"] == "loop" and edited["playback"]["sync_anchor_seconds"] is None
    assert digest(parent / "manifest.json") == original_hash
    assert digest(fixture_audio) == original["source"]["sha256"]
    assert read_json(child / edited["takes"][0]["review_file"])["listening"] == "unreviewed"
    assert run_job(tmp_path, child_job["id"])["status"] == "completed"


def test_review_requires_observed_ranges_and_rejects_wrong_revision(tmp_path, fixture_audio):
    result = submit(tmp_path, "import", ImportRequest(name="audio", source=str(fixture_audio), kind="sfx"))
    revision = Path(result["revision"])
    take = verify_manifest(revision)["takes"][0]
    with pytest.raises(ValueError, match="actual method"):
        Review(audio_sha256=take["sha256"], listening="pass")
    with pytest.raises(ValueError, match="does not match"):
        record_review(revision, 1, Review(audio_sha256="0" * 64))
    with pytest.raises(ValueError, match="exceeds"):
        record_review(revision, 1, Review(audio_sha256=take["sha256"], listening="pass",
                                         method="test validator only", listened_ranges_seconds=[(0, 2)]))


def test_failed_edit_keeps_partial_out_of_completed_library(tmp_path, fixture_audio):
    job = submit(tmp_path, "edit", EditRequest(name="bad", source=str(fixture_audio), start_seconds=2))
    assert job["status"] == "failed"
    revision = Path(job["revision"])
    assert not (revision / "manifest.json").exists()
    assert Path(job["source"]["snapshot"]).is_file()


def test_downloaded_provider_output_recovers_without_key_or_second_post(tmp_path, fixture_audio):
    revision = tmp_path / ".assets/audio/recover/r1"
    take = revision / "take-001"
    take.mkdir(parents=True)
    import shutil
    raw = take / "provider.wav"
    shutil.copy2(fixture_audio, raw)
    write_json(take / "remote.json", {"state": "downloaded", "file": raw.name,
                                      "sha256": digest(raw), "model": "eleven_text_to_sound_v2"})
    request = GenerateRequest(name="recover", kind="sfx", prompt="A recovered sound", duration_seconds=1)
    job_id = "j" + "a" * 24
    write_json(revision / "request.json", request.model_dump())
    write_json(job_path(tmp_path, job_id), {"id": job_id, "status": "failed", "revision": str(revision),
               "request": request.model_dump(), "operation": "generate", "completed_takes": 0,
               "selection": {"provider": "elevenlabs", "model": "eleven_text_to_sound_v2"}})
    assert run_job(tmp_path, job_id)["status"] == "completed"
    assert saved_raw(take, "remote.json")[0] == raw
    assert verify_manifest(revision)["takes"][0]["provenance"]["sha256"] == digest(raw)


def test_bgm_adoption_requires_review_and_keeps_model(tmp_path, fixture_audio):
    comparison = create_plan(tmp_path / "benchmark", variants=1)
    assert len(comparison["cases"]) == 9 and comparison["paid_jobs_submitted"] == 0
    job = submit(tmp_path, "import", ImportRequest(name="bgm", source=str(fixture_audio), kind="music",
                   provider="stable_audio", model="small-music", playback={"intent": "loop"}))
    revision = Path(job["revision"])
    with pytest.raises(ValueError, match="passing listening"):
        adopt(tmp_path, "exploration", revision, 1, "Synthetic validation of the decision workflow")
    take = verify_manifest(revision)["takes"][0]
    review = Review(audio_sha256=take["sha256"], listening="pass", repetition="pass",
                    method="Synthetic test of evidence storage; not real sound quality approval",
                    listened_ranges_seconds=[(0, 1)], evidence=["Synthetic maintenance fixture"])
    record_review(revision, 1, review)
    decision = adopt(tmp_path, "exploration", revision, 1, "Synthetic fixture; no provider quality comparison")
    assert decision["model"] == "small-music"
    assert load_settings(tmp_path).music_defaults["exploration"].model == "small-music"


def test_async_worker_finishes_and_can_be_queried(tmp_path, fixture_audio):
    job = submit(tmp_path, "edit", EditRequest(name="background", source=str(fixture_audio), gain_db=-3),
                 background=True)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        result = get_job(tmp_path, job["id"])
        if result["status"] in ("completed", "failed"):
            break
        time.sleep(0.1)
    assert result["status"] == "completed", result
    assert verify_manifest(Path(result["revision"]))["takes"]


def test_skill_wrapper_resolves_runtime_from_another_working_directory(tmp_path):
    root = Path(__file__).resolve().parents[1]
    wrapper = root / ".agents/skills/game-audio/scripts/audioctl.py"
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    result = subprocess.run([sys.executable, str(wrapper), "--help"], cwd=tmp_path, env=environment,
                            capture_output=True, text=True, encoding="utf-8", check=False)
    assert result.returncode == 0 and "benchmark-plan" in result.stdout

import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from game_audio.cli import parser
from game_audio.config import plan
from game_audio.dialogue_finishing import adaptive_threshold, loudness
from game_audio.jobs import run_job, submit, verify_manifest
from game_audio.models import FinishDialogueRequest, GenerateRequest, ImportRequest, Settings
from game_audio.storage import digest, read_json, write_json


def dialogue(**changes):
    return GenerateRequest(name="hero", kind="dialogue", provider="gemini", prompt="준비됐어요.",
                           voice_id="Kore", **changes)


def fake_provider(monkeypatch, fixture_audio):
    calls = []

    def generate(root, request, selection, take, settings, pending_takes):
        calls.append(take)
        raw = take / "provider.wav"
        shutil.copy2(fixture_audio, raw)
        return raw, {"state": "generated", "provider": "synthetic-test-fixture", "file": raw.name,
                     "sha256": digest(raw)}

    monkeypatch.setenv("GEMINI_API_KEY", "test-only")
    monkeypatch.setattr("game_audio.jobs.generate_take", generate)
    return calls


def test_routing_exposes_density_only_for_gemini_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-only")
    assert plan(tmp_path, dialogue(), Settings())["dialogue_processing"] == "density"
    assert plan(tmp_path, dialogue(dialogue_processing="none"), Settings())["dialogue_processing"] == "none"
    auto = dialogue().model_copy(update={"provider": "auto"})
    selected = plan(tmp_path, auto, Settings())
    assert selected["provider"] == "elevenlabs" and selected["dialogue_processing"] == "none"
    assert plan(tmp_path, auto.model_copy(update={"dialogue_processing": "density"}),
                Settings())["dialogue_processing"] == "density"
    with pytest.raises(ValueError, match="Dialogue processing"):
        GenerateRequest(name="invalid", kind="sfx", prompt="bang", duration_seconds=1,
                        dialogue_processing="density")


def test_default_generation_creates_immutable_density_child_and_keeps_raw(tmp_path, monkeypatch, fixture_audio):
    calls = fake_provider(monkeypatch, fixture_audio)
    original_hash = digest(fixture_audio)
    job = submit(tmp_path, "generate", dialogue(export={"sample_rate": 24000, "channels": "mono"}))
    assert job["status"] == "completed", job
    assert len(calls) == 1 and len(job["finishing_jobs"]) == 1
    raw_revision = Path(job["revision"])
    raw_manifest = verify_manifest(raw_revision)
    child_revision = Path(job["delivery_revisions"][0])
    assert child_revision != raw_revision
    child = verify_manifest(child_revision)
    assert child["operation"] == "finish-dialogue" and child["kind"] == "dialogue"
    assert child["generator"] == raw_manifest["generator"]
    assert child["parent"]["revision"] == str(raw_revision)
    assert child["parent"]["manifest_sha256"] == digest(raw_revision / "manifest.json")
    assert child["source"]["sha256"] == raw_manifest["takes"][0]["sha256"]
    assert digest(raw_revision / "take-001/provider.wav") == original_hash == digest(fixture_audio)
    take = child["takes"][0]
    analysis = take["analysis"]
    assert analysis["sample_rate"] == 24000 and analysis["channels"] == 1
    assert analysis["frames"] == raw_manifest["takes"][0]["analysis"]["frames"]
    assert analysis["near_full_scale_samples"] == 0
    recipe = read_json(child_revision / "take-001/finishing.json")
    assert recipe["compressor"]["ratio"] == 2 and recipe["compressor"]["attack_ms"] == 18
    assert recipe["target_lufs"] is None and recipe["headroom_gain_db"] <= 0
    assert recipe["output_loudness"]["true_peak_dbtp"] <= -1.2
    assert recipe["source_sha256"] == child["source"]["sha256"]
    assert recipe["output_sha256"] == take["sha256"]
    monkeypatch.delenv("GEMINI_API_KEY")
    assert run_job(tmp_path, job["id"])["delivery_revisions"] == job["delivery_revisions"]
    assert len(calls) == 1
    # Hash-bound finishing settings are part of verification, not editable review metadata.
    recipe["eq"]["presence_db"] = 0
    write_json(child_revision / "take-001/finishing.json", recipe)
    with pytest.raises(ValueError, match="recipe changed"):
        run_job(tmp_path, job["id"])


def test_none_opt_out_does_not_finish_or_create_children(tmp_path, monkeypatch, fixture_audio):
    calls = fake_provider(monkeypatch, fixture_audio)
    monkeypatch.setattr("game_audio.jobs.finish_dialogue", lambda *_: pytest.fail("Unexpected finishing"))
    job = submit(tmp_path, "generate", dialogue(dialogue_processing="none"))
    assert job["status"] == "completed" and len(calls) == 1
    assert job["delivery_revisions"] == [job["revision"]]
    assert "finishing_jobs" not in job


def test_failed_finishing_resumes_local_child_without_regeneration(tmp_path, monkeypatch, fixture_audio):
    from game_audio.dialogue_finishing import finish_dialogue

    calls = fake_provider(monkeypatch, fixture_audio)

    def broken(*_):
        raise ValueError("Synthetic local processing failure")

    monkeypatch.setattr("game_audio.jobs.finish_dialogue", broken)
    failed = submit(tmp_path, "generate", dialogue())
    assert failed["status"] == "failed" and len(calls) == 1
    assert (Path(failed["revision"]) / "manifest.json").is_file()
    assert len(failed["finishing_jobs"]) == 1
    monkeypatch.setattr("game_audio.jobs.finish_dialogue", finish_dialogue)
    monkeypatch.delenv("GEMINI_API_KEY")
    recovered = run_job(tmp_path, failed["id"])
    assert recovered["status"] == "completed", recovered
    assert len(calls) == 1 and recovered["finishing_jobs"] == failed["finishing_jobs"]
    assert len(list((tmp_path / ".assets/jobs").glob("j*.json"))) == 2
    verify_manifest(Path(recovered["delivery_revisions"][0]))


def test_local_finishing_preserves_parent_and_rejects_stacking(tmp_path, fixture_audio):
    imported = submit(tmp_path, "import", ImportRequest(name="line", source=str(fixture_audio),
                                                       kind="dialogue"))
    parent = Path(imported["revision"])
    source = parent / verify_manifest(parent)["takes"][0]["file"]
    request = FinishDialogueRequest(name="line", source=str(source), parent_revision=str(parent),
                                    export={"sample_rate": 48000, "channels": "stereo"})
    assert parser().parse_args(["finish-dialogue", "spec.json", "--async"]).background
    job = submit(tmp_path, "finish-dialogue", request)
    assert job["status"] == "completed", job
    child = Path(job["revision"])
    manifest = verify_manifest(child)
    assert manifest["playback"] == verify_manifest(parent)["playback"]
    assert manifest["takes"][0]["analysis"]["frames"] == 48000
    with pytest.raises(ValueError, match="already finished"):
        submit(tmp_path, "finish-dialogue", request.model_copy(update={
            "source": str(child / manifest["takes"][0]["file"]), "parent_revision": str(child)}))


@pytest.mark.parametrize("duration", [0.01, 1.0])
def test_short_or_silent_input_has_finite_recipe_and_no_invented_loudness(tmp_path, duration):
    source = tmp_path / "silent.wav"
    sf.write(source, np.zeros(round(24000 * duration)), 24000, subtype="PCM_16")
    assert adaptive_threshold(source) == -30
    job = submit(tmp_path, "finish-dialogue", FinishDialogueRequest(name="silence", source=str(source),
                  export={"sample_rate": 24000, "channels": "mono"}))
    assert job["status"] == "completed", job
    revision = Path(job["revision"])
    manifest = verify_manifest(revision)
    assert manifest["takes"][0]["analysis"]["frames"] == round(24000 * duration)
    assert loudness(revision / manifest["takes"][0]["file"])["true_peak_dbtp"] is None


def test_true_peak_headroom_is_checked_after_export_resampling(tmp_path):
    source = tmp_path / "hot.wav"
    time = np.arange(24000 * 2) / 24000
    sf.write(source, 0.98 * np.sin(time * 2 * np.pi * 2300), 24000, subtype="FLOAT")
    job = submit(tmp_path, "finish-dialogue", FinishDialogueRequest(name="hot", source=str(source),
                  low_shelf_db=0, presence_db=4.5, export={"sample_rate": 48000, "channels": "stereo"}))
    assert job["status"] == "completed", job
    revision = Path(job["revision"])
    take = verify_manifest(revision)["takes"][0]
    assert take["analysis"]["frames"] == 96000 and take["analysis"]["channels"] == 2
    assert take["analysis"]["near_full_scale_samples"] == 0
    assert loudness(revision / take["file"])["true_peak_dbtp"] <= -1.2


def test_auto_density_preserves_hot_resampled_parent_as_float(tmp_path, monkeypatch):
    source = tmp_path / "hot-provider.wav"
    time = np.arange(24000) / 24000
    sf.write(source, 0.98 * np.sign(np.sin(time * 2 * np.pi * 1000)), 24000, subtype="PCM_16")
    calls = fake_provider(monkeypatch, source)
    job = submit(tmp_path, "generate", dialogue(export={"sample_rate": 48000, "subtype": "PCM_24"}))
    assert job["status"] == "completed", job
    assert len(calls) == 1
    parent = Path(job["revision"])
    raw_take = verify_manifest(parent)["takes"][0]
    assert sf.info(parent / raw_take["file"]).subtype == "FLOAT"
    assert raw_take["analysis"]["peak_dbfs"] > 0
    assert raw_take["provenance"]["generation_export"]["subtype"] == "FLOAT"
    child = Path(job["delivery_revisions"][0])
    take = verify_manifest(child)["takes"][0]
    assert sf.info(child / take["file"]).subtype == "PCM_24"
    assert take["analysis"]["near_full_scale_samples"] == 0
    assert loudness(child / take["file"])["true_peak_dbtp"] <= -1.2

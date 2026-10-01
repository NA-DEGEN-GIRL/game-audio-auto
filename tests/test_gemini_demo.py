import importlib.util
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from game_audio import audio
from game_audio.storage import digest, job_path, read_json, write_json


@pytest.fixture
def demo():
    spec = importlib.util.spec_from_file_location(
        "gemini_demo", Path(__file__).parents[1] / "scripts/gemini_character_demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mock_ready(demo, root, monkeypatch):
    manifest = root / "mock-profile.json"
    write_json(manifest, {"voice_id": "voice_character", "model": demo.MODEL})
    profile = {"voice_id": "voice_character", "manifest": str(manifest),
               "sha256": digest(manifest), "expired": False}
    monkeypatch.setattr(demo, "_preflight", lambda *args: [])
    monkeypatch.setattr(demo, "create_voice", lambda *args: profile)
    monkeypatch.setattr(demo, "show_voice", lambda *args: profile)
    return profile


def save_job(root, request, index=1):
    record = {"id": "j" + f"{index:024x}", "status": "running", "operation": "generate",
              "request": request.model_dump()}
    write_json(job_path(root, record["id"]), record)
    return record


def test_prepare_is_persistent_and_keeps_exact_words_with_provider_controls(demo, tmp_path):
    directory = tmp_path / "demo"
    initial = demo.prepare(tmp_path, directory, "observed-eleven-voice")
    assert len(initial["lines"]) == 8
    assert demo.prepare(tmp_path, directory, "observed-eleven-voice") == initial
    first = read_json(directory / "gemini-neutral.json")
    paired = read_json(directory / "elevenlabs-neutral.json")
    assert first["prompt"] == demo.COMMON_TEXT and first["voice_id"] is None
    assert paired["prompt"].endswith(demo.COMMON_TEXT) and paired["instruction"] == ""
    assert paired["voice_id"] == "observed-eleven-voice"
    assert paired["model"] == "eleven_v3"
    with pytest.raises(ValueError, match="different comparison voice"):
        demo.prepare(tmp_path, directory, "another-voice")
    (directory / "gemini-neutral.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="specification changed"):
        demo.prepare(tmp_path, directory)


def test_missing_key_leaves_preparation_complete_without_submission_or_mode_change(demo, tmp_path, monkeypatch):
    directory = tmp_path / "demo"
    demo.prepare(tmp_path, directory)
    before = digest(directory / "state.json")
    monkeypatch.setattr(demo, "create_voice", lambda *args: pytest.fail("No voice POST allowed"))
    monkeypatch.setattr(demo, "submit", lambda *args, **kwargs: pytest.fail("No TTS POST allowed"))
    result = demo.generate(tmp_path, directory)
    assert result["status"] == "blocked" and result["blockers"]
    assert digest(directory / "state.json") == before
    assert not (tmp_path / "audio-system.local.json").exists()


def test_repeated_generate_keeps_one_job_per_prepared_line(demo, tmp_path, monkeypatch):
    directory = tmp_path / "demo"
    demo.prepare(tmp_path, directory, "observed-eleven")
    profile = mock_ready(demo, tmp_path, monkeypatch)
    requests = []

    def submit(root, operation, request, background):
        requests.append(request)
        assert operation == "generate" and background
        return save_job(root, request, len(requests))

    monkeypatch.setattr(demo, "submit", submit)
    demo.generate(tmp_path, directory)
    again = demo.generate(tmp_path, directory)
    assert len(requests) == 8 and len(again["jobs"]) == 8
    assert all(request.voice_id == profile["voice_id"] for request in requests if request.provider == "gemini")


def test_archived_design_does_not_hide_missing_synthesis_key(demo, tmp_path, monkeypatch):
    directory = tmp_path / "demo"
    demo.prepare(tmp_path, directory)
    monkeypatch.setattr(demo, "plan_voice", lambda *args: {"ready": True, "blockers": [], "remote_calls": 0})
    monkeypatch.setattr(demo, "submit", lambda *args, **kwargs: pytest.fail("No synthesis without key"))
    before = digest(directory / "state.json")
    result = demo.generate(tmp_path, directory)
    assert result["status"] == "blocked" and digest(directory / "state.json") == before


def test_crash_after_job_persisted_before_helper_receives_id_recovers_without_duplicate(demo, tmp_path, monkeypatch):
    directory = tmp_path / "demo"
    demo.prepare(tmp_path, directory)
    mock_ready(demo, tmp_path, monkeypatch)
    calls = []

    def submit(root, operation, request, background):
        calls.append(request.name)
        record = save_job(root, request, len(calls))
        if len(calls) == 1:
            raise RuntimeError("Simulated lost return after durable job write")
        return record

    monkeypatch.setattr(demo, "submit", submit)
    with pytest.raises(RuntimeError):
        demo.generate(tmp_path, directory)
    demo.generate(tmp_path, directory)
    assert len(calls) == 4 and len(set(calls)) == 4
    assert all(item.get("job_id") for item in read_json(directory / "state.json")["lines"])


def test_crash_before_job_persisted_stops_for_reconciliation(demo, tmp_path, monkeypatch):
    directory = tmp_path / "demo"
    demo.prepare(tmp_path, directory)
    mock_ready(demo, tmp_path, monkeypatch)
    calls = []

    def submit(*args, **kwargs):
        calls.append("attempt")
        raise RuntimeError("Simulated interruption without durable job ID")

    monkeypatch.setattr(demo, "submit", submit)
    with pytest.raises(RuntimeError):
        demo.generate(tmp_path, directory)
    with pytest.raises(ValueError, match="No duplicate was submitted"):
        demo.generate(tmp_path, directory)
    assert calls == ["attempt"]


def test_generate_reuses_legacy_jobs_without_retroactive_finishing(demo, tmp_path, monkeypatch):
    directory = tmp_path / "demo"
    demo.prepare(tmp_path, directory)
    mock_ready(demo, tmp_path, monkeypatch)
    calls = []

    def submit(root, operation, request, background):
        calls.append(request.name)
        record = save_job(root, request, len(calls))
        record["request"].pop("dialogue_processing")
        record["status"] = "completed"
        write_json(job_path(root, record["id"]), record)
        return record

    monkeypatch.setattr(demo, "submit", submit)
    demo.generate(tmp_path, directory)
    state = read_json(directory / "state.json")
    hashes = {i["job_id"]: digest(job_path(tmp_path, i["job_id"])) for i in state["lines"]}
    demo.generate(tmp_path, directory)
    assert len(calls) == 4
    assert all(digest(job_path(tmp_path, job_id)) == before for job_id, before in hashes.items())
    first = read_json(directory / state["lines"][0]["bound_spec"])
    assert demo._recover_submission(tmp_path, first)["id"] == state["lines"][0]["job_id"]
    assert not demo._same_generation_request(first, {**first, "dialogue_processing": "none"})


@pytest.mark.parametrize("density", [False, True])
def test_collect_preserves_old_catalog_and_archives_text_style_and_identity(
        demo, tmp_path, monkeypatch, fixture_audio, density):
    directory = tmp_path / "demo"
    state = demo.prepare(tmp_path, directory)
    profile = mock_ready(demo, tmp_path, monkeypatch)
    state["voice"] = profile
    line = state["lines"][0]
    bound = read_json(directory / line["spec"])
    bound["voice_id"] = profile["voice_id"]
    bound_path = directory / "bound.json"
    write_json(bound_path, bound)
    line.update(bound_spec=bound_path.name, bound_sha256=digest(bound_path), job_id="j" + "1" * 24)
    write_json(directory / "state.json", state)
    revision = tmp_path / "revision"
    revision.mkdir()
    source = revision / "master.wav"
    source.write_bytes(fixture_audio.read_bytes())
    manifest = {"request": bound, "generator": {"provider": "gemini", "model": demo.MODEL},
                "takes": [{"file": "master.wav", "sha256": digest(source)}]}
    write_json(revision / "manifest.json", manifest)
    record = {"id": line["job_id"], "status": "completed", "revision": str(revision)}
    manifests = {revision: manifest}
    if density:
        child = tmp_path / "finished"
        child.mkdir()
        child_source = child / "master.wav"
        samples, rate = sf.read(source)
        sf.write(child_source, samples * .5, rate, subtype="PCM_24")
        child_manifest = {"operation": "finish-dialogue", "request": {"preset": "density"},
                          "parent": {"revision": str(revision),
                                     "manifest_sha256": digest(revision / "manifest.json")},
                          "generator": manifest["generator"],
                          "takes": [{"file": "master.wav", "sha256": digest(child_source)}]}
        write_json(child / "manifest.json", child_manifest)
        manifests[child] = child_manifest
        record.update(finishing_jobs=["j" + "2" * 24], delivery_revisions=[str(child)])
    monkeypatch.setattr(demo, "get_job", lambda *args: record)
    monkeypatch.setattr(demo, "verify_manifest", lambda path: manifests[path])
    monkeypatch.setattr(demo, "_matched", lambda src, dest, ffmpeg: dest.write_bytes(src.read_bytes()))
    catalog_path = tmp_path / ".assets/deliveries/catalog.json"
    original = {"providers": [{"id": "elevenlabs", "name": "ElevenLabs", "categories": ["legendary"]}],
                "tracks": [{"id": "old-track", "category": "legendary", "keep": "unchanged"}]}
    write_json(catalog_path, original)
    report = demo.collect(tmp_path, directory, catalog_path)
    assert report["collected"] == 1 and report["status"] == "pending"
    catalog = read_json(catalog_path)
    assert catalog["tracks"][0] == original["tracks"][0] and len(catalog["tracks"]) == 2
    assert catalog["tracks"][1]["category"] == "dialogue"
    sidecar = Path(report["delivery"]) / (catalog["tracks"][1]["id"] + ".json")
    saved = read_json(sidecar)
    assert saved["text"] == demo.COMMON_TEXT and saved["profile_sha256"] == profile["sha256"]
    assert saved["voice_id"] == profile["voice_id"] and saved["listening"] == "unreviewed"
    assert saved["dialogue_processing"] == ("density" if density else "none")
    assert saved["source_revision"] == str(revision)
    if density:
        assert saved["sha256"] == digest(child_source) != digest(source)
        assert "밀도 강화" in catalog["tracks"][1]["title"]
    demo.collect(tmp_path, directory, catalog_path)
    assert len(read_json(catalog_path)["tracks"]) == 2


def test_collect_finishes_downloaded_clipping_take_locally_once_preserving_failed_job(
        demo, tmp_path, monkeypatch):
    directory = tmp_path / "demo"
    state = demo.prepare(tmp_path, directory)
    state["voice"] = mock_ready(demo, tmp_path, monkeypatch)
    item = state["lines"][0]
    expected = read_json(directory / item["spec"])
    expected["voice_id"] = state["voice"]["voice_id"]
    bound = directory / "bound-neutral.json"
    write_json(bound, expected)
    item.update(bound_spec=bound.name, bound_sha256=digest(bound), job_id="j" + "f" * 24)
    write_json(directory / "state.json", state)
    revision = tmp_path / ".assets/audio/original/r1"
    take = revision / "take-001"
    take.mkdir(parents=True)
    raw = take / "provider.wav"
    # Emulate samples above full scale after resampling. No external codec is involved in this fixture.
    data = (1.1 * np.sin(np.arange(48000) * 2 * np.pi * 200 / 48000)).astype(np.float32)
    sf.write(raw, data, 48000, subtype="FLOAT")
    write_json(take / "response.json", {"id": "mock-original-response"})
    write_json(take / "remote.json", {"state": "downloaded", "file": raw.name, "sha256": digest(raw),
                                      "response_file": "response.json",
                                      "response_sha256": digest(take / "response.json")})
    write_json(revision / "request.json", expected)
    job = {"id": item["job_id"], "status": "failed", "operation": "generate", "revision": str(revision),
           "request": expected, "selection": {"provider": "gemini", "model": demo.MODEL},
           "error": {"type": "ValueError", "message": "Source would clip integer PCM; import as FLOAT "
                                                      "then edit its gain"}}
    path = job_path(tmp_path, job["id"])
    write_json(path, job)
    originals = {file: digest(file) for file in (path, raw, take / "remote.json", take / "response.json")}
    monkeypatch.setattr(audio, "decode", lambda source, output, *args: shutil.copy2(source, output))
    monkeypatch.setattr(demo, "_matched", lambda source, target, ffmpeg: shutil.copy2(source, target))
    report = demo.collect(tmp_path, directory)
    assert report["collected"] == 1
    assert report["jobs"][0]["status"] == "completed_local_finish"
    assert report["jobs"][0]["source_job_status"] == "failed"
    after = read_json(directory / "state.json")
    recovery = after["lines"][0]["local_finish"]
    assert recovery["gain_db"] < -1 and recovery["source_raw_sha256"] == digest(raw)
    finished = demo.get_job(tmp_path, recovery["edit_job_id"])
    exported = demo.verify_manifest(Path(finished["revision"]))
    assert exported["generator"]["provider"] == "gemini"
    assert exported["takes"][0]["analysis"]["peak_dbfs"] == pytest.approx(-1, abs=0.001)
    assert exported["takes"][0]["analysis"]["near_full_scale_samples"] == 0
    assert len(list((tmp_path / ".assets/jobs").glob("j*.json"))) == 3
    demo.collect(tmp_path, directory)
    assert len(list((tmp_path / ".assets/jobs").glob("j*.json"))) == 3
    assert all(digest(file) == expected_hash for file, expected_hash in originals.items())
    sidecar = next(Path(report["delivery"]).glob("*.json"))
    assert read_json(sidecar)["local_finish"]["source_response_sha256"] == digest(take / "response.json")

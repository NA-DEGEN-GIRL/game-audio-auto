import base64
import io
import json
import wave
from pathlib import Path

import httpx
import pytest

from game_audio.cli import parser
from game_audio.config import capabilities, gemini_credential, plan
from game_audio.elevenlabs import UnknownSubmission
from game_audio.gemini import Gemini, recover_saved, speech_body
from game_audio.jobs import generate_take, run_job, submit, verify_manifest
from game_audio.models import GenerateRequest, Settings
from game_audio.storage import digest, job_path, read_json, write_json


def dialogue(**changes):
    return GenerateRequest.model_validate({"name": "hero", "kind": "dialogue", "provider": "gemini",
                                           "prompt": "물러서! <short pause> 내가 막을게.",
                                           "instruction": "urgent but controlled", "voice_id": "Kore", **changes})


def wav_bytes():
    # Synthetic silence verifies transport/container handling, never perceptual TTS quality.
    stream = io.BytesIO()
    with wave.open(stream, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(b"\x00\x00" * 2400)
    return stream.getvalue()


def response_body():
    return {"id": "interaction-test", "model": "gemini-3.8-flash-tts", "status": "completed",
            "usage": {"total_input_tokens": 20, "total_output_tokens": 32},
            "steps": [{"type": "user_input", "content": [{"type": "text", "text": "test"}]},
                      {"type": "model_output", "content": [{"type": "audio", "mime_type": "audio/wav",
                                                            "data": base64.b64encode(wav_bytes()).decode()}]}]}


def client_for(root, monkeypatch, handler):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-gemini-key")
    return Gemini(root, Settings(), transport=httpx.MockTransport(handler))


def test_gemini_credential_precedence_presence_and_no_secret_output(tmp_path, monkeypatch):
    private = tmp_path / ".secrets/gemini_api_key"
    private.parent.mkdir()
    private.write_text("test-file-key\n", encoding="utf-8-sig")
    settings = Settings()
    assert gemini_credential(tmp_path, settings) == ("test-file-key", "key_file")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    assert gemini_credential(tmp_path, settings) == ("test-gemini-key", "environment:GEMINI_API_KEY")
    report = capabilities(tmp_path, settings)
    assert report["gemini"]["key_present"] and not report["gemini"]["account_checked"]
    assert "test-gemini-key" not in json.dumps(report)
    monkeypatch.delenv("GEMINI_API_KEY")
    assert gemini_credential(tmp_path, settings)[0] == "test-google-key"
    monkeypatch.delenv("GOOGLE_API_KEY")
    custom = tmp_path / "custom-key"
    custom.write_text("test-override", encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY_FILE", str(custom))
    assert gemini_credential(tmp_path, settings)[0] == "test-override"
    custom.write_text("two words", encoding="utf-8")
    with pytest.raises(ValueError, match="one key"):
        gemini_credential(tmp_path, settings)


def test_gemini_explicit_only_local_policy_budget_and_existing_default(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    selected = plan(tmp_path, dialogue(), Settings())
    assert selected["provider"] == "gemini" and selected["model"] == "gemini-3.8-flash-tts"
    assert selected["ready"] and selected["remote_calls"] == 1 and selected["transport"] == "api"
    assert selected["effective_mode"] == "auto"  # Missing ElevenLabs key must not block explicit Gemini.
    assert plan(tmp_path, dialogue(provider="auto", instruction=""), Settings())["provider"] == "qwen"
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-eleven-key")
    assert plan(tmp_path, dialogue(provider="auto", instruction=""), Settings())["provider"] == "elevenlabs"
    assert plan(tmp_path, dialogue(model="gemini-3.8-flash-lite-tts"), Settings())["ready"]
    with pytest.raises(ValueError, match="Only-local"):
        plan(tmp_path, dialogue(), Settings(mode="only_local"))
    capped = plan(tmp_path, dialogue(max_credits=100), Settings())
    assert not capped["ready"] and "ElevenLabs units" in " ".join(capped["blockers"])
    for changes, match in (({"duration_seconds": 2}, "cannot guarantee"),
                           ({"voice_mode": "design"}, "separate action"),
                           ({"voice_mode": "clone", "reference_audio": "reference.wav"}, "separate action"),
                           ({"model": "gemini-2.5-flash-preview-tts"}, "Select gemini"),
                           ({"kind": "sfx", "instruction": "", "voice_id": None,
                             "duration_seconds": 2}, "does not support")):
        with pytest.raises(ValueError, match=match):
            plan(tmp_path, dialogue(**changes), Settings())


def test_missing_gemini_key_blocks_without_falling_back(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-eleven")
    selected = plan(tmp_path, dialogue(), Settings())
    assert not selected["ready"] and selected["provider"] == "gemini"
    assert any("GEMINI_API_KEY" in blocker for blocker in selected["blockers"])


def test_explicit_gemini_does_not_read_an_unrelated_invalid_eleven_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "an invalid unrelated value")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    assert plan(tmp_path, dialogue(), Settings())["ready"]


def test_official_rest_body_receipt_response_provenance_and_reuse(tmp_path, monkeypatch):
    calls = []
    request = dialogue(seed=99)

    def handler(req):
        calls.append(req)
        assert req.url.host == "generativelanguage.googleapis.com"
        assert req.url.path == "/v1beta/interactions" and req.method == "POST"
        assert req.headers["x-goog-api-key"] == "test-only-gemini-key"
        receipt = read_json(tmp_path / "remote.json")
        assert receipt["state"] == "submitting" and receipt["remote_posts"] == 1
        body = json.loads(req.content)
        assert body["model"] == "gemini-3.8-flash-tts" and body["stream"] is False
        assert body["input"] == [{"type": "user_input", "content": [{"type": "text",
                "text": request.prompt, "annotations": [{"type": "speech_metadata",
                                                          "style": request.instruction}]}]}]
        assert body["generation_config"] == {"speech_config": [{"voice": "Kore"}]}
        assert "seed" not in json.dumps(body) and "language_code" not in json.dumps(body)
        return httpx.Response(200, json=response_body(), headers={"x-request-id": "request-test",
                "x-goog-api-key": "test-only-gemini-key", "set-cookie": "do-not-save"})

    client = client_for(tmp_path, monkeypatch, handler)
    try:
        raw, receipt = client.generate(request, {"model": "gemini-3.8-flash-tts"}, tmp_path)
        assert raw.read_bytes() == wav_bytes() and receipt["response_model"] == "gemini-3.8-flash-tts"
        assert receipt["interaction_id"] == "interaction-test" and receipt["usage"]["total_output_tokens"] == 32
        assert receipt["headers"] == {"x-request-id": "request-test"}
        assert receipt["seed_sent"] is False and receipt["raw_format"]["sample_rate"] == 24000
        assert client.generate(request, {"model": "gemini-3.8-flash-tts"}, tmp_path)[0] == raw
        assert len(calls) == 1
        for path in tmp_path.glob("*.json"):
            assert "test-only-gemini-key" not in path.read_text(encoding="utf-8")
            assert "do-not-save" not in path.read_text(encoding="utf-8")
    finally:
        client.close()


@pytest.mark.parametrize("failure", ["timeout", "server", "rejected", "malformed", "no_audio", "bad_audio"])
def test_failed_submission_is_never_reposted_or_downgraded(tmp_path, monkeypatch, failure):
    calls = []

    def handler(req):
        calls.append(req)
        if failure == "timeout":
            raise httpx.ReadTimeout("test-only-gemini-key echoed error", request=req)
        if failure in ("server", "rejected"):
            return httpx.Response(503 if failure == "server" else 403,
                                  json={"error": "test-only-gemini-key echoed body"})
        if failure == "malformed":
            return httpx.Response(200, content=b"test-only-gemini-key invalid JSON")
        if failure == "no_audio":
            return httpx.Response(200, json={"steps": []})
        data = response_body()
        data["steps"][1]["content"][0]["data"] = "invalid base64!"
        return httpx.Response(200, json=data)

    client = client_for(tmp_path, monkeypatch, handler)
    try:
        with pytest.raises((UnknownSubmission, ValueError)) as error:
            client.generate(dialogue(), {"model": "gemini-3.8-flash-tts"}, tmp_path)
        assert "test-only-gemini-key" not in str(error.value)
        with pytest.raises((UnknownSubmission, ValueError)):
            client.generate(dialogue(), {"model": "gemini-3.8-flash-tts"}, tmp_path)
        assert len(calls) == 1
        assert "test-only-gemini-key" not in (tmp_path / "remote.json").read_text(encoding="utf-8")
    finally:
        client.close()


def test_response_received_resumes_decode_without_credentials_or_network(tmp_path):
    write_json(tmp_path / "response.json", response_body())
    write_json(tmp_path / "remote.json", {"state": "response_received", "provider": "gemini",
               "model": "gemini-3.8-flash-tts", "response_file": "response.json",
               "response_sha256": digest(tmp_path / "response.json")})
    raw, receipt = recover_saved(tmp_path)
    assert raw.read_bytes() == wav_bytes() and receipt["state"] == "downloaded"
    assert recover_saved(tmp_path)[0] == raw
    write_json(tmp_path / "response.json", {"changed": True})
    with pytest.raises(ValueError, match="response changed"):
        recover_saved(tmp_path)


def test_gemini_job_export_preserves_remote_model_and_resumes_without_key(tmp_path, monkeypatch):
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(200, json=response_body())

    def factory(root, settings):
        return Gemini(root, settings, transport=httpx.MockTransport(handler))

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("game_audio.jobs.Gemini", factory)
    record = submit(tmp_path, "generate", dialogue())
    assert record["status"] == "completed", record
    revision = Path(record["revision"])
    manifest = verify_manifest(revision)
    assert manifest["generator"] == {"provider": "gemini", "model": "gemini-3.8-flash-tts", "transport": "api"}
    assert manifest["takes"][0]["provenance"]["usage"]["total_input_tokens"] == 20
    assert read_json(revision / "take-001/review.json")["listening"] == "unreviewed"
    monkeypatch.delenv("GEMINI_API_KEY")
    assert run_job(tmp_path, record["id"])["status"] == "completed" and len(calls) == 1


def test_job_unknown_submission_stays_reconciliation_on_resume(tmp_path, monkeypatch):
    calls = []

    def handler(req):
        calls.append(req)
        raise httpx.ReadTimeout("unknown", request=req)

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("game_audio.jobs.Gemini", lambda root, settings: Gemini(
        root, settings, transport=httpx.MockTransport(handler)))
    record = submit(tmp_path, "generate", dialogue())
    assert record["status"] == "needs_reconciliation"
    assert run_job(tmp_path, record["id"])["status"] == "needs_reconciliation" and len(calls) == 1


def test_saved_response_job_recovery_does_not_need_key(tmp_path):
    revision = tmp_path / ".assets/audio/hero/recovered"
    take = revision / "take-001"
    take.mkdir(parents=True)
    write_json(take / "response.json", response_body())
    write_json(take / "remote.json", {"state": "response_received", "provider": "gemini",
               "model": "gemini-3.8-flash-tts", "response_file": "response.json",
               "response_sha256": digest(take / "response.json")})
    request = dialogue()
    job_id = "j" + "b" * 24
    write_json(revision / "request.json", request.model_dump())
    write_json(job_path(tmp_path, job_id), {"id": job_id, "status": "failed", "revision": str(revision),
               "request": request.model_dump(), "operation": "generate", "completed_takes": 0,
               "selection": {"provider": "gemini", "model": "gemini-3.8-flash-tts"}})
    assert run_job(tmp_path, job_id)["status"] == "completed"
    assert verify_manifest(revision)["takes"][0]["provenance"]["interaction_id"] == "interaction-test"


def test_read_only_voice_and_model_commands_omit_audio_data(tmp_path, monkeypatch):
    calls = []

    def handler(req):
        calls.append(req)
        assert req.method == "GET"
        if req.url.path.endswith("/models/gemini-3.8-flash-tts"):
            return httpx.Response(200, json={"name": "models/gemini-3.8-flash-tts"})
        voice = {"id": "voice_mock", "display_name": "Mock hero", "sample_audio": {
            "mime_type": "audio/wav", "data": "large-base64-do-not-print"}}
        if req.url.path == "/v1beta/voices":
            assert req.url.params["page_token"] == "page two"
            return httpx.Response(200, json={"voices": [voice], "next_page_token": "next"})
        return httpx.Response(200, json=voice)

    client = client_for(tmp_path, monkeypatch, handler)
    try:
        assert client.voices("page two")["voices"][0]["id"] == "voice_mock"
        assert client.voice("voice_mock")["sample_audio"]["available"]
        assert "large-base64" not in json.dumps(client.voice("voice_mock"))
        assert client.model()["synthesis_verified"] is False
        assert all(req.method == "GET" for req in calls)
    finally:
        client.close()
    for command in ("gemini-voices", "gemini-model"):
        assert parser().parse_args([command]).command == command
    assert parser().parse_args(["voice-plan", "hero.json"]).spec == Path("hero.json")


def test_low_level_only_local_guard_never_posts(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    client = Gemini(tmp_path, Settings(mode="only_local"), transport=httpx.MockTransport(
        lambda _: pytest.fail("Only-local request attempted network")))
    try:
        with pytest.raises(ValueError, match="Only-local"):
            client.request_json("POST", "/v1beta/voices", {})
    finally:
        client.close()


def test_bound_voice_profile_change_blocks_unsubmitted_take(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("game_audio.character_voices.voice_for_synthesis",
                        lambda root, voice_id: {"voice_id": voice_id, "sha256": "a" * 64})
    request = dialogue(voice_id="voice_hero")
    selected = plan(tmp_path, request, Settings())
    monkeypatch.setattr("game_audio.character_voices.voice_for_synthesis",
                        lambda root, voice_id: {"voice_id": voice_id, "sha256": "b" * 64})
    monkeypatch.setattr("game_audio.jobs.Gemini", lambda *_: pytest.fail("Changed voice reached network"))
    with pytest.raises(ValueError, match="voice profile changed"):
        generate_take(tmp_path, request, selected, tmp_path, Settings(), 1)
    assert not (tmp_path / "remote.json").exists()


@pytest.mark.parametrize("crash", [KeyboardInterrupt, OSError])
def test_complete_response_saved_before_receipt_update_recovers_without_repost(tmp_path, monkeypatch, crash):
    calls = []
    data = response_body()
    data["model"] = "models/gemini-3.8-flash-tts"
    data["steps"] = data["steps"][1:]  # Real Interactions responses need not echo the input.

    def handler(req):
        calls.append(req)
        return httpx.Response(200, json=data)

    original_write = write_json

    def crash_before_receipt(path, value):
        if path.name == "remote.json" and value.get("state") == "response_received":
            raise crash("Simulated crash after response.json was atomically saved")
        original_write(path, value)

    client = client_for(tmp_path, monkeypatch, handler)
    monkeypatch.setattr("game_audio.gemini.write_json", crash_before_receipt)
    try:
        with pytest.raises((KeyboardInterrupt, UnknownSubmission)):
            client.generate(dialogue(), {"model": "gemini-3.8-flash-tts"}, tmp_path)
        assert (tmp_path / "response.json").is_file()
        assert read_json(tmp_path / "remote.json")["state"] in ("submitting", "unknown")
        saved_hash = digest(tmp_path / "response.json")
        monkeypatch.setattr("game_audio.gemini.write_json", original_write)
        monkeypatch.delenv("GEMINI_API_KEY")
        raw, receipt = recover_saved(tmp_path)
        assert raw.read_bytes() == wav_bytes()
        assert receipt["recovered_response_receipt_gap"] is True
        assert receipt["response_sha256"] == saved_hash
        assert receipt["interaction_id"] == "interaction-test"
        assert recover_saved(tmp_path)[0] == raw and len(calls) == 1
    finally:
        client.close()


@pytest.mark.parametrize("damage", ["model", "transcript", "gibberish", "truncated_wav", "bound_hash"])
def test_orphan_response_mismatch_or_damage_never_reposts(tmp_path, monkeypatch, damage):
    record = {"state": "submitting", "provider": "gemini", "endpoint": "/v1beta/interactions",
              "model": "gemini-3.8-flash-tts", "remote_posts": 1,
              "request": speech_body(dialogue(), "gemini-3.8-flash-tts")}
    data = response_body()
    if damage == "model":
        data["model"] = "gemini-3.8-flash-lite-tts"
    elif damage == "truncated_wav":
        data["steps"] = data["steps"][1:]
        data["steps"][0]["content"][0]["data"] = base64.b64encode(wav_bytes()[:-100]).decode()
    elif damage == "bound_hash":
        record["response_sha256"] = "a" * 64
    write_json(tmp_path / "remote.json", record)
    if damage == "gibberish":
        (tmp_path / "response.json").write_text("incomplete {", encoding="utf-8")
    else:
        write_json(tmp_path / "response.json", data)
    client = client_for(tmp_path, monkeypatch, lambda _: pytest.fail("Recovery attempted a new POST"))
    try:
        with pytest.raises((UnknownSubmission, ValueError)):
            client.generate(dialogue(), {"model": "gemini-3.8-flash-tts"}, tmp_path)
        assert not (tmp_path / "provider.wav").exists()
        assert read_json(tmp_path / "remote.json")["state"] == "submitting"
    finally:
        client.close()


def test_response_without_attempt_receipt_requires_reconciliation(tmp_path, monkeypatch):
    write_json(tmp_path / "response.json", response_body())
    client = client_for(tmp_path, monkeypatch, lambda _: pytest.fail("Orphan response led to a paid POST"))
    try:
        with pytest.raises(UnknownSubmission, match="without its attempt receipt"):
            client.generate(dialogue(), {"model": "gemini-3.8-flash-tts"}, tmp_path)
    finally:
        client.close()

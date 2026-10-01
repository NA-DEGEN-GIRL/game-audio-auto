import base64
import io
import json
import wave
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from game_audio import character_voices as voices
from game_audio.config import plan
from game_audio.elevenlabs import UnknownSubmission
from game_audio.gemini import Gemini
from game_audio.models import GenerateRequest, Settings
from game_audio.storage import read_json, write_json


def design():
    return {"name": "gregory-v1", "display_name": "광란의 그레고리", "gender": "male",
            "prompt": "An adult theatrical baritone with a dry texture and measured Korean diction."}


def provider_response(expired=False):
    sample = io.BytesIO()
    with wave.open(sample, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\x00\x00\x01\x00" * 1200)
    return {"id": "voice_fictional123", "model": "gemini-3.8-flash-tts", "type": "prompted",
            "expire_time": (datetime.now(UTC) + timedelta(days=-1 if expired else 300)).isoformat(),
            "sample_audio": {"mime_type": "audio/wav", "data": base64.b64encode(sample.getvalue()).decode()},
            "usage": {"total_tokens": 123}}


def mock_api(tmp_path, monkeypatch, handler):
    monkeypatch.setenv("GEMINI_API_KEY", "private-test-gemini-key")
    monkeypatch.setattr(voices, "Gemini", lambda root, settings:
                        Gemini(root, settings, transport=httpx.MockTransport(handler)))


def test_design_created_once_receipt_first_and_archive_redacted(tmp_path, monkeypatch):
    calls = []
    response = provider_response()
    directory = tmp_path / ".assets/voices/gregory-v1"

    def handler(request):
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.url.path == "/v1beta/voices" and request.method == "POST"
        assert read_json(directory / "remote.json")["state"] == "submitting"
        assert read_json(directory / "request.json")["request"]["name"] == "gregory-v1"
        payload = json.loads(request.content)
        assert payload["store"] is True
        assert payload["voice"]["type"] == "prompted"
        assert payload["voice"]["language_code"] == "ko-KR"
        assert payload["voice"]["prompted"]["input"] == design()["prompt"]
        calls.append(request)
        return httpx.Response(200, json=response)

    mock_api(tmp_path, monkeypatch, handler)
    first = voices.create_voice(tmp_path, design())
    second = voices.create_voice(tmp_path, design())
    assert first == second and len(calls) == 1
    assert first["voice_id"] == response["id"] and first["expired"] is False
    assert first["listening"] == "unreviewed"
    assert response["sample_audio"]["data"] not in json.dumps(first)
    assert "private-test-gemini-key" not in "".join(p.read_text() for p in directory.glob("*.json"))
    assert read_json(directory / "response.json")["usage"] == response["usage"]
    planned = voices.plan_voice(tmp_path, design())
    assert planned["remote_calls"] == 0 and planned["ready"]
    bound = voices.voice_for_synthesis(tmp_path, first["voice_id"])
    assert bound["sha256"] == first["sha256"]
    assert voices.voice_for_synthesis(tmp_path, "Kore") is None


@pytest.mark.parametrize("name", ["../oops", "gregory/another", "CON", "con", "nul", "com1"])
def test_character_names_reject_unsafe_paths(tmp_path, name):
    with pytest.raises(ValueError):
        voices.plan_voice(tmp_path, {**design(), "name": name})
    assert not (tmp_path / ".assets").exists()


def test_missing_key_and_only_local_are_blocked_before_attempt(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No network client should be created")

    monkeypatch.setattr(voices, "Gemini", forbidden)
    planned = voices.plan_voice(tmp_path, design())
    assert not planned["ready"] and "GEMINI_API_KEY" in planned["blockers"][0]
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        voices.create_voice(tmp_path, design())
    monkeypatch.setenv("GEMINI_API_KEY", "private-test-gemini-key")
    write_json(tmp_path / "audio-system.local.json", {"mode": "only_local"})
    with pytest.raises(ValueError, match="Only-local"):
        voices.create_voice(tmp_path, design())
    assert not (tmp_path / ".assets/voices/gregory-v1/remote.json").exists()


@pytest.mark.parametrize("failure", ["timeout", "rejected", "server"])
def test_uncertain_and_rejected_creation_never_reposted(tmp_path, monkeypatch, failure):
    calls = []

    def handler(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("sensitive response private-test-gemini-key", request=request)
        return httpx.Response(403 if failure == "rejected" else 503,
                              json={"error": "sensitive response private-test-gemini-key"})

    mock_api(tmp_path, monkeypatch, handler)
    with pytest.raises((ValueError, UnknownSubmission)) as captured:
        voices.create_voice(tmp_path, design())
    assert "private-test-gemini-key" not in str(captured.value)
    with pytest.raises(UnknownSubmission):
        voices.create_voice(tmp_path, design())
    assert len(calls) == 1
    receipt = read_json(tmp_path / ".assets/voices/gregory-v1/remote.json")
    assert receipt["state"] == ("rejected" if failure == "rejected" else "unknown")
    assert "private-test-gemini-key" not in json.dumps(receipt)
    assert voices.plan_voice(tmp_path, design())["state"] == "needs_reconciliation"


def test_saved_response_archives_after_local_failure_without_credentials_or_post(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=provider_response())

    mock_api(tmp_path, monkeypatch, handler)
    original_archive = voices._archive_response
    monkeypatch.setattr(voices, "_archive_response", lambda *args: (_ for _ in ()).throw(OSError("disk issue")))
    with pytest.raises(OSError):
        voices.create_voice(tmp_path, design())
    assert voices.plan_voice(tmp_path, design())["state"] == "archive_pending"
    monkeypatch.setattr(voices, "_archive_response", original_archive)
    monkeypatch.delenv("GEMINI_API_KEY")
    write_json(tmp_path / "audio-system.local.json", {"mode": "only_local"})
    result = voices.create_voice(tmp_path, design())
    assert result["voice_id"] == "voice_fictional123" and len(calls) == 1


def test_name_cannot_be_reused_with_changed_brief(tmp_path, monkeypatch):
    mock_api(tmp_path, monkeypatch, lambda request: httpx.Response(200, json=provider_response()))
    voices.create_voice(tmp_path, design())
    with pytest.raises(ValueError, match="different design"):
        voices.create_voice(tmp_path, {**design(), "prompt": "A different character voice"})


@pytest.mark.parametrize("filename", ["sample.wav", "response.json"])
def test_changed_archive_rejected_for_reuse_and_synthesis(tmp_path, monkeypatch, filename):
    mock_api(tmp_path, monkeypatch, lambda request: httpx.Response(200, json=provider_response()))
    result = voices.create_voice(tmp_path, design())
    path = tmp_path / ".assets/voices/gregory-v1" / filename
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="changed"):
        voices.create_voice(tmp_path, design())
    with pytest.raises(ValueError, match="changed"):
        voices.voice_for_synthesis(tmp_path, result["voice_id"])


def test_expired_voice_stays_archived_but_cannot_synthesize(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=provider_response(expired=True))

    mock_api(tmp_path, monkeypatch, handler)
    result = voices.create_voice(tmp_path, design())
    assert result["expired"] is True
    assert voices.create_voice(tmp_path, design()) == result
    assert not voices.plan_voice(tmp_path, design())["ready"]
    with pytest.raises(ValueError, match="expired"):
        voices.voice_for_synthesis(tmp_path, result["voice_id"])
    request = GenerateRequest(name="expired-dialogue", kind="dialogue", provider="gemini",
                              prompt="다시 만났군.", voice_id=result["voice_id"])
    with pytest.raises(ValueError, match="expired"):
        plan(tmp_path, request, Settings())
    assert len(calls) == 1


def test_prefixed_provider_model_is_normalized_and_original_preserved(tmp_path, monkeypatch):
    response = provider_response()
    response["model"] = "models/gemini-3.8-flash-tts"
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=response)

    mock_api(tmp_path, monkeypatch, handler)
    result = voices.create_voice(tmp_path, design())
    assert result["model"] == "gemini-3.8-flash-tts"
    assert result["response_model"] == response["model"]
    assert voices.create_voice(tmp_path, design()) == result
    assert voices.voice_for_synthesis(tmp_path, result["voice_id"]) == result
    assert len(calls) == 1


def test_incomplete_provider_preview_preserves_response_for_recovery(tmp_path, monkeypatch):
    response = provider_response()
    response["sample_audio"]["data"] = "not-valid-base64"
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=response)

    mock_api(tmp_path, monkeypatch, handler)
    for _ in range(2):
        with pytest.raises(ValueError, match="valid WAV"):
            voices.create_voice(tmp_path, design())
    assert len(calls) == 1
    assert (tmp_path / ".assets/voices/gregory-v1/response.json").exists()
    assert not (tmp_path / ".assets/voices/gregory-v1/manifest.json").exists()

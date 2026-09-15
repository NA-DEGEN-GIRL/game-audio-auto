import json

import httpx
import pytest

from game_audio.config import plan
from game_audio.elevenlabs import ElevenLabs, UnknownSubmission
from game_audio.models import GenerateRequest, Settings
from game_audio.storage import read_json, write_json


def make_client(root, monkeypatch, handler):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-only-key")
    return ElevenLabs(root, Settings(), transport=httpx.MockTransport(handler))


def request():
    return GenerateRequest(name="sfx", kind="sfx", prompt="A wooden door closing", duration_seconds=1)


def test_receipt_is_saved_before_post_and_download_reused(tmp_path, monkeypatch):
    posts = []

    def handler(req):
        assert read_json(tmp_path / "remote.json")["state"] == "submitting"
        assert req.url.host == "api.elevenlabs.io"
        posts.append(req)
        return httpx.Response(200, content=b"mock-audio", headers={"request-id": "r1", "character-cost": "40"})

    client = make_client(tmp_path, monkeypatch, handler)
    try:
        first = client.generate(request(), {"model": "eleven_text_to_sound_v2"}, tmp_path, "mp3_44100_128")
        second = client.generate(request(), {"model": "eleven_text_to_sound_v2"}, tmp_path, "mp3_44100_128")
        assert first[0] == second[0] and len(posts) == 1
        assert "test-only-key" not in (tmp_path / "remote.json").read_text()
    finally:
        client.close()


@pytest.mark.parametrize("failure", ["timeout", "server", "empty", "rejected"])
def test_uncertain_or_rejected_attempt_is_never_reposted(tmp_path, monkeypatch, failure):
    calls = []

    def handler(req):
        calls.append(req)
        if failure == "timeout":
            raise httpx.ReadTimeout("mock timeout", request=req)
        return httpx.Response({"server": 503, "empty": 200, "rejected": 422}[failure], content=b"")

    client = make_client(tmp_path, monkeypatch, handler)
    try:
        with pytest.raises((UnknownSubmission, ValueError)):
            client.generate(request(), {"model": "eleven_text_to_sound_v2"}, tmp_path, "mp3_44100_128")
        with pytest.raises(UnknownSubmission):
            client.generate(request(), {"model": "eleven_text_to_sound_v2"}, tmp_path, "mp3_44100_128")
        assert len(calls) == 1
    finally:
        client.close()


def test_history_recovery_requires_identity_not_only_repeated_text(tmp_path, monkeypatch):
    record = {"state": "unknown", "endpoint": "/v1/sound-generation", "request-id": "original",
              "model": "eleven_text_to_sound_v2", "request": {"text": request().prompt}}
    write_json(tmp_path / "remote.json", record)
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(200, json={"request_id": "other", "model_id": record["model"],
                                         "text": request().prompt})

    client = make_client(tmp_path, monkeypatch, handler)
    try:
        with pytest.raises(ValueError, match="request ID"):
            client.recover_history(tmp_path, "different-history")
        assert len(calls) == 1 and all(req.method == "GET" for req in calls)
    finally:
        client.close()


@pytest.mark.parametrize("model", [None, "music_v2_5", "music_v2", "music_v1"])
def test_music_model_reaches_official_api_and_saved_provenance(tmp_path, monkeypatch, model):
    calls = []
    expected_model = model or "music_v2_5"
    music = GenerateRequest(name="boss", kind="music", provider="elevenlabs", model=model,
                            prompt="Menacing instrumental boss battle in D minor at 156 BPM",
                            duration_seconds=32.125)

    def handler(req):
        calls.append(req)
        assert req.method == "POST" and req.url.path == "/v1/music"
        assert req.url.host == "api.elevenlabs.io"
        assert req.url.params["output_format"] == "auto"
        assert req.headers["xi-api-key"] == "test-only-key"
        assert json.loads(req.content) == {
            "prompt": music.prompt, "model_id": expected_model,
            "music_length_ms": 32125, "force_instrumental": True,
        }  # No seed: the prompt API rejects it.
        pending = read_json(tmp_path / "remote.json")
        assert pending["state"] == "submitting" and pending["model"] == expected_model
        return httpx.Response(200, content=b"mock-music", headers={
            "content-type": "audio/mpeg", "song-id": "song-v25", "request-id": "music-request",
        })

    client = make_client(tmp_path, monkeypatch, handler)
    try:
        selected = plan(tmp_path, music, Settings(
            elevenlabs_music_eligible=True, elevenlabs_music_evidence="mock test only"))
        assert selected["transport"] == "api" and selected["model"] == expected_model
        raw, receipt = client.generate(music, selected, tmp_path, "mp3_44100_128")
        assert raw.read_bytes() == b"mock-music"
        assert receipt["song-id"] == "song-v25" and receipt["request-id"] == "music-request"
        assert receipt["model"] == expected_model and receipt["seed_sent"] is False
        assert client.generate(music, selected, tmp_path, "mp3_44100_128")[0] == raw
        assert len(calls) == 1
    finally:
        client.close()


def test_music_v25_rejection_never_downgrades_or_reposts(tmp_path, monkeypatch):
    calls = []

    def handler(req):
        calls.append(json.loads(req.content)["model_id"])
        return httpx.Response(422, json={"detail": "model unavailable"})

    client = make_client(tmp_path, monkeypatch, handler)
    music = GenerateRequest(name="boss", kind="music", provider="elevenlabs", model="music_v2_5",
                            prompt="Dark instrumental boss battle", duration_seconds=32)
    try:
        with pytest.raises(ValueError, match="HTTP 422"):
            client.generate(music, {"model": "music_v2_5"}, tmp_path, "auto")
        with pytest.raises(UnknownSubmission):
            client.generate(music, {"model": "music_v2_5"}, tmp_path, "auto")
        assert calls == ["music_v2_5"]
        assert read_json(tmp_path / "remote.json")["state"] == "rejected"
    finally:
        client.close()

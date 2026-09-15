import sys

import pytest

from game_audio.config import credential, effective_mode, plan
from game_audio.models import GenerateRequest, LocalBackend, MusicChoice, Settings


def request(**changes):
    return GenerateRequest.model_validate({"name": "door", "kind": "sfx", "prompt": "A wooden door closing",
                                           "duration_seconds": 2, **changes})


def test_missing_key_routes_local_without_pretending_backend_ready(tmp_path):
    settings = Settings()
    result = plan(tmp_path, request(), settings)
    assert result["provider"] == "stable_audio" and result["remote_calls"] == 0
    assert not result["ready"]
    assert effective_mode(tmp_path, settings) == "only_local"


def test_key_and_explicit_local_are_independent(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-only-not-a-real-key")
    assert plan(tmp_path, request(), Settings())["provider"] == "elevenlabs"
    local = Settings(mode="only_local", local_backends={"stable_audio": LocalBackend(python=sys.executable)})
    assert plan(tmp_path, request(), local)["provider"] == "stable_audio"
    with pytest.raises(ValueError, match="blocks all remote"):
        plan(tmp_path, request(provider="elevenlabs"), local)


def test_private_file_and_budget(tmp_path):
    private = tmp_path / ".secrets/elevenlabs_api_key"
    private.parent.mkdir()
    private.write_text("test-only-key\n", encoding="utf-8")
    assert credential(tmp_path, Settings())[1] == "key_file"
    result = plan(tmp_path, request(variants=3, max_credits=200), Settings())
    assert not result["ready"] and result["estimated_credits"] == 240
    private.write_text("two lines\nnot a key", encoding="utf-8")
    with pytest.raises(ValueError, match="one key"):
        credential(tmp_path, Settings())


@pytest.mark.parametrize("has_key", [False, True])
def test_bgm_default_uses_cloud_with_access_and_keeps_explicit_local_choices(tmp_path, monkeypatch, has_key):
    if has_key:
        monkeypatch.setenv("ELEVENLABS_API_KEY", "test-only-key")
    if has_key:
        selected = plan(tmp_path, request(kind="music", duration_seconds=60), Settings())
        assert (selected["provider"], selected["model"]) == ("elevenlabs", "music_v2_5")
        assert selected["ready"] and selected["remote_calls"] == 1
    else:
        with pytest.raises(ValueError, match="Choose a local BGM provider"):
            plan(tmp_path, request(kind="music", duration_seconds=60), Settings())
    for provider, model in (("ace_step", "acestep-v15-turbo"), ("stable_audio", "small-music")):
        result = plan(tmp_path, request(kind="music", duration_seconds=60, provider=provider), Settings())
        assert (result["provider"], result["model"], result["remote_calls"]) == (provider, model, 0)
        assert not result["ready"]  # Missing local setup does not switch to a paid provider.


def test_bgm_preserves_adopted_local_model(tmp_path):
    music = request(kind="music", duration_seconds=30, purpose="exploration")
    settings = Settings(music_defaults={"exploration": MusicChoice(
        provider="stable_audio", model="small-music", evidence_record="decision.json")})
    result = plan(tmp_path, music, settings)
    assert result["model"] == "small-music"
    with pytest.raises(ValueError, match="category"):
        plan(tmp_path, request(provider="stable_audio", model="small-music"), settings)


@pytest.mark.parametrize("saved_provider,saved_model", [
    ("elevenlabs", "music_v2"), ("stable_audio", "small-music"), ("ace_step", "acestep-v15-turbo")])
def test_new_cloud_default_takes_priority_over_old_adopted_preferences(
        tmp_path, monkeypatch, saved_provider, saved_model):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-only-key")
    settings = Settings(elevenlabs_music_eligible=True, elevenlabs_music_evidence="test evidence",
                        music_defaults={"boss": MusicChoice(
                            provider=saved_provider, model=saved_model, evidence_record="decision.json")})
    music = request(kind="music", duration_seconds=60, purpose="boss")
    selected = plan(tmp_path, music, settings)
    assert selected["model"] == "music_v2_5" and selected["remote_calls"] == 1
    if saved_provider != "elevenlabs":
        local = plan(tmp_path, music, settings.model_copy(update={"mode": "only_local"}))
        assert local["model"] == saved_model and local["remote_calls"] == 0
    else:
        with pytest.raises(ValueError, match="Choose a local BGM provider"):
            plan(tmp_path, music, settings.model_copy(update={"mode": "only_local"}))


def test_music_generation_does_not_claim_unverified_release_rights(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-only-key")
    result = plan(tmp_path, request(kind="music", duration_seconds=30), Settings())
    assert result["ready"] and result["provider"] == "elevenlabs"
    assert result["music_eligibility"]["status"] == "unverified"
    assert result["music_eligibility"]["evidence"] == ""


def test_request_music_evidence_is_scoped_and_cannot_override_local_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-only-key")
    settings = Settings()
    music = request(kind="music", provider="elevenlabs", duration_seconds=60,
                    music_eligibility_evidence="Mock private listening comparison only; not release permission")
    assert plan(tmp_path, music, settings)["model"] == "music_v2_5"
    assert not settings.elevenlabs_music_eligible and not settings.elevenlabs_music_evidence
    assert plan(tmp_path, music, settings)["music_eligibility"]["status"] == "recorded"
    assert plan(tmp_path, music.model_copy(update={"music_eligibility_evidence": ""}),
                settings)["music_eligibility"]["status"] == "unverified"
    automatic = GenerateRequest.model_validate({**music.model_dump(), "provider": "auto"})
    assert plan(tmp_path, automatic, settings)["music_eligibility"]["status"] == "recorded"
    with pytest.raises(ValueError, match="blocks all remote"):
        plan(tmp_path, music, Settings(mode="only_local"))
    with pytest.raises(ValueError, match="ElevenLabs music"):
        request(music_eligibility_evidence="Not applicable to effects")


def test_overlong_sfx_is_rejected_before_submission_but_local_prompt_is_unrestricted(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-only-key")
    with pytest.raises(ValueError, match="450 characters"):
        plan(tmp_path, request(prompt="a" * 451), Settings())
    assert plan(tmp_path, request(prompt="a" * 450), Settings())["ready"]
    assert plan(tmp_path, request(prompt="a" * 451, provider="stable_audio"), Settings())["remote_calls"] == 0


def test_music_api_constraints_are_checked_before_submission(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-only-key")
    settings = Settings(elevenlabs_music_eligible=True, elevenlabs_music_evidence="mock test only")
    music = request(kind="music", provider="elevenlabs", duration_seconds=32, prompt="a" * 4100)
    selected = plan(tmp_path, music, settings)
    assert selected["ready"] and selected["model"] == "music_v2_5"
    with pytest.raises(ValueError, match="4100 characters"):
        plan(tmp_path, music.model_copy(update={"prompt": "a" * 4101}), settings)
    for alias in ("eleven_music_v2", "eleven_music_v2_5"):
        with pytest.raises(ValueError, match="API model ID"):
            plan(tmp_path, music.model_copy(update={"model": alias}), settings)
    capped = plan(tmp_path, music.model_copy(update={"max_credits": 100}), settings)
    assert not capped["ready"] and "budget" in capped["blockers"][0]
    with pytest.raises(ValueError, match="blocks all remote"):
        plan(tmp_path, music, settings.model_copy(update={"mode": "only_local"}))
    assert plan(tmp_path, music.model_copy(update={"provider": "ace_step", "prompt": "a" * 4101}),
                settings)["remote_calls"] == 0

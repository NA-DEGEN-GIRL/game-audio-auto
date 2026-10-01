import os
import shutil
from pathlib import Path

from .models import GenerateRequest, Settings
from .storage import read_json, resolve, write_json


def load_settings(root: Path):
    path = root / "audio-system.local.json"
    return Settings.model_validate(read_json(path)) if path.exists() else Settings()


def save_settings(root: Path, settings: Settings):
    write_json(root / "audio-system.local.json", settings.model_dump())


def credential(root: Path, settings: Settings):
    # Deliberately do not search unrelated files, shell history or credential stores.
    for name in ("ELEVENLABS_API_KEY", "ELEVEN_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            if any(c.isspace() for c in value):
                raise ValueError(f"{name} contains whitespace; fix its value privately")
            return value, "environment:" + name
    path = resolve(root, os.environ.get("ELEVENLABS_API_KEY_FILE") or settings.elevenlabs_key_file)
    if path.is_file():
        value = path.read_text(encoding="utf-8-sig").strip()
        if value:
            if any(c.isspace() for c in value):
                raise ValueError("The ElevenLabs key file must contain one key only")
            return value, "key_file"
    return None, None


def effective_mode(root: Path, settings: Settings):
    if settings.mode == "only_local":
        return "only_local"
    return "auto" if credential(root, settings)[0] else "only_local"


def gemini_credential(root: Path, settings: Settings):
    # Explicit Gemini requests have their own credential, independent of ElevenLabs.
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            if any(c.isspace() for c in value):
                raise ValueError(f"{name} contains whitespace; fix its value privately")
            return value, "environment:" + name
    path = resolve(root, os.environ.get("GEMINI_API_KEY_FILE") or settings.gemini_key_file)
    if path.is_file():
        value = path.read_text(encoding="utf-8-sig").strip()
        if value:
            if any(c.isspace() for c in value):
                raise ValueError("The Gemini key file must contain one key only")
            return value, "key_file"
    return None, None


def capabilities(root: Path, settings: Settings):
    key, source = credential(root, settings)
    gemini_key, gemini_source = gemini_credential(root, settings)
    local = {}
    for provider in ("stable_audio", "qwen", "ace_step"):
        backend = settings.local_backends.get(provider)
        local[provider] = {
            "configured": backend is not None,
            "python_exists": bool(backend and resolve(root, backend.python).is_file()),
            "inference_verified": False,
            "note": "Configuration/file presence alone does not verify models or inference",
        }
    return {
        "root": str(root), "configured_mode": settings.mode, "effective_mode": effective_mode(root, settings),
        "elevenlabs": {"key_present": bool(key), "key_source": source,
                       "key_prompt": settings.key_prompt, "account_checked": False,
                       "music_eligible": settings.elevenlabs_music_eligible},
        "gemini": {"key_present": bool(gemini_key), "key_source": gemini_source,
                   "explicit_selection_only": True, "account_checked": False,
                   "generation_allowed": settings.mode != "only_local" and bool(gemini_key)},
        "effective_mode_note": "Auto routing follows ElevenLabs availability; explicitly selected Gemini "
                               "uses its own key unless configured_mode is only_local",
        "local": local, "ffmpeg": settings.ffmpeg or shutil.which("ffmpeg"),
        "listening": "Requires an actual audio-capable reviewer; analysis is not listening",
    }


def select_provider(root: Path, request: GenerateRequest, settings: Settings):
    mode = settings.mode if request.provider == "gemini" else effective_mode(root, settings)
    provider = request.provider
    adopted_model = None
    reason = "User/request selected provider"
    if provider == "auto":
        if mode == "auto":
            provider, reason = "elevenlabs", "ElevenLabs-first default with an available key"
        elif request.kind == "music":
            choice = settings.music_defaults.get(request.purpose)
            if choice is not None and choice.provider != "elevenlabs":
                provider, adopted_model = choice.provider, choice.model
                reason = "Saved local BGM choice for the requested purpose"
            else:
                raise ValueError("Choose a local BGM provider (ace_step or stable_audio) for this brief; "
                                 "only-local mode applies and neither local model has a fixed priority")
        else:
            provider = "qwen" if request.kind == "dialogue" else "stable_audio"
            reason = "Only-local mode (explicit preference or no ElevenLabs key)"
    if provider == "gemini" and settings.mode == "only_local":
        raise ValueError("Only-local mode blocks Gemini remote generation; select auto mode first")
    if provider == "elevenlabs" and mode == "only_local":
        raise ValueError("Only-local mode blocks all remote generation; configure a key and auto mode first")
    allowed = {"elevenlabs": {"sfx", "ambience", "dialogue", "music"},
               "gemini": {"dialogue"},
               "stable_audio": {"sfx", "ambience", "music"}, "qwen": {"dialogue"}, "ace_step": {"music"}}
    if request.kind not in allowed[provider]:
        raise ValueError(f"{provider} does not support {request.kind}")
    model = request.model or adopted_model
    if not model:
        if provider == "elevenlabs":
            model = {"sfx": "eleven_text_to_sound_v2", "ambience": "eleven_text_to_sound_v2",
                     "dialogue": "eleven_v3", "music": "music_v2_5"}[request.kind]
        elif provider == "stable_audio":
            model = "small-music" if request.kind == "music" else "small-sfx"
        elif provider == "gemini":
            model = "gemini-3.8-flash-tts"
        elif provider == "qwen":
            suffix = {"custom": "CustomVoice", "design": "VoiceDesign", "clone": "Base"}[request.voice_mode]
            model = "Qwen/Qwen3-TTS-12Hz-1.7B-" + suffix
        else:
            model = "acestep-v15-turbo"
    return provider, model, reason


def plan(root: Path, request: GenerateRequest, settings: Settings):
    provider, model, reason = select_provider(root, request, settings)
    blockers = []
    estimated_credits = None
    music_eligibility = None
    character_voice = None
    if provider == "elevenlabs":
        if request.kind in ("sfx", "ambience"):
            if len(request.prompt) > 450:
                raise ValueError("ElevenLabs SFX prompts must be at most 450 characters")
            if not 0.5 <= request.duration_seconds <= 30:
                raise ValueError("ElevenLabs SFX duration must be 0.5–30 seconds")
            if model != "eleven_text_to_sound_v2":
                raise ValueError("This SFX adapter supports eleven_text_to_sound_v2")
            estimated_credits = int(request.duration_seconds * 40 * request.variants + 0.999)
        elif request.kind == "dialogue":
            if not request.voice_id:
                blockers.append("Select an observed voice_id with the voices command")
            if request.reference_audio or request.instruction or request.voice_mode != "custom":
                raise ValueError("ElevenLabs dialogue uses an existing voice_id and text/audio tags; "
                                 "voice creation is a separate authoring action")
            if request.duration_seconds:
                raise ValueError("TTS cannot guarantee duration; omit duration_seconds and inspect the result")
            if model not in ("eleven_v4", "eleven_v4_turbo", "eleven_v3",
                             "eleven_multilingual_v2", "eleven_flash_v2_5"):
                raise ValueError("Select a supported ElevenLabs TTS model")
            # Conservative standard estimate; actual billing headers remain authoritative.
            estimated_credits = len(request.prompt) * request.variants
        else:
            evidence = request.music_eligibility_evidence or (
                settings.elevenlabs_music_evidence if settings.elevenlabs_music_eligible else "")
            music_eligibility = {"status": "recorded" if evidence else "unverified",
                                 "evidence": evidence,
                                 "note": "Use-specific evidence, not a license grant or release approval"}
            if len(request.prompt) > 4100:
                raise ValueError("Eleven Music prompts must be at most 4100 characters")
            if not 3 <= request.duration_seconds <= 600:
                raise ValueError("Eleven Music duration must be 3–600 seconds")
            if model not in ("music_v1", "music_v2", "music_v2_5"):
                raise ValueError("Use an API model ID: music_v2_5, music_v2 or music_v1; "
                                 "plugin model IDs are not REST model IDs")
            if request.bpm or request.key:
                raise ValueError("For Eleven Music, include BPM/key in the prompt; they are not exact API controls")
        if request.max_credits is not None:
            if estimated_credits is None:
                blockers.append("This adapter cannot enforce a credit estimate for music; resolve the budget first")
            elif estimated_credits > request.max_credits:
                blockers.append("Estimated batch credits exceed max_credits")
    elif provider == "gemini":
        if model not in ("gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"):
            raise ValueError("Select gemini-3.8-flash-tts or gemini-3.8-flash-lite-tts")
        if request.reference_audio or request.reference_text or request.voice_mode != "custom":
            raise ValueError("Gemini dialogue uses an existing voice_id; voice creation is a separate action")
        if request.duration_seconds:
            raise ValueError("TTS cannot guarantee duration; omit duration_seconds and inspect the result")
        if len(request.instruction) > 1000:
            raise ValueError("Keep Gemini turn-level acting instruction at most 1000 characters")
        if not request.voice_id:
            blockers.append("Select an observed Gemini voice_id using gemini-voices or a saved voice profile")
        else:
            from .character_voices import voice_for_synthesis
            character_voice = voice_for_synthesis(root, request.voice_id)
        if not gemini_credential(root, settings)[0]:
            blockers.append("Set GEMINI_API_KEY, GOOGLE_API_KEY, or the configured Gemini key file")
        if request.max_credits is not None:
            blockers.append("max_credits uses ElevenLabs units and cannot cap Gemini billing; "
                            "resolve that budget and omit max_credits before Gemini generation")
    else:
        backend = settings.local_backends.get(provider)
        if not backend or not resolve(root, backend.python).is_file():
            blockers.append(f"Set up the isolated {provider} backend; see references/local-models.md")
        if provider == "stable_audio":
            if model not in ("small-sfx", "small-music", "medium"):
                raise ValueError("Stable Audio model must be small-sfx, small-music or medium")
            if (request.kind == "music" and model == "small-sfx") or (
                request.kind != "music" and model == "small-music"
            ):
                raise ValueError("Use the Stable Audio model trained for the requested audio category")
            if request.duration_seconds > (380 if model == "medium" else 120):
                raise ValueError("Duration exceeds the selected Stable Audio model limit")
            if request.bpm or request.key:
                raise ValueError("For Stable Audio, include BPM/key in the prompt; they are not exact API controls")
        if provider == "ace_step" and request.duration_seconds < 10:
            raise ValueError("ACE-Step adapter uses clips of at least 10 seconds")
        if provider == "qwen" and request.duration_seconds:
            raise ValueError("Qwen TTS duration is determined by speech; omit duration_seconds")
        if provider == "qwen":
            if request.voice_mode == "design" and not request.instruction:
                raise ValueError("Qwen voice design requires an instruction")
            if request.voice_mode == "clone" and request.instruction:
                raise ValueError("Qwen Base clone does not accept acting instructions")
    return {
        "provider": provider, "model": model, "reason": reason,
        "dialogue_processing": ("density" if provider == "gemini" and request.kind == "dialogue"
                                 else "none") if request.dialogue_processing == "auto"
                                else request.dialogue_processing,
        "transport": "api" if provider in ("elevenlabs", "gemini") else "local",
        "effective_mode": settings.mode if provider == "gemini" else effective_mode(root, settings),
        "variants": request.variants,
        "remote_calls": request.variants if provider in ("elevenlabs", "gemini") else 0,
        "automatic_paid_retries": 0, "estimated_credits": estimated_credits,
        "music_eligibility": music_eligibility,
        "character_voice": character_voice,
        "request_notes": ["Gemini seed and language fields are metadata only; language is inferred from text"]
                         if provider == "gemini" else [],
        "estimate_note": "Local estimate, not a server-side spending guarantee; inspect actual usage",
        "ready": not blockers, "blockers": blockers,
    }

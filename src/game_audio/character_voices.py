"""Persistent fictional Gemini voice designs with local receipts and no renewal claims."""

import base64
import hashlib
import io
import json
import os
import re
import uuid
import wave
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from filelock import FileLock
from pydantic import Field, field_validator

from .config import gemini_credential, load_settings
from .elevenlabs import UnknownSubmission
from .gemini import Gemini, GeminiRejected
from .models import StrictModel
from .storage import digest, now, read_json, write_json


class VoiceDesignRequest(StrictModel):
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")
    display_name: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=2000)
    language_code: str = Field("ko-KR", pattern=r"^[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*$")
    gender: Literal["male", "female", "neutral"] | None = None
    model: Literal["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"] = "gemini-3.8-flash-tts"

    @field_validator("name")
    @classmethod
    def portable_name(cls, value):
        if re.fullmatch(r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])", value):
            raise ValueError("Choose a character name that is a portable folder name")
        return value


def _spec_hash(spec):
    return hashlib.sha256(json.dumps(spec, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _directory(root, name):
    base = (root / ".assets/voices").resolve()
    directory = (base / name).resolve()
    if directory.parent != base:
        raise ValueError("Character voice path must stay inside the local voice registry")
    return directory


def _expiry(value):
    try:
        expiry = datetime.fromisoformat(value)
        if expiry.tzinfo is None:
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        raise ValueError("Voice response has no valid server expire_time; "
                         "reconcile the saved response") from None
    return expiry <= datetime.now(UTC)


def _check_request(directory, spec):
    path = directory / "request.json"
    if path.exists():
        saved = read_json(path)
        if saved.get("request") != spec or saved.get("sha256") != _spec_hash(spec):
            raise ValueError("This character name already has a different design; use a new name")
    elif directory.exists() and any(directory.iterdir()):
        raise ValueError("Character directory has no valid request; reconcile existing files first")


def _payload(spec):
    voice = {"model": spec["model"], "type": "prompted", "display_name": spec["display_name"],
             "language_code": spec["language_code"], "prompted": {"input": spec["prompt"]}}
    if spec["gender"]:
        voice["gender"] = spec["gender"]
    return {"store": True, "voice": voice}


def _model_code(value):
    return value.removeprefix("models/") if isinstance(value, str) else None


def plan_voice(root: Path, raw_spec: dict):
    """Validate a design and inspect local readiness without sending any requests."""
    spec = VoiceDesignRequest.model_validate(raw_spec).model_dump()
    directory = _directory(root, spec["name"])
    _check_request(directory, spec)
    blockers = []
    state = "new"
    remote_calls = 1
    if (directory / "manifest.json").is_file():
        summary = show_voice(root, str(directory / "manifest.json"))
        state, remote_calls = "archived", 0
        if summary["expired"]:
            blockers.append("This stored voice has expired; no supported automatic renewal is implemented")
    elif (directory / "response.json").is_file():
        state, remote_calls = "archive_pending", 0
    elif (directory / "remote.json").exists():
        state, remote_calls = "needs_reconciliation", 0
        blockers.append("A previous voice creation attempt exists; reconcile it without another POST")
    if remote_calls:
        settings = load_settings(root)
        if settings.mode == "only_local":
            blockers.append("Only-local mode blocks Gemini voice design")
        if not gemini_credential(root, settings)[0]:
            blockers.append("Set GEMINI_API_KEY or the configured private Gemini key file")
    return {"name": spec["name"], "provider": "gemini", "model": spec["model"], "state": state,
            "manifest": str(directory / "manifest.json"), "remote_calls": remote_calls,
            "automatic_paid_retries": 0, "ready": not blockers, "blockers": blockers,
            "renewal": "No automatic renewal or reconstruction from generated samples is supported"}


def _archive_response(root, directory, spec):
    response_path = directory / "response.json"
    response = read_json(response_path)
    receipt = read_json(directory / "remote.json")
    if receipt.get("request_sha256") != _spec_hash(spec):
        raise ValueError("Voice receipt does not match the saved design")
    if receipt.get("response_sha256") and digest(response_path) != receipt["response_sha256"]:
        raise ValueError("Saved voice response changed; reconcile without another POST")
    voice_id = response.get("id", "")
    if not isinstance(voice_id, str) or not re.fullmatch(r"voice_[A-Za-z0-9_-]+", voice_id):
        raise ValueError("Saved voice response has no valid stored voice ID")
    if response.get("type") not in (None, "prompted") or _model_code(response.get("model")) != spec["model"]:
        raise ValueError("Saved voice response differs from the requested type or model")
    _expiry(response.get("expire_time"))
    sample = response.get("sample_audio") or {}
    try:
        if sample.get("mime_type") != "audio/wav":
            raise ValueError
        data = base64.b64decode(sample["data"], validate=True)
        with wave.open(io.BytesIO(data), "rb") as wav:
            frames, rate, channels = wav.getnframes(), wav.getframerate(), wav.getnchannels()
            expected_bytes = frames * channels * wav.getsampwidth()
            if frames <= 0 or rate <= 0 or len(wav.readframes(frames)) != expected_bytes:
                raise ValueError
    except (KeyError, TypeError, ValueError, wave.Error, EOFError):
        raise ValueError("Saved voice response has no complete valid WAV preview; reconcile it") from None
    sample_path = directory / "sample.wav"
    expected = hashlib.sha256(data).hexdigest()
    if sample_path.exists():
        if digest(sample_path) != expected:
            raise ValueError("Saved voice preview changed; refusing to overwrite it")
    else:
        temporary = directory / ("sample." + uuid.uuid4().hex + ".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, sample_path)
    manifest = {
        "schema_version": 1, "name": spec["name"], "provider": "gemini", "type": "prompted",
        "voice_id": voice_id, "model": spec["model"], "response_model": response["model"],
        "expire_time": response["expire_time"],
        "display_name": response.get("display_name", spec["display_name"]),
        "language_code": response.get("language_code", spec["language_code"]),
        "request": spec, "request_sha256": _spec_hash(spec),
        "response": {"file": "response.json", "sha256": digest(response_path)},
        "sample_audio": {"file": "sample.wav", "sha256": expected, "mime_type": "audio/wav",
                         "sample_rate": rate, "channels": channels, "frames": frames,
                         "duration_seconds": frames / rate},
        "usage": response.get("usage"), "archived_at": now(), "listening": "unreviewed",
        "renewal": "No supported automatic renewal; archived WAV is not a portable voice identity",
    }
    write_json(directory / "manifest.json", manifest)
    receipt.update(state="archived", voice_id=voice_id, expire_time=response["expire_time"],
                   response_sha256=digest(response_path), completed_at=now())
    write_json(directory / "remote.json", receipt)
    return show_voice(root, str(directory / "manifest.json"))


def create_voice(root: Path, raw_spec: dict):
    """Create once, or finish archiving an already saved remote response after a crash."""
    spec = VoiceDesignRequest.model_validate(raw_spec).model_dump()
    directory = _directory(root, spec["name"])
    lock = root / ".runtime/locks" / ("voice-" + spec["name"] + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(lock), timeout=0):
        _check_request(directory, spec)
        if (directory / "manifest.json").exists():
            return show_voice(root, str(directory / "manifest.json"))
        if (directory / "response.json").exists():
            return _archive_response(root, directory, spec)
        if (directory / "remote.json").exists():
            raise UnknownSubmission("A previous voice creation attempt exists; "
                                    "reconcile it without another POST")
        planned = plan_voice(root, spec)
        if not planned["ready"]:
            raise ValueError("; ".join(planned["blockers"]))
        client = Gemini(root, load_settings(root))
        try:
            directory.mkdir(parents=True, exist_ok=True)
            write_json(directory / "request.json", {"request": spec, "sha256": _spec_hash(spec)})
            receipt = {"state": "submitting", "provider": "gemini", "started_at": now(),
                       "endpoint": "/v1beta/voices",
                       "request_sha256": _spec_hash(spec), "request": _payload(spec)}
            write_json(directory / "remote.json", receipt)
            try:
                response = client.request_json("POST", "/v1beta/voices", _payload(spec))
            except GeminiRejected as error:
                receipt.update(state="rejected", **getattr(client, "last_response_metadata", {}))
                receipt["http_status"] = error.status_code
                write_json(directory / "remote.json", receipt)
                raise ValueError(f"Gemini voice creation rejected with HTTP {error.status_code}; "
                                 "no retry sent") from None
            except (UnknownSubmission, OSError) as error:
                receipt.update(state="unknown", failure_type=type(error).__name__,
                               **getattr(client, "last_response_metadata", {}))
                write_json(directory / "remote.json", receipt)
                raise UnknownSubmission("Voice creation outcome is uncertain; "
                                        "reconcile the saved receipt") from None
            write_json(directory / "response.json", response)
            receipt.update(state="response_received", response_sha256=digest(directory / "response.json"),
                           **getattr(client, "last_response_metadata", {}))
            write_json(directory / "remote.json", receipt)
        finally:
            client.close()
        return _archive_response(root, directory, spec)


def show_voice(root: Path, name_or_path: str):
    """Return verified local metadata, never raw response audio or credentials."""
    if re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", name_or_path):
        directory = _directory(root, name_or_path)
    else:
        path = Path(name_or_path)
        path = (path if path.is_absolute() else root / path).resolve()
        directory = path if path.is_dir() else path.parent
        if not path.is_dir() and path.name != "manifest.json":
            raise ValueError("Use a character name or its manifest.json path")
        if directory != _directory(root, directory.name):
            raise ValueError("Voice profile must belong to this project's local registry")
    manifest_path = directory / "manifest.json"
    manifest = read_json(manifest_path)
    spec = VoiceDesignRequest.model_validate(manifest["request"]).model_dump()
    _check_request(directory, spec)
    if (manifest.get("name") != directory.name or manifest.get("model") != spec["model"]
            or manifest.get("request_sha256") != _spec_hash(spec)):
        raise ValueError("Voice profile request identity changed")
    response_path = directory / "response.json"
    sample_path = directory / "sample.wav"
    if digest(response_path) != manifest["response"]["sha256"]:
        raise ValueError("Saved voice response changed")
    response = read_json(response_path)
    if (_model_code(response.get("model")) != manifest["model"]
            or response.get("model") != manifest.get("response_model", manifest["model"])):
        raise ValueError("Voice profile model differs from its saved provider response")
    for key, value in (("id", manifest["voice_id"]), ("expire_time", manifest["expire_time"])):
        if response.get(key) != value:
            raise ValueError("Voice profile differs from its saved provider response")
    if digest(sample_path) != manifest["sample_audio"]["sha256"]:
        raise ValueError("Saved voice preview changed")
    return {"name": manifest["name"], "provider": "gemini", "voice_id": manifest["voice_id"],
            "model": manifest["model"], "response_model": manifest.get("response_model", manifest["model"]),
            "manifest": str(manifest_path), "sha256": digest(manifest_path),
            "expire_time": manifest["expire_time"], "expired": _expiry(manifest["expire_time"]),
            "sample_audio": {**manifest["sample_audio"], "path": str(sample_path)},
            "listening": manifest["listening"], "renewal": manifest["renewal"]}


def voice_for_synthesis(root: Path, voice_id: str):
    """Bind locally registered identity/expiry to generation; external IDs return None."""
    for path in (root / ".assets/voices").glob("*/manifest.json"):
        if read_json(path).get("voice_id") == voice_id:
            profile = show_voice(root, str(path))
            if profile["expired"]:
                raise ValueError("The selected character voice has expired; "
                                 "automatic recreation is unsupported")
            return profile
    return None

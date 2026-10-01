"""Explicit Gemini TTS with a durable single-submission boundary.

The REST schema is the Interactions API, not generateContent or SDK convenience
properties. Never retry a POST automatically, including after a timeout.
"""

import base64
import binascii
import io
import wave
from pathlib import Path
from urllib.parse import quote, urlencode

import httpx

from .config import gemini_credential
from .elevenlabs import UnknownSubmission
from .models import GenerateRequest, Settings
from .storage import digest, now, read_json, write_json

API = "https://generativelanguage.googleapis.com"
MODELS = ("gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts")


def voice_summary(value):
    fields = ("id", "name", "voice_id", "display_name", "description", "language", "language_code",
              "create_time", "update_time", "expire_time", "model", "labels", "state", "type",
              "gender", "pitch", "accent", "persona", "contexts")
    result = {key: value[key] for key in fields if key in value}
    sample = value.get("sample_audio")
    if isinstance(sample, dict):
        result["sample_audio"] = {"available": bool(sample.get("data")),
                                  "mime_type": sample.get("mime_type")}
    return result


class GeminiRejected(ValueError):
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__(f"Gemini request rejected with HTTP {status_code}; no retry sent")


def speech_body(request: GenerateRequest, model: str):
    if request.kind != "dialogue" or model not in MODELS:
        raise ValueError("Gemini adapter requires dialogue and a supported Gemini TTS model")
    if not request.voice_id or request.voice_mode != "custom" or request.reference_audio:
        raise ValueError("Gemini synthesis requires an existing voice_id; author voices separately")
    content = {"type": "text", "text": request.prompt}
    if request.instruction:
        content["annotations"] = [{"type": "speech_metadata", "style": request.instruction}]
    return {"model": model, "input": [{"type": "user_input", "content": [content]}],
            "response_format": {"type": "audio", "mime_type": "audio/wav", "sample_rate": 24000},
            "generation_config": {"speech_config": [{"voice": request.voice_id}]}, "stream": False}


def _response_audio(response):
    if not isinstance(response, dict) or not isinstance(response.get("steps"), list):
        raise UnknownSubmission("Saved Gemini response has an invalid shape; reconcile without resubmitting")
    blocks = [content for step in response["steps"]
              if isinstance(step, dict) and step.get("type") == "model_output"
              and isinstance(step.get("content"), list)
              for content in step["content"] if isinstance(content, dict) and content.get("type") == "audio"]
    if not blocks:
        raise UnknownSubmission("Gemini returned no audio block; inspect the saved response without resubmitting")
    block = blocks[-1]  # Same final-block semantics as the official SDK output_audio convenience property.
    mime_type = block.get("mime_type", "audio/wav")
    if not isinstance(mime_type, str) or mime_type.split(";", 1)[0] not in ("audio/wav", "audio/x-wav"):
        raise UnknownSubmission("Gemini returned an unexpected audio format; preserve the saved response")
    try:
        data = base64.b64decode(block["data"], validate=True)
        with wave.open(io.BytesIO(data), "rb") as audio:
            raw_format = {"sample_rate": audio.getframerate(), "channels": audio.getnchannels(),
                          "sample_width": audio.getsampwidth(), "frames": audio.getnframes()}
            expected_bytes = audio.getnframes() * audio.getnchannels() * audio.getsampwidth()
            if expected_bytes <= 0 or len(audio.readframes(audio.getnframes())) != expected_bytes:
                raise ValueError("Empty or truncated audio")
            if len(data) < int.from_bytes(data[4:8], "little") + 8:
                raise ValueError("Truncated WAV container")
    except (KeyError, TypeError, ValueError, binascii.Error, wave.Error, EOFError):
        raise UnknownSubmission("Saved Gemini audio cannot be decoded; reconcile without resubmitting") from None
    return data, raw_format


def _decode_response(take: Path, record: dict):
    response_path = take / "response.json"
    if not response_path.is_file() or digest(response_path) != record.get("response_sha256"):
        raise ValueError("Saved Gemini response is missing or changed; reconcile without regenerating")
    response = read_json(response_path)
    data, raw_format = _response_audio(response)
    raw = take / "provider.wav"
    if raw.exists():
        if raw.read_bytes() != data:
            raise ValueError("Existing Gemini audio differs from the saved response; do not overwrite it")
    else:
        temporary = take / "provider.partial"
        temporary.write_bytes(data)
        temporary.replace(raw)
    record.update(state="downloaded", file=raw.name, sha256=digest(raw), raw_format=raw_format,
                  interaction_id=response.get("id"), response_model=response.get("model"),
                  response_status=response.get("status"), usage=response.get("usage"), completed_at=now())
    write_json(take / "remote.json", record)
    return raw, record


def _bind_saved_response(take: Path, record: dict):
    """Close the crash window between atomic response save and receipt update."""
    response_path = take / "response.json"
    try:
        response_hash = digest(response_path)
        response = read_json(response_path)
    except (OSError, ValueError):
        raise UnknownSubmission("Saved Gemini response is incomplete; reconcile without resubmitting") from None
    body = record.get("request")
    if (record.get("endpoint") != "/v1beta/interactions" or record.get("remote_posts") != 1
            or not isinstance(body, dict) or body.get("model") not in MODELS
            or record.get("model") != body["model"] or not isinstance(response, dict)
            or str(response.get("model", "")).removeprefix("models/") != body["model"]
            or response.get("status") != "completed" or not isinstance(response.get("id"), str)
            or not response["id"]):
        raise UnknownSubmission("Saved Gemini response does not match this attempt; reconcile without resubmitting")
    if record.get("interaction_id") and record["interaction_id"] != response["id"]:
        raise UnknownSubmission("Saved Gemini interaction ID differs; reconcile without resubmitting")
    if record.get("response_sha256") and record["response_sha256"] != response_hash:
        raise ValueError("Previously bound Gemini response changed; do not rebind it")
    _response_audio(response)  # Validate the complete WAV before establishing a new hash binding.
    # Some API responses omit user_input; when echoed, require the exact saved transcript and metadata.
    echoed = [step for step in response["steps"] if isinstance(step, dict) and step.get("type") == "user_input"]
    if echoed and [{"type": step["type"], "content": step.get("content")} for step in echoed] != body.get("input"):
        raise UnknownSubmission("Saved Gemini response input differs; reconcile without resubmitting")
    if digest(response_path) != response_hash:
        raise ValueError("Gemini response changed during recovery")
    record.update(state="response_received", response_file=response_path.name,
                  response_sha256=response_hash, recovered_response_receipt_gap=True,
                  recovered_at=now())
    write_json(take / "remote.json", record)
    return _decode_response(take, record)


def recover_saved(take: Path):
    """Resume locally saved WAV/JSON, even when a key is no longer available."""
    receipt = take / "remote.json"
    if not receipt.exists():
        if (take / "response.json").exists():
            raise UnknownSubmission("A Gemini response exists without its attempt receipt; reconcile, do not resubmit")
        return None
    record = read_json(receipt)
    if record.get("provider") != "gemini":
        raise ValueError("Saved remote receipt belongs to another provider")
    if record.get("state") == "downloaded":
        raw = take / record["file"]
        if not raw.is_file() or digest(raw) != record["sha256"]:
            raise ValueError("Saved Gemini audio is missing or changed; reconcile without regenerating")
        if digest(take / "response.json") != record["response_sha256"]:
            raise ValueError("Saved Gemini response changed")
        return raw, record
    if record.get("state") == "response_received":
        return _decode_response(take, record)
    if record.get("state") in ("submitting", "unknown") and (take / "response.json").is_file():
        return _bind_saved_response(take, record)
    raise UnknownSubmission("A Gemini submission already exists; inspect remote.json and response.json. "
                            "No automatic POST retry or provider fallback is allowed")


class Gemini:
    def __init__(self, root: Path, settings: Settings, transport=None):
        key, _ = gemini_credential(root, settings)
        if not key:
            raise ValueError("Gemini API key is missing; configure GEMINI_API_KEY or its private key file")
        self.settings = settings
        self.last_response_metadata = {}
        self.client = httpx.Client(base_url=API, headers={"x-goog-api-key": key},
                                   timeout=httpx.Timeout(600, connect=20), transport=transport,
                                   follow_redirects=False)

    def close(self):
        self.client.close()

    def request_json(self, method, path, payload=None):
        """Safe low-level interface; POST callers must persist their receipt first."""
        method = method.upper()
        if method not in ("GET", "POST") or not path.startswith("/v1beta/"):
            raise ValueError("Use GET/POST with a Gemini /v1beta/ path")
        if method == "POST" and self.settings.mode == "only_local":
            raise ValueError("Only-local mode blocks Gemini remote generation")
        self.last_response_metadata = {}
        try:
            response = self.client.request(method, path, json=payload)
        except httpx.HTTPError:
            if method == "POST":
                raise UnknownSubmission("Gemini submission outcome is uncertain; no retry sent") from None
            raise ValueError("Gemini read-only request failed; credentials and response bodies were omitted") from None
        self.last_response_metadata = {"http_status": response.status_code,
                                       "headers": {name: response.headers[name]
                                                   for name in ("x-request-id", "request-id")
                                                   if name in response.headers}}
        if response.status_code >= 400 or response.status_code < 200 or response.status_code >= 300:
            if method == "POST" and response.status_code >= 500:
                raise UnknownSubmission("Gemini returned an uncertain HTTP result; no retry sent")
            raise GeminiRejected(response.status_code)
        try:
            result = response.json()
            if not isinstance(result, dict):
                raise TypeError("Expected object")
        except (ValueError, TypeError):
            if method == "POST":
                raise UnknownSubmission("Gemini returned invalid JSON; reconcile without resubmitting") from None
            raise ValueError("Gemini returned invalid JSON for a read-only request") from None
        return result

    def voices(self, page_token=None):
        path = "/v1beta/voices"
        if page_token:
            path += "?" + urlencode({"page_token": page_token})
        result = self.request_json("GET", path)
        return {"voices": [voice_summary(voice) for voice in result.get("voices", [])],
                "next_page_token": result.get("next_page_token")}

    def voice(self, voice_id):
        return voice_summary(self.request_json("GET", "/v1beta/voices/" + quote(voice_id, safe="")))

    def model(self, model_id="gemini-3.8-flash-tts"):
        if model_id not in MODELS:
            raise ValueError("Select a supported Gemini TTS model")
        result = self.request_json("GET", "/v1beta/models/" + quote(model_id, safe=""))
        fields = ("name", "version", "displayName", "description", "supportedGenerationMethods",
                  "inputTokenLimit", "outputTokenLimit")
        return {"model": {key: result[key] for key in fields if key in result},
                "read_access_verified": True, "synthesis_verified": False}

    def generate(self, request: GenerateRequest, selected: dict, take: Path):
        cached = recover_saved(take)
        if cached:
            return cached
        if self.settings.mode == "only_local":
            raise ValueError("Only-local mode blocks Gemini remote generation")
        body = speech_body(request, selected["model"])
        receipt = take / "remote.json"
        record = {"state": "submitting", "provider": "gemini", "started_at": now(),
                  "endpoint": "/v1beta/interactions", "model": selected["model"], "request": body,
                  "character_voice": selected.get("character_voice"), "seed_sent": False,
                  "seed_note": "Gemini 3.8 TTS has no supported seed control in this adapter",
                  "remote_posts": 1}
        write_json(receipt, record)
        try:
            response = self.request_json("POST", record["endpoint"], body)
            response_path = take / "response.json"
            write_json(response_path, response)
            record.update(state="response_received", response_file=response_path.name,
                          response_sha256=digest(response_path), **self.last_response_metadata)
            write_json(receipt, record)
        except GeminiRejected as error:
            record.update(state="rejected", **self.last_response_metadata)
            record["http_status"] = error.status_code
            write_json(receipt, record)
            raise
        except (UnknownSubmission, OSError):
            record.update(state="unknown", **self.last_response_metadata)
            write_json(receipt, record)
            raise UnknownSubmission("Gemini submission/response persistence is uncertain; no retry sent") from None
        return _decode_response(take, record)

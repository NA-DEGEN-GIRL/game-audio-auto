from pathlib import Path
from urllib.parse import quote

import httpx

from .config import credential
from .models import GenerateRequest, Settings
from .storage import digest, now, read_json, write_json

API = "https://api.elevenlabs.io"


class UnknownSubmission(RuntimeError):
    """A paid operation may have run. Never automatically repeat the POST."""


class ElevenLabs:
    def __init__(self, root: Path, settings: Settings, transport=None):
        key, _ = credential(root, settings)
        if not key:
            raise ValueError("ElevenLabs API key is missing; use only-local mode")
        self.client = httpx.Client(base_url=API, headers={"xi-api-key": key},
                                   timeout=httpx.Timeout(600, connect=20), transport=transport,
                                   follow_redirects=False)

    def close(self):
        self.client.close()

    def get(self, endpoint, params=None):
        response = self.client.get(endpoint, params=params)
        if response.status_code != 200:
            raise ValueError(f"ElevenLabs read-only request returned HTTP {response.status_code}")
        return response.json()

    def account(self):
        data = self.get("/v1/user/subscription")
        # Intentionally exclude invoices, payment details and account identity.
        fields = ("tier", "status", "character_count", "character_limit", "next_character_count_reset_unix")
        result = {key: data.get(key) for key in fields}
        used, limit = data.get("character_count"), data.get("character_limit")
        result["credits_remaining"] = max(0, limit - used) if isinstance(used, int) and isinstance(limit, int) else None
        return result

    def voices(self, page_token=None):
        params = {"page_size": 100}
        if page_token:
            params["next_page_token"] = page_token
        data = self.get("/v2/voices", params)
        return {"voices": [{k: v.get(k) for k in ("voice_id", "name", "category", "labels")}
                            for v in data.get("voices", [])],
                "has_more": data.get("has_more", False), "next_page_token": data.get("next_page_token")}

    def history(self, start_after=None):
        params = {"page_size": 30}
        if start_after:
            params["start_after_history_item_id"] = start_after
        data = self.get("/v1/history", params)
        fields = ("history_item_id", "request_id", "date_unix", "voice_name", "model_id", "text")
        return {"history": [{k: item.get(k) for k in fields} for item in data.get("history", [])],
                "has_more": data.get("has_more", False)}

    def generate(self, request: GenerateRequest, selected: dict, take: Path, output_format: str):
        receipt = take / "remote.json"
        if receipt.exists():
            previous = read_json(receipt)
            if previous.get("state") == "downloaded":
                raw = take / previous["file"]
                if not raw.is_file() or digest(raw) != previous["sha256"]:
                    raise ValueError("Saved provider output is missing or changed; reconcile, do not regenerate")
                return raw, previous
            raise UnknownSubmission("A previous paid attempt exists. Inspect remote.json and history; "
                                    "recover its audio instead of submitting again")
        model = selected["model"]
        if request.kind in ("sfx", "ambience"):
            endpoint = "/v1/sound-generation"
            body = {"text": request.prompt, "model_id": model, "duration_seconds": request.duration_seconds,
                    "loop": request.playback.intent == "loop", "prompt_influence": request.prompt_influence}
        elif request.kind == "dialogue":
            endpoint = "/v1/text-to-speech/" + quote(request.voice_id, safe="")
            body = {"text": request.prompt, "model_id": model, "seed": request.seed}
            if model != "eleven_multilingual_v2":
                body["language_code"] = request.language
        else:
            endpoint = "/v1/music"
            body = {"prompt": request.prompt, "model_id": model,
                    "music_length_ms": round(request.duration_seconds * 1000),
                    "force_instrumental": request.instrumental}
            # The prompt endpoint does not accept seed, including when our local spec records one.
            output_format = "auto"
        if output_format != "auto" and not output_format.startswith("mp3_"):
            raise ValueError("Initial ElevenLabs adapter supports MP3 source formats; WAV masters are decoded locally")
        record = {"state": "submitting", "started_at": now(), "endpoint": endpoint,
                  "model": model, "output_format": output_format, "request": body,
                  "seed_sent": request.kind == "dialogue"}
        write_json(receipt, record)  # Persist before the single potentially paid POST.
        temporary = take / "provider.partial"
        try:
            with self.client.stream("POST", endpoint, json=body,
                                    params={"output_format": output_format}) as response:
                record["http_status"] = response.status_code
                for header in ("request-id", "x-request-id", "history-item-id", "song-id", "character-cost"):
                    if response.headers.get(header):
                        record[header] = response.headers[header]
                if response.status_code != 200:
                    record["state"] = "rejected" if 400 <= response.status_code < 500 else "unknown"
                    write_json(receipt, record)
                    if record["state"] == "unknown":
                        raise UnknownSubmission("ElevenLabs returned an uncertain result; inspect the saved receipt")
                    raise ValueError(f"ElevenLabs generation rejected with HTTP {response.status_code}; no retry sent")
                record["state"] = "receiving"
                record["content_type"] = response.headers.get("content-type", "")
                write_json(receipt, record)
                with temporary.open("wb") as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
            if not temporary.stat().st_size:
                raise UnknownSubmission("ElevenLabs returned an empty stream; reconcile this attempt")
            raw = take / "provider.mp3"
            temporary.replace(raw)
            record.update(state="downloaded", file=raw.name, sha256=digest(raw), completed_at=now())
            write_json(receipt, record)
            return raw, record
        except (httpx.HTTPError, OSError) as error:
            record.update(state="unknown", failure_type=type(error).__name__)
            write_json(receipt, record)
            raise UnknownSubmission("Provider submission/download outcome is uncertain; no automatic retry") from None

    def recover_history(self, take: Path, history_id: str):
        receipt = take / "remote.json"
        record = read_json(receipt)
        if record.get("state") == "downloaded":
            raise ValueError("This take already has a downloaded output")
        if record.get("endpoint") == "/v1/music":
            raise ValueError("Music recovery uses the saved song ID/provider UI; import verified existing audio")
        metadata = self.get("/v1/history/" + quote(history_id, safe=""))
        known_history = record.get("history-item-id")
        known_request = record.get("request-id") or record.get("x-request-id")
        if known_history:
            if known_history != history_id:
                raise ValueError("History ID differs from the saved receipt")
        elif known_request:
            if metadata.get("request_id") != known_request:
                raise ValueError("History request ID does not match the saved receipt")
        else:
            raise ValueError("No provider ID was captured; reconcile manually and import verified existing audio")
        original = record.get("request", {})
        if metadata.get("text") != original.get("text") or metadata.get("model_id") != record.get("model"):
            raise ValueError("History item does not match the saved text/model; reconcile manually")
        if record.get("endpoint", "").startswith("/v1/text-to-speech/") and (
            quote(str(metadata.get("voice_id", "")), safe="") != record["endpoint"].rsplit("/", 1)[-1]
        ):
            raise ValueError("History voice does not match the saved request")
        response = self.client.get("/v1/history/" + quote(history_id, safe="") + "/audio")
        if response.status_code != 200 or not response.content:
            raise ValueError(f"History audio download failed with HTTP {response.status_code}")
        raw = take / "provider.mp3"
        if raw.exists():
            raise ValueError("An existing raw file must be reconciled without overwriting it")
        raw.write_bytes(response.content)
        record.update(state="downloaded", file=raw.name, sha256=digest(raw),
                      recovered_history_item_id=history_id, completed_at=now())
        write_json(receipt, record)
        return {"recovered": str(raw), "remote_posts": 0}

import os
import subprocess
from pathlib import Path

from filelock import FileLock

from .models import GenerateRequest, Settings
from .storage import digest, now, read_json, resolve, write_json


def generate_local(root: Path, request: GenerateRequest, selected: dict, take: Path, settings: Settings):
    backend = settings.local_backends[selected["provider"]]
    receipt_path = take / "local.json"
    if receipt_path.exists():
        saved = read_json(receipt_path)
        if saved.get("state") == "generated":
            raw = take / saved["file"]
            if not raw.is_file() or digest(raw) != saved["sha256"]:
                raise ValueError("Saved local output is missing or changed")
            return raw, saved
    context = {"request": request.model_dump(), "selection": selected,
               "backend": backend.model_dump(), "runtime_root": str(root)}
    context_path = take / "local-request.json"
    write_json(context_path, context)
    runner = Path(__file__).resolve().parents[2] / "scripts/local_runner.py"
    raw = take / "provider.wav"
    if raw.exists():
        raise ValueError("Uncheckpointed local audio exists; inspect and preserve it before retrying")
    environment = os.environ.copy()
    for key in ("ELEVENLABS_API_KEY", "ELEVEN_API_KEY", "XI_API_KEY", "ELEVENLABS_API_KEY_FILE"):
        environment.pop(key, None)
    environment.setdefault("HF_HOME", str(root / ".runtime/huggingface"))
    if settings.huggingface_token_file and not environment.get("HF_TOKEN"):
        token_path = resolve(root, settings.huggingface_token_file)
        if token_path.is_file():
            environment["HF_TOKEN"] = token_path.read_text(encoding="utf-8-sig").strip()
    environment["HF_HUB_DISABLE_TELEMETRY"] = "1"
    environment["PYTHONUTF8"] = "1"
    lock = resolve(root, settings.gpu_lock)
    lock.parent.mkdir(parents=True, exist_ok=True)
    write_json(receipt_path, {"state": "waiting", "model": selected["model"]})
    with FileLock(lock, timeout=3600):
        write_json(receipt_path, {"state": "running", "started_at": now(), "model": selected["model"]})
        with (take / "local.log").open("ab") as log:
            result = subprocess.run([str(resolve(root, backend.python)), str(runner),
                                     str(context_path), str(raw)],
                                    cwd=resolve(root, backend.project_root) if backend.project_root else root,
                                    env=environment, stdout=log, stderr=subprocess.STDOUT, check=False,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    if result.returncode or not raw.is_file():
        write_json(receipt_path, {"state": "failed", "exit_code": result.returncode, "model": selected["model"]})
        raise ValueError(f"Local {selected['provider']} inference failed; inspect the saved local.log")
    metadata = read_json(take / "backend-metadata.json")
    record = {"state": "generated", "provider": selected["provider"], "model": selected["model"],
              "file": raw.name, "sha256": digest(raw), "metadata": metadata, "completed_at": now()}
    write_json(receipt_path, record)
    return raw, record

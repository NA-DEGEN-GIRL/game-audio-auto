import hashlib
import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path


def now():
    return datetime.now(UTC).isoformat()


def digest(path: Path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    os.replace(temporary, path)


def resolve(root: Path, value: str):
    path = Path(value).expanduser()
    return (path if path.is_absolute() else root / path).resolve()


def job_path(root: Path, job_id: str):
    if not re.fullmatch(r"j[a-f0-9]{24}", job_id):
        raise ValueError("Invalid job ID")
    return root / ".assets/jobs" / (job_id + ".json")


def new_revision(root: Path, name: str):
    revision = "r" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    path = root / ".assets/audio" / name / revision
    path.mkdir(parents=True, exist_ok=False)
    return path

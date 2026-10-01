"""Prepare and run one recoverable fictional-character dialogue comparison.

Preparation and collection make no paid calls. Generation creates one stored
Gemini design and one take per prepared line/provider; uncertain submissions
are reconciled with saved job records, never submitted again automatically.
"""

import argparse
import shutil
import uuid
from pathlib import Path

from filelock import FileLock

from game_audio.audio import measure, run_ffmpeg
from game_audio.character_voices import create_voice, plan_voice, show_voice
from game_audio.config import gemini_credential, load_settings, plan
from game_audio.jobs import get_job, launch, run_job, submit, verify_manifest
from game_audio.models import EditRequest, GenerateRequest, ImportRequest
from game_audio.storage import digest, now, read_json, resolve, write_json

MODEL = "gemini-3.8-flash-tts"
COMMON_TEXT = "왔구나. 문은 이미 닫혔어. 이제 나와 끝까지 놀아야 해."
LINES = [
    ("neutral", "A", "평상시", COMMON_TEXT,
     "Calm, conversational and dry. Natural Korean articulation, no laughter.", "[calm] "),
    ("menacing", "B", "낮게 위협", COMMON_TEXT,
     "Very quietly menacing, controlled and intimate. Low volume, deliberate pauses, never cheerful.",
     "[whispers] [sinister] "),
    ("angry", "C", "분노", COMMON_TEXT,
     "Furious controlled rage, forceful clipped delivery, rising intensity.",
     "[angry] "),
    ("cackle", "D", "광기 어린 웃음", "<laughs> 아하하하! 도망쳐 봐. 그럴수록 더 재미있어!",
     "Unsettling theatrical cackle, then predatory delight and sharp threat.",
     "[laughs] [sinister] "),
]


def _state(directory):
    state = read_json(directory / "state.json")
    for item in [state["design"], *state["lines"]]:
        if digest(directory / item["spec"]) != item["sha256"]:
            raise ValueError("Prepared demo specification changed; preserve this batch and prepare a new directory")
    return state


def prepare(root: Path, directory: Path, eleven_voice_id=None):
    directory.mkdir(parents=True, exist_ok=True)
    with FileLock(str(directory / ".demo.lock"), timeout=0):
        if (directory / "state.json").exists():
            state = _state(directory)
            if eleven_voice_id and state.get("eleven_voice_id") != eleven_voice_id:
                raise ValueError("This demo already has a different comparison voice; use a new directory")
            return state
        if any(path.name != ".demo.lock" for path in directory.iterdir()):
            raise ValueError("Partial preparation exists; reconcile it or choose a new empty demo directory")
        token = uuid.uuid4().hex[:12]
        design = {
            "name": "gregoriya-v1", "display_name": "광란의 그레고리야 · 성인 남성",
            "model": MODEL, "language_code": "ko-KR", "gender": "male",
            "prompt": "An original fictional adult male dark-fantasy court jester in his late 40s. "
                      "Native Korean, medium-low resonant baritone with a lightly gravelly edge, "
                      "precise consonants and a distinctive sly theatrical texture; mature and never childlike.",
        }
        design_path = directory / "voice-design.json"
        write_json(design_path, design)
        state = {"schema_version": 1, "session": token, "prepared_at": now(),
                 "eleven_voice_id": eleven_voice_id,
                 "design": {"spec": design_path.name, "sha256": digest(design_path)}, "lines": []}
        providers = ["gemini", "elevenlabs"] if eleven_voice_id else ["gemini"]
        for index, (mood, candidate, title, text, style, tags) in enumerate(LINES):
            for provider_index, provider in enumerate(providers):
                transcript = text.replace("<laughs> ", "")
                spec = GenerateRequest(
                    name=f"gregoriya-{token}-{provider}-{mood}", kind="dialogue", provider=provider,
                    model=MODEL if provider == "gemini" else "eleven_v3",
                    prompt=text if provider == "gemini" else tags + transcript,
                    voice_id=eleven_voice_id if provider == "elevenlabs" else None,
                    instruction=style if provider == "gemini" else "", language="ko", variants=1,
                    purpose="fictional boss character acting comparison",
                    acceptance=["recognizable stable adult character voice", "clear Korean words",
                                "matches the requested scene emotion"],
                    playback={"intent": "once", "spatial": "2d"},
                    export={"sample_rate": 48000, "channels": "mono", "subtype": "PCM_24"},
                ).model_dump(mode="json")
                spec_path = directory / f"{provider}-{mood}.json"
                write_json(spec_path, spec)
                state["lines"].append({"provider": provider, "mood": mood, "title": title,
                                       "candidate": candidate, "text": transcript, "style": style,
                                       "order": index * len(providers) + provider_index,
                                       "spec": spec_path.name, "sha256": digest(spec_path)})
        write_json(directory / "state.json", state)
        return state


def _preflight(root, state, directory):
    voice_plan = plan_voice(root, read_json(directory / state["design"]["spec"]))
    blockers = list(voice_plan["blockers"])
    settings = load_settings(root)
    if any(item["provider"] == "gemini" and not item.get("job_id") for item in state["lines"]):
        if settings.mode == "only_local":
            blockers.append("Only-local mode blocks Gemini generation")
        if not gemini_credential(root, settings)[0]:
            blockers.append("Save a Gemini API key privately before generating the prepared dialogue")
    for item in state["lines"]:
        if item["provider"] == "elevenlabs" and not item.get("job_id"):
            try:
                selected = plan(root, GenerateRequest.model_validate(read_json(directory / item["spec"])), settings)
                blockers.extend(selected["blockers"])
            except ValueError as error:
                blockers.append(str(error))
    return list(dict.fromkeys(blockers))


def _same_generation_request(left, right):
    # Old immutable jobs predate this optional field. Their saved selection still
    # controls finishing; comparing requests must not retrofit a new selection.
    left, right = dict(left), dict(right)
    left.setdefault("dialogue_processing", "auto")
    right.setdefault("dialogue_processing", "auto")
    return left == right


def _recover_submission(root, spec, operation="generate"):
    matches = []
    for path in (root / ".assets/jobs").glob("j*.json"):
        record = read_json(path)
        if record.get("operation") == operation and record.get("request", {}).get("name") == spec["name"]:
            if not (_same_generation_request(record["request"], spec) if operation == "generate"
                    else record["request"] == spec):
                raise ValueError("A saved job with this demo name has a different request; reconcile it")
            matches.append(record)
    if len(matches) != 1:
        raise ValueError("Submission was started but no unique saved job can be identified; "
                         "reconcile before taking further action. No duplicate was submitted")
    return matches[0]


def generate(root: Path, directory: Path):
    with FileLock(str(directory / ".demo.lock"), timeout=0):
        state = _state(directory)
        blockers = _preflight(root, state, directory)
        if blockers:
            return {"status": "blocked", "blockers": blockers, "new_generation_calls": 0}
        if not state.get("voice"):
            state["voice_creation_started_at"] = state.get("voice_creation_started_at") or now()
            write_json(directory / "state.json", state)
            state["voice"] = create_voice(root, read_json(directory / state["design"]["spec"]))
            write_json(directory / "state.json", state)
        profile = show_voice(root, state["voice"]["manifest"])
        if profile["sha256"] != state["voice"]["sha256"] or profile["voice_id"] != state["voice"]["voice_id"]:
            raise ValueError("Selected character voice profile changed; preserve the original demo identity")
        if profile["expired"]:
            raise ValueError("Selected character voice expired; no automatic recreation was attempted")
        for item in state["lines"]:
            if not item.get("bound_spec"):
                spec = read_json(directory / item["spec"])
                if item["provider"] == "gemini":
                    spec["voice_id"] = profile["voice_id"]
                bound = directory / ("bound-" + item["spec"])
                write_json(bound, spec)
                item.update(bound_spec=bound.name, bound_sha256=digest(bound))
                write_json(directory / "state.json", state)
            bound = directory / item["bound_spec"]
            if digest(bound) != item["bound_sha256"]:
                raise ValueError("Frozen generation specification changed")
            spec = GenerateRequest.model_validate(read_json(bound)).model_dump(mode="json")
            if item.get("job_id"):
                record = get_job(root, item["job_id"])
                if not _same_generation_request(record["request"], spec):
                    raise ValueError("Saved demo job differs from its frozen specification")
            elif item.get("submission_started_at"):
                record = _recover_submission(root, spec)
                item["job_id"] = record["id"]
                write_json(directory / "state.json", state)
            else:
                # This marker survives a crash before submit() returns its durable job ID.
                item["submission_started_at"] = now()
                write_json(directory / "state.json", state)
                record = submit(root, "generate", GenerateRequest.model_validate(spec), background=True)
                item["job_id"] = record["id"]
                write_json(directory / "state.json", state)
            if record["status"] == "queued":
                launch(root, record["id"])  # Resume this saved job; never create a replacement.
        return {"status": "dispatched", "voice_id": profile["voice_id"],
                "jobs": [{"provider": item["provider"], "mood": item["mood"], "id": item["job_id"]}
                         for item in state["lines"]]}


def _matched(source, target, ffmpeg):
    run_ffmpeg(["-y", "-i", str(source), "-af", "loudnorm=I=-18:TP=-1:LRA=11",
                "-ar", "48000", "-c:a", "pcm_s16le", str(target)], executable=ffmpeg)


def _local_finish_job(root, directory, state, recovery, operation, request):
    """Checkpoint local imports/edits too; an interrupted return must not duplicate revisions."""
    spec = request.model_dump(mode="json")
    id_key, start_key = operation + "_job_id", operation + "_started_at"
    if recovery.get(id_key):
        record = get_job(root, recovery[id_key])
        if record["request"] != spec:
            raise ValueError("Local finishing job differs from the preserved recovery settings")
    elif recovery.get(start_key):
        record = _recover_submission(root, spec, operation)
        recovery[id_key] = record["id"]
        write_json(directory / "state.json", state)
    else:
        recovery[start_key] = now()
        write_json(directory / "state.json", state)
        record = submit(root, operation, request)
        recovery[id_key] = record["id"]
        write_json(directory / "state.json", state)
    if record["status"] in ("queued", "failed") or record.get("observed_status") == "interrupted":
        record = run_job(root, record["id"])
    if record["status"] != "completed":
        raise ValueError("Saved local finishing job has not completed; inspect its job ID before continuing")
    return record, verify_manifest(Path(record["revision"]))


def _finish_clipping(root, directory, state, item, job, expected):
    """Recover only a downloaded take whose integer export explicitly failed for clipping."""
    if (job.get("error", {}).get("type") != "ValueError" or
            "Source would clip integer PCM" not in job.get("error", {}).get("message", "")):
        return None
    revision = Path(job["revision"])
    if (not _same_generation_request(job["request"], expected)
            or not _same_generation_request(read_json(revision / "request.json"), expected)):
        raise ValueError("Failed source job differs from the frozen demo request")
    if any(job["selection"].get(field) != expected[field] for field in ("provider", "model")):
        raise ValueError("Failed source job has a different provider or model")
    take = revision / "take-001"
    receipt_path = take / "remote.json"
    receipt = read_json(receipt_path)
    if receipt.get("state") != "downloaded":
        raise ValueError("Local finishing requires a confirmed downloaded provider response")
    raw = (take / receipt["file"]).resolve()
    if raw.parent != take.resolve() or digest(raw) != receipt["sha256"]:
        raise ValueError("Downloaded provider audio differs from its receipt")
    response_sha256 = None
    if receipt.get("response_file"):
        response = (take / receipt["response_file"]).resolve()
        response_sha256 = receipt.get("response_sha256")
        if response.parent != take.resolve() or not response_sha256 or digest(response) != response_sha256:
            raise ValueError("Saved provider response differs from its receipt")
    identity = {"source_job_id": job["id"], "source_job_status": "failed",
                "source_revision": str(revision), "source_raw": str(raw), "source_raw_sha256": digest(raw),
                "source_receipt_sha256": digest(receipt_path), "source_response_sha256": response_sha256}
    recovery = item.setdefault("local_finish", identity.copy())
    if any(recovery.get(key) != value for key, value in identity.items()):
        raise ValueError("Original failed generation changed after local finishing began")
    write_json(directory / "state.json", state)
    imported, manifest = _local_finish_job(root, directory, state, recovery, "import", ImportRequest(
        name=expected["name"] + "-float", source=str(raw), source_sha256=receipt["sha256"],
        kind="dialogue", provider=expected["provider"], model=expected["model"], transport="local",
        prompt=expected["prompt"], purpose=expected["purpose"], playback=expected["playback"],
        export={**expected["export"], "subtype": "FLOAT"},
        notes="Local recovery of downloaded raw after integer export clipping; original job " + job["id"],
    ))
    imported_revision = Path(imported["revision"])
    source = imported_revision / manifest["takes"][0]["file"]
    if "gain_db" not in recovery:
        peak = manifest["takes"][0]["analysis"]["peak_dbfs"]
        recovery["gain_db"] = min(0.0, -1.0 - peak) if peak is not None else 0.0
        write_json(directory / "state.json", state)
    finished, manifest = _local_finish_job(root, directory, state, recovery, "edit", EditRequest(
        name=expected["name"] + "-finished", source=str(source), source_sha256=digest(source),
        parent_revision=str(imported_revision), gain_db=recovery["gain_db"],
        export=expected["export"], notes="Reserve -1 dBFS peak headroom after preserved FLOAT conversion",
    ))
    recovery["status"] = "completed_local_finish"
    write_json(directory / "state.json", state)
    return finished, manifest, recovery


def collect(root: Path, directory: Path, catalog_path: Path | None = None):
    with FileLock(str(directory / ".demo.lock"), timeout=0):
        state = _state(directory)
        deliveries = root / ".assets/deliveries"
        folder = deliveries / ("character-dialogue-" + state["session"])
        folder.mkdir(parents=True, exist_ok=True)
        tracks, statuses = [], []
        for item in state["lines"]:
            if not item.get("job_id"):
                statuses.append({"provider": item["provider"], "mood": item["mood"], "status": "not_submitted"})
                continue
            job = get_job(root, item["job_id"])
            status = {"provider": item["provider"], "mood": item["mood"],
                      "job_id": job["id"], "status": job.get("observed_status", job["status"])}
            statuses.append(status)
            expected = read_json(directory / item["bound_spec"])
            if digest(directory / item["bound_spec"]) != item["bound_sha256"]:
                raise ValueError("Frozen generation specification changed")
            recovery = None
            if job["status"] == "failed":
                recovered = _finish_clipping(root, directory, state, item, job, expected)
                if recovered is None:
                    continue
                export_job, manifest, recovery = recovered
                revision = Path(export_job["revision"])
                status.update(status="completed_local_finish", source_job_status="failed",
                              import_job_id=recovery["import_job_id"], edit_job_id=recovery["edit_job_id"])
            elif job["status"] == "completed":
                revision = Path(job["revision"])
                manifest = verify_manifest(revision)
            else:
                continue
            if recovery is None and not _same_generation_request(manifest["request"], expected):
                raise ValueError("Completed job does not match this demo's frozen request")
            source_revision = revision
            processing = "none"
            if recovery is None and job.get("finishing_jobs"):
                deliveries_for_job = job.get("delivery_revisions", [])
                if len(deliveries_for_job) != 1:
                    raise ValueError("Expected one finished dialogue delivery for this demo line")
                revision = Path(deliveries_for_job[0])
                manifest = verify_manifest(revision)
                parent = manifest.get("parent") or {}
                if (manifest.get("operation") != "finish-dialogue"
                        or Path(parent.get("revision", "")) != source_revision
                        or parent.get("manifest_sha256") != digest(source_revision / "manifest.json")):
                    raise ValueError("Finished dialogue delivery is not bound to the original generation")
                processing = manifest["request"]["preset"]
            if len(manifest["takes"]) != 1 or manifest["generator"]["provider"] != item["provider"]:
                raise ValueError("Unexpected provider or take count in this dialogue demo")
            take = manifest["takes"][0]
            source = revision / take["file"]
            track_id = f"{item['provider']}-dialogue-{state['session']}-{item['mood']}"
            output, matched = folder / (track_id + ".wav"), folder / (track_id + "-matched.wav")
            sidecar = folder / (track_id + ".json")
            if output.exists():
                if digest(output) != take["sha256"]:
                    raise ValueError("Existing dialogue delivery changed; refusing to overwrite")
            else:
                shutil.copy2(source, output)
            if sidecar.exists():
                saved = read_json(sidecar)
                if saved["job_id"] != job["id"] or saved["sha256"] != digest(output):
                    raise ValueError("Dialogue sidecar belongs to a different result")
                if not matched.exists() or digest(matched) != saved["matched_sha256"]:
                    raise ValueError("Dialogue matched preview changed")
            else:
                # Local preview work is repeatable; no provider call occurs during collection.
                _matched(output, matched, load_settings(root).ffmpeg)
                saved = {"job_id": job["id"], "revision": str(revision), "source": str(source),
                         "source_revision": str(source_revision), "dialogue_processing": processing,
                         "manifest_sha256": digest(revision / "manifest.json"),
                         "sha256": digest(output), "matched_sha256": digest(matched),
                         "provider": item["provider"], "model": manifest["generator"]["model"],
                         "voice_id": expected["voice_id"], "text": item["text"], "style": item["style"],
                         "submitted_prompt": expected["prompt"], "profile_sha256":
                         state["voice"]["sha256"] if item["provider"] == "gemini" else None,
                         "analysis": measure(output), "matched_analysis": measure(matched),
                         "local_finish": recovery,
                         "target_lufs": -18, "listening": "unreviewed"}
                write_json(sidecar, saved)
            tracks.append({"id": track_id, "provider": item["provider"], "category": "dialogue",
                           "candidate": item["candidate"], "title": item["title"] + " · " +
                           ("Gemini" if item["provider"] == "gemini" else "ElevenLabs") +
                           (" · 밀도 강화" if processing == "density" else ""),
                           "description": item["text"], "display_order": item["order"],
                           "model": saved["model"], "duration": saved["analysis"]["duration_seconds"],
                           "original": output.relative_to(deliveries).as_posix(),
                           "matched": matched.relative_to(deliveries).as_posix()})
        if catalog_path and tracks:
            with FileLock(str(catalog_path) + ".lock", timeout=0):
                catalog = read_json(catalog_path) if catalog_path.exists() else {"providers": [], "tracks": []}
                for provider in {track["provider"] for track in tracks}:
                    entry = next((entry for entry in catalog["providers"] if entry["id"] == provider), None)
                    if entry is None:
                        entry = {"id": provider, "name": "Gemini" if provider == "gemini" else "ElevenLabs",
                                 "local": False, "categories": []}
                        catalog["providers"].append(entry)
                    if "dialogue" not in entry["categories"]:
                        entry["categories"].append("dialogue")
                by_id = {track["id"]: track for track in tracks}
                catalog["tracks"] = [by_id.pop(track["id"], track) for track in catalog["tracks"]]
                catalog["tracks"].extend(by_id.values())
                write_json(catalog_path, catalog)
        report = {"status": "completed" if len(tracks) == len(state["lines"]) else "pending",
                  "jobs": statuses, "collected": len(tracks), "expected": len(state["lines"]),
                  "delivery": str(folder), "listening": "unreviewed", "remote_calls": 0}
        write_json(directory / "collection.json", report)
        return report


def main():
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "generate", "collect"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--directory", default=".work/gemini-character-demo")
    parser.add_argument("--eleven-voice-id", help="Observed ElevenLabs voice ID; adds four comparison takes")
    parser.add_argument("--catalog", help="Optional existing read-only player's catalog path")
    args = parser.parse_args()
    root = args.root.resolve()
    directory = resolve(root, args.directory)
    if args.command == "prepare":
        result = prepare(root, directory, args.eleven_voice_id)
    elif args.command == "generate":
        result = generate(root, directory)
    else:
        result = collect(root, directory, resolve(root, args.catalog) if args.catalog else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

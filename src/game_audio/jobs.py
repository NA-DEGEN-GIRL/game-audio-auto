import hashlib
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import psutil
from filelock import FileLock, Timeout

from .audio import export_audio, process_edit
from .config import load_settings, plan
from .dialogue_finishing import finish_dialogue
from .elevenlabs import ElevenLabs, UnknownSubmission
from .gemini import Gemini
from .gemini import recover_saved as recover_gemini
from .local import generate_local
from .models import EditRequest, FinishDialogueRequest, GenerateRequest, ImportRequest, Playback, Review
from .storage import digest, job_path, new_revision, now, read_json, resolve, write_json


def alive(record):
    try:
        process = psutil.Process(record["pid"])
        return abs(process.create_time() - record["process_created"]) < 0.05 and process.is_running()
    except (psutil.Error, KeyError):
        return False


def snapshot(root, source, revision, expected=None, reuse=False):
    original = resolve(root, source)
    if not original.is_file():
        raise ValueError("Source audio does not exist")
    before = digest(original)
    if expected and before != expected:
        raise ValueError("Source hash does not match the requested file")
    target = revision / "source" / ("input" + original.suffix.lower())
    target.parent.mkdir(parents=True, exist_ok=reuse)
    if reuse and target.exists():
        if digest(target) != before:
            raise ValueError("Existing recovery snapshot differs; reconcile without overwriting it")
    else:
        shutil.copy2(original, target)
    if digest(target) != before or digest(original) != before:
        raise ValueError("Source changed during snapshot; no processing was started")
    return {"original_path": str(original), "snapshot": str(target), "sha256": before}


def submit(root: Path, operation: str, request, background=False):
    record = prepare_job(root, operation, request)
    return launch(root, record["id"]) if background else run_job(root, record["id"])


def prepare_job(root: Path, operation: str, request, *, fixed_id=None, fixed_revision=None):
    # Fixed locations are private to deterministic, local-only finishing children.
    if fixed_id and job_path(root, fixed_id).exists():
        record = read_json(job_path(root, fixed_id))
        if (record["operation"] != operation or record["request"] != request.model_dump()
                or Path(record["revision"]) != fixed_revision):
            raise ValueError("Finishing recovery record differs; reconcile it without a replacement")
        return record
    settings = load_settings(root)
    selection = None
    if operation == "generate":
        selection = plan(root, request, settings)
        if not selection["ready"]:
            raise ValueError("; ".join(selection["blockers"]))
    revision = fixed_revision or new_revision(root, request.name)
    if fixed_revision:
        revision.mkdir(parents=True, exist_ok=True)
    spec = request.model_dump()
    record = {"id": fixed_id or "j" + uuid.uuid4().hex[:24], "operation": operation, "status": "queued",
              "created_at": now(), "revision": str(revision), "request": spec,
              "selection": selection, "completed_takes": 0}
    if operation in ("edit", "import", "finish-dialogue"):
        record["source"] = snapshot(root, request.source, revision, request.source_sha256, bool(fixed_id))
        if operation in ("edit", "finish-dialogue"):
            original = resolve(root, request.source)
            # Bind an inferred parent to an observed exported take, not a caller-supplied label alone.
            for candidate in (original.parent, original.parent.parent):
                manifest_path = candidate / "manifest.json"
                if manifest_path.is_file():
                    manifest = read_json(manifest_path)
                    if any((candidate / take["file"]).resolve() == original
                           and take["sha256"] == record["source"]["sha256"]
                           for take in manifest.get("takes", [])):
                        record["parent"] = {"revision": str(candidate),
                                            "manifest_sha256": digest(manifest_path)}
                        break
            if request.parent_revision:
                expected_parent = resolve(root, request.parent_revision)
                if not record.get("parent") or expected_parent != Path(record["parent"]["revision"]):
                    raise ValueError("parent_revision must identify the manifest containing the actual source")
            if operation == "finish-dialogue" and record.get("parent"):
                parent = read_json(Path(record["parent"]["revision"]) / "manifest.json")
                if parent.get("kind") != "dialogue":
                    raise ValueError("Dialogue finishing requires a dialogue parent")
                if parent.get("operation") == "finish-dialogue":
                    raise ValueError("Finish the original dialogue revision, not an already finished child")
    elif request.reference_audio:
        record["source"] = snapshot(root, request.reference_audio, revision)
        spec["reference_audio"] = record["source"]["snapshot"]
    if selection and selection["provider"] not in ("elevenlabs", "gemini"):
        record["backend"] = settings.local_backends[selection["provider"]].model_dump()
    write_json(revision / "request.json", spec)
    write_json(job_path(root, record["id"]), record)
    return record


def get_job(root: Path, job_id: str):
    record = read_json(job_path(root, job_id))
    if record["status"] == "running" and not alive(record):
        # Read-only observation; run_job owns state mutations under the job lock.
        record["observed_status"] = "interrupted"
        record["note"] = "Worker is no longer alive; resume the saved job, do not submit a replacement"
    return record


def launch(root: Path, job_id: str):
    record = get_job(root, job_id)
    if record["status"] == "completed" or (record["status"] == "running" and alive(record)):
        return record
    revision = Path(record["revision"])
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    with (revision / "worker.log").open("ab") as log:
        child = subprocess.Popen(
            [sys.executable, "-m", "game_audio.cli", "--root", str(root), "_run", job_id],
            cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=environment,
            creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
            if os.name == "nt" else 0, start_new_session=os.name != "nt",
        )
    # The child alone writes its PID/state under the file lock, avoiding a completion race.
    return {"id": job_id, "status": "dispatched", "pid": child.pid,
            "revision": str(revision), "next": "job " + job_id}


def saved_raw(take: Path, receipt_name: str):
    receipt_path = take / receipt_name
    if not receipt_path.exists():
        return None
    receipt = read_json(receipt_path)
    if receipt.get("state") not in ("downloaded", "generated"):
        if receipt_name == "remote.json":
            raise UnknownSubmission("A paid attempt exists; reconcile its saved receipt before resuming")
        return None
    raw = take / receipt["file"]
    if not raw.is_file() or digest(raw) != receipt["sha256"]:
        raise ValueError("Saved provider audio is missing or changed; preserve and reconcile it")
    return raw, receipt


def generate_take(root, request, selection, take, settings, pending_takes):
    provider = selection["provider"]
    cached = recover_gemini(take) if provider == "gemini" else saved_raw(
        take, "remote.json" if provider == "elevenlabs" else "local.json")
    if cached:
        return cached
    # Freeze provider/model while checking current routing preferences and prerequisites.
    fixed = request.model_copy(update={"provider": provider, "model": selection["model"],
                                       "variants": pending_takes})
    current = plan(root, fixed, settings)
    if not current["ready"]:
        raise ValueError("; ".join(current["blockers"]))
    if provider == "gemini":
        if current.get("character_voice") != selection.get("character_voice"):
            raise ValueError("Bound Gemini voice profile changed; reconcile the saved job before generation")
        lock = root / ".assets/.locks/gemini.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(lock, timeout=3600):
            client = Gemini(root, settings)
            try:
                return client.generate(request, selection, take)
            finally:
                client.close()
    if provider != "elevenlabs":
        return generate_local(root, request, selection, take, settings)
    lock = root / ".assets/.locks/elevenlabs.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(lock, timeout=3600):
        client = ElevenLabs(root, settings)
        try:
            account = client.account()
            remaining = account["credits_remaining"]
            estimate = current["estimated_credits"]
            if remaining is None:
                raise ValueError("Account usage is unavailable; resolve read access before a paid request")
            if remaining <= 0 or (estimate is not None and remaining < estimate):
                raise ValueError("Remaining ElevenLabs credits are insufficient for the planned remaining takes")
            write_json(take / "account-before.json", {**account, "checked_at": now(),
                       "estimated_remaining_batch_credits": estimate})
            return client.generate(request, selection, take, settings.elevenlabs_output_format)
        finally:
            client.close()


def run_job(root: Path, job_id: str):
    path = job_path(root, job_id)
    lock = FileLock(str(path) + ".lock", timeout=0)
    try:
        with lock:
            record = read_json(path)
            if record["status"] == "completed":
                verify_manifest(Path(record["revision"]))
                for delivery in record.get("delivery_revisions", []):
                    verify_manifest(Path(delivery))
                return record
            record.update(status="running", pid=os.getpid(),
                          process_created=psutil.Process().create_time(), updated_at=now())
            record.pop("error", None)
            write_json(path, record)
            try:
                _execute(root, record, path)
            except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 - Persist every interrupted job.
                record.update(status="needs_reconciliation" if isinstance(error, UnknownSubmission) else "failed",
                              error={"type": type(error).__name__,
                                     "message": str(error) if isinstance(error, (ValueError, UnknownSubmission))
                                     else "Inspect the saved job inputs and backend log; no replacement was submitted"},
                              updated_at=now())
                write_json(path, record)
            return record
    except Timeout:
        record = get_job(root, job_id)
        record["note"] = "Another worker owns this job; no duplicate work started"
        return record


def _execute(root, record, path):
    settings = load_settings(root)
    revision = Path(record["revision"])
    manifest_path = revision / "manifest.json"
    if manifest_path.exists():
        manifest = verify_manifest(revision)
        complete_job(root, record, path, manifest)
        return
    operation = record["operation"]
    request_type = {"generate": GenerateRequest, "edit": EditRequest, "import": ImportRequest,
                    "finish-dialogue": FinishDialogueRequest}[operation]
    request = request_type.model_validate(record["request"])
    if record.get("source"):
        source = Path(record["source"]["snapshot"])
        if digest(source) != record["source"]["sha256"]:
            raise ValueError("Snapshotted source has changed")
    parent = None
    if record.get("parent"):
        parent_path = Path(record["parent"]["revision"]) / "manifest.json"
        if digest(parent_path) != record["parent"]["manifest_sha256"]:
            raise ValueError("Parent manifest changed")
        parent = read_json(parent_path)
    selection = record["selection"]
    if record.get("backend") and (settings.local_backends.get(selection["provider"]) is None or
        settings.local_backends[selection["provider"]].model_dump() != record["backend"]
    ):
        raise ValueError("Local backend configuration changed; restore the saved backend to resume")
    count = request.variants if operation == "generate" else 1
    takes = []
    for index in range(count):
        take = revision / f"take-{index + 1:03}"
        take.mkdir(exist_ok=True)
        checkpoint = take / "take.json"
        if checkpoint.exists():
            result = read_json(checkpoint)
            if digest(revision / result["file"]) != result["sha256"]:
                raise ValueError("Completed take has changed; do not overwrite it")
        else:
            output = take / "master.wav"
            if operation == "generate":
                variant = request.model_copy(update={"seed": (request.seed + index) % 4294967296, "variants": 1})
                raw, provenance = generate_take(root, variant, selection, take, settings, count - index)
                # Preserve resampling overshoot in FLOAT until the child applies measured headroom.
                raw_export = request.export.model_copy(update={"subtype": "FLOAT"}) if (
                    selection.get("dialogue_processing") == "density") else request.export
                analysis = export_audio(raw, output, raw_export, settings.ffmpeg)
                if raw_export != request.export:
                    provenance = {**provenance, "generation_export": raw_export.model_dump(),
                                  "export_note": "Unprocessed FLOAT parent; requested export applies to delivery child"}
            elif operation == "edit":
                analysis = process_edit(source, output, request, settings.ffmpeg)
                provenance = {"operation": "local_edit", "source": record["source"],
                              "parent": record.get("parent"), "settings": request.model_dump()}
            elif operation == "finish-dialogue":
                analysis, recipe = finish_dialogue(source, output, request, settings.ffmpeg)
                write_json(take / "finishing.json", recipe)
                provenance = {"operation": "local_dialogue_finishing", "source": record["source"],
                              "parent": record.get("parent"), "settings": request.model_dump(),
                              "recipe_file": "finishing.json", "recipe_sha256": digest(take / "finishing.json"),
                              "remote_posts": 0}
            else:
                analysis = export_audio(source, output, request.export, settings.ffmpeg)
                provenance = {"operation": "import", "provider": request.provider, "model": request.model,
                              "transport": request.transport, "request_id": request.request_id,
                              "source": record["source"], "notes": request.notes, "remote_posts": 0}
            result = {"file": output.relative_to(revision).as_posix(), "sha256": digest(output),
                      "provenance": provenance, "analysis": analysis,
                      "review_file": (take / "review.json").relative_to(revision).as_posix()}
            write_json(take / "analysis.json", analysis)
            write_json(take / "review.json", Review(audio_sha256=result["sha256"]).model_dump())
            write_json(checkpoint, result)
        takes.append(result)
        record.update(completed_takes=index + 1, updated_at=now())
        write_json(path, record)
    if operation == "generate":
        generator = {"provider": selection["provider"], "model": selection["model"],
                     "transport": "api" if selection["provider"] in ("elevenlabs", "gemini") else "local"}
    elif operation == "import":
        generator = {"provider": request.provider, "model": request.model, "transport": request.transport}
    else:
        generator = (parent or {}).get("generator", {"provider": "supplied", "model": "unknown"})
    playback = request.playback
    if playback is None:
        playback = Playback.model_validate((parent or {}).get("playback", {}))
        if operation == "edit" and request.loop_crossfade_seconds:
            playback.intent = "loop"
        if operation == "edit" and playback.sync_anchor_seconds is not None and (
            request.start_seconds or request.end_seconds is not None or request.loop_crossfade_seconds
        ):
            playback.sync_anchor_seconds = None
            playback.notes += " Timing changed; recheck the audio/gameplay synchronization anchor."
    manifest = {"schema_version": 1, "status": "completed", "name": request.name,
                "revision": revision.name, "operation": operation, "job_id": record["id"],
                "request_sha256": digest(revision / "request.json"), "request": request.model_dump(),
                "selection": selection, "source": record.get("source"), "parent": record.get("parent"),
                "kind": getattr(request, "kind", None) or ("dialogue" if operation == "finish-dialogue"
                                                          else (parent or {}).get("kind", "unknown")),
                "purpose": getattr(request, "purpose", "") or (parent or {}).get("purpose", ""),
                "generator": generator,
                "playback": playback.model_dump(), "takes": takes, "completed_at": now(),
                "completion_scope": "Files exported; consult hash-bound review sidecars for quality approval"}
    write_json(manifest_path, manifest)
    complete_job(root, record, path, manifest)


def complete_job(root, record, path, manifest):
    revision = Path(record["revision"])
    selection = record.get("selection") or {}
    delivery_revisions = [str(revision)]
    if record["operation"] == "generate" and selection.get("dialogue_processing") == "density":
        if manifest["kind"] != "dialogue":
            raise ValueError("Saved finishing selection requires dialogue")
        delivery_revisions = []
        finishing_jobs = []
        for index, take in enumerate(manifest["takes"], 1):
            # These stable identities recover local finishing even across a crash before the parent update.
            identity = hashlib.sha256(f'{record["id"]}:density:{index}'.encode()).hexdigest()[:24]
            child_revision = revision.with_name(revision.name + f"-density-{index:03}")
            request = FinishDialogueRequest(name=manifest["name"], source=str(revision / take["file"]),
                                            source_sha256=take["sha256"], parent_revision=str(revision),
                                            export=manifest["request"]["export"],
                                            notes="Automatic dialogue density finishing; original retained")
            child = prepare_job(root, "finish-dialogue", request, fixed_id="j" + identity,
                                fixed_revision=child_revision)
            finishing_jobs.append(child["id"])
            record["finishing_jobs"] = finishing_jobs
            write_json(path, record)
            child = run_job(root, child["id"])
            if child["status"] != "completed":
                raise ValueError("Local dialogue finishing is incomplete; resume this saved job. "
                                 "No additional generation is needed. Child: " + child["id"])
            delivery_revisions.append(str(child_revision))
    record.update(status="completed", manifest=str(revision / "manifest.json"),
                  delivery_revisions=delivery_revisions, updated_at=now())
    write_json(path, record)


def verify_manifest(revision: Path):
    manifest = read_json(revision / "manifest.json")
    if digest(revision / "request.json") != manifest["request_sha256"]:
        raise ValueError("Saved request changed")
    if manifest.get("source"):
        source = manifest["source"]
        if digest(Path(source["snapshot"])) != source["sha256"]:
            raise ValueError("Source snapshot changed")
    for take in manifest["takes"]:
        if digest(revision / take["file"]) != take["sha256"]:
            raise ValueError("Exported audio changed")
        provenance = take["provenance"]
        if provenance.get("operation") == "local_dialogue_finishing":
            recipe = (revision / take["file"]).parent / provenance["recipe_file"]
            if digest(recipe) != provenance["recipe_sha256"]:
                raise ValueError("Dialogue finishing recipe changed")
            saved_recipe = read_json(recipe)
            if (saved_recipe["source_sha256"] != manifest["source"]["sha256"]
                    or saved_recipe["output_sha256"] != take["sha256"]):
                raise ValueError("Dialogue finishing recipe does not match source/output")
            parent = manifest.get("parent")
            if parent and digest(Path(parent["revision"]) / "manifest.json") != parent["manifest_sha256"]:
                raise ValueError("Dialogue finishing parent manifest changed")
        if provenance.get("state") in ("downloaded", "generated"):
            raw = (revision / take["file"]).parent / provenance["file"]
            if digest(raw) != provenance["sha256"]:
                raise ValueError("Provider source changed")
            if provenance.get("provider") == "gemini":
                response = raw.parent / provenance["response_file"]
                if digest(response) != provenance["response_sha256"]:
                    raise ValueError("Gemini response provenance changed")
    return manifest


def record_review(revision: Path, take_number: int, review: Review):
    manifest = verify_manifest(revision)
    if not 1 <= take_number <= len(manifest["takes"]):
        raise ValueError("Take number is out of range")
    take = manifest["takes"][take_number - 1]
    if review.audio_sha256 != take["sha256"]:
        raise ValueError("Review does not match this audio revision")
    duration = take["analysis"]["duration_seconds"]
    if any(end > duration + 0.001 for _, end in review.listened_ranges_seconds):
        raise ValueError("Listening range exceeds this audio duration")
    path = revision / take["review_file"]
    if path.exists():
        archive = path.parent / "review-history" / (uuid.uuid4().hex + ".json")
        archive.parent.mkdir(exist_ok=True)
        shutil.copy2(path, archive)
    write_json(path, {**review.model_dump(), "recorded_at": now()})
    return {"review": str(path), "audio_sha256": take["sha256"], "listening": review.listening}

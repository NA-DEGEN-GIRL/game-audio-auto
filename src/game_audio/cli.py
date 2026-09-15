import argparse
import json
import sys
from pathlib import Path

from .audio import audition, measure
from .benchmark import adopt, create_plan
from .config import capabilities, load_settings, plan, save_settings
from .elevenlabs import ElevenLabs
from .jobs import get_job, launch, record_review, run_job, submit, verify_manifest
from .models import EditRequest, GenerateRequest, ImportRequest, Review
from .storage import read_json, resolve


def parser():
    cli = argparse.ArgumentParser(description="Generate, preserve, edit and review game audio")
    cli.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2],
                     help="Shared runtime directory (before subcommand)")
    sub = cli.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="Inspect prerequisites without generating")
    doctor.add_argument("--online", action="store_true", help="Read ElevenLabs subscription with configured key")
    mode = sub.add_parser("mode")
    mode.add_argument("value", choices=["auto", "only_local"])
    key = sub.add_parser("key-status", help="Record the key request state without receiving a secret")
    key.add_argument("value", choices=["not_asked", "requested", "declined", "configured"])
    for command in ("plan", "generate", "edit", "import"):
        item = sub.add_parser(command)
        item.add_argument("spec", type=Path)
        if command != "plan":
            item.add_argument("--async", dest="background", action="store_true")
    for command in ("job", "resume", "_run"):
        item = sub.add_parser(command)
        item.add_argument("job_id")
        if command == "resume":
            item.add_argument("--async", dest="background", action="store_true")
    sub.add_parser("account", help="Read subscription/usage only")
    voices = sub.add_parser("voices", help="Read available voices without creating one")
    voices.add_argument("--page-token")
    history = sub.add_parser("history", help="Read existing generation history")
    history.add_argument("--start-after")
    recovery = sub.add_parser("recover-history", help="Download an identified prior result; never resubmit")
    recovery.add_argument("job_id")
    recovery.add_argument("--take", type=int, required=True)
    recovery.add_argument("--history-id", required=True)
    analysis = sub.add_parser("analyze", help="Measure an existing PCM/WAV file; does not listen")
    analysis.add_argument("file", type=Path)
    preview = sub.add_parser("audition", help="Make listening/repetition previews without changing masters")
    preview.add_argument("files", type=Path, nargs="+")
    preview.add_argument("--output", type=Path, required=True)
    preview.add_argument("--repeat", type=int, default=1)
    preview.add_argument("--gap", type=float, default=0.5)
    preview.add_argument("--target-lufs", type=float)
    verify = sub.add_parser("verify", help="Check manifest/source/export hashes")
    verify.add_argument("revision", type=Path)
    review = sub.add_parser("review", help="Save actual listening/playback evidence")
    review.add_argument("revision", type=Path)
    review.add_argument("--take", type=int, required=True)
    review.add_argument("--spec", type=Path, required=True)
    benchmark = sub.add_parser("benchmark-plan", help="Write BGM comparison requests; generates no audio")
    benchmark.add_argument("--output", type=Path, required=True)
    benchmark.add_argument("--duration", type=float, default=30)
    benchmark.add_argument("--variants", type=int, default=2)
    adoption = sub.add_parser("adopt-music", help="Save a reviewed provider choice for a gameplay purpose")
    adoption.add_argument("revision", type=Path)
    adoption.add_argument("--take", type=int, required=True)
    adoption.add_argument("--purpose", required=True)
    adoption.add_argument("--evidence", required=True)
    return cli


def execute(args):
    root = args.root.expanduser().resolve()
    settings = load_settings(root)
    command = args.command
    if command == "doctor":
        report = capabilities(root, settings)
        if args.online:
            client = ElevenLabs(root, settings)
            try:
                report["elevenlabs"].update(account=client.account(), account_checked=True)
            finally:
                client.close()
        return report
    if command == "mode":
        settings.mode = args.value
        save_settings(root, settings)
        return capabilities(root, settings)
    if command == "key-status":
        settings.key_prompt = args.value
        if args.value == "declined":
            settings.mode = "only_local"
        save_settings(root, settings)
        return capabilities(root, settings)
    if command in ("plan", "generate", "edit", "import"):
        model = {"plan": GenerateRequest, "generate": GenerateRequest,
                 "edit": EditRequest, "import": ImportRequest}[command]
        request = model.model_validate(read_json(resolve(root, str(args.spec))))
        return plan(root, request, settings) if command == "plan" else submit(
            root, command, request, args.background)
    if command == "job":
        return get_job(root, args.job_id)
    if command in ("resume", "_run"):
        return launch(root, args.job_id) if getattr(args, "background", False) else run_job(root, args.job_id)
    if command in ("account", "voices", "history", "recover-history"):
        client = ElevenLabs(root, settings)
        try:
            if command == "voices":
                return client.voices(args.page_token)
            if command == "history":
                return client.history(args.start_after)
            if command == "account":
                return client.account()
            record = get_job(root, args.job_id)
            if record["operation"] != "generate" or record["selection"]["provider"] != "elevenlabs":
                raise ValueError("History recovery requires an ElevenLabs generation job")
            if not 1 <= args.take <= record["request"]["variants"]:
                raise ValueError("Take number is out of range")
            from filelock import FileLock

            from .storage import job_path
            with FileLock(str(job_path(root, args.job_id)) + ".lock", timeout=0):
                take = Path(record["revision"]) / f"take-{args.take:03}"
                return client.recover_history(take, args.history_id)
        finally:
            client.close()
    if command == "analyze":
        return measure(resolve(root, str(args.file)))
    if command == "audition":
        return audition([resolve(root, str(x)) for x in args.files], resolve(root, str(args.output)),
                        args.repeat, args.gap, args.target_lufs, settings.ffmpeg)
    if command == "verify":
        manifest = verify_manifest(resolve(root, str(args.revision)))
        return {"hashes_match": True, "takes": len(manifest["takes"]), "listening": "Consult review sidecars"}
    if command == "review":
        review = Review.model_validate(read_json(resolve(root, str(args.spec))))
        return record_review(resolve(root, str(args.revision)), args.take, review)
    if command == "benchmark-plan":
        return create_plan(resolve(root, str(args.output)), args.duration, args.variants)
    if command == "adopt-music":
        return adopt(root, args.purpose, resolve(root, str(args.revision)), args.take, args.evidence)
    raise ValueError("Unknown command")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        result = execute(parser().parse_args())
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 1 if result.get("status") in ("failed", "needs_reconciliation") else 0
    except Exception as error:  # noqa: BLE001 - CLI boundary must not expose credential-bearing HTTP errors.
        # API keys never appear in request specs; suppress external exception bodies/headers.
        from pydantic import ValidationError
        if isinstance(error, ValidationError):
            details = [{"field": ".".join(str(x) for x in e["loc"]), "message": e["msg"]}
                       for e in error.errors(include_input=False, include_url=False)]
            message = json.dumps(details, ensure_ascii=False)
        elif isinstance(error, (ValueError, FileNotFoundError, FileExistsError)):
            message = str(error)
        else:
            message = "Operation failed; inspect saved state and prerequisites before retrying"
        print(json.dumps({"error": type(error).__name__, "message": message}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

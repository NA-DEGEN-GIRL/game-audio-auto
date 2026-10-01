"""Add completed, verified generated or imported takes to the read-only player."""

import argparse
from pathlib import Path

from game_audio.audio import export_audio, measure, process_edit, run_ffmpeg
from game_audio.jobs import get_job, verify_manifest
from game_audio.models import EditRequest, Export
from game_audio.storage import digest, read_json, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("job_id")
    parser.add_argument("category", choices=["bgm", "crowd", "drop", "boss", "legendary"])
    parser.add_argument("--candidate-start", default="A", choices=list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    job = get_job(root, args.job_id)
    if job["status"] != "completed":
        raise SystemExit("Job has not completed; preserve it and check its status")
    revision = Path(job["revision"])
    manifest = verify_manifest(revision)
    start = ord(args.candidate_start)
    if start + len(manifest["takes"]) - 1 > ord("Z"):
        raise ValueError("Candidate labels exceed Z")
    provider = manifest["generator"]["provider"]
    deliveries = root / ".assets/deliveries"
    folder = deliveries / "themepark-comparison-20260915"
    catalog_path = folder / "catalog.json"
    catalog = read_json(catalog_path)
    target = {"bgm": -18, "crowd": -23, "drop": -18, "boss": -18, "legendary": -18}[args.category]
    entry = next(p for p in catalog["providers"] if p["id"] == provider)
    if args.category not in entry["categories"]:
        entry["categories"].append(args.category)
    previous_model = entry.get("models", {}).get(args.category, entry.get("model"))
    for old_track in catalog["tracks"]:
        if old_track["provider"] == provider and old_track["category"] == args.category:
            old_provenance = folder / (old_track["id"] + ".json")
            old_model = read_json(old_provenance).get("model") if old_provenance.exists() else previous_model
            if old_model:
                old_track.setdefault("model", old_model)
    entry.setdefault("models", {})[args.category] = manifest["generator"]["model"]
    for index, item in enumerate(manifest["takes"]):
        candidate = chr(start + index)
        track_id = f"{provider}-{args.category}-{candidate}"
        source = revision / item["file"]
        output = folder / f"{track_id}.wav"
        matched = folder / f"{track_id}-matched.wav"
        provenance = folder / f"{track_id}.json"
        if not provenance.exists():
            if output.exists() or matched.exists():
                raise ValueError("Partial comparison output exists; inspect before resuming")
            report = measure(source)
            # Reserve integer PCM headroom without changing the preserved float source.
            gain = min(0, -1 - report["peak_dbfs"]) if report["peak_dbfs"] is not None else 0
            export = Export(sample_rate=48000, channels="stereo", subtype="PCM_24")
            if gain:
                edit = EditRequest(name=track_id, source=str(source), gain_db=gain, export=export)
                final = process_edit(source, output, edit)
            else:
                final = export_audio(source, output, export)
            run_ffmpeg(["-y", "-i", str(output), "-af", f"loudnorm=I={target}:TP=-1:LRA=11",
                        "-ar", "48000", "-c:a", "pcm_s16le", str(matched)])
            write_json(provenance, {"job_id": args.job_id, "revision": str(revision),
                                   "source": str(source), "source_sha256": digest(source),
                                   "file": output.name, "sha256": digest(output),
                                   "matched": matched.name, "matched_sha256": digest(matched),
                                   "gain_db": gain, "target_lufs": target, "analysis": final,
                                   "matched_analysis": measure(matched),
                                   "provider": provider, "model": manifest["generator"]["model"],
                                   "seed": (manifest["request"]["seed"] + index
                                            if "seed" in manifest["request"] and
                                            item["provenance"].get("seed_sent", True) else None),
                                   "transport": manifest["generator"].get("transport", "local"),
                                   "request_id": (manifest["request"].get("request_id") or
                                                  item["provenance"].get("request-id") or
                                                  item["provenance"].get("x-request-id")),
                                   "song_id": item["provenance"].get("song-id"),
                                   "prompt": manifest["request"]["prompt"], "listening": "unreviewed"})
        record = read_json(provenance)
        if record["job_id"] != args.job_id or record["source_sha256"] != digest(source):
            raise ValueError("Comparison slot belongs to another generation; preserve it and use a new slot")
        if digest(output) != record["sha256"] or digest(matched) != record["matched_sha256"]:
            raise ValueError("Existing comparison files changed")
        track = {"id": track_id, "provider": provider, "category": args.category,
                 "model": record["model"],
                 "candidate": candidate, "duration": record["analysis"]["duration_seconds"],
                 "original": output.relative_to(deliveries).as_posix(),
                 "matched": matched.relative_to(deliveries).as_posix()}
        catalog["tracks"] = [t for t in catalog["tracks"] if t["id"] != track_id] + [track]
    write_json(catalog_path, catalog)
    print(f"Added {len(manifest['takes'])} verified {provider} {args.category} takes to the player")


if __name__ == "__main__":
    main()

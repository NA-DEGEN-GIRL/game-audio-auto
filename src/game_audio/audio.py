import math
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from .models import EditRequest, Export
from .storage import digest, write_json


def run_ffmpeg(arguments, executable=None):
    binary = executable or shutil.which("ffmpeg")
    if not binary:
        raise ValueError("FFmpeg is required for decoding/export; install it or configure ffmpeg")
    result = subprocess.run([binary, "-nostdin", "-hide_banner", "-loglevel", "error", *arguments],
                            capture_output=True, check=False)
    if result.returncode:
        raise ValueError("FFmpeg failed: " + result.stderr.decode("utf-8", errors="replace")[-1500:])


def decode(source: Path, output: Path, sample_rate=48000, channels="preserve", ffmpeg=None):
    if not source.is_file():
        raise ValueError("Audio source does not exist")
    output.parent.mkdir(parents=True, exist_ok=True)
    arguments = ["-y", "-i", str(source), "-vn", "-ar", str(sample_rate)]
    if channels != "preserve":
        arguments += ["-ac", "1" if channels == "mono" else "2"]
    run_ffmpeg([*arguments, "-c:a", "pcm_f32le", str(output)], ffmpeg)


def measure(path: Path):
    data, sr = sf.read(path, dtype="float32", always_2d=True)
    if not len(data) or not np.isfinite(data).all():
        raise ValueError("Audio is empty or contains non-finite samples")
    envelope = np.max(np.abs(data), axis=1)
    peak = float(envelope.max())
    audible = np.flatnonzero(envelope >= 10 ** (-50 / 20))
    rms = np.sqrt(np.mean(data.astype(np.float64) ** 2, axis=0))
    clipped = int(np.count_nonzero(np.abs(data) >= 0.9999))
    warnings = []
    if not len(audible):
        warnings.append("No samples above the -50 dBFS inspection threshold")
    if clipped:
        warnings.append("Samples near full scale; inspect for clipping")
    if abs(data.mean(axis=0)).max() > 0.01:
        warnings.append("DC offset exceeds 0.01 in a channel")
    return {
        "audio_sha256": digest(path), "sample_rate": sr, "channels": data.shape[1],
        "frames": len(data), "duration_seconds": len(data) / sr,
        "peak_dbfs": 20 * math.log10(peak) if peak else None,
        "rms_dbfs_per_channel": [20 * math.log10(float(x)) if x else None for x in rms],
        "dc_per_channel": data.mean(axis=0).astype(float).tolist(), "near_full_scale_samples": clipped,
        "first_above_threshold_seconds": float(audible[0] / sr) if len(audible) else None,
        "last_above_threshold_seconds": float(audible[-1] / sr) if len(audible) else None,
        "threshold_dbfs": -50, "boundary_step": float(np.max(np.abs(data[-1] - data[0]))),
        "warnings": warnings, "listening_review": "unreviewed",
        "loop_note": "Boundary sample difference alone does not establish a seamless or convincing loop",
    }


def export_audio(source: Path, output: Path, export: Export, ffmpeg=None):
    intermediate = output.with_name(output.stem + ".decode.wav")
    decode(source, intermediate, export.sample_rate, export.channels, ffmpeg)
    data, sr = sf.read(intermediate, dtype="float32", always_2d=True)
    if not np.isfinite(data).all() or not len(data):
        raise ValueError("Decoded audio is empty or non-finite")
    if export.subtype != "FLOAT" and np.max(np.abs(data)) >= 1:
        raise ValueError("Source would clip integer PCM; import as FLOAT then edit its gain")
    sf.write(output, data, sr, subtype=export.subtype)
    intermediate.unlink()
    return measure(output)


def process_edit(source: Path, output: Path, request: EditRequest, ffmpeg=None):
    intermediate = output.with_name("decoded-source.wav")
    decode(source, intermediate, request.export.sample_rate, request.export.channels, ffmpeg)
    data, sr = sf.read(intermediate, dtype="float32", always_2d=True)
    start = round(request.start_seconds * sr)
    end = round(request.end_seconds * sr) if request.end_seconds is not None else len(data)
    if start >= len(data) or end > len(data) or end <= start:
        raise ValueError("Trim range is outside the actual decoded audio")
    data = data[start:end].copy()
    gain = 10 ** (request.gain_db / 20)
    data *= gain
    fade_in = round(request.fade_in_seconds * sr)
    fade_out = round(request.fade_out_seconds * sr)
    if fade_in + fade_out > len(data):
        raise ValueError("Combined fades exceed the trimmed duration")
    if fade_in:
        data[:fade_in] *= np.linspace(0, 1, fade_in, dtype=np.float32)[:, None]
    if fade_out:
        data[-fade_out:] *= np.linspace(1, 0, fade_out, dtype=np.float32)[:, None]
    overlap = round(request.loop_crossfade_seconds * sr)
    if overlap:
        if overlap < 2 or overlap * 2 >= len(data):
            raise ValueError("Loop crossfade must be at least two samples and less than half the clip")
        ramp = np.linspace(0, 1, overlap, dtype=np.float32)[:, None]
        seam = data[-overlap:] * (1 - ramp) + data[:overlap] * ramp
        # Rotate the start past the overlap: the new loop is shorter by overlap samples.
        data = np.concatenate((data[overlap:-overlap], seam))
    if request.export.subtype != "FLOAT" and np.max(np.abs(data)) >= 1:
        raise ValueError("Edit would clip integer PCM; lower gain or deliberately export FLOAT")
    sf.write(output, data, sr, subtype=request.export.subtype)
    intermediate.unlink()
    report = measure(output)
    report["loop_crossfade_seconds"] = overlap / sr
    return report


def audition(sources: list[Path], output: Path, repeat=1, gap_seconds=0.5,
             target_lufs: float | None = None, ffmpeg=None):
    if not sources:
        raise ValueError("Audition needs at least one source")
    if output.exists() or output.with_suffix(".json").exists():
        raise ValueError("Audition output already exists; choose a new path")
    if repeat < 1 or repeat > 20 or not 0 <= gap_seconds <= 10:
        raise ValueError("repeat must be 1–20 and gap_seconds 0–10")
    if target_lufs is not None and not -40 <= target_lufs <= -5:
        raise ValueError("Audition target_lufs must be between -40 and -5")
    output.parent.mkdir(parents=True, exist_ok=True)
    work = output.parent / (output.stem + "-sources")
    work.mkdir(exist_ok=False)
    labels, cursor = [], 0
    sr = 48000
    with sf.SoundFile(output, "w", samplerate=sr, channels=2, subtype="PCM_24") as destination:
        for i, source in enumerate(sources):
            normalized = work / f"{i + 1:03}.wav"
            decode(source, normalized, sr, "stereo", ffmpeg)
            if target_lufs is not None:
                leveled = work / f"{i + 1:03}-level.wav"
                run_ffmpeg(["-y", "-i", str(normalized), "-af",
                            f"loudnorm=I={target_lufs}:TP=-1:LRA=11", "-ar", str(sr), str(leveled)], ffmpeg)
                normalized = leveled
            data, _ = sf.read(normalized, dtype="float32", always_2d=True)
            start = cursor / sr
            for _ in range(repeat):
                destination.write(data)
                cursor += len(data)
            labels.append({"label": chr(65 + i) if i < 26 else str(i + 1), "source": str(source),
                           "sha256": digest(source), "start_seconds": start, "end_seconds": cursor / sr,
                           "repeat": repeat})
            if i + 1 < len(sources):
                frames = round(gap_seconds * sr)
                destination.write(np.zeros((frames, 2), dtype=np.float32))
                cursor += frames
    metadata = {"audio": str(output), "sha256": digest(output), "labels": labels,
                "preview_only_target_lufs": target_lufs,
                "note": "Preview normalization does not alter masters or establish listening approval"}
    write_json(output.with_suffix(".json"), metadata)
    return metadata


def atomic_audio_replace(temporary: Path, final: Path):
    if not temporary.is_file() or temporary.stat().st_size == 0:
        raise ValueError("Backend did not produce a nonempty audio file")
    os.replace(temporary, final)

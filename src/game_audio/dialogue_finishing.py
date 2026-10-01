"""Conservative, reproducible dialogue finishing; no remote calls or fixed loudness target."""

import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from .audio import decode, measure, run_ffmpeg
from .models import FinishDialogueRequest
from .storage import digest


def loudness(path: Path, ffmpeg=None):
    binary = ffmpeg or shutil.which("ffmpeg")
    if not binary:
        raise ValueError("FFmpeg is required for dialogue finishing")
    result = subprocess.run([binary, "-nostdin", "-hide_banner", "-i", str(path), "-af",
                             "loudnorm=I=-23:TP=-1:LRA=11:print_format=json", "-f", "null", "-"],
                            capture_output=True, check=False)
    if result.returncode:
        raise ValueError("FFmpeg could not measure dialogue loudness/true peak")
    matches = re.findall(r"\{[^{}]*\}", result.stderr.decode("utf-8", errors="replace"), re.DOTALL)
    if not matches:
        raise ValueError("FFmpeg returned no dialogue loudness measurement")
    report = json.loads(matches[-1])
    values = {"integrated_lufs": float(report["input_i"]), "true_peak_dbtp": float(report["input_tp"])}
    # Silence/very short clips may not have a finite integrated-loudness estimate.
    return {key: value if math.isfinite(value) else None for key, value in values.items()}


def adaptive_threshold(source: Path):
    data, sr = sf.read(source, dtype="float64", always_2d=True)
    if not len(data) or not np.isfinite(data).all():
        raise ValueError("Dialogue source is empty or non-finite")
    frame = max(1, round(sr * 0.04))
    rms = [np.sqrt(np.mean(data[i:i + frame] ** 2))
           for i in range(0, max(1, len(data) - frame + 1), max(1, frame // 2))]
    db = 20 * np.log10(np.maximum(rms, 1e-12))
    active = db[db > max(-45, float(db.max()) - 35)]
    return float(np.clip(np.percentile(active, 90) - 5, -30, -12)) if len(active) else -30.0


def finish_dialogue(source: Path, output: Path, request: FinishDialogueRequest, ffmpeg=None):
    """Process FLOAT intermediates and apply attenuation only if true-peak headroom needs it."""
    source_hash = digest(source)
    decoded = output.with_name("finishing-source.wav")
    eq_output = output.with_name("finishing-eq.wav")
    processed = output.with_name("finishing-dynamics.wav")
    decode(source, decoded, request.export.sample_rate, request.export.channels, ffmpeg)
    source_analysis = measure(decoded)
    filters = (f"highpass=f=55:p=2,bass=f=170:t=q:w=0.707:g={request.low_shelf_db}:r=f64,"
               f"equalizer=f=2300:t=q:w=0.7:g={request.presence_db}:r=f64")
    run_ffmpeg(["-y", "-i", str(decoded), "-af", filters, "-c:a", "pcm_f32le", str(eq_output)], ffmpeg)
    threshold_db = adaptive_threshold(eq_output)
    dynamics = (f"acompressor=threshold={10 ** (threshold_db / 20):.9f}:ratio=2:attack=18:"
                "release=160:knee=2.5:detection=rms:makeup=1")
    run_ffmpeg(["-y", "-i", str(eq_output), "-af", dynamics, "-c:a", "pcm_f32le", str(processed)], ffmpeg)
    before = loudness(processed, ffmpeg)
    true_peak = before["true_peak_dbtp"]
    gain_db = min(0.0, -1.25 - true_peak) if true_peak is not None else 0.0
    data, sr = sf.read(processed, dtype="float64", always_2d=True)
    data *= 10 ** (gain_db / 20)
    if not np.isfinite(data).all() or len(data) != source_analysis["frames"]:
        raise ValueError("Dialogue finishing changed frame count or produced non-finite samples")
    if np.max(np.abs(data)) >= 1:
        raise ValueError("Dialogue finishing exceeded PCM headroom")
    sf.write(output, data, sr, subtype=request.export.subtype)
    analysis, after = measure(output), loudness(output, ffmpeg)
    if after["true_peak_dbtp"] is not None and after["true_peak_dbtp"] > -1.2:
        raise ValueError("Dialogue finishing did not retain -1.2 dBTP headroom")
    if digest(source) != source_hash:
        raise ValueError("Dialogue source changed during finishing")
    recipe = {
        "preset": "density", "recipe_version": 1, "implementation_sha256": digest(Path(__file__)),
        "source_sha256": source_hash, "output_sha256": digest(output),
        "filtergraph": filters + "," + dynamics,
        "eq": {"highpass_hz": 55, "low_shelf_hz": 170, "low_shelf_db": request.low_shelf_db,
               "presence_hz": 2300, "presence_q": 0.7, "presence_db": request.presence_db},
        "compressor": {"threshold_dbfs": threshold_db, "ratio": 2, "attack_ms": 18,
                       "release_ms": 160, "knee": 2.5, "detector": "rms", "makeup_linear": 1},
        "threshold_method": "40 ms RMS / 20 ms hop; active P90 minus 5 dB, bounded -30 to -12 dBFS",
        "headroom_gain_db": gain_db, "true_peak_ceiling_dbtp": -1.2,
        "before_headroom": before, "output_loudness": after,
        "source_frames_at_export_rate": source_analysis["frames"],
        "target_lufs": None, "pitch_or_duration_edits": False, "denoise_or_gate": False,
        "remote_calls": 0, "listening": "unreviewed",
    }
    # Keep only the immutable source snapshot, final master and recorded recipe.
    for intermediate in (decoded, eq_output, processed):
        intermediate.unlink()
    return analysis, recipe

"""Run inside the selected isolated model environment, not the core environment."""

import importlib.metadata
import json
import os
import shutil
import sys
from pathlib import Path


def main():
    context = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    output = Path(sys.argv[2])
    request, selected, backend = (context[key] for key in ("request", "selection", "backend"))
    provider = selected["provider"]
    import torch

    device = backend["device"]
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(request["seed"])
    if provider == "stable_audio":
        import soundfile as sf
        from stable_audio_3 import StableAudioModel

        model = StableAudioModel.from_pretrained(selected["model"], device=device,
                                                 model_half=device.startswith("cuda"))
        audio = model.generate(prompt=request["prompt"], duration=request["duration_seconds"],
                               seed=request["seed"], steps=request["steps"] or 8, batch_size=1)
        sf.write(output, audio[0].detach().cpu().float().numpy().T, model.model.sample_rate, subtype="FLOAT")
    elif provider == "qwen":
        import soundfile as sf
        from qwen_tts import Qwen3TTSModel

        dtype = torch.bfloat16 if device.startswith("cuda") else torch.float32
        model = Qwen3TTSModel.from_pretrained(selected["model"], device_map=device, dtype=dtype,
                                             attn_implementation="sdpa")
        language = {"ko": "Korean", "en": "English", "ja": "Japanese", "zh": "Chinese"}.get(
            request["language"], request["language"])
        params = {"text": request["prompt"], "language": language}
        if request["voice_mode"] == "clone":
            if request["instruction"]:
                raise ValueError("Qwen Base clone adapter does not accept acting instructions")
            audio, sr = model.generate_voice_clone(**params, ref_audio=request["reference_audio"],
                                                   ref_text=request["reference_text"],
                                                   x_vector_only_mode=not bool(request["reference_text"]))
        elif request["voice_mode"] == "design":
            if not request["instruction"]:
                raise ValueError("Voice design requires an instruction describing the voice")
            audio, sr = model.generate_voice_design(**params, instruct=request["instruction"])
        else:
            audio, sr = model.generate_custom_voice(**params, speaker=request["speaker"],
                                                    instruct=request["instruction"])
        sf.write(output, audio[0], sr, subtype="FLOAT")
    else:
        from acestep.handler import AceStepHandler
        from acestep.inference import GenerationConfig, GenerationParams, generate_music
        from acestep.llm_inference import LLMHandler

        if not backend["project_root"]:
            raise ValueError("ACE-Step requires its source/project_root for checkpoints")
        project = Path(backend["project_root"])
        if not project.is_absolute():
            project = Path(context["runtime_root"]) / project
        handler = AceStepHandler()
        status = handler.initialize_service(project_root=str(project), config_path=selected["model"],
                                            device=device, offload_to_cpu=True)
        if isinstance(status, tuple) and len(status) > 1 and status[1] is False:
            raise RuntimeError("ACE-Step model initialization failed")
        params = GenerationParams(caption=request["prompt"], lyrics="[Instrumental]" if request["instrumental"] else "",
                                  instrumental=request["instrumental"], duration=request["duration_seconds"],
                                  bpm=request["bpm"], keyscale=request["key"], seed=request["seed"],
                                  inference_steps=request["steps"] or (8 if "turbo" in selected["model"] else 50),
                                  shift=3.0 if "turbo" in selected["model"] else 1.0,
                                  thinking=False, use_cot_metas=False, use_cot_caption=False, use_cot_language=False)
        (output.parent / "ace-effective-params.json").write_text(json.dumps({
            "caption": params.caption, "bpm": params.bpm, "keyscale": params.keyscale,
            "duration": params.duration, "inference_steps": params.inference_steps,
            "shift": params.shift, "thinking": params.thinking,
        }, indent=2), encoding="utf-8")
        config = GenerationConfig(batch_size=1, audio_format="wav32", use_random_seed=False,
                                  seeds=[request["seed"]])
        result = generate_music(handler, LLMHandler(), params, config, save_dir=str(output.parent / "ace-output"))
        if not result.success or len(result.audios) != 1:
            raise RuntimeError("ACE-Step did not return one successful audio result")
        shutil.copyfile(result.audios[0]["path"], output)
    packages = {}
    for package in ("torch", "torchaudio", "transformers", "stable-audio-3", "qwen-tts", "ace-step"):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pass
    hf = Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface"))
    snapshots = [str(path.relative_to(hf)) for path in (hf / "hub").glob("models--*/snapshots/*") if path.is_dir()]
    metadata = {"model": selected["model"], "device": device, "packages": packages,
                "seed": request["seed"], "cached_model_snapshots": snapshots,
                "provenance_limit": "Cache inventory is not proof that every listed snapshot was used",
                "ace_lm_enabled": False if provider == "ace_step" else None}
    (output.parent / "backend-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

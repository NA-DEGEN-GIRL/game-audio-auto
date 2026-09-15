"""Install only a selected model backend. Does not download model weights or alter drivers."""

import argparse
import os
import subprocess
from pathlib import Path

from game_audio.config import load_settings, save_settings
from game_audio.models import LocalBackend
from game_audio.storage import digest, write_json

PINS = {
    "stable_audio": ("https://github.com/Stability-AI/stable-audio-3.git", "779434a908193105335fd8d833418603625b2859"),
    "qwen": ("https://github.com/QwenLM/Qwen3-TTS.git", "022e286b98fbec7e1e916cb940cdf532cd9f488e"),
    "ace_step": ("https://github.com/ace-step/ACE-Step-1.5.git", "ca1e85fe9430179831e6bc6be790c332190a3866"),
}


def run(args, cwd=None):
    environment = os.environ.copy()
    environment.pop("VIRTUAL_ENV", None)
    subprocess.run(args, cwd=cwd, env=environment, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=PINS)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--backend-root", type=Path, help="Separate model environment directory; keep core settings under --root")
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    url, pin = PINS[args.provider]
    home = (args.backend_root.resolve() if args.backend_root else root / ".runtime") / args.provider
    source = home / "source"
    if args.plan:
        print({"provider": args.provider, "source": url, "revision": pin, "directory": str(home),
               "weights": "Downloaded separately on first selected inference; some require provider access",
               "device": args.device, "inference_verified": False})
        return
    home.mkdir(parents=True, exist_ok=True)
    if source.exists():
        current = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
        if current != pin:
            raise SystemExit("Existing model checkout has a different revision; preserve it and resolve deliberately")
    else:
        run(["git", "init", str(source)])
        run(["git", "remote", "add", "origin", url], source)
        run(["git", "fetch", "--depth", "1", "origin", pin], source)
        run(["git", "checkout", "--detach", "FETCH_HEAD"], source)
    if args.provider == "ace_step":
        if not (source / "uv.lock").is_file():
            run(["uv", "lock", "--python", "3.12"], source)
        run(["uv", "sync", "--locked", "--python", "3.12"], source)
        environment = source / ".venv"
    else:
        package = "stable-audio-3" if args.provider == "stable_audio" else "qwen-tts"
        # Wheel metadata excludes upstream uv source-index overrides, which conflict
        # with this runtime's explicit CUDA 12.8 torch index on RTX 50-series GPUs.
        wheels = home / "wheels"
        wheels.mkdir(exist_ok=True)
        run(["uv", "build", "--wheel", "--out-dir", str(wheels)], source)
        wheel = next(wheels.glob(package.replace("-", "_") + "-*.whl"))
        dependency_path = wheel.relative_to(home).as_posix()
        index = "https://download.pytorch.org/whl/cu128" if args.device == "cuda" else "https://download.pytorch.org/whl/cpu"
        project = f'''[project]
name = "game-audio-{args.provider.replace('_', '-')}-runtime"
version = "0.0.1"
requires-python = ">=3.12,<3.13"
dependencies = ["{package}", "torch==2.7.1", "torchaudio==2.7.1"]

[[tool.uv.index]]
name = "torch-runtime"
url = "{index}"
explicit = true

[tool.uv.sources]
{package} = {{ path = "{dependency_path}" }}
torch = {{ index = "torch-runtime" }}
torchaudio = {{ index = "torch-runtime" }}
'''
        file = home / "pyproject.toml"
        if file.exists() and file.read_text(encoding="utf-8-sig").strip() != project.strip():
            raise SystemExit("Existing backend environment has different settings; preserve it and configure deliberately")
        file.write_text(project, encoding="utf-8")
        if not (home / "uv.lock").is_file():
            run(["uv", "lock", "--python", "3.12"], home)
        run(["uv", "sync", "--locked", "--python", "3.12"], home)
        environment = home / ".venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    settings = load_settings(root)
    settings.local_backends[args.provider] = LocalBackend(python=str(python), project_root=str(source), device=args.device)
    save_settings(root, settings)
    write_json(home / "installed.json", {"source": url, "revision": pin, "python": str(python),
                                        "device": args.device, "model_inference_verified": False,
                                        "dependency_lock": str((source if args.provider == "ace_step" else home) / "uv.lock")})
    if args.provider != "ace_step":
        write_json(home / "wheel.json", {"file": str(wheel), "sha256": digest(wheel), "source_revision": pin})
    print("Selected backend environment installed. Model access, weights and actual inference remain to be checked.")


if __name__ == "__main__":
    main()

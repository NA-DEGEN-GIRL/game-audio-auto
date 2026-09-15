"""Locate the linked runtime and forward CLI arguments without changing the caller's environment."""

import os
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[4]
    python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        raise SystemExit(f"Core runtime is not installed. Run uv sync --locked --python 3.12 in {root}")
    return subprocess.call([str(python), "-m", "game_audio.cli", "--root", str(root), *sys.argv[1:]],
                           cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())

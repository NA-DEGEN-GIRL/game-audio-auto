import os
import subprocess
import venv

import pytest

from game_audio.local import generate_local
from game_audio.models import GenerateRequest, LocalBackend, Settings


@pytest.mark.skipif(os.name == "nt", reason="POSIX virtualenv interpreter symlink regression")
@pytest.mark.parametrize("relative", [False, True])
def test_local_child_uses_configured_virtualenv_when_interpreter_is_symlink(tmp_path, monkeypatch, relative):
    environment = tmp_path / "backend-venv"
    venv.EnvBuilder(with_pip=False, symlinks=True).create(environment)
    python = environment / "bin/python"
    assert python.is_symlink()
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import json, sys\nfrom pathlib import Path\n"
        "output = Path(sys.argv[2])\noutput.write_bytes(b'local backend fixture')\n"
        "(output.parent / 'backend-metadata.json').write_text(json.dumps({'prefix': sys.prefix}))\n",
        encoding="utf-8",
    )
    actual_run = subprocess.run

    def run_probe(arguments, **kwargs):
        # Keep the real configured child interpreter; substitute only expensive ML inference.
        return actual_run([arguments[0], str(probe), *arguments[2:]], **kwargs)

    monkeypatch.setattr("game_audio.local.subprocess.run", run_probe)
    backend = LocalBackend(python=str(python.relative_to(tmp_path) if relative else python),
                           project_root=str(tmp_path), device="cpu")
    settings = Settings(local_backends={"stable_audio": backend})
    request = GenerateRequest(name="venv_probe", kind="sfx", prompt="Maintenance fixture", duration_seconds=1)
    take = tmp_path / "take"
    take.mkdir()
    _, receipt = generate_local(tmp_path, request, {"provider": "stable_audio", "model": "small-sfx"},
                                take, settings)
    assert receipt["metadata"]["prefix"] == str(environment)

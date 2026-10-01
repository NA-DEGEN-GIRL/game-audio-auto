"""Wrapper routing checks: bridge delegation versus the linked local runtime.

Subprocess, platform, ownership and file mode are injected or mocked, so these tests
never run a runtime, load a model, read a key or contact the network.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / ".agents/skills/game-audio/scripts/audioctl.py"
SKILL = "game-audio"
PRIVATE_FILE = 0o100600
GROUP_READABLE = 0o100644
SYMLINK = 0o120777


def load_wrapper():
    spec = importlib.util.spec_from_file_location("audioctl_bridge_under_test", WRAPPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # The main guard keeps the import side-effect free.
    return module


def key(path):
    return os.path.normcase(str(path))


class FakeStat:
    def __init__(self, mode, uid):
        self.st_mode = mode
        self.st_uid = uid


class FakePosixOS:
    """POSIX metadata view over real fixture paths, without touching deployment files."""

    def __init__(self, *, uid=1000, mode=PRIVATE_FILE, uid_overrides=None, mode_overrides=None, missing=()):
        self.uid = uid
        self.mode = mode
        self.uid_overrides = {key(item): value for item, value in (uid_overrides or {}).items()}
        self.mode_overrides = {key(item): value for item, value in (mode_overrides or {}).items()}
        self.missing = {key(item) for item in missing}

    def stat(self, path, follow_symlinks=True):
        text = key(path)
        if text in self.missing:
            raise FileNotFoundError(text)
        return FakeStat(self.mode_overrides.get(text, self.mode), self.uid_overrides.get(text, self.uid))

    def getuid(self):
        return self.uid


class FakeSubprocess:
    """Records forwarded commands without starting a process."""

    def __init__(self, returncode=0):
        self.calls = []
        self.returncode = returncode

    def run(self, command, **kwargs):
        self.calls.append((list(command), kwargs))
        return subprocess.CompletedProcess(command, self.returncode)

    def call(self, command, **kwargs):
        self.calls.append((list(command), kwargs))
        return self.returncode


@pytest.fixture
def wrapper(tmp_path, monkeypatch):
    # A developer's registered native runtime must not change these routing fixtures.
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "unregistered-home"))
    return load_wrapper()


@pytest.fixture
def fake_subprocess(wrapper, monkeypatch):
    fake = FakeSubprocess()
    monkeypatch.setattr(wrapper, "subprocess", fake)
    return fake


@pytest.fixture
def posix_os(wrapper, monkeypatch):
    """Install fabricated POSIX metadata; every test still injects os_name explicitly."""

    def install(**kwargs):
        fake = FakePosixOS(**kwargs)
        monkeypatch.setattr(wrapper, "os", fake)
        return fake

    return install


def write_descriptor(directory, payload):
    directory.mkdir(parents=True, exist_ok=True)
    descriptor = directory / "connection.json"
    descriptor.write_text(json.dumps(payload), encoding="utf-8")
    return descriptor


def bridge_dir(directory, *, enabled=(SKILL,), client_name="client.py", write_client=True, client=None):
    directory.mkdir(parents=True, exist_ok=True)
    client_path = directory / client_name
    if write_client:
        client_path.write_text("# deployed bridge client placeholder\n", encoding="utf-8")
    return write_descriptor(directory, {"client": str(client_path) if client is None else client,
                                        "enabled_skills": list(enabled)}), client_path


def runtime_root(tmp_path, platform):
    root = tmp_path / f"runtime-{platform}"
    python = root / ".venv" / ("Scripts/python.exe" if platform == "nt" else "bin/python")
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("placeholder interpreter\n", encoding="utf-8")
    return root, python


def test_windows_ignores_an_enabled_descriptor(wrapper, tmp_path, fake_subprocess):
    descriptor, client = bridge_dir(tmp_path / "bridge")
    root, python = runtime_root(tmp_path, "nt")
    environ = {"CODEX_WORKSPACE_SKILL_BRIDGE": str(descriptor)}
    assert wrapper.main(["doctor"], os_name="nt", environ=environ, root=root) == 0
    command, kwargs = fake_subprocess.calls[0]
    assert command == [str(python), "-m", "game_audio.cli", "--root", str(root), "doctor"]
    assert kwargs["cwd"] == root
    assert str(client) not in command


def test_local_runtime_without_a_descriptor(wrapper, tmp_path, fake_subprocess):
    root, python = runtime_root(tmp_path, "posix")
    environ = {"CODEX_HOME": str(tmp_path / "codex-home"), "HOME": str(tmp_path / "home")}
    assert wrapper.main(["job", "jabc"], os_name="posix", environ=environ, root=root) == 0
    command, kwargs = fake_subprocess.calls[0]
    assert command == [str(python), "-m", "game_audio.cli", "--root", str(root), "job", "jabc"]
    assert kwargs["cwd"] == root


def test_explicit_override_missing_path_is_a_configuration_error(wrapper, tmp_path, fake_subprocess):
    root, _ = runtime_root(tmp_path, "posix")
    environ = {"CODEX_WORKSPACE_SKILL_BRIDGE": str(tmp_path / "absent-connection.json")}
    with pytest.raises(SystemExit, match="Bridge configuration error"):
        wrapper.main(["doctor"], os_name="posix", environ=environ, root=root)
    assert fake_subprocess.calls == []


def test_discovered_malformed_descriptor_is_a_configuration_error(wrapper, tmp_path, fake_subprocess):
    directory = tmp_path / "codex-home" / "workspace-skill-bridge"
    directory.mkdir(parents=True)
    (directory / "connection.json").write_text("{not json", encoding="utf-8")
    root, _ = runtime_root(tmp_path, "posix")
    environ = {"CODEX_HOME": str(tmp_path / "codex-home")}
    with pytest.raises(SystemExit, match="not valid JSON"):
        wrapper.main(["doctor"], os_name="posix", environ=environ, root=root)
    assert fake_subprocess.calls == []


def test_descriptor_without_this_skill_keeps_the_local_runtime(wrapper, tmp_path, fake_subprocess):
    descriptor, _ = bridge_dir(tmp_path / "bridge", enabled=("3d-assets",))
    root, python = runtime_root(tmp_path, "posix")
    environ = {"CODEX_WORKSPACE_SKILL_BRIDGE": str(descriptor)}
    assert wrapper.main(["doctor"], os_name="posix", environ=environ, root=root) == 0
    assert fake_subprocess.calls[0][0] == [str(python), "-m", "game_audio.cli", "--root", str(root), "doctor"]


@pytest.mark.parametrize(
    ("mode", "uid", "match"),
    [
        (GROUP_READABLE, 1000, "group- or world-accessible"),
        (PRIVATE_FILE, 4321, "owned by the current user"),
        (SYMLINK, 1000, "symlink"),
    ],
)
def test_enabled_descriptor_must_be_a_private_owned_regular_file(
        wrapper, tmp_path, fake_subprocess, posix_os, mode, uid, match):
    descriptor, _ = bridge_dir(tmp_path / "bridge")
    posix_os(mode_overrides={descriptor: mode}, uid_overrides={descriptor: uid})
    root, _ = runtime_root(tmp_path, "posix")
    environ = {"CODEX_WORKSPACE_SKILL_BRIDGE": str(descriptor)}
    with pytest.raises(SystemExit, match=match):
        wrapper.main(["doctor"], os_name="posix", environ=environ, root=root)
    assert fake_subprocess.calls == []


def test_client_must_be_absolute_and_a_sibling(wrapper, tmp_path, fake_subprocess, posix_os):
    posix_os()
    root, _ = runtime_root(tmp_path, "posix")
    outside = tmp_path / "outside.py"
    outside.write_text("# outside the descriptor directory\n", encoding="utf-8")
    relative = write_descriptor(tmp_path / "relative", {"client": "client.py", "enabled_skills": [SKILL]})
    with pytest.raises(SystemExit, match="must be an absolute path"):
        wrapper.main(["doctor"], os_name="posix", environ={"CODEX_WORKSPACE_SKILL_BRIDGE": str(relative)},
                     root=root)
    foreign = write_descriptor(tmp_path / "foreign", {"client": str(outside), "enabled_skills": [SKILL]})
    with pytest.raises(SystemExit, match="must be a sibling"):
        wrapper.main(["doctor"], os_name="posix", environ={"CODEX_WORKSPACE_SKILL_BRIDGE": str(foreign)},
                     root=root)
    assert fake_subprocess.calls == []


@pytest.mark.parametrize(("mode", "match"), [(SYMLINK, "symlink"), (GROUP_READABLE, "group- or world")])
def test_client_must_be_a_private_symlink_free_file(wrapper, tmp_path, fake_subprocess, posix_os, mode, match):
    descriptor, client = bridge_dir(tmp_path / "bridge")
    posix_os(mode_overrides={client: mode})
    root, _ = runtime_root(tmp_path, "posix")
    environ = {"CODEX_WORKSPACE_SKILL_BRIDGE": str(descriptor)}
    with pytest.raises(SystemExit, match=match):
        wrapper.main(["doctor"], os_name="posix", environ=environ, root=root)
    assert fake_subprocess.calls == []


def test_missing_client_is_a_configuration_error(wrapper, tmp_path, fake_subprocess, posix_os):
    descriptor, client = bridge_dir(tmp_path / "bridge")
    client.unlink()
    posix_os(missing=[client])
    root, _ = runtime_root(tmp_path, "posix")
    environ = {"CODEX_WORKSPACE_SKILL_BRIDGE": str(descriptor)}
    with pytest.raises(SystemExit, match="cannot be inspected"):
        wrapper.main(["doctor"], os_name="posix", environ=environ, root=root)
    assert fake_subprocess.calls == []


def test_enabled_descriptor_delegates_the_same_arguments(wrapper, tmp_path, fake_subprocess, posix_os):
    descriptor, client = bridge_dir(tmp_path / "bridge", enabled=("3d-assets", SKILL))
    posix_os()
    root, _ = runtime_root(tmp_path, "posix")  # Present local runtime must not win.
    environ = {"CODEX_WORKSPACE_SKILL_BRIDGE": str(descriptor)}
    assert wrapper.main(["generate", "request.json", "--async"], os_name="posix", environ=environ, root=root) == 0
    command, kwargs = fake_subprocess.calls[0]
    assert command == [sys.executable, str(client), "--connection", str(descriptor), "run", SKILL, "--",
                       "generate", "request.json", "--async"]
    assert kwargs == {"check": False}


def test_client_failure_is_returned_instead_of_falling_back(wrapper, tmp_path, monkeypatch, posix_os):
    descriptor, client = bridge_dir(tmp_path / "bridge")
    posix_os()
    fake = FakeSubprocess(returncode=3)
    monkeypatch.setattr(wrapper, "subprocess", fake)
    root, _ = runtime_root(tmp_path, "posix")
    environ = {"CODEX_WORKSPACE_SKILL_BRIDGE": str(descriptor)}
    assert wrapper.main(["doctor"], os_name="posix", environ=environ, root=root) == 3
    assert [call[0][1] for call in fake.calls] == [str(client)]


def test_descriptor_without_a_client_field_uses_the_sibling_client(wrapper, tmp_path, fake_subprocess, posix_os):
    directory = tmp_path / "bridge"
    directory.mkdir()
    client = directory / "client.py"
    client.write_text("# deployed bridge client placeholder\n", encoding="utf-8")
    descriptor = write_descriptor(directory, {"enabled_skills": [SKILL]})
    posix_os()
    environ = {"CODEX_WORKSPACE_SKILL_BRIDGE": str(descriptor)}
    assert wrapper.main(["doctor"], os_name="posix", environ=environ) == 0
    assert fake_subprocess.calls[0][0][1] == str(client)


def test_discovery_uses_codex_home_then_the_user_profile(wrapper, tmp_path, fake_subprocess, posix_os):
    posix_os()
    codex_home = tmp_path / "codex-home"
    _, codex_client = bridge_dir(codex_home / "workspace-skill-bridge")
    assert wrapper.main(["doctor"], os_name="posix", environ={"CODEX_HOME": str(codex_home)}) == 0
    assert fake_subprocess.calls[0][0][1] == str(codex_client)
    home = tmp_path / "home"
    _, home_client = bridge_dir(home / ".codex" / "workspace-skill-bridge")
    assert wrapper.main(["doctor"], os_name="posix", environ={"HOME": str(home)}) == 0
    assert fake_subprocess.calls[1][0][1] == str(home_client)


def test_explicit_override_wins_over_codex_home(wrapper, tmp_path, fake_subprocess, posix_os):
    posix_os()
    codex_home = tmp_path / "codex-home"
    _, codex_client = bridge_dir(codex_home / "workspace-skill-bridge")
    explicit, explicit_client = bridge_dir(tmp_path / "explicit")
    environ = {"CODEX_WORKSPACE_SKILL_BRIDGE": str(explicit), "CODEX_HOME": str(codex_home)}
    assert wrapper.main(["doctor"], os_name="posix", environ=environ) == 0
    assert fake_subprocess.calls[0][0][1] == str(explicit_client)
    assert str(explicit_client) != str(codex_client)


def test_missing_local_runtime_reports_the_install_hint(wrapper, tmp_path):
    with pytest.raises(SystemExit, match="uv sync"):
        wrapper.main(["doctor"], os_name="posix", environ={"HOME": str(tmp_path / "home")},
                     root=tmp_path / "absent")
def register_fixture(wrapper, tmp_path, root, execution="auto"):
    environ = {"HOME": str(tmp_path / "home"), "CODEX_HOME": str(tmp_path / "codex")}
    path = wrapper.runtime_preferences(environ)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"version": 1, "root": str(root), "execution": execution}), encoding="utf-8")
    return environ


def test_registered_native_takes_priority_over_bridge(wrapper, tmp_path, fake_subprocess):
    native, python = runtime_root(tmp_path, "posix")
    environ = register_fixture(wrapper, tmp_path, native)
    environ["CODEX_WORKSPACE_SKILL_BRIDGE"] = str(tmp_path / "stale-bridge")
    assert wrapper.main(["doctor"], os_name="posix", environ=environ, root=tmp_path / "projection") == 0
    assert fake_subprocess.calls[0][0][0] == str(python)


def test_explicit_windows_still_works_with_native_registered(wrapper, tmp_path, fake_subprocess, posix_os):
    posix_os()
    native, _ = runtime_root(tmp_path, "posix")
    environ = register_fixture(wrapper, tmp_path, native)
    descriptor, client = bridge_dir(tmp_path / "bridge")
    environ["CODEX_WORKSPACE_SKILL_BRIDGE"] = str(descriptor)
    assert wrapper.main(["--execution", "windows", "job", "known-job"], os_name="posix", environ=environ) == 0
    command = fake_subprocess.calls[0][0]
    assert str(client) in command and command[-2:] == ["job", "known-job"]
    assert "--execution" not in command


def test_local_selection_ignores_broken_bridge(wrapper, tmp_path, fake_subprocess):
    native, python = runtime_root(tmp_path, "posix")
    environ = {"HOME": str(tmp_path / "home"), "CODEX_WORKSPACE_SKILL_BRIDGE": str(tmp_path / "missing")}
    assert wrapper.main(["--execution", "local", "doctor"], os_name="posix", environ=environ, root=native) == 0
    assert fake_subprocess.calls[0][0][0] == str(python)


def test_explicit_windows_never_silently_runs_native(wrapper, tmp_path, fake_subprocess):
    native, _ = runtime_root(tmp_path, "posix")
    environ = register_fixture(wrapper, tmp_path, native)
    with pytest.raises(SystemExit, match="no enabled bridge"):
        wrapper.main(["--execution", "windows", "generate", "request.json"], os_name="posix", environ=environ)
    assert fake_subprocess.calls == []


def test_missing_registered_native_never_falls_back(wrapper, tmp_path, fake_subprocess):
    environ = register_fixture(wrapper, tmp_path, tmp_path / "removed")
    with pytest.raises(SystemExit, match="uv sync"):
        wrapper.main(["generate", "request.json"], os_name="posix", environ=environ)
    assert fake_subprocess.calls == []


def test_registration_roundtrip_and_repair(wrapper, tmp_path, fake_subprocess, capsys):
    native, python = runtime_root(tmp_path, "posix")
    (native / "pyproject.toml").write_text("[project]", encoding="utf-8")
    environ = {"HOME": str(tmp_path / "home")}
    path = wrapper.runtime_preferences(environ)
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    assert wrapper.main(["runtime-configure", "--root", str(native)], os_name="posix", environ=environ) == 0
    assert json.loads(capsys.readouterr().out)["registered"]
    assert wrapper.main(["doctor"], os_name="posix", environ=environ) == 0
    assert fake_subprocess.calls[0][0][0] == str(python)


def test_runtime_status_does_not_run_any_job(wrapper, tmp_path, fake_subprocess, capsys):
    native, _ = runtime_root(tmp_path, "posix")
    environ = register_fixture(wrapper, tmp_path, native)
    assert wrapper.main(["runtime-status"], os_name="posix", environ=environ) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["local_installed"] and report["local_registered"]
    assert report["windows_bridge_enabled"] is False
    assert fake_subprocess.calls == []

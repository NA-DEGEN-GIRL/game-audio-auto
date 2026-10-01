"""Locate the linked runtime and forward CLI arguments without changing the caller's environment.

Select local or Windows execution explicitly, or register a native runtime for auto.
Without native registration, preserve the existing SSH-to-Windows bridge behavior.
See references/execution-setup.md and references/windows-bridge.md.
"""

import argparse
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

SKILL_NAME = "game-audio"
CLIENT_NAME = "client.py"
CONNECTION_NAME = "connection.json"


def descriptor_path(environ):
    """Return the registered descriptor to use, or None when no implicit descriptor exists.

    An explicit CODEX_WORKSPACE_SKILL_BRIDGE that does not exist is a configuration error.
    """
    explicit = environ.get("CODEX_WORKSPACE_SKILL_BRIDGE")
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise SystemExit(
                f"Bridge configuration error: CODEX_WORKSPACE_SKILL_BRIDGE points at {path}, "
                "which is not an existing descriptor file"
            )
        return absolute(path)
    candidates = []
    if environ.get("CODEX_HOME"):
        candidates.append(Path(environ["CODEX_HOME"]).expanduser() / "workspace-skill-bridge" / CONNECTION_NAME)
    home = environ.get("HOME") or environ.get("USERPROFILE")
    if home:
        candidates.append(Path(home).expanduser() / ".codex" / "workspace-skill-bridge" / CONNECTION_NAME)
    for candidate in candidates:
        if candidate.is_file():
            return absolute(candidate)
    return None


def absolute(path):
    """Return an absolute path without following a symlink in the final component."""
    return path.parent.resolve() / path.name


def file_problem(path, os_module):
    """Describe why a POSIX bridge file is untrusted, or return None when it is private."""
    try:
        info = os_module.stat(path, follow_symlinks=False)
    except (OSError, ValueError):
        return "cannot be inspected"
    if stat.S_ISLNK(info.st_mode):
        return "must not be a symlink"
    if not stat.S_ISREG(info.st_mode):
        return "must be a regular file"
    getuid = getattr(os_module, "getuid", None)
    if getuid is not None and info.st_uid != getuid():
        return "must be owned by the current user"
    if info.st_mode & 0o077:
        return "must not be group- or world-accessible; set mode 600"
    return None


def bridge_command(os_name, environ, arguments):
    """Return the bridge client argv when a descriptor enables this skill, else None."""
    if os_name == "nt":
        return None
    path = descriptor_path(environ)
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as error:
        raise SystemExit(f"Bridge configuration error: {path} cannot be read ({error})") from None
    try:
        descriptor = json.loads(text)
    except ValueError as error:
        raise SystemExit(f"Bridge configuration error: {path} is not valid JSON ({error})") from None
    if not isinstance(descriptor, dict):
        raise SystemExit(f"Bridge configuration error: {path} must contain a JSON object")
    enabled = descriptor.get("enabled_skills")
    if not isinstance(enabled, list) or SKILL_NAME not in enabled:
        return None
    problem = file_problem(path, os)
    if problem is not None:
        raise SystemExit(f"Bridge configuration error: {path} {problem}")
    raw_client = descriptor.get("client")
    if raw_client is None:
        client = path.parent / CLIENT_NAME
    else:
        client = Path(str(raw_client)).expanduser()
        if not client.is_absolute():
            raise SystemExit(
                f"Bridge configuration error: client {raw_client} in {path} must be an absolute path"
            )
        if client.parent != path.parent:
            raise SystemExit(f"Bridge configuration error: client {client} must be a sibling of {path}")
    problem = file_problem(client, os)
    if problem is not None:
        raise SystemExit(f"Bridge configuration error: client {client} {problem}")
    return [sys.executable, str(client), "--connection", str(path), "run", SKILL_NAME, "--", *arguments]


def runtime_preferences(environ):
    home = environ.get("HOME") or environ.get("USERPROFILE") or str(Path.home())
    directory = Path(environ.get("XDG_CONFIG_HOME") or (Path(home) / ".config"))
    return directory / "codex-skill-runtimes" / (SKILL_NAME + ".json")


def runtime_options(arguments, environ, runtime_root, os_name):
    """Resolve host selection before any runtime/API call; never retry elsewhere."""
    path = runtime_preferences(environ)
    preferences = {}
    if path.exists() and arguments[:1] != ["runtime-configure"]:
        try:
            preferences = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise SystemExit("Invalid runtime registration; use runtime-configure again.") from None
        if (not isinstance(preferences, dict) or preferences.get("version") != 1
                or preferences.get("execution") not in ("auto", "local", "windows")
                or not isinstance(preferences.get("root"), str)
                or not Path(preferences["root"]).is_absolute()):
            raise SystemExit("Invalid runtime registration; use runtime-configure again.")
    if arguments and arguments[0] == "runtime-configure":
        parser = argparse.ArgumentParser(description="Register this host's installed skill runtime.")
        parser.add_argument("--root", required=True)
        parser.add_argument("--execution", choices=("auto", "local", "windows"), default="auto")
        options = parser.parse_args(arguments[1:])
        root = Path(options.root).expanduser().resolve()
        python = root / ".venv" / ("Scripts/python.exe" if os_name == "nt" else "bin/python")
        if not python.is_file() or not (root / "pyproject.toml").is_file():
            raise SystemExit("Install the runtime with uv sync before registering this root.")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                json.dump({"version": 1, "root": str(root), "execution": options.execution}, stream)
            temporary.chmod(0o600)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        print(json.dumps({"registered": True, "root": str(root), "execution": options.execution}))
        return None
    execution = preferences.get("execution", "auto")
    arguments = list(arguments)
    if arguments and arguments[0] == "--execution":
        if len(arguments) < 3 or arguments[1] not in ("auto", "local", "windows"):
            raise SystemExit("Use --execution auto|local|windows before the runtime command.")
        execution, arguments = arguments[1], arguments[2:]
    registered = bool(preferences)
    local_root = Path(preferences["root"]) if registered else runtime_root
    if arguments == ["runtime-status"]:
        python = local_root / ".venv" / ("Scripts/python.exe" if os_name == "nt" else "bin/python")
        bridge_enabled, bridge_error = False, None
        try:
            bridge_enabled = bridge_command(os_name, environ, ["doctor"]) is not None
        except SystemExit as error:
            bridge_error = str(error)
        print(json.dumps({"skill": SKILL_NAME, "execution": execution, "local_root": str(local_root),
                          "local_installed": python.is_file(), "local_registered": registered,
                          "windows_bridge_enabled": bridge_enabled, "bridge_error": bridge_error,
                          "note": "Installation is not inference proof. Run doctor/plan on the selected host."}))
        return None
    return arguments, local_root, execution, registered


def main(argv=None, *, os_name=None, environ=None, root=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    os_name = os.name if os_name is None else os_name
    environ = os.environ if environ is None else environ
    runtime_root = Path(__file__).resolve().parents[4] if root is None else Path(root)
    options = runtime_options(arguments, environ, runtime_root, os_name)
    if options is None:
        return 0
    arguments, runtime_root, execution, registered = options
    if os_name != "nt" and (execution == "windows" or (execution == "auto" and not registered)):
        command = bridge_command(os_name, environ, arguments)
        if command is not None:
            return subprocess.run(command, check=False).returncode
        if execution == "windows":
            raise SystemExit("Windows execution requested but this skill has no enabled bridge. Check SSH skill settings.")
    python = runtime_root / ".venv" / ("Scripts/python.exe" if os_name == "nt" else "bin/python")
    if not python.is_file():
        raise SystemExit(f"Core runtime is not installed. Run uv sync --locked --python 3.12 in {runtime_root}")
    return subprocess.call([str(python), "-m", "game_audio.cli", "--root", str(runtime_root), *arguments],
                           cwd=runtime_root)


if __name__ == "__main__":
    raise SystemExit(main())

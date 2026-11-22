"""Versioned, local-only analytical environment for Machine Time on Windows.

Never relocate a venv, mutate previous releases, install globally, or use a
network package index. Publish a usable interpreter only after an import probe.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys

PANDAS = "2.2.3"
NUMPY = "2.1.3"
CACHE_KEY = f"cp311-{struct.calcsize('P') * 8}-pandas-{PANDAS}-numpy-{NUMPY}-v1"
PROBE = (
    "import sys,pandas,numpy; "
    "assert sys.version_info[:2] == (3,11) and sys.prefix != sys.base_prefix; "
    f"assert pandas.__version__ == '{PANDAS}' and numpy.__version__ == '{NUMPY}'"
)


def _plain(path: Path) -> bool:
    """Reject symlink/reparse paths, including directory junctions."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return True
    return not (stat.S_ISLNK(info.st_mode) or
                getattr(info, "st_file_attributes", 0) &
                getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _interpreter(env: Path) -> Path:
    return env / "Scripts" / "python.exe"


def _usable(env: Path) -> bool:
    py = _interpreter(env)
    try:
        if not all(_plain(p) for p in (env, py.parent, py)) or not py.is_file():
            return False
        return subprocess.run([str(py), "-I", "-B", "-c", PROBE],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=15, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


@contextmanager
def _environment_lock(path: Path):
    import msvcrt
    if not _plain(path):
        raise OSError("untrusted_environment_lock")
    with path.open("a+b") as stream:
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def _bootstrap(env: Path, wheels: Path) -> bool:
    py = _interpreter(env)
    if not py.is_file():
        subprocess.run([sys.executable, "-I", "-m", "venv", str(env)],
                       stdout=sys.stderr, check=True, timeout=180)
    subprocess.run([str(py), "-I", "-m", "pip", "--isolated", "install",
                    "--disable-pip-version-check", "--no-index",
                    "--find-links", str(wheels),
                    f"pandas=={PANDAS}", f"numpy=={NUMPY}"],
                   stdout=sys.stderr, check=True, timeout=300)
    return _usable(env)


def select_python(release: Path, app_data: Path) -> Path | None:
    legacy = release / ".wedge-python"
    root = app_data / "BybitScanner" / "MachineTime" / "python-envs"
    env = root / CACHE_KEY
    ready = env / ".machine-time-ready"
    wheels = release / "python-wheels"
    try:
        if not all(_plain(p) for p in (app_data, root.parent.parent,
                                       root.parent, root, env, ready)):
            raise OSError("untrusted_environment_path")
        if ready.is_file() and _usable(env):
            return _interpreter(env)
        # A previously published environment is never repaired in place:
        # another viewer may be running with it. Fall back instead.
        if not ready.exists() and wheels.is_dir() and _plain(wheels):
            root.mkdir(parents=True, exist_ok=True)
            with _environment_lock(root / (CACHE_KEY + ".lock")):
                if ready.is_file():
                    if _usable(env):
                        return _interpreter(env)
                elif not ready.exists() and (_usable(env) or _bootstrap(env, wheels)):
                    ready.touch(exist_ok=False)
                    return _interpreter(env)
    except (OSError, subprocess.SubprocessError):
        pass
    # Read-only compatibility with the current release's old private venv.
    # Never move or repair it, or alter existing local data.
    return _interpreter(legacy) if _usable(legacy) else None


def main() -> int:
    local = os.environ.get("LOCALAPPDATA")
    if os.name != "nt" or not local or sys.version_info[:2] != (3, 11):
        return 2
    py = select_python(Path.cwd(), Path(local))
    if py is None:
        print("Machine Time analytical environment unavailable; opening viewer only.",
              file=sys.stderr)
        return 2
    print(py)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

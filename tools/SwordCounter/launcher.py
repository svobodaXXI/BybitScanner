"""SwordCounter S4: start MetaScalp and SwordCounter as two independent processes.

``python -m tools.SwordCounter.launcher [--dry-run] [--metascalp-exe PATH]``

- MetaScalp is started from its installed location, exactly as its own shortcuts do (no
  arguments, working folder = its folder). If it is already running it is left alone.
- SwordCounter is started with the windowless interpreter. If it is already running it is
  left alone.
- Both are detached and never waited for: closing one does not affect the other.
- No administrator rights, no shell, no API keys on any command line. MetaScalp receives a
  scrubbed environment without the SwordCounter key variables; SwordCounter inherits the user
  environment where its keys live.
- An unknown MetaScalp location is reported as a blocker; nothing is guessed.
- It never touches MetaScalp settings, existing shortcuts or the BybitScanner runtime.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from tools.SwordCounter import single_instance

METASCALP_ENV = "SWORDCOUNTER_METASCALP_EXE"
METASCALP_IMAGE = "MetaScalp.exe"
SECRET_ENV = ("SWORDCOUNTER_BYBIT_API_KEY", "SWORDCOUNTER_BYBIT_API_SECRET")
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
EXIT_OK, EXIT_PARTIAL, EXIT_BLOCKED = 0, 1, 2


class MetaScalpNotFound(RuntimeError):
    """The MetaScalp executable is unknown or missing; the launcher will not guess."""


def find_metascalp(explicit: str | None = None, environ: Mapping[str, str] | None = None) -> Path:
    environ = os.environ if environ is None else environ
    candidate = explicit or environ.get(METASCALP_ENV)
    if not candidate:
        local = environ.get("LOCALAPPDATA")
        if not local:
            raise MetaScalpNotFound("LOCALAPPDATA is not set and no MetaScalp path was given")
        candidate = str(Path(local) / "MetaScalp" / "current" / METASCALP_IMAGE)
    path = Path(candidate)
    if path.name.lower() != METASCALP_IMAGE.lower() or not path.is_file():
        raise MetaScalpNotFound(f"MetaScalp executable not found: {path}")
    return path


def is_metascalp_running(run: Callable = subprocess.run) -> bool | None:
    """True/False from the local process list; None when it cannot be read (never guessed)."""
    try:
        result = run(["tasklist", "/FI", f"IMAGENAME eq {METASCALP_IMAGE}", "/FO", "CSV", "/NH"],
                     capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    wanted = f'"{METASCALP_IMAGE}"'.lower()
    return any(line.strip().lower().startswith(wanted) for line in result.stdout.splitlines())


def windowless_python(python: Path) -> Path:
    python = Path(python)
    sibling = python.with_name("pythonw.exe")
    return sibling if python.name.lower() == "python.exe" and sibling.is_file() else python


@dataclass(frozen=True)
class Deps:
    metascalp_running: Callable[[], bool | None]
    swordcounter_running: Callable[[], bool]
    popen: Callable
    environ: Mapping[str, str]


def live_deps() -> Deps:
    return Deps(metascalp_running=is_metascalp_running, swordcounter_running=single_instance.is_running,
                popen=subprocess.Popen, environ=os.environ)


def _scrubbed(environ: Mapping[str, str]) -> dict[str, str]:
    return {k: v for k, v in environ.items() if k.upper() not in SECRET_ENV}


def _spawn(deps: Deps, args: list, **kwargs) -> None:
    deps.popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
               close_fds=True, creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP, **kwargs)


def launch(root: Path, python: Path, metascalp_exe: Path, deps: Deps, *, dry_run: bool = False,
           out: Callable[[str], object] = print) -> int:
    """Start what is not running yet. Independent steps: one failure never blocks the other."""
    problems = 0
    prefix = "DRY-RUN: " if dry_run else ""

    running = deps.metascalp_running()
    if running is True:
        out("MetaScalp: уже запущен, второй экземпляр не запускается.\n")
    elif running is None:
        problems += 1
        out("MetaScalp: не удалось определить, запущен ли он; второй экземпляр не запускается.\n")
    else:
        out(f"{prefix}MetaScalp: запуск {metascalp_exe}\n")
        if not dry_run:
            try:
                _spawn(deps, [str(metascalp_exe)], cwd=str(metascalp_exe.parent),
                       env=_scrubbed(deps.environ))
            except OSError as error:
                problems += 1
                out(f"MetaScalp: не запущен ({type(error).__name__}).\n")

    if deps.swordcounter_running():
        out("SwordCounter: уже запущен, второй экземпляр не запускается.\n")
    else:
        out(f"{prefix}SwordCounter: запуск {python} -m tools.SwordCounter (папка {root})\n")
        if not dry_run:
            try:
                _spawn(deps, [str(python), "-m", "tools.SwordCounter"], cwd=str(root))
            except OSError as error:
                problems += 1
                out(f"SwordCounter: не запущен ({type(error).__name__}).\n")
    return EXIT_PARTIAL if problems else EXIT_OK


def _report(message: str) -> None:
    """Console when there is one, a message box for the windowless shortcut launch."""
    if sys.stdout is not None:
        sys.stdout.write(message)
        return
    if sys.platform == "win32" and message.strip():
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message.strip(), "MetaScalp + Мечи", 0x40)
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="SwordCounter launcher")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--metascalp-exe")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    python = windowless_python(Path(sys.executable))
    messages: list[str] = []
    try:
        exe = find_metascalp(args.metascalp_exe)
    except MetaScalpNotFound as error:
        messages.append(f"БЛОКЕР: {error}\n")
        exe = None
    if exe is None:
        # Unknown MetaScalp location: report the blocker and start nothing.
        code = EXIT_BLOCKED
    else:
        code = launch(root, python, exe, live_deps(), dry_run=args.dry_run, out=messages.append)
    if code or args.dry_run:
        _report("".join(messages))
    return code


if __name__ == "__main__":
    sys.exit(main())

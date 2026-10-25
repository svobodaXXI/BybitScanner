"""Offline prepare/validate-only check for a Linux VPS (issue #624). Never starts anything.

Usage (as root, from the repository root, with the existing project venv)::

    /opt/BybitScanner/venv/bin/python -m tools.vps_check

It only reads files, installed-package metadata and *read-only* system state (``systemctl show``,
``nginx -T``, ``ss -ltn``). It does **not**: import the PAPER backend, Scanner, Robot, Autopilot
or Telegram modules; connect to Bybit or any remote host; open, create or migrate the PAPER DB;
start, enable or reload any unit or service. Secret values are never printed (only key names).

Verdict: ``OK`` (exit 0) only when every check ran on Linux against the *installed* units, the
*effective* environment and the *effective* nginx configuration and passed. ``INCOMPLETE`` (exit 2)
when installed-state checks were skipped or could not run; ``FAILED`` (exit 1) otherwise.
``--pre-start`` is the backend unit's ExecStartPre gate: it runs inside systemd, so the process
environment *is* the effective unit environment.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib.metadata
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
from typing import Callable, Iterable, Mapping

from tools.runtime_intent import (
    DEFAULT_BACKEND_URL,
    DEFAULT_TELEGRAM_PORT,
    PAPER_SAFE_BACKEND_ENV,
    PROJECT_ROOT,
    expected_database_identity,
)

MIN_PYTHON = (3, 12)
SERVICE_USER = "bybitscanner"
ENV_FILE = Path("/etc/bybitscanner/paper.env")
STATE_DIR = Path("/var/lib/bybitscanner")              # systemd StateDirectory: PAPER DB + its side files
UNITS = ("bybitscanner-paper-backend.service", "bybitscanner-telegram.service")
UNIT_DIR = Path("deploy/systemd")
NGINX_LOOPBACK = Path("deploy/nginx/bybitscanner-loopback.conf")
NGINX_SITE = Path("/etc/nginx/sites-enabled/bybitscanner")
# Gitignored, repository-relative runtime outputs the services write (nothing tracked).
WRITE_TARGETS = ("runtime", "charts", "debug", "review_queue", "reports", "signals_history.json")
# Ports that must never listen on a non-loopback address on this host.
GUARDED_PORTS = (80, 443, 8080, 8765, int(DEFAULT_TELEGRAM_PORT))
# Owner-only switches that must stay off on a prepare-only server.
OFF_SWITCHES = ("BYBITSCANNER_MIRROR_STANDALONE_ROBOT",)
# Keys whose *value* is secret: reported as set/unset only.
SECRET_KEY = re.compile(r"(TOKEN|SECRET|API_KEY|PASSWORD)", re.IGNORECASE)
_FALSE = {"", "0", "false", "no", "off"}
_LOOPBACK = re.compile(r"^(127\.\d+\.\d+\.\d+|\[::1\]|::1|localhost)(:\d+)?$")

Runner = Callable[..., subprocess.CompletedProcess]


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def _run(run: Runner, argv: list[str]) -> subprocess.CompletedProcess:
    return run(argv, capture_output=True, text=True, timeout=30)


def parse_env_lines(lines: Iterable[str]) -> dict[str, str]:
    """``KEY=VALUE`` lines as systemd ``EnvironmentFile`` reads them (comments/blank ignored)."""
    values: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith(("#", ";")) or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def parse_env_file(path: Path) -> dict[str, str]:
    return parse_env_lines(path.read_text(encoding="utf-8").splitlines())


# --- interpreter, packages, environment ---------------------------------------------------------

def check_python(version: tuple[int, ...] = tuple(sys.version_info[:3]), prefix: str = sys.prefix,
                 base_prefix: str = sys.base_prefix) -> list[Check]:
    return [
        Check("python_version", tuple(version[:2]) >= MIN_PYTHON,
              f"{'.'.join(map(str, version))} (need >= {'.'.join(map(str, MIN_PYTHON))})"),
        Check("python_venv", prefix != base_prefix, f"sys.prefix={prefix}"),
    ]


def check_requirements(root: Path,
                       version_of: Callable[[str], str] = importlib.metadata.version) -> list[Check]:
    """Installed distributions vs the pinned ``requirements.txt`` -- metadata only, nothing imported."""
    missing, mismatched = [], []
    for raw in (root / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or "==" not in line:
            continue
        name, pinned = (part.strip() for part in line.split("==", 1))
        try:
            installed = version_of(name)
        except importlib.metadata.PackageNotFoundError:
            missing.append(name)
            continue
        if installed != pinned:
            mismatched.append(f"{name} {installed}!={pinned}")
    detail = "all pinned packages installed" if not (missing or mismatched) else \
        f"missing={missing} mismatched={mismatched}"
    return [Check("requirements", not missing and not mismatched, detail)]


def check_safety_env(env: Mapping[str, str], source: str) -> list[Check]:
    """LIVE gates and the operator token stay off (the same keys the bootstrap forces off)."""
    checks = []
    for key, safe in PAPER_SAFE_BACKEND_ENV.items():
        value = str(env.get(key, "")).strip()
        ok = value.lower() in _FALSE or value == safe
        shown = ("<set>" if value else "<unset>") if SECRET_KEY.search(key) else (value or "<unset>")
        checks.append(Check(f"{source}:{key}", ok, shown))
    for key in OFF_SWITCHES:
        value = str(env.get(key, "")).strip()
        checks.append(Check(f"{source}:{key}", value != "1", value or "<unset>"))
    return checks


def check_paper_db(root: Path, env: Mapping[str, str],
                   exists: Callable[[Path], bool] = Path.exists) -> list[Check]:
    """Report the DB path and identity the runtime would use; never open or create it."""
    raw = Path(env.get("BYBITSCANNER_PAPER_DB") or "paper_runtime.sqlite3")
    path = raw if raw.is_absolute() else root / raw
    identity = expected_database_identity(root, env)
    present = [p.name for p in (path, Path(f"{path}-wal"), Path(f"{path}-shm")) if exists(p)]
    return [Check("paper_db_not_transferred", not present,
                  f"path={path} identity={identity[:16]} present={present or 'none'}")]


def check_ports(host: str = "127.0.0.1", ports: Iterable[int] = (8765, int(DEFAULT_TELEGRAM_PORT)),
                connect: Callable[..., socket.socket] | None = None) -> list[Check]:
    """Loopback only: a listener on 8765/8766 means a backend or Telegram worker is running."""
    connect = connect or socket.create_connection
    checks = []
    for port in ports:
        try:
            connect((host, port), timeout=0.5).close()
            listening = True
        except OSError:
            listening = False
        checks.append(Check(f"port_{port}_free", not listening, "listening" if listening else "free"))
    return checks


# --- unit files -------------------------------------------------------------------------------

def _unit_sections(text: str) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1], {})
        elif current is not None and "=" in line:
            key, value = line.split("=", 1)
            current[key.strip()] = value.strip()
    return sections


def unit_problems(text: str, entry: str, *, check_interpreter: bool) -> list[str]:
    """The unit contract: cannot be enabled, never restarts, PAPER entrypoint, existing interpreter."""
    sections = _unit_sections(text)
    service = sections.get("Service", {})
    problems = []
    if "Install" in sections:
        problems.append("has [Install] (could be enabled)")
    if service.get("Restart", "no") != "no":
        problems.append(f"Restart={service.get('Restart')}")
    if entry not in service.get("ExecStart", ""):
        problems.append("unexpected ExecStart")
    if service.get("EnvironmentFile", "").lstrip("-") != ENV_FILE.as_posix():
        problems.append(f"EnvironmentFile={service.get('EnvironmentFile')}")
    interpreter = (service.get("ExecStart", "").split() or [""])[0]
    if check_interpreter and not Path(interpreter).exists():
        problems.append(f"interpreter {interpreter} not found on this host")
    problems += stop_contract_problems(service, entry, unit=sections.get("Unit", {}))
    return problems


# Issue #627: a plain signal is not a safe stop. The backend stops only through the canonical owner
# safe-stop (ExecStop); when that is blocked the stop signal must be harmless and SIGKILL disabled.
_SAFE_STOP = "-m tools.stop_robot_runtime all"
_HARMLESS_STOP_SIGNALS = {"SIGCONT"}


def stop_contract_problems(service: Mapping[str, str], entry: str, *,
                           unit: Mapping[str, str] | None = None) -> list[str]:
    problems = []
    unit = unit or {}
    if "paper_http_server" in entry:
        if unit.get("RefuseManualStop", "no") not in {"yes", "true", "1", "on"}:
            problems.append("RefuseManualStop is not yes (a manual stop job could untrack a protected backend)")
        if _SAFE_STOP not in service.get("ExecStop", ""):
            problems.append("ExecStop is not the canonical safe-stop (tools.stop_robot_runtime all)")
        if service.get("KillSignal", "SIGTERM") not in _HARMLESS_STOP_SIGNALS:
            problems.append(f"KillSignal={service.get('KillSignal', 'SIGTERM')} would end the backend after a blocked safe-stop")
        if service.get("SendSIGKILL", "yes") != "no":
            problems.append("SendSIGKILL is not disabled")
        if service.get("KillMode", "control-group") == "none":
            problems.append("KillMode=none")
    else:
        if service.get("KillMode", "control-group") != "process":
            problems.append("KillMode is not process (the detached stop helper would be reaped with the worker)")
        if "ExecStop" in service:
            problems.append("unexpected ExecStop on the Telegram worker")
    return problems


_ENTRIES = {"bybitscanner-paper-backend.service": "-m terminal.runtime.paper_http_server",
            "bybitscanner-telegram.service": "telegram_monitoring.py"}


def check_repo_units(root: Path, *, check_interpreter: bool = False) -> list[Check]:
    checks = []
    for unit, entry in _ENTRIES.items():
        path = root / UNIT_DIR / unit
        if not path.exists():
            checks.append(Check(f"unit_file:{unit}", False, "missing"))
            continue
        problems = unit_problems(path.read_text(encoding="utf-8"), entry, check_interpreter=check_interpreter)
        checks.append(Check(f"unit_file:{unit}", not problems, "; ".join(problems) or "static, Restart=no"))
    return checks


def _show(run: Runner, unit: str) -> dict[str, str]:
    props = "LoadState,UnitFileState,ActiveState,FragmentPath,DropInPaths,EnvironmentFiles,Environment"
    out = _run(run, ["systemctl", "show", unit, f"--property={props}", "--no-pager"]).stdout
    show: dict[str, str] = {}
    for line in out.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        # A property may repeat (one line per EnvironmentFiles entry): keep them all, one per line.
        if key in show and show[key] and value:
            show[key] = show[key] + "\n" + value
        else:
            show[key] = value or show.get(key, "")
    return show


def check_installed_units(root: Path, *, run: Runner = subprocess.run,
                          which: Callable[[str], str | None] = shutil.which,
                          read: Callable[[Path], str] = lambda p: p.read_text(encoding="utf-8")) -> list[Check]:
    """The *installed* units as systemd resolves them (read-only ``systemctl show``)."""
    if which("systemctl") is None:
        return [Check("systemd", False, "systemctl not found")]
    checks = []
    for unit, entry in _ENTRIES.items():
        show = _show(run, unit)
        name = f"installed_unit:{unit}"
        if show.get("LoadState") != "loaded":
            checks.append(Check(name, False, f"LoadState={show.get('LoadState') or '?'} (not installed)"))
            continue
        problems = []
        if show.get("UnitFileState") in {"enabled", "enabled-runtime", "linked", "linked-runtime", "alias"}:
            problems.append(f"UnitFileState={show.get('UnitFileState')}")
        if show.get("ActiveState") in {"active", "activating", "reloading", "deactivating"}:
            problems.append(f"ActiveState={show.get('ActiveState')}")
        if show.get("DropInPaths", "").strip():
            problems.append(f"drop-ins present: {show['DropInPaths']}")
        fragment = Path(show.get("FragmentPath", ""))
        try:
            text = read(fragment)
        except OSError:
            text = None
            problems.append(f"FragmentPath {fragment} unreadable")
        if text is not None:
            if text.replace("\r\n", "\n") != read(root / UNIT_DIR / unit).replace("\r\n", "\n"):
                problems.append(f"{fragment} differs from {UNIT_DIR / unit}")
            problems += unit_problems(text, entry, check_interpreter=True)
        files = [item.split(" (", 1)[0].lstrip("-") for item in show.get("EnvironmentFiles", "").split("\n")
                 if item.strip()]
        if files != [ENV_FILE.as_posix()]:
            problems.append(f"EnvironmentFiles={files or 'none'}")
        checks.append(Check(name, not problems,
                            "; ".join(problems) or f"static, {show.get('ActiveState')}, no drop-ins"))
        # Effective environment = env file(s) + inline Environment= (inline wins).
        effective: dict[str, str] = {}
        for path in files:
            try:
                effective.update(parse_env_lines(read(Path(path)).splitlines()))
            except OSError:
                checks.append(Check(f"effective_env:{unit}", False, f"{path} unreadable"))
        effective.update(parse_env_lines(show.get("Environment", "").split()))
        checks += check_safety_env(effective, f"effective:{unit}")
    return checks


# --- nginx and listening sockets ---------------------------------------------------------------

def _listens(config: str) -> list[str]:
    return [item.split()[0] for item in re.findall(r"^\s*listen\s+([^;]+);", config, re.MULTILINE)]


def check_repo_nginx(root: Path) -> list[Check]:
    path = root / NGINX_LOOPBACK
    if not path.exists():
        return [Check("nginx_repo_loopback", False, "missing")]
    text = path.read_text(encoding="utf-8")
    listens = _listens(text)
    ok = bool(listens) and all(_LOOPBACK.match(item) for item in listens) and \
        f"proxy_pass {DEFAULT_BACKEND_URL}" in text
    return [Check("nginx_repo_loopback", ok, f"listen={listens}")]


def check_installed_nginx(root: Path, *, run: Runner = subprocess.run,
                          which: Callable[[str], str | None] = shutil.which,
                          read: Callable[[Path], str] = lambda p: p.read_text(encoding="utf-8")) -> list[Check]:
    """The *effective* nginx configuration (``nginx -T`` only tests and prints; it starts nothing)."""
    if which("nginx") is None:
        return [Check("nginx_effective", False, "nginx not found")]
    dump = _run(run, ["nginx", "-T"])
    if dump.returncode != 0:
        return [Check("nginx_effective", False, "nginx -T failed (run the check as root)")]
    listens = _listens(dump.stdout)
    public = [item for item in listens if not _LOOPBACK.match(item)]
    checks = [Check("nginx_effective_loopback_only", bool(listens) and not public,
                    f"listen={sorted(set(listens))}" + (f" public={sorted(set(public))}" if public else ""))]
    try:
        site = read(NGINX_SITE).replace("\r\n", "\n")
        same = site == read(root / NGINX_LOOPBACK).replace("\r\n", "\n")
        checks.append(Check("nginx_site_matches_repo", same,
                            f"{NGINX_SITE} {'==' if same else 'differs from'} {NGINX_LOOPBACK}"))
    except OSError:
        checks.append(Check("nginx_site_matches_repo", False, f"{NGINX_SITE} missing"))
    return checks


def check_listeners(*, run: Runner = subprocess.run,
                    which: Callable[[str], str | None] = shutil.which) -> list[Check]:
    """Actual listening TCP sockets (``ss -ltn``, read-only): guarded ports only on loopback."""
    if which("ss") is None:
        return [Check("listeners", False, "ss not found")]
    out = _run(run, ["ss", "-H", "-ltn"]).stdout
    exposed = []
    for line in out.splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        local = fields[3]
        host, _, port = local.rpartition(":")
        host = host.split("%", 1)[0].strip("[]")            # 127.0.0.53%lo -> 127.0.0.53, [::1] -> ::1
        if port.isdigit() and int(port) in GUARDED_PORTS and not _LOOPBACK.match(host):
            exposed.append(local)
    return [Check("listeners_loopback_only", not exposed, f"exposed={exposed}" if exposed else
                  f"guarded ports {list(GUARDED_PORTS)} not exposed")]


# --- service write access ----------------------------------------------------------------------

def check_write_targets(root: Path, *, owner_of: Callable[[Path], str] | None = None) -> list[Check]:
    """Least privilege: the service user owns only the state dir and the gitignored runtime outputs."""
    if owner_of is None:
        import pwd

        def owner_of(path: Path) -> str:
            return pwd.getpwuid(path.stat().st_uid).pw_name
    checks = []
    for path in (STATE_DIR, *(root / target for target in WRITE_TARGETS)):
        try:
            owner = owner_of(path)
        except (OSError, KeyError):
            checks.append(Check(f"write_target:{path}", False, "missing"))
            continue
        checks.append(Check(f"write_target:{path}", owner == SERVICE_USER, f"owner={owner}"))
    try:
        repo_owner = owner_of(root)
        checks.append(Check("repository_owner_unchanged", repo_owner != SERVICE_USER, f"owner={repo_owner}"))
    except (OSError, KeyError):
        checks.append(Check("repository_owner_unchanged", False, "unknown"))
    return checks


# --- verdict ----------------------------------------------------------------------------------

def run_checks(*, root: Path = PROJECT_ROOT, env: Mapping[str, str] | None = None,
               env_file: Path | None = ENV_FILE, systemd: bool = True, platform: str = sys.platform,
               pre_start: bool = False) -> tuple[list[Check], bool]:
    """``(checks, complete)``. ``complete`` is False whenever installed-state checks were skipped."""
    env = dict(os.environ if env is None else env)
    linux = platform.startswith("linux")
    checks = [Check("platform_linux", linux, platform)]
    checks += check_python()
    checks += check_requirements(root)
    checks += check_safety_env(env, "process_env")
    checks.append(Check("scanner_config_present", (root / "config.py").exists(),
                        "config.py (machine-local, gitignored; contents not read)"))
    checks += check_ports()
    checks += check_repo_units(root, check_interpreter=linux)
    if pre_start:
        return checks, linux
    runtime_env = env
    if env_file is not None:
        if env_file.exists():
            file_env = parse_env_file(env_file)
            checks += check_safety_env(file_env, "env_file")
            runtime_env = {**env, **file_env}
        else:
            checks.append(Check("env_file", False, f"{env_file} missing"))
    checks += check_paper_db(root, runtime_env)
    checks += check_repo_nginx(root)
    complete = linux and systemd
    if complete:
        checks += check_installed_units(root)
        checks += check_installed_nginx(root)
        checks += check_listeners()
        checks += check_write_targets(root)
    return checks, complete


def verdict(checks: list[Check], complete: bool) -> tuple[str, int]:
    if any(not check.ok for check in checks):
        return "FAILED", 1
    if not complete:
        return "INCOMPLETE", 2
    return "OK", 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.vps_check", description=__doc__.splitlines()[0])
    parser.add_argument("--env-file", type=Path, default=ENV_FILE)
    parser.add_argument("--no-systemd", action="store_true",
                        help="skip installed-state checks (the verdict can then never be OK)")
    parser.add_argument("--pre-start", action="store_true",
                        help="ExecStartPre gate of the backend unit (LIVE off, ports free)")
    args = parser.parse_args(argv)
    checks, complete = run_checks(env_file=args.env_file, systemd=not args.no_systemd,
                                  pre_start=args.pre_start)
    for check in checks:
        print(f"{'PASS' if check.ok else 'FAIL'}  {check.name}: {check.detail}", flush=True)
    word, code = verdict(checks, complete)
    if args.pre_start and code == 2:
        word, code = "OK", 0                    # inside systemd: process env is the effective env
    failed = sum(1 for check in checks if not check.ok)
    print(f"VPS_PREPARE_CHECK {word}: {len(checks) - failed}/{len(checks)} passed;"
          " nothing was started, opened or connected", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())

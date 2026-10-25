"""Offline prepare/validate-only check for a Linux VPS (issue #624). Never starts anything.

Usage (from the repository root, with the project venv)::

    python -m tools.vps_check [--env-file /etc/bybitscanner/paper.env]

It only reads files, installed-package metadata and local state. It does **not**:
import the PAPER backend, Scanner, Robot, Autopilot or Telegram modules; connect to
Bybit or any remote host; open, create or migrate the PAPER DB; start or enable a
systemd unit. Secret values are never printed (only key names).

Exit code 0 = the server is prepared *and stopped*; 1 = at least one check failed.
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
UNITS = ("bybitscanner-paper-backend.service", "bybitscanner-telegram.service")
UNIT_DIR = Path("deploy/systemd")
NGINX_LOOPBACK = Path("deploy/nginx/bybitscanner-loopback.conf")
# Owner-only switches that must stay off on a prepare-only server.
OFF_SWITCHES = ("BYBITSCANNER_MIRROR_STANDALONE_ROBOT",)
# Keys whose *value* is secret: reported as set/unset only.
SECRET_KEY = re.compile(r"(TOKEN|SECRET|API_KEY|PASSWORD)", re.IGNORECASE)
_FALSE = {"", "0", "false", "no", "off"}


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def parse_env_file(path: Path) -> dict[str, str]:
    """``KEY=VALUE`` lines as systemd ``EnvironmentFile`` reads them (comments/blank ignored)."""
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


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


def check_repo_units(root: Path, *, check_interpreter: bool = False) -> list[Check]:
    """Repository units: no [Install] (cannot be enabled), no auto-restart, PAPER-only entrypoints."""
    checks = []
    expected = {"bybitscanner-paper-backend.service": "-m terminal.runtime.paper_http_server",
                "bybitscanner-telegram.service": "telegram_monitoring.py"}
    for unit, entry in expected.items():
        path = root / UNIT_DIR / unit
        if not path.exists():
            checks.append(Check(f"unit_file:{unit}", False, "missing"))
            continue
        sections = _unit_sections(path.read_text(encoding="utf-8"))
        service = sections.get("Service", {})
        problems = []
        if "Install" in sections:
            problems.append("has [Install] (could be enabled)")
        if service.get("Restart", "no") != "no":
            problems.append(f"Restart={service.get('Restart')}")
        if entry not in service.get("ExecStart", ""):
            problems.append("unexpected ExecStart")
        interpreter = (service.get("ExecStart", "").split() or [""])[0]
        if check_interpreter and not Path(interpreter).exists():
            problems.append(f"interpreter {interpreter} not found on this host")
        checks.append(Check(f"unit_file:{unit}", not problems, "; ".join(problems) or "static, Restart=no"))
    return checks


def check_installed_units(run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                          which: Callable[[str], str | None] = shutil.which) -> list[Check]:
    """Installed units are neither enabled nor active (read-only ``systemctl is-*`` queries)."""
    if which("systemctl") is None:
        return [Check("systemd", False, "systemctl not found")]
    checks = []
    for unit in UNITS:
        enabled = run(["systemctl", "is-enabled", unit], capture_output=True, text=True).stdout.strip()
        active = run(["systemctl", "is-active", unit], capture_output=True, text=True).stdout.strip()
        ok = enabled not in {"enabled", "enabled-runtime", "linked", "linked-runtime", "alias"} and \
            active not in {"active", "activating", "reloading"}
        checks.append(Check(f"unit_state:{unit}", ok, f"is-enabled={enabled or '?'} is-active={active or '?'}"))
    return checks


def check_nginx(root: Path) -> list[Check]:
    path = root / NGINX_LOOPBACK
    if not path.exists():
        return [Check("nginx_loopback", False, "missing")]
    text = path.read_text(encoding="utf-8")
    listens = re.findall(r"^\s*listen\s+([^;]+);", text, re.MULTILINE)
    backend = urllib_host(DEFAULT_BACKEND_URL)
    ok = bool(listens) and all(item.split()[0].startswith("127.0.0.1:") for item in listens) and \
        f"proxy_pass http://{backend}" in text
    return [Check("nginx_loopback", ok, f"listen={listens}")]


def urllib_host(url: str) -> str:
    return url.split("://", 1)[-1].rstrip("/")


def run_checks(*, root: Path = PROJECT_ROOT, env: Mapping[str, str] | None = None,
               env_file: Path | None = None, systemd: bool = True, platform: str = sys.platform,
               pre_start: bool = False) -> list[Check]:
    """``pre_start`` (the backend unit's ExecStartPre gate): only what must hold for an authorized
    start -- Linux, Python/venv, packages, LIVE gates off, ports free, unit contract. The prepare
    checks that a running system legitimately fails (DB present, units active) are skipped."""
    env = dict(os.environ if env is None else env)
    linux = platform.startswith("linux")
    checks = [Check("platform_linux", platform.startswith("linux"), platform)]
    checks += check_python()
    checks += check_requirements(root)
    checks += check_safety_env(env, "process_env")
    runtime_env = env
    if env_file is not None:
        if env_file.exists():
            file_env = parse_env_file(env_file)
            checks += check_safety_env(file_env, "env_file")
            runtime_env = {**env, **file_env}
        else:
            checks.append(Check("env_file", False, f"{env_file} missing"))
    checks.append(Check("scanner_config_present", (root / "config.py").exists(),
                        "config.py (machine-local, gitignored; contents not read)"))
    checks += check_ports()
    checks += check_repo_units(root, check_interpreter=linux)
    if pre_start:
        return checks
    checks += check_paper_db(root, runtime_env)
    if systemd:
        checks += check_installed_units()
    checks += check_nginx(root)
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.vps_check", description=__doc__.splitlines()[0])
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--no-systemd", action="store_true", help="skip installed-unit queries")
    parser.add_argument("--pre-start", action="store_true",
                        help="ExecStartPre gate of the backend unit (LIVE off, ports free)")
    args = parser.parse_args(argv)
    checks = run_checks(env_file=args.env_file, systemd=not args.no_systemd, pre_start=args.pre_start)
    for check in checks:
        print(f"{'PASS' if check.ok else 'FAIL'}  {check.name}: {check.detail}", flush=True)
    failed = [check for check in checks if not check.ok]
    print(f"VPS_PREPARE_CHECK {'OK' if not failed else 'FAILED'}: {len(checks) - len(failed)}/{len(checks)} passed;"
          " nothing was started, opened or connected", flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

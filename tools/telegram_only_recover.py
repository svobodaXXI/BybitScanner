"""One-shot, fail-closed recovery of ONLY a proven-absent Telegram PAPER worker.

Not a release installer or an alternative Robot/PAPER lifecycle controller.
Requires explicit operator invocation and the exact installed release SHA.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import subprocess

ROOT = Path("/opt/BybitScanner")
UNIT = "bybitscanner-telegram.service"
BACKEND_UNIT = "bybitscanner-paper-backend.service"
UNIT_DIR = Path("/etc/systemd/system")
ENV_FILE = Path("/etc/bybitscanner/paper.env")
SHA = re.compile(r"[0-9a-f]{40}\Z")


class TelegramRecoveryBlocked(Exception):
    pass


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise TelegramRecoveryBlocked(reason)


def _read_json(path: str) -> dict:
    from tools.runtime_intent import http_get
    response = http_get("http://127.0.0.1:8765" + path, 3)
    _require(response.status == 200, "backend_api_unavailable")
    body = response.json()
    _require(isinstance(body, dict) and body.get("ok") is True, "backend_api_invalid")
    return body


def _systemd(unit: str) -> dict[str, str]:
    result = subprocess.run(
        ["systemctl", "show", unit, "--no-pager",
         "--property=LoadState,ActiveState,MainPID,FragmentPath,DropInPaths"],
        capture_output=True, text=True, check=False, timeout=10,
    )
    _require(result.returncode == 0, "systemd_query_failed")
    state = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    _require(state.get("LoadState") == "loaded", "unit_not_loaded")
    _require(state.get("FragmentPath") == str(UNIT_DIR / unit), "unit_origin_unproven")
    _require(not state.get("DropInPaths"), "unit_override_unproven")
    return state


def _positive_decimal(value: object) -> Decimal:
    _require(isinstance(value, str), "quantity_not_string")
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise TelegramRecoveryBlocked("quantity_invalid") from exc
    _require(number.is_finite() and number > 0, "quantity_invalid")
    return number


def _proof(target: str, *, expected_pid: int | None = None) -> int:
    """Complete read-only proof. Never uses reconcile, Telegram API or DB writes."""
    from tools.paper_maintenance import _durable_editor_freeze
    from tools.vps_release_identity import verify_release

    _require(verify_release(ROOT) == target, "installed_release_mismatch")
    source = ROOT / "deploy/systemd" / UNIT
    installed = UNIT_DIR / UNIT
    _require(source.is_file() and installed.is_file()
             and not installed.is_symlink()
             and source.read_bytes() == installed.read_bytes(), "telegram_unit_mismatch")

    identity = _durable_editor_freeze(ROOT, ENV_FILE)
    backend = _systemd(BACKEND_UNIT)
    pid = backend.get("MainPID", "")
    _require(backend.get("ActiveState") == "active" and pid.isdecimal()
             and int(pid) > 0, "backend_owner_unproven")
    if expected_pid is not None:
        _require(int(pid) == expected_pid, "backend_pid_changed")

    health = _read_json("/api/health")
    _require(health.get("component") == "paper_backend"
             and health.get("mode") == "paper"
             and health.get("build_sha") == target
             and health.get("database_identity") == identity
             and health.get("paper_live_safe") is True
             and health.get("robot_admission_ready") is False,
             "backend_release_or_admission_unproven")
    scanner = _read_json("/api/scanner/status")
    autopilot = _read_json("/api/robot/autopilot")
    _require(scanner.get("mode") == "SCANNER_STOPPED"
             and scanner.get("worker_quiescent") is True
             and autopilot.get("mode") == "OFF",
             "trading_ingress_not_frozen")

    inventory = _read_json("/api/open-positions")
    _require(inventory.get("account_id") == "paper"
             and isinstance(inventory.get("positions"), list), "position_inventory_unproven")
    symbols: set[str] = set()
    for position in inventory["positions"]:
        _require(isinstance(position, dict), "position_invalid")
        symbol = position.get("symbol")
        _require(isinstance(symbol, str) and symbol.isascii()
                 and re.fullmatch(r"[A-Z0-9]{3,32}", symbol) is not None
                 and symbol not in symbols, "position_identity_unproven")
        symbols.add(symbol)
        quantity = _positive_decimal(position.get("position_quantity"))
        paper = _read_json("/api/paper-state?symbol=" + symbol)
        protection = paper.get("protection")
        _require(paper.get("account_id") == "paper"
                 and paper.get("symbol") == symbol
                 and paper.get("position_side") == position.get("position_side")
                 and _positive_decimal(paper.get("position_quantity")) == quantity
                 and paper.get("active_limit_orders") == []
                 and isinstance(protection, dict)
                 and protection.get("status") == "confirmed_active"
                 and protection.get("stop_loss") is not None
                 and protection.get("take_profit") is not None
                 and protection.get("pending_command_id") is None
                 and protection.get("warning") is None
                 and _positive_decimal(protection.get("effective_quantity")) == quantity,
                 "position_protection_unproven:" + symbol)
        _positive_decimal(protection["stop_loss"])
        _positive_decimal(protection["take_profit"])

    # A health snapshot cannot replace per-position PAPER protection proof.
    coverage = _read_json("/api/robot/protection-health")
    _require(coverage.get("healthy") is True
             and coverage.get("unhealthy_symbols") == {},
             "protection_health_unproven")
    return int(pid)


def recover(target: str) -> str:
    from tools.legacy_runtime_process import probe_listener_pids

    _require(SHA.fullmatch(target) is not None, "invalid_target_sha")
    pid = _proof(target)
    state = _systemd(UNIT)
    _require(state.get("ActiveState") in ("inactive", "failed")
             and state.get("MainPID") == "0", "telegram_worker_not_absent")
    _require(not probe_listener_pids("127.0.0.1", 8766),
             "telegram_listener_not_absent")
    _proof(target, expected_pid=pid)  # verify immutable guards again before action

    # Sole mutation: a single systemd start of the exact installed Telegram unit.
    # A 409 Conflict must fail closed; never attempt restart or retry.
    result = subprocess.run(["systemctl", "start", UNIT], cwd=ROOT,
                            capture_output=True, text=True, check=False, timeout=180)
    _require(result.returncode == 0, "telegram_start_failed_no_retry")
    _require(_proof(target, expected_pid=pid) == pid,
             "backend_postcondition_unproven")

    from tools.runtime_intent import http_get
    response = http_get("http://127.0.0.1:8766/health", 3)
    _require(response.status == 200, "telegram_health_unavailable")
    health = response.json()
    backend = _read_json("/api/health")
    _require(isinstance(health, dict)
             and health.get("component") == "telegram_monitoring"
             and health.get("status") == "ready"
             and health.get("database_identity") == backend.get("database_identity"),
             "telegram_readiness_unproven")
    return "TELEGRAM_ONLY_RECOVERED"



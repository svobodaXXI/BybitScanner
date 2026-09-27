"""One-action owner runtime intent reconciliation (RUNTIME_INTENT_RECONCILER_PLAN.md).

Observes authoritative Robot / Scanner / protection state through injected
ports and applies only the existing canonical commands those ports wrap. It
owns no state: legality stays with robot_control / ScannerControlRuntime,
and every decision is taken from a fresh read after each mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Protocol

from terminal.application.robot_recovery import (
    PAUSED,
    READY,
    RECONCILIATION_REQUIRED,
    ROBOT_RUNNING,
    ROBOT_STOPPED,
)

# Mirrors terminal.runtime.paper_runtime; the application layer must not import the runtime layer.
SCANNER_STOPPED = "SCANNER_STOPPED"
SCANNER_RUNNING = "SCANNER_RUNNING"
SCANNER_PAUSED = "SCANNER_PAUSED"
_SCANNER_STATES = {SCANNER_STOPPED, SCANNER_RUNNING, SCANNER_PAUSED}

_ROBOT_STOPPED_PAIR = (ROBOT_STOPPED, ROBOT_STOPPED)
_ROBOT_READY_PAIR = (ROBOT_RUNNING, READY)
_ROBOT_PAUSED_PAIR = (ROBOT_RUNNING, PAUSED)
_ROBOT_RECON_PAIR = (ROBOT_RUNNING, RECONCILIATION_REQUIRED)
_ROBOT_STOPPED_RECON_PAIR = (ROBOT_STOPPED, RECONCILIATION_REQUIRED)

ROBOT_STATE_UNKNOWN = "ROBOT_STATE_UNKNOWN"
ROBOT_STOPPED_RECONCILIATION_REQUIRED = "ROBOT_STOPPED_RECONCILIATION_REQUIRED"
ROBOT_RECONCILIATION_REQUIRED = "ROBOT_RECONCILIATION_REQUIRED"
ROBOT_RECONCILIATION_FAILED = "ROBOT_RECONCILIATION_FAILED"
ROBOT_START_FAILED = "ROBOT_START_FAILED"
ROBOT_RESUME_FAILED = "ROBOT_RESUME_FAILED"
ROBOT_NOT_CONVERGED = "ROBOT_NOT_CONVERGED"
ROBOT_PROTECTION_UNHEALTHY = "ROBOT_PROTECTION_UNHEALTHY"
SCANNER_STATE_UNKNOWN = "SCANNER_STATE_UNKNOWN"
SCANNER_START_FAILED = "SCANNER_START_FAILED"
SCANNER_RESUME_FAILED = "SCANNER_RESUME_FAILED"
SCANNER_NOT_RUNNING = "SCANNER_NOT_RUNNING"


class RuntimeIntent(str, Enum):
    SCANNER = "SCANNER"
    ROBOT = "ROBOT"
    ALL = "ALL"


class RuntimeIntentPorts(Protocol):
    def robot_state(self) -> tuple[str, str] | None: ...
    def protection_healthy(self) -> bool | None: ...
    def scanner_state(self) -> str | None: ...
    def start_robot(self) -> object: ...
    def resume_robot(self) -> object: ...
    def reconcile_robot(self) -> object: ...
    def start_scanner(self) -> object: ...
    def resume_scanner(self) -> object: ...


@dataclass(frozen=True)
class RuntimeIntentResult:
    intent: RuntimeIntent
    changed: tuple[str, ...]
    final: Mapping[str, str]
    blocked_by: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.blocked_by


class RuntimeIntentReconciler:
    def __init__(self, ports: RuntimeIntentPorts) -> None:
        self._ports = ports

    def reconcile(self, intent: RuntimeIntent | str) -> RuntimeIntentResult:
        intent = RuntimeIntent(intent)
        needs_robot = intent in (RuntimeIntent.ROBOT, RuntimeIntent.ALL)
        needs_scanner = intent in (RuntimeIntent.SCANNER, RuntimeIntent.ALL)
        changed: list[str] = []

        blocker = None
        if needs_scanner and self._read_scanner() not in _SCANNER_STATES:
            blocker = SCANNER_STATE_UNKNOWN
        if blocker is None and needs_robot:
            blocker = self._ensure_robot_ready(changed)
            if blocker is None and self._read_protection() is not True:
                blocker = ROBOT_PROTECTION_UNHEALTHY
        if blocker is None and needs_scanner:
            blocker = self._ensure_scanner_running(changed)

        return RuntimeIntentResult(
            intent=intent,
            changed=tuple(changed),
            final=self._final(needs_robot=needs_robot, needs_scanner=needs_scanner),
            blocked_by=(blocker,) if blocker else (),
        )

    def _ensure_robot_ready(self, changed: list[str]) -> str | None:
        # Each canonical command may run at most once per reconcile(); the loop is
        # bounded by that, and every step decides from a fresh authoritative read.
        commands = {
            _ROBOT_STOPPED_PAIR: ("robot:start", self._ports.start_robot, ROBOT_START_FAILED),
            _ROBOT_PAUSED_PAIR: ("robot:resume", self._ports.resume_robot, ROBOT_RESUME_FAILED),
            _ROBOT_RECON_PAIR: (
                "robot:reconcile", self._ports.reconcile_robot, ROBOT_RECONCILIATION_FAILED,
            ),
        }
        used: set[str] = set()
        while True:
            state = self._read_robot()
            if state == _ROBOT_READY_PAIR:
                return None
            if state == _ROBOT_STOPPED_RECON_PAIR:
                return ROBOT_STOPPED_RECONCILIATION_REQUIRED
            if state not in commands:
                return ROBOT_STATE_UNKNOWN
            name, command, failure = commands[state]
            if name in used:
                return (
                    ROBOT_RECONCILIATION_REQUIRED if state == _ROBOT_RECON_PAIR
                    else ROBOT_NOT_CONVERGED
                )
            used.add(name)
            try:
                command()
            except Exception:
                return failure
            changed.append(name)

    def _ensure_scanner_running(self, changed: list[str]) -> str | None:
        state = self._read_scanner()
        if state == SCANNER_RUNNING:
            return None
        if state == SCANNER_STOPPED:
            name, command, failure = "scanner:start", self._ports.start_scanner, SCANNER_START_FAILED
        elif state == SCANNER_PAUSED:
            name, command, failure = "scanner:resume", self._ports.resume_scanner, SCANNER_RESUME_FAILED
        else:
            return SCANNER_STATE_UNKNOWN
        try:
            command()
        except Exception:
            return failure
        changed.append(name)
        return None if self._read_scanner() == SCANNER_RUNNING else SCANNER_NOT_RUNNING

    def _final(self, *, needs_robot: bool, needs_scanner: bool) -> dict[str, str]:
        final: dict[str, str] = {}
        if needs_robot:
            final["robot"] = _project_robot(self._read_robot())
            protection = self._read_protection()
            final["protection"] = (
                "HEALTHY" if protection is True
                else "UNHEALTHY" if protection is False
                else "UNKNOWN"
            )
        if needs_scanner:
            scanner = self._read_scanner()
            final["scanner"] = (
                scanner.removeprefix("SCANNER_") if scanner in _SCANNER_STATES else "UNKNOWN"
            )
        return final

    def _read_robot(self) -> tuple[str, str] | None:
        try:
            state = self._ports.robot_state()
        except Exception:
            return None
        if not isinstance(state, tuple) or len(state) != 2:
            return None
        return state

    def _read_scanner(self) -> str | None:
        try:
            return self._ports.scanner_state()
        except Exception:
            return None

    def _read_protection(self) -> bool | None:
        try:
            return self._ports.protection_healthy()
        except Exception:
            return None


def _project_robot(state: tuple[str, str] | None) -> str:
    if state == _ROBOT_READY_PAIR:
        return "READY"
    if state == _ROBOT_PAUSED_PAIR:
        return "PAUSED"
    if state == _ROBOT_STOPPED_PAIR:
        return "STOPPED"
    if state in (_ROBOT_RECON_PAIR, _ROBOT_STOPPED_RECON_PAIR):
        return "RECONCILIATION_REQUIRED"
    return "UNKNOWN"

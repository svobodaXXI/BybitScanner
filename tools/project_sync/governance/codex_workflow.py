"""Orchestrate task-scoped Codex recovery using existing governance components."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .change_request import load_change_request, validate_change_request
from .context_dump import (
    GitState,
    VALIDATION_EXIT_CODES,
    generate_context_dump,
    validate_context_dump,
)
from .legacy_warning import enforce_scoped_warnings, load_registry


IMPLEMENTABLE_REQUEST_STATUSES = {"APPROVED_NOT_IMPLEMENTED", "IN_PROGRESS"}
NON_AUTHORITATIVE_CONTEXT = "NON_AUTHORITATIVE_DERIVED_CONTEXT"


@dataclass(frozen=True)
class WorkflowDecision:
    task_kind: str
    status: str
    recovery: str
    reasons: tuple[str, ...] = ()
    warning_ids: tuple[str, ...] = ()
    context_path: Path | None = None
    context_authority: str | None = None

    @property
    def continuation_allowed(self) -> bool:
        return self.status in {"PASS", "ADVISORY"}

    @property
    def exit_code(self) -> int:
        return VALIDATION_EXIT_CODES[self.status]


def context_generation_is_appropriate(
    *,
    multi_session: bool = False,
    context_heavy: bool = False,
    recovery_package: bool = False,
    explicitly_requested: bool = False,
) -> bool:
    """Return whether durable work benefits from a generated context package."""

    return any((multi_session, context_heavy, recovery_package, explicitly_requested))


def _warning_decision(
    project_root: Path,
    *,
    task_kind: str,
    recovery: str,
    paths: Sequence[str],
    symbols: Sequence[str],
) -> WorkflowDecision:
    if not paths and not symbols:
        return WorkflowDecision(
            task_kind,
            "FAIL",
            recovery,
            ("Task scope requires at least one path or symbol",),
        )
    try:
        registry = load_registry(project_root / "DOCUMENTS/LEGACY_WARNINGS.json")
        enforcement = enforce_scoped_warnings(
            registry,
            paths=tuple(paths),
            symbols=tuple(symbols),
        )
    except (OSError, ValueError) as exc:
        return WorkflowDecision(task_kind, "FAIL", recovery, (str(exc),))

    warning_ids = tuple(str(item["warning_id"]) for item in enforcement.warnings)
    reasons = (
        ("Applicable BLOCKING LegacyWarning",)
        if enforcement.status == "BLOCKING"
        else ()
    )
    return WorkflowDecision(
        task_kind,
        enforcement.status,
        recovery,
        reasons,
        warning_ids,
    )


def prepare_lightweight(
    project_root: str | Path,
    *,
    paths: Sequence[str] = (),
    symbols: Sequence[str] = (),
) -> WorkflowDecision:
    """Prepare lightweight work through direct scoped recovery, without ContextDump."""

    return _warning_decision(
        Path(project_root).resolve(),
        task_kind="LIGHTWEIGHT",
        recovery="DIRECT_SCOPED_RECOVERY",
        paths=paths,
        symbols=symbols,
    )


def prepare_durable(
    project_root: str | Path,
    change_request_path: str | Path,
    *,
    context_path: str | Path | None = None,
    multi_session: bool = False,
    context_heavy: bool = False,
    recovery_package: bool = False,
    explicitly_requested: bool = False,
    git_state: GitState | None = None,
) -> WorkflowDecision:
    """Prepare durable work and apply the implementation continuation gate."""

    root = Path(project_root).resolve()
    request_path = Path(change_request_path)
    if not request_path.is_absolute():
        request_path = root / request_path
    try:
        request = load_change_request(request_path)
        validation = validate_change_request(request)
    except (OSError, ValueError) as exc:
        return WorkflowDecision("DURABLE", "FAIL", "CHANGE_REQUEST", (str(exc),))
    if not validation.valid:
        return WorkflowDecision(
            "DURABLE",
            "FAIL",
            "CHANGE_REQUEST",
            tuple(validation.errors),
        )
    if request.get("status") not in IMPLEMENTABLE_REQUEST_STATUSES:
        return WorkflowDecision(
            "DURABLE",
            "FAIL",
            "CHANGE_REQUEST",
            (f"ChangeRequest status does not authorize implementation: {request.get('status')}",),
        )

    if context_path is not None:
        resolved_context = Path(context_path)
        if not resolved_context.is_absolute():
            resolved_context = root / resolved_context
        result = validate_context_dump(
            root,
            resolved_context,
            request_path,
            git_state=git_state,
        )
        return WorkflowDecision(
            "DURABLE",
            result.status,
            "VALIDATED_CONTEXT",
            result.reasons,
            result.warning_ids,
            resolved_context,
            NON_AUTHORITATIVE_CONTEXT,
        )

    if context_generation_is_appropriate(
        multi_session=multi_session,
        context_heavy=context_heavy,
        recovery_package=recovery_package,
        explicitly_requested=explicitly_requested,
    ):
        try:
            generated = generate_context_dump(root, request_path, git_state=git_state)
            result = validate_context_dump(
                root,
                generated,
                request_path,
                git_state=git_state,
            )
        except (OSError, ValueError) as exc:
            return WorkflowDecision(
                "DURABLE", "FAIL", "GENERATED_CONTEXT", (str(exc),)
            )
        return WorkflowDecision(
            "DURABLE",
            result.status,
            "GENERATED_CONTEXT",
            result.reasons,
            result.warning_ids,
            generated,
            NON_AUTHORITATIVE_CONTEXT,
        )

    paths = request.get("context_scope_paths")
    symbols = request.get("context_scope_symbols", [])
    if not isinstance(paths, list) or not all(isinstance(item, str) for item in paths):
        return WorkflowDecision(
            "DURABLE",
            "FAIL",
            "DIRECT_SCOPED_RECOVERY",
            ("ChangeRequest context_scope_paths is missing or invalid",),
        )
    if not isinstance(symbols, list) or not all(isinstance(item, str) for item in symbols):
        return WorkflowDecision(
            "DURABLE",
            "FAIL",
            "DIRECT_SCOPED_RECOVERY",
            ("ChangeRequest context_scope_symbols is invalid",),
        )
    return _warning_decision(
        root,
        task_kind="DURABLE",
        recovery="DIRECT_SCOPED_RECOVERY",
        paths=paths,
        symbols=symbols,
    )


def _print_decision(decision: WorkflowDecision) -> None:
    print(decision.status)
    print(f"- task_kind: {decision.task_kind}")
    print(f"- recovery: {decision.recovery}")
    if decision.context_path is not None:
        print(f"- context: {decision.context_path}")
        print(f"- context_authority: {decision.context_authority}")
    for reason in decision.reasons:
        print(f"- reason: {reason}")
    for warning_id in decision.warning_ids:
        print(f"- LegacyWarning: {warning_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="task_kind", required=True)

    lightweight = subparsers.add_parser("lightweight")
    lightweight.add_argument("--path", action="append", default=[])
    lightweight.add_argument("--symbol", action="append", default=[])

    durable = subparsers.add_parser("durable")
    durable.add_argument("change_request", type=Path)
    durable.add_argument("--context", type=Path)
    durable.add_argument("--multi-session", action="store_true")
    durable.add_argument("--context-heavy", action="store_true")
    durable.add_argument("--recovery-package", action="store_true")
    durable.add_argument("--generate-context", action="store_true")

    args = parser.parse_args()
    if args.task_kind == "lightweight":
        decision = prepare_lightweight(
            args.project_root,
            paths=args.path,
            symbols=args.symbol,
        )
    else:
        decision = prepare_durable(
            args.project_root,
            args.change_request,
            context_path=args.context,
            multi_session=args.multi_session,
            context_heavy=args.context_heavy,
            recovery_package=args.recovery_package,
            explicitly_requested=args.generate_context,
        )
    _print_decision(decision)
    return decision.exit_code


if __name__ == "__main__":
    raise SystemExit(main())

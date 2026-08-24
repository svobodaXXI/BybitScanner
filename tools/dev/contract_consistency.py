"""Fail-closed Trading Workspace frontend/backend contract consistency checks."""

from __future__ import annotations

import argparse
import ast
import inspect
import re
import textwrap
from dataclasses import fields
from enum import Enum
from pathlib import Path
from typing import Sequence

from terminal.api.models import CommandResult, MarketCommandRequest, VolumeRequest, VolumeUnit
from terminal.application.pretrade_guard import RejectionCode, SlippageToleranceType
from terminal.domain.models import OrderSide, PositionSide
from terminal.runtime import paper_runtime

from .workflow import compact


FRONTEND_CONTRACT = Path("terminal/frontend/src/contracts/trading.ts")


def _enum_values(enum_type: type[Enum]) -> set[str]:
    return {str(item.value) for item in enum_type}


def _array(source: str, name: str) -> set[str]:
    match = re.search(rf"export const {name}\s*=\s*\[(.*?)\]\s*as const", source, re.S)
    if match is None:
        raise ValueError(f"frontend declaration {name} is missing")
    return set(re.findall(r'["\']([^"\']+)["\']', match.group(1)))


def _type_fields(source: str, name: str) -> set[str]:
    match = re.search(rf"export type {name}\s*=\s*\{{(.*?)\}};", source, re.S)
    if match is None:
        raise ValueError(f"frontend type {name} is missing")
    return set(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\??\s*:", match.group(1), re.M))


def _paper_state_fields() -> set[str]:
    tree = ast.parse(textwrap.dedent(inspect.getsource(paper_runtime.PaperRuntime.paper_state)))
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            return {
                key.value for key in node.value.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
    raise ValueError("backend PaperRuntime.paper_state dict contract is not statically discoverable")


def _reason_codes() -> set[str]:
    # RejectionCode is authoritative for admission failures; these transport outcomes
    # are emitted directly by terminal.api.rest and remain generic UI fallbacks.
    from terminal.api import rest

    source = inspect.getsource(rest)
    literals = set(re.findall(r'_result\([^\n]*?["\']([a-z][a-z0-9_]*)["\']', source))
    literals.update(_enum_values(RejectionCode))
    return literals | {"blocked"}


def check_source(source: str) -> tuple[bool, str]:
    checks: list[str] = []
    failed: list[str] = []

    def compare(label: str, frontend: set[str], backend: set[str], *, exact: bool = False) -> None:
        checks.append(label)
        missing = frontend ^ backend if exact else frontend - backend
        if missing:
            failed.append(f"{label}:{','.join(sorted(missing))}")

    try:
        compare("market-request-fields", _type_fields(source, "MarketCommandRequest"),
                {field.name for field in fields(MarketCommandRequest)}, exact=True)
        compare("volume-request-fields", _type_fields(source, "VolumeRequest"),
                {field.name for field in fields(VolumeRequest)}, exact=True)
        compare("command-result-fields", _type_fields(source, "CommandResult"),
                {field.name for field in fields(CommandResult)})
        compare("paper-state-fields", _type_fields(source, "PaperState"),
                _paper_state_fields() | {"ok"})
        compare("market-sides", _array(source, "MARKET_SIDES"), _enum_values(OrderSide))
        compare("volume-units", _array(source, "VOLUME_UNITS"), _enum_values(VolumeUnit))
        compare("slippage-types", _array(source, "SLIPPAGE_TYPES"),
                _enum_values(SlippageToleranceType))
        compare("position-sides", _array(source, "POSITION_SIDES"),
                _enum_values(PositionSide), exact=True)
        compare("handled-reason-codes", _array(source, "HANDLED_REASON_CODES"), _reason_codes())
    except (OSError, TypeError, ValueError, SyntaxError) as exc:
        return False, compact("FAIL", [str(FRONTEND_CONTRACT)], checks, failed, [str(exc)])
    return not failed, compact(
        "PASS" if not failed else "FAIL", [str(FRONTEND_CONTRACT)], checks, failed, (),
    )


def check(path: Path) -> tuple[bool, str]:
    try:
        return check_source(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return False, compact("FAIL", [path.as_posix()], (), (), (str(exc),))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-contract", type=Path, default=FRONTEND_CONTRACT)
    args = parser.parse_args(argv)
    passed, output = check(args.frontend_contract)
    print(output)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

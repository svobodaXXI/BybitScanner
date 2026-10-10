"""Owner-authorized closure of two orphaned historical PAPER Market commands.

On 2026-08-30 two manual PAPER ``create_market`` commands for OGUSDT were made
durable as SUBMITTING and the simulator then refused the provider book before
any fill. Nothing ever moved them on, so the PAPER portfolio collector cannot
prove the symbol flat and every Autopilot decision WAITs.

The PAPER simulator is the exchange of record. It writes one execution with the
deterministic identity ``paper-exec-<order_link_id>`` / ``paper-order-<order_link_id>``
together with the synced position projection in a single transaction
(``ExecutionEngine.apply_paper_execution`` -> ``apply_execution_once``). No such
execution, and no other PAPER trace on the symbol, proves the command never
executed. Only then is the existing, allowed ``SUBMITTING -> FAILED`` transition
recorded through ``transition_command_state`` with an exact audit reason.

Scope is the explicit allowlist below and nothing else. Any doubt refuses before
any write. Command age is never evidence. No execution, position, order or
revision is created, changed or removed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from terminal.domain.models import CommandId, Symbol, TradingAccountId
from terminal.domain.states import CommandState
from terminal.persistence.sqlite_store import CommandRecord, SQLiteStore

PAPER_ACCOUNT = TradingAccountId("paper")

# command_id -> (symbol, order_link_id). Exactly the two OGUSDT orphans.
ALLOWED_ORPHAN_COMMANDS: dict[str, tuple[str, str]] = {
    "cmd_b5ce5acd36b7489daf23a7632afa3fd2": ("OGUSDT", "tw_b5ce5acd36b7489daf23a7632afa3fd2d"),
    "cmd_3ebfeec0374e4f589c96c2dd5599e035": ("OGUSDT", "tw_3ebfeec0374e4f589c96c2dd5599e035b"),
}

FAILED_REASON = (
    "PAPER Market never executed: no simulator execution for the deterministic "
    "paper-exec/paper-order identity and no PAPER trace on the symbol; "
    "owner-authorized orphan reconciliation"
)

_EXPECTED_SUBMITTING_HISTORY = (
    (None, CommandState.ADMITTED, "admitted before exchange submission"),
    (CommandState.ADMITTED, CommandState.SUBMITTING, "single mutation attempt durably started"),
)
_EXPECTED_FAILED_HISTORY = _EXPECTED_SUBMITTING_HISTORY + (
    (CommandState.SUBMITTING, CommandState.FAILED, FAILED_REASON),
)


class OrphanEvidenceError(ValueError):
    """The command is not provably an unexecuted orphan; nothing was written."""


@dataclass(frozen=True, slots=True)
class OrphanProof:
    command_id: str
    symbol: str
    order_link_id: str
    exec_id: str
    order_id: str
    version: int
    already_failed: bool


def prove_orphan_paper_market_command(store: SQLiteStore, command_id: str) -> OrphanProof:
    """Read-only. Raise OrphanEvidenceError unless every check proves the orphan."""
    allowed = ALLOWED_ORPHAN_COMMANDS.get(command_id)
    if allowed is None:
        raise OrphanEvidenceError(f"{command_id} is not on the orphan allowlist")
    symbol, link = allowed
    command = store.get_command(CommandId(command_id))
    if command is None:
        raise OrphanEvidenceError(f"{command_id} does not exist")
    _require_identity(command, symbol, link)

    exec_id, order_id = f"paper-exec-{link}", f"paper-order-{link}"
    # Strongest evidence first: the deterministic identity must not exist in any account.
    for execution in store.load_executions():
        if execution.dedup_key.exec_id.value == exec_id or execution.order_id.value == order_id:
            raise OrphanEvidenceError(f"{command_id}: simulator execution {exec_id} exists")

    history = tuple(
        (item.previous_state, item.next_state, item.reason)
        for item in store.load_command_history(command.command_id)
    )
    already_failed = command.current_state is CommandState.FAILED
    if already_failed:
        if history != _EXPECTED_FAILED_HISTORY or command.version != 3:
            raise OrphanEvidenceError(
                f"{command_id} is FAILED with a history this reconciliation did not write")
    else:
        if command.current_state is not CommandState.SUBMITTING:
            raise OrphanEvidenceError(
                f"{command_id} state is {command.current_state.value}, not submitting")
        if command.version != 2:
            raise OrphanEvidenceError(f"{command_id} version is {command.version}, expected 2")
        if history != _EXPECTED_SUBMITTING_HISTORY:
            raise OrphanEvidenceError(f"{command_id} history is not exactly admitted -> submitting")
    if command.exchange_order_id is not None:
        raise OrphanEvidenceError(f"{command_id} has an exchange_order_id")

    rows =store.load_paper_portfolio_rows(PAPER_ACCOUNT)
    if any(row["symbol"] == symbol for row in rows["executions"]):
        raise OrphanEvidenceError(f"{command_id}: a PAPER execution exists on {symbol}")
    if any(row["symbol"] == symbol for row in rows["paper_limit_orders"]):
        raise OrphanEvidenceError(f"{command_id}: a PAPER order exists on {symbol}")
    if any(row["symbol"] == symbol for row in rows["position_projections"]):
        raise OrphanEvidenceError(f"{command_id}: a PAPER position exists on {symbol}")
    if store.get_paper_state_revision(PAPER_ACCOUNT, Symbol(symbol)) != 0:
        raise OrphanEvidenceError(f"{command_id}: a PAPER state revision exists on {symbol}")
    others = [row for row in rows["trading_commands"]
              if row["symbol"] == symbol and row["command_id"] not in ALLOWED_ORPHAN_COMMANDS]
    if others:
        raise OrphanEvidenceError(
            f"{command_id}: other unfinished command or command history exists on {symbol}")

    return OrphanProof(command_id, symbol, link, exec_id, order_id, command.version,
                       already_failed)


def fail_orphan_paper_market_commands(
    store: SQLiteStore, command_ids: Iterable[str], *, occurred_at_ms: int,
) -> tuple[CommandRecord, ...]:
    """Prove every command first, then record SUBMITTING -> FAILED for each.

    Already reconciled commands (exactly this FAILED history) are returned as-is.
    The caller guarantees a stopped runtime; the version guard still refuses any
    concurrent change.
    """
    ids = tuple(command_ids)
    if not ids:
        raise OrphanEvidenceError("no command ids were given")
    if len(set(ids)) != len(ids):
        raise OrphanEvidenceError("duplicate command ids were given")
    proofs = tuple(prove_orphan_paper_market_command(store, command_id) for command_id in ids)

    results = []
    for proof in proofs:
        if proof.already_failed:
            results.append(store.get_command(CommandId(proof.command_id)))
            continue
        results.append(store.transition_command_state(
            CommandId(proof.command_id), CommandState.SUBMITTING, CommandState.FAILED,
            expected_version=proof.version, reason=FAILED_REASON,
            occurred_at_ms=occurred_at_ms,
        ))
    return tuple(results)


def _require_identity(command: CommandRecord, symbol: str, link: str) -> None:
    command_id = command.command_id.value
    if command.trading_account_id != PAPER_ACCOUNT:
        raise OrphanEvidenceError(f"{command_id} account is not paper")
    if command.symbol.value != symbol:
        raise OrphanEvidenceError(f"{command_id} symbol {command.symbol.value} != {symbol}")
    if command.order_link_id != link:
        raise OrphanEvidenceError(f"{command_id} order_link_id does not match the allowlist")
    if command.command_kind != "create_market":
        raise OrphanEvidenceError(f"{command_id} kind is {command.command_kind}")
    if (command.category.value, command.position_idx) != ("linear", 0):
        raise OrphanEvidenceError(f"{command_id} category/position_idx scope does not match")
    if (command.origin.value, command.controller.value) != ("terminal_manual", "manual"):
        raise OrphanEvidenceError(f"{command_id} is not a manual terminal command")

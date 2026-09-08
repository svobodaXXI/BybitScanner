import tempfile
from decimal import Decimal
from pathlib import Path

from terminal.application.execution_engine import ExecutionEngine
from terminal.application.models import ProtectionEvidence, ProtectionState
from terminal.domain.models import (
    Category,
    CommandId,
    Controller,
    Notional,
    OrderSide,
    Origin,
    PositionKey,
    Symbol,
    TradingAccountId,
)
from terminal.domain.states import CommandState
from terminal.exchange.bybit_v5_mutation_adapter import (
    MutationDisposition,
    MutationKind,
    MutationOutcome,
)
from terminal.persistence.sqlite_store import (
    CommandRecord,
    ProtectionIntentRecord,
    ProtectionProjectionRecord,
    SQLiteStore,
)


def test_live_protection_reconciliation_accepts_runtime_timestamp_and_resolves_pending_intent():
    with tempfile.TemporaryDirectory() as temp:
        store = SQLiteStore.open(Path(temp) / "runtime.sqlite3")
        try:
            engine = ExecutionEngine(store)
            account_id = TradingAccountId("bybit-main")
            key = PositionKey(account_id, Category.LINEAR, Symbol("OGUSDT"), 0)
            command_id = CommandId("command-protection")
            command = CommandRecord(
                command_id=command_id,
                order_link_id="protection-link",
                trading_account_id=account_id,
                category=Category.LINEAR,
                symbol=Symbol("OGUSDT"),
                position_idx=0,
                command_kind="protection",
                side=OrderSide.SELL,
                requested_notional=Notional(Decimal("0")),
                normalized_price=None,
                normalized_quantity=None,
                origin=Origin.TERMINAL_MANUAL,
                controller=Controller.MANUAL,
                current_state=CommandState.ADMITTED,
                version=1,
                exchange_order_id=None,
                created_at_ms=1000,
                updated_at_ms=1000,
            )
            store.persist_command_before_submit(command)
            submitting = store.transition_command_state(
                command_id,
                CommandState.ADMITTED,
                CommandState.SUBMITTING,
                expected_version=1,
                reason="protection mutation attempt durably started",
                occurred_at_ms=1100,
            )
            engine.ingest_mutation_outcome(
                submitting,
                MutationOutcome(
                    MutationKind.PROTECTION,
                    MutationDisposition.ACKNOWLEDGED,
                    reason="exchange accepted protection mutation",
                ),
                occurred_at_ms=1200,
            )
            store.persist_protection_intent(ProtectionIntentRecord(
                command_id,
                key,
                None,
                Decimal("2.732"),
                "MarkPrice",
                "MarkPrice",
                ProtectionState.PENDING_CONFIRMATION.value,
                1000,
                1200,
            ))
            store.upsert_protection_projection(
                ProtectionProjectionRecord(
                    key,
                    ProtectionState.PENDING_CONFIRMATION.value,
                    None,
                    None,
                    Decimal("0"),
                    command_id,
                    1,
                    1000,
                    1200,
                ),
                expected_version=None,
            )

            projection = engine.ingest_protection_evidence(
                ProtectionEvidence(
                    key,
                    None,
                    Decimal("2.732"),
                    Decimal("0"),
                    1500,
                ),
                occurred_at_ms=2000,
            )

            resolved = store.get_command(command_id)
            intent = store.get_protection_intent(command_id)
            assert resolved is not None
            assert intent is not None
            assert resolved.current_state is CommandState.AMENDED
            assert intent.status == ProtectionState.CONFIRMED_ACTIVE.value
            assert intent.updated_at_ms == 2000
            assert projection.pending_command_id is None
            assert projection.status == ProtectionState.CONFIRMED_ACTIVE.value
            assert projection.stop_loss == Decimal("2.732")
            assert projection.evidence_at_ms == 1500
            assert projection.updated_at_ms == 2000
        finally:
            store.close()

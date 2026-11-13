"""Historical partial LIMIT fills cannot claim a later Robot candidate.

Pure, isolated SQLite fixtures; never mutate an operator PAPER runtime.
"""
from pathlib import Path

import pytest

from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore


ACCOUNT = TradingAccountId("paper")
SYMBOL = "B2USDT"


def _seed_candidate_and_prior_limit(
    store, *, created_at=100, updated_at=300, filled="242",
    execution_qty="242", execution_at=250, execution_symbol=SYMBOL,
):
    candidate, _ = store.create_robot_candidate(
        candidate_id="later-b2-approval",
        trading_account_id=ACCOUNT,
        symbol=Symbol(SYMBOL),
        status="APPROVED",
        signal_snapshot={"symbol": SYMBOL, "pattern": "Wedge"},
        approved_at_ms=1000,
        updated_at_ms=1001,
    )
    store._connection.execute(
        """INSERT INTO paper_limit_orders (
            order_id, order_link_id, trading_account_id, symbol, side, price,
            quantity, filled_quantity, time_in_force, status, created_at_ms, updated_at_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "previous-b2-limit", "previous-b2-link", ACCOUNT.value, SYMBOL,
            "Buy", "1", "500", filled, "GTC", "cancelled", created_at, updated_at,
        ),
    )
    if execution_qty is not None:
        store._connection.execute(
            """INSERT INTO executions (
                trading_account_id, category, exec_id, order_id, symbol,
                side, price, quantity, fee, exchange_timestamp_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ACCOUNT.value, "linear", "prior-exec", "previous-b2-limit",
                execution_symbol, "Buy", "1", execution_qty, "0", execution_at,
            ),
        )
    return candidate


@pytest.mark.parametrize(
    ("created_at", "updated_at", "filled", "execution_qty",
     "execution_at", "execution_symbol", "expected"),
    [
        (100, 300, "242", "242", 250, SYMBOL, True),
        (100, 300, "242", "241", 250, SYMBOL, False),
        (100, 300, "242", None, 250, SYMBOL, False),
        (100, 300, "242", "242", 1000, SYMBOL, False),
        (100, 1000, "242", "242", 250, SYMBOL, False),
        (1000, 1001, "242", "242", 1000, SYMBOL, False),
        (100, 300, "242", "242", 250, "ADAUSDT", False),
        (100, 300, "NaN", "242", 250, SYMBOL, False),
        (100, 300, "0", None, 250, SYMBOL, True),
    ],
)
def test_never_traded_proof_requires_prior_witnessed_cancelled_partial_fill(
    tmp_path: Path, created_at, updated_at, filled, execution_qty,
    execution_at, execution_symbol, expected,
):
    store = SQLiteStore.open(tmp_path / "paper.sqlite3")
    try:
        candidate = _seed_candidate_and_prior_limit(
            store,
            created_at=created_at, updated_at=updated_at, filled=filled,
            execution_qty=execution_qty, execution_at=execution_at,
            execution_symbol=execution_symbol,
        )
        assert store.prove_approved_candidate_never_traded(candidate) is expected
        # Proof reads only; no candidate terminalization or trade fabrication.
        assert store.get_robot_candidate(candidate.candidate_id).status == "APPROVED"
    finally:
        store.close()


def test_post_approval_execution_on_another_order_still_blocks_proof(tmp_path: Path):
    store = SQLiteStore.open(tmp_path / "paper.sqlite3")
    try:
        candidate = _seed_candidate_and_prior_limit(store)
        assert store.prove_approved_candidate_never_traded(candidate)
        store._connection.execute(
            """INSERT INTO executions (
                trading_account_id, category, exec_id, order_id, symbol,
                side, price, quantity, fee, exchange_timestamp_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ACCOUNT.value, "linear", "new-exec", "another-order", SYMBOL,
             "Buy", "1", "1", "0", 1001),
        )
        assert not store.prove_approved_candidate_never_traded(candidate)
    finally:
        store.close()

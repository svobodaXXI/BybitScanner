"""Real Box PAPER_AUTO handoff under reentry policy; temp DB only."""
from decimal import Decimal
from pathlib import Path

from terminal.application.robot_autopilot_shadow import (
    SOURCE_BOX_PLAN, admit_arrived_auto_candidate,
)
from terminal.domain.models import TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore


ACCOUNT = TradingAccountId("paper")


def canonical_box_snapshot():
    # Fixed explicit fixture from the already verified approved LONG planner.
    def exposure(q, e, profit, loss, rr):
        return dict(quantity=q, average_entry=e, net_target_profit=profit,
                    net_stop_loss=loss, reward_risk=rr)
    return dict(
        contract_version=1, planner_version="099cfedc", pattern="IKIGAI_BOX",
        environment="PAPER", execution_authorized=False, attempt=1,
        identity=dict(venue="bybit", market="linear", symbol="BTCUSDT", timeframe="5",
                      direction="LONG", a_time_ms=1000, b_time_ms=2000),
        decision_time_ms=300000, anchors=dict(a_price="112.94498381877023", b_price="100"),
        fibonacci=dict(f1="100", f1618="92", f2618="79.05501618122977"),
        inputs=dict(working_quantity="8", tick_size="0.01", entry_fee_rate="0",
                    target_fee_rate="0", stop_fee_rate="0", structural_stop=None),
        plan=dict(direction="LONG", limit_prices=["94", "93.2", "92.4", "91.6"],
                  limit_quantities=["2"] * 4, frozen_f1="100", frozen_f1618="92",
                  take_price="99.2", grid_spacing="0.8", stop_price="89.6",
                  stop_basis="FULL_GRID_RR_CAP", environment="PAPER", execution_authorized=False,
                  full_position=exposure("8", "92.8", "51.2", "25.6", "2"),
                  slices=[exposure("2", "94", "10.4", "8.8", "1.181818181818181818181818182"),
                          exposure("2", "93.2", "12", "7.2", "1.666666666666666666666666667"),
                          exposure("2", "92.4", "13.6", "5.6", "2.428571428571428571428571429"),
                          exposure("2", "91.6", "15.2", "4", "3.8")],
                  partial_fill_loss_upper_bound="25.6",
                  minimum_partial_fill_rr="1.181818181818181818181818182"))



def test_canonical_box_plan_and_robot_diary_reserve_atomically(tmp_path, monkeypatch):
    monkeypatch.setenv("BYBITSCANNER_STOP_REENTRY_AUTO", "1")
    path = Path(tmp_path) / "paper.sqlite3"
    with SQLiteStore.open(path) as store:
        store.initialize_paper_account(ACCOUNT, Decimal("5000"), updated_at_ms=1)
        runtime = store.initialize_robot_runtime_state(ACCOUNT, updated_at_ms=1)
        store.update_robot_runtime_state(
            ACCOUNT, mode="ROBOT_RUNNING", recovery_status="READY",
            reason=None, expected_version=runtime.version, updated_at_ms=2,
        )
        ap = store.initialize_robot_autopilot_state(ACCOUNT, updated_at_ms=1)
        store.update_robot_autopilot_state(
            ACCOUNT, mode="PAPER_AUTO", expected_version=ap.version,
            updated_at_ms=2,
        )
        source, created = store.save_box_plan_only(
            snapshot=canonical_box_snapshot(), created_at_ms=300001,
        )
        assert created
        result = admit_arrived_auto_candidate(
            store, ACCOUNT, source=SOURCE_BOX_PLAN,
            candidate_ref=source.candidate_id, clock_ms=lambda: 600000,
            protection_healthy=lambda: True,
            candidate_fresh=lambda *_: True,
            daily_loss_gate_enabled=False,
        )
        assert result is not None
        assert result.result.outcome == "ALLOW", result.result
        assert result.candidate_created
        assert result.candidate.candidate_id != source.candidate_id
        assert store._connection.execute(
            "SELECT count(*) FROM robot_reentry_campaigns"
        ).fetchone()[0] == 1
        row = store._connection.execute(
            """SELECT candidate_id, reserved_risk_usdt FROM robot_reentry_attempts
               WHERE attempt_index=1"""
        ).fetchone()
        assert row["candidate_id"] == result.candidate.candidate_id
        assert Decimal(row["reserved_risk_usdt"]) == (
            Decimal("25.6") + Decimal("8") * Decimal("92.8") * Decimal("0.002")
        )
        assert store._connection.execute(
            "SELECT count(*) FROM robot_trades"
        ).fetchone()[0] == 0

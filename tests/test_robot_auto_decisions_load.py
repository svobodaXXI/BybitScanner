"""Full audit reads retain account isolation, ordering and opaque facts."""
import tempfile
import unittest
from pathlib import Path

from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import RobotAutoDecisionRecord, SQLiteStore


class AutoDecisionLoadTests(unittest.TestCase):
    def test_full_read_matches_sql_contract_after_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.sqlite3"
            expected = {}
            with SQLiteStore.open(path) as store:
                for account in ("paper", "paper-other", "PAPER"):
                    key = TradingAccountId(account)
                    store.initialize_robot_autopilot_state(key, updated_at_ms=0)
                    store.update_robot_autopilot_state(
                        key, mode="SHADOW", expected_version=1, updated_at_ms=1,
                    )
                    records = []
                    for suffix, timestamp in (("z", 2), ("é", 1), ("a", 1), ("A", 1)):
                        record = RobotAutoDecisionRecord(
                            decision_id=f"{account}-{suffix}", trading_account_id=key,
                            candidate_ref=suffix, pattern="Wedge", symbol=Symbol("BTCUSDT"),
                            timeframe="1", source_identity=suffix, snapshot_sha256=None,
                            mode="SHADOW", policy_version="v1", outcome="WAIT",
                            reason_code="test", evaluated_at_ms=timestamp,
                            resulting_candidate_id=None,
                            facts_json='{"opaque": "' + account + ('x' * 8192) + '"}',
                        )
                        store.append_robot_auto_decision(record)
                        records.append(record)
                    ordered_ids = [row[0] for row in store._connection.execute(
                        "SELECT decision_id FROM robot_auto_decisions "
                        "WHERE trading_account_id=? ORDER BY evaluated_at_ms, decision_id",
                        (account,),
                    )]
                    by_id = {record.decision_id: record for record in records}
                    expected[account] = tuple(by_id[item] for item in ordered_ids)
            with SQLiteStore.open_reader(path) as store:
                for account, records in expected.items():
                    self.assertEqual(store.load_robot_auto_decisions(TradingAccountId(account)), records)
                self.assertEqual(store.load_robot_auto_decisions(TradingAccountId("missing")), ())

    def test_empty_history(self):
        with tempfile.TemporaryDirectory() as directory:
            with SQLiteStore.open(Path(directory) / "empty.sqlite3") as store:
                self.assertEqual(store.load_robot_auto_decisions(TradingAccountId("paper")), ())

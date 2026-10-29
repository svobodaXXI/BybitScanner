"""D6 Trading Diary projection of one canonical Robot reentry lineage.

All tests use disposable local SQLite. No VPS/exchange/backend operations.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from terminal.diary.reentry import ReentryDiaryReader
from terminal.persistence.sqlite_store import SQLiteStore


class ReentryDiaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "paper.sqlite3"
        with SQLiteStore.open(self.path) as store:
            self.assertEqual(store.settings().schema_version, 26)

    def _connect(self):
        con = sqlite3.connect(self.path)
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def _candidate(self, con, candidate_id, digest):
        con.execute(
            """INSERT INTO robot_candidates (
                candidate_id,trading_account_id,symbol,status,
                signal_snapshot_json,snapshot_sha256,robot_state_json,
                state_revision,approved_at_ms,updated_at_ms
            ) VALUES (?, 'paper','LABUSDT','CLOSED','{}',?,NULL,0,100,100)""",
            (candidate_id, digest * 64),
        )

    def _campaign(self, con):
        self._candidate(con, "first-candidate", "a")
        con.execute(
            """INSERT INTO robot_reentry_campaigns
               (trading_account_id,campaign_id,symbol,direction,
                first_candidate_id,frozen_thesis_sha256,
                original_risk_budget_usdt,created_at_ms)
               VALUES ('paper','campaign-1','LABUSDT','LONG',
                       'first-candidate',?,'8',150)""",
            ("f" * 64,),
        )
        con.execute(
            """INSERT INTO robot_reentry_attempts
               (trading_account_id,campaign_id,attempt_index,candidate_id,
                reserved_risk_usdt,previous_stop_exec_id,reserved_at_ms)
               VALUES ('paper','campaign-1',1,'first-candidate',
                       '4',NULL,160)"""
        )

    def _closed_trade(self, con):
        con.execute(
            """INSERT INTO robot_trades (
                trade_id,trading_account_id,candidate_id,symbol,direction,
                pattern,source_timeframe,signal_time_ms,entry_time_ms,entry_path,
                actual_wv,average_entry,stop_price,take_price,
                exit_time_ms,exit_price,exit_reason,realized_pnl_usdt,
                realized_pnl_pct,fees_costs_usdt,version,created_at_ms,
                updated_at_ms,entry_quantity,entry_position_version
            ) VALUES ('trade-1','paper','first-candidate','LABUSDT','LONG',
                      'MIRROR','1',110,200,'LIMIT','1','1','0.9','1.2',
                      300,'0.95','STOP','-1.5','-1.5','0.5',2,200,
                      310,'30',2)"""
        )

    def test_migration_of_existing_v25_preserves_data_and_adds_diary_links(self):
        con = self._connect()
        self._candidate(con, "preexisting", "b")
        con.execute("DROP TABLE robot_reentry_attempts")
        con.execute("DROP TABLE robot_reentry_campaigns")
        con.execute("PRAGMA user_version=25")
        con.commit()
        con.close()
        with SQLiteStore.open(self.path) as store:
            self.assertEqual(store.settings().schema_version, 26)
        con = self._connect()
        count = con.execute("SELECT count(*) FROM robot_candidates").fetchone()[0]
        self.assertEqual(count, 1)
        con.close()

    def test_diary_uses_canonical_robot_statistics_for_net_pnl(self):
        con = self._connect()
        self._campaign(con)
        self._closed_trade(con)
        con.commit()
        con.close()
        campaigns = ReentryDiaryReader(self.path).load()
        self.assertEqual(len(campaigns), 1)
        item = campaigns[0]
        self.assertEqual(item.symbol, "LABUSDT")
        self.assertEqual(item.filled_attempt_count, 1)
        self.assertEqual(str(item.known_net_pnl_usdt), "-2.0")
        self.assertEqual(item.attempts[0].pattern, "MIRROR")
        self.assertEqual(item.attempts[0].exit_reason, "STOP")
        self.assertEqual(str(item.attempts[0].fees_costs_usdt), "0.5")

    def _second_attempt(self, con, *, attempt_index=2, reserved_at_ms=360):
        self._candidate(con, "retry-candidate", "b")
        con.execute(
            """INSERT INTO robot_reentry_attempts (
               trading_account_id,campaign_id,attempt_index,candidate_id,
               reserved_risk_usdt,previous_stop_exec_id,reserved_at_ms)
               VALUES ('paper','campaign-1',?,'retry-candidate','2',
                       ?,?)""", (attempt_index,
                                None if attempt_index == 1 else 'exec-stop-1',
                                reserved_at_ms),
        )

    def _second_closed_trade(self, con, *, signal_at=350, direction="LONG"):
        con.execute(
            """INSERT INTO robot_trades (
               trade_id,trading_account_id,candidate_id,symbol,direction,
               pattern,source_timeframe,signal_time_ms,entry_time_ms,entry_path,
               actual_wv,average_entry,stop_price,take_price,
               exit_time_ms,exit_price,exit_reason,realized_pnl_usdt,
               realized_pnl_pct,fees_costs_usdt,version,created_at_ms,
               updated_at_ms,entry_quantity,entry_position_version
            ) VALUES ('trade-2','paper','retry-candidate','LABUSDT',?,
                      'L-shape','1',?,400,'LIMIT','1','1','0.9','1.2',
                      500,'0.95','TAKE','2','2','0.3',2,400,510,'30',3)""",
            (direction, signal_at),
        )

    def test_unfilled_first_candidate_does_not_count_as_filled_entry(self):
        con = self._connect()
        self._campaign(con)
        con.commit()
        con.close()
        campaign = ReentryDiaryReader(self.path).load()[0]
        self.assertEqual(campaign.filled_attempt_count, 0)
        self.assertIsNone(campaign.known_net_pnl_usdt)
        self.assertEqual([a.status for a in campaign.attempts],
                         ["RESERVED_OR_UNFILLED"])

    def test_second_attempt_can_use_new_pattern_after_proven_stop(self):
        con = self._connect()
        self._campaign(con)
        self._closed_trade(con)
        self._second_attempt(con)
        self._second_closed_trade(con)
        con.commit()
        con.close()
        campaign = ReentryDiaryReader(self.path).load()[0]
        self.assertEqual(campaign.filled_attempt_count, 2)
        self.assertEqual([a.pattern for a in campaign.attempts], ["MIRROR", "L-shape"])
        self.assertEqual([a.exit_reason for a in campaign.attempts], ["STOP", "TAKE"])
        self.assertEqual(str(campaign.known_net_pnl_usdt), "-0.3")

    def test_retry_without_closed_stop_must_not_be_reported_valid(self):
        con = self._connect()
        self._campaign(con)
        self._second_attempt(con)
        con.commit()
        con.close()
        with self.assertRaisesRegex(Exception, "prior closed STOP"):
            ReentryDiaryReader(self.path).load()

    def test_non_stop_exit_cannot_support_retry(self):
        con = self._connect()
        self._campaign(con)
        self._closed_trade(con)
        con.execute("UPDATE robot_trades SET exit_reason='TAKE' WHERE trade_id='trade-1'")
        self._second_attempt(con)
        con.commit()
        con.close()
        with self.assertRaisesRegex(Exception, "prior closed STOP"):
            ReentryDiaryReader(self.path).load()

    def test_attempt_index_duplicate_fails_closed(self):
        con = self._connect()
        self._campaign(con)
        self._closed_trade(con)
        self._second_attempt(con, attempt_index=1)
        con.commit()
        con.close()
        with self.assertRaisesRegex(Exception, "attempt indexes"):
            ReentryDiaryReader(self.path).load()

    def test_retry_trade_direction_conflict_fails_closed(self):
        con = self._connect()
        self._campaign(con)
        self._closed_trade(con)
        self._second_attempt(con)
        self._second_closed_trade(con, direction="SHORT")
        con.commit()
        con.close()
        with self.assertRaisesRegex(Exception, "differs from campaign"):
            ReentryDiaryReader(self.path).load()

    def test_old_formation_can_finish_as_new_confirmed_post_stop_setup(self):
        # The trade signal_time_ms may refer to the first candle of a
        # double-bottom, before STOP. The owning strategy checks the actual
        # *confirmation* close separately in canonical admission.
        con = self._connect()
        self._campaign(con)
        self._closed_trade(con)
        self._second_attempt(con)
        self._second_closed_trade(con, signal_at=250)
        con.commit()
        con.close()
        result = ReentryDiaryReader(self.path).load()[0]
        self.assertEqual(result.filled_attempt_count, 2)

    def test_reentry_execution_cannot_overlap_prior_position(self):
        con = self._connect()
        self._campaign(con)
        self._closed_trade(con)
        self._second_attempt(con)
        self._second_closed_trade(con)
        con.execute("UPDATE robot_trades SET entry_time_ms=300 WHERE trade_id='trade-2'")
        con.commit()
        con.close()
        with self.assertRaisesRegex(Exception, "entry predates prior STOP"):
            ReentryDiaryReader(self.path).load()

    def test_read_only_diary_does_not_create_missing_database(self):
        missing = self.path.with_name("missing.sqlite3")
        with self.assertRaisesRegex(Exception, "does not exist"):
            ReentryDiaryReader(missing).load()
        self.assertFalse(missing.exists())

    def test_account_scoping_does_not_leak_other_trades(self):
        con = self._connect()
        self._campaign(con)
        con.commit()
        con.close()
        self.assertEqual(ReentryDiaryReader(self.path).load(trading_account_id="other"), ())


if __name__ == "__main__":
    unittest.main()

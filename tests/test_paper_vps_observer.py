"""Offline-only tests of the public-safe scheduled PAPER observer."""
import json
import unittest
from datetime import datetime, timezone
from unittest import mock

from ci import paper_vps_observer as observer

AT = "2026-11-18T00:00:00Z"
SHA = "c6f6990abd68e8ed631fbd2579f4833866871741"


def raw_diag(*, robot="RECONCILIATION_REQUIRED", version=1, secret="SECRET-TOKEN"):
    db = {
        "available": True, "quick_check": True,
        "robot_mode": "ROBOT_RUNNING", "robot_recovery": robot,
        "approvals": 9, "open_robot_trades": 1,
    }
    if version == 2:
        db["robot_reason"] = {
            "kind": "PROTECTION_COVERAGE_LOST", "fingerprint": "randomsecret",
            "symbol": "ALICEUSDT",
        }
        db["recent_exit_reasons_72h"] = {"EMERGENCY_CLOSE": 3}
    return "DIAGNOSE_READ_ONLY: " + json.dumps({
        "kind": "PAPER_STOP_READ_ONLY", "version": version,
        "sha": SHA, "api": {
            "health": {
                "reachable": True, "ok": True, "paper": True,
                "build_sha": SHA, "note": secret,
            },
            "scanner": {"reachable": True, "mode": "SCANNER_RUNNING"},
            "autopilot": {"reachable": True, "mode": "PAPER_AUTO"},
            "protection": {
                "reachable": True, "healthy": True, "unhealthy_count": 0,
            },
        }, "db": db, "units": {
            "bybitscanner-telegram.service": "active",
            "untrusted": secret,
        },
    }, ensure_ascii=False)


class ObserverTests(unittest.TestCase):
    def test_old_pinned_diagnose_reports_fenced_but_no_private_values(self):
        snap = observer.sanitize_diagnostic(
            raw_diag(), ssh_exit=0, at=AT,
        )
        self.assertEqual(snap["status"], "FENCED")
        self.assertEqual(snap["robot"], "RECONCILIATION_REQUIRED")
        self.assertEqual(snap["protection"], "HEALTHY")
        self.assertEqual(snap["installed_sha"], SHA)
        self.assertEqual(snap["reason_class"], "UNAVAILABLE")
        rendered = json.dumps(snap) + observer.render_comment(snap)
        for forbidden in ("SECRET-TOKEN", "ALICEUSDT", "approvals", "open_robot_trades"):
            self.assertNotIn(forbidden, rendered)

    def test_new_pinned_diagnose_reports_allowlisted_reason_class_only(self):
        snap = observer.sanitize_diagnostic(
            raw_diag(version=2), ssh_exit=0, at=AT,
        )
        self.assertEqual(snap["status"], "FENCED")
        self.assertEqual(snap["reason_class"], "PROTECTION_COVERAGE_LOST")
        rendered = json.dumps(snap) + observer.render_comment(snap)
        self.assertNotIn("ALICEUSDT", rendered)
        self.assertNotIn("randomsecret", rendered)

    def test_connection_failure_corrupt_input_or_unknown_schema_fails_closed(self):
        good = raw_diag()
        for raw, exit_code in (
            (good, 255),
            ("", 0),
            ("DIAGNOSE_READ_ONLY: {}", 0),
            (good + "\n" + good, 0),
            ("DIAGNOSE_READ_ONLY: {bad json", 0),
            ("DANGER: " + good, 0),
            ("x" * 65537 + good, 0),
        ):
            with self.subTest(raw_prefix=raw[:40], exit_code=exit_code):
                snap = observer.sanitize_diagnostic(raw, ssh_exit=exit_code, at=AT)
                self.assertEqual(snap["status"], "UNKNOWN")
                self.assertEqual(snap["robot"], "UNKNOWN")
                self.assertEqual(snap["installed_sha"], None)

    def test_reported_ready_is_not_claimed_safe_to_trade(self):
        snap = observer.sanitize_diagnostic(
            raw_diag(robot="READY"), ssh_exit=0, at=AT,
        )
        self.assertEqual(snap["status"], "RUNNING_REPORTED")
        self.assertIn("не", observer.render_comment(snap))
        self.assertNotIn("ACCEPTED", observer.render_comment(snap))

    def test_invalid_open_protection_never_returns_running_reported(self):
        raw = raw_diag(robot="READY").replace(
            '"healthy": true', '"healthy": false',
        )
        snap = observer.sanitize_diagnostic(raw, ssh_exit=0, at=AT)
        self.assertEqual(snap["status"], "DEGRADED")
        self.assertEqual(snap["protection"], "UNHEALTHY")

    def test_change_dedup_and_daily_heartbeat(self):
        snap = observer.sanitize_diagnostic(raw_diag(), ssh_exit=0, at=AT)
        original = observer.fingerprint(snap)
        now = datetime(2026, 11, 18, 5, tzinfo=timezone.utc)
        with (
            mock.patch.object(observer, "_last_bot_record",
                              return_value=(original, datetime(
                                  2026, 11, 18, 4, tzinfo=timezone.utc))) as latest,
            mock.patch.object(observer, "_api") as api,
        ):
            self.assertEqual(observer.publish(snap, "fake-token", now=now), "UNCHANGED")
            latest.assert_called_once()
            api.assert_not_called()
        with (
            mock.patch.object(observer, "_last_bot_record",
                              return_value=(original, datetime(
                                  2026, 11, 17, 3, tzinfo=timezone.utc))),
            mock.patch.object(observer, "_api", return_value=({"id": 10}, "")) as api,
        ):
            self.assertEqual(observer.publish(snap, "fake-token", now=now), "RECORDED")
            self.assertEqual(api.call_args.args[1], "POST")
            self.assertTrue(api.call_args.args[3]["body"].startswith(observer.MARKER))

    def test_last_page_lookup_preserves_per_page_and_selects_bot_only(self):
        import types
        latest = {
            "user": {"login": "github-actions[bot]"},
            "body": observer.MARKER + "a" * 20 + " -->\\nsummary",
            "created_at": "2026-11-18T01:00:00Z",
        }
        link = (
            '<https://api.github.com/repos/svobodaXXI/BybitScanner/'
            'issues/1136/comments?per_page=100&page=13>; rel="last"'
        )
        with mock.patch.object(observer, "_api", side_effect=[
            ([], link), ([latest], ""),
        ]) as fetch:
            marker, stamp = observer._last_bot_record("fake-token")
        self.assertEqual(marker, "a" * 20)
        self.assertEqual(stamp, datetime(2026, 11, 18, 1, tzinfo=timezone.utc))
        self.assertTrue(fetch.call_args_list[1].args[2].endswith(
            "per_page=100&page=13",
        ))

    def test_publish_rejects_unallowlisted_text_without_calling_github(self):
        snap = observer.sanitize_diagnostic(raw_diag(), ssh_exit=0, at=AT)
        snap["reason_class"] = "SECRET-TOKEN"
        with mock.patch.object(observer, "_last_bot_record") as api:
            with self.assertRaises(ValueError):
                observer.publish(snap, "fake-token")
            api.assert_not_called()

    def test_no_public_journal_write_from_raw_or_restricted_keys(self):
        snapshot = observer.sanitize_diagnostic(raw_diag(), ssh_exit=0, at=AT)
        self.assertEqual(set(snapshot), set(observer._unknown(AT)))
        self.assertIn("sha", observer.render_comment(snapshot).lower())
        self.assertNotIn("SECRET-TOKEN", observer.render_comment(snapshot))


if __name__ == "__main__":
    unittest.main()

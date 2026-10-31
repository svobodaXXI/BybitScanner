"""Exceptional FLAT-only transition: synthetic process and in-memory SQLite."""
from contextlib import contextmanager
from pathlib import Path
import signal
import unittest
from unittest import mock

from tests.test_flat_paper_recovery_gate import fixture, IDENTITY
from tools.flat_paper_recovery_gate import FlatRecoveryBlocked
from tools.flat_paper_recovery_transition import execute_flat_handoff, _send_exact_sigint


SHA = "d345411c95a079a2c8ac3cd02d9f875700ba8ca3"
PID = 500879


class TransitionCase(unittest.TestCase):
    def case(self, *, execute=False, mutate=None, token=None, pid=None, exit_after=True):
        conn, snapshots = fixture()
        snapshots.pop("expected_identity")  # passed independently by handoff
        snapshots["backend"]["build_sha"] = SHA
        snapshots["backend"]["process_instance_id"] = "old-paper-process"
        if mutate:
            mutate(conn, snapshots)
        events = []
        live = [True]
        @contextmanager
        def barrier(_):
            events.append("barrier:enter")
            try:
                yield conn
            finally:
                events.append("barrier:exit")
        def interrupt(p, signum):
            events.append(("signal", p, signum))
            if exit_after:
                live[0] = False
        tick = [0]
        def advancing_clock():
            tick[0] += 1
            return tick[0]
        result = execute_flat_handoff(
            db_path=Path("/no-vps-access"),
            expected_identity=IDENTITY, expected_pid=PID,
            expected_build_sha=SHA, execute=execute, snapshots=snapshots,
            service_pid=pid or (lambda: PID if live[0] else 0),
            start_token=token or (lambda p: "start-77"),
            send_interrupt=interrupt, is_alive=lambda p: live[0],
            writer_guard=barrier,
            monotonic=advancing_clock,
            sleep=lambda n: None,
        )
        return result, events, conn

    def test_preflight_never_signals_and_does_not_modify_sqlite(self):
        result, events, conn = self.case()
        self.assertTrue(result.startswith("PRECHECK_ONLY:"))
        self.assertEqual(events, ["barrier:enter", "barrier:exit"])
        self.assertEqual(conn.execute(
            "SELECT status FROM paper_protection_obligations"
        ).fetchone(), ("DISPATCHING",))

    def test_one_signal_only_inside_barrier_after_proof(self):
        result, events, _ = self.case(execute=True)
        self.assertTrue(result.startswith("INTERRUPT_EXIT_OBSERVED:"))
        self.assertEqual(events, [
            "barrier:enter", ("signal", PID, signal.SIGINT), "barrier:exit",
        ])

    def test_any_open_exposure_blocks_without_signal(self):
        def mutate(conn, snapshots):
            conn.execute("UPDATE position_projections SET quantity='422',side='Short' "
                         "WHERE symbol='VIRTUALUSDT'")
        with self.assertRaises(FlatRecoveryBlocked):
            self.case(execute=True, mutate=mutate)

    def test_mismatched_build_blocks(self):
        def mutate(conn, snapshots):
            snapshots["backend"]["build_sha"] = "0" * 40
        with self.assertRaisesRegex(FlatRecoveryBlocked, "installed_build_sha_changed"):
            self.case(execute=True, mutate=mutate)

    def test_changed_systemd_pid_blocks(self):
        with self.assertRaisesRegex(FlatRecoveryBlocked, "systemd_main_pid_changed"):
            self.case(execute=True, pid=lambda: PID+1)

    def test_changed_start_token_blocks(self):
        attempts = iter(["start-77", "start-78"])
        with self.assertRaisesRegex(FlatRecoveryBlocked, "backend_process_changed"):
            self.case(execute=True, token=lambda p: next(attempts))

    def test_busdt_evidence_ambiguity_blocks(self):
        def mutate(conn, snapshots):
            conn.execute("UPDATE executions SET quantity='486'")
        with self.assertRaises(FlatRecoveryBlocked):
            self.case(execute=True, mutate=mutate)

    def test_unfinished_market_blocks(self):
        def mutate(conn, snapshots):
            conn.execute("INSERT INTO trading_commands VALUES ('paper','unknown')")
        with self.assertRaises(FlatRecoveryBlocked):
            self.case(execute=True, mutate=mutate)

    def test_unknown_exit_never_retries_signal(self):
        result, events, _ = self.case(execute=True, exit_after=False)
        self.assertTrue(result.startswith("OUTCOME_UNKNOWN:"))
        self.assertEqual(
            [event for event in events if isinstance(event, tuple) and event[0] == "signal"],
            [("signal", PID, signal.SIGINT)],
        )

    def test_linux_pidfd_pins_process_before_signal(self):
        with (mock.patch("tools.flat_paper_recovery_transition.os.pidfd_open", return_value=19) as open_fd,
              mock.patch("tools.flat_paper_recovery_transition._service_pid", return_value=PID),
              mock.patch("tools.flat_paper_recovery_transition._process_start_token", return_value="start-77"),
              mock.patch("tools.flat_paper_recovery_transition.signal.pidfd_send_signal") as send,
              mock.patch("tools.flat_paper_recovery_transition.os.close") as close):
            _send_exact_sigint(PID, "start-77")
            open_fd.assert_called_once_with(PID, 0)
            send.assert_called_once_with(19, signal.SIGINT, None, 0)
            close.assert_called_once_with(19)

    def test_reused_pidfd_blocks_signal_and_closes_handle(self):
        with (mock.patch("tools.flat_paper_recovery_transition.os.pidfd_open", return_value=19),
              mock.patch("tools.flat_paper_recovery_transition._service_pid", return_value=PID),
              mock.patch("tools.flat_paper_recovery_transition._process_start_token", return_value="new-instance"),
              mock.patch("tools.flat_paper_recovery_transition.signal.pidfd_send_signal") as send,
              mock.patch("tools.flat_paper_recovery_transition.os.close") as close):
            with self.assertRaisesRegex(FlatRecoveryBlocked, "backend_process_changed"):
                _send_exact_sigint(PID, "old-instance")
            send.assert_not_called()
            close.assert_called_once_with(19)

    def test_owner_authorization_requires_exact_pid(self):
        with self.assertRaisesRegex(FlatRecoveryBlocked, "expected_pid_invalid"):
            execute_flat_handoff(
                db_path=Path("/none"), expected_identity=IDENTITY,
                expected_pid=0, expected_build_sha=SHA, execute=True,
            )


if __name__ == "__main__":
    unittest.main()

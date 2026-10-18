"""AUTOPILOT-DAILY-GATE-1: PAPER_AUTO daily-loss gate (-10% block / resume strictly above -7%)."""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import json
import tempfile
import threading
import unittest
from unittest import mock

from terminal.application import robot_autopilot as ap
from terminal.application import robot_autopilot_shadow as shadow
from terminal.application.execution_engine import ExecutionEngine
from terminal.application.paper_daily_equity import MarkPrice, PaperDailyEquityFacts
from terminal.domain.models import Category, ExecutionId, OrderId, OrderSide
from terminal.exchange.events import ExecutionEvent
from terminal.persistence.sqlite_store import SQLiteStore
from tests.test_robot_autopilot_shadow import _Db, _wedge, ACCOUNT

D0 = 1791925200000  # 2026-10-14 00:00 MSK
MIN = 60_000


def _equity(pct, *, date="2026-10-14", available=True):
    base = Decimal(5000)
    change = None if pct is None else base * Decimal(pct) / 100
    return PaperDailyEquityFacts(
        "paper", date, D0, D0 + MIN, base if available else None,
        None if change is None else base + change, change,
        None if pct is None else Decimal(pct), available,
        None if available else "POSITION_OPEN_AT_DAY_START")


class _Audit:
    """Stand-in for an audited PAPER_AUTO decision row (mode + facts_json)."""

    def __init__(self, gate, mode="PAPER_AUTO"):
        self.mode = mode
        self.facts_json = json.dumps({"daily_loss_gate": gate})


def _facts(gate, mode="PAPER_AUTO", environment="PAPER"):
    return ap.RobotAutoAdmissionFacts(
        autopilot_mode=mode, environment=environment, robot_mode="ROBOT_RUNNING",
        robot_recovery_status="READY", candidate_valid=True, candidate_executable=True,
        candidate_stale=False, candidate_invalidated=False, already_admitted=False,
        reconciliation_clear=True, symbol_owned=False, protection_healthy=True,
        portfolio_policy_ready=True, portfolio_facts={"available": True, "occupied_ro": 0},
        candidate_fresh=True, daily_loss_gate=gate)


class HysteresisTests(unittest.TestCase):
    def gate(self, pct, history=(), *, enabled=True, **kw):
        return ap.daily_loss_gate_facts(_equity(pct, **kw), [_Audit(g) for g in history],
                                        enabled=enabled)

    def test_block_at_exactly_minus_ten_and_not_above(self):
        self.assertEqual((self.gate("-10")["latched"], self.gate("-10")["transition"]), (True, "BLOCKED"))
        self.assertFalse(self.gate("-9.99")["latched"])
        self.assertFalse(self.gate("-8")["latched"])  # never blocked today: -8% is open

    def test_resume_only_strictly_above_minus_seven(self):
        blocked = self.gate("-10.5")
        self.assertTrue(self.gate("-8", [blocked])["latched"])
        at_seven = self.gate("-7", [blocked])
        self.assertEqual((at_seven["latched"], at_seven["transition"]), (True, None))
        resumed = self.gate("-6.99", [blocked])
        self.assertEqual((resumed["latched"], resumed["transition"]), (False, "RESUMED"))
        # After resuming the latch is open again until the next -10% crossing.
        self.assertFalse(self.gate("-9", [blocked, resumed])["latched"])

    def test_new_msk_date_resets_the_latch(self):
        blocked = self.gate("-12", date="2026-10-13")
        self.assertFalse(self.gate("-8", [blocked])["latched"])
        self.assertIsNone(self.gate("-8", [blocked])["previous_latched"])

    def test_unavailable_equity_keeps_a_same_day_block_and_is_never_open(self):
        self.assertIsNone(self.gate(None, available=False)["latched"])
        blocked = self.gate("-11")
        self.assertTrue(self.gate(None, [blocked], available=False)["latched"])
        # An unavailable observation carries no latch: the block is still found behind it.
        unknown = self.gate(None, [blocked], available=False) | {"latched": None}
        self.assertTrue(self.gate("-8", [blocked, unknown])["latched"])

    def test_shadow_rows_and_malformed_latches(self):
        blocked = self.gate("-11")
        self.assertFalse(ap.daily_loss_gate_facts(_equity("-8"), [_Audit(blocked, mode="SHADOW")],
                                                  enabled=True)["latched"])
        with self.assertRaises(ValueError):
            ap.daily_loss_gate_facts(_equity("-8"), [_Audit(blocked | {"latched": "yes"})], enabled=True)


class PolicyTests(unittest.TestCase):
    def test_enabled_gate_outcomes(self):
        open_gate = ap.daily_loss_gate_facts(_equity("-3"), [], enabled=True)
        self.assertEqual(ap.evaluate_auto_admission(_facts(open_gate)).outcome, ap.OUTCOME_ALLOW)
        blocked = ap.daily_loss_gate_facts(_equity("-10"), [], enabled=True)
        self.assertEqual(ap.evaluate_auto_admission(_facts(blocked)).reason_code, ap.REASON_DAILY_LOSS_LIMIT)
        unknown = ap.daily_loss_gate_facts(_equity(None, available=False), [], enabled=True)
        self.assertEqual(ap.evaluate_auto_admission(_facts(unknown)).reason_code,
                         ap.REASON_DAILY_EQUITY_UNAVAILABLE)
        self.assertEqual(ap.evaluate_auto_admission(_facts(None)).reason_code,
                         ap.REASON_DAILY_EQUITY_UNAVAILABLE)

    def test_disabled_gate_exempts_only_itself_and_is_still_audited(self):
        blocked = ap.daily_loss_gate_facts(_equity("-15"), [], enabled=False)
        self.assertEqual((blocked["enabled"], blocked["latched"], blocked["transition"]),
                         (False, True, "BLOCKED"))
        self.assertEqual(ap.evaluate_auto_admission(_facts(blocked)).outcome, ap.OUTCOME_ALLOW)
        unknown = ap.daily_loss_gate_facts(_equity(None, available=False), [], enabled=False)
        self.assertEqual(ap.evaluate_auto_admission(_facts(unknown)).outcome, ap.OUTCOME_ALLOW)
        # Every other gate still applies.
        other = replace(_facts(blocked), protection_healthy=False)
        self.assertEqual(ap.evaluate_auto_admission(other).reason_code, ap.REASON_PROTECTION_UNHEALTHY)
        self.assertEqual(ap.evaluate_auto_admission(replace(_facts(blocked), symbol_owned=True)).reason_code,
                         ap.REASON_SYMBOL_OWNED)

    def test_shadow_and_live_are_unaffected(self):
        self.assertEqual(ap.evaluate_auto_admission(_facts(None, mode="SHADOW")).outcome, ap.OUTCOME_ALLOW)
        live = _facts(ap.daily_loss_gate_facts(_equity("-1"), [], enabled=False), environment="LIVE")
        self.assertEqual(ap.evaluate_auto_admission(live).reason_code, ap.REASON_LIVE_NOT_ALLOWED)

    def test_only_the_exact_owner_value_disables_the_gate(self):
        self.assertTrue(ap.daily_loss_gate_enabled({}))
        for value in ("", "0", "false", "off", "disabled", "DISABLED", "disabled_for_paper_debug "):
            self.assertTrue(ap.daily_loss_gate_enabled({ap.DAILY_LOSS_GATE_ENV: value}), value)
        self.assertFalse(ap.daily_loss_gate_enabled({ap.DAILY_LOSS_GATE_ENV: "DISABLED_FOR_PAPER_DEBUG"}))


class AdmissionTransactionTests(unittest.TestCase):
    """The gate inside the real PAPER_AUTO admission transaction and durable audit."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = _Db(self.root)  # PAPER account 5000 created at 1 ms
        self.store = self.db.store
        state = self.store.get_robot_autopilot_state(ACCOUNT)
        self.store.update_robot_autopilot_state(ACCOUNT, mode="PAPER_AUTO",
                                                expected_version=state.version, updated_at_ms=D0)
        self.n = 0

    def tearDown(self):
        self.store.close()

    def fill(self, side, price, qty, at, symbol="LOSSUSDT"):
        self.n += 1
        price, qty = Decimal(price), Decimal(qty)
        ExecutionEngine(self.store).apply_paper_execution(ExecutionEvent(
            trading_account_id=ACCOUNT, category=Category.LINEAR, symbol=symbol,
            exec_id=ExecutionId(f"x{self.n}"), order_id=OrderId(f"ox{self.n}"), order_link_id=None,
            side=OrderSide(side), execution_price=price, execution_quantity=qty,
            execution_fee=Decimal(0), execution_value=price * qty, is_maker=True,
            executed_at_ms=at, sequence=None))

    def admit(self, ref, now, **kw):
        _wedge(self.db.candidates, ref, symbol=f"{ref.upper()}USDT")
        return shadow.admit_arrived_auto_candidate(
            self.store, ACCOUNT, source=shadow.SOURCE_SCANNER, candidate_ref=ref,
            protection_healthy=lambda: True, candidate_fresh=lambda *_: True,
            candidate_store_dir=self.db.candidates, clock_ms=lambda: now, **kw)

    def outcome(self, admission):
        return admission.result.outcome, admission.result.reason_code

    def test_healthy_day_allows_and_audits_the_gate(self):
        admission = self.admit("a", D0 + MIN)
        self.assertEqual(self.outcome(admission), (ap.OUTCOME_ALLOW, ap.REASON_ELIGIBLE))
        gate = json.loads(admission.decision.facts_json)["daily_loss_gate"]
        self.assertEqual((gate["enabled"], gate["latched"], gate["daily_change_pct"],
                          gate["business_date_msk"]), (True, False, "0", "2026-10-14"))

    def test_minus_ten_blocks_then_restart_keeps_the_latch_until_strictly_above_minus_seven(self):
        self.fill("Buy", "1000", "1", D0 + MIN)
        self.fill("Sell", "500", "1", D0 + 2 * MIN)  # -500 = -10%
        self.assertEqual(self.outcome(self.admit("b", D0 + 3 * MIN)),
                         (ap.OUTCOME_WAIT, ap.REASON_DAILY_LOSS_LIMIT))
        self.assertIsNone(self.store.get_robot_candidate("b"))
        self.fill("Buy", "100", "1", D0 + 4 * MIN)
        self.fill("Sell", "250", "1", D0 + 5 * MIN)  # +150 -> exactly -7%
        self.store.close()  # restart: the latch comes back from the durable audit only
        self.store = SQLiteStore.open(self.root / "paper.sqlite3")
        self.assertEqual(self.outcome(self.admit("c", D0 + 6 * MIN)),
                         (ap.OUTCOME_WAIT, ap.REASON_DAILY_LOSS_LIMIT))
        self.fill("Buy", "100", "1", D0 + 7 * MIN)
        self.fill("Sell", "100.5", "1", D0 + 8 * MIN)  # -6.99%
        admission = self.admit("d", D0 + 9 * MIN)
        self.assertEqual(self.outcome(admission), (ap.OUTCOME_ALLOW, ap.REASON_ELIGIBLE))
        self.assertEqual(json.loads(admission.decision.facts_json)["daily_loss_gate"]["transition"], "RESUMED")

    def test_next_msk_day_starts_unblocked_on_its_own_proven_baseline(self):
        self.fill("Buy", "1000", "1", D0 + MIN)
        self.fill("Sell", "400", "1", D0 + 2 * MIN)  # -12%
        self.assertEqual(self.admit("e", D0 + 3 * MIN).result.reason_code, ap.REASON_DAILY_LOSS_LIMIT)
        admission = self.admit("f", D0 + 86_400_000 + MIN)
        gate = json.loads(admission.decision.facts_json)["daily_loss_gate"]
        self.assertEqual((self.outcome(admission), gate["baseline_equity_usdt"], gate["previous_latched"]),
                         ((ap.OUTCOME_ALLOW, ap.REASON_ELIGIBLE), "4400", None))

    def test_open_position_without_fresh_mark_waits_and_a_fresh_mark_allows(self):
        self.fill("Buy", "100", "1", D0 + MIN)
        self.assertEqual(self.admit("g", D0 + 2 * MIN).result.reason_code,
                         ap.REASON_DAILY_EQUITY_UNAVAILABLE)
        marks = lambda: ({"LOSSUSDT": MarkPrice(Decimal("99"), D0 + 3 * MIN)}, 5000)
        self.assertEqual(self.admit("h", D0 + 3 * MIN, daily_marks=marks).result.outcome,
                         ap.OUTCOME_ALLOW)
        stale = lambda: ({"LOSSUSDT": MarkPrice(Decimal("99"), D0)}, 5000)
        self.assertEqual(self.admit("i", D0 + 4 * MIN, daily_marks=stale).result.reason_code,
                         ap.REASON_DAILY_EQUITY_UNAVAILABLE)
        broken = mock.Mock(side_effect=RuntimeError("feed down"))
        self.assertEqual(self.admit("j", D0 + 5 * MIN, daily_marks=broken).result.reason_code,
                         ap.REASON_DAILY_EQUITY_UNAVAILABLE)

    def test_unprovable_baseline_waits_unless_owner_disabled_the_gate(self):
        self.fill("Buy", "100", "1", D0 - MIN)
        self.fill("Sell", "100", "1", D0 + MIN)  # open across 00:00 MSK
        self.assertEqual(self.admit("k", D0 + 2 * MIN).result.reason_code,
                         ap.REASON_DAILY_EQUITY_UNAVAILABLE)
        admission = self.admit("l", D0 + 3 * MIN, daily_loss_gate_enabled=False)
        gate = json.loads(admission.decision.facts_json)["daily_loss_gate"]
        self.assertEqual((admission.result.outcome, gate["enabled"], gate["unavailability_reason"]),
                         (ap.OUTCOME_ALLOW, False, "POSITION_OPEN_AT_DAY_START"))

    def test_disabled_gate_still_audits_the_block_crossing(self):
        self.fill("Buy", "1000", "1", D0 + MIN)
        self.fill("Sell", "450", "1", D0 + 2 * MIN)  # -11%
        admission = self.admit("m", D0 + 3 * MIN, daily_loss_gate_enabled=False)
        gate = json.loads(admission.decision.facts_json)["daily_loss_gate"]
        self.assertEqual((admission.result.outcome, gate["latched"], gate["transition"]),
                         (ap.OUTCOME_ALLOW, True, "BLOCKED"))
        # Re-enabled later the same day: the audited latch still blocks.
        self.assertEqual(self.admit("n", D0 + 4 * MIN).result.reason_code, ap.REASON_DAILY_LOSS_LIMIT)

    def test_competing_admissions_see_one_serialized_latch(self):
        self.fill("Buy", "1000", "1", D0 + MIN)
        self.fill("Sell", "500", "1", D0 + 2 * MIN)
        for ref in ("p", "q"):
            _wedge(self.db.candidates, ref, symbol=f"{ref.upper()}USDT")
        path, results, errors = self.root / "paper.sqlite3", {}, []

        def run(ref):
            store = SQLiteStore.open(path)
            try:
                results[ref] = shadow.admit_arrived_auto_candidate(
                    store, ACCOUNT, source=shadow.SOURCE_SCANNER, candidate_ref=ref,
                    protection_healthy=lambda: True, candidate_fresh=lambda *_: True,
                    candidate_store_dir=self.db.candidates, clock_ms=lambda: D0 + 3 * MIN)
            except Exception as error:  # pragma: no cover - reported below
                errors.append(error)
            finally:
                store.close()

        threads = [threading.Thread(target=run, args=(ref,)) for ref in ("p", "q")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        self.assertEqual(errors, [])
        self.assertEqual({ref: r.result.reason_code for ref, r in results.items()},
                         {"p": ap.REASON_DAILY_LOSS_LIMIT, "q": ap.REASON_DAILY_LOSS_LIMIT})
        transitions = sorted(str(json.loads(r.decision.facts_json)["daily_loss_gate"]["transition"])
                             for r in results.values())
        self.assertEqual(transitions, ["BLOCKED", "None"])  # one crossing, serialized


if __name__ == "__main__":
    unittest.main()


class DailyMarksRuntimeWiringTests(unittest.TestCase):
    """No network or owner-runtime start: prove source completeness and fail-closed handoff."""

    def test_off_owner_provider_requires_all_exchange_marks(self):
        import time
        from terminal.runtime.paper_http_server import LiveOrderBookProvider

        now = int(time.time() * 1000)

        class Response:
            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self):
                pass

            def json(self):
                return self.payload

        class Session:
            def __init__(self, payload):
                self.payload = payload
                self.calls = []

            def get(self, url, *, params, timeout):
                self.calls.append((url, params, timeout))
                return Response(self.payload)

        def feed(tickers, *, age=0):
            session = Session({"retCode": 0, "time": now-age, "result": {"list": tickers}})
            provider = LiveOrderBookProvider(None, rest_session=session)
            return provider.get_mark_prices(("ALPHAUSDT", "BETAUSDT")), session.calls

        full, calls = feed([
            {"symbol": "ALPHAUSDT", "markPrice": "101.25"},
            {"symbol": "BETAUSDT", "markPrice": "3.2"},
        ])
        self.assertEqual(set(full), {"ALPHAUSDT", "BETAUSDT"})
        self.assertEqual(full["ALPHAUSDT"].price, Decimal("101.25"))
        self.assertEqual(len(calls), 1)
        self.assertIn("/v5/market/tickers", calls[0][0])
        self.assertEqual(calls[0][1], {"category": "linear"})
        self.assertEqual(feed([{"symbol": "ALPHAUSDT", "markPrice": "101.25"}])[0], {})
        self.assertEqual(feed([
            {"symbol": "ALPHAUSDT", "markPrice": "101.25"},
            {"symbol": "BETAUSDT", "markPrice": "0"},
        ])[0], {})
        self.assertEqual(feed([
            {"symbol": "ALPHAUSDT", "markPrice": "101.25"},
            {"symbol": "BETAUSDT", "markPrice": "3.2"},
        ], age=10_000)[0], {})

    def test_runtime_owner_reads_all_positions_and_binds_one_captured_snapshot(self):
        from types import SimpleNamespace
        from terminal.runtime.paper_runtime import PaperRuntime

        runtime = object.__new__(PaperRuntime)
        runtime._paper_account_id = ACCOUNT
        runtime.store = SimpleNamespace(load_open_position_projections=mock.Mock(return_value=(
            SimpleNamespace(position_key=SimpleNamespace(symbol=SimpleNamespace(value="ALPHAUSDT"))),
            SimpleNamespace(position_key=SimpleNamespace(symbol=SimpleNamespace(value="BETAUSDT"))),
        )))
        runtime._robot_command_dispatcher = lambda operation: operation(runtime)
        mark = MarkPrice(Decimal("2"), D0 + MIN)
        provider = mock.Mock()
        provider.get_mark_prices.return_value = {"ALPHAUSDT": mark, "BETAUSDT": mark}
        runtime._book_provider = provider
        captured = runtime._prepare_autopilot_daily_marks()
        self.assertEqual(captured, ({"ALPHAUSDT": mark, "BETAUSDT": mark}, 5000))
        provider.get_mark_prices.assert_called_once_with(("ALPHAUSDT", "BETAUSDT"))
        provider.get_mark_prices.return_value = {"ALPHAUSDT": mark}
        self.assertEqual(runtime._prepare_autopilot_daily_marks(), ({}, 0))
        provider.get_mark_prices.side_effect = RuntimeError("REST down")
        self.assertEqual(runtime._prepare_autopilot_daily_marks(), ({}, 0))

    def test_runtime_forwards_prepared_marks_to_existing_gate_without_disabling(self):
        from types import SimpleNamespace
        from terminal.runtime.paper_runtime import PaperRuntime
        runtime = object.__new__(PaperRuntime)
        runtime.store = SimpleNamespace(get_robot_autopilot_state=lambda _: SimpleNamespace(mode="PAPER_AUTO"))
        runtime._paper_account_id = ACCOUNT
        runtime._autopilot_protection_health = lambda: True
        runtime._autopilot_daily_loss_gate_enabled = True
        runtime._autopilot_candidate_fresh = lambda *_: True
        marks = ({"ALPHAUSDT": MarkPrice(Decimal("2"), D0 + MIN)}, 5000)
        with mock.patch("terminal.runtime.paper_runtime.admit_arrived_auto_candidate") as admission:
            runtime.observe_autopilot_candidate("SCANNER", "candidate", daily_marks=marks)
        kwargs = admission.call_args.kwargs
        self.assertIs(kwargs["daily_loss_gate_enabled"], True)
        self.assertEqual(kwargs["daily_marks"](), marks)


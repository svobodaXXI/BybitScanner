"""HORN-4/HORN-5: observation-only Broadening («Рупор») Scanner integration.

Detection on the closed prefix, chart rendering, Telegram delivery and
deduplication, incremental evidence, visible progress, coexistence with Wedge
delivery and the absence of any trading path. No exchange or Telegram calls.
"""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

import tests.test_telegram_delivery  # noqa: F401  offline config/API stubs
import horn_scanner
import main
import notification
from tests.test_broadening_detector import FIVE, FOUR, zigzag


def snapshot(points, closed_length):
    """Closed candles 0..closed_length-1 plus one extra (possibly open) Bybit candle."""
    closed = zigzag(points, closed_length)
    open_bar = closed.iloc[[-1]].copy()
    open_bar["time"] = int(closed["time"].iloc[-1]) + 300000
    open_bar[["open", "high", "low", "close"]] = [150.0, 160.0, 40.0, 50.0]  # wild, must be ignored
    return pd.concat([closed, open_bar], ignore_index=True)


def read_events(root):
    path = Path(root) / horn_scanner.EVENTS_FILE
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class ObserveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "evidence")
        self.charts = os.path.join(self.tmp.name, "charts")

    def tearDown(self):
        self.tmp.cleanup()

    def observe(self, candles, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return horn_scanner.observe_broadening(
                "TESTUSDT", candles, timeframe="5", chart_dir=self.charts, root=self.root, **kwargs
            )

    def test_four_pivots_preliminary_with_chart_and_incremental_evidence(self):
        candles = snapshot(FOUR, 112)  # closed 0..111: LOW108 confirmed at 111
        observation = self.observe(candles)
        self.assertEqual(observation["stage"], "PRELIMINARY")
        times = [int(candles["time"].iloc[i]) for i in (72, 84, 96, 108)]
        self.assertEqual([a["time_ms"] for a in observation["anchors"]], times)
        self.assertEqual([a["side"] for a in observation["anchors"]], ["H", "L", "H", "L"])
        self.assertEqual(observation["start_time_ms"], times[0])
        self.assertEqual(observation["decision_time_ms"], int(candles["time"].iloc[111]))
        self.assertGreater(observation["upper_line"]["slope"], 0)
        self.assertLess(observation["lower_line"]["slope"], 0)
        self.assertTrue(Path(observation["chart_path"]).is_file())
        ohlc = pd.read_csv(observation["ohlc_path"])
        self.assertEqual(len(ohlc), 112)  # the open candle is never stored or used
        (event,) = read_events(self.root)
        self.assertEqual(event["event"], "horn_detected")
        self.assertEqual(event["identity"], observation["identity"])
        self.assertEqual(event["stage"], "PRELIMINARY")
        self.assertNotIn("direction", json.dumps(event).lower())

    def test_open_candle_never_changes_the_observation(self):
        a = self.observe(snapshot(FOUR, 112))
        candles = snapshot(FOUR, 112)
        candles.loc[len(candles) - 1, ["high", "low"]] = [999.0, 0.001]
        b = self.observe(candles)
        self.assertEqual(
            (a["identity"], a["anchors"], a["upper_line"], a["lower_line"]),
            (b["identity"], b["anchors"], b["upper_line"], b["lower_line"]),
        )

    def test_five_pivots_mature(self):
        observation = self.observe(snapshot(FIVE, 133))
        self.assertEqual(observation["stage"], "MATURE")
        self.assertEqual(len(observation["anchors"]), 5)

    def test_no_formation_writes_nothing(self):
        flat = snapshot([(0, 100.0), (120, 100.5)], 121)
        self.assertIsNone(self.observe(flat))
        self.assertFalse(Path(self.root).exists())

    def test_wedge_on_same_snapshot_is_kept_next_to_horn(self):
        candles = snapshot(FOUR, 112)
        wedge = {
            "pattern": "Falling Wedge", "detected": True,
            "geometry": {"start_index": 60, "end_index": 110,
                         "upper_line": {"slope": -0.1, "intercept": 110.0, "anchor_index": 60, "second_index": 96},
                         "lower_line": {"slope": -0.05, "intercept": 101.0, "anchor_index": 84, "second_index": 108}},
        }
        observation = self.observe(candles, wedge_result=wedge)
        kept = observation["wedge_on_same_snapshot"]
        self.assertEqual(kept["pattern"], "Falling Wedge")
        self.assertEqual(kept["start_time_ms"], int(candles["time"].iloc[60]))
        self.assertEqual(read_events(self.root)[0]["wedge_on_same_snapshot"]["pattern"], "Falling Wedge")


class DeliveryTest(unittest.TestCase):
    """HORN-5 (#509): canonical short text, then the chart with the shared keyboard."""

    OK = {"ok": True, "result": {"message_id": 7}}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "evidence")
        self.charts = os.path.join(self.tmp.name, "charts")
        self.memory = {}

    def tearDown(self):
        self.tmp.cleanup()

    def observation(self, points=FOUR, length=112):
        with contextlib.redirect_stdout(io.StringIO()):
            return horn_scanner.observe_broadening(
                "TESTUSDT", snapshot(points, length), timeframe="5", chart_dir=self.charts, root=self.root,
            )

    def mature(self, preliminary):
        return dict(preliminary, stage="MATURE",
                    formation=SimpleNamespace(**{**vars(preliminary["formation"]), "stage": "MATURE"}))

    def send(self, observation, texts=(), photos=(), test_mode=False):
        """One delivery; returns (result, ordered [(kind, chat_id, args, kwargs)])."""
        calls = []

        def responder(responses, kind):
            responses = iter(responses)

            def call(token, chat_id, *args, **kwargs):
                calls.append((kind, chat_id, args, kwargs))
                response = next(responses)
                if isinstance(response, Exception):
                    raise response
                return response
            return call

        with patch.object(horn_scanner.config, "TELEGRAM_ENABLED", True), \
                patch.object(horn_scanner, "get_telegram_chat_ids", return_value=("owner", "friend")), \
                patch.object(horn_scanner, "get_telegram_owner_chat_id", return_value="owner"), \
                patch.object(horn_scanner, "load_memory", side_effect=lambda: self.memory), \
                patch.object(horn_scanner, "save_memory", side_effect=lambda m: self.memory.update(m)), \
                patch.object(horn_scanner, "send_message", side_effect=responder(texts, "text")), \
                patch.object(horn_scanner, "send_photo", side_effect=responder(photos, "photo")):
            result = horn_scanner.send_broadening_observation(
                "TESTUSDT", observation, timeframe="5", test_mode=test_mode, root=self.root,
            )
        return result, calls

    @staticmethod
    def order(calls):
        return [(kind, chat_id) for kind, chat_id, _, _ in calls]

    @staticmethod
    def buttons(call):
        return [button for row in call[3]["reply_markup"]["inline_keyboard"] for button in row]

    def test_text_then_chart_with_canonical_buttons(self):
        observation = self.observation()
        result, calls = self.send(observation, [self.OK] * 2, [self.OK] * 2)
        self.assertTrue(result)
        self.assertEqual(self.order(calls),
                         [("text", "owner"), ("photo", "owner"), ("text", "friend"), ("photo", "friend")])
        text = calls[0][2][0]
        self.assertEqual(text.splitlines(), [
            "📡 Сканер: TESTUSDT",
            "Рупор · PRELIMINARY — предварительная геометрия",
            notification.format_timeframe_ru("5"),
            "Наблюдение: без сделки",
        ])
        for word in ("LONG", "SHORT", "Баллы", "↑", "↓"):
            self.assertNotIn(word, text)
        self.assertEqual(calls[1][2][0], observation["chart_path"])
        self.assertEqual(calls[1][3]["caption"], "")
        # Exactly the shared builder's keyboards: owner review set, friend TradingView only.
        self.assertEqual(calls[1][3]["reply_markup"],
                         notification.build_tradingview_keyboard("TESTUSDT", "5", include_review_actions=True))
        self.assertEqual(calls[3][3]["reply_markup"],
                         notification.build_tradingview_keyboard("TESTUSDT", "5", include_review_actions=False))
        owner = {b["callback_data"] for b in self.buttons(calls[1]) if "callback_data" in b}
        self.assertLessEqual({f"review:{a}:TESTUSDT:5" for a in ("queue", "good", "geometry", "anchor")}, owner)
        self.assertIn("url", self.buttons(calls[1])[0])
        friend = self.buttons(calls[3])
        self.assertTrue(all("url" in b and "callback_data" not in b for b in friend), friend)
        events = [(e["event"], e["chat_id"], e["ok"], e["message_id"])
                  for e in read_events(self.root) if e["event"] != "horn_detected"]
        self.assertEqual(events, [
            ("horn_text_delivery", "owner", True, 7), ("horn_delivery", "owner", True, 7),
            ("horn_text_delivery", "friend", True, 7), ("horn_delivery", "friend", True, 7),
        ])
        # Same formation and stage on the next pass: nothing is sent again.
        result, calls = self.send(observation)
        self.assertFalse(result)
        self.assertEqual(calls, [])

    def test_review_callbacks_are_accepted_by_the_existing_handler(self):
        import telegram_review
        _, calls = self.send(self.observation(), [self.OK] * 2, [self.OK] * 2)
        reviews = [b["callback_data"] for b in self.buttons(calls[1])
                   if str(b.get("callback_data", "")).startswith("review:")]
        self.assertEqual(len(reviews), 4)
        for data in reviews:
            parsed = telegram_review._parse_callback(data)
            self.assertEqual((parsed["kind"], parsed["symbol"], parsed["timeframe"]), ("review", "TESTUSDT", "5"))

    def test_no_robot_button_or_handoff_for_any_stage(self):
        preliminary = self.observation()
        with patch("pattern_robot_integration.prepare_robot_handoff") as handoff, \
                patch("notification.prepare_robot_handoff") as notification_handoff:
            _, first = self.send(preliminary, [self.OK] * 2, [self.OK] * 2)
            _, second = self.send(self.mature(preliminary), [self.OK] * 2, [self.OK] * 2)
        handoff.assert_not_called()
        notification_handoff.assert_not_called()
        photos = [call for call in first + second if call[0] == "photo"]
        self.assertEqual(len(photos), 4)
        for call in photos:
            for button in self.buttons(call):
                self.assertFalse(str(button.get("callback_data", "")).startswith("robot:"), button)
                self.assertNotIn("Робот", button["text"])

    def test_upgrade_to_mature_is_delivered_once_more(self):
        preliminary = self.observation()
        mature = self.mature(preliminary)
        self.send(preliminary, [self.OK] * 2, [self.OK] * 2)
        result, calls = self.send(mature, [self.OK] * 2, [self.OK] * 2)
        self.assertTrue(result)
        self.assertEqual(len(calls), 4)
        self.assertIn("Рупор · MATURE", calls[0][2][0])
        result, calls = self.send(mature)
        self.assertEqual(calls, [])

    def test_failed_chart_is_retried_without_repeating_the_text(self):
        observation = self.observation()
        result, _ = self.send(observation, [self.OK] * 2, [self.OK, RuntimeError("timeout")])
        self.assertFalse(result)
        failed = [e for e in read_events(self.root) if e["event"] == "horn_delivery" and not e["ok"]]
        self.assertEqual(failed[0]["chat_id"], "friend")
        self.assertIn("timeout", failed[0]["error"])
        result, calls = self.send(observation, [], [self.OK])
        self.assertTrue(result)
        self.assertEqual(self.order(calls), [("photo", "friend")])

    def test_failed_text_sends_no_chart_and_stays_retryable(self):
        observation = self.observation()
        result, calls = self.send(observation, [self.OK, {"ok": False}], [self.OK])
        self.assertFalse(result)
        self.assertEqual(self.order(calls), [("text", "owner"), ("photo", "owner"), ("text", "friend")])
        result, calls = self.send(observation, [self.OK], [self.OK])
        self.assertTrue(result)
        self.assertEqual(self.order(calls), [("text", "friend"), ("photo", "friend")])

    def test_test_mode_does_not_persist_memory(self):
        _, calls = self.send(self.observation(), [self.OK] * 2, [self.OK] * 2, test_mode=True)
        self.assertTrue(calls[0][2][0].endswith("🧪 TEST MODE"))
        self.assertEqual(self.memory, {})


class NoTradingPathTest(unittest.TestCase):
    def test_module_has_no_trading_dependency(self):
        source = Path(horn_scanner.__file__).read_text(encoding="utf-8")
        imports = [line for line in source.splitlines() if line.startswith(("import ", "from "))]
        for forbidden in ("robot", "admission", "pattern_robot_integration", "terminal", "order", "autopilot", "paper"):
            self.assertFalse([line for line in imports if forbidden in line.lower()], forbidden)


class ScanLoopTest(unittest.TestCase):
    def run_pass(self, *, wedge=None, horn_failure=None):
        candles = snapshot(FOUR, 112)
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {
                "BYBITSCANNER_IKIGAI_BOX_SIGNALS": "0",
                "BYBITSCANNER_HORN_OBSERVATION": "1",
                "BYBITSCANNER_HORN_EVIDENCE_DIR": os.path.join(tmp, "evidence"),
            }))
            stack.enter_context(patch.object(main, "MAX_SYMBOLS", None))
            stack.enter_context(patch.object(main.config, "TELEGRAM_TEST_MODE", False))
            stack.enter_context(patch.object(main, "get_symbols", return_value=["AUSDT", "BUSDT"]))
            stack.enter_context(patch.object(main, "analyze_symbol", return_value={"result": wedge, "data": candles}))
            stack.enter_context(patch("l_shape_scanner.observe_l_shape", return_value=None))
            observe = stack.enter_context(patch.object(
                horn_scanner, "observe_broadening",
                side_effect=horn_failure or (lambda symbol, data, **kw: {"identity": f"horn:{symbol}", "stage": "PRELIMINARY"}),
            ))
            deliver = stack.enter_context(patch.object(horn_scanner, "send_broadening_observation", return_value=True))
            send_wedge = stack.enter_context(patch.object(main, "send_signal", return_value=True))
            finished = stack.enter_context(patch.object(main, "send_message"))
            stack.enter_context(patch.object(main, "prepare_signal", return_value={"score": 90}))
            stack.enter_context(patch.object(main, "update_signal", return_value="NEW"))
            stack.enter_context(patch.object(main, "record_scanner_diary_observation", return_value=SimpleNamespace(setup_instance_id=None)))
            robot = stack.enter_context(patch("notification.prepare_robot_handoff"))
            stack.enter_context(contextlib.redirect_stdout(out))
            main.run_scan_pass()
            progress = json.loads((Path(tmp) / "evidence" / horn_scanner.PROGRESS_FILE).read_text(encoding="utf-8"))
        robot.assert_not_called()
        return out.getvalue(), observe, deliver, send_wedge, finished, progress

    def test_progress_is_reported_during_the_pass(self):
        output, observe, deliver, _, finished, progress = self.run_pass()
        lines = [l for l in output.splitlines() if l.startswith("[SCAN PROGRESS]")]
        self.assertEqual(len(lines), 4)  # 2 symbols x (5m, 1m), one line each as it happens
        self.assertTrue(lines[0].startswith("[SCAN PROGRESS] 1/2 AUSDT 5m horn_found=1 horn_sent=1"))
        self.assertTrue(lines[-1].startswith("[SCAN PROGRESS] 2/2 BUSDT 1m horn_found=4 horn_sent=4"))
        self.assertEqual((progress["symbols_done"], progress["symbols_total"], progress["horn_found"]), (2, 2, 4))
        self.assertEqual(observe.call_count, 4)
        self.assertEqual(deliver.call_count, 4)
        self.assertIn("Рупор (наблюдение): найдено 4, отправлено 4", finished.call_args_list[-1].args[0])

    def test_horn_and_wedge_are_both_delivered_without_suppression(self):
        wedge = {"pattern": "Falling Wedge", "final_score": 90, "signal": {"approved": True}}
        _, observe, deliver, send_wedge, _, _ = self.run_pass(wedge=wedge)
        self.assertEqual(deliver.call_count, 4)
        self.assertEqual(send_wedge.call_count, 4)
        self.assertIs(observe.call_args.kwargs["wedge_result"], wedge)

    def test_horn_failure_is_counted_and_does_not_block_wedge(self):
        wedge = {"pattern": "Falling Wedge", "final_score": 90, "signal": {"approved": True}}
        output, _, deliver, send_wedge, _, progress = self.run_pass(wedge=wedge, horn_failure=RuntimeError("render failed"))
        deliver.assert_not_called()
        self.assertEqual(send_wedge.call_count, 4)
        self.assertIn("HORN ERROR: render failed", output)
        self.assertEqual(progress["errors"], 4)


if __name__ == "__main__":
    unittest.main()

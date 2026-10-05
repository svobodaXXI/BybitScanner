"""End-to-end opt-in Scanner/Telegram observation tests (no network or PAPER DB)."""

import os
import contextlib
import io
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pandas as pd

# Reuse existing import-time config/bybit stubs rather than reading local secrets.
import tests.test_telegram_delivery  # noqa: F401
import main
import ikigai_box_scanner as box
import robot_failure_diagnostics as diagnostics
from tests.test_ikigai_box_detector import _two_impulses, _terminal_wick_two_impulses
from geometry.ikigai_box import detect_ikigai_box, detect_ikigai_box_watches
from geometry.ikigai_box_chart import ikigai_box_signal_text


def _candles():
    frame, _, _ = _two_impulses(second_steps=7)
    frame["time"] = [
        1_790_000_000_000 + n * 300_000 for n in range(len(frame))
    ]
    # Simulate Bybit's current, still-open candle: extreme high must never
    # change the first impulse anchor or be sent to the detector/renderer.
    frame.loc[len(frame)] = dict(
        time=int(frame.iloc[-1]["time"]) + 300_000,
        open=100_000, high=100_001, low=99_999, close=100_000,
    )
    return frame


class IkigaiBoxTelegramBridgeTests(unittest.TestCase):
    def test_actual_scanner_without_wedge_sends_confirmed_box_without_robot_affordance(self):
        source = _candles()
        original = source.copy(deep=True)
        history = {}
        plotted = []
        send_order = []

        def fake_render(frame, formation, path, **kwargs):
            plotted.append((frame.copy(), formation, path))
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"fresh-ikigai-image")
            return target

        real_sender = box.send_ikigai_box_observation
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"BYBITSCANNER_IKIGAI_BOX_SIGNALS": "1"}
        ), patch.object(main, "get_symbols", return_value=["TESTUSDT"]), patch.object(
            main, "analyze_symbol",
            side_effect=lambda symbol, *, timeframe: {"symbol": symbol, "result": None, "data": source if timeframe == "5" else None},
        ) as scan, patch.object(
            main, "send_message", return_value=True,
        ), patch.object(
            box, "render_ikigai_box_chart", side_effect=fake_render,
        ), patch.object(
            box, "send_message",
            side_effect=lambda *args: (send_order.append("text"), {"ok": True})[1],
        ) as text, patch.object(
            box, "send_photo",
            side_effect=lambda *args, **kwargs: (
                send_order.append("photo"), {"ok": True}
            )[1],
        ) as photo, patch.object(
            box, "load_memory", side_effect=lambda: dict(history),
        ), patch.object(
            box, "save_memory", side_effect=lambda record: history.update(record),
        ), patch.object(box, "get_telegram_chat_ids", return_value=("owner",)), patch.object(
            box, "get_telegram_owner_chat_id", return_value="owner",
        ), patch(
            "pattern_robot_integration.create_signal_snapshot",
        ) as robot:
            # Actual Scanner integration; temporary chart root can be passed by
            # patching the module's default function call below.
            def send_under_test(symbol, candles, *, timeframe, test_mode=False, **kwargs):
                return real_sender(
                    symbol, candles, timeframe=timeframe,
                    test_mode=test_mode, chart_dir=folder, **kwargs,
                )

            with patch.object(box, "send_ikigai_box_observation", side_effect=send_under_test):
                main.run_scan_pass()
                main.run_scan_pass()

        self.assertEqual(scan.call_count, 4)
        self.assertEqual(photo.call_count, 1)
        text.assert_called_once()
        self.assertEqual(send_order, ["text", "photo"])
        self.assertEqual(len(plotted), 1)
        received_frame, formation, path = plotted[0]
        self.assertEqual(len(received_frame), len(source) - 1)
        self.assertLess(received_frame["high"].max(), 100_000)
        self.assertNotIn("_analysis.png", path)
        self.assertIn("ikigai_box", path)
        self.assertEqual(formation.direction, "SHORT")
        potential = (
            abs(formation.fibonacci_1_618 - formation.fibonacci_1_0)
            / formation.fibonacci_1_0 * 100
        )
        self.assertEqual(
            text.call_args.args[2],
            f"📡 Сканер: TESTUSDT\n"
            f"↑ Коробка Икигаи (+{potential:.2f}%)\n"
            "5м",
        )
        self.assertEqual(photo.call_args.kwargs["caption"], "")
        buttons = [
            button["text"]
            for row in photo.call_args.kwargs["reply_markup"]["inline_keyboard"]
            for button in row
        ]
        self.assertNotIn("🤖 Робот", buttons)
        callbacks = [
            button.get("callback_data")
            for row in photo.call_args.kwargs["reply_markup"]["inline_keyboard"]
            for button in row
            if button.get("callback_data")
        ]
        self.assertFalse(any(
            callback.startswith("robot:")
            for callback in callbacks
        ))
        robot.assert_not_called()
        self.assertEqual(len(history), 1)
        pd.testing.assert_frame_equal(source, original)

    def test_watch_ready_photo_is_distinct_and_never_creates_robot_candidate(self):
        history = {}
        frames, end = _terminal_wick_two_impulses(second=False)
        frames["time"] = [
            1_790_000_000_000 + i * 3_600_000
            for i in range(len(frames))
        ]
        watch = next(
            w for w in detect_ikigai_box_watches(frames)
            if w.anchor_identity == ("SHORT", 20, 23)
        )
        self.assertEqual(watch.phase, "BOX_READY")
        # Bybit returns one still-forming newest candle. Its extreme must
        # never alter WATCH's current frame, frozen anchor or chart.
        live = pd.concat([frames, pd.DataFrame([{
            "time": int(frames.iloc[-1]["time"]) + 3_600_000,
            "open": 1000, "high": 1001, "low": 999, "close": 1000,
        }])], ignore_index=True)
        with tempfile.TemporaryDirectory() as root, patch.object(
            box, "get_telegram_chat_ids", return_value=("owner",),
        ), patch.object(
            box, "send_message", return_value={"ok": True},
        ) as text, patch.object(
            box, "send_photo", return_value={"ok": True},
        ) as photo, patch.object(
            box, "load_memory", side_effect=lambda: dict(history),
        ), patch.object(
            box, "save_memory", side_effect=lambda v: history.update(v),
        ), patch("pattern_robot_integration.create_signal_snapshot") as robot:
            self.assertTrue(box.send_ikigai_box_watch_observation(
                "HEIUSDT", live, watch, timeframe="60", chart_dir=root,
            ))
            self.assertFalse(box.send_ikigai_box_watch_observation(
                "HEIUSDT", live, watch, timeframe="60", chart_dir=root,
            ))
        photo.assert_called_once()
        sent = photo.call_args
        text.assert_called_once()
        self.assertEqual(
            text.call_args.args[2],
            ikigai_box_signal_text("HEIUSDT", "60", watch),
        )
        self.assertEqual(sent.kwargs["caption"], "")
        self.assertNotIn("_analysis.png", sent.args[2])
        self.assertIn("_WATCH_", sent.args[2])
        self.assertEqual(len(history), 1)
        robot.assert_not_called()

    def test_watch_invalid_or_zone_touched_is_not_telegram_signal(self):
        from dataclasses import replace
        frames, _ = _terminal_wick_two_impulses(second=False)
        frames["time"] = [
            1_790_000_000_000 + i * 3_600_000
            for i in range(len(frames))
        ]
        watch = next(
            w for w in detect_ikigai_box_watches(frames)
            if w.anchor_identity == ("SHORT", 20, 23)
        )
        live = pd.concat([frames, pd.DataFrame([{
            "time": int(frames.iloc[-1]["time"]) + 3_600_000,
            "open": 0.1400, "high": 0.1700,
            "low": 0.1398, "close": 0.1680,
        }])], ignore_index=True)
        with patch.object(box, "send_photo") as photo, patch.object(
            box, "render_ikigai_box_chart",
        ) as render, patch.object(
            box, "get_telegram_chat_ids", return_value=("owner",),
        ):
            self.assertFalse(box.send_ikigai_box_watch_observation(
                "HEIUSDT", live, replace(watch, anchor_end_price=0.150),
                timeframe="60",
            ))
            # Real data now includes an already touched extension, but caller
            # may still carry the earlier frozen WATCH: fail closed.
            touched = pd.concat([live, pd.DataFrame([{
                "time": int(live.iloc[-1]["time"]) + 3_600_000,
                "open": 0.168, "high": 0.170,
                "low": 0.167, "close": 0.169,
            }])], ignore_index=True)
            current_watch = replace(watch, as_of_index=len(touched)-2)
            self.assertFalse(box.send_ikigai_box_watch_observation(
                "HEIUSDT", touched, current_watch, timeframe="60",
            ))
        photo.assert_not_called()
        render.assert_not_called()

    def test_shared_review_buttons_are_owner_only_for_confirmed_and_watch(self):
        from contextlib import ExitStack
        frames, _ = _terminal_wick_two_impulses(second=False)
        frames["time"] = [1_790_000_000_000 + i * 300_000 for i in range(len(frames))]
        watch = next(w for w in detect_ikigai_box_watches(frames)
                     if w.anchor_identity == ("SHORT", 20, 23))
        live = pd.concat([frames, frames.iloc[[-1]]], ignore_index=True)
        for early in (False, True):
            with self.subTest(watch=early), ExitStack() as stack:
                stack.enter_context(patch.object(box, "get_telegram_chat_ids", return_value=("owner", "guest")))
                stack.enter_context(patch.object(box, "get_telegram_owner_chat_id", return_value="owner"))
                stack.enter_context(patch.object(box, "load_memory", return_value={}))
                saved = stack.enter_context(patch.object(box, "save_memory"))
                stack.enter_context(patch.object(box, "render_ikigai_box_chart"))
                text = stack.enter_context(patch.object(box, "send_message", return_value={"ok": True}))
                photo = stack.enter_context(patch.object(box, "send_photo", return_value={"ok": True}))
                robot = stack.enter_context(patch("pattern_robot_integration.create_signal_snapshot"))
                if early:
                    result = box.send_ikigai_box_watch_observation(
                        "TESTUSDT", live, watch, timeframe="5", test_mode=True)
                else:
                    result = box.send_ikigai_box_observation(
                        "TESTUSDT", _candles(), timeframe="5", test_mode=True)
                self.assertTrue(result)
                expected_text = ikigai_box_signal_text(
                    "TESTUSDT", "5",
                    watch if early else detect_ikigai_box(_candles().iloc[:-1]),
                )
                self.assertEqual(text.call_count, 2)
                for index, call in enumerate(photo.call_args_list):
                    self.assertEqual(text.call_args_list[index].args[2], expected_text)
                    self.assertEqual(call.kwargs["caption"], "")
                    buttons = [b for row in call.kwargs["reply_markup"]["inline_keyboard"] for b in row]
                    callbacks = [b["callback_data"] for b in buttons if "callback_data" in b]
                    self.assertEqual(callbacks, [f"review:{action}:TESTUSDT:5" for action in
                                               ("queue", "good", "geometry", "anchor")] if index == 0 else [])
                    self.assertTrue(any("url" in b for b in buttons))
                saved.assert_not_called()
                robot.assert_not_called()

    def test_opt_in_off_preserves_old_scanner_behavior(self):
        with patch.dict(os.environ, {"BYBITSCANNER_IKIGAI_BOX_SIGNALS": "0"}), patch.object(
            main, "get_symbols", return_value=["TESTUSDT"],
        ), patch.object(
            main, "analyze_symbol",
            return_value={"symbol": "TESTUSDT", "result": None, "data": _candles()},
        ), patch.object(main, "send_message", return_value=True), patch.object(
            box, "send_ikigai_box_observation",
        ) as sending:
            main.run_scan_pass()
        sending.assert_not_called()

    def test_completed_gate_uses_frozen_take_without_p1_for_both_directions(self):
        for direction in (1, -1):
            with self.subTest(direction=direction):
                frame, _, _ = _two_impulses(direction, second_steps=7)
                formation = detect_ikigai_box(frame)
                self.assertIsNotNone(formation)
                tick = Decimal("0.01")
                prices, take = box.approved_first_grid(
                    direction=formation.direction,
                    frozen_f1=Decimal(str(formation.fibonacci_1_0)),
                    frozen_f1618=Decimal(str(formation.fibonacci_1_618)),
                    tick_size=tick,
                )
                still_valid = frame.copy(deep=True)
                start, end = formation.second_start_index, formation.as_of_index
                self.assertGreater(end, start)

                if formation.direction == "SHORT":
                    for index in range(start, end + 1):
                        still_valid.loc[index, "high"] = float(prices[0] - tick / 2)
                        still_valid.loc[index, "low"] = float(take + tick / 2)
                else:
                    for index in range(start, end + 1):
                        still_valid.loc[index, "low"] = float(prices[0] + tick / 2)
                        still_valid.loc[index, "high"] = float(take - tick / 2)

                self.assertFalse(box._completed_before_delivery(
                    still_valid, formation, tick,
                ))

                completed = still_valid.copy(deep=True)
                if formation.direction == "SHORT":
                    completed.loc[start, "low"] = float(take)
                else:
                    completed.loc[start, "high"] = float(take)
                self.assertTrue(box._completed_before_delivery(
                    completed, formation, tick,
                ))

    def test_completed_box_is_suppressed_before_render_delivery_and_robot_plan(self):
        frame, _, _ = _two_impulses(second_steps=7)
        formation = detect_ikigai_box(frame)
        tick = Decimal("0.01")
        prices, take = box.approved_first_grid(
            direction=formation.direction,
            frozen_f1=Decimal(str(formation.fibonacci_1_0)),
            frozen_f1618=Decimal(str(formation.fibonacci_1_618)),
            tick_size=tick,
        )
        still_valid = frame.copy(deep=True)
        start = formation.second_start_index
        for index in range(start, formation.as_of_index + 1):
            still_valid.loc[index, "high"] = float(prices[0] - tick / 2)
            still_valid.loc[index, "low"] = float(take + tick / 2)
        still_valid["time"] = [
            1_790_000_000_000 + i * 300_000 for i in range(len(still_valid))
        ]
        completed = still_valid.copy(deep=True)
        completed.loc[start + 1, "low"] = float(take)
        later_valid = still_valid.copy(deep=True)
        later_valid["time"] += 24 * 60 * 60 * 1000

        def with_open_candle(closed):
            return pd.concat([closed, pd.DataFrame([{
                "time": int(closed.iloc[-1]["time"]) + 300_000,
                "open": 100, "high": 101, "low": 99, "close": 100,
            }])], ignore_index=True)

        history = {}
        preparer = unittest.mock.Mock(return_value=SOURCE_ID)
        with patch.object(
            box.config, "TELEGRAM_ENABLED", True,
        ), patch.object(
            box, "detect_ikigai_box", return_value=formation,
        ), patch.object(
            box, "load_memory", side_effect=lambda: dict(history),
        ), patch.object(
            box, "save_memory", side_effect=lambda value: history.update(value),
        ) as save, patch.object(
            box, "render_ikigai_box_chart",
        ) as render, patch.object(
            box, "send_message", return_value={"ok": True},
        ) as text, patch.object(
            box, "send_photo", return_value={"ok": True},
        ) as photo, patch.object(
            box, "get_telegram_chat_ids", return_value=("owner",),
        ), patch.object(
            box, "get_telegram_owner_chat_id", return_value="owner",
        ):
            self.assertFalse(box.send_ikigai_box_observation(
                "TESTUSDT", with_open_candle(completed), timeframe="5",
                robot_plan_preparer=preparer, tick_size=tick,
            ))
            render.assert_not_called()
            text.assert_not_called()
            photo.assert_not_called()
            preparer.assert_not_called()
            self.assertEqual(
                history["ikigai_box:TESTUSDT:5:SHORT"]["status"],
                "COMPLETED_BEFORE_DELIVERY",
            )

            self.assertTrue(box.send_ikigai_box_observation(
                "TESTUSDT", with_open_candle(later_valid), timeframe="1",
                robot_plan_preparer=preparer, tick_size=tick,
            ))

        render.assert_called_once()
        text.assert_called_once()
        photo.assert_called_once()
        preparer.assert_called_once()
        self.assertEqual(save.call_count, 2)
        self.assertIn("ikigai_box:TESTUSDT:1:SHORT", history)

    def test_render_failure_never_sends_stale_file(self):
        source = _candles()
        with patch.object(box, "render_ikigai_box_chart",
                          side_effect=RuntimeError("render failed")), patch.object(
            box, "send_photo",
        ) as photo, patch.object(
            box, "get_telegram_chat_ids", return_value=("owner",),
        ), patch.object(box, "load_memory", return_value={}), patch.object(
            box, "save_memory",
        ) as save:
            with self.assertRaisesRegex(RuntimeError, "render failed"):
                box.send_ikigai_box_observation(
                    "TESTUSDT", source, timeframe="5",
                )
        photo.assert_not_called()
        save.assert_not_called()

    def test_failed_text_does_not_send_photo_or_mark_delivery(self):
        with patch.object(box, "render_ikigai_box_chart"), patch.object(
            box, "get_telegram_chat_ids", return_value=("owner",),
        ), patch.object(
            box, "send_message", return_value={"ok": False},
        ) as text, patch.object(
            box, "send_photo",
        ) as photo, patch.object(
            box, "load_memory", return_value={},
        ), patch.object(
            box, "save_memory",
        ) as save:
            self.assertFalse(box.send_ikigai_box_observation(
                "TESTUSDT", _candles(), timeframe="5",
            ))
        text.assert_called_once()
        photo.assert_not_called()
        save.assert_not_called()

    def test_failed_delivery_does_not_mark_candidate_as_delivered(self):
        source = _candles()
        seen = {}
        def fake_render(frame, formation, path, **kwargs):
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"fresh")
            return target

        with tempfile.TemporaryDirectory() as directory, patch.object(
            box, "render_ikigai_box_chart", side_effect=fake_render,
        ), patch.object(box, "get_telegram_chat_ids", return_value=("owner",)), patch.object(
            box, "send_message", return_value={"ok": True},
        ) as text, patch.object(
            box, "send_photo", side_effect=[{"ok": False}, {"ok": True}],
        ) as photo, patch.object(box, "load_memory",
                               side_effect=lambda: dict(seen)), patch.object(
            box, "save_memory", side_effect=lambda row: seen.update(row),
        ):
            for expected in (False, True):
                result = box.send_ikigai_box_observation(
                    "TESTUSDT", source, timeframe="5",
                    chart_dir=directory,
                )
                self.assertEqual(result, expected)
                self.assertEqual(bool(seen), expected)
        self.assertEqual(photo.call_count, 2)
        self.assertEqual(text.call_count, 2)
        self.assertEqual(
            photo.call_args_list[0].args[2],
            photo.call_args_list[1].args[2],
        )


SOURCE_ID = "box-plan-" + "ab12" * 16


def _markup_callbacks(call):
    return [
        (button["text"], button.get("callback_data"))
        for row in call.kwargs["reply_markup"]["inline_keyboard"]
        for button in row
    ]


class IkigaiBoxOwnerRobotAdmissionTests(unittest.TestCase):
    """CONFIRMED Box: frozen BOX_PLAN_ONLY before the keyboard; owner tap admits."""

    def _deliver(self, *, preparer, recipients=("owner", "guest"), test_mode=False):
        from contextlib import ExitStack

        with ExitStack() as stack, tempfile.TemporaryDirectory() as folder:
            stack.enter_context(patch.object(box, "get_telegram_chat_ids", return_value=recipients))
            stack.enter_context(patch.object(box, "get_telegram_owner_chat_id", return_value="owner"))
            stack.enter_context(patch.object(box, "load_memory", return_value={}))
            stack.enter_context(patch.object(box, "save_memory"))
            stack.enter_context(patch.object(box, "render_ikigai_box_chart"))
            stack.enter_context(patch.object(box, "send_message", return_value={"ok": True}))
            photo = stack.enter_context(patch.object(box, "send_photo", return_value={"ok": True}))
            warn = stack.enter_context(patch.object(box, "warn_owner_robot_candidate_failed"))
            result = box.send_ikigai_box_observation(
                "TESTUSDT", _candles(), timeframe="5", test_mode=test_mode,
                chart_dir=folder, robot_plan_preparer=preparer,
            )
            return result, photo, warn

    def test_owner_photo_gets_robot_admission_for_the_frozen_source_plan(self):
        calls = []

        def preparer(symbol, timeframe, formation):
            calls.append((symbol, timeframe, formation))
            return SOURCE_ID

        result, photo, warn = self._deliver(preparer=preparer)
        self.assertTrue(result)
        self.assertEqual(len(calls), 1)
        symbol, timeframe, formation = calls[0]
        closed = _candles().iloc[:-1]
        expected = detect_ikigai_box(closed)
        self.assertEqual((symbol, timeframe), ("TESTUSDT", "5"))
        self.assertEqual(formation, box.box_robot_formation(closed, expected))
        self.assertEqual(formation["direction"], expected.direction)
        owner, guest = photo.call_args_list
        handle = "bp-" + SOURCE_ID.removeprefix("box-plan-")[:40]
        self.assertIn(("🤖 Робот", f"robot:approve:{handle}"), _markup_callbacks(owner))
        self.assertLessEqual(len(f"robot:approve:{handle}".encode("utf-8")), 64)
        self.assertFalse(any(
            (data or "").startswith("robot:") for _text, data in _markup_callbacks(guest)
        ))
        self.assertNotIn("🤖 Статус робота", [text for text, _ in _markup_callbacks(owner)])
        warn.assert_not_called()

    def test_test_mode_never_prepares_or_shows_robot(self):
        preparer = unittest.mock.Mock(return_value=SOURCE_ID)
        result, photo, warn = self._deliver(preparer=preparer, test_mode=True)
        self.assertTrue(result)
        preparer.assert_not_called()
        for call in photo.call_args_list:
            self.assertFalse(any((data or "").startswith("robot:") for _t, data in _markup_callbacks(call)))
        warn.assert_not_called()

    def test_no_owner_recipient_never_prepares(self):
        preparer = unittest.mock.Mock(return_value=SOURCE_ID)
        result, photo, _warn = self._deliver(preparer=preparer, recipients=("guest",))
        self.assertTrue(result)
        preparer.assert_not_called()
        self.assertFalse(any(
            (data or "").startswith("robot:") for _t, data in _markup_callbacks(photo.call_args)
        ))

    def test_preparation_failure_still_delivers_without_false_button_and_warns_owner(self):
        for preparer in (
            unittest.mock.Mock(side_effect=ValueError("1 WV is below the instrument minimum")),
            unittest.mock.Mock(return_value=None),
            unittest.mock.Mock(return_value="box-robot-" + "ab12" * 16),
        ):
            with self.subTest(preparer=preparer), patch.object(
                box, "record_robot_incident",
            ) as incident:
                result, photo, warn = self._deliver(preparer=preparer)
                self.assertTrue(result)
                self.assertEqual(photo.call_count, 2)
                for call in photo.call_args_list:
                    self.assertFalse(any(
                        (data or "").startswith("robot:") for _t, data in _markup_callbacks(call)
                    ))
                warn.assert_called_once_with("owner", "TESTUSDT", "5")
                incident.assert_called_once()
                kwargs = incident.call_args.kwargs
                self.assertEqual(kwargs["incident_type"], "ROBOT_CANDIDATE_FAILURE")
                self.assertEqual(kwargs["stage"], "box_plan_preparation")
                self.assertEqual(kwargs["reason_code"], "BOX_PLAN_PREPARATION_EXCEPTION")
                self.assertEqual(kwargs["symbol"], "TESTUSDT")
                self.assertEqual(kwargs["timeframe"], "5")
                self.assertEqual(kwargs["pattern"], "IKIGAI_BOX")
                self.assertIsInstance(kwargs["error"], Exception)

    def test_preparation_failure_writes_durable_incident_from_missing_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            incident_dir = Path(temp) / "missing" / "robot_incidents"
            with patch.object(
                diagnostics, "_default_incident_dir", return_value=incident_dir,
            ):
                delivered, photo, warn = self._deliver(
                    preparer=unittest.mock.Mock(
                        side_effect=ValueError("secret at C:/private/box-plan.json"),
                    ),
                )
            self.assertTrue(delivered)
            self.assertEqual(photo.call_count, 2)
            warn.assert_called_once_with("owner", "TESTUSDT", "5")
            record, = diagnostics.load_recent_robot_incidents(incident_dir=incident_dir)
            self.assertEqual(record["incident_type"], "ROBOT_CANDIDATE_FAILURE")
            self.assertEqual(record["stage"], "box_plan_preparation")
            self.assertEqual(record["reason_code"], "BOX_PLAN_PREPARATION_EXCEPTION")
            self.assertEqual(record["symbol"], "TESTUSDT")
            self.assertEqual(record["timeframe"], "5")
            self.assertEqual(record["pattern"], "IKIGAI_BOX")
            self.assertEqual(record["error_class"], "ValueError")
            self.assertNotIn("private", next(incident_dir.glob("*.json")).read_text(encoding="utf-8"))

    def test_diagnostic_storage_failure_keeps_box_delivery_and_reports_safe_cause(self):
        with tempfile.TemporaryDirectory() as temp:
            occupied = Path(temp) / "occupied"
            occupied.write_text("x", encoding="utf-8")
            incident_dir = occupied / "robot_incidents"
            with patch.object(
                diagnostics, "_default_incident_dir", return_value=incident_dir,
            ), contextlib.redirect_stdout(io.StringIO()) as output:
                delivered, photo, warn = self._deliver(
                    preparer=unittest.mock.Mock(
                        side_effect=ValueError("secret at C:/private/box-plan.json"),
                    ),
                )
            self.assertTrue(delivered)
            self.assertEqual(photo.call_count, 2)
            warn.assert_called_once_with("owner", "TESTUSDT", "5")
            self.assertFalse(incident_dir.exists())
            self.assertIn("stage=directory_create", output.getvalue())
            self.assertIn("error_class=FileExistsError", output.getvalue())
            self.assertNotIn("private", output.getvalue())
            self.assertNotIn(str(incident_dir), output.getvalue())

    def test_scanner_pass_prepares_only_through_the_owner_card_and_never_admits(self):
        source = _candles()
        history = {}
        preparer = unittest.mock.Mock(return_value=SOURCE_ID)
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"BYBITSCANNER_IKIGAI_BOX_SIGNALS": "1"}
        ), patch.object(main, "get_symbols", return_value=["TESTUSDT"]), patch.object(
            main, "analyze_symbol",
            side_effect=lambda symbol, *, timeframe: {
                "symbol": symbol, "result": None, "data": source if timeframe == "5" else None,
            },
        ), patch.object(main, "send_message", return_value=True), patch.object(
            box, "render_ikigai_box_chart",
        ), patch.object(box, "send_message", return_value={"ok": True}), patch.object(
            box, "send_photo", return_value={"ok": True},
        ) as photo, patch.object(
            box, "load_memory", side_effect=lambda: dict(history),
        ), patch.object(
            box, "save_memory", side_effect=lambda record: history.update(record),
        ), patch.object(box, "get_telegram_chat_ids", return_value=("owner",)), patch.object(
            box, "get_telegram_owner_chat_id", return_value="owner",
        ), patch(
            "terminal.persistence.sqlite_store.SQLiteStore.handoff_box_plan_to_robot",
            side_effect=AssertionError("Scanner must never admit a Box"),
        ) as handoff:
            main.run_scan_pass(box_plan_preparer=preparer)
            main.run_scan_pass(box_plan_preparer=preparer)
        preparer.assert_called_once()
        handoff.assert_not_called()
        photo.assert_called_once()
        self.assertIn(
            ("🤖 Робот", "robot:approve:bp-" + SOURCE_ID.removeprefix("box-plan-")[:40]),
            _markup_callbacks(photo.call_args),
        )


if __name__ == "__main__":
    unittest.main()

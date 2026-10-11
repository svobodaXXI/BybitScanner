"""SwordCounter S3: settings, rounding, persistence, status display, background refresh.

Offline: no network, no API keys. The GUI smoke test is skipped where Tk has no display.
"""

import json
import os
import re
import tempfile
import threading
import time
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from tools.SwordCounter import app as app_module
from tools.SwordCounter import connection, setup_keys
from tools.SwordCounter.connection import ConnectionController
from tools.SwordCounter.setup_keys import CheckResult
from tools.SwordCounter import settings_store as store
from tools.SwordCounter import view_model as vm
from tools.SwordCounter.settings_store import AppSettings, parse_ro_usdt, parse_total_swords
from tools.SwordCounter.swords import (
    STATUS_NO_CONNECTION, STATUS_OK, STATUS_UNAVAILABLE, SwordCount,
)

REPO = Path(__file__).resolve().parents[1]


def result(status=STATUS_OK, used=3, free=17, total=20, size="5", over=False):
    numbers = status == STATUS_OK
    return SwordCount(status=status, total_swords=total, sword_size_usdt=Decimal(size),
                      positions_count=2 if numbers else None,
                      occupied_margin_usdt=Decimal("12") if numbers else None,
                      used_swords=used if numbers else None, free_swords=free if numbers else None,
                      over_limit=over if numbers else None,
                      reason="" if numbers else "BybitTransportError: Bybit request failed: Timeout")


class SettingsParsingTests(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual((AppSettings().total_swords, AppSettings().ro_usdt), (20, 5))

    def test_total_swords_is_a_positive_integer(self):
        for text, value in (("20", 20), (" 7 ", 7), ("1", 1)):
            self.assertEqual(parse_total_swords(text), value)
        for text in ("0", "-1", "20.5", "2e1", "abc", "", " ", "1_000"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_total_swords(text)

    def test_ro_cost_rounds_half_up_to_a_positive_integer(self):
        for text, value in (("5", 5), ("4.5", 5), ("5.49", 5), ("5.5", 6), ("2.5", 3), ("0.5", 1),
                            (" 10 ", 10), ("7,5", 8)):
            with self.subTest(text=text):
                self.assertEqual(parse_ro_usdt(text), value)
        for text in ("0.4", "0", "-1", "-0.5", "abc", "", "NaN", "Infinity"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_ro_usdt(text)

    def test_app_settings_validate_types(self):
        for kwargs in ({"total_swords": 0}, {"total_swords": True}, {"total_swords": 2.0},
                       {"ro_usdt": 0}, {"ro_usdt": 5.5}, {"ro_usdt": True}, {"ro_usdt": "5"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                AppSettings(**kwargs)

    def test_settings_feed_the_s2_count_as_decimal(self):
        sword = store.to_sword_settings(AppSettings(total_swords=12, ro_usdt=7))
        self.assertEqual((sword.total_swords, sword.sword_size_usdt), (12, Decimal("7")))


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "SwordCounter" / "settings.json"

    def test_roundtrip_and_only_the_two_settings_are_written(self):
        store.save_settings(AppSettings(total_swords=15, ro_usdt=8), self.path)
        loaded, warning = store.load_settings(self.path)
        self.assertEqual((loaded, warning), (AppSettings(total_swords=15, ro_usdt=8), None))
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(set(data), {"version", "total_swords", "ro_usdt"})
        self.assertNotRegex(self.path.read_text(encoding="utf-8").lower(), r"key|secret|token")

    def test_missing_file_gives_defaults_without_warning(self):
        self.assertEqual(store.load_settings(self.path), (AppSettings(), None))

    def test_corrupt_or_invalid_file_gives_defaults_with_a_warning_and_is_kept(self):
        self.path.parent.mkdir(parents=True)
        for content in ("{not json", json.dumps({"version": 1, "total_swords": 0, "ro_usdt": 5}),
                        json.dumps([1, 2]), json.dumps({"version": 1, "total_swords": "x", "ro_usdt": 5})):
            with self.subTest(content=content):
                self.path.write_text(content, encoding="utf-8")
                loaded, warning = store.load_settings(self.path)
                self.assertEqual(loaded, AppSettings())
                self.assertTrue(warning)
                self.assertEqual(self.path.read_text(encoding="utf-8"), content)

    def test_default_location_is_the_windows_user_profile_outside_git(self):
        with mock.patch.dict(os.environ, {"APPDATA": self.tmp.name}):
            path = store.default_settings_path()
        self.assertEqual(path, Path(self.tmp.name) / "SwordCounter" / "settings.json")
        with self.assertRaises(ValueError):
            store.save_settings(AppSettings(), REPO / "tools" / "SwordCounter" / "settings.json")
        self.assertFalse((REPO / "tools" / "SwordCounter" / "settings.json").exists())

    def test_settings_store_never_handles_api_keys(self):
        source = Path(store.__file__).read_text(encoding="utf-8")
        self.assertNotIn("SWORDCOUNTER_BYBIT_API", source)
        self.assertNotIn("Credentials", source)


class DisplayTests(unittest.TestCase):
    S = AppSettings()

    def test_header_shows_the_ro_cost_as_an_integer(self):
        self.assertEqual(vm.header_text(AppSettings(ro_usdt=5)), "1 РО = 5 USDT")
        self.assertEqual(vm.header_text(AppSettings(ro_usdt=6)), "1 РО = 6 USDT")

    def test_ok_shows_green_free_and_red_used(self):
        d = vm.build_display(self.S, result(used=3, free=17), age_s=1)
        self.assertEqual((d.free_text, d.used_text, d.numbers_shown), ("17", "3", True))
        self.assertEqual((d.free_color, d.used_color), (vm.GREEN, vm.RED))

    def test_over_limit_shows_the_real_used_count(self):
        d = vm.build_display(self.S, result(used=25, free=0, over=True), age_s=1)
        self.assertEqual((d.free_text, d.used_text), ("0", "25"))
        self.assertIn("25", d.status_text)

    def test_unavailable_and_no_connection_replace_the_numbers(self):
        for status, text in ((STATUS_UNAVAILABLE, "Недоступно"), (STATUS_NO_CONNECTION, "Нет соединения")):
            with self.subTest(status=status):
                d = vm.build_display(self.S, result(status=status), age_s=1)
                self.assertEqual((d.free_text, d.used_text, d.numbers_shown), (text, text, False))
                self.assertNotIn(d.free_color, (vm.GREEN, vm.RED))

    def test_old_or_mismatched_results_are_not_shown_as_current(self):
        stale = vm.build_display(self.S, result(), age_s=vm.STALE_AFTER_S + 1)
        self.assertFalse(stale.numbers_shown)
        other_settings = vm.build_display(AppSettings(total_swords=10), result(total=20), age_s=1)
        self.assertFalse(other_settings.numbers_shown)
        loading = vm.build_display(self.S, None, age_s=None)
        self.assertFalse(loading.numbers_shown)
        failed = vm.build_display(self.S, vm.WORKER_FAILED, age_s=1)
        self.assertFalse(failed.numbers_shown)
        self.assertGreater(vm.STALE_AFTER_S, app_module.REFRESH_INTERVAL_S)


class RefresherTests(unittest.TestCase):
    def test_refreshes_immediately_off_the_gui_thread_then_every_interval(self):
        self.assertEqual(app_module.REFRESH_INTERVAL_S, 10)
        seen, done = [], threading.Event()

        def count():
            seen.append(threading.get_ident())
            if len(seen) >= 2:
                done.set()
            return result()

        posted = []
        refresher = app_module.Refresher(count, posted.append, interval_s=0.05)
        refresher.start()
        try:
            self.assertTrue(done.wait(2))
        finally:
            refresher.stop()
        self.assertNotIn(threading.get_ident(), seen)
        self.assertGreaterEqual(len(posted), 2)
        self.assertFalse(refresher.is_alive())

    def test_request_now_wakes_the_worker_before_the_interval(self):
        calls, second = [], threading.Event()

        def count():
            calls.append(time.monotonic())
            if len(calls) == 2:
                second.set()
            return result()

        refresher = app_module.Refresher(count, lambda _r: None, interval_s=60)
        refresher.start()
        try:
            time.sleep(0.1)
            refresher.request_now()
            self.assertTrue(second.wait(2))
        finally:
            refresher.stop()

    def test_an_unexpected_worker_failure_is_reported_not_hidden(self):
        posted, got = [], threading.Event()

        def boom():
            raise KeyError("bug")

        refresher = app_module.Refresher(boom, lambda r: (posted.append(r), got.set()), interval_s=60)
        refresher.start()
        try:
            self.assertTrue(got.wait(2))
        finally:
            refresher.stop()
        self.assertIs(posted[0], vm.WORKER_FAILED)

    def test_the_live_counter_uses_s1_and_s2_and_reports_missing_keys_as_no_connection(self):
        from tools.SwordCounter.bybit_positions import BybitCredentialsError

        # Never consult the real Credential Manager from a test.
        with mock.patch.object(app_module, "resolve_credentials",
                               side_effect=BybitCredentialsError("Ключ SwordCounter не настроен")):
            counted = app_module.make_live_counter(lambda: AppSettings())()
        self.assertEqual(counted.status, STATUS_NO_CONNECTION)
        self.assertIsNone(counted.used_swords)

    def test_no_trading_runtime_and_no_order_calls(self):
        for module in (app_module, vm, store):
            source = Path(module.__file__).read_text(encoding="utf-8")
            with self.subTest(module=module.__name__):
                self.assertNotRegex(source, r"(?m)^\s*(from|import)\s+(terminal|robot_|paper_|sqlite3|config)\b")
                for forbidden in ("/v5/order", ".post(", "place_order", "create_order"):
                    self.assertNotIn(forbidden, source)


class GuiSmokeTests(unittest.TestCase):
    def test_window_builds_shows_values_and_is_always_on_top(self):
        try:
            import tkinter
            root = tkinter.Tk()
        except Exception as error:  # no display (e.g. CI)
            self.skipTest(f"Tk unavailable: {type(error).__name__}")
        root.withdraw()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            gui = app_module.SwordCounterApp(root, settings_path=path,
                                             counter_factory=lambda get: (lambda: result(used=4, free=16)),
                                             interval_s=60, start_worker=False)
            try:
                self.assertEqual(root.title(), "SwordCounter")
                self.assertTrue(bool(root.attributes("-topmost")))
                self.assertEqual(root.resizable(), (False, False))
                self.assertEqual(gui.header_label.cget("text"), "1 РО = 5 USDT")
                gui.apply_result(result(used=4, free=16))
                gui.render()
                self.assertEqual((gui.free_value.cget("text"), gui.used_value.cget("text")), ("16", "4"))
                self.assertEqual(gui.free_value.cget("fg").lower(), vm.GREEN.lower())
                gui.apply_result(result(status=STATUS_NO_CONNECTION))
                gui.render()
                self.assertEqual(gui.free_value.cget("text"), "Нет соединения")
                gui.save_settings_from_text("12", "7.5")
                self.assertEqual(gui.header_label.cget("text"), "1 РО = 8 USDT")
                self.assertEqual(store.load_settings(path)[0], AppSettings(total_swords=12, ro_usdt=8))
                with self.assertRaises(ValueError):
                    gui.save_settings_from_text("0", "5")
            finally:
                gui.close()

    def test_connection_section_visible_key_secret_toggle_and_save_only_after_check(self):
        try:
            import tkinter
            root = tkinter.Tk()
        except Exception as error:  # no display (e.g. CI)
            self.skipTest(f"Tk unavailable: {type(error).__name__}")
        root.withdraw()
        fake_store = FakeCredentialStore()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            store.save_settings(AppSettings(total_swords=12, ro_usdt=8), path)
            gui = app_module.SwordCounterApp(root, settings_path=path, credential_store=fake_store,
                                             counter_factory=lambda get: (lambda: result()),
                                             interval_s=60, start_worker=False)
            try:
                gui.open_settings()
                w = gui._connection_widgets
                w["controller"]._verify = lambda c: CheckResult(True, "Bybit подтвердил: ключ Read-Only")
                self.assertEqual(w["key"].cget("show"), "")
                self.assertEqual(w["secret"].cget("show"), app_module.SECRET_MASK)
                w["show"].invoke()
                self.assertEqual(w["secret"].cget("show"), "")
                w["show"].invoke()
                self.assertEqual(w["secret"].cget("show"), app_module.SECRET_MASK)
                handler = app_module.bind_clipboard_keys(w["key"])
                with mock.patch.object(w["key"], "event_generate") as generate:   # Russian layout
                    self.assertEqual(handler(mock.Mock(keycode=86, keysym="Cyrillic_em")), "break")
                generate.assert_called_once_with("<<Paste>>")   # Ctrl+V by physical key, pasted once
                w["key"].insert(0, FAKE_KEY)
                w["secret"].insert(0, FAKE_SECRET)
                self.assertEqual(w["save"].cget("state"), "disabled")
                w["check"].invoke()
                deadline = time.monotonic() + 5
                while w["controller"].checking and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.02)
                root.update()
                self.assertEqual(w["save"].cget("state"), "normal")
                with mock.patch.object(gui.refresher, "request_now") as refresh:
                    w["save"].invoke()
                refresh.assert_called_once()
                self.assertEqual(fake_store.saves, [(FAKE_KEY, FAKE_SECRET)])
                self.assertNotIn(FAKE_SECRET, w["result"].cget("text"))
                self.assertEqual(store.load_settings(path)[0], AppSettings(total_swords=12, ro_usdt=8))
                self.assertNotIn(FAKE_SECRET, path.read_text(encoding="utf-8"))
            finally:
                gui.close()


FAKE_KEY = "GUIKEY0123456789"
FAKE_SECRET = "GUISECRET0123456789abcdef"


class FakeCredentialStore:
    def __init__(self):
        self.saves = []

    def save(self, credentials):
        self.saves.append((credentials.api_key, credentials.api_secret))

    def load(self):
        return None

    def delete(self):
        return False


class ConnectionControllerTests(unittest.TestCase):
    def make(self, ok=True, verify=None):
        fake_store, seen, jobs = FakeCredentialStore(), [], []

        def default_verify(credentials):
            seen.append((credentials.api_key, credentials.api_secret))
            return CheckResult(ok, "проверено")
        controller = ConnectionController(fake_store, verify=verify or default_verify, run_async=jobs.append)
        return controller, fake_store, seen, jobs

    def test_save_only_the_exact_values_that_passed_the_check(self):
        controller, fake_store, seen, jobs = self.make()
        self.assertFalse(controller.save(FAKE_KEY, FAKE_SECRET).ok)          # never checked
        self.assertEqual(controller.start_check(f" {FAKE_KEY}\n", FAKE_SECRET), connection.CHECKING)
        self.assertIsNone(controller.poll())                               # still running
        jobs.pop()()
        self.assertTrue(controller.poll().ok)
        self.assertEqual(seen, [(FAKE_KEY, FAKE_SECRET)])
        self.assertFalse(controller.save(FAKE_KEY, FAKE_SECRET + "x").ok)   # other values
        self.assertTrue(controller.save(FAKE_KEY, FAKE_SECRET).ok)
        self.assertEqual(fake_store.saves, [(FAKE_KEY, FAKE_SECRET)])

    def test_any_edit_drops_the_confirmation_even_back_to_the_same_value(self):
        controller, fake_store, _seen, jobs = self.make()
        controller.start_check(FAKE_KEY, FAKE_SECRET)
        jobs.pop()()
        controller.poll()
        controller.fields_changed()
        self.assertFalse(controller.save(FAKE_KEY, FAKE_SECRET).ok)
        self.assertEqual(fake_store.saves, [])

    def test_a_check_finished_after_an_edit_is_discarded(self):
        controller, fake_store, _seen, jobs = self.make()
        controller.start_check(FAKE_KEY, FAKE_SECRET)
        controller.fields_changed()
        jobs.pop()()
        self.assertFalse(controller.poll().ok)
        self.assertFalse(controller.confirmed)

    def test_refusal_empty_fields_and_crash_save_nothing_and_leak_nothing(self):
        controller, fake_store, seen, jobs = self.make(ok=False)
        self.assertEqual(controller.start_check("", FAKE_SECRET), "Введите API Key.")
        self.assertEqual(controller.start_check(FAKE_KEY, "  "), "Введите API Secret.")
        self.assertEqual((seen, jobs), ([], []))
        controller.start_check(FAKE_KEY, FAKE_SECRET)
        jobs.pop()()
        self.assertFalse(controller.poll().ok)
        self.assertFalse(controller.save(FAKE_KEY, FAKE_SECRET).ok)

        def crash(_credentials):
            raise RuntimeError(f"boom {FAKE_SECRET}")
        controller, fake_store, _seen, jobs = self.make(verify=crash)
        controller.start_check(FAKE_KEY, FAKE_SECRET)
        jobs.pop()()
        outcome = controller.poll()
        self.assertFalse(outcome.ok)
        self.assertNotIn(FAKE_SECRET, outcome.message)
        self.assertEqual(fake_store.saves, [])

    def test_real_check_uses_only_the_two_read_only_endpoints(self):
        self.assertIs(ConnectionController(FakeCredentialStore())._verify, setup_keys.verify_key)
        source = Path(connection.__file__).read_text(encoding="utf-8")
        for forbidden in ("print(", "logging", "os.environ", "settings_store", "/v5/order", ".post("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

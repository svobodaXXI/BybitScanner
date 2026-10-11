"""SwordCounter S5: safe Read-Only key setup (Windows Credential Manager), verification, wizard.

Offline: every Bybit call is faked, no real key exists anywhere in these tests. The
Credential Manager test uses a unique throw-away target and removes it afterwards; the
real SwordCounter entry is never touched.
"""

import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

import requests

from tools.SwordCounter import bybit_positions as bp
from tools.SwordCounter import credential_store as cs
from tools.SwordCounter import setup_keys as sk
from tools.SwordCounter.bybit_positions import (
    BybitApiError, BybitCredentialsError, BybitResponseError, BybitTransportError, Credentials,
)

REPO = Path(__file__).resolve().parents[1]
KEY = "ABCDEFGH12345678"
SECRET = "SECRETSECRETSECRET1234567890abcdef"
NOW_MS = 1_700_000_000_123


class FakeStore:
    def __init__(self, existing=None):
        self.value = existing
        self.saves = []
        self.deleted = 0

    def save(self, credentials):
        self.saves.append(credentials)
        self.value = credentials

    def load(self):
        return self.value

    def delete(self):
        had = self.value is not None
        self.value = None
        self.deleted += 1
        return had


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status_code = status
        self._payload = payload
        self.url = None
        self.history = []

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, headers=None, timeout=None, allow_redirects=True):
        self.calls.append({"url": url, "headers": dict(headers or {})})
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        item.url = url
        return item


def key_info(read_only=1, ips=("203.0.113.5",), **extra):
    result = {"id": "1", "apiKey": KEY, "secret": "", "readOnly": read_only, "ips": list(ips),
              "permissions": {"ContractTrade": ["Order", "Position"]}, "isMaster": True}
    result.update(extra)
    return {"retCode": 0, "retMsg": "", "result": result, "time": NOW_MS}


class ApiKeyInfoTests(unittest.TestCase):
    def fetch(self, *responses):
        session = FakeSession(*responses)
        return bp.fetch_api_key_info(Credentials(KEY, SECRET), session=session, clock_ms=lambda: NOW_MS), session

    def test_signed_get_of_the_documented_read_only_endpoint_without_parameters(self):
        info, session = self.fetch(FakeResponse(key_info()))
        call = session.calls[0]
        self.assertEqual(call["url"], "https://api.bybit.com/v5/user/query-api")
        import hashlib, hmac
        expected = hmac.new(SECRET.encode(), f"{NOW_MS}{KEY}5000".encode(), hashlib.sha256).hexdigest()
        self.assertEqual(call["headers"]["X-BAPI-SIGN"], expected)
        self.assertEqual(call["headers"]["X-BAPI-API-KEY"], KEY)
        self.assertTrue(info.read_only)

    def test_read_only_flag_is_taken_from_readonly_exactly(self):
        self.assertTrue(self.fetch(FakeResponse(key_info(read_only=1)))[0].read_only)
        self.assertFalse(self.fetch(FakeResponse(key_info(read_only=0)))[0].read_only)

    def test_anything_but_integer_zero_or_one_is_an_error_never_a_guess(self):
        for bad in (True, False, "1", None, 2, -1, 1.0, [1]):
            with self.subTest(readOnly=bad), self.assertRaises(BybitResponseError):
                self.fetch(FakeResponse(key_info(read_only=bad)))
        missing = key_info()
        del missing["result"]["readOnly"]
        with self.assertRaises(BybitResponseError):
            self.fetch(FakeResponse(missing))

    def test_ip_restriction_is_reported_without_exposing_addresses(self):
        self.assertTrue(self.fetch(FakeResponse(key_info(ips=("203.0.113.5",))))[0].ip_restricted)
        self.assertFalse(self.fetch(FakeResponse(key_info(ips=())))[0].ip_restricted)
        self.assertFalse(self.fetch(FakeResponse(key_info(ips=("*",))))[0].ip_restricted)
        info = self.fetch(FakeResponse(key_info()))[0]
        self.assertNotIn(KEY, repr(info))
        self.assertNotIn("203.0.113.5", repr(info))

    def test_errors_are_explicit(self):
        bad = {"retCode": 10003, "retMsg": "API key is invalid.", "result": {}}
        with self.assertRaises(BybitApiError):
            self.fetch(FakeResponse(bad))
        with self.assertRaises(BybitTransportError):
            self.fetch(requests.Timeout("slow"))
        with self.assertRaises(BybitResponseError):
            self.fetch(FakeResponse({"retCode": 0, "retMsg": "", "result": []}))

    def test_only_two_read_only_get_paths_can_ever_be_signed(self):
        self.assertEqual(bp.ALLOWED_READ_PATHS, frozenset({"/v5/position/list", "/v5/user/query-api"}))
        session = FakeSession()
        with mock.patch.object(bp.hmac, "new", side_effect=AssertionError("signed")):
            with self.assertRaises(ValueError):
                bp._signed_get(session, Credentials(KEY, SECRET), "https://api.bybit.com", {}, 5000, 10,
                               lambda: NOW_MS, path="/v5/order/create")
        self.assertEqual(session.calls, [])

    def test_the_host_allowlist_still_applies(self):
        with self.assertRaises(ValueError):
            bp.fetch_api_key_info(Credentials(KEY, SECRET), base_url="https://evil.example",
                                  session=FakeSession(), clock_ms=lambda: NOW_MS)


@unittest.skipUnless(sys.platform == "win32", "Windows Credential Manager")
class CredentialManagerTests(unittest.TestCase):
    def setUp(self):
        self.target = f"SwordCounter.Test.{uuid.uuid4().hex}"
        self.store = cs.WindowsCredentialStore(self.target)
        self.addCleanup(self.store.delete)

    def test_roundtrip_missing_and_delete(self):
        self.assertIsNone(self.store.load())
        self.assertFalse(self.store.delete())
        self.store.save(Credentials(KEY, SECRET))
        loaded = self.store.load()
        self.assertEqual((loaded.api_key, loaded.api_secret), (KEY, SECRET))
        self.store.save(Credentials(KEY.lower(), SECRET.lower()))  # replace in place
        self.assertEqual(self.store.load().api_key, KEY.lower())
        self.assertTrue(self.store.delete())
        self.assertIsNone(self.store.load())

    def test_nothing_is_written_to_files_while_saving(self):
        with tempfile.TemporaryDirectory() as tmp:
            before_cwd = set(os.listdir(tmp))
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                self.store.save(Credentials(KEY, SECRET))
            finally:
                os.chdir(cwd)
            self.assertEqual(set(os.listdir(tmp)), before_cwd)
        tracked = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"], capture_output=True,
                                 text=True).stdout
        self.assertNotIn(SECRET, tracked)

    def test_a_damaged_entry_is_an_explicit_error_without_its_content(self):
        self.store._write_blob(b"not json at all " + SECRET.encode())
        with self.assertRaises(BybitCredentialsError) as raised:
            self.store.load()
        self.assertNotIn(SECRET, str(raised.exception) + repr(raised.exception))
        self.store._write_blob(json.dumps({"v": 99}).encode())
        with self.assertRaises(BybitCredentialsError):
            self.store.load()

    def test_entries_are_generic_per_user_and_locally_persisted(self):
        self.assertEqual((cs.CRED_TYPE_GENERIC, cs.CRED_PERSIST_LOCAL_MACHINE), (1, 2))
        self.assertEqual(cs.DEFAULT_TARGET, "SwordCounter/BybitReadOnly")


class StoreSourceTests(unittest.TestCase):
    def test_the_store_never_uses_files_the_robot_config_or_robot_variables(self):
        source = Path(cs.__file__).read_text(encoding="utf-8")
        for forbidden in ("open(", "write_text", "write_bytes", "json.dump(", "pickle", "shelve", "sqlite3",
                          "config.py", "BYBITSCANNER_", "setx", "winreg"):
            self.assertNotIn(forbidden, source, forbidden)
        self.assertNotRegex(source, r"\.env\b")  # a dotenv file (not os.environ)
        self.assertNotRegex(source, r"(?m)^\s*(from|import)\s+(terminal|robot_|paper_|config)\b")

    def test_non_windows_is_an_explicit_error(self):
        with mock.patch.object(cs.sys, "platform", "linux"):
            with self.assertRaises(BybitCredentialsError):
                cs.WindowsCredentialStore("x").load()


class ResolveCredentialsTests(unittest.TestCase):
    def test_credential_manager_wins_and_reports_only_its_source(self):
        stored = Credentials(KEY, SECRET)
        env = {"SWORDCOUNTER_BYBIT_API_KEY": "ENVKEY", "SWORDCOUNTER_BYBIT_API_SECRET": "ENVSECRET"}
        creds, source = cs.resolve_credentials(FakeStore(stored), env)
        self.assertEqual((creds, source), (stored, "credential_manager"))

    def test_environment_is_only_a_fallback_for_the_swordcounter_variables(self):
        env = {"SWORDCOUNTER_BYBIT_API_KEY": KEY, "SWORDCOUNTER_BYBIT_API_SECRET": SECRET}
        creds, source = cs.resolve_credentials(FakeStore(), env)
        self.assertEqual((creds.api_key, source), (KEY, "environment"))

    def test_robot_or_generic_variables_are_never_read(self):
        env = {"BYBIT_API_KEY": KEY, "BYBIT_API_SECRET": SECRET, "BYBITSCANNER_BYBIT_API_KEY": KEY,
               "API_KEY": KEY, "API_SECRET": SECRET}
        with self.assertRaises(BybitCredentialsError):
            cs.resolve_credentials(FakeStore(), env)

    def test_nothing_configured_gives_a_clear_message_without_values(self):
        with self.assertRaises(BybitCredentialsError) as raised:
            cs.resolve_credentials(FakeStore(), {})
        text = str(raised.exception)
        self.assertIn("setup_sword_counter_keys.bat", text)
        self.assertNotIn(SECRET, text)

    def test_half_configured_environment_is_not_used(self):
        for env in ({"SWORDCOUNTER_BYBIT_API_KEY": KEY}, {"SWORDCOUNTER_BYBIT_API_SECRET": SECRET}):
            with self.assertRaises(BybitCredentialsError):
                cs.resolve_credentials(FakeStore(), env)


class VerifyKeyTests(unittest.TestCase):
    CREDS = Credentials(KEY, SECRET)

    def verify(self, info=None, positions=(), info_error=None, positions_error=None):
        def fetch_info(credentials):
            if info_error:
                raise info_error
            return info

        def fetch_positions(credentials):
            if positions_error:
                raise positions_error
            return positions
        return sk.verify_key(self.CREDS, info_fetch=fetch_info, positions_fetch=fetch_positions)

    def test_a_read_only_key_that_reads_positions_is_accepted(self):
        result = self.verify(bp.ApiKeyInfo(read_only=True, ip_restricted=True, is_master=True), ())
        self.assertTrue(result.ok)

    def test_a_key_with_write_rights_is_refused_even_though_it_works(self):
        result = self.verify(bp.ApiKeyInfo(read_only=False, ip_restricted=True, is_master=True))
        self.assertFalse(result.ok)
        self.assertIn("Read-Only", result.message)

    def test_bybit_errors_refuse_the_key_without_leaking_it(self):
        for error in (BybitApiError("Bybit retCode 10003: API key is invalid.", ret_code=10003),
                      BybitTransportError("Bybit request failed: Timeout"),
                      BybitResponseError("bad reply")):
            with self.subTest(type(error).__name__):
                result = self.verify(info_error=error)
                self.assertFalse(result.ok)
                self.assertNotIn(SECRET, result.message)
                self.assertNotIn(KEY, result.message)

    def test_positions_must_be_readable_too(self):
        info = bp.ApiKeyInfo(read_only=True, ip_restricted=False, is_master=True)
        self.assertFalse(self.verify(info, positions_error=BybitApiError("denied", ret_code=10005)).ok)


class WizardTests(unittest.TestCase):
    def run_wizard(self, *, secrets=(KEY, SECRET), store=None, verify_ok=True, yes=True, verify=None):
        store = store if store is not None else FakeStore()
        asked, out = [], io.StringIO()
        answers = iter(secrets)

        def ask_secret(prompt):
            asked.append(prompt)
            return next(answers)

        calls = []

        def default_verify(credentials):
            calls.append(credentials)
            return sk.CheckResult(verify_ok, "ключ принят" if verify_ok else "ключ отклонён")

        code = sk.run_wizard(ask_secret=ask_secret, ask_yes_no=lambda _q: yes, store=store,
                             verify=verify or default_verify, out=out.write)
        return code, store, out.getvalue(), asked, calls

    def test_happy_path_saves_once_and_never_prints_the_values(self):
        code, store, text, asked, calls = self.run_wizard()
        self.assertEqual(code, 0, text)
        self.assertEqual([(c.api_key, c.api_secret) for c in store.saves], [(KEY, SECRET)])
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(asked), 2)
        self.assertNotIn(SECRET, text + "".join(asked))
        self.assertNotIn(KEY, text + "".join(asked))
        self.assertIn("Read-Only", text)

    def test_a_rejected_key_is_not_saved(self):
        code, store, text, _asked, _calls = self.run_wizard(verify_ok=False)
        self.assertEqual((code, store.saves), (1, []))
        self.assertNotIn(SECRET, text)

    def test_malformed_input_is_rejected_before_any_network_call(self):
        for key, secret in (("short", SECRET), (KEY, "tiny"), (KEY + " x", SECRET), ("", ""), (KEY, SECRET + "\n!")):
            with self.subTest(key=len(key), secret=len(secret)):
                code, store, text, _asked, calls = self.run_wizard(secrets=(key, secret))
                self.assertEqual((code, store.saves, calls), (1, [], []))
                self.assertNotIn(secret or "\0", text)

    def test_input_is_trimmed_but_otherwise_unchanged(self):
        code, store, _text, _a, _c = self.run_wizard(secrets=(f"  {KEY}\n", f"{SECRET}  "))
        self.assertEqual((code, store.saves[0].api_key, store.saves[0].api_secret), (0, KEY, SECRET))

    def test_replacing_an_existing_key_needs_confirmation(self):
        existing = FakeStore(Credentials("OLDKEYOLDKEY1234", "OLDSECRETOLDSECRET1234"))
        code, store, _text, asked, calls = self.run_wizard(store=existing, yes=False)
        self.assertEqual((code, store.saves, calls, asked), (2, [], [], []))
        self.assertEqual(store.value.api_key, "OLDKEYOLDKEY1234")
        code2, store2, *_ = self.run_wizard(store=existing, yes=True)
        self.assertEqual((code2, store2.saves[0].api_key), (0, KEY))

    def test_an_unexpected_failure_never_carries_the_secret(self):
        def broken(_credentials):
            raise requests.exceptions.ProxyError(f"proxy http://u:{SECRET}@p:1 refused")
        out = io.StringIO()
        with self.assertRaises(Exception) as raised:
            sk.run_wizard(ask_secret=lambda _p, it=iter((KEY, SECRET)): next(it), ask_yes_no=lambda _q: True,
                          store=FakeStore(), verify=broken, out=out.write)
        self.assertNotIn(SECRET, out.getvalue())


class EntryPointTests(unittest.TestCase):
    def test_no_option_accepts_a_secret_value(self):
        parser = sk.build_parser()
        flags = {a.dest for a in parser._actions if a.dest != "help"}
        self.assertEqual(flags, {"status", "test", "delete"})
        for action in parser._actions:
            self.assertEqual(action.nargs, 0 if action.option_strings and action.dest != "help" else action.nargs)
        for argv in (["--key", KEY], ["--secret", SECRET], [KEY], ["--api-key=" + KEY]):
            with self.subTest(argv=argv), self.assertRaises(SystemExit):
                parser.parse_args(argv)

    def test_secrets_are_only_requested_in_an_interactive_console(self):
        out = io.StringIO()
        with mock.patch.object(sk.sys, "stdin", io.StringIO(KEY + "\n" + SECRET + "\n")):
            code = sk.main([], store=FakeStore(), out=out.write, verify=lambda c: sk.CheckResult(True, "ok"))
        self.assertEqual(code, 1)
        self.assertNotIn(SECRET, out.getvalue())
        self.assertIn("консол", out.getvalue())

    def test_status_never_prints_values_and_delete_removes_only_the_swordcounter_entry(self):
        out = io.StringIO()
        store = FakeStore(Credentials(KEY, SECRET))
        self.assertEqual(sk.main(["--status"], store=store, out=out.write, environ={}), 0)
        self.assertIn("Credential Manager", out.getvalue())
        self.assertNotIn(KEY, out.getvalue())
        self.assertNotIn(SECRET, out.getvalue())
        self.assertEqual(sk.main(["--delete"], store=store, out=out.write, ask_yes_no=lambda _q: True), 0)
        self.assertIsNone(store.value)

    def test_test_option_rechecks_the_saved_key_and_reports_without_values(self):
        out = io.StringIO()
        store = FakeStore(Credentials(KEY, SECRET))
        seen = []
        verify = lambda c: (seen.append(c), sk.CheckResult(True, "ключ принят"))[1]
        self.assertEqual(sk.main(["--test"], store=store, out=out.write, verify=verify, environ={}), 0)
        self.assertEqual(len(seen), 1)
        self.assertNotIn(SECRET, out.getvalue())
        empty = FakeStore()
        self.assertEqual(sk.main(["--test"], store=empty, out=out.write, verify=verify, environ={}), 1)

    def test_the_wizard_sources_leak_nothing_and_touch_no_trading_code(self):
        for module in (sk, cs):
            source = Path(module.__file__).read_text(encoding="utf-8")
            with self.subTest(module=module.__name__):
                self.assertNotIn("sys.argv", source)
                self.assertNotRegex(source, r"print\([^)]*(secret|key)", )
                for forbidden in ("/v5/order", ".post(", "set-leverage", "terminal.", "robot_"):
                    self.assertNotIn(forbidden, source)
        bat = (REPO / "tools" / "SwordCounter" / "setup_sword_counter_keys.bat").read_text(encoding="utf-8")
        self.assertNotRegex(bat, r"(?i)api[_-]?(key|secret)\s*=|setx|set\s+SWORDCOUNTER")
        self.assertIn("tools.SwordCounter.setup_keys", bat)


class AppIntegrationTests(unittest.TestCase):
    def test_the_live_counter_uses_the_resolver_and_a_missing_key_is_no_connection(self):
        from tools.SwordCounter import app as app_module
        from tools.SwordCounter.settings_store import AppSettings
        from tools.SwordCounter.swords import STATUS_NO_CONNECTION

        with mock.patch.object(app_module, "resolve_credentials",
                               side_effect=BybitCredentialsError("Ключ SwordCounter не настроен")), \
                mock.patch.object(bp.requests, "Session", side_effect=AssertionError("network")):
            counted = app_module.make_live_counter(lambda: AppSettings())()
        self.assertEqual(counted.status, STATUS_NO_CONNECTION)
        self.assertIsNone(counted.used_swords)
        self.assertIn("не настроен", counted.reason)


if __name__ == "__main__":
    unittest.main()

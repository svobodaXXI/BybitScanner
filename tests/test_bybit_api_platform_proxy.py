"""bybit_api routes through the local SOCKS5 proxy on Windows only; Linux connects directly (#632)."""
import importlib
import sys
import types
import unittest
from unittest.mock import patch

# Heavy dependencies must be imported under the real platform before it is faked below.
import pandas  # noqa: F401
import pybit.unified_trading  # noqa: F401


def _load_bybit_api(platform):
    # config.py is machine-local and git-ignored; the module only needs BYBIT_CATEGORY.
    stub = types.ModuleType("config")
    stub.BYBIT_CATEGORY = "linear"
    with patch.dict(sys.modules, {"config": stub}), patch.object(sys, "platform", platform):
        sys.modules.pop("bybit_api", None)
        try:
            return importlib.import_module("bybit_api")
        finally:
            sys.modules.pop("bybit_api", None)


class BybitApiPlatformProxyTests(unittest.TestCase):
    def test_windows_keeps_the_local_socks_proxy_for_requests_and_dns(self):
        module = _load_bybit_api("win32")
        self.assertEqual(module.session.client.proxies.get("http"), "socks5h://127.0.0.1:10808")
        self.assertEqual(module.session.client.proxies.get("https"), "socks5h://127.0.0.1:10808")
        self.assertFalse(module.session.client.trust_env)

    def test_linux_connects_directly_without_a_proxy(self):
        module = _load_bybit_api("linux")
        self.assertEqual(module.session.client.proxies, {})
        self.assertFalse(module.session.client.trust_env)

    def test_default_proxies_by_platform(self):
        module = _load_bybit_api("linux")
        self.assertEqual(module.default_bybit_proxies("linux"), {})
        self.assertEqual(module.default_bybit_proxies("darwin"), {})
        self.assertEqual(set(module.default_bybit_proxies("win32")), {"http", "https"})


if __name__ == "__main__":
    unittest.main()

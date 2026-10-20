import unittest
from unittest.mock import patch, Mock
from workspace_gateway_probe import verify_workspace_gateway

KWARGS = {"client_id": "test-client", "client_secret": "test-secret"}


class GatewayProbeTests(unittest.TestCase):
    @patch("workspace_gateway_probe.requests.get")
    def test_access_denies_anon_and_serves_authenticated(self, get):
        get.side_effect = [Mock(status_code=403), Mock(status_code=200)]
        self.assertTrue(verify_workspace_gateway("https://terminal.example.org", **KWARGS))
        self.assertNotIn("test-secret", get.call_args.args[0])
        self.assertEqual(get.call_args.kwargs["headers"]["CF-Access-Client-Secret"], "test-secret")

    @patch("workspace_gateway_probe.requests.get")
    def test_public_site_is_never_ready(self, get):
        get.return_value = Mock(status_code=200)
        self.assertFalse(verify_workspace_gateway("https://terminal.example.org", **KWARGS))
        get.assert_called_once()

    @patch("workspace_gateway_probe.requests.get")
    def test_access_login_redirect_and_authenticated_site(self, get):
        get.side_effect = [Mock(status_code=302, headers={"Location": "/cdn-cgi/access/login"}), Mock(status_code=200)]
        self.assertTrue(verify_workspace_gateway("https://terminal.example.org", **KWARGS))

    @patch("workspace_gateway_probe.requests.get")
    def test_untrusted_redirect_or_failed_auth_rejected(self, get):
        get.side_effect = [Mock(status_code=302, headers={"Location": "https://other.example.org/login"})]
        self.assertFalse(verify_workspace_gateway("https://terminal.example.org", **KWARGS))
        get.side_effect = [Mock(status_code=403), Mock(status_code=403)]
        self.assertFalse(verify_workspace_gateway("https://terminal.example.org", **KWARGS))

    @patch("workspace_gateway_probe.requests.get")
    def test_missing_token_and_http_rejected_before_network(self, get):
        self.assertFalse(verify_workspace_gateway("http://terminal.example.org", **KWARGS))
        self.assertFalse(verify_workspace_gateway("https://terminal.example.org", client_id="", client_secret="x"))
        get.assert_not_called()


if __name__ == "__main__":
    unittest.main()

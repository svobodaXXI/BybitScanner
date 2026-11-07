import unittest
from unittest.mock import patch, Mock
from workspace_gateway_probe import verify_workspace_gateway

HOST = "https://terminal.example.com/"

class WorkspaceGatewayProbeTests(unittest.TestCase):
    @patch("workspace_gateway_probe.requests.get")
    def test_public_workspace_not_verified(self, get):
        get.return_value = Mock(status_code=200, headers={})
        self.assertFalse(verify_workspace_gateway(HOST, client_id="id", client_secret="secret"))
        get.assert_called_once()

    @patch("workspace_gateway_probe.requests.get")
    def test_access_login_same_host_and_authorized_200(self, get):
        get.side_effect = [
            Mock(status_code=302, headers={"Location": "/cdn-cgi/access/login?redirect_url=%2F"}),
            Mock(status_code=200, headers={}),
        ]
        self.assertTrue(verify_workspace_gateway(HOST, client_id="id", client_secret="secret"))
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args.kwargs["headers"]["CF-Access-Client-Secret"], "secret")

    @patch("workspace_gateway_probe.requests.get")
    def test_offsite_login_redirect_is_rejected(self, get):
        get.return_value = Mock(status_code=302, headers={"Location": "https://attacker.example/cdn-cgi/access/login"})
        self.assertFalse(verify_workspace_gateway(HOST, client_id="id", client_secret="secret"))
        get.assert_called_once()

    @patch("workspace_gateway_probe.requests.get")
    def test_access_denied_even_with_token_is_not_ready(self, get):
        get.side_effect = [Mock(status_code=403, headers={}), Mock(status_code=403, headers={})]
        self.assertFalse(verify_workspace_gateway(HOST, client_id="id", client_secret="secret"))

if __name__ == "__main__":
    unittest.main()

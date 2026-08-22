import json
import unittest
from unittest.mock import patch

from telegram_bot import set_workspace_menu_button


class TelegramWorkspaceMenuTests(unittest.TestCase):
    def test_requires_https(self):
        with self.assertRaises(ValueError):
            set_workspace_menu_button("secret", "123", "http://localhost:5173")

    @patch("telegram_bot.requests.post")
    def test_configures_private_chat_web_app_without_token_in_payload(self, post):
        post.return_value.json.return_value = {"ok": True, "result": True}
        result = set_workspace_menu_button("secret-token", "123", "https://demo.trycloudflare.com")
        self.assertTrue(result["ok"])
        call = post.call_args
        self.assertIn("secret-token", call.args[0])
        self.assertNotIn("secret-token", str(call.kwargs["data"]))
        button = json.loads(call.kwargs["data"]["menu_button"])
        self.assertEqual(button["type"], "web_app")
        self.assertEqual(button["web_app"]["url"], "https://demo.trycloudflare.com")


if __name__ == "__main__":
    unittest.main()

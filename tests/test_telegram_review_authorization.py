import unittest
from unittest.mock import patch

import telegram_review


class TelegramReviewAuthorizationTests(unittest.TestCase):
    def callback(self, user_id):
        return {
            "id": "callback-id",
            "from": {
                "id": user_id,
            },
            "data": "review:good:BTCUSDT:5",
        }

    def test_workspace_callback_owner_only_and_no_trade_commands(self):
        for user_id, expected in (("owner", True), ("other-user", False)):
            callback = self.callback(user_id)
            callback["data"] = "workspace:EDITOR:BTCUSDT:5m"
            with patch.object(telegram_review.config, "TELEGRAM_CHAT_ID", "owner"), \
                 patch.object(telegram_review, "_run_workspace_callback") as open_mock, \
                 patch.object(telegram_review, "_answer_callback") as answer_mock, \
                 patch.object(telegram_review, "_save_review") as review_mock, \
                 patch.object(telegram_review, "_approve_robot_candidate") as robot_mock:
                telegram_review._process_callback(callback)
            self.assertEqual(open_mock.called, expected)
            review_mock.assert_not_called()
            robot_mock.assert_not_called()
            if not expected:
                answer_mock.assert_called_once_with("callback-id", "Недостаточно прав")

    def test_invalid_workspace_callback_does_not_launch(self):
        with patch.object(telegram_review.config, "TELEGRAM_CHAT_ID", "owner"), \
             patch.object(telegram_review, "_run_workspace_callback") as open_mock:
            callback = self.callback("owner")
            callback["data"] = "workspace:EDITOR:BTC;rm:5m"
            telegram_review._process_callback(callback)
        open_mock.assert_not_called()

    def test_owner_review_callback_is_accepted(self):
        with patch.object(
            telegram_review.config,
            "TELEGRAM_CHAT_ID",
            "owner",
        ), patch.object(
            telegram_review,
            "_save_review",
            return_value="review-case",
        ) as save_mock, patch.object(
            telegram_review,
            "_answer_callback",
        ) as answer_mock:
            telegram_review._process_callback(
                self.callback("owner")
            )

        save_mock.assert_called_once()
        answer_mock.assert_called_once_with(
            "callback-id",
            "Сохранено в Review Queue ✅",
        )

    def test_non_owner_review_callback_cannot_change_review_state(self):
        with patch.object(
            telegram_review.config,
            "TELEGRAM_CHAT_ID",
            "owner",
        ), patch.object(
            telegram_review,
            "_save_review",
        ) as save_mock, patch.object(
            telegram_review,
            "_answer_callback",
        ) as answer_mock:
            telegram_review._process_callback(
                self.callback("other-user")
            )

        save_mock.assert_not_called()
        answer_mock.assert_called_once_with(
            "callback-id",
            "Недостаточно прав",
        )


if __name__ == "__main__":
    unittest.main()

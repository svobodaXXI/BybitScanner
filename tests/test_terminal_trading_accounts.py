import unittest
from dataclasses import fields

from terminal.application.trading_accounts import (
    AccountSessionToken,
    TradingAccount,
    TradingAccountEnvironment,
    TradingAccountManager,
    TradingAccountProvider,
    TradingAccountStatus,
    paper_account_manager,
)
from terminal.domain.models import TradingAccountId


def _paper_account() -> TradingAccount:
    return TradingAccount(
        TradingAccountId("paper"),
        "Paper / Virtual",
        TradingAccountProvider.PAPER,
        TradingAccountEnvironment.PAPER,
        TradingAccountStatus.READY,
    )


class TradingAccountManagerTests(unittest.TestCase):
    def test_paper_manager_owns_one_active_account_and_generation_one(self) -> None:
        manager = paper_account_manager()

        self.assertEqual(manager.accounts, (manager.active_account,))
        self.assertEqual(manager.active_account_id, TradingAccountId("paper"))
        self.assertEqual(
            manager.session_token, AccountSessionToken(TradingAccountId("paper"), 1)
        )
        self.assertIs(
            manager.require_active(TradingAccountId("paper")), manager.active_account
        )

    def test_account_descriptor_has_no_active_or_credential_material(self) -> None:
        descriptor_fields = {item.name.lower() for item in fields(TradingAccount)}

        self.assertNotIn("active", descriptor_fields)
        self.assertFalse(any(
            "secret" in name or "credential" in name or "api_key" in name
            for name in descriptor_fields
        ))
        representation = repr(_paper_account()).lower()
        self.assertNotIn("secret", representation)
        self.assertNotIn("credential", representation)
        self.assertNotIn("api_key", representation)

    def test_duplicate_account_id_is_rejected(self) -> None:
        account = _paper_account()

        with self.assertRaisesRegex(ValueError, "duplicate trading account id"):
            TradingAccountManager((account, account), active_account_id=account.id)

    def test_plain_strings_cannot_bypass_account_enums(self) -> None:
        with self.assertRaisesRegex(TypeError, "provider"):
            TradingAccount(
                TradingAccountId("paper"), "Paper", "PAPER",  # type: ignore[arg-type]
                TradingAccountEnvironment.PAPER, TradingAccountStatus.READY,
            )

    def test_unknown_active_account_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "not registered"):
            TradingAccountManager(
                (_paper_account(),), active_account_id=TradingAccountId("unknown")
            )

    def test_generation_must_be_positive(self) -> None:
        for generation in (0, -1):
            with self.subTest(generation=generation):
                with self.assertRaisesRegex(ValueError, "must be positive"):
                    TradingAccountManager(
                        (_paper_account(),),
                        active_account_id=TradingAccountId("paper"),
                        generation=generation,
                    )

    def test_non_active_context_is_rejected(self) -> None:
        manager = paper_account_manager()

        with self.assertRaisesRegex(RuntimeError, "not the active account"):
            manager.require_active(TradingAccountId("other"))


if __name__ == "__main__":
    unittest.main()

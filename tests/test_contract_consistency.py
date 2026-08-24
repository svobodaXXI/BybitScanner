from __future__ import annotations

import unittest
from pathlib import Path

from tools.dev.contract_consistency import FRONTEND_CONTRACT, check_source


SOURCE = FRONTEND_CONTRACT.read_text(encoding="utf-8")


class ContractConsistencyTests(unittest.TestCase):
    def test_current_contract_is_consistent(self) -> None:
        passed, output = check_source(SOURCE)
        self.assertTrue(passed, output)

    def test_unsupported_enum_and_unit_fail_closed(self) -> None:
        changed = SOURCE.replace('["Buy", "Sell"]', '["Buy", "Sell", "Hold"]')
        changed = changed.replace('["working_volume", "usdt"]', '["coin"]')
        passed, output = check_source(changed)
        self.assertFalse(passed)
        self.assertIn("market-sides:Hold", output)
        self.assertIn("volume-units:coin", output)

    def test_missing_backend_field_expectation_fails_closed(self) -> None:
        changed = SOURCE.replace("  engaged_wv: string;", "  engaged_wv: string;\n  magic_balance: string;")
        passed, output = check_source(changed)
        self.assertFalse(passed)
        self.assertIn("paper-state-fields:magic_balance", output)

    def test_unknown_handled_reason_fails_closed(self) -> None:
        changed = SOURCE.replace(
            '["insufficient_sizing_precision"]',
            '["insufficient_sizing_precision", "invented_reason"]',
        )
        passed, output = check_source(changed)
        self.assertFalse(passed)
        self.assertIn("handled-reason-codes:invented_reason", output)

    def test_request_shape_drift_fails_closed(self) -> None:
        changed = SOURCE.replace("  sizing_reference_price: string;", "  reference_price: string;")
        passed, output = check_source(changed)
        self.assertFalse(passed)
        self.assertIn("market-request-fields", output)


if __name__ == "__main__":
    unittest.main()

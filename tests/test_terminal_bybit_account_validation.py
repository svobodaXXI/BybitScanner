import unittest

from terminal.exchange.bybit_account_validation import AccountValidationError, BybitAccountValidator
from terminal.exchange.bybit_v5_adapter import BybitCredentials


class Session:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def get_api_key_information(self):
        if self.error:
            raise self.error
        return self.response


class BybitAccountValidatorTests(unittest.TestCase):
    def test_validator_detects_exactly_one_environment_and_disables_request_logging(self):
        calls = []
        def factory(**kwargs):
            calls.append(kwargs)
            if kwargs["testnet"]:
                return Session({"retCode": 0, "result": {
                    "apiKey": "key", "readOnly": 1,
                    "permissions": {"ContractTrade": []},
                }})
            return Session(error=TimeoutError())
        result = BybitAccountValidator(factory).validate(BybitCredentials("key", "secret"))
        self.assertEqual(result.environment, "TESTNET")
        self.assertTrue(result.read_only)
        self.assertTrue(all(call["timeout"] == 10 and call["log_requests"] is False for call in calls))

    def test_validator_fails_closed_for_invalid_or_ambiguous_credentials(self):
        invalid = lambda **kwargs: Session({"retCode": 10003, "retMsg": "invalid"})
        with self.assertRaisesRegex(AccountValidationError, "bybit_validation_failed"):
            BybitAccountValidator(invalid).validate(BybitCredentials("key", "secret"))
        valid = lambda **kwargs: Session({"retCode": 0, "result": {
            "apiKey": "key", "readOnly": 0,
            "permissions": {"ContractTrade": ["Order", "Position"]},
        }})
        with self.assertRaisesRegex(AccountValidationError, "bybit_validation_failed"):
            BybitAccountValidator(valid).validate(BybitCredentials("key", "secret"))

    def test_validator_requires_both_contract_permissions_for_mainnet_write_access(self):
        def factory(**kwargs):
            if kwargs["testnet"]:
                return Session(error=TimeoutError())
            return Session({"retCode": 0, "result": {
                "apiKey": "key", "readOnly": 0,
                "permissions": {"ContractTrade": ["Order"]},
            }})

        result = BybitAccountValidator(factory).validate(BybitCredentials("key", "secret"))

        self.assertEqual(result.environment, "MAINNET")
        self.assertTrue(result.read_only)

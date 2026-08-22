import unittest
from decimal import Decimal

from terminal.api.models import (
    ClientActionId, CommandResult, CommandResultStatus, EventEnvelope, EventType,
    PROTOCOL_VERSION, to_primitive,
)


class TerminalApiModelTests(unittest.TestCase):
    def test_client_action_id_roundtrip_is_transport_identity_only(self):
        action = ClientActionId("gesture-opaque-123")
        result = CommandResult(
            action.value, CommandResultStatus.ACCEPTED_PENDING, "accepted_pending",
            "pending", "cmd-1",
        )
        encoded = to_primitive(result)
        self.assertEqual(encoded["client_action_id"], action.value)
        self.assertEqual(encoded["command_id"], "cmd-1")
        self.assertNotEqual(encoded["client_action_id"], encoded["command_id"])

    def test_decimal_serialization_is_string_and_missing_fact_is_null(self):
        encoded = to_primitive({"price": Decimal("100.2500"), "missing": None})
        self.assertEqual(encoded, {"price": "100.2500", "missing": None})
        self.assertNotIsInstance(encoded["price"], float)

    def test_event_envelope_keeps_four_sequence_domains_distinct(self):
        event = EventEnvelope(
            PROTOCOL_VERSION, "stream", "snapshot", 7, 3, "order-1", 11, 99,
            EventType.ORDER_UPDATED, {"status": "cancelled"},
        )
        encoded = to_primitive(event)
        self.assertEqual(encoded["event_sequence"], 7)
        self.assertEqual(encoded["reconciliation_generation"], 3)
        self.assertEqual(encoded["entity_version"], 11)
        self.assertEqual(encoded["exchange_sequence"], 99)

    def test_unsupported_objects_and_invalid_action_ids_fail_closed(self):
        with self.assertRaises(ValueError):
            ClientActionId("")
        with self.assertRaises(TypeError):
            to_primitive(object())


if __name__ == "__main__":
    unittest.main()

import sqlite3
import tempfile
import json
import threading
import urllib.request
import unittest
from decimal import Decimal
from http.server import ThreadingHTTPServer
from pathlib import Path

from terminal.api.models import (
    ClientActionId,
    MarketCommandRequest,
    PaperStopDeleteRequest,
    PaperStopMutationRequest,
    VolumeRequest,
    VolumeUnit,
)
from terminal.domain.models import OrderSide
from terminal.persistence.schema import SCHEMA_VERSION
from terminal.persistence.sqlite_store import PersistenceError, SQLiteStore
from terminal.runtime.paper_http_server import SerializedPaperRuntime
from terminal.runtime.paper_http_server import PaperHttpHandler
from tests.test_terminal_paper_runtime import _runtime


def _open(runtime, side: OrderSide, action_id: str) -> None:
    runtime.api.market(MarketCommandRequest(
        ClientActionId(action_id), "BTCUSDT", side,
        VolumeRequest(VolumeUnit.USDT, Decimal("321")), Decimal("64250"),
        "Percent", Decimal("0.5"),
    ))


def _serialized_paper_stop_long_crud_projection_revision_and_quantity():
    with tempfile.TemporaryDirectory() as temp:
        owner = SerializedPaperRuntime(
            lambda: _runtime(Path(temp) / "paper.sqlite3")
        )
        try:
            owner.call(lambda runtime: _open(runtime, OrderSide.BUY, "open-long"))
            initial = owner.call(lambda runtime: runtime.paper_state("BTCUSDT"))
            quantity = initial["position_quantity"]

            request = PaperStopMutationRequest(
                ClientActionId("stop-create-long"), "BTCUSDT", Decimal("64000.24"),
            )
            created, state = owner.call(lambda runtime: (
                runtime.create_stop(request), runtime.paper_state("BTCUSDT"),
            ))
            duplicate = owner.call(lambda runtime: runtime.create_stop(request))

            assert created.reason_code == "created"
            assert duplicate.reason_code == "duplicate_action"
            assert state["protection"]["status"] == "confirmed_active"
            assert state["protection"]["stop_loss"] == "64000.5"
            assert state["protection"]["effective_quantity"] == quantity
            assert state["state_revision"] == initial["state_revision"] + 1

            amended, amended_state = owner.call(lambda runtime: (
                runtime.amend_stop(PaperStopMutationRequest(
                    ClientActionId("stop-amend-long"), "BTCUSDT", Decimal("65000.24"),
                )),
                runtime.paper_state("BTCUSDT"),
            ))
            assert amended.reason_code == "amended"
            assert amended_state["protection"]["stop_loss"] == "65000.5"
            assert amended_state["protection"]["effective_quantity"] == quantity
            assert amended_state["state_revision"] == state["state_revision"] + 1

            delete_request = PaperStopDeleteRequest(
                ClientActionId("stop-delete-long"), "BTCUSDT",
            )
            deleted, deleted_state = owner.call(lambda runtime: (
                runtime.delete_stop(delete_request),
                runtime.paper_state("BTCUSDT"),
            ))
            repeated, repeated_state = owner.call(lambda runtime: (
                runtime.delete_stop(PaperStopDeleteRequest(
                    ClientActionId("stop-delete-repeat"), "BTCUSDT",
                )),
                runtime.paper_state("BTCUSDT"),
            ))
            assert deleted.reason_code == "deleted"
            assert deleted_state["protection"]["stop_loss"] is None
            assert deleted_state["protection"]["effective_quantity"] is None
            assert deleted_state["state_revision"] == amended_state["state_revision"] + 1
            assert repeated.reason_code == "already_absent"
            assert repeated_state["state_revision"] == deleted_state["state_revision"]

            owner.call(lambda runtime: runtime.create_stop(PaperStopMutationRequest(
                ClientActionId("stop-recreate-long"), "BTCUSDT", Decimal("63800"),
            )))
            replayed_delete, replayed_state = owner.call(lambda runtime: (
                runtime.delete_stop(delete_request), runtime.paper_state("BTCUSDT"),
            ))
            assert replayed_delete.reason_code == "duplicate_action"
            assert replayed_state["protection"]["stop_loss"] == "63800"
        finally:
            owner.close()


def _paper_stop_short_direction_and_tick_normalization():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            _open(runtime, OrderSide.SELL, "open-short")
            runtime.create_stop(PaperStopMutationRequest(
                ClientActionId("stop-create-short"), "BTCUSDT", Decimal("64500.24"),
            ))
            runtime.amend_stop(PaperStopMutationRequest(
                ClientActionId("stop-amend-short"), "BTCUSDT", Decimal("63000.24"),
            ))
            state = runtime.paper_state("BTCUSDT")
            assert state["protection"]["stop_loss"] == "63000.0"
            assert state["protection"]["effective_quantity"] == state["position_quantity"]
        finally:
            runtime.close()


def _paper_stop_rejects_flat_and_duplicate_leg(test_case: unittest.TestCase):
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            with test_case.assertRaisesRegex(ValueError, "open position"):
                runtime.create_stop(PaperStopMutationRequest(
                    ClientActionId("stop-flat"), "BTCUSDT", Decimal("64000"),
                ))
            _open(runtime, OrderSide.BUY, "open-for-validation")
            runtime.create_stop(PaperStopMutationRequest(
                ClientActionId("stop-first"), "BTCUSDT", Decimal("65000"),
            ))
            with test_case.assertRaisesRegex(PersistenceError, "already exists"):
                runtime.create_stop(PaperStopMutationRequest(
                    ClientActionId("stop-second"), "BTCUSDT", Decimal("63900"),
                ))
        finally:
            runtime.close()


def _schema_v9_migrates_paper_protection_action_journal():
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "paper.sqlite3"
        store = SQLiteStore.open(path)
        store.close()
        connection = sqlite3.connect(path)
        connection.execute("DROP TABLE paper_protection_actions")
        connection.execute("PRAGMA user_version = 9")
        connection.commit()
        connection.close()

        migrated = SQLiteStore.open(path)
        try:
            assert migrated.settings().schema_version == SCHEMA_VERSION
        finally:
            migrated.close()


def _paper_stop_http_mutations_return_authoritative_resulting_state():
    with tempfile.TemporaryDirectory() as temp:
        owner = SerializedPaperRuntime(
            lambda: _runtime(Path(temp) / "paper.sqlite3")
        )
        owner.call(lambda runtime: _open(runtime, OrderSide.BUY, "http-open-long"))
        server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
        server.runtime = owner
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def post(path: str, payload: dict) -> dict:
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}{path}",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request) as response:
                assert response.status == 200
                return json.load(response)

        try:
            created = post("/api/stop", {
                "client_action_id": "http-stop-create",
                "symbol": "BTCUSDT",
                "trigger_price": "64000.24",
            })
            amended = post("/api/stop/amend", {
                "client_action_id": "http-stop-amend",
                "symbol": "BTCUSDT",
                "trigger_price": "63900.24",
            })
            deleted = post("/api/stop/delete", {
                "client_action_id": "http-stop-delete",
                "symbol": "BTCUSDT",
            })

            assert created["paper_state"]["protection"]["stop_loss"] == "64000.5"
            assert amended["paper_state"]["protection"]["stop_loss"] == "63900.5"
            assert deleted["paper_state"]["protection"]["stop_loss"] is None
            assert (
                created["paper_state"]["state_revision"] + 1
                == amended["paper_state"]["state_revision"]
            )
            assert (
                amended["paper_state"]["state_revision"] + 1
                == deleted["paper_state"]["state_revision"]
            )
        finally:
            server.shutdown()
            server.server_close()
            owner.close()


class PaperStopTests(unittest.TestCase):
    def test_serialized_crud_projection_revision_and_quantity(self):
        _serialized_paper_stop_long_crud_projection_revision_and_quantity()

    def test_short_direction_and_tick_normalization(self):
        _paper_stop_short_direction_and_tick_normalization()

    def test_flat_and_duplicate_leg_are_rejected(self):
        _paper_stop_rejects_flat_and_duplicate_leg(self)

    def test_schema_v9_migration(self):
        _schema_v9_migrates_paper_protection_action_journal()

    def test_http_mutations_return_authoritative_state(self):
        _paper_stop_http_mutations_return_authoritative_resulting_state()

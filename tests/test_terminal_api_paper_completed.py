from types import SimpleNamespace

from terminal.api.models import ClientActionId, CommandResultStatus
from terminal.api.rest import _application_result
from terminal.application.trading_application import ApplicationResult
from terminal.domain.models import CommandId
from terminal.domain.states import CommandState
from terminal.exchange.bybit_v5_mutation_adapter import (
    MutationDisposition,
    MutationKind,
    MutationOutcome,
)


def test_filled_application_result_maps_to_completed():
    command = SimpleNamespace(
        command_id=CommandId("paper-command-1"),
        current_state=CommandState.FILLED,
    )
    outcome = MutationOutcome(
        MutationKind.CREATE,
        MutationDisposition.ACKNOWLEDGED,
        order_id="paper-order-1",
        reason="paper market order executed",
    )

    result = _application_result(
        ClientActionId("gesture-paper-1").value,
        ApplicationResult(None, command, outcome),
    )

    assert result.status is CommandResultStatus.COMPLETED
    assert result.reason_code == "completed"
    assert result.command_id == "paper-command-1"
    assert result.reconciliation_required is False

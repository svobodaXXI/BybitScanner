from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.trades.enums import ExecutionSide
from app.dev_harness.formatting import format_aggregate, format_execution_lab_result
from app.dev_harness.keyboards import execution_lab_keyboard, main_menu_keyboard
from app.dev_harness.state import ExecutionLabState


def test_execution_lab_state_applies_facts_and_ignores_replays() -> None:
    lab = ExecutionLabState()
    first_fact = lab.make_fact(
        ExecutionSide.BUY,
        Price(100),
        Quantity(1),
        Money(1, "USDT"),
        "fill-1",
    )
    execution, aggregate, duplicate = lab.apply_fact(first_fact)

    assert execution.external_execution_id == "fill-1"
    assert not duplicate
    assert aggregate.open_quantity == Quantity(1)

    replay_fact = lab.make_fact(
        ExecutionSide.BUY,
        Price(100),
        Quantity(1),
        Money(1, "USDT"),
        "fill-1",
    )
    _, replayed_aggregate, duplicate = lab.apply_fact(replay_fact)

    assert duplicate
    assert replayed_aggregate is aggregate
    assert aggregate.open_quantity == Quantity(1)
    assert aggregate.total_fees == Money(1, "USDT")


def test_execution_lab_formatting_is_domain_state_only() -> None:
    lab = ExecutionLabState()
    execution, aggregate, _ = lab.apply_fact(
        lab.make_fact(ExecutionSide.BUY, Price(100), Quantity(1), Money(0, "USDT"), "fill-1")
    )
    aggregate = lab.service.apply_fact(
        lab.make_fact(ExecutionSide.BUY, Price(110), Quantity(1), Money(0, "USDT"), "fill-2")
    )

    text = format_execution_lab_result(execution, aggregate)
    assert "EXECUTION APPLIED" in text
    assert "Direction: LONG" in text
    assert "Open Qty: 2" in text
    assert "Avg Entry: 105" in text
    assert "Realized Gross PnL: 0 USDT" in text
    assert "Fees: 0 USDT" in text
    assert "Executions: 2" in text
    assert "TRADE AGGREGATE" in format_aggregate(aggregate)


def test_execution_lab_keyboards_expose_required_actions() -> None:
    main_callbacks = {
        button.callback_data
        for row in main_menu_keyboard(dev_mode=False).inline_keyboard
        for button in row
    }
    lab_callbacks = {
        button.callback_data
        for row in execution_lab_keyboard().inline_keyboard
        for button in row
    }

    assert "execution_lab" not in main_callbacks
    dev_callbacks = {
        button.callback_data
        for row in main_menu_keyboard(dev_mode=True).inline_keyboard
        for button in row
    }
    assert "execution_lab" not in dev_callbacks
    assert "development" in dev_callbacks
    assert {"lab:buy", "lab:sell", "lab:show", "lab:reset"} <= lab_callbacks


def test_execution_lab_reset_clears_aggregation_context() -> None:
    lab = ExecutionLabState()
    lab.apply_fact(lab.make_fact(ExecutionSide.SELL, Price(100), Quantity(1), Money(0, "USDT"), "fill-1"))

    lab.reset()

    assert lab.aggregate() is None

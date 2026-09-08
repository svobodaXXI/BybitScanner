from app.core.common.expense import Expense
from app.core.common.money import Money


def test_positive_expense_is_added_to_net_pnl() -> None:
    gross_pnl = Money("100", "USD")
    fees = Money("10", "USD")
    expense = Expense(Money("25", "USD"))

    net = gross_pnl - fees + expense.amount

    assert net == Money("115", "USD")


def test_negative_expense_is_subtracted_from_net_pnl() -> None:
    gross_pnl = Money("100", "USD")
    fees = Money("10", "USD")
    expense = Expense(Money("-25", "USD"))

    net = gross_pnl - fees + expense.amount

    assert net == Money("65", "USD")


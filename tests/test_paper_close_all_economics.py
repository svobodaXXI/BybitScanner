"""Verified account-wide PAPER Close-All economics, synthetic evidence only."""
from __future__ import annotations
from decimal import Decimal as D
from types import SimpleNamespace as NS
import unittest
from terminal.api.models import to_primitive
from terminal.application.paper_close_all_report import (
    verified_manual_close, verified_robot_close, paper_close_all_market_link,
)
from terminal.domain.models import (
    Category, Execution, ExecutionDedupKey, ExecutionId, OrderId, OrderSide,
    PositionSide, Price, Quantity, Symbol, TradingAccountId,
)
A = TradingAccountId("paper")
S = Symbol("BTCUSDT")
L = paper_close_all_market_link("confirmed", S.value)

def projection(side=PositionSide.LONG, qty="2", avg="10", version=3, ms=100):
    return NS(
        position_key=NS(trading_account_id=A, category=Category.LINEAR, symbol=S, position_idx=0),
        side=side, quantity=Quantity(D(qty)), average_entry=Price(D(avg)) if avg else None,
        version=version, updated_at_ms=ms,
    )

def fill(*, tag="entry", side=OrderSide.BUY, qty="2", price="10", fee="0.02", ms=100):
    link = "paper-" + L if tag == "exit" else tag
    eid = "paper-exec-" + L if tag == "exit" else tag
    return Execution(
        dedup_key=ExecutionDedupKey(A, Category.LINEAR, ExecutionId(eid)),
        order_id=OrderId("paper-order-" + L if tag == "exit" else tag),
        symbol=S, side=side, price=Price(D(price)), quantity=Quantity(D(qty)),
        fee=D(fee), exchange_timestamp_ms=ms,
    )

def proof(before=None, after=None, final=None, history=None, link=L):
    before = before or projection()
    after = after or projection(PositionSide.FLAT, "0", None, 4, 200)
    final = final or fill(tag="exit", side=OrderSide.SELL, price="12", fee="0.03", ms=200)
    history = tuple(history) if history is not None else (fill(), final)
    return verified_manual_close(
        symbol=S.value, before=before, after=after,
        exit_fill=final, fills=history, expected_link=link, account_id=A,
    )

class ManualProof(unittest.TestCase):
    def test_long_exact_gross_entry_and_exit_fee_net(self):
        report=proof()
        self.assertEqual(report.evidence_status,"VERIFIED")
        self.assertEqual(report.gross_pnl_usdt,D("4"))
        self.assertEqual(report.fees_costs_usdt,D("0.05"))
        self.assertEqual(report.net_pnl_usdt,D("3.95"))
        self.assertEqual(to_primitive(report)["net_pnl_usdt"],"3.95")

    def test_short_exact_net(self):
        entry=fill(side=OrderSide.SELL)
        exit=fill(tag="exit",side=OrderSide.BUY,price="8",fee="0.03",ms=200)
        report=proof(before=projection(PositionSide.SHORT),final=exit,history=(entry,exit))
        self.assertEqual(report.net_pnl_usdt,D("3.95"))

    def test_weighted_multiple_entries(self):
        a=fill(tag="one",price="9",qty="1",fee="0.01",ms=90)
        b=fill(tag="two",price="11",qty="1",fee="0.02",ms=100)
        z=fill(tag="exit",side=OrderSide.SELL,price="12",fee="0.03",ms=200)
        report=proof(history=(a,b,z))
        self.assertEqual(report.net_pnl_usdt,D("3.94"))

    def test_prior_closed_lot_is_excluded(self):
        old=fill(tag="old",price="1",qty="1",fee="0.2",ms=10)
        close=fill(tag="old-close",side=OrderSide.SELL,price="2",qty="1",fee="0.1",ms=20)
        result=proof(history=(old,close,fill(),fill(tag="exit",side=OrderSide.SELL,price="12",fee="0.03",ms=200)))
        self.assertEqual(result.fees_costs_usdt,D("0.05"))

    def test_partial_exit_rejects_unproven_fee_allocation(self):
        e=fill(qty="3",fee="0.03",ms=90)
        p=fill(tag="partial",side=OrderSide.SELL,qty="1",ms=95)
        z=fill(tag="exit",side=OrderSide.SELL,price="12",fee="0.03",ms=200)
        result=proof(history=(e,p,z))
        self.assertEqual(result.evidence_status,"UNPROVEN")
        self.assertIsNone(result.net_pnl_usdt)

    def test_missing_entry_or_wrong_market_identity_is_unproven(self):
        z=fill(tag="exit",side=OrderSide.SELL,price="12",fee="0.03",ms=200)
        self.assertEqual(proof(history=(z,)).evidence_status,"UNPROVEN")
        self.assertEqual(proof(link="tw_"+"b"*32+"0").evidence_status,"UNPROVEN")

    def test_wrong_position_version_or_open_exposure_is_unproven(self):
        self.assertEqual(proof(after=projection(PositionSide.FLAT,"0",None,3,200)).evidence_status,"UNPROVEN")
        self.assertEqual(proof(after=projection()).evidence_status,"UNPROVEN")

    def test_wrong_side_or_quantity_is_unproven(self):
        z=fill(tag="exit",side=OrderSide.BUY,price="12",fee="0.03",ms=200)
        self.assertEqual(proof(final=z,history=(fill(),z)).evidence_status,"UNPROVEN")
        z=fill(tag="exit",side=OrderSide.SELL,qty="1",price="12",fee="0.03",ms=200)
        self.assertEqual(proof(final=z,history=(fill(),z)).evidence_status,"UNPROVEN")

    def test_tied_timestamps_are_ambiguous(self):
        e=fill(tag="one",qty="1")
        b=fill(tag="two",qty="1")
        z=fill(tag="exit",side=OrderSide.SELL,price="12",fee="0.03",ms=200)
        self.assertEqual(proof(history=(e,b,z)).evidence_status,"UNPROVEN")

class RobotProof(unittest.TestCase):
    def trade(self,**kw):
        d=dict(symbol=S,exit_time_ms=200,exit_reason="MANUAL",exit_price=D("12"),
               average_entry=D("10"),entry_quantity=D("2"),realized_pnl_usdt=D("4"),
               fees_costs_usdt=D("0.05"))
        d.update(kw)
        return NS(**d)
    def test_confirmed_close(self):
        r=verified_robot_close("BTCUSDT",self.trade(),projection(PositionSide.FLAT,"0",None,4,200))
        self.assertEqual(r.net_pnl_usdt,D("3.95"))
    def test_missing_fees_and_unrelated_exit(self):
        flat=projection(PositionSide.FLAT,"0",None,4,200)
        self.assertEqual(verified_robot_close("BTCUSDT",self.trade(fees_costs_usdt=None),flat).evidence_status,"UNPROVEN")
        self.assertEqual(verified_robot_close("BTCUSDT",self.trade(exit_reason="STOP"),flat).evidence_status,"UNPROVEN")

if __name__ == "__main__":
    unittest.main()

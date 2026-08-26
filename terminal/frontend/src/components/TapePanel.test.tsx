import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { NormalizedOrderBook, TradePrint } from "../contracts/marketData";
import {
  displaySweptRows,
  executionPriceToLadderRow,
} from "../marketData/domProjection";
import { printWidthPx, TapePanel } from "./TapePanel";

const cumulative = (
  id: string,
  side: "BUY" | "SELL",
  notional: number,
  sweptTicks: number,
  rowOffset: number,
): TradePrint => ({
  id,
  side,
  startedAtMs: 1000,
  endedAtMs: 1040,
  tradeCount: 3,
  totalQuantity: 60,
  totalNotionalUsdt: notional,
  firstExecutionPrice: 1.59477,
  lastExecutionPrice: 1.5948,
  sweepLowPrice: 1.59477,
  sweepHighPrice: 1.5948,
  sweptPriceRange: 0.00003,
  sweptTicks,
  tickSize: 0.00001,
  rowOffset,
});

const book: NormalizedOrderBook = {
  symbol: "ONGUSDT",
  asks: Array.from({ length: 8 }, (_, index) => ({
    price: 1.5948 + index * 0.00001,
    quantity: 1,
  })),
  bids: Array.from({ length: 8 }, (_, index) => ({
    price: 1.59479 - index * 0.00001,
    quantity: 1,
  })),
  health: "READY",
  receivedAt: "now",
  availableDepth: 8,
};

describe("Smart Tape cumulative geometry", () => {
  it("renders cumulative queue order with tick height, USDT width, and side colors", () => {
    render(
      <TapePanel
        book={book}
        centerPrice={1.5948}
        trades={[
          cumulative("older-buy", "BUY", 76, 1, -1),
          cumulative("newer-sell", "SELL", 1200, 4, 2),
        ]}
      />,
    );

    const bubbles = document.querySelectorAll<HTMLElement>(
      ".trade-print-bubble",
    );
    expect(bubbles).toHaveLength(2);
    expect(bubbles[0]).toHaveClass("buy");
    expect(bubbles[1]).toHaveClass("sell");
    expect(screen.getByText("76")).toBeInTheDocument();
    expect(screen.getByText("1.2k")).toBeInTheDocument();
    expect(bubbles[0].style.getPropertyValue("--print-height")).toBe("1.36rem");
    expect(bubbles[1].style.getPropertyValue("--print-height")).toBe("2.72rem");
    expect(
      Number.parseFloat(bubbles[1].style.getPropertyValue("--print-width")),
    ).toBeGreaterThan(
      Number.parseFloat(bubbles[0].style.getPropertyValue("--print-width")),
    );
    expect(bubbles[0]).toHaveAttribute("title", "3 trades · 1 ticks");
    expect(bubbles[1]).toHaveAttribute("title", "3 trades · 4 ticks");
  });

  it("compresses native sweep height and strongly bounds USDT width", () => {
    expect(displaySweptRows(1)).toBe(1);
    expect(displaySweptRows(3)).toBe(1);
    expect(displaySweptRows(4)).toBe(2);
    expect(displaySweptRows(6)).toBe(2);
    expect(displaySweptRows(7)).toBe(3);

    expect(printWidthPx(0)).toBe(10.8);
    expect(printWidthPx(100)).toBeGreaterThan(10.8);
    expect(printWidthPx(1_000_000)).toBeLessThanOrEqual(22.8);
    expect(printWidthPx(1_000_000) - printWidthPx(100)).toBeLessThan(10.8);
  });

  it("anchors the bubble to the last execution DOM bucket, not sweep midpoint", () => {
    const trade = cumulative("bucketed-buy", "BUY", 100, 4, 0);
    trade.lastExecutionPrice = 1.59478;
    trade.sweepLowPrice = 1.5947;
    trade.sweepHighPrice = 1.5949;
    render(<TapePanel book={book} centerPrice={1.5948} trades={[trade]} />);

    const bubble = document.querySelector<HTMLElement>(".trade-print-bubble");
    const expectedRow = executionPriceToLadderRow(
      trade.lastExecutionPrice,
      trade.side,
      trade.tickSize,
      1.5948,
    );
    expect(bubble?.style.getPropertyValue("--print-y")).toBe(
      `${(expectedRow ?? 0) * 1.36}rem`,
    );
  });
});

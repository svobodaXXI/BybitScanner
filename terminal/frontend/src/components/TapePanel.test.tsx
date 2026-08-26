import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { NormalizedOrderBook, TradePrint } from "../contracts/marketData";
import {
  displaySweptRows,
  executionPriceToLadderRow,
} from "../marketData/domProjection";
import {
  formatPositionPnlPercent,
  positionPnlPercent,
  printWidthPx,
  TapePanel,
} from "./TapePanel";

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
  firstTradeSeq: 1,
  lastTradeSeq: 3,
  backendFirstReceivedAtMs: 1010,
  backendLastReceivedAtMs: 1050,
  finalizedAtMs: 1100,
  browserReceivedAtMs: 1110,
  bookCorrelation: null,
  correlatedBookExchangeSkewMs: null,
  correlatedBookCtsSkewMs: null,
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
  it.each([
    ["Long", 100, 101, 1, "+1.00%"],
    ["Long", 100, 99, -1, "−1.00%"],
    ["Short", 100, 99, 1, "+1.00%"],
    ["Short", 100, 101, -1, "−1.00%"],
  ] as const)("renders %s live PnL without moving the position indicator", (
    side, average, current, expected, label,
  ) => {
    render(
      <TapePanel book={book} centerPrice={1.5948} trades={[]}
        positionSide={side} averageEntryPrice={average} currentPrice={current}
        compression={3} />,
    );
    expect(positionPnlPercent(side, average, current)).toBeCloseTo(expected);
    expect(screen.getByText(label)).toBeInTheDocument();
    expect(document.querySelector(".prints-position-indicator")).toBeInTheDocument();
  });

  it("omits the full indicator for Flat", () => {
    render(<TapePanel book={book} centerPrice={null} trades={[]}
      positionSide="Flat" averageEntryPrice={100} currentPrice={101} compression={3} />);
    expect(document.querySelector(".prints-position-indicator")).not.toBeInTheDocument();
  });

  it("keeps the arrow but omits invalid or unavailable PnL", () => {
    const { rerender } = render(<TapePanel book={book} centerPrice={null} trades={[]}
      positionSide="Long" averageEntryPrice={null} currentPrice={101} compression={3} />);
    expect(screen.getByText("↑")).toBeInTheDocument();
    expect(document.querySelector(".position-pnl")).not.toBeInTheDocument();
    rerender(<TapePanel book={book} centerPrice={null} trades={[]}
      positionSide="Long" averageEntryPrice={0} currentPrice={Infinity} compression={3} />);
    expect(document.body).not.toHaveTextContent(/NaN|Infinity/);
  });

  it("renders zero PnL with a neutral tone", () => {
    render(<TapePanel book={book} centerPrice={null} trades={[]}
      positionSide="Short" averageEntryPrice={100} currentPrice={100} compression={3} />);
    const pnl = screen.getByText("0.00%");
    expect(pnl).toHaveClass("neutral");
    expect(formatPositionPnlPercent(0)).toBe("0.00%");
  });

  it("renders cumulative queue order with tick height, USDT width, and side colors", () => {
    render(
      <TapePanel
        book={book}
        centerPrice={1.5948}
        trades={[
          cumulative("older-buy", "BUY", 76, 1, -1),
          cumulative("newer-sell", "SELL", 1200, 4, 2),
        ]}
        positionSide="Flat" compression={3}
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
    render(<TapePanel book={book} centerPrice={1.5948} trades={[trade]} positionSide="Flat" compression={3} />);

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

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { NormalizedOrderBook, TradePrint } from "../contracts/marketData";
import {
  displaySweptRows,
  projectSweepCenterRow,
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
    expect(bubbles[1].style.getPropertyValue("--print-height")).toBe("1.36rem");
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
    expect(displaySweptRows(5)).toBe(1);
    expect(displaySweptRows(6)).toBe(2);
    expect(displaySweptRows(10)).toBe(2);
    expect(displaySweptRows(11)).toBe(3);

    expect(printWidthPx(0)).toBe(18);
    expect(printWidthPx(100)).toBeGreaterThan(18);
    expect(printWidthPx(1_000_000)).toBeLessThanOrEqual(38);
    expect(printWidthPx(1_000_000) - printWidthPx(100)).toBeLessThan(18);
  });

  it("projects the frozen sweep center onto the same visible DOM row ordering", () => {
    expect(projectSweepCenterRow(book, 1.59478, 1.5948, 0.00001)).toBeCloseTo(
      0.7,
    );
  });
});

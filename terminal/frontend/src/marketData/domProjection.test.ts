import { describe, expect, it } from "vitest";
import type { NormalizedOrderBook } from "../contracts/marketData";
import {
  DOM_COMPRESSION,
  executionPriceToLadderRow,
  priceToLadderRow,
  projectDomBook,
  projectSweepCenterRow,
} from "./domProjection";

const sparseBook = (bestAsk = 0.0925): NormalizedOrderBook => ({
  symbol: "ONGUSDT",
  asks: [
    { price: bestAsk, quantity: 10 },
    { price: bestAsk + 0.00001, quantity: 2 },
  ],
  bids: [
    { price: 0.0923, quantity: 20 },
    { price: 0.09229, quantity: 3 },
  ],
  health: "READY",
  receivedAt: "now",
  availableDepth: 2,
});

describe("continuous DOM x5 price ladder", () => {
  it("keeps empty spread rows and continuous fixed price labels", () => {
    const projection = projectDomBook(sparseBook(), 0.0924);
    const spread = projection.levels.filter(
      (level) => level.price <= 0.0925 && level.price >= 0.0923,
    );

    expect(DOM_COMPRESSION).toBe(5);
    expect(projection.displayStep).toBeCloseTo(0.00005, 8);
    expect(spread.map((level) => level.price)).toEqual([
      0.0925, 0.09245, 0.0924, 0.09235, 0.0923,
    ]);
    expect(spread.map((level) => level.side)).toEqual([
      "SELL",
      null,
      null,
      null,
      "BUY",
    ]);
    expect(spread.map((level) => level.quantity)).toEqual([10, 0, 0, 0, 20]);
    expect(
      projection.levels
        .slice(1)
        .every(
          (level, index) =>
            Number(
              (projection.levels[index].price - level.price).toFixed(8),
            ) === 0.00005,
        ),
    ).toBe(true);
  });

  it("does not delete rows when liquidity disappears or a new best moves away", () => {
    const centerPrice = 0.0924;
    const before = projectDomBook(sparseBook(0.0925), centerPrice);
    const after = projectDomBook(sparseBook(0.0926), centerPrice);

    expect(after.levels.map((level) => level.price)).toEqual(
      before.levels.map((level) => level.price),
    );
    expect(after.levels.find((level) => level.price === 0.0925)?.quantity).toBe(
      0,
    );
    expect(after.levels.find((level) => level.price === 0.0926)).toMatchObject({
      side: "SELL",
      quantity: 10,
      isBest: true,
    });
  });

  it("aggregates all native quantities in an x5 side bucket", () => {
    const book: NormalizedOrderBook = {
      ...sparseBook(),
      asks: Array.from({ length: 5 }, (_, index) => ({
        price: 0.09251 + index * 0.00001,
        quantity: index + 1,
      })),
    };
    const projection = projectDomBook(book, 0.0924);
    expect(
      projection.levels.find((level) => level.price === 0.09255)?.quantity,
    ).toBe(15);
  });

  it("projects Tape prices onto the exact same ladder rows", () => {
    const book = sparseBook();
    const centerPrice = 0.0924;
    expect(priceToLadderRow(0.0925, centerPrice, 0.00001)).toBeCloseTo(6);
    expect(priceToLadderRow(0.0923, centerPrice, 0.00001)).toBeCloseTo(10);
    expect(
      projectSweepCenterRow(book, 0.0923, 0.0925, 0.00001, centerPrice),
    ).toBeCloseTo(0.5);
  });

  it.each([
    ["BUY", 0.09233, 0.0923],
    ["SELL", 0.09247, 0.0925],
    ["BUY", 0.09235, 0.09235],
    ["SELL", 0.09235, 0.09235],
  ] as const)(
    "projects %s execution %s through DOM bucket %s",
    (side, executionPrice, displayPrice) => {
      const centerPrice = 0.0924;
      const tapeRow = executionPriceToLadderRow(
        executionPrice,
        side,
        0.00001,
        centerPrice,
      );
      const domRow =
        priceToLadderRow(displayPrice, centerPrice, 0.00001) - (16 - 1) / 2;
      expect(tapeRow).toBeCloseTo(domRow, 10);
      expect(Number.isInteger((tapeRow ?? 0) + 0.5)).toBe(true);
    },
  );

  it("moves Tape and DOM rows together when ladder center changes", () => {
    const before = executionPriceToLadderRow(0.09233, "BUY", 0.00001, 0.0924);
    const after = executionPriceToLadderRow(0.09233, "BUY", 0.00001, 0.09245);
    expect(after).toBe((before ?? 0) + 1);
  });
});

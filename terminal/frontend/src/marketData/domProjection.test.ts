import { describe, expect, it } from "vitest";
import type { NormalizedOrderBook } from "../contracts/marketData";
import {
  DOM_COMPRESSION,
  domViewportGeometry,
  dragDeltaToCenterStep,
  executionPriceToLadderRow,
  priceToLadderRow,
  projectDomBook,
  projectPriceToDisplayBucket,
  projectSweepCenterRow,
  visibleDomRowsForHeight,
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

describe("continuous DOM x3 price ladder", () => {
  it("fills the viewport exactly with an effective row height near canonical", () => {
    const geometry = domViewportGeometry(500, 21.76);
    expect(geometry.visibleRows).toBe(23);
    expect(geometry.rowHeightPx).toBeCloseTo(21.7391304348, 10);
    expect(geometry.visibleRows * geometry.rowHeightPx).toBeCloseTo(
      geometry.viewportHeightPx,
      10,
    );
  });

  it("derives and projects a responsive row count beyond the historical 16", () => {
    expect(visibleDomRowsForHeight(544, 21.76)).toBe(25);
    const projection = projectDomBook(sparseBook(), 0.0924, 3, 25);
    expect(projection.levels).toHaveLength(25);
    expect(projection.levels[0].price).toBeCloseTo(0.09276, 8);
    expect(projection.levels.at(-1)?.price).toBeCloseTo(0.09204, 8);
    expect(projection.levels[12].price).toBeCloseTo(0.0924, 8);
  });

  it("safely clamps measured row counts", () => {
    expect(visibleDomRowsForHeight(10, 20)).toBe(2);
    expect(visibleDomRowsForHeight(10_000, 20)).toBe(200);
  });

  it("keeps empty spread rows and continuous fixed price labels", () => {
    const projection = projectDomBook(sparseBook(), 0.0924);
    const spread = projection.levels.filter(
      (level) => level.price <= 0.09252 && level.price >= 0.09228,
    );

    expect(DOM_COMPRESSION).toBe(3);
    expect(projection.displayStep).toBeCloseTo(0.00003, 8);
    expect(spread.map((level) => level.price)).toEqual([
      0.09252,
      0.09249,
      0.09246,
      0.09243,
      0.0924,
      0.09237,
      0.09234,
      0.09231,
      0.09228,
    ]);
    expect(spread.map((level) => level.side)).toEqual([
      "SELL",
      null,
      null,
      null,
      null,
      null,
      null,
      null,
      "BUY",
    ]);
    expect(spread.map((level) => level.quantity)).toEqual([
      12, 0, 0, 0, 0, 0, 0, 0, 23,
    ]);
    expect(
      projection.levels
        .slice(1)
        .every(
          (level, index) =>
            Number(
              (projection.levels[index].price - level.price).toFixed(8),
            ) === 0.00003,
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
    expect(after.levels.find((level) => level.price === 0.09252)?.quantity).toBe(
      0,
    );
    expect(after.levels.find((level) => level.price === 0.09261)).toMatchObject({
      side: "SELL",
      quantity: 12,
      isBest: true,
    });
  });

  it("aggregates all native quantities in an x3 side bucket", () => {
    const book: NormalizedOrderBook = {
      ...sparseBook(),
      asks: Array.from({ length: 3 }, (_, index) => ({
        price: 0.0925 + index * 0.00001,
        quantity: index + 1,
      })),
    };
    const projection = projectDomBook(book, 0.0924);
    expect(
      projection.levels.find((level) => level.price === 0.09252)?.quantity,
    ).toBe(6);
  });

  it("projects Tape prices onto the exact same ladder rows", () => {
    const book = sparseBook();
    const centerPrice = 0.0924;
    const askBucket = projectPriceToDisplayBucket(
      0.0925,
      "SELL",
      0.00001,
    );
    const bidBucket = projectPriceToDisplayBucket(0.0923, "BUY", 0.00001);
    expect(askBucket).toBe(0.09252);
    expect(bidBucket).toBe(0.09228);
    expect(priceToLadderRow(askBucket, centerPrice, 0.00001)).toBeCloseTo(4);
    expect(priceToLadderRow(bidBucket, centerPrice, 0.00001)).toBeCloseTo(12);
    expect(
      projectSweepCenterRow(book, 0.0923, 0.0925, 0.00001, centerPrice),
    ).toBeCloseTo(0.5);
  });

  it.each([
    ["BUY", 0.09233, 0.09231],
    ["SELL", 0.09247, 0.09249],
    ["BUY", 0.09234, 0.09234],
    ["SELL", 0.09234, 0.09234],
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
    const after = executionPriceToLadderRow(0.09233, "BUY", 0.00001, 0.09243);
    expect(after).toBe((before ?? 0) + 1);
  });

  it("keeps Tape and DOM price-to-Y geometry identical for non-16 row counts", () => {
    const visibleRows = 25;
    const projection = projectDomBook(sparseBook(), 0.0924, 3, visibleRows);
    const displayPrice = projectPriceToDisplayBucket(0.09233, "BUY", 0.00001);
    const domRow = projection.levels.findIndex((level) => level.price === displayPrice);
    const tapeOffset = executionPriceToLadderRow(
      0.09233,
      "BUY",
      0.00001,
      0.0924,
      3,
      visibleRows,
    );
    expect(tapeOffset).toBeCloseTo(domRow - (visibleRows - 1) / 2, 10);
  });

  it("moves the ladder in the same direction as the pointer drag", () => {
    expect(dragDeltaToCenterStep(12)).toBe(1);
    expect(dragDeltaToCenterStep(-12)).toBe(-1);

    const centerPrice = 0.0924;
    const displayStep = 0.00003;
    const spreadPrice = 0.0924;
    const before = priceToLadderRow(spreadPrice, centerPrice, 0.00001);
    const afterDown = priceToLadderRow(
      spreadPrice,
      centerPrice + dragDeltaToCenterStep(12) * displayStep,
      0.00001,
    );
    const afterUp = priceToLadderRow(
      spreadPrice,
      centerPrice + dragDeltaToCenterStep(-12) * displayStep,
      0.00001,
    );
    expect(afterDown).toBeCloseTo(before + 1);
    expect(afterUp).toBeCloseTo(before - 1);
  });
});

it("fills consecutive lower bid buckets when native depth is sufficient", () => {
  const tickSize = 0.00001;
  const bestBid = 0.09230;
  const bestAsk = 0.09231;

  const book: NormalizedOrderBook = {
    symbol: "ONGUSDT",
    asks: Array.from({ length: 100 }, (_, index) => ({
      price: bestAsk + index * tickSize,
      quantity: 1,
    })),
    bids: Array.from({ length: 100 }, (_, index) => ({
      price: bestBid - index * tickSize,
      quantity: 1,
    })),
    health: "READY",
    receivedAt: "now",
    availableDepth: 100,
  };

  const projection = projectDomBook(book);

  const firstBidRow = projection.levels.findIndex(
    (level) => level.price <= projectPriceToDisplayBucket(
      bestBid,
      "BUY",
      tickSize,
    ),
  );
  const lowerBidRows = projection.levels.slice(firstBidRow);

  expect(firstBidRow).toBeGreaterThanOrEqual(0);
  expect(lowerBidRows.length).toBeGreaterThan(0);
  expect(lowerBidRows.every((level) => level.quantity > 0)).toBe(true);
});

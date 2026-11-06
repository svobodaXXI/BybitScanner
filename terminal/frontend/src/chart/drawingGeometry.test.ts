import { describe, expect, it } from "vitest";
import { nearestOhlcAnchor, rayEndPoint } from "./drawingGeometry";

describe("OHLC magnet for Editor anchors", () => {
  const candles = [
    { open: 100, high: 110, low: 90, close: 102 },
    { open: 103, high: 120, low: 97, close: 102 },
    { open: 111, high: 112, low: 105, close: 107 },
  ];
  const x = (logical: number) => logical * 30;
  const y = (price: number) => 300 - price * 2;

  it("snaps a finger near the first upper wick to exact original OHLC and candle", () => {
    // Finger center 17px below the wick is outside the old 14px radius.
    expect(nearestOhlcAnchor({ logical: 1.08, price: 111.5 }, candles, x, y, 26))
      .toEqual({ logical: 1, price: 120 });
  });

  it("respects real horizontal distance instead of the rounded candle index", () => {
    const nearNext = { logical: 1.8, price: 120 };
    // The second bar is horizontally > 14px away, despite its matching high.
    expect(nearestOhlcAnchor(nearNext, candles, x, y, 14)).toEqual(nearNext);
  });

  it("keeps freehand position unchanged outside the touch radius", () => {
    const away = { logical: 0.2, price: 150 };
    expect(nearestOhlcAnchor(away, candles, x, y, 26)).toEqual(away);
  });
});

describe("ray geometry", () => {
  it("starts at the origin and extends only forward through direction", () => {
    expect(
      rayEndPoint({ x: 20, y: 30 }, { x: 40, y: 40 }, { width: 100, height: 100 }),
    ).toEqual({ x: 100, y: 70 });
    expect(
      rayEndPoint({ x: 80, y: 60 }, { x: 60, y: 50 }, { width: 100, height: 100 }),
    ).toEqual({ x: 0, y: 20 });
  });
});

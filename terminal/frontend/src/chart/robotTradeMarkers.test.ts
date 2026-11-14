import { describe, expect, it } from "vitest";
import {
  TELEGRAM_BUY_COLOR, TELEGRAM_SELL_COLOR, visibleRobotTradeMarkers,
} from "./robotTradeMarkers";

const candles = [0, 300000, 600000].map((delta) => ({
  time: new Date(1800000000000 + delta).toISOString(),
  open: 1, high: 2, low: 0.5, close: 1.5,
}));

describe("Telegram Robot execution marker parity", () => {
  it("uses exact execution prices and candle times, with Buy up / Sell down and unfilled LIMIT", () => {
    const t = 1800000000000;
    const found = visibleRobotTradeMarkers([
      { time_ms: t + 42, price: "1.234", side: "Buy", filled: true },
      { time_ms: t + 300001, price: "1.222", side: "Sell", filled: true },
      { time_ms: t + 600001, price: "1.5", side: "Buy", filled: false },
    ], candles, "5m");
    expect(found).toEqual([
      { logical: 0, price: 1.234, side: "Buy", filled: true },
      { logical: 1, price: 1.222, side: "Sell", filled: true },
      { logical: 2, price: 1.5, side: "Buy", filled: false },
    ]);
    expect(TELEGRAM_BUY_COLOR).toBe("#00a152");
    expect(TELEGRAM_SELL_COLOR).toBe("#d50000");
  });

  it("never moves executions outside real candles or substitutes OHLC prices", () => {
    const t = 1800000000000;
    expect(visibleRobotTradeMarkers([
      { time_ms: t - 1, price: "2", side: "Buy", filled: true },
      { time_ms: t + 900000, price: "2", side: "Sell", filled: true },
      { time_ms: t + 1, price: "-1", side: "Buy", filled: true },
      { time_ms: t + 1, price: "1.45", side: "Buy", filled: true },
    ], candles, "5m")).toEqual([{ logical: 0, price: 1.45, side: "Buy", filled: true }]);
    expect(visibleRobotTradeMarkers([
      { time_ms: t + 1, price: "1", side: "Buy", filled: true },
    ], candles.slice().reverse(), "5m")).toEqual([]);
    expect(visibleRobotTradeMarkers([], candles, "5m")).toEqual([]);
  });
});

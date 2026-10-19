import { describe, expect, it } from "vitest";

import {
  entryBasisFor,
  mskDayStartMs,
  summarizeDay,
} from "./autopilotFirstScreenData";

// 2026-10-19 12:00:00 UTC == 15:00 MSK; the MSK business day began at 2026-10-18 21:00 UTC.
const NOW = Date.UTC(2026, 9, 19, 12, 0, 0);
const DAY_START = Date.UTC(2026, 9, 18, 21, 0, 0);

const trade = (
  overrides: Partial<Parameters<typeof summarizeDay>[0][number]>,
) => ({
  symbol: "LSKUSDT",
  closed_at_ms: null,
  pnl: null,
  readiness: "OPEN",
  ...overrides,
});

describe("AUTOPILOT first-screen data", () => {
  it("uses the 00:00 MSK business-day boundary of the daily-loss gate", () => {
    expect(mskDayStartMs(NOW)).toBe(DAY_START);
    expect(mskDayStartMs(DAY_START)).toBe(DAY_START);
    expect(mskDayStartMs(DAY_START - 1)).toBe(DAY_START - 24 * 60 * 60 * 1000);
  });

  it("sums only trades closed during the current MSK day", () => {
    const summary = summarizeDay(
      [
        trade({
          closed_at_ms: DAY_START + 1,
          pnl: "1.5",
          readiness: "CLOSED_READY",
        }),
        trade({
          closed_at_ms: DAY_START + 2,
          pnl: "-0.5",
          readiness: "CLOSED_READY",
        }),
        trade({
          closed_at_ms: DAY_START - 1,
          pnl: "100",
          readiness: "CLOSED_READY",
        }),
        trade({}),
      ],
      NOW,
    );

    expect(summary).toMatchObject({
      closedTrades: 2,
      netPnl: 1,
      tradesWithoutPnl: 0,
    });
  });

  it("never reports a day PnL when any closed trade has no PnL", () => {
    const summary = summarizeDay(
      [
        trade({
          closed_at_ms: DAY_START + 1,
          pnl: "1.5",
          readiness: "CLOSED_READY",
        }),
        trade({
          closed_at_ms: DAY_START + 2,
          pnl: null,
          readiness: "CLOSED_INCOMPLETE",
        }),
      ],
      NOW,
    );

    expect(summary).toMatchObject({
      closedTrades: 2,
      netPnl: null,
      tradesWithoutPnl: 1,
    });
  });

  it("takes the entry basis only from the open Diary episode of that symbol", () => {
    const trades = [
      trade({
        symbol: "LSKUSDT",
        closed_at_ms: 1,
        details: { decision: { decision_reason: "old" } },
      }),
      trade({
        symbol: "LSKUSDT",
        details: { decision: { decision_reason: "Falling Wedge retest" } },
      }),
      trade({
        symbol: "NIGHTUSDT",
        details: { decision: { decision_reason: null } },
      }),
    ];

    expect(entryBasisFor("LSKUSDT", trades)).toBe("Falling Wedge retest");
    expect(entryBasisFor("NIGHTUSDT", trades)).toBeNull();
    expect(entryBasisFor("BTCUSDT", trades)).toBeNull();
  });
});

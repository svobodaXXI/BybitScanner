import { describe, expect, it } from "vitest";
import { currentCandleCloseCountdown as remaining } from "./candleCloseCountdown";

describe("live last-candle close countdown", () => {
  const epoch = (iso: string) => Date.parse(iso);

  it("updates the displayed remaining time every second for a 5m candle", () => {
    const open = "2026-11-06T20:00:00Z";
    expect(remaining(open, "5m", epoch("2026-11-06T20:00:33Z"))).toBe("04:27");
    expect(remaining(open, "5m", epoch("2026-11-06T20:00:34Z"))).toBe("04:26");
    expect(remaining(open, "5m", epoch("2026-11-06T20:04:59Z"))).toBe("00:01");
    expect(remaining(open, "5m", epoch("2026-11-06T20:05:00Z"))).toBeNull();
  });

  it("uses each allowed terminal timeframe, independent of device timezone", () => {
    const open = "2026-11-06T20:00:00Z";
    expect(remaining(open, "15s", epoch("2026-11-06T20:00:02Z"))).toBe("00:13");
    expect(remaining(open, "1m", epoch("2026-11-06T20:00:02Z"))).toBe("00:58");
    expect(remaining(open, "15m", epoch("2026-11-06T20:00:02Z"))).toBe("14:58");
    expect(remaining(open, "1h", epoch("2026-11-06T20:00:02Z"))).toBe("59:58");
    expect(remaining("2026-11-06T00:00:00Z", "1d", epoch("2026-11-06T20:00:02Z"))).toBe("03:59:58");
  });

  it("does not claim a countdown for missing, stale, future, or invalid bars", () => {
    const now = epoch("2026-11-06T20:30:00Z");
    expect(remaining(null, "5m", now)).toBeNull();
    expect(remaining("invalid", "5m", now)).toBeNull();
    expect(remaining("2026-11-06T20:00:00Z", "5m", now)).toBeNull();
    expect(remaining("2026-11-06T20:31:00Z", "5m", now)).toBeNull();
    expect(remaining("2026-11-06T20:30:00Z", "unknown", now)).toBeNull();
    expect(remaining("2026-11-06T20:30:00Z", "5m", Number.NaN)).toBeNull();
  });

  it("uses the actual candle start, not an independent local wall-clock bucket", () => {
    expect(remaining("2026-11-06T20:01:00Z", "5m", epoch("2026-11-06T20:02:00Z"))).toBe("04:00");
  });
});

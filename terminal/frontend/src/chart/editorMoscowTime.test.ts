import { TickMarkType, type UTCTimestamp } from "lightweight-charts";
import { describe, expect, it } from "vitest";
import { editorMoscowCrosshairTime, editorMoscowTickMark } from "./editorMoscowTime";

describe("Editor chart Moscow time presentation", () => {
  it("renders UTC+3 on axis ticks and crosshair, including the next calendar day", () => {
    const utc = (Date.parse("2026-11-06T21:30:00Z") / 1000) as UTCTimestamp;
    expect(editorMoscowTickMark(utc, TickMarkType.Time)).toBe("00:30");
    expect(editorMoscowTickMark(utc, TickMarkType.TimeWithSeconds)).toBe("00:30:00");
    expect(editorMoscowTickMark(utc, TickMarkType.DayOfMonth)).toBe("07");
    expect(editorMoscowTickMark(utc, TickMarkType.Year)).toBe("2026");
    const crosshair = editorMoscowCrosshairTime(utc);
    expect(crosshair).toContain("07.11.2026");
    expect(crosshair).toContain("00:30");
    expect(crosshair).toContain("МСК");
    // Formatting must not modify the underlying candle instant.
    expect(utc).toBe(Date.parse("2026-11-06T21:30:00Z") / 1000);
  });

  it("is independent of the viewer device's local timezone", () => {
    const utc = (Date.parse("2026-11-06T15:30:00Z") / 1000) as UTCTimestamp;
    expect(editorMoscowTickMark(utc, TickMarkType.Time)).toBe("18:30");
  });

  it("does not pretend a non-UTC-timestamp is Moscow chart data", () => {
    expect(editorMoscowTickMark({ year: 2026, month: 11, day: 6 }, TickMarkType.Time)).toBeNull();
  });
});

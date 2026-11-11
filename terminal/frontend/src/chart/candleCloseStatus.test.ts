import { describe, expect, it } from "vitest";
import { candleCloseStatus } from "./candleCloseStatus";
import { editorMoscowCrosshairTime } from "./editorMoscowTime";

describe("Shared chart UTC/Moscow display and countdown", () => {
  it("formats the original UTC instant as Moscow time without shifting candle timestamps", () => {
    const utc = Date.parse("2026-11-11T09:35:00Z");
    expect(editorMoscowCrosshairTime(utc / 1000 as never)).toContain("12:35");
    expect(utc).toBe(Date.parse("2026-11-11T09:35:00Z"));
  });

  it("counts to the next 5m close and resets at the boundary", () => {
    const start = "2026-11-11T09:35:00Z";
    expect(candleCloseStatus(start, "5m", Date.parse("2026-11-11T09:38:00Z")))
      .toEqual({ status: "LIVE", label: "02:00" });
    expect(candleCloseStatus(start, "5m", Date.parse("2026-11-11T09:39:59Z")))
      .toEqual({ status: "LIVE", label: "00:01" });
    expect(candleCloseStatus("2026-11-11T09:40:00Z", "5m", Date.parse("2026-11-11T09:40:00Z")))
      .toEqual({ status: "LIVE", label: "05:00" });
  });

  it("does not present a stale market chart as a live candle", () => {
    expect(candleCloseStatus("2026-11-11T09:35:00Z", "5m", Date.parse("2026-11-11T09:41:00Z")))
      .toEqual({ status: "STALE", label: "Нет свежих свечей" });
    expect(candleCloseStatus("2026-11-11T09:35:00Z", "5m", Date.parse("2026-11-11T10:10:00Z")))
      .toEqual({ status: "STALE", label: "Нет свежих свечей" });
    expect(candleCloseStatus(undefined, "5m", Date.now()))
      .toEqual({ status: "UNAVAILABLE", label: "" });
  });
});

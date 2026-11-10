import { describe, expect, it } from "vitest";
import {
  ALL_SELECTABLE, MIRROR_OPTIONS, clearAll, isAllSelected,
  onlyWedges, parseUtcMinute, presetEndInclusive, selectAll,
  toggleMirror, toggleStrategy, validateInclusiveWindow,
} from "./runSetup";

describe("local one-symbol strategy setup (no trading)", () => {
  it("selects everything only once, including the entire Mirror bundle", () => {
    const all = selectAll();
    expect(isAllSelected(all)).toBe(true);
    expect(new Set(all.selected).size).toBe(ALL_SELECTABLE.length);
    expect(MIRROR_OPTIONS.every(option => all.selected.includes(option.id))).toBe(true);
    expect(isAllSelected(clearAll())).toBe(false);
  });
  it("enables Mirror defaults while preserving independent selections", () => {
    const trend = toggleStrategy(clearAll(), "H1_TREND", true);
    const mirror = toggleMirror(trend, true);
    expect(mirror.mirror).toBe(true);
    expect(mirror.selected).toContain("H1_TREND");
    expect(mirror.selected).toContain("WEDGE_RISING");
    expect(mirror.selected).toContain("WEDGE_FALLING");
    expect(mirror.selected).toContain("IKIGAI_BOX");
    const withoutBox = toggleStrategy(mirror, "IKIGAI_BOX", false);
    expect(withoutBox.mirror).toBe(true);
    expect(withoutBox.selected).not.toContain("IKIGAI_BOX");
    expect(toggleMirror(withoutBox, false).selected).toEqual(["H1_TREND"]);
  });
  it("lets owner isolate wedges without activating Mirror or other patterns", () => {
    expect(onlyWedges()).toEqual({
      mirror: false, selected: ["WEDGE_RISING", "WEDGE_FALLING"],
    });
  });
  it("applies inclusive last minute for day, week, 30 and 90 days", () => {
    const start = "2026-10-01T12:34";
    const cases = [
      ["DAY", "2026-10-02T12:33", 1440],
      ["WEEK", "2026-10-08T12:33", 10080],
      ["MONTH", "2026-10-31T12:33", 43200],
      ["THREE_MONTHS", "2026-12-30T12:33", 129600],
    ] as const;
    for (const [preset, expectedEnd, minutes] of cases) {
      const end = presetEndInclusive(start, preset);
      expect(end).toBe(expectedEnd);
      const window = validateInclusiveWindow(start, end);
      expect(window.minutes).toBe(minutes);
      expect(window.endExclusiveMs).toBe(parseUtcMinute(end) + 60_000);
    }
  });
  it("handles year and leap-day boundaries without local timezone dependence", () => {
    expect(presetEndInclusive("2024-02-29T23:59", "DAY")).toBe("2024-03-01T23:58");
    expect(presetEndInclusive("2026-12-31T23:59", "WEEK")).toBe("2027-01-07T23:58");
    expect(validateInclusiveWindow("2026-10-01T00:00", "2026-10-01T00:00").minutes).toBe(1);
  });
  it("rejects invalid, reversed or non-minute boundaries", () => {
    expect(() => parseUtcMinute("2026-02-30T00:00")).toThrow();
    expect(() => parseUtcMinute("2026-02-28T24:00")).toThrow();
    expect(() => parseUtcMinute("2026-02-28T11:00:00")).toThrow();
    expect(() => validateInclusiveWindow("2026-10-02T00:00", "2026-10-01T23:59")).toThrow();
  });
});

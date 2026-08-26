import { describe, expect, it } from "vitest";
import { isAtLatest } from "./followLatest";

describe("follow-latest range state", () => {
  it("is false while the viewport is in history", () => {
    expect(isAtLatest({ from: 2, to: 14 }, 24)).toBe(false);
  });

  it("becomes true when the latest candle is back in range", () => {
    expect(isAtLatest({ from: 10, to: 23 }, 24)).toBe(true);
  });

  it("allows the small right-edge tolerance used by the chart", () => {
    expect(isAtLatest({ from: 10, to: 21.5 }, 24)).toBe(true);
    expect(isAtLatest(null, 24)).toBe(false);
  });
});

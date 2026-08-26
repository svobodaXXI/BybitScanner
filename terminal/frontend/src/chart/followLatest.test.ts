import { describe, expect, it, vi } from "vitest";
import {
  DEFAULT_RIGHT_OFFSET_BARS,
  isAtLatest,
  replaceSeriesDataPreservingViewport,
} from "./followLatest";

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

describe("live candle viewport preservation", () => {
  it("restores the historical logical range after replacing live data", () => {
    let visibleRange = { from: 100, to: 160 };
    const scrollToPosition = vi.fn();
    replaceSeriesDataPreservingViewport(
      [{ close: 1 }, { close: 2 }],
      false,
      {
        setData: () => {
          visibleRange = { from: 940, to: 999 };
        },
      },
      {
        getVisibleLogicalRange: () => visibleRange,
        setVisibleLogicalRange: (range) => {
          visibleRange = range;
        },
        scrollToPosition,
      },
    );
    expect(visibleRange).toEqual({ from: 100, to: 160 });
    expect(scrollToPosition).not.toHaveBeenCalled();
  });

  it("keeps the canonical future offset while following latest", () => {
    const scrollToPosition = vi.fn();
    replaceSeriesDataPreservingViewport(
      [{ close: 2 }],
      true,
      { setData: vi.fn() },
      {
        getVisibleLogicalRange: () => null,
        setVisibleLogicalRange: vi.fn(),
        scrollToPosition,
      },
    );
    expect(scrollToPosition).toHaveBeenCalledWith(
      DEFAULT_RIGHT_OFFSET_BARS,
      false,
    );
  });
});

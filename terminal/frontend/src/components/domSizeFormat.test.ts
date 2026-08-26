import { describe, expect, it } from "vitest";
import { formatDomSize } from "./domSizeFormat";

describe("DOM size presentation", () => {
  it.each([
    [123, "123"],
    [123.5, "123.5"],
    [123.25, "123.25"],
    [1_000, "1K"],
    [1_250, "1.25K"],
    [1_500, "1.5K"],
    [10_000, "10K"],
    [1_250_000, "1.25M"],
    [1_500_000, "1.5M"],
  ])("formats %d as %s", (value, expected) => {
    expect(formatDomSize(value)).toBe(expected);
  });
});

import { describe, expect, it } from "vitest";
import { journalTimeParts } from "./journalTime";

describe("causal replay journal original epoch milliseconds", () => {
  it("shows seconds and three separate millisecond digits in MSK and UTC", () => {
    const original = Date.UTC(2026, 10, 10, 8, 4, 8, 129);
    expect(journalTimeParts(original, "MSK")).toEqual({
      date: "10.11.2026", seconds: "11:04:08", milliseconds: "129",
    });
    expect(journalTimeParts(original, "UTC")).toEqual({
      date: "10.11.2026", seconds: "08:04:08", milliseconds: "129",
    });
  });

  it("keeps millisecond precision across local day boundary without rewriting the source", () => {
    const original = Date.UTC(2026, 10, 10, 22, 59, 59, 7);
    expect(journalTimeParts(original, "MSK")).toEqual({
      date: "11.11.2026", seconds: "01:59:59", milliseconds: "007",
    });
    expect(journalTimeParts(original, "UTC")).toEqual({
      date: "10.11.2026", seconds: "22:59:59", milliseconds: "007",
    });
    expect(original).toBe(Date.UTC(2026, 10, 10, 22, 59, 59, 7));
  });

  it("rejects inferred and invalid timestamps", () => {
    for (const time of [NaN, Infinity, -1, 1000.5, Number.MAX_SAFE_INTEGER]) {
      expect(() => journalTimeParts(time, "UTC")).toThrow();
    }
  });
});

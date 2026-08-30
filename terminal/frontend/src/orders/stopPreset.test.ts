import { describe, expect, it } from "vitest";
import {
  DEFAULT_STOP_PRESET_PERCENT,
  DEFAULT_TAKE_PRESET_PERCENT,
  isImprovingStop,
  loadStopPreset,
  saveStopPreset,
  shouldCloseStopSettings,
  stopPercentFromPrice,
  stopPriceFromPercent,
  takePriceFromPercent,
} from "./stopPreset";

describe("STOP preset candidates", () => {
  it("defaults to 2% and persists a changed preset", () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    };
    expect(loadStopPreset(storage)).toBe(DEFAULT_STOP_PRESET_PERCENT);
    expect(DEFAULT_TAKE_PRESET_PERCENT).toBe("3");
    saveStopPreset("3.5", storage);
    expect(loadStopPreset(storage)).toBe("3.5");
  });

  it("builds first and repeat TAKE candidates from the supplied authoritative reference", () => {
    expect(takePriceFromPercent("Long", "100", "3", "0.5")).toBe("103");
    expect(takePriceFromPercent("Short", "100", "3", "0.5")).toBe("97");
    expect(takePriceFromPercent("Long", "110", "3", "0.5")).toBe("113.5");
  });

  it("uses average/current reference and keeps normalized price/percent consistent", () => {
    const firstLong = stopPriceFromPercent("Long", "100", "2", "0.5");
    const trailingShort = stopPriceFromPercent("Short", "90", "2", "0.5");
    expect(firstLong).toBe("98");
    expect(trailingShort).toBe("91.5");
    expect(stopPercentFromPrice("Short", "90", trailingShort)).toBe("1.66666667");
  });

  it("enforces one-way ratchet for repeat taps without restricting manual edits", () => {
    const longCandidate = stopPriceFromPercent("Long", "100", "2", "0.5")!;
    const shortCandidate = stopPriceFromPercent("Short", "100", "2", "0.5")!;
    expect(isImprovingStop("Long", longCandidate, "95")).toBe(true);
    expect(isImprovingStop("Long", longCandidate, "99")).toBe(false);
    expect(isImprovingStop("Short", shortCandidate, "105")).toBe(true);
    expect(isImprovingStop("Short", shortCandidate, "101")).toBe(false);
  });

  it("closes settings on FLAT or symbol switch", () => {
    const open = { ok: true, position_side: "Long" } as const;
    expect(shouldCloseStopSettings("BTCUSDT", open, "BTCUSDT")).toBe(false);
    expect(shouldCloseStopSettings("BTCUSDT", { ...open, position_side: "Flat" }, "BTCUSDT")).toBe(true);
    expect(shouldCloseStopSettings("BTCUSDT", open, "ETHUSDT")).toBe(true);
  });
});

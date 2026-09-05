import { describe, expect, it } from "vitest";
import { createLimitDraft } from "./limitDraft";
import {
  canConfirmLimitInteractionDraft,
  captureLimitInteractionIntent,
  limitDraftVolumeUsdt,
  sideDraftVolumesValid,
} from "./limitInteractionCore";

describe("shared Limit interaction core", () => {
  it("uses the explicit side volume when it is valid", () => {
    expect(captureLimitInteractionIntent({
      side: "Buy",
      selectedVolumeUsdt: "25",
      defaultOneWvUsdt: "10",
      origin: "chart-fast",
    })).toEqual({ side: "Buy", volumeUsdt: "25", origin: "chart-fast" });
  });

  it("falls back to one WV when the side control is empty", () => {
    expect(captureLimitInteractionIntent({
      side: "Sell",
      selectedVolumeUsdt: "",
      defaultOneWvUsdt: "10",
      origin: "chart-fast",
    })).toEqual({ side: "Sell", volumeUsdt: "10", origin: "chart-fast" });
  });

  it("rejects an intent when neither selected volume nor one WV is valid", () => {
    expect(captureLimitInteractionIntent({
      side: "Buy",
      selectedVolumeUsdt: "",
      defaultOneWvUsdt: "0",
      origin: "chart-fast",
    })).toBeNull();
  });

  it("treats the volume captured in the draft as confirmation authority", () => {
    const draft = createLimitDraft({
      draftId: "draft-1",
      symbol: "BTCUSDT",
      side: "Buy",
      origin: "chart-fast",
      volume: { unit: "usdt", amount: "10" },
      sizingReferencePrice: "100",
      price: "99",
      authoritativeTickSize: "0.5",
    });

    expect(limitDraftVolumeUsdt(draft)).toBe("10");
    expect(canConfirmLimitInteractionDraft(draft)).toBe(true);
  });

  it("fails closed when any visible same-side draft has an invalid captured volume", () => {
    const valid = createLimitDraft({
      draftId: "valid",
      symbol: "BTCUSDT",
      side: "Buy",
      origin: "chart-fast",
      volume: { unit: "usdt", amount: "10" },
      sizingReferencePrice: "100",
      price: "99",
      authoritativeTickSize: "0.5",
    });
    const invalid = createLimitDraft({
      draftId: "invalid",
      symbol: "BTCUSDT",
      side: "Buy",
      origin: "limits-popup",
      volume: { unit: "usdt", amount: "" },
      sizingReferencePrice: "100",
      price: "98",
      authoritativeTickSize: "0.5",
    });

    expect(sideDraftVolumesValid([valid], "Buy", "")).toBe(true);
    expect(sideDraftVolumesValid([valid, invalid], "Buy", "10")).toBe(false);
  });
});

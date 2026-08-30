import { describe, expect, it, vi } from "vitest";
import type { PaperState } from "../contracts/trading";
import {
  authoritativeStopPrice,
  authoritativeTakePrice,
  initialStopCandidate,
  paperStateNeedsPolling,
  shouldClearStopDraft,
  stopDraftReducer,
} from "./stopDraft";

const state = (side: "Long" | "Short" | "Flat", stop: string | null): PaperState => ({
  ok: true,
  state_revision: 1,
  account_id: "paper",
  symbol: "BTCUSDT",
  initial_deposit_usdt: "5000",
  equity_usdt: "5000",
  one_wv_usdt: "250",
  position_side: side,
  position_quantity: side === "Flat" ? "0" : "2",
  average_entry: side === "Flat" ? null : "100",
  engaged_notional_usdt: side === "Flat" ? "0" : "200",
  engaged_wv: side === "Flat" ? "0" : "1",
  active_limit_orders: [],
  protection: {
    status: stop === null ? "no_protection_configured" : "confirmed_active",
    take_profit: null,
    stop_loss: stop,
    trailing_stop: null,
    pending_command_id: null,
    warning: null,
    effective_quantity: stop === null ? null : "2",
  },
});

describe("STOP draft", () => {
  it("creates normalized 2% candidates from authoritative LONG and SHORT average entry", () => {
    expect(initialStopCandidate("Long", "100", "0.5")).toBe("98");
    expect(initialStopCandidate("Short", "100", "0.5")).toBe("102");
  });

  it("creates only local state and does not submit a backend mutation", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const draft = stopDraftReducer(null, {
      type: "begin-create", symbol: "BTCUSDT", price: "98",
    });
    expect(draft?.mode).toBe("CREATE");
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("projects ACTIVE only from authoritative protection", () => {
    expect(authoritativeStopPrice(state("Long", null))).toBeNull();
    expect(authoritativeStopPrice(state("Long", "98"))).toBe("98");
  });

  it("projects TAKE only from the authoritative protection aggregate", () => {
    const withBoth = state("Long", "98");
    withBoth.protection!.take_profit = "103";
    expect(authoritativeStopPrice(withBoth)).toBe("98");
    expect(authoritativeTakePrice(withBoth)).toBe("103");
  });

  it("keeps reconciliation polling active while authoritative STOP exists", () => {
    expect(paperStateNeedsPolling(state("Long", "98"))).toBe(true);
    expect(paperStateNeedsPolling(state("Long", null))).toBe(false);
  });

  it("preserves authority while a manual pencil edit worsens STOP and cancel restores it", () => {
    let draft = stopDraftReducer(null, {
      type: "begin-edit", symbol: "BTCUSDT", authoritativePrice: "98",
    });
    draft = stopDraftReducer(draft, { type: "update-price", price: "97" });
    expect(draft).toMatchObject({ price: "97", originalPrice: "98" });
    draft = stopDraftReducer(draft, { type: "clear" });
    expect(draft).toBeNull();
    expect(authoritativeStopPrice(state("Long", "98"))).toBe("98");
  });

  it("clears local draft on FLAT or symbol change", () => {
    const draft = stopDraftReducer(null, {
      type: "begin-create", symbol: "BTCUSDT", price: "98",
    });
    expect(shouldClearStopDraft(draft, state("Flat", null), "BTCUSDT")).toBe(true);
    expect(shouldClearStopDraft(draft, state("Long", null), "ETHUSDT")).toBe(true);
    expect(shouldClearStopDraft(draft, state("Long", null), "BTCUSDT")).toBe(false);
  });
});

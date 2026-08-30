import { expect, it, vi } from "vitest";
import type { PaperState } from "../contracts/trading";
import { stopDraftReducer } from "./stopDraft";
import {
  isSignalTakeProposalHandled,
  markSignalTakeProposalHandled,
  readScannerSignalContext,
  shouldClearSignalTakeProposal,
  signalTakeProposalPrice,
  type ScannerSignalContext,
} from "./signalTakeProposal";

const state = (side: "Long" | "Short" | "Flat" = "Long"): PaperState => ({
  ok: true, state_revision: 1, account_id: "paper", symbol: "BTCUSDT",
  initial_deposit_usdt: "5000", equity_usdt: "5000", one_wv_usdt: "250",
  position_side: side, position_quantity: side === "Flat" ? "0" : "2",
  average_entry: side === "Flat" ? null : "100", engaged_notional_usdt: "200",
  engaged_wv: "1", active_limit_orders: [], protection: {
    status: "no_protection_configured", take_profit: null, stop_loss: null,
    trailing_stop: null, pending_command_id: null, warning: null, effective_quantity: null,
  },
});
const signal = (id: string, targetPrice: string | null = null): ScannerSignalContext => ({
  signalId: id, symbol: "BTCUSDT", targetPrice,
});
const price = (input: Partial<Parameters<typeof signalTakeProposalPrice>[0]> = {}) =>
  signalTakeProposalPrice({
    signal: signal("sig-1"), state: state(), activeTakePrice: null,
    presetPercent: "3", tickSize: "0.5", workspaceSymbol: "BTCUSDT",
    handled: false, ...input,
  });

it("uses a valid signal target, otherwise normalized average-entry TAKE preset", () => {
  expect(price({ signal: signal("target", "104.2") })).toBe("104.5");
  expect(price()).toBe("103");
  expect(price({ state: state("Short") })).toBe("97");
  expect(price({ signal: signal("invalid", "95") })).toBe("103");
});

it("suppresses existing or handled TAKE while allowing a new signal", () => {
  const values = new Map<string, string>();
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
  };
  expect(price({ activeTakePrice: "103" })).toBeNull();
  markSignalTakeProposalHandled("sig-1", storage);
  expect(isSignalTakeProposalHandled("sig-1", storage)).toBe(true);
  expect(price({ handled: isSignalTakeProposalHandled("sig-1", storage) })).toBeNull();
  expect(price({ signal: signal("sig-2"), handled: isSignalTakeProposalHandled("sig-2", storage) })).toBe("103");
});

it("creates and dismisses only the reused local TAKE draft without mutation", () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch");
  const proposal = stopDraftReducer(null, {
    type: "begin-create", symbol: "BTCUSDT", price: "103", proposalSignalId: "sig-1",
  });
  expect(proposal).toMatchObject({ mode: "CREATE", price: "103", proposalSignalId: "sig-1" });
  expect(stopDraftReducer(proposal, { type: "clear" })).toBeNull();
  expect(fetchSpy).not.toHaveBeenCalled();
  fetchSpy.mockRestore();
});

it("clears a proposal on FLAT, symbol change, or authoritative TAKE", () => {
  expect(shouldClearSignalTakeProposal("sig", state("Flat"), "BTCUSDT", null)).toBe(true);
  expect(shouldClearSignalTakeProposal("sig", state(), "ETHUSDT", null)).toBe(true);
  expect(shouldClearSignalTakeProposal("sig", state(), "BTCUSDT", "103")).toBe(true);
  expect(shouldClearSignalTakeProposal(undefined, state(), "BTCUSDT", "103")).toBe(false);
});

it("reads the minimal stable signal identity from workspace deep-link params", () => {
  expect(readScannerSignalContext({
    search: "?signal_id=sig-7&symbol=btcusdt&target_price=105",
    hash: "",
  })).toEqual({ signalId: "sig-7", symbol: "BTCUSDT", targetPrice: "105" });
});

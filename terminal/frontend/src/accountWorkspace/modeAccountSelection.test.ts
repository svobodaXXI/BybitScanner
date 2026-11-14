import { describe, expect, it } from "vitest";
import { scopedProjection } from "./modeAccountSelection";
import type { AccountWorkspaceProjection } from "./accountWorkspaceStore";

const paper = {
  ok: true, account_id: "paper", provider: "PAPER", environment: "PAPER",
  status: "READY", read_only: false, session_generation: 2,
  projection_generation: 2, wallet_balance_usdt: "5000", total_equity_usdt: "5000",
  available_balance_usdt: "5000", positions: [], orders: [], paper_state: null,
} satisfies AccountWorkspaceProjection;
const main = {
  ...paper, account_id: "bybit-a", provider: "BYBIT", environment: "MAINNET",
  read_only: true, capabilities: {
    market: false, limit: false, stop: false, take: false, full_close: false,
  },
} satisfies AccountWorkspaceProjection;

describe("mode-scoped account projection", () => {
  it("keeps Autopilot PAPER regardless of the Terminal MAIN selection", () => {
    expect(scopedProjection("AUTOPILOT", "paper", paper, main)).toBe(paper);
    expect(scopedProjection("TERMINAL", "bybit-a", paper, main)).toBe(main);
    expect(scopedProjection("AUTOPILOT", "bybit-a", paper, main)).toBeNull();
  });
  it("fails closed for missing or mismatched identities", () => {
    expect(scopedProjection("TERMINAL", "bybit-b", paper, main)).toBeNull();
    expect(scopedProjection("TERMINAL", "paper", main, null)).toBeNull();
    expect(scopedProjection("TERMINAL", null, paper, main)).toBeNull();
    expect(scopedProjection("EDITOR", "paper", paper, main)).toBeNull();
    expect(scopedProjection("TERMINAL", "bybit-a", paper,
      { ...main, read_only: false })).toBeNull();
  });
});

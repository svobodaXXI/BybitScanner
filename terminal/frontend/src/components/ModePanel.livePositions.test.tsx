import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AccountWorkspaceProjection } from "../accountWorkspace/accountWorkspaceStore";
import { EMPTY_LIMIT_DRAFT_STATE } from "../orders/limitDraft";
import { ModePanel } from "./ModePanel";

afterEach(() => vi.unstubAllGlobals());
const projection: AccountWorkspaceProjection = {
  ok: true, account_id: "bybit-main", provider: "BYBIT", environment: "MAINNET", status: "READY",
  session_generation: 8, projection_generation: 4, read_only: false,
  wallet_balance_usdt: "90", total_equity_usdt: "100", available_balance_usdt: "70",
  positions: [
    { symbol: "BTCUSDT", side: "Long", size: "1", average_entry: "64000", unrealized_pnl: "1000" },
    { symbol: "ETHUSDT", side: "Short", size: "2", average_entry: "3500", unrealized_pnl: "200" },
  ], orders: [], paper_state: null,
};
const props = {
  mode: "TERMINAL" as const, onModeChange: vi.fn(), symbol: "BTCUSDT", paperState: null,
  activeLimitOrders: [], refreshPaperState: vi.fn(), sizingReferencePrice: "65000",
  authoritativeTickSize: "0.5", limitDraftState: EMPTY_LIMIT_DRAFT_STATE,
  dispatchLimitDraft: vi.fn(), onLimitDraftConfirm: vi.fn(), onPositionSideChange: vi.fn(),
};

describe("ModePanel positions navigation", () => {
  it("opens outside disabled mutations and selects the exact LIVE symbol without mutations", () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
    const onWorkspaceSymbolSelect = vi.fn();
    render(<ModePanel {...props} accountWorkspaceProjection={projection} mutationsAllowed={false}
      liveMarketAllowed={false} onWorkspaceSymbolSelect={onWorkspaceSymbolSelect} />);
    const entry = screen.getByRole("button", { name: "Открытые позиции" });
    expect(screen.getByLabelText("PAPER utility controls")).toContainElement(entry);
    expect(screen.getByLabelText("Workspace account")).not.toContainElement(entry);
    const mutationFieldsets = Array.from(document.querySelectorAll<HTMLFieldSetElement>(".paper-mutation-boundary"));
    expect(mutationFieldsets).toHaveLength(2);
    mutationFieldsets.forEach((fieldset) => {
      expect(fieldset).toBeDisabled();
      expect(fieldset).not.toContainElement(entry);
    });
    expect(entry).toBeEnabled();
    fireEvent.pointerDown(entry, { pointerType: "touch", pointerId: 1 });
    fireEvent.pointerUp(entry, { pointerType: "touch", pointerId: 1 });
    fireEvent.click(entry);
    expect(screen.getByTestId("live-positions-surface").parentElement).toBe(document.body);
    fireEvent.click(screen.getByRole("button", { name: /Открыть ETHUSDT/ }));
    expect(onWorkspaceSymbolSelect).toHaveBeenCalledOnce();
    expect(onWorkspaceSymbolSelect).toHaveBeenCalledWith("ETHUSDT");
    expect(screen.queryByTestId("live-positions-surface")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.every(([url, options]) => url === "/api/accounts" && options?.method === undefined)).toBe(true);
  });

  it("preserves the PAPER positions overlay path", () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) }));
    render(<ModePanel {...props} accountWorkspaceProjection={{ ...projection, account_id: "paper", provider: "PAPER", environment: "PAPER" }} />);
    fireEvent.click(screen.getByRole("button", { name: "Открытые позиции" }));
    expect(document.querySelector(".paper-open-positions")).toBeInTheDocument();
    expect(screen.queryByTestId("live-positions-surface")).not.toBeInTheDocument();
  });
});

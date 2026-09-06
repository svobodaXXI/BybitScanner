import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ComponentProps, Dispatch } from "react";
import { beforeEach, expect, it, vi } from "vitest";
import type { LimitDraftAction } from "../orders/limitDraft";

const { liveProjection, liveProjectionState, refreshActiveLive } = vi.hoisted(() => {
  const projection = {
    ok: true,
    account_id: "bybit-main",
    provider: "BYBIT",
    environment: "MAINNET",
    status: "READY",
    session_generation: 8,
    projection_generation: 3,
    read_only: false,
    capabilities: { market: false, limit: true, stop: true, take: true, full_close: false },
    wallet_balance_usdt: "10",
    total_equity_usdt: "10",
    available_balance_usdt: "10",
    positions: [],
    orders: [],
    paper_state: null,
  };
  return {
    liveProjection: projection,
    liveProjectionState: { current: projection },
    refreshActiveLive: vi.fn(async () => {}),
  };
});

beforeEach(() => {
  liveProjectionState.current = liveProjection;
  refreshActiveLive.mockClear();
});

vi.mock("../accountWorkspace/accountWorkspaceStore", () => ({
  accountWorkspaceStore: { refreshActiveLive },
  useAccountWorkspace: () => ({ switching: false, projection: liveProjectionState.current }),
}));
vi.mock("../marketData/useMarketData", () => ({
  setMarketSymbol: vi.fn(), setMarketTimeframe: vi.fn(),
  useMarketData: () => ({
    book: { symbol: "ONGUSDT", health: "READY", bids: [{ price: 0.1, size: 1 }], asks: [{ price: 0.101, size: 1 }] },
    candles: [], trades: [], ownOrders: [], tickSize: 0.00001,
  }),
}));
vi.mock("../paperTrading/paperTradingStore", () => ({
  paperTradingStore: {
    setAccountSession: vi.fn(), captureApplyPaperState: () => vi.fn(), refresh: vi.fn(),
    runMutation: vi.fn(async (_key: string, operation: () => Promise<unknown>) => operation()),
    subscribe: vi.fn(() => () => {}), getSnapshot: () => ({ paperState: null, pendingActions: new Set() }),
  },
  usePaperTrading: () => ({ paperState: null, pendingActions: new Set() }),
}));
vi.mock("../components/AccountMenu", () => ({ AccountMenu: () => null }));
vi.mock("../components/DomPanel", () => ({ DomPanel: () => null }));
vi.mock("../components/TapePanel", () => ({ TapePanel: () => null }));
vi.mock("../components/WorkspaceHeader", () => ({ WorkspaceHeader: () => null }));
vi.mock("../telegram/TelegramMiniAppBridge", () => ({ TelegramMiniAppBridge: () => null }));
vi.mock("../components/ChartPanel", () => ({ ChartPanel: () => null }));
vi.mock("../components/ModePanel", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../components/ModePanel")>();
  const Harness = ({ dispatchLimitDraft, onSelectedVolumeChange, onLimitDraftConfirm }: {
    dispatchLimitDraft: Dispatch<LimitDraftAction>;
    onSelectedVolumeChange: (side: "Buy", value: string) => void;
    onLimitDraftConfirm: () => void;
  }) => <div>
    <button type="button" onClick={() => dispatchLimitDraft({ type: "begin", draft: {
      draftId: "live-draft", symbol: "ONGUSDT", side: "Buy", origin: "chart-fast",
      volume: { unit: "usdt", amount: "" }, sizingReferencePrice: "0.1005", price: "0.09849",
      authoritativeTickSize: "0.00001", status: "draft", clientActionId: null, rejectionReason: null,
    } })}>Create draft</button>
    <button type="button" onClick={() => {
      onSelectedVolumeChange("Buy", "5");
      dispatchLimitDraft({ type: "update-volume", draftId: "live-draft", volume: { unit: "usdt", amount: "5" } });
    }}>Set valid volume</button>
    <button type="button" onClick={() => onLimitDraftConfirm()}>Confirm draft</button>
  </div>;
  return { ModePanel: (props: ComponentProps<typeof actual.ModePanel>) => <Harness {...props as Parameters<typeof Harness>[0]} /> };
});

import { App } from "./App";

it("drops a late LIVE Limit response after session authority changes", async () => {
  let resolveLimit!: (value: { ok: boolean; json: () => Promise<object> }) => void;
  const fetchMock = vi.fn((url: string) => url === "/api/live/limit"
    ? new Promise<{ ok: boolean; json: () => Promise<object> }>((resolve) => { resolveLimit = resolve; })
    : Promise.resolve({ ok: true, json: async () => ({ instruments: [] }) }));
  vi.stubGlobal("fetch", fetchMock);

  const view = render(<App />);
  await act(async () => {});
  fireEvent.click(screen.getByRole("button", { name: "Create draft" }));
  fireEvent.click(screen.getByRole("button", { name: "Set valid volume" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm draft" }));
  await waitFor(() => expect(fetchMock.mock.calls.filter(([url]) => url === "/api/live/limit")).toHaveLength(1));

  await act(async () => {
    liveProjectionState.current = { ...liveProjection, session_generation: 9, projection_generation: 4 };
    view.rerender(<App />);
  });

  await act(async () => resolveLimit({
    ok: true,
    json: async () => ({
      status: "accepted_pending", reason_code: "accepted_pending",
      command_id: "old-session-command", reconciliation_required: true,
    }),
  }));

  expect(refreshActiveLive).not.toHaveBeenCalled();
});

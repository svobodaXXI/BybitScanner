import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { Dispatch, ReactNode } from "react";
import { beforeEach, expect, it, vi } from "vitest";
import type { LimitDraftAction, LimitDraft } from "../orders/limitDraft";

const { liveProjection, liveProjectionState, refreshActiveLive } = vi.hoisted(() => {
  const projection = {
    ok: true, account_id: "bybit-main", provider: "BYBIT", environment: "MAINNET",
    status: "READY", session_generation: 8, projection_generation: 3, read_only: false,
    capabilities: { market: false, limit: true, stop: false, take: false, full_close: false },
    wallet_balance_usdt: "10", total_equity_usdt: "10", available_balance_usdt: "10",
    positions: [], orders: [], paper_state: null,
  };
  return {
    refreshActiveLive: vi.fn(async () => {}),
    liveProjection: projection,
    liveProjectionState: { current: projection },
  };
});

beforeEach(() => {
  liveProjectionState.current = liveProjection;
  refreshActiveLive.mockClear();
});

vi.mock("../accountWorkspace/accountWorkspaceStore", () => ({
  accountWorkspaceStore: { refreshActiveLive },
  useAccountWorkspace: () => ({
    switching: false,
    projection: liveProjectionState.current,
  }),
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
    runMutation: vi.fn(), subscribe: vi.fn(() => () => {}), getSnapshot: () => ({ paperState: null, pendingActions: new Set() }),
  },
  usePaperTrading: () => ({ paperState: null, pendingActions: new Set() }),
}));
vi.mock("../components/AccountMenu", () => ({ AccountMenu: () => null }));
vi.mock("../components/DomPanel", () => ({ DomPanel: () => null }));
vi.mock("../components/TapePanel", () => ({ TapePanel: () => null }));
vi.mock("../components/WorkspaceHeader", () => ({ WorkspaceHeader: () => null }));
vi.mock("../telegram/TelegramMiniAppBridge", () => ({ TelegramMiniAppBridge: () => null }));
vi.mock("../components/ChartPanel", () => ({
  ChartPanel: ({ pendingLimitDrafts = [], pendingLimitVolumeValid, onPendingLimitConfirm, workspaceControls }: {
    pendingLimitDrafts?: readonly LimitDraft[];
    pendingLimitVolumeValid: Readonly<Record<"Buy" | "Sell", boolean>>;
    onPendingLimitConfirm: (draftId: string) => void;
    workspaceControls?: ReactNode;
  }) => <div>{workspaceControls}{pendingLimitDrafts.map((draft) => (
    <button key={draft.draftId} type="button" disabled={!pendingLimitVolumeValid[draft.side]}
      onClick={() => onPendingLimitConfirm(draft.draftId)}>Chart confirm</button>
  ))}</div>,
}));
vi.mock("../components/ModePanel", () => ({
  ModePanel: ({ dispatchLimitDraft, onSelectedVolumeChange, onLimitDraftConfirm }: {
    dispatchLimitDraft: Dispatch<LimitDraftAction>;
    onSelectedVolumeChange: (side: "Buy", value: string) => void;
    onLimitDraftConfirm: () => void;
  }) => <div>
    <button type="button" onClick={() => dispatchLimitDraft({ type: "begin", draft: {
      draftId: "live-draft", symbol: "ONGUSDT", side: "Buy", origin: "limits-popup",
      volume: { unit: "usdt", amount: "" }, sizingReferencePrice: "0.1005", price: "0.09849",
      authoritativeTickSize: "0.00001", status: "draft", clientActionId: null, rejectionReason: null,
    } })}>Create draft</button>
    <button type="button" onClick={() => onSelectedVolumeChange("Buy", "5")}>Set valid volume</button>
    <button type="button" onClick={onLimitDraftConfirm}>Attempt confirmation</button>
  </div>,
}));

import { App } from "./App";

it("blocks an empty LIVE Limit volume with feedback and no mutation request", async () => {
  const fetchMock = vi.fn(async (_url: string, _options?: RequestInit) => (
    { ok: true, json: async () => ({ instruments: [] }) }
  ));
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  await act(async () => {});
  fireEvent.click(screen.getByRole("button", { name: "Create draft" }));
  expect(screen.getByRole("button", { name: "Chart confirm" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Attempt confirmation" }));
  expect(await screen.findByRole("status")).toHaveTextContent(/Limit confirmation|positive USDT/);
  expect(fetchMock.mock.calls.filter(([url, options]) => url === "/api/live/limit" && options?.method === "POST")).toHaveLength(0);
});

it("sends exactly one LIVE Limit request after volume becomes valid", async () => {
  const fetchMock = vi.fn(async (url: string, _options?: RequestInit) => url === "/api/live/limit"
    ? { ok: true, json: async () => ({ status: "accepted_pending", reason_code: "accepted_pending", command_id: "c1", reconciliation_required: true }) }
    : { ok: true, json: async () => ({ instruments: [] }) });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Create draft" }));
  fireEvent.click(screen.getByRole("button", { name: "Set valid volume" }));
  const confirm = screen.getByRole("button", { name: "Chart confirm" });
  await waitFor(() => expect(confirm).toBeEnabled());
  fireEvent.click(confirm);
  await waitFor(() => expect(fetchMock.mock.calls.filter(
    ([url, options]) => url === "/api/live/limit" && options?.method === "POST",
  )).toHaveLength(1));
});

it("does not resubmit a submitting LIVE Limit draft after projection refresh", async () => {
  let resolveLimit: (() => void) | undefined;
  const fetchMock = vi.fn((url: string, _options?: RequestInit) => url === "/api/live/limit"
    ? new Promise<{ ok: boolean; json: () => Promise<object> }>((resolve) => {
        resolveLimit = () => resolve({
          ok: true,
          json: async () => ({
            status: "accepted_pending", reason_code: "accepted_pending",
            command_id: "c1", reconciliation_required: true,
          }),
        });
      })
    : Promise.resolve({ ok: true, json: async () => ({ instruments: [] }) }));
  vi.stubGlobal("fetch", fetchMock);
  const view = render(<App />);
  await act(async () => {});
  fireEvent.click(screen.getByRole("button", { name: "Create draft" }));
  fireEvent.click(screen.getByRole("button", { name: "Set valid volume" }));
  const confirm = screen.getByRole("button", { name: "Chart confirm" });
  await waitFor(() => expect(confirm).toBeEnabled());
  fireEvent.click(confirm);
  await waitFor(() => expect(fetchMock.mock.calls.filter(
    ([url, options]) => url === "/api/live/limit" && options?.method === "POST",
  )).toHaveLength(1));

  await act(async () => {
    liveProjectionState.current = { ...liveProjection, projection_generation: 4 };
    view.rerender(<App />);
  });
  fireEvent.click(screen.getByRole("button", { name: "Attempt confirmation" }));
  expect(fetchMock.mock.calls.filter(
    ([url, options]) => url === "/api/live/limit" && options?.method === "POST",
  )).toHaveLength(1);

  await act(async () => resolveLimit?.());
});

it("allows a new identity for a deliberate retry after definitive rejection", async () => {
  let limitCalls = 0;
  const fetchMock = vi.fn(async (url: string, _options?: RequestInit) => {
    if (url !== "/api/live/limit") return { ok: true, json: async () => ({ instruments: [] }) };
    limitCalls += 1;
    return {
      ok: true,
      json: async () => limitCalls === 1
        ? { status: "blocked", reason_code: "rejected", command_id: null, reconciliation_required: false }
        : { status: "accepted_pending", reason_code: "accepted_pending", command_id: "c2", reconciliation_required: true },
    };
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  await act(async () => {});
  fireEvent.click(screen.getByRole("button", { name: "Create draft" }));
  fireEvent.click(screen.getByRole("button", { name: "Set valid volume" }));
  const confirm = screen.getByRole("button", { name: "Chart confirm" });
  await waitFor(() => expect(confirm).toBeEnabled());
  fireEvent.click(confirm);
  await waitFor(() => expect(confirm).toBeEnabled());
  fireEvent.click(confirm);
  await waitFor(() => expect(fetchMock.mock.calls.filter(
    ([url, options]) => url === "/api/live/limit" && options?.method === "POST",
  )).toHaveLength(2));
  const bodies = fetchMock.mock.calls
    .filter(([url, options]) => url === "/api/live/limit" && options?.method === "POST")
    .map(([, options]) => JSON.parse(String(options?.body)) as { client_action_id: string });
  expect(bodies[0].client_action_id).not.toBe(bodies[1].client_action_id);
});

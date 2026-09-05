import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ComponentProps, Dispatch, ReactNode } from "react";
import { beforeEach, expect, it, vi } from "vitest";
import type { LimitDraftAction, LimitDraft } from "../orders/limitDraft";
import { PendingLimitLine } from "../chart/PendingLimitLine";
import type { PaperLimitOrder } from "../contracts/trading";

const { liveProjection, liveProjectionState, refreshActiveLive } = vi.hoisted(() => {
  const projection = {
    ok: true, account_id: "bybit-main", provider: "BYBIT", environment: "MAINNET",
    status: "READY", session_generation: 8, projection_generation: 3, read_only: false,
    capabilities: { market: false, limit: true, stop: false, take: false, full_close: false },
    wallet_balance_usdt: "10", total_equity_usdt: "10", available_balance_usdt: "10",
    positions: [], orders: [] as Array<Record<string, unknown>>, paper_state: null,
  };
  return {
    refreshActiveLive: vi.fn(async () => {}),
    liveProjection: projection,
    liveProjectionState: { current: projection },
  };
});

const testMode = vi.hoisted(() => ({
  realPanel: false,
  chart: {} as { fastLimitActive?: boolean; onFastLimitPriceSelect?: (price: string) => void },
}));

beforeEach(() => {
  testMode.realPanel = false;
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
    runMutation: vi.fn(async (_key: string, operation: () => Promise<unknown>) => operation()), subscribe: vi.fn(() => () => {}), getSnapshot: () => ({ paperState: null, pendingActions: new Set() }),
  },
  usePaperTrading: () => ({ paperState: null, pendingActions: new Set() }),
}));
vi.mock("../components/AccountMenu", () => ({ AccountMenu: () => null }));
vi.mock("../components/DomPanel", () => ({ DomPanel: () => null }));
vi.mock("../components/TapePanel", () => ({ TapePanel: () => null }));
vi.mock("../components/WorkspaceHeader", () => ({ WorkspaceHeader: () => null }));
vi.mock("../telegram/TelegramMiniAppBridge", () => ({ TelegramMiniAppBridge: () => null }));
vi.mock("../components/ChartPanel", () => ({
  ChartPanel: ({ pendingLimitDrafts = [], liveLimitDrafts, pendingLimitVolumeValid, onPendingLimitConfirm, workspaceControls, fastLimitActive, onFastLimitPriceSelect }: {
    pendingLimitDrafts?: readonly LimitDraft[];
    liveLimitDrafts?: boolean;
    pendingLimitVolumeValid: Readonly<Record<"Buy" | "Sell", boolean>>;
    onPendingLimitConfirm: (draftId: string) => void;
    workspaceControls?: ReactNode;
    fastLimitActive?: boolean;
    onFastLimitPriceSelect?: (price: string) => void;
  }) => {
    testMode.chart = { fastLimitActive, onFastLimitPriceSelect };
    return <div>{workspaceControls}{pendingLimitDrafts.map((draft) => (
    <PendingLimitLine key={draft.draftId} side={draft.side} price={draft.price} top={120}
      onDragClientY={() => {}} confirmDisabled={!pendingLimitVolumeValid[draft.side]}
      popupLinked={draft.origin === "limits-popup"}
      liveSubmitStatus={liveLimitDrafts && (draft.status === "submitting" || draft.status === "ambiguous")
        ? draft.status : undefined}
      onConfirm={() => onPendingLimitConfirm(draft.draftId)} />
  ))}</div>;
  },
}));
vi.mock("../components/ModePanel", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../components/ModePanel")>();
  const DraftPanel = ({ dispatchLimitDraft, onSelectedVolumeChange, onLimitDraftConfirm, activeLimitOrders }: {
    dispatchLimitDraft: Dispatch<LimitDraftAction>;
    onSelectedVolumeChange: (side: "Buy", value: string) => void;
    onLimitDraftConfirm: () => void;
    activeLimitOrders: readonly PaperLimitOrder[];
  }) => <div>
    {activeLimitOrders.map((order) => <div key={order.order_id}>Active LIVE Limit {order.order_id}</div>)}
    <button type="button" onClick={() => dispatchLimitDraft({ type: "begin", draft: {
      draftId: "live-draft", symbol: "ONGUSDT", side: "Buy", origin: "chart-fast",
      volume: { unit: "usdt", amount: "" }, sizingReferencePrice: "0.1005", price: "0.09849",
      authoritativeTickSize: "0.00001", status: "draft", clientActionId: null, rejectionReason: null,
    } })}>Create draft</button>
    <button type="button" onClick={() => {
      onSelectedVolumeChange("Buy", "5");
      dispatchLimitDraft({
        type: "update-volume",
        draftId: "live-draft",
        volume: { unit: "usdt", amount: "5" },
      });
    }}>Set valid volume</button>
    <button type="button" onClick={() => onLimitDraftConfirm()}>Attempt confirmation</button>
  </div>;
  return { ModePanel: (props: ComponentProps<typeof actual.ModePanel>) => testMode.realPanel
    ? <actual.ModePanel {...props} />
    : <DraftPanel {...props as Parameters<typeof DraftPanel>[0]} /> };
});

import { App } from "./App";
import { paperTradingStore } from "../paperTrading/paperTradingStore";

it.each(["Buy", "Sell"] as const)("creates a LIVE %s chart draft only with current Limit capability and no submission", async (side) => {
  testMode.realPanel = true;
  const fetchMock = vi.fn(async (_url: string, _options?: RequestInit) => ({
    ok: true, json: async () => ({ instruments: [] }),
  }));
  vi.stubGlobal("fetch", fetchMock);
  const view = render(<App />);
  await act(async () => {});
  fireEvent.change(screen.getByLabelText(`${side.toUpperCase()} amount`), { target: { value: "5" } });
  vi.useFakeTimers();
  try {
    fireEvent.pointerDown(screen.getByRole("button", { name: side.toUpperCase() }), {
      button: 0, pointerId: 10, pointerType: "touch",
    });
    act(() => vi.advanceTimersByTime(200));
    expect(testMode.chart.fastLimitActive).toBe(true);
    act(() => testMode.chart.onFastLimitPriceSelect?.("0.09849"));
    expect(screen.getByRole("slider", { name: `Pending ${side} Limit at 0.09849` })).toBeInTheDocument();

    liveProjectionState.current = { ...liveProjection, capabilities: { ...liveProjection.capabilities, limit: false } };
    view.rerender(<App />);
    act(() => testMode.chart.onFastLimitPriceSelect?.("0.09848"));
    expect(screen.queryByRole("slider", { name: `Pending ${side} Limit at 0.09848` })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, options]) => options?.method === "POST")).toBe(false);
  } finally {
    vi.useRealTimers();
  }
});

it("blocks an empty LIVE Limit volume with feedback and no mutation request", async () => {
  const fetchMock = vi.fn(async (_url: string, _options?: RequestInit) => (
    { ok: true, json: async () => ({ instruments: [] }) }
  ));
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  await act(async () => {});
  fireEvent.click(screen.getByRole("button", { name: "Create draft" }));
  expect(screen.getByRole("button", { name: "Confirm pending Buy Limit" })).toBeDisabled();
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
  const confirm = screen.getByRole("button", { name: "Confirm pending Buy Limit" });
  await waitFor(() => expect(confirm).toBeEnabled());
  fireEvent.click(confirm);
  expect(screen.getByRole("status")).toHaveTextContent("SUBMITTING…");
  expect(confirm).toBeDisabled();
  fireEvent.click(confirm);
  fireEvent.click(screen.getByRole("button", { name: "Attempt confirmation" }));
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
  const confirm = screen.getByRole("button", { name: "Confirm pending Buy Limit" });
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
  const confirm = screen.getByRole("button", { name: "Confirm pending Buy Limit" });
  await waitFor(() => expect(confirm).toBeEnabled());
  fireEvent.click(confirm);
  await waitFor(() => expect(confirm).toBeEnabled());
  expect(limitCalls).toBe(1);
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  fireEvent.click(confirm);
  await waitFor(() => expect(fetchMock.mock.calls.filter(
    ([url, options]) => url === "/api/live/limit" && options?.method === "POST",
  )).toHaveLength(2));
  const bodies = fetchMock.mock.calls
    .filter(([url, options]) => url === "/api/live/limit" && options?.method === "POST")
    .map(([, options]) => JSON.parse(String(options?.body)) as { client_action_id: string });
  expect(bodies[0].client_action_id).not.toBe(bodies[1].client_action_id);
});

it.each(["unknown", "network failure"])("locks %s without resending after projection refresh", async (outcome) => {
  const fetchMock = vi.fn(async (url: string, _options?: RequestInit) => {
    if (url !== "/api/live/limit") return { ok: true, json: async () => ({ instruments: [] }) };
    if (outcome === "network failure") throw new Error("connection lost");
    return { ok: true, json: async () => ({
      status: "unknown", reason_code: "unknown", command_id: "original-command", reconciliation_required: true,
    }) };
  });
  vi.stubGlobal("fetch", fetchMock);
  const view = render(<App />);
  await act(async () => {});
  fireEvent.click(screen.getByRole("button", { name: "Create draft" }));
  fireEvent.click(screen.getByRole("button", { name: "Set valid volume" }));
  act(() => {
    fireEvent.click(screen.getByRole("button", { name: "Attempt confirmation" }));
    fireEvent.click(screen.getByRole("button", { name: "Attempt confirmation" }));
  });
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("RECONCILING — DO NOT RETRY"));
  await act(async () => {
    liveProjectionState.current = { ...liveProjection, projection_generation: 4 };
    view.rerender(<App />);
  });
  const confirm = screen.getByRole("button", { name: "Confirm pending Buy Limit" });
  expect(confirm).toBeDisabled();
  fireEvent.click(confirm);
  fireEvent.click(screen.getByRole("button", { name: "Attempt confirmation" }));
  expect(fetchMock.mock.calls.filter(([url]) => url === "/api/live/limit")).toHaveLength(1);
  expect(screen.getByRole("status")).toHaveTextContent("RECONCILING — DO NOT RETRY");
});

it.each(["completed", "accepted_pending"])("%s removes the draft and refreshes authoritative LIVE orders", async (status) => {
  refreshActiveLive.mockImplementationOnce(async () => {
    liveProjectionState.current = { ...liveProjection, projection_generation: 4, orders: [{
      order_id: "exchange-order", symbol: "ONGUSDT", side: "Buy", order_type: "Limit",
      status: "open", price: "0.09849", quantity: "50",
    }] };
  });
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({
    ok: true, json: async () => url === "/api/live/limit"
      ? { status, reason_code: status, command_id: "c1", reconciliation_required: status === "accepted_pending" }
      : { instruments: [] },
  })));
  const view = render(<App />);
  await act(async () => {});
  fireEvent.click(screen.getByRole("button", { name: "Create draft" }));
  fireEvent.click(screen.getByRole("button", { name: "Set valid volume" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm pending Buy Limit" }));
  await waitFor(() => expect(refreshActiveLive).toHaveBeenCalledOnce());
  view.rerender(<App />);
  expect(screen.getByText("Active LIVE Limit exchange-order")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Confirm pending Buy Limit" })).not.toBeInTheDocument();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

it("popup and chart confirms share one LIVE CREATE attempt", async () => {
  testMode.realPanel = true;

  const fetchMock = vi.fn(async (url: string, _options?: RequestInit) => ({
    ok: true,
    json: async () =>
      url === "/api/live/limit"
        ? {
            status: "accepted_pending",
            reason_code: "accepted_pending",
            command_id: "popup-create",
            reconciliation_required: true,
          }
        : { instruments: [] },
  }));

  vi.stubGlobal("fetch", fetchMock);

  render(<App />);
  await act(async () => {});

  fireEvent.click(screen.getByRole("button", { name: "BUY LIMITS 0" }));

  const popup = screen.getByRole("dialog", { name: "New Buy Limit" });

  fireEvent.change(within(popup).getByLabelText("LONG Limit volume"), {
    target: { value: "5" },
  });

  const chartConfirm = screen.getByRole("button", {
    name: "Confirm pending Buy Limit",
  });

  fireEvent.click(
    within(popup).getByRole("button", { name: "Confirm LONG Limit" }),
  );
  fireEvent.click(chartConfirm);

  await waitFor(() =>
    expect(
      fetchMock.mock.calls.filter(
        ([url, options]) =>
          url === "/api/live/limit" && options?.method === "POST",
      ),
    ).toHaveLength(1),
  );
});

function setupCancel(status = "completed", deferred = false) {
  testMode.realPanel = true;
  liveProjectionState.current = { ...liveProjection, orders: [
    { order_id: "test-buy", symbol: "ONGUSDT", side: "Buy", order_type: "Limit", status: "open", price: "0.098", quantity: "50" },
    { order_id: "external-sell", symbol: "ONGUSDT", side: "Sell", order_type: "Limit", status: "open", price: "0.11", quantity: "50" },
  ] };
  let resolve!: (value: object) => void;
  const response = new Promise<object>((done) => { resolve = done; });
  const fetcher = vi.fn(async (url: string, _options?: RequestInit) => {
    if (url === "/api/live/limit/cancel") {
      if (status === "network-error") throw new Error("connection lost");
      return { ok: true, json: async () => deferred ? response : {
        status, reason_code: status, command_id: "cancel-command", reconciliation_required: status === "unknown",
      } };
    }
    return { ok: true, json: async () => ({ instruments: [], accounts: [] }) };
  });
  vi.stubGlobal("fetch", fetcher);
  vi.mocked(paperTradingStore.runMutation).mockClear();
  vi.mocked(paperTradingStore.refresh).mockClear();
  const view = render(<App />);
  return { fetcher, view, resolve };
}

function cancelBuySide() {
  vi.mocked(paperTradingStore.refresh).mockClear();
  fireEvent.click(screen.getByRole("button", { name: "Cancel all Buy Limit orders for ONGUSDT" }));
  const dialog = screen.getByRole("dialog", { name: "Cancel all LONG Limit orders for ONGUSDT?" });
  fireEvent.click(within(dialog).getByRole("button", { name: "CANCEL" }));
}

it("routes the real LIVE side-cancel control only to LIVE and leaves the opposite side alone", async () => {
  const { fetcher } = setupCancel();
  await act(async () => {});
  cancelBuySide();
  await screen.findByText("LIVE LIMIT cancellations submitted: 1/1");
  const posts = fetcher.mock.calls.filter(([, options]) => options?.method === "POST");
  expect(posts).toHaveLength(1);
  expect(posts[0][0]).toBe("/api/live/limit/cancel");
  expect(JSON.parse(String(posts[0][1]?.body))).toMatchObject({
    account_id: "bybit-main", session_generation: 8, order_id: "test-buy", symbol: "ONGUSDT",
  });
  expect(refreshActiveLive).toHaveBeenCalledOnce();
  expect(paperTradingStore.runMutation).not.toHaveBeenCalled();
  expect(paperTradingStore.refresh).not.toHaveBeenCalled();
});

it.each(["unknown", "network-error", "blocked"])("never falls back to PAPER on %s", async (status) => {
  const { fetcher } = setupCancel(status);
  await act(async () => {});
  cancelBuySide();
  await screen.findByText("LIVE LIMIT cancellation failed or requires reconciliation");
  expect(fetcher.mock.calls.filter(([, options]) => options?.method === "POST").map(([url]) => url))
    .toEqual(["/api/live/limit/cancel"]);
  expect(paperTradingStore.runMutation).not.toHaveBeenCalled();
  expect(paperTradingStore.refresh).not.toHaveBeenCalled();
  expect(refreshActiveLive).not.toHaveBeenCalled();
  expect(screen.queryByText("PAPER LIMIT cancellation failed")).not.toBeInTheDocument();
});

it("blocks repeated side cancellation while in flight and suppresses stale session feedback", async () => {
  const { fetcher, view, resolve } = setupCancel("completed", true);
  await act(async () => {});
  cancelBuySide();
  cancelBuySide();
  expect(fetcher.mock.calls.filter(([url]) => url === "/api/live/limit/cancel")).toHaveLength(1);
  await act(async () => {
    liveProjectionState.current = { ...liveProjectionState.current, session_generation: 9 };
    view.rerender(<App />);
  });
  await act(async () => resolve({ status: "completed", reason_code: "completed", command_id: "c", reconciliation_required: false }));
  expect(screen.queryByText("LIVE LIMIT cancellations submitted: 1/1")).not.toBeInTheDocument();
  expect(paperTradingStore.runMutation).not.toHaveBeenCalled();
});

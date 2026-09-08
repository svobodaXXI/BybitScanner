import { act, render, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { paperTradingStore } from "../paperTrading/paperTradingStore";

let latestOnLimitCancel: ((orderId: string) => Promise<{ status: string } | null>) | undefined;

vi.mock("../components/ModePanel", () => ({
  ModePanel: (props: { onLimitCancel?: (orderId: string) => Promise<{ status: string } | null> }) => {
    latestOnLimitCancel = props.onLimitCancel;
    return null;
  },
}));
vi.mock("../components/DomPanel", () => ({ DomPanel: () => null }));
vi.mock("../components/TapePanel", () => ({ TapePanel: () => null }));
vi.mock("../components/ChartPanel", () => ({
  ChartPanel: ({ workspaceControls }: { workspaceControls: ReactNode }) => <>{workspaceControls}</>,
}));
vi.mock("../components/WorkspaceHeader", () => ({ WorkspaceHeader: () => null }));
vi.mock("../telegram/TelegramMiniAppBridge", () => ({ TelegramMiniAppBridge: () => null }));
vi.mock("../marketData/useMarketData", () => ({
  setMarketSymbol: vi.fn(),
  setMarketTimeframe: vi.fn(),
  useMarketData: () => ({
    book: {
      symbol: "ONGUSDT",
      health: "READY",
      bids: [{ price: 0.093, size: 1 }],
      asks: [{ price: 0.094, size: 1 }],
    },
    candles: [],
    trades: [],
    ownOrders: [],
    tickSize: 0.00001,
  }),
}));
vi.mock("../accountWorkspace/accountWorkspaceStore", () => ({
  accountWorkspaceStore: {
    refreshActiveLive: vi.fn(async () => undefined),
  },
  useAccountWorkspace: () => ({
    switching: false,
    projection: {
      account_id: "paper",
      provider: "PAPER",
      environment: "PAPER",
      status: "READY",
      session_generation: 1,
      projection_generation: 1,
      read_only: false,
      wallet_balance_usdt: "5000",
      total_equity_usdt: "5000",
      available_balance_usdt: "5000",
      one_wv_usdt: "250",
      positions: [],
      orders: [],
      paper_state: null,
    },
  }),
}));

const paperState = (revision: number, withOrder: boolean) => ({
  ok: true,
  state_revision: revision,
  account_id: "paper",
  symbol: "ONGUSDT",
  initial_deposit_usdt: "5000",
  equity_usdt: "5000",
  one_wv_usdt: "250",
  position_side: "Flat",
  position_quantity: "0",
  average_entry: null,
  engaged_notional_usdt: "0",
  engaged_wv: "0",
  active_limit_orders: withOrder
    ? [{
        order_id: "order-1",
        order_link_id: "link-1",
        symbol: "ONGUSDT",
        side: "Buy",
        price: "0.09",
        quantity: "10",
        time_in_force: "GTC",
      }]
    : [],
  protection: null,
});

beforeEach(() => {
  latestOnLimitCancel = undefined;
  paperTradingStore.setAccountSession(null, null);
  paperTradingStore.setSymbol("ONGUSDT");
});

it("refreshes the PAPER cancel callback after the authoritative account session is installed", async () => {
  let cancelCalls = 0;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/instruments") {
      return { ok: true, json: async () => ({ instruments: [{ symbol: "ONGUSDT" }] }) } as Response;
    }
    if (url.includes("/api/paper-state")) {
      return { ok: true, json: async () => paperState(10, true) } as Response;
    }
    if (url === "/api/limit/cancel" && init?.method === "POST") {
      cancelCalls += 1;
      return {
        ok: true,
        json: async () => ({
          client_action_id: "cancel-1",
          status: "completed",
          reason_code: "cancelled",
          order_id: "order-1",
          paper_state: paperState(11, false),
        }),
      } as Response;
    }
    return { ok: false, json: async () => ({}) } as Response;
  }));

  render(<App />);

  await waitFor(() => {
    expect(paperTradingStore.getSnapshot().paperState?.state_revision).toBe(10);
    expect(latestOnLimitCancel).toBeTypeOf("function");
  });

  await act(async () => {
    const result = await latestOnLimitCancel!("order-1");
    expect(result?.status).toBe("completed");
  });

  expect(cancelCalls).toBe(1);
  expect(paperTradingStore.getSnapshot().paperState?.state_revision).toBe(11);
});

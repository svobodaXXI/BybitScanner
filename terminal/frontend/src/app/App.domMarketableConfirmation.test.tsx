import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";

vi.mock("../components/AccountMenu", () => ({ AccountMenu: () => null }));
vi.mock("../components/ChartPanel", () => ({ ChartPanel: () => <div /> }));
vi.mock("../components/TapePanel", () => ({ TapePanel: () => <div /> }));
vi.mock("../components/WorkspaceHeader", () => ({ WorkspaceHeader: () => null }));
vi.mock("../telegram/TelegramMiniAppBridge", () => ({ TelegramMiniAppBridge: () => null }));

vi.mock("../components/ModePanel", () => ({
  ModePanel: ({ onFastLimitHoldChange }: {
    onFastLimitHoldChange: (intent: {
      side: "Buy" | "Sell";
      volumeUsdt: string;
      origin: "chart-fast";
    } | null) => void;
  }) => (
    <button
      type="button"
      onClick={() => onFastLimitHoldChange({
        side: "Buy",
        volumeUsdt: "250",
        origin: "chart-fast",
      })}
    >Arm fast Buy
    </button>
  ),
}));

vi.mock("../components/DomPanel", () => ({
  DomPanel: ({ fastLimitActive, onFastLimitPriceSelect }: {
    fastLimitActive?: boolean;
    onFastLimitPriceSelect?: (price: string) => void;
  }) => (
    <button
      type="button"
      disabled={!fastLimitActive}
      onClick={() => onFastLimitPriceSelect?.("102")}
    >Select marketable ask
    </button>
  ),
}));

vi.mock("../marketData/useMarketData", () => ({
  setMarketSymbol: vi.fn(),
  setMarketTimeframe: vi.fn(),
  useMarketData: () => ({
    book: {
      symbol: "BTCUSDT",
      health: "READY",
      bids: [{ price: 99, size: 1 }],
      asks: [{ price: 101, size: 1 }],
    },
    candles: [],
    trades: [],
    ownOrders: [],
    tickSize: 0.5,
  }),
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

it("executes a marketable DOM selection immediately as MARKET without a confirmation dialog", async () => {
  const fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/instruments") {
      return { ok: true, json: async () => ({ instruments: [{ symbol: "BTCUSDT" }] }) };
    }
    if (url === "/api/workspace/account?symbol=BTCUSDT") {
      return {
        ok: true,
        json: async () => ({
          ok: true,
          account_id: "paper-main",
          provider: "PAPER",
          environment: "PAPER",
          status: "READY",
          session_generation: 1,
          projection_generation: 1,
          read_only: false,
          wallet_balance_usdt: "5000",
          total_equity_usdt: "5000",
          available_balance_usdt: "5000",
          positions: [],
          orders: [],
          paper_state: null,
        }),
      };
    }
    if (url === "/api/paper-state?symbol=BTCUSDT") {
      return {
        ok: true,
        json: async () => ({
          ok: true,
          state_revision: 1,
          account_id: "paper-main",
          symbol: "BTCUSDT",
          initial_deposit_usdt: "5000",
          equity_usdt: "5000",
          one_wv_usdt: "250",
          position_side: "Flat",
          position_quantity: "0",
          average_entry: null,
          engaged_notional_usdt: "0",
          engaged_wv: "0.0",
          active_limit_orders: [],
        }),
      };
    }
    if (url === "/api/market") {
      return {
        ok: true,
        json: async () => ({
          client_action_id: "market-1",
          status: "completed",
          reason_code: "filled",
          reconciliation_required: false,
          paper_state: {
            ok: true,
            state_revision: 2,
            account_id: "paper-main",
            symbol: "BTCUSDT",
            initial_deposit_usdt: "5000",
            equity_usdt: "5000",
            one_wv_usdt: "250",
            position_side: "Long",
            position_quantity: "2.45",
            average_entry: "102",
            engaged_notional_usdt: "250",
            engaged_wv: "1.0",
            active_limit_orders: [],
          },
        }),
      };
    }
    return { ok: false, json: async () => ({}) };
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);

  await waitFor(() => {
    expect(screen.getByRole("button", { name: "Arm fast Buy" })).toBeEnabled();
  });
  fireEvent.click(screen.getByRole("button", { name: "Arm fast Buy" }));
  fireEvent.click(screen.getByRole("button", { name: "Select marketable ask" }));

  await waitFor(() => {
    expect(fetchMock.mock.calls.filter(([url]) => url === "/api/market")).toHaveLength(1);
  });
  expect(screen.queryByRole("dialog", { name: "Confirm marketable DOM order" })).not.toBeInTheDocument();
});

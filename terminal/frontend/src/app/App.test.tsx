import { render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { App } from "./App";

vi.mock("../components/AccountMenu", () => ({ AccountMenu: () => null }));
vi.mock("../components/DomPanel", () => ({ DomPanel: () => null }));
vi.mock("../components/ModePanel", () => ({ ModePanel: () => null }));
vi.mock("../components/TapePanel", () => ({ TapePanel: () => null }));
vi.mock("../components/WorkspaceHeader", () => ({ WorkspaceHeader: () => null }));
vi.mock("../telegram/TelegramMiniAppBridge", () => ({
  TelegramMiniAppBridge: () => null,
}));
vi.mock("../components/ChartPanel", () => ({
  ChartPanel: ({ activeLimitOrders }: { activeLimitOrders: unknown[] }) => (
    <div data-testid="active-limit-count">{activeLimitOrders.length}</div>
  ),
}));
vi.mock("../marketData/useMarketData", () => ({
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

it("removes a fully filled PAPER Limit after authoritative refresh", async () => {
  let requestCount = 0;
  vi.stubGlobal("fetch", vi.fn(async () => {
    requestCount += 1;
    return {
      ok: true,
      json: async () => ({
        ok: true,
        symbol: "BTCUSDT",
        active_limit_orders: requestCount === 1 ? [{ order_id: "limit-1" }] : [],
      }),
    };
  }));

  render(<App />);

  await waitFor(() => {
    expect(screen.getByTestId("active-limit-count")).toHaveTextContent("1");
  });
  await waitFor(() => {
    expect(screen.getByTestId("active-limit-count")).toHaveTextContent("0");
  }, { timeout: 1500 });
});

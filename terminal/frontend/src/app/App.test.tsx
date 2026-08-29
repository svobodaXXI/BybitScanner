import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { expect, it, vi } from "vitest";
import { App } from "./App";

vi.mock("../components/AccountMenu", () => ({ AccountMenu: () => null }));
vi.mock("../components/DomPanel", () => ({
  DomPanel: () => <div data-testid="dom-panel" />,
}));
vi.mock("../components/ModePanel", () => ({ ModePanel: () => null }));
vi.mock("../components/TapePanel", () => ({
  TapePanel: () => <div data-testid="tape-panel" />,
}));
vi.mock("../components/WorkspaceHeader", () => ({ WorkspaceHeader: () => <div data-testid="chart-workspace-controls" /> }));
vi.mock("../telegram/TelegramMiniAppBridge", () => ({
  TelegramMiniAppBridge: () => null,
}));
vi.mock("../components/ChartPanel", () => ({
  ChartPanel: ({ activeLimitOrders, workspaceControls }: { activeLimitOrders: unknown[]; workspaceControls: unknown }) => (
    <div data-testid="chart-region">
      {workspaceControls as ReactNode}
      <span data-testid="active-limit-count">{activeLimitOrders.length}</span>
    </div>
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

it("owns ticker and timeframe inside the chart region without a separate top strip", () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false })));
  render(<App />);
  expect(screen.getByTestId("chart-region")).toContainElement(
    screen.getByTestId("chart-workspace-controls"),
  );
  expect(document.querySelector(".workspace-header")).toBeNull();
});

it("removes a fully filled PAPER Limit after authoritative refresh", async () => {
  let requestCount = 0;
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    if (url === "/api/instruments") {
      return { ok: true, json: async () => ({ instruments: [{ symbol: "BTCUSDT" }] }) };
    }
    requestCount += 1;
    return {
      ok: true,
      json: async () => ({
        ok: true,
        state_revision: requestCount,
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
  }, { timeout: 3000 });
});

it("collapses and restores one DOM plus Smart Tape side panel", () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false })));
  render(<App />);

  const workspaceRow = screen
    .getByRole("button", { name: "Hide DOM and Smart Tape" })
    .closest(".workspace-market-row");
  const sidePanel = screen.getByLabelText("Market depth and tape", {
    selector: "aside",
  });
  expect(workspaceRow).toHaveClass("side-panel-open");
  expect(sidePanel).not.toHaveClass("is-hidden");
  expect(sidePanel.children[0]).toBe(screen.getByTestId("tape-panel"));
  expect(sidePanel.children[1]).toBe(screen.getByTestId("dom-panel"));
  const tapePanel = screen.getByTestId("tape-panel");
  const domPanel = screen.getByTestId("dom-panel");

  fireEvent.click(screen.getByRole("button", { name: "Hide DOM and Smart Tape" }));
  expect(workspaceRow).toHaveClass("side-panel-closed");
  expect(sidePanel).toHaveClass("is-hidden");

  fireEvent.click(screen.getByRole("button", { name: "Show DOM and Smart Tape" }));
  expect(workspaceRow).toHaveClass("side-panel-open");
  expect(sidePanel).not.toHaveClass("is-hidden");
  expect(screen.getByTestId("tape-panel")).toBe(tapePanel);
  expect(screen.getByTestId("dom-panel")).toBe(domPanel);
});

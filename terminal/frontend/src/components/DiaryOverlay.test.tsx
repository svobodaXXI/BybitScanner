import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  afterEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import { DiaryOverlay } from "./DiaryOverlay";

const detail = {
  identity: {
    trade_episode_id: "closed-1",
    symbol: "BTCUSDT",
    side: "LONG" as const,
    environment: "PAPER" as const,
    controller_origin: null,
  },
  decision: {
    controller_origin: null,
    setup_id: null,
    strategy: null,
    decision_reason: null,
  },
  risk: {
    initial_risk: null,
    stop: null,
    take_profit: null,
  },
  orders_executions: [
    {
      execution_id: "exec-1",
      role: "CLOSE",
      quantity: "1",
      fee: "0.1",
      occurred_at_ms: 1_700_003_600_000,
    },
  ],
  management: {
    opening_price: "100",
    average_entry: "101",
    open_quantity: "0",
  },
  outcome: {
    status: "CLOSED" as const,
    realized_price_pnl: "3",
    execution_fees: "0.1",
    net_pnl: null,
    readiness: "CLOSED_INCOMPLETE" as const,
    missing_reasons: ["MISSING_FUNDING"],
  },
  automatic_factors: null,
  notes: null,
};

const response = {
  ok: true,
  active_account_id: "paper",
  session_generation: 1,
  environment: "PAPER" as const,
  trades: [
    {
      trade_episode_id: "closed-1",
      symbol: "BTCUSDT",
      side: "LONG" as const,
      environment: "PAPER" as const,
      controller_origin: null,
      opened_at_ms: 1_700_000_000_000,
      closed_at_ms: 1_700_003_600_000,
      opening_price: "100",
      average_entry: "101",
      exit_price: null,
      open_quantity: "0",
      pnl: null,
      holding_duration_ms: 3_600_000,
      readiness: "CLOSED_INCOMPLETE" as const,
      needs_attention: true,
      missing_reasons: ["MISSING_FUNDING"],
      details: detail,
    },
    {
      trade_episode_id: "open-1",
      symbol: "ETHUSDT",
      side: "SHORT" as const,
      environment: "PAPER" as const,
      controller_origin: null,
      opened_at_ms: 1_700_010_000_000,
      closed_at_ms: null,
      opening_price: "200",
      average_entry: "200",
      exit_price: null,
      open_quantity: "2",
      pnl: null,
      holding_duration_ms: 120_000,
      readiness: "OPEN" as const,
      needs_attention: false,
      missing_reasons: ["TRADE_OPEN"],
      details: {
        ...detail,
        identity: {
          ...detail.identity,
          trade_episode_id: "open-1",
          symbol: "ETHUSDT",
          side: "SHORT" as const,
        },
        outcome: {
          ...detail.outcome,
          status: "OPEN" as const,
          readiness: "OPEN" as const,
          missing_reasons: ["TRADE_OPEN"],
        },
      },
    },
  ],
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DiaryOverlay", () => {
  it("keeps unavailable values missing and filters attention", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => response,
      }),
    );

    render(<DiaryOverlay accountKey="paper:1" onClose={() => {}} />);

    expect(await screen.findByText("BTCUSDT")).toBeTruthy();
    expect(screen.getByText("ETHUSDT")).toBeTruthy();
    expect(screen.getAllByText("PnL —").length).toBe(2);

    fireEvent.click(screen.getByRole("button", { name: "Требуют внимания" }));

    await waitFor(() => {
      expect(screen.getByText("BTCUSDT")).toBeTruthy();
      expect(screen.queryByText("ETHUSDT")).toBeNull();
    });
  });

  it("opens read-only Trade Details from the selected episode", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => response,
      }),
    );

    render(<DiaryOverlay accountKey="paper:1" onClose={() => {}} />);

    fireEvent.click(await screen.findByRole("button", { name: /BTCUSDT/ }));

    expect(screen.getByText("Identity")).toBeTruthy();
    expect(screen.getByText("Decision")).toBeTruthy();
    expect(screen.getByText("Risk")).toBeTruthy();
    expect(screen.getByText("Orders / Executions")).toBeTruthy();
    expect(screen.getByText("Management")).toBeTruthy();
    expect(screen.getByText("Outcome")).toBeTruthy();
    expect(screen.getByText("Automatic factors")).toBeTruthy();
    expect(screen.getByText("Notes / annotations")).toBeTruthy();
    expect(screen.getByText("exec-1")).toBeTruthy();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("refetches after active account authority changes", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => response,
    });
    vi.stubGlobal("fetch", fetchMock);

    const rendered = render(<DiaryOverlay accountKey="paper:1" onClose={() => {}} />);

    await screen.findByText("BTCUSDT");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    rendered.rerender(<DiaryOverlay accountKey="bybit-1:2" onClose={() => {}} />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });
});

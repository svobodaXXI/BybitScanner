import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AutopilotDiaryControls } from "./AutopilotDiaryControls";

const statisticsResponse = {
  ok: true,
  account_id: "paper",
  owner: "ROBOT",
  period: "TODAY",
  period_start_ms: 1_793_000_000_000,
  as_of_ms: 1_793_050_000_000,
  source_revision: 2,
  source: "PAPER_EXECUTIONS_ATTRIBUTED",
  pnl_basis: "REALIZED_PRICE_MINUS_EXECUTION_FEES",
  tickers: [{ symbol: "BTCUSDT", pnl_usdt: "12.5", trade_count: 1 }],
};

const linkedTrade = {
  trade_episode_id: "trade-robot-1",
  symbol: "BTCUSDT",
  side: "LONG" as const,
  environment: "PAPER" as const,
  controller_origin: "ROBOT",
  opened_at_ms: 1_700_000_000_000,
  closed_at_ms: null,
  opening_price: "100",
  average_entry: "101",
  exit_price: null,
  open_quantity: "1",
  pnl: null,
  holding_duration_ms: 120_000,
  readiness: "OPEN" as const,
  needs_attention: false,
  missing_reasons: ["TRADE_OPEN"],
  details: {
    identity: {
      trade_episode_id: "trade-robot-1",
      symbol: "BTCUSDT",
      side: "LONG" as const,
      environment: "PAPER" as const,
      controller_origin: "ROBOT",
    },
    decision: {
      controller_origin: "ROBOT",
      setup_id: "setup-1",
      strategy: "robot-v0.1",
      decision_reason: "APPROVED",
    },
    risk: {
      initial_risk: "2",
      stop: "98",
      take_profit: "103",
    },
    orders_executions: [],
    management: {
      opening_price: "100",
      average_entry: "101",
      open_quantity: "1",
    },
    outcome: {
      status: "OPEN" as const,
      realized_price_pnl: "0",
      execution_fees: "0",
      net_pnl: null,
      readiness: "OPEN" as const,
      missing_reasons: ["TRADE_OPEN"],
    },
    automatic_factors: null,
    notes: null,
  },
};

const tradesResponse = {
  ok: true,
  active_account_id: "paper",
  session_generation: 1,
  environment: "PAPER",
  trades: [linkedTrade],
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AutopilotDiaryControls", () => {
  it("keeps trade details disabled when no explicit Diary episode link exists", () => {
    render(<AutopilotDiaryControls accountKey="paper:1" />);

    expect(screen.getByRole("button", { name: "Статистика" })).toBeEnabled();
    const details = screen.getByRole("button", { name: "Подробности сделки" });
    expect(details).toBeDisabled();
    expect(details).toHaveAttribute("title", "Нет связи с эпизодом сделки");
  });

  it("opens shared Diary statistics directly without loading the trades list first", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(statisticsResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    render(<AutopilotDiaryControls accountKey="paper:1" />);
    fireEvent.click(screen.getByRole("button", { name: "Статистика" }));

    await screen.findByText("BTCUSDT");
    expect(screen.getByText("+12.5 USDT")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=TODAY");
  });

  it("opens only the explicitly linked trade episode", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(tradesResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    render(
      <AutopilotDiaryControls
        accountKey="paper:1"
        tradeEpisodeId="trade-robot-1"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Подробности сделки" }));

    await screen.findByText("Идентификация");
    expect(screen.getByText("trade-robot-1")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/diary/trades");
  });

  it("fails closed when an explicit trade episode is absent from the Diary response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ...tradesResponse, trades: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    render(
      <AutopilotDiaryControls
        accountKey="paper:1"
        tradeEpisodeId="trade-missing"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Подробности сделки" }));

    await waitFor(() => {
      expect(screen.getByText("Сделка недоступна в текущем дневнике")).toBeInTheDocument();
    });
    expect(screen.queryByText("trade-robot-1")).not.toBeInTheDocument();
  });
});

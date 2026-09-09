import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AutopilotDiaryControls } from "./AutopilotDiaryControls";

const statisticsResponse = {
  ok: true,
  active_account_id: "paper",
  session_generation: 1,
  environment: "PAPER",
  statistics: {
    sample: {
      total: 1,
      eligible_closed_ready: 0,
      excluded_open: 1,
      excluded_incomplete: 0,
    },
    pnl: {
      net_pnl: null,
      average_net_pnl: null,
      wins: 0,
      losses: 0,
      breakeven: 0,
      win_rate: null,
      average_win: null,
      average_loss: null,
      payoff_ratio: null,
      profit_factor: null,
    },
    holding: { average_duration_ms: null },
    coverage: {
      pnl_ready_ratio: "0",
      post_trade_factors: {
        "trade.mae_pct": { eligible_closed: 0, observed: 0, coverage_ratio: "0" },
        "trade.mfe_pct": { eligible_closed: 0, observed: 0, coverage_ratio: "0" },
        "trade.exit_capture_ratio": { eligible_closed: 0, observed: 0, coverage_ratio: "0" },
      },
    },
  },
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

    await screen.findByText("Выборка");
    expect(screen.getByText("Результативность")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/diary/statistics");
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

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

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

const tradesResponse = {
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

const setupsResponse = {
  ok: true,
  source: "TRADING_DIARY_D2" as const,
  setups: [
    {
      setup_instance_id: "setup-1",
      setup_id: "falling-wedge",
      symbol: "BTCUSDT",
      timeframe: "1m",
      pattern: "Falling Wedge",
      direction: "LONG" as const,
      strategy_version: "strategy-v1",
      hypothesis_id: null,
      entry_mode: "breakout_retest",
      origin: "ROBOT",
      created_at_ms: 1_700_000_000_000,
      status: "ADMITTED",
      decision_state: null,
      reason_code: null,
      controller: null,
      latest_decision_at_ms: null,
      trade_episode_ids: [],
      needs_attention: true,
      missing_evidence: ["MISSING_DECISION_EVENTS"],
    },
  ],
};

function installFetchMock() {
  const fetchMock = vi.fn().mockImplementation(async (url: string) => ({
    ok: true,
    json: async () => url.includes("/api/diary/setups") ? setupsResponse : tradesResponse,
  }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DiaryOverlay", () => {
  it("keeps unavailable values missing and filters attention", async () => {
    installFetchMock();
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

  it("opens read-only trade details with Russian UI labels", async () => {
    installFetchMock();
    render(<DiaryOverlay accountKey="paper:1" onClose={() => {}} />);

    fireEvent.click(await screen.findByRole("button", { name: /BTCUSDT/ }));

    expect(screen.getByText("Идентификация")).toBeTruthy();
    expect(screen.getByText("Решение")).toBeTruthy();
    expect(screen.getByText("Риск")).toBeTruthy();
    expect(screen.getByText("Ордера / исполнения")).toBeTruthy();
    expect(screen.getByText("Ведение")).toBeTruthy();
    expect(screen.getByText("Результат")).toBeTruthy();
    expect(screen.getByText("Автоматические факторы")).toBeTruthy();
    expect(screen.getByText("Заметки / аннотации")).toBeTruthy();
    expect(screen.getByText("exec-1")).toBeTruthy();
  });

  it("opens Setups as Сетапы and exposes attention evidence read-only", async () => {
    const fetchMock = installFetchMock();
    render(<DiaryOverlay accountKey="paper:1" onClose={() => {}} />);

    await screen.findByText("BTCUSDT");
    fireEvent.click(screen.getByRole("button", { name: "Сетапы" }));

    expect(await screen.findByText("Режим входа breakout_retest")).toBeTruthy();
    expect(screen.getByText("Не хватает данных: MISSING_DECISION_EVENTS")).toBeTruthy();
    expect(screen.getByText("ЛОНГ")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith("/api/diary/setups");
  });

  it("refetches after active account authority changes", async () => {
    const fetchMock = installFetchMock();
    const rendered = render(<DiaryOverlay accountKey="paper:1" onClose={() => {}} />);

    await screen.findByText("BTCUSDT");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    rendered.rerender(<DiaryOverlay accountKey="bybit-1:2" onClose={() => {}} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });
});

import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AutopilotFirstScreen } from "./AutopilotFirstScreen";

const NOW = Date.UTC(2026, 9, 19, 12, 0, 0);
const DAY_START = Date.UTC(2026, 9, 18, 21, 0, 0);

type Routes = Record<string, unknown>;

function position(symbol: string, side: "Long" | "Short", pnl: string | null) {
  return {
    symbol,
    position_side: side,
    position_quantity: "100",
    average_entry: "0.2",
    engaged_notional_usdt: "20",
    engaged_wv: "0.08",
    current_price: pnl === null ? null : "0.21",
    unrealized_pnl: pnl,
    tick_size: "0.0001",
  };
}

function paperState(symbol: string, stop: string | null, take: string | null) {
  return {
    ok: true,
    symbol,
    protection: {
      status: "confirmed_active",
      stop_loss: stop,
      take_profit: take,
      trailing_stop: null,
      pending_command_id: null,
      warning: null,
      effective_quantity: "100",
    },
  };
}

const healthyRoutes: Routes = {
  "/api/robot/autopilot": {
    ok: true,
    mode: "PAPER_AUTO",
    reason: "owner",
    version: 27,
  },
  "/api/health": {
    ok: true,
    robot_admission_ready: true,
    paper_live_safe: true,
  },
  "/api/robot/protection-health": {
    ok: true,
    healthy: true,
    unhealthy_symbols: {},
  },
  "/api/diary/trades": {
    ok: true,
    active_account_id: "paper",
    session_generation: 1,
    trades: [
      {
        symbol: "OLDUSDT",
        closed_at_ms: DAY_START + 10,
        pnl: "2.5",
        readiness: "CLOSED_READY",
      },
      {
        symbol: "LSKUSDT",
        trade_episode_id: "episode-lsk",
        closed_at_ms: null,
        pnl: null,
        readiness: "OPEN",
        details: { decision: { decision_reason: "Falling Wedge retest" } },
      },
    ],
  },
  "/api/open-positions": {
    ok: true,
    account_id: "paper",
    positions: [
      position("LSKUSDT", "Long", "1"),
      position("NIGHTUSDT", "Short", null),
    ],
  },
  "/api/paper-state?symbol=LSKUSDT": paperState("LSKUSDT", "0.19", "0.23"),
  "/api/paper-state?symbol=NIGHTUSDT": paperState("NIGHTUSDT", null, "0.18"),
};

function mockFetch(routes: Routes | "offline" | "pending") {
  const fetchMock = vi.fn((url: string) => {
    if (routes === "pending") return new Promise<Response>(() => {});
    if (routes === "offline")
      return Promise.reject(new TypeError("Failed to fetch"));
    const body = routes[url];
    if (body === undefined)
      return Promise.resolve(new Response("", { status: 503 }));
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Autopilot compact first screen", () => {
  it("shows only the day result and trade count, without unrelated status labels", async () => {
    mockFetch(healthyRoutes);
    render(<AutopilotFirstScreen now={() => NOW} />);
    expect(await screen.findByText("+2.50 USDT")).toBeInTheDocument();
    expect(screen.getByText("PnL за день")).toBeInTheDocument();
    expect(screen.getByText("Сделок за день")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.queryByText("Блок серии STOP")).not.toBeInTheDocument();
    expect(screen.queryByText("PAPER_AUTO")).not.toBeInTheDocument();
    expect(screen.queryByText("Что робот сейчас делает")).not.toBeInTheDocument();
  });

  it("uses accessible icon-only controls in the requested order", async () => {
    mockFetch(healthyRoutes);
    const onTradeDetails = vi.fn();
    const onOpenPositions = vi.fn();
    const onStatistics = vi.fn();
    const onTerminal = vi.fn();
    render(<AutopilotFirstScreen
      now={() => NOW}
      onTradeDetails={onTradeDetails}
      onOpenPositions={onOpenPositions}
      onStatistics={onStatistics}
      onTerminal={onTerminal}
      accountControl={<button type="button" aria-label="Счёт">key</button>}
    />);
    await screen.findByText("+2.50 USDT");
    const nav = screen.getByRole("navigation", { name: "Панель управления Автопилотом" });
    const buttons = within(nav).getAllByRole("button");
    expect(buttons.map((button) => button.getAttribute("aria-label"))).toEqual([
      "Подробности сделки", "Все открытые позиции", "Статистика", "Терминал", "Счёт",
    ]);
    expect(buttons[0]).toBeDisabled(); // Multiple open positions: no ambiguous trade selection.
    fireEvent.click(buttons[1]);
    fireEvent.click(buttons[2]);
    fireEvent.click(buttons[3]);
    expect(onOpenPositions).toHaveBeenCalledOnce();
    expect(onStatistics).toHaveBeenCalledOnce();
    expect(onTerminal).toHaveBeenCalledOnce();
    expect(onTradeDetails).not.toHaveBeenCalled();
  });

  it("never invents a financial result when a closed trade lacks PnL", async () => {
    mockFetch({
      ...healthyRoutes,
      "/api/diary/trades": {
        ok: true,
        active_account_id: "paper",
        session_generation: 1,
        trades: [{ symbol: "X", closed_at_ms: DAY_START + 1, pnl: null, readiness: "CLOSED_INCOMPLETE" }],
      },
    });
    render(<AutopilotFirstScreen now={() => NOW} accountKey="paper:1" />);
    expect(await screen.findByText("Нет данных: 1 из 1 сделок без PnL")).toBeInTheDocument();
  });

  it("shows backend failures without a fabricated zero result", async () => {
    mockFetch("offline");
    render(<AutopilotFirstScreen now={() => NOW} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("PAPER backend недоступен");
    expect(screen.queryByText("+0.00 USDT")).not.toBeInTheDocument();
  });

  it("uses read-only requests", async () => {
    const fetchMock = mockFetch(healthyRoutes);
    render(<AutopilotFirstScreen now={() => NOW} />);
    await screen.findByText("+2.50 USDT");
    for (const call of fetchMock.mock.calls as unknown as [string, RequestInit?][]) {
      expect(call[1]?.method ?? "GET").toBe("GET");
    }
  });
});

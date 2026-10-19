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
    trades: [
      {
        symbol: "OLDUSDT",
        closed_at_ms: DAY_START + 10,
        pnl: "2.5",
        readiness: "CLOSED_READY",
      },
      {
        symbol: "LSKUSDT",
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

describe("AutopilotFirstScreen (UI-1)", () => {
  it("shows an explicit loading state before data arrives", () => {
    mockFetch("pending");
    render(<AutopilotFirstScreen now={() => NOW} />);

    expect(screen.getAllByText("Загрузка…").length).toBeGreaterThan(0);
  });

  it("renders the summary and every open position with its own STOP and TAKE", async () => {
    mockFetch(healthyRoutes);
    render(<AutopilotFirstScreen now={() => NOW} />);

    expect(await screen.findByText("PAPER_AUTO")).toBeInTheDocument();
    expect(screen.getByText("+2.50 USDT")).toBeInTheDocument();
    expect(screen.getByText("Открыт")).toBeInTheDocument();
    expect(screen.getByText("HEALTHY")).toBeInTheDocument();

    const lsk = await screen.findByRole("article", { name: "Сделка LSKUSDT" });
    expect(within(lsk).getByText("LONG")).toBeInTheDocument();
    expect(await within(lsk).findByText("0.1900")).toBeInTheDocument();
    expect(within(lsk).getByText("0.2300")).toBeInTheDocument();
    expect(within(lsk).getByText("Falling Wedge retest")).toBeInTheDocument();

    const night = screen.getByRole("article", { name: "Сделка NIGHTUSDT" });
    expect(within(night).getByText("SHORT")).toBeInTheDocument();
    expect(await within(night).findByText("Не установлен")).toBeInTheDocument();
    expect(within(night).getByText("Нет текущей цены")).toBeInTheDocument();
  });

  it("marks sources the backend does not publish instead of inventing values", async () => {
    mockFetch(healthyRoutes);
    render(<AutopilotFirstScreen now={() => NOW} />);

    await screen.findByText("PAPER_AUTO");
    // STOP series, daily drawdown, STOP level, Robot state + per-card holding reason.
    expect(
      screen.getAllByText("Нет источника данных").length,
    ).toBeGreaterThanOrEqual(6);
  });

  it("refuses a day PnL when a closed trade of the day has no PnL", async () => {
    mockFetch({
      ...healthyRoutes,
      "/api/diary/trades": {
        ok: true,
        trades: [
          {
            symbol: "X",
            closed_at_ms: DAY_START + 1,
            pnl: null,
            readiness: "CLOSED_INCOMPLETE",
          },
        ],
      },
    });
    render(<AutopilotFirstScreen now={() => NOW} />);

    expect(
      await screen.findByText("Нет данных: 1 из 1 сделок без PnL"),
    ).toBeInTheDocument();
  });

  it("distinguishes no positions from unavailable positions", async () => {
    mockFetch({
      ...healthyRoutes,
      "/api/open-positions": { ok: true, account_id: "paper", positions: [] },
    });
    const { unmount } = render(<AutopilotFirstScreen now={() => NOW} />);
    expect(await screen.findByText("Нет открытых позиций")).toBeInTheDocument();
    unmount();

    const { "/api/open-positions": _omitted, ...withoutPositions } =
      healthyRoutes;
    mockFetch(withoutPositions);
    render(<AutopilotFirstScreen now={() => NOW} />);
    const positions = screen.getByLabelText("Открытые позиции");
    expect(
      await within(positions).findByText("Данные недоступны"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Нет открытых позиций")).not.toBeInTheDocument();
  });

  it("reports an offline backend without offering any control", async () => {
    mockFetch("offline");
    render(<AutopilotFirstScreen now={() => NOW} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "PAPER backend недоступен",
    );
    expect(
      screen.getAllByRole("button").map((button) => button.textContent),
    ).toEqual(["Обновить"]);
  });

  it("opens trade-specific read-only details and closes without mutations", async () => {
    const fetchMock = mockFetch(healthyRoutes);
    render(<AutopilotFirstScreen now={() => NOW} />);
    const lsk = await screen.findByRole("article", { name: "Сделка LSKUSDT" });
    fireEvent.click(within(lsk).getByRole("button", { name: "Подробности сделки" }));
    const details = screen.getByRole("dialog", { name: "Подробности сделки LSKUSDT" });
    expect(within(details).getByText("Falling Wedge retest")).toBeInTheDocument();
    expect(within(details).getByRole("button", { name: "Закрыть подробности" })).toHaveFocus();
    expect(within(details).getByText("Причина удержания")).toBeInTheDocument();
    expect(within(details).getAllByText("Нет источника данных").length).toBeGreaterThan(0);
    fireEvent.click(within(details).getByRole("button", { name: "Закрыть подробности" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    for (const call of fetchMock.mock.calls as unknown as [string, RequestInit?][]) {
      expect(call[1]?.method ?? "GET").toBe("GET");
    }
  });

  it("closes details on Escape and returns focus to the originating trade", async () => {
    mockFetch(healthyRoutes);
    render(<AutopilotFirstScreen now={() => NOW} />);
    const lsk = await screen.findByRole("article", { name: "Сделка LSKUSDT" });
    const trigger = within(lsk).getByRole("button", { name: "Подробности сделки" });
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog", { name: "Подробности сделки LSKUSDT" })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("issues only GET requests", async () => {
    const fetchMock = mockFetch(healthyRoutes);
    render(<AutopilotFirstScreen now={() => NOW} />);
    await screen.findByRole("article", { name: "Сделка NIGHTUSDT" });

    for (const call of fetchMock.mock.calls as unknown as [
      string,
      RequestInit?,
    ][]) {
      expect(call[1]?.method ?? "GET").toBe("GET");
    }
  });
});

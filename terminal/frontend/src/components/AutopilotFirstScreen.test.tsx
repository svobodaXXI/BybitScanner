import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  "/api/robot/day-summary": {
    ok: true,
    source: "robot_trades",
    account_id: "paper",
    day_start_ms: DAY_START,
    closed_trades: 1,
    trades_without_pnl: 0,
    net_pnl_usdt: "2.50",
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
        controller_origin: "ROBOT",
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
  const fetchMock = vi.fn((url: string, _options?: RequestInit) => {
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
  vi.restoreAllMocks();
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

  it("reuses the Terminal's PAPER position visual fields without trading buttons", async () => {
    mockFetch(healthyRoutes);
    const verifiedPosition = { ...position("LSKUSDT", "Long", "1"), robot_trade_id: "robot-lsk" };
    render(<AutopilotFirstScreen now={() => NOW}
      verifiedPosition={verifiedPosition} oneWorkingVolumeUsdt="250" />);
    const panel = screen.getByLabelText("Позиция робота на панели управления");
    expect(within(panel).getByLabelText("Engaged working volume")).toHaveTextContent("⚔️ 0.1");
    expect(within(panel).getByTitle("1 РО = 250 USDT")).toBeInTheDocument();
    expect(within(panel).getByText("20")).toBeInTheDocument();
    expect(within(panel).getByText("USDT")).toBeInTheDocument();
    expect(within(panel).getByText("LSKUSDT")).toBeInTheDocument();
    expect(within(panel).getByText("0.20000")).toBeInTheDocument();
    expect(within(panel).getByText("+5.00%")).toBeInTheDocument();
    expect(within(panel).getByText("+1.00 USDT")).toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: /Закрыть|Market|Limit/ })).not.toBeInTheDocument();
  });

  it("shows the exact verified signal context above the day totals", async () => {
    mockFetch(healthyRoutes);
    const verifiedPosition = { ...position("LSKUSDT", "Long", "1"), robot_trade_id: "robot-lsk" };
    render(<AutopilotFirstScreen verifiedPosition={verifiedPosition} verifiedOrigin={{
      pattern: "Falling Wedge", candidate_id: "candidate-lsk",
      signal_timeframe_minutes: 5, mirror_campaign: false,
      mirror_level_source: null, mirror_pattern: null, reentry_attempt_index: 2,
    }} />);
    const provenance = screen.getByLabelText("Происхождение выбранной сделки");
    expect(provenance).toHaveTextContent("Falling Wedge");
    expect(provenance).toHaveTextContent("Сигнал робота");
    expect(provenance).toHaveTextContent("5м");
    expect(provenance).toHaveTextContent("№2");
    expect(provenance).toHaveTextContent("candidate-lsk");
    const root = screen.getByRole("region", { name: "Автопилот: первый экран" });
    const summary = screen.getByLabelText("Сводка дня");
    expect(root.compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_CONTAINED_BY).toBeTruthy();
    expect(summary.compareDocumentPosition(provenance) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
    expect(await screen.findByText("+2.50 USDT")).toBeInTheDocument();
  });

  it("does not attribute an unverified position to the Robot", async () => {
    mockFetch(healthyRoutes);
    render(<AutopilotFirstScreen now={() => NOW} />);
    const panel = screen.getByLabelText("Позиция робота на панели управления");
    expect(within(panel).getByText("⚔️ —")).toBeInTheDocument();
    expect(within(panel).queryByText("LSKUSDT")).not.toBeInTheDocument();
    expect(within(panel).queryByText(/PnL/)).not.toBeInTheDocument();
  });

  it("uses accessible icon-only controls in the requested order", async () => {
    mockFetch(healthyRoutes);
    const onTradeDetails = vi.fn();
    const onOpenPositions = vi.fn();
    const onStatistics = vi.fn();
    const onTerminal = vi.fn();
    const onRobotControls = vi.fn();
    render(<AutopilotFirstScreen
      now={() => NOW}
      onTradeDetails={onTradeDetails}
      onOpenPositions={onOpenPositions}
      onStatistics={onStatistics}
      onTerminal={onTerminal}
      onRobotControls={onRobotControls}
      accountControl={<button type="button" aria-label="Счёт">key</button>}
    />);
    await screen.findByText("+2.50 USDT");
    const nav = screen.getByRole("navigation", { name: "Панель управления Автопилотом" });
    const buttons = within(nav).getAllByRole("button");
    expect(buttons.map((button) => button.getAttribute("aria-label"))).toEqual([
      "Подробности сделки", "Все открытые позиции", "Статистика", "Терминал", "Управление роботом", "Счёт",
    ]);
    expect(buttons[0]).toBeDisabled(); // Multiple open positions: no ambiguous trade selection.
    // Icons are three separate thin strokes/bars, not dense Unicode glyphs.
    expect(buttons[0].querySelector("svg")).not.toBeNull();
    expect(buttons[1].querySelectorAll("svg line")).toHaveLength(3);
    expect(buttons[2].querySelectorAll("svg rect")).toHaveLength(3);
    expect(buttons[2].textContent).toBe("");
    expect(buttons[4].querySelector("svg")).not.toBeNull();
    fireEvent.click(buttons[1]);
    fireEvent.click(buttons[2]);
    fireEvent.click(buttons[3]);
    fireEvent.click(buttons[4]);
    expect(onOpenPositions).toHaveBeenCalledOnce();
    expect(onStatistics).toHaveBeenCalledOnce();
    expect(onTerminal).toHaveBeenCalledOnce();
    expect(onRobotControls).toHaveBeenCalledOnce();
    expect(onTradeDetails).not.toHaveBeenCalled();
  });

  it("never invents a financial result when a closed trade lacks PnL", async () => {
    mockFetch({
      ...healthyRoutes,
      "/api/robot/day-summary": {
        ok: true,
        source: "robot_trades",
        account_id: "paper",
        day_start_ms: DAY_START,
        closed_trades: 1,
        trades_without_pnl: 1,
        net_pnl_usdt: null,
      },
    });
    render(<AutopilotFirstScreen now={() => NOW} accountKey="paper:1" />);
    expect(await screen.findByText("Нет данных: 1 из 1 сделок без полного PnL")).toBeInTheDocument();
  });

  it("takes Robot PnL from robot_trades, not unrelated manual Diary trades", async () => {
    mockFetch({
      ...healthyRoutes,
      "/api/diary/trades": {
        ok: true,
        active_account_id: "paper",
        session_generation: 1,
        trades: [
          { symbol: "UNKNOWN", closed_at_ms: DAY_START + 1, pnl: "100", controller_origin: null, readiness: "CLOSED_READY" },
          { symbol: "MANUAL", closed_at_ms: DAY_START + 2, pnl: "200", controller_origin: "TERMINAL", readiness: "CLOSED_READY" },
        ],
      },
    });
    render(<AutopilotFirstScreen now={() => NOW} accountKey="paper:1" />);
    expect(await screen.findByText("+2.50 USDT")).toBeInTheDocument();
    expect(screen.queryByText("+300.00 USDT")).not.toBeInTheDocument();
  });

  it("rejects an untrusted Robot daily summary instead of showing a false zero", async () => {
    mockFetch({
      ...healthyRoutes,
      "/api/robot/day-summary": {
        ok: true,
        source: "robot_trades",
        account_id: "other-paper",
        day_start_ms: DAY_START,
        closed_trades: 0,
        trades_without_pnl: 0,
        net_pnl_usdt: "0",
      },
    });
    render(<AutopilotFirstScreen now={() => NOW} />);
    expect(await screen.findAllByText("Данные недоступны")).toHaveLength(2);
    expect(screen.queryByText("+0.00 USDT")).not.toBeInTheDocument();
  });

  it("shows backend failures without a fabricated zero result", async () => {
    mockFetch("offline");
    render(<AutopilotFirstScreen now={() => NOW} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("PAPER backend недоступен");
    expect(screen.queryByText("+0.00 USDT")).not.toBeInTheDocument();
  });

  it("refreshes one shared Robot inventory without re-fetching trading/diary state", async () => {
    const initial = [{ ...position("LSKUSDT", "Long", "1"), robot_trade_id: "robot-lsk" }];
    const updated = [{ ...position("LSKUSDT", "Long", "3"), robot_trade_id: "robot-lsk" },
      { ...position("NIGHTUSDT", "Short", "2"), robot_trade_id: "robot-night" }];
    const routes: Routes = {
      ...healthyRoutes,
      "/api/open-positions": { ok: true, account_id: "paper", positions: initial },
    };
    const intervals: Array<() => void> = [];
    vi.spyOn(window, "setInterval").mockImplementation((fn) => {
      intervals.push(fn as () => void);
      return 17;
    });
    vi.spyOn(window, "clearInterval").mockImplementation(() => {});
    const fetchMock = mockFetch(routes);
    const onPositionsLoaded = vi.fn();
    const view = render(<AutopilotFirstScreen onPositionsLoaded={onPositionsLoaded} />);

    await waitFor(() => expect(onPositionsLoaded).toHaveBeenCalledWith(initial));
    expect(intervals).toHaveLength(1);
    routes["/api/open-positions"] = { ok: true, account_id: "paper", positions: updated };
    act(() => { intervals[0](); });
    await waitFor(() => expect(onPositionsLoaded).toHaveBeenCalledWith(updated));

    const called = (url: string) => fetchMock.mock.calls.filter(([path]) => path === url);
    expect(called("/api/open-positions")).toHaveLength(2);
    expect(called("/api/robot/day-summary")).toHaveLength(1);
    expect(called("/api/diary/trades")).toHaveLength(1);
    expect(called("/api/robot/autopilot")).toHaveLength(1);
    expect(fetchMock.mock.calls.every(([,options]) =>
      !options || (typeof options === "object" && !("method" in options)))).toBe(true);
    view.unmount();
  });

  it("prevents overlapping inventory loads and invalidates in-flight results on unmount", async () => {
    let resolveInventory: ((response: Response) => void) | null = null;
    const pending = new Promise<Response>((resolve) => { resolveInventory = resolve; });
    const intervals: Array<() => void> = [];
    vi.spyOn(window, "setInterval").mockImplementation((fn) => {
      intervals.push(fn as () => void);
      return 18;
    });
    vi.spyOn(window, "clearInterval").mockImplementation(() => {});
    const fetchMock = vi.fn((url: string, _options?: RequestInit) =>
      url === "/api/open-positions" ? pending
        : Promise.resolve(new Response(JSON.stringify(healthyRoutes[url]), { status: 200 })));
    vi.stubGlobal("fetch", fetchMock);
    const onPositionsLoaded = vi.fn();
    const view = render(<AutopilotFirstScreen onPositionsLoaded={onPositionsLoaded} />);
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => url === "/api/open-positions")).toBe(true));
    expect(intervals).toHaveLength(1);
    act(() => { intervals[0](); intervals[0](); });
    expect(fetchMock.mock.calls.filter(([url]) => url === "/api/open-positions")).toHaveLength(1);
    const signal = fetchMock.mock.calls.find(([url]) => url === "/api/open-positions")?.[1]?.signal;
    view.unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () => {
      resolveInventory?.(new Response(JSON.stringify({ ok: true, positions: [
        { ...position("LSKUSDT", "Long", "1"), robot_trade_id: "robot-lsk" },
      ] }), { status: 200 }));
      await Promise.resolve();
    });
    expect(onPositionsLoaded).not.toHaveBeenCalledWith(expect.any(Array));
    expect(onPositionsLoaded).toHaveBeenCalledWith(null);
  });

  it("clears previously observed Robot inventory when the live read fails", async () => {
    const initial = [{ ...position("LSKUSDT", "Long", "1"), robot_trade_id: "robot-lsk" }];
    const routes: Routes = {
      ...healthyRoutes,
      "/api/open-positions": { ok: true, account_id: "paper", positions: initial },
    };
    const intervals: Array<() => void> = [];
    vi.spyOn(window, "setInterval").mockImplementation((fn) => {
      intervals.push(fn as () => void);
      return 19;
    });
    vi.spyOn(window, "clearInterval").mockImplementation(() => {});
    mockFetch(routes);
    const onPositionsLoaded = vi.fn();
    render(<AutopilotFirstScreen onPositionsLoaded={onPositionsLoaded} />);
    await waitFor(() => expect(onPositionsLoaded).toHaveBeenCalledWith(initial));
    delete routes["/api/open-positions"];
    act(() => { intervals[0](); });
    await waitFor(() => expect(onPositionsLoaded).toHaveBeenLastCalledWith(null));
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

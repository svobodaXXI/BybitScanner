import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DiaryOverlay, displayTradePnl } from "./DiaryOverlay";

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

const statisticsResponse = {
  ok: true,
  account_id: "paper",
  owner: "MANUAL" as const,
  source_revision: 2,
  statistics: {
    sample: {
      total: 2,
      eligible_closed_ready: 0,
      excluded_open: 1,
      excluded_incomplete: 1,
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
    holding: {
      average_duration_ms: null,
    },
    coverage: {
      pnl_ready_ratio: "0",
      post_trade_factors: {
        "trade.mae_pct": { eligible_closed: 1, observed: 1, coverage_ratio: "1" },
        "trade.mfe_pct": { eligible_closed: 1, observed: 1, coverage_ratio: "1" },
        "trade.exit_capture_ratio": { eligible_closed: 1, observed: 0, coverage_ratio: "0" },
      },
    },
  },
};

const mirrorResponse = {
  ok: true,
  paper_admission: "NOT_AUTHORIZED",
  paper_blockers: ["standalone_mirror_trading_rules_not_owner_accepted"],
  counts: { BROKEN_UNTESTED: 1 },
  levels: [
    {
      symbol: "KNCUSDT",
      timeframe: "5",
      level_id: "lvl-1",
      status: "BROKEN_UNTESTED",
      lifecycle: "TRACKING",
      candidate: true,
      freshness: "FRESH",
      rejection_reason: null,
      breakout: { direction: "DOWN", campaign_direction: "LONG", open_time_ms: 1792843800000, open: 0.12299, close: 0.12228 },
      breakout_evidence: { kind: "FULL_BODY", body_atr: 2.21 },
      level_label: "Broadening lower",
      level_geometry_text: "наклонная A1 2026-10-24 05:20 UTC 0.12433 → A2 2026-10-24 09:00 UTC 0.1237",
      first_retest_text: "ещё не было (уровень свежий)",
      imbalance_text: "нет (на допуск не влияет)",
      sources_text: "Broadening",
      parent_patterns: [{ pattern: "Broadening", formation_id: "horn:KNCUSDT:5:1" }],
      robot: {
        mode: "OBSERVE_ONLY",
        risk_reason: "robot_execution_not_authorized",
        paper_admission: "NOT_AUTHORIZED",
        paper_blockers: ["standalone_mirror_trading_rules_not_owner_accepted"],
      },
    },
  ],
};

function installFetchMock() {
  const fetchMock = vi.fn().mockImplementation(async (url: string) => ({
    ok: true,
    json: async () => {
      if (url.includes("/api/diary/setups")) return setupsResponse;
      if (url.includes("/api/diary/scoped-statistics?")) return statisticsResponse;
      if (url.includes("/api/scanner/mirror-levels")) return mirrorResponse;
      return tradesResponse;
    },
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
    render(<DiaryOverlay accountKey="paper:1" initialSection="SETUPS" onClose={() => {}} />);

    expect(await screen.findByText("Режим входа breakout_retest")).toBeTruthy();
    expect(screen.getByText("Не хватает данных: MISSING_DECISION_EVENTS")).toBeTruthy();
    expect(screen.getByText("ЛОНГ")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith("/api/diary/setups");
  });

  it("opens D6.4 statistics read-only and keeps unavailable metrics missing", async () => {
    const fetchMock = installFetchMock();
    render(<DiaryOverlay accountKey="paper:1" initialSection="STATISTICS" statisticsScope={{ accountId: "paper", owner: "MANUAL" }} onClose={() => {}} />);

    expect(await screen.findByText("Выборка")).toBeTruthy();
    expect(screen.getByText("Результативность")).toBeTruthy();
    expect(screen.getByText("Удержание позиции")).toBeTruthy();
    expect(screen.getByText("Полнота данных")).toBeTruthy();
    expect(screen.getByText("Готовы для чистого PnL")).toBeTruthy();
    expect(screen.getByText("Покрытие MAE")).toBeTruthy();
    expect(screen.getAllByText("1/1 (100%)")).toHaveLength(2);
    expect(screen.getByText("0/1 (0%)")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith("/api/diary/scoped-statistics?account_id=paper&owner=MANUAL");
  });

  it("shows Scanner MIRROR levels read-only with geometry, retest and PAPER status", async () => {
    const fetchMock = installFetchMock();
    render(<DiaryOverlay accountKey="paper:1" initialSection="MIRROR" onClose={() => {}} />);

    expect(await screen.findByText("KNCUSDT")).toBeTruthy();
    expect(screen.getByText("КАНДИДАТ")).toBeTruthy();
    expect(screen.getByText(/Уровень Broadening lower: наклонная A1/)).toBeTruthy();
    expect(screen.getByText("Ретест: ещё не было (уровень свежий)")).toBeTruthy();
    expect(screen.getByText(/PAPER NOT_AUTHORIZED/)).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith("/api/scanner/mirror-levels");
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


describe("scoped statistics fail-closed UX", () => {
  it("never uses global statistics when no authoritative account/owner scope exists", async () => {
    const fetchMock = installFetchMock();
    render(<DiaryOverlay accountKey="unknown:0" initialSection="STATISTICS" onClose={() => {}} />);
    await screen.findByText("Не удалось загрузить статистику выбранного счёта");
    expect(fetchMock).not.toHaveBeenCalledWith("/api/diary/statistics");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects a report from another account or controller", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ ...statisticsResponse, owner: "ROBOT" }), { status: 200 },
    ));
    vi.stubGlobal("fetch", fetchMock);
    render(<DiaryOverlay accountKey="paper:1" initialSection="STATISTICS"
      statisticsScope={{ accountId: "paper", owner: "MANUAL" }} onClose={() => {}} />);
    await screen.findByText("Не удалось загрузить статистику выбранного счёта");
    expect(screen.queryByText("Результативность")).not.toBeInTheDocument();
  });

  it("does not publish a stale report after switching the requested account", async () => {
    const pending: { resolve?: (response: Response) => void } = {};
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.includes("account_id=paper")) {
        return new Promise<Response>((resolve) => { pending.resolve = resolve; });
      }
      return Promise.resolve(new Response(JSON.stringify({
        ...statisticsResponse, account_id: "bybit-main",
      }), { status: 200 }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const rerendered = render(<DiaryOverlay
      accountKey="paper:1" initialSection="STATISTICS"
      statisticsScope={{ accountId: "paper", owner: "MANUAL" }}
      onClose={() => {}} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    rerendered.rerender(<DiaryOverlay
      accountKey="bybit-main:2" initialSection="STATISTICS"
      statisticsScope={{ accountId: "bybit-main", owner: "MANUAL" }}
      onClose={() => {}} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    await screen.findByText("Результативность");
    if (!pending.resolve) throw new Error("old request missing");
    pending.resolve(new Response(JSON.stringify(statisticsResponse), { status: 200 }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Переключение счёта недоступно" })).toHaveTextContent("Счёт: bybit-main"));
    expect(screen.queryByText("Не удалось загрузить статистику выбранного счёта")).not.toBeInTheDocument();
  });
});

const finrezResponse = {
  ok: true,
  account_id: "paper",
  owner: "ROBOT" as const,
  period: "DAY" as const,
  period_start_ms: 1_793_000_000_000,
  as_of_ms: 1_793_050_000_000,
  source_revision: 3,
  source: "PAPER_EXECUTIONS_ATTRIBUTED" as const,
  pnl_basis: "REALIZED_PRICE_MINUS_EXECUTION_FEES" as const,
  tickers: [
    { symbol: "ETHUSDT", pnl_usdt: "7.2", trade_count: 3 },
    { symbol: "BTCUSDT", pnl_usdt: "-2.5", trade_count: 1 },
  ],
  manual_interventions: [],
  joint_management: [],
  closed_episodes: [],
  attribution_coverage: {
    status: "COMPLETE" as const,
    excluded_unattributed_episode_count: 0,
    excluded_unattributed_execution_count: 0,
  },
};

describe("Closed deals / exact episode index", () => {
  const robotDeal = {
    trade_episode_id: "robot-episode-42", symbol: "BTCUSDT", side: "LONG",
    opened_at_ms: 1_793_001_000_000, closed_at_ms: 1_793_002_000_000,
    pnl_usdt: "-4.8", execution_count: 2,
    cohort: "ROBOT", replay_evidence: "EPISODE_INDEX_ONLY",
  };
  const sharedDeal = {
    trade_episode_id: "shared-episode-43", symbol: "XRPUSDT", side: "SHORT",
    opened_at_ms: 1_793_001_500_000, closed_at_ms: 1_793_003_000_000,
    pnl_usdt: "-1.81622186", execution_count: 7,
    cohort: "JOINT_MANAGEMENT", replay_evidence: "EPISODE_INDEX_ONLY",
  };

  it("filters closed deals by realized result and direction, preserves selections across periods and resets on ticker drilldown", async () => {
    const episode = (id: string, symbol: string, pnl_usdt: string, side: "LONG" | "SHORT" = "LONG") => ({
      ...robotDeal, trade_episode_id: "te_" + id.repeat(24), symbol, pnl_usdt, side,
    });
    const deals = [
      episode("a", "ETHUSDT", "3.1"),
      episode("b", "BTCUSDT", "-0.0026140884"),
      episode("c", "ADAUSDT", "-12.3", "SHORT"),
      episode("d", "XRPUSDT", "-0.0000000004", "SHORT"),
      episode("e", "DOGEUSDT", "0", "SHORT"),
    ];
    const fetchMock = vi.fn().mockImplementation(async (url: string) => new Response(JSON.stringify({
      ...finrezResponse,
      period: new URL(url, "http://localhost").searchParams.get("period") ?? "DAY",
      closed_episodes: deals,
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<DiaryOverlay accountKey="paper:deal-filters" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    await screen.findByRole("button", { name: /ETHUSDT/ });

    const orderedSymbols = () => screen.getAllByRole("button", {
      name: /ETHUSDT|BTCUSDT|ADAUSDT|XRPUSDT|DOGEUSDT/,
    }).map((row) => row.querySelector(".diary-trade-heading strong")?.textContent);
    const controls = screen.getByRole("searchbox", { name: "Поиск по тикеру" }).closest(".diary-ticker-search");
    expect(controls).toHaveClass("diary-ticker-search-deals");
    expect(controls?.querySelectorAll("input, select")).toHaveLength(2);
    expect(controls?.querySelectorAll(".diary-deal-filter-group")).toHaveLength(1);
    expect(controls?.querySelector(".diary-deal-side-filters")).not.toBeNull();
    expect(controls?.querySelector(".diary-deal-filter-button.profit")).toBeNull();
    expect(controls?.querySelector(".diary-deal-filter-button.loss")).toBeNull();
    const dealDistribution = screen.getByRole("group", { name: "Распределение результатов сделок" });
    expect(dealDistribution).toHaveTextContent("Прибыльных: 1");
    expect(dealDistribution).toHaveTextContent("Убыточных: 3");
    expect(dealDistribution).toHaveTextContent("Всего: 5 · в ноль: 1");
    expect(dealDistribution.querySelector(".diary-outcome-segment.profit")).toHaveStyle({ width: "20%" });
    expect(dealDistribution.querySelector(".diary-outcome-segment.loss")).toHaveStyle({ width: "60%" });
    expect(dealDistribution.querySelector(".diary-outcome-segment.neutral")).toHaveStyle({ width: "20%" });

    const profit = screen.getByRole("button", { name: "Прибыльные" });
    const loss = screen.getByRole("button", { name: "Убыточные" });
    const long = screen.getByRole("button", { name: "LONG" });
    const short = screen.getByRole("button", { name: "SHORT" });
    const pattern = screen.getByRole("combobox", { name: "Выбор паттерна" });
    expect(loss).toHaveAttribute("aria-pressed", "false");
    expect(long).toHaveAttribute("aria-pressed", "false");
    expect(orderedSymbols()).toEqual(["ETHUSDT", "BTCUSDT", "ADAUSDT", "XRPUSDT", "DOGEUSDT"]);

    fireEvent.click(loss);
    expect(loss).toHaveAttribute("aria-pressed", "true");
    expect(orderedSymbols()).toEqual(["ADAUSDT", "BTCUSDT", "XRPUSDT"]);
    expect(screen.getByRole("button", { name: /ADAUSDT/ })).toHaveTextContent("PnL: -12,30 USDT");
    expect(screen.getByRole("button", { name: /XRPUSDT/ })).toHaveTextContent("PnL: -<0,01 USDT");

    fireEvent.click(long);
    expect(orderedSymbols()).toEqual(["BTCUSDT"]);
    fireEvent.click(long);
    expect(orderedSymbols()).toEqual(["ADAUSDT", "BTCUSDT", "XRPUSDT"]);
    fireEvent.click(loss);
    expect(orderedSymbols()).toEqual(["ETHUSDT", "BTCUSDT", "ADAUSDT", "XRPUSDT", "DOGEUSDT"]);

    fireEvent.click(profit);
    expect(orderedSymbols()).toEqual(["ETHUSDT"]);
    fireEvent.click(short);
    expect(screen.getByText("Нет прибыльных сделок по выбранным фильтрам")).toBeInTheDocument();
    fireEvent.click(short);
    expect(orderedSymbols()).toEqual(["ETHUSDT"]);
    fireEvent.click(profit);
    expect(orderedSymbols()).toEqual(["ETHUSDT", "BTCUSDT", "ADAUSDT", "XRPUSDT", "DOGEUSDT"]);

    fireEvent.click(loss);
    fireEvent.change(screen.getByRole("searchbox", { name: "Поиск по тикеру" }), {
      target: { value: "BTC" },
    });
    expect(orderedSymbols()).toEqual(["BTCUSDT"]);
    fireEvent.click(screen.getByRole("button", { name: "Неделя" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=WEEK",
    ));
    expect(await screen.findByRole("button", { name: /BTCUSDT/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Убыточные" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.change(screen.getByRole("searchbox", { name: "Поиск по тикеру" }), {
      target: { value: "ETH" },
    });
    expect(screen.getByText("Нет убыточных сделок по выбранным фильтрам")).toBeInTheDocument();
    // The Deals result bar is remounted when the period changes; use the current control.
    fireEvent.click(screen.getByRole("button", { name: "Убыточные" }));
    expect(orderedSymbols()).toEqual(["ETHUSDT"]);
    fireEvent.change(pattern, { target: { value: "__NO_VERIFIED_PATTERN__" } });
    expect(orderedSymbols()).toEqual(["ETHUSDT"]);

    // Explicit ticker drilldown clears every Deals-only filter.
    fireEvent.click(screen.getByRole("button", { name: "Финрез" }));
    fireEvent.click(await screen.findByRole("button", { name: "Показать сделки по ETHUSDT" }));
    expect(screen.getByRole("combobox", { name: "Выбор паттерна" })).toHaveValue("");
    expect(await screen.findByRole("button", { name: "Прибыльные" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "Убыточные" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "LONG" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "SHORT" })).toHaveAttribute("aria-pressed", "false");
    await screen.findByRole("button", { name: /ETHUSDT/ });
    expect(orderedSymbols()).toEqual(["ETHUSDT"]);
  });

  it("keeps micro-losses visible on both closed deal rows and their details", async () => {
    const smallLoss = {
      ...robotDeal, trade_episode_id: "te_" + "a".repeat(24),
      symbol: "BTCUSDT", pnl_usdt: "-0.0026140884",
    };
    const tinyLoss = {
      ...robotDeal, trade_episode_id: "te_" + "b".repeat(24),
      symbol: "XRPUSDT", pnl_usdt: "-0.0000000004",
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ...finrezResponse, closed_episodes: [smallLoss, tinyLoss],
    }), { status: 200 })));
    render(<DiaryOverlay accountKey="paper:micro-deal-pnl" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);

    const row = await screen.findByRole("button", { name: /BTCUSDT/ });
    expect(row).toHaveTextContent("PnL: -<0,01 USDT");
    expect(screen.getByTitle("-0.0026140884")).toBeInTheDocument();
    const tinyRow = screen.getByRole("button", { name: /XRPUSDT/ });
    expect(tinyRow).toHaveTextContent("PnL: -<0,01 USDT");
    expect(screen.getByTitle("-0.0000000004")).toBeInTheDocument();

    fireEvent.click(row);
    expect(screen.getByText("-<0,01 USDT")).toHaveAttribute("title", "-0.0026140884");
    fireEvent.click(screen.getByRole("button", { name: /К сделкам/ }));
    fireEvent.click(await screen.findByRole("button", { name: /XRPUSDT/ }));
    expect(screen.getByText("-<0,01 USDT")).toHaveAttribute("title", "-0.0000000004");
  });

  it("displays exact robot episode identifiers and keeps shared PnL labelled separately", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ...finrezResponse, closed_episodes: [sharedDeal, robotDeal],
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<DiaryOverlay accountKey="paper:deals" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    const row = await screen.findByRole("button", { name: /BTCUSDT/ });
    expect(screen.getByRole("button", { name: /XRPUSDT/ })).toHaveTextContent("Робот + ручное управление");
    expect(row).toHaveTextContent("-4,80 USDT");
    fireEvent.click(row);
    expect(screen.getByText("robot-episode-42")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("не воспроизведение");
    expect(screen.queryByRole("button", { name: /Открыть сделку в Симуляторе/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /К сделкам/ }));
    expect(await screen.findByRole("button", { name: /BTCUSDT/ })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=DAY",
    );
  });

  it("copies selected episode ID with explicit unavailable notice on another device", async () => {
    const copy = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { userAgent: "Android", clipboard: { writeText: copy } });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ...finrezResponse, closed_episodes: [robotDeal],
    }), { status: 200 })));
    render(<DiaryOverlay accountKey="paper:deals" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: /BTCUSDT/ }));
    fireEvent.click(screen.getByRole("button", { name: "Открыть в Симуляторе" }));
    await waitFor(() => expect(copy).toHaveBeenCalledWith(robotDeal.trade_episode_id));
    expect(await screen.findByText(/Автоматический запуск этой сделки недоступен/)).toHaveTextContent(
      "Идентификатор скопирован.",
    );
  });

  it("copies real episode ID directly without protocol launch or bridge request", async () => {
    const episodeId = "te_" + "f".repeat(24);
    const copy = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { userAgent: "Android", clipboard: { writeText: copy } });
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ...finrezResponse,
      closed_episodes: [{ ...robotDeal, trade_episode_id: episodeId }],
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<DiaryOverlay accountKey="paper:deals" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: /BTCUSDT/ }));
    fireEvent.click(screen.getByRole("button", { name: "Скопировать ID" }));
    await waitFor(() => expect(copy).toHaveBeenCalledWith(episodeId));
    expect(await screen.findByText(/ID сделки скопирован:/)).toHaveTextContent(episodeId);
    expect(fetchMock.mock.calls.filter(([url]) =>
      String(url).includes("/simulator-bridge/"))).toHaveLength(0);
  });

  it("Windows requests scoped JSON via owner bridge, never leaks facts into a URI", async () => {
    const episodeId = "te_" + "a".repeat(24);
    const requestId = "1".repeat(32);
    const copy = vi.fn().mockResolvedValue(undefined);
    const launches: string[] = [];
    vi.stubGlobal("navigator", {
      userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
      clipboard: { writeText: copy },
    });
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        launches.push(this.getAttribute("href") || "");
      });
    try {
      const fetchMock = vi.fn().mockImplementation(async (url: string) => {
        if (url.endsWith("/simulator-bridge/request")) return new Response(JSON.stringify({
          ok: true, state: "QUEUED", request_id: requestId,
        }), { status: 200 });
        if (url.endsWith("/simulator-bridge/status")) return new Response(JSON.stringify({
          ok: true, state: "LAUNCHED", request_id: requestId,
        }), { status: 200 });
        return new Response(JSON.stringify({
          ...finrezResponse,
          closed_episodes: [{ ...robotDeal, trade_episode_id: episodeId }],
        }), { status: 200 });
      });
      vi.stubGlobal("fetch", fetchMock);
      render(<DiaryOverlay accountKey="paper:deals" initialSection="DEALS"
        statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
      fireEvent.click(await screen.findByRole("button", { name: /BTCUSDT/ }));
      fireEvent.click(screen.getByRole("button", { name: "Открыть в Симуляторе" }));
      expect(await screen.findByText(/Локальный адаптер сохранил JSON исполнений/))
        .toHaveTextContent("Идентификатор скопирован.");
      expect(copy).toHaveBeenCalledWith(episodeId);
      expect(launches).toEqual([]); // The device agent opens the viewer AFTER syncing JSON.
      expect(fetchMock).toHaveBeenCalledWith("/api/diary/simulator-bridge/request", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          episode_id: episodeId, owner: "ROBOT", source_revision: 3,
        }),
      });
    } finally {
      anchorClick.mockRestore();
    }
  });

  it("pairs an existing VPS device slot through a confirmed Windows link only", async () => {
    const token = "A".repeat(64);
    const copies = vi.fn().mockResolvedValue(undefined);
    const linkClicks: string[] = [];
    vi.stubGlobal("navigator", {
      userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
      clipboard: { writeText: copies },
    });
    const spy = vi.spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        linkClicks.push(this.href);
      });
    try {
      const fetchMock = vi.fn().mockImplementation(async (url: string) => {
        if (url.endsWith("/simulator-bridge/pair")) return new Response(JSON.stringify({
          ok: true, device_id: "owner-pc", token,
        }), { status: 200 });
        return new Response(JSON.stringify({
          ...finrezResponse, closed_episodes: [robotDeal],
        }), { status: 200 });
      });
      vi.stubGlobal("fetch", fetchMock);
      render(<DiaryOverlay accountKey="paper:deals" initialSection="DEALS"
        statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
      fireEvent.click(await screen.findByRole("button", { name: /BTCUSDT/ }));
      fireEvent.click(screen.getByRole("button", { name: "Связать ПК" }));
      expect(await screen.findByRole("button", { name: "Подтвердить подключение" }))
        .toBeInTheDocument();
      expect(linkClicks).toHaveLength(0); // browser must not auto-open on async request
      expect(fetchMock).toHaveBeenCalledWith("/api/diary/simulator-bridge/pair", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_id: "owner-pc" }),
      });
      fireEvent.click(screen.getByRole("button", { name: "Подтвердить подключение" }));
      expect(linkClicks).toEqual([
        "bybitscanner-simulator://pair?device_id=owner-pc&token=" + token,
      ]);
      expect(screen.getByText(/Запрос сопряжения передан Windows/))
        .toHaveTextContent("Успешное подключение пока не подтверждено.");
      expect(screen.queryByRole("button", { name: "Подтвердить подключение" }))
        .not.toBeInTheDocument();
    } finally {
      spy.mockRestore();
    }
  });

  it.each([
    [503, "simulator_bridge_disabled", "Мост сопряжения отключён на сервере (HTTP 503)"],
    [503, "simulator_pairing_device_not_configured", "Это устройство не настроено на сервере (HTTP 503)"],
    [403, "simulator_bridge_unauthorized", "Сервер отклонил авторизацию или источник Telegram Mini App (HTTP 403)"],
    [400, "invalid_simulator_bridge_request", "Сервер отклонил формат запроса (HTTP 400)"],
    [502, "PRIVATE_ERROR_TOKEN", "Сервер отклонил сопряжение (HTTP 502)"],
  ])("shows only safe in-app pairing error for HTTP %i %s", async (status, error, expected) => {
    const secret = "SECRET_PAIRING_TOKEN_MUST_NOT_RENDER";
    vi.stubGlobal("navigator", { userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" });
    const fetchMock = vi.fn().mockImplementation(async (url: string) => {
      if (url.endsWith("/simulator-bridge/pair"))
        return new Response(JSON.stringify({ ok: false, error, token: secret }), { status });
      return new Response(JSON.stringify({
        ...finrezResponse, closed_episodes: [robotDeal],
      }), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<DiaryOverlay accountKey="paper:pair-error" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: /BTCUSDT/ }));
    fireEvent.click(screen.getByRole("button", { name: "Связать ПК" }));
    const notice = await screen.findByText(/Подключение пока недоступно:/);
    expect(notice).toHaveTextContent(expected);
    expect(notice).not.toHaveTextContent(secret);
    expect(notice).not.toHaveTextContent("PRIVATE_ERROR_TOKEN");
    expect(screen.queryByRole("button", { name: "Подтвердить подключение" }))
      .not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/diary/simulator-bridge/pair", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: "owner-pc" }),
    });
  });

  it("distinguishes network failure and invalid success without leaking server payloads", async () => {
    const secret = "SECRET_PAIRING_TOKEN_MUST_NOT_RENDER";
    const scenarios = [
      { failure: "Нет ответа сервера (сеть или шлюз)", payload: null },
      { failure: "Ответ сервера не прошёл проверку (HTTP 200)", payload: { ok: true, device_id: "owner-laptop", token: secret } },
    ];
    for (const scenario of scenarios) {
      vi.stubGlobal("navigator", { userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" });
      vi.stubGlobal("fetch", vi.fn().mockImplementation(async (url: string) => {
        if (url.endsWith("/simulator-bridge/pair")) {
          if (!scenario.payload) throw new TypeError("network " + secret);
          return new Response(JSON.stringify(scenario.payload), { status: 200 });
        }
        return new Response(JSON.stringify({
          ...finrezResponse, closed_episodes: [robotDeal],
        }), { status: 200 });
      }));
      const view = render(<DiaryOverlay accountKey="paper:pair-unknown" initialSection="DEALS"
        statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
      fireEvent.click(await screen.findByRole("button", { name: /BTCUSDT/ }));
      fireEvent.click(screen.getByRole("button", { name: "Связать ПК" }));
      const notice = await screen.findByText(/Подключение пока недоступно:/);
      expect(notice).toHaveTextContent(scenario.failure);
      expect(notice).not.toHaveTextContent(secret);
      expect(screen.queryByRole("button", { name: "Подтвердить подключение" }))
        .not.toBeInTheDocument();
      view.unmount();
    }
  });

  it("on phone requests paired adapter and reports acknowledged local utility opening", async () => {
    const episodeId = "te_" + "c".repeat(24);
    const requestId = "d".repeat(32);
    const copy = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { userAgent: "Android", clipboard: { writeText: copy } });
    const fetchMock = vi.fn().mockImplementation(async (url: string) => {
      if (url.endsWith("/simulator-bridge/request")) return new Response(JSON.stringify({
        ok: true, state: "QUEUED", request_id: requestId,
      }), { status: 200 });
      if (url.endsWith("/simulator-bridge/status")) return new Response(JSON.stringify({
        ok: true, state: "LAUNCHED", request_id: requestId,
      }), { status: 200 });
      return new Response(JSON.stringify({
        ...finrezResponse, closed_episodes: [{ ...robotDeal, trade_episode_id: episodeId }],
      }), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<DiaryOverlay accountKey="paper:deals" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: /BTCUSDT/ }));
    fireEvent.click(screen.getByRole("button", { name: "Открыть в Симуляторе" }));
    expect(await screen.findByText(/Локальный адаптер сохранил JSON исполнений/))
      .toHaveTextContent("Идентификатор скопирован.");
    expect(copy).toHaveBeenCalledWith(episodeId);
    expect(fetchMock).toHaveBeenCalledWith("/api/diary/simulator-bridge/request", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ episode_id: episodeId, owner: "ROBOT", source_revision: 3 }),
    });
    expect(fetchMock).toHaveBeenCalledWith("/api/diary/simulator-bridge/status", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_id: requestId }),
    });
  });

  it("on phone retains copied ID when no paired adapter is connected", async () => {
    const episodeId = "te_" + "e".repeat(24);
    const copy = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { userAgent: "Android", clipboard: { writeText: copy } });
    const fetchMock = vi.fn().mockImplementation(async (url: string) => {
      if (url.endsWith("/simulator-bridge/request")) return new Response(JSON.stringify({
        ok: false, error: "no_connected_simulator_adapter",
      }), { status: 503 });
      return new Response(JSON.stringify({
        ...finrezResponse, closed_episodes: [{ ...robotDeal, trade_episode_id: episodeId }],
      }), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<DiaryOverlay accountKey="paper:deals" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: /BTCUSDT/ }));
    fireEvent.click(screen.getByRole("button", { name: "Открыть в Симуляторе" }));
    expect(await screen.findByText(/Нет сопряжённого Симулятора для передачи JSON/))
      .toHaveTextContent("Идентификатор скопирован.");
    expect(copy).toHaveBeenCalledWith(episodeId);
    expect(fetchMock.mock.calls.filter(([url]) =>
      (url as string).endsWith("/simulator-bridge/status"))).toHaveLength(0);
  });

  it("blocks missing episode contract on an older backend instead of inventing deals", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ...finrezResponse, closed_episodes: undefined,
    }), { status: 200 })));
    render(<DiaryOverlay accountKey="paper:old" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    expect(await screen.findByText("Не удалось загрузить статистику выбранного счёта")).toBeInTheDocument();
    expect(screen.queryByText("robot-episode-42")).not.toBeInTheDocument();
  });

  it("rejects foreign controller provenance, duplicate IDs, invalid timestamps and unproven replay claims", async () => {
    const violations = [
      { ...robotDeal, cohort: "MANUAL" },
      { ...robotDeal, replay_evidence: "FULL_REPLAY" },
      { ...robotDeal, closed_at_ms: 1_792_000_000_000 },
      { ...robotDeal, pnl_usdt: "NaN" },
    ];
    for (const invalid of violations) {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
        ...finrezResponse, closed_episodes: [invalid],
      }), { status: 200 })));
      const view = render(<DiaryOverlay accountKey="paper:invalid" initialSection="DEALS"
        statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
      expect(await screen.findByText("Не удалось загрузить статистику выбранного счёта")).toBeInTheDocument();
      view.unmount();
    }
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ...finrezResponse, closed_episodes: [robotDeal, robotDeal],
    }), { status: 200 })));
    render(<DiaryOverlay accountKey="paper:duplicate" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    expect(await screen.findByText("Не удалось загрузить статистику выбранного счёта")).toBeInTheDocument();
  });
  it("downloads exact persisted fills without claiming that Robot decisions were replayed", async () => {
    const episodeId = "te_" + "a".repeat(24);
    const selectedDeal = { ...robotDeal, trade_episode_id: episodeId };
    const payload = {
      ok: true, schema: "BYBITSCANNER_CLOSED_EPISODE_FACTS_V1",
      namespace: "PAPER_READ_ONLY", source: "PAPER_EXECUTIONS_ATTRIBUTED",
      source_revision: finrezResponse.source_revision,
      account_id: "paper", owner: "ROBOT", cohort: "ROBOT",
      trade_episode_id: episodeId, symbol: "BTCUSDT", side: "LONG",
      opened_at_ms: selectedDeal.opened_at_ms, closed_at_ms: selectedDeal.closed_at_ms,
      pnl_usdt: "-4.8", replay_evidence: "EXECUTION_FACTS_ONLY_NO_DECISIONS_OR_CANDLES",
      execution_allocations: [
        { execution_id: "exec-1", execution_price: "100" },
        { execution_id: "exec-2", execution_price: "99" },
      ],
    };
    const fetchMock = vi.fn().mockImplementation(async (url: string) =>
      new Response(JSON.stringify(url.includes("/api/diary/episode-facts") ? payload :
        { ...finrezResponse, closed_episodes: [selectedDeal] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const URLWithBlobs = Object.assign(class extends URL {}, {
      createObjectURL: vi.fn(() => "blob:episode-facts"), revokeObjectURL: vi.fn(),
    });
    vi.stubGlobal("URL", URLWithBlobs);
    try {
      render(<DiaryOverlay accountKey="paper:export" initialSection="DEALS"
        statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
      fireEvent.click(await screen.findByRole("button", { name: /BTCUSDT/ }));
      expect(screen.getByRole("status")).toHaveTextContent("только реальные зарегистрированные исполнения");
      fireEvent.click(screen.getByRole("button", { name: "Скачать JSON исполнений" }));
      await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
        `/api/diary/episode-facts?account_id=paper&owner=ROBOT&trade_episode_id=${episodeId}&source_revision=3`,
        { cache: "no-store" },
      ));
      await waitFor(() => expect(click).toHaveBeenCalledOnce());
      expect(URLWithBlobs.createObjectURL).toHaveBeenCalledOnce();
      expect(await screen.findByRole("button", { name: "Скопировать JSON" })).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Скопировать JSON" }));
      expect(await screen.findByRole("textbox", { name: "Проверенный JSON сделки" })).toHaveValue(
        JSON.stringify(payload, null, 2) + "\n",
      );
    } finally {
      click.mockRestore();
    }
  });

  it("rejects an outdated source revision without downloading a misleading replay", async () => {
    const selectedDeal = { ...robotDeal, trade_episode_id: "te_" + "b".repeat(24) };
    const fetchMock = vi.fn().mockImplementation(async (url: string) =>
      new Response(JSON.stringify(url.includes("/api/diary/episode-facts")
        ? { ok: false, error: "episode_facts_source_changed" }
        : { ...finrezResponse, closed_episodes: [selectedDeal] }),
      { status: url.includes("/api/diary/episode-facts") ? 409 : 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<DiaryOverlay accountKey="paper:expired" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: /BTCUSDT/ }));
    fireEvent.click(screen.getByRole("button", { name: "Скачать JSON исполнений" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("История обновилась");
  });

  it("rejects an exported episode with mismatched provenance rather than saving it", async () => {
    const selectedDeal = { ...robotDeal, trade_episode_id: "te_" + "c".repeat(24) };
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async (url: string) =>
      new Response(JSON.stringify(url.includes("/api/diary/episode-facts")
        ? { ok: true, schema: "BYBITSCANNER_CLOSED_EPISODE_FACTS_V1",
            namespace: "PAPER_READ_ONLY", source: "PAPER_EXECUTIONS_ATTRIBUTED",
            account_id: "paper", owner: "MANUAL", trade_episode_id: selectedDeal.trade_episode_id,
            source_revision: 3, execution_allocations: [] }
        : { ...finrezResponse, closed_episodes: [selectedDeal] }), { status: 200 })));
    render(<DiaryOverlay accountKey="paper:wrong-owner" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: /BTCUSDT/ }));
    fireEvent.click(screen.getByRole("button", { name: "Скачать JSON исполнений" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("не совпала");
  });

});

describe("Statistics full-width account/close header", () => {
  it("reuses the canonical golden-key account picker beside an equal-height square close button", async () => {
    const catalog = {
      ok: true, active_account_id: "paper", session_generation: 1,
      accounts: [{ id: "paper", display_name: "Paper / Virtual",
        provider: "PAPER", environment: "PAPER", status: "READY" }],
    };
    const onClose = vi.fn();
    const fetchMock = vi.fn().mockImplementation(async (url: string) => {
      if (url === "/api/accounts") {
        return new Response(JSON.stringify(catalog), { status: 200 });
      }
      if (url === "/api/manual-main/accounts") {
        return new Response(JSON.stringify({ ok: true, accounts: [] }), { status: 200 });
      }
      return new Response(JSON.stringify(finrezResponse), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const { container } = render(<DiaryOverlay accountKey="paper:header" initialSection="FINREZ"
      statisticsScope={{ accountId: "paper", owner: "MANUAL" }}
      accountMenu={{
        workspaceProjection: {
          ok: true, account_id: "paper", provider: "PAPER", environment: "PAPER",
          status: "READY", session_generation: 1, projection_generation: 1,
          read_only: false, wallet_balance_usdt: "100",
          total_equity_usdt: "100", available_balance_usdt: "100",
          positions: [], orders: [], paper_state: null,
        },
        mode: "TERMINAL", selectedAccountId: "paper", onSelectAccount: vi.fn(),
      }}
      onClose={onClose} />);
    const header = container.querySelector(".diary-header")!;
    const accountControl = screen.getByRole("button", { name: "Open account selection" });
    const closeButton = screen.getByRole("button", { name: "Закрыть статистику" });
    expect(header.children).toHaveLength(2);
    expect(header.firstElementChild).toBe(accountControl.closest(".paper-account-control"));
    expect(header.lastElementChild).toBe(closeButton);
    const heading = container.querySelector(".diary-context-heading")!;
    expect(header.nextElementSibling).toBe(heading);
    expect(heading).toHaveTextContent("Терминал");
    expect(heading).toHaveTextContent("Статистика");
    expect(heading.children).toHaveLength(2);
    expect(heading.firstElementChild?.nextElementSibling).toBe(heading.querySelector("h2"));
    expect(heading).not.toHaveTextContent("раздельная статистика");
    expect(accountControl).toHaveClass("account-switch-button");
    expect(accountControl.querySelectorAll(".account-switch-key")).toHaveLength(1);
    expect(await screen.findByText("PAPER")).toBeInTheDocument();
    fireEvent.click(accountControl);
    expect(await screen.findByRole("dialog", { name: "Accounts" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close Accounts" }));
    expect(screen.queryByRole("dialog", { name: "Accounts" })).not.toBeInTheDocument();
    fireEvent.click(closeButton);
    expect(onClose).toHaveBeenCalledOnce();
  });
});

describe("Statistics source headings", () => {
  it("shows Автопилот and Статистика next to each other in the shared compact heading", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(finrezResponse), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const { container } = render(<DiaryOverlay accountKey="paper:robot" initialSection="FINREZ"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    const heading = container.querySelector(".diary-context-heading")!;
    expect(heading.querySelector("p")).toHaveTextContent("Автопилот");
    expect(heading.querySelector("h2")).toHaveTextContent("Статистика");
    expect(heading.children).toHaveLength(2);
    expect(heading.firstElementChild?.nextElementSibling).toBe(heading.querySelector("h2"));
    expect(heading).not.toHaveTextContent("PAPER");
    expect(heading).not.toHaveTextContent("раздельная статистика");
    await screen.findByText("ETHUSDT");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=DAY",
    );
  });
});

describe("Finrez first-screen UI", () => {
  it("shows exact indexed D2 patterns on every eligible deal without opening each one", async () => {
    const btc = {
      trade_episode_id: "te_" + "a".repeat(24), symbol: "BTCUSDT", side: "LONG",
      opened_at_ms: 1_793_001_000_000, closed_at_ms: 1_793_002_000_000,
      pnl_usdt: "-2.5", execution_count: 2, cohort: "ROBOT",
      replay_evidence: "EPISODE_INDEX_ONLY", opening_controller: "ROBOT",
      setup_context: {
        status: "EXACT_D2_LINK", source: "TRADING_DIARY_D2",
        consistency: "INDEPENDENT_READ_SNAPSHOT_NOT_ATOMIC_WITH_PAPER",
        decision_scope: "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG",
        setup: {
          setup_id: "candidate-btc", symbol: "BTCUSDT", direction: "LONG",
          origin: "ROBOT", pattern: "Falling Wedge", timeframe: "5",
          strategy_version: "robot-v3", created_at_ms: 1_793_000_000_000,
        },
      },
    };
    const eth = {
      ...btc, trade_episode_id: "te_" + "b".repeat(24), symbol: "ETHUSDT",
      setup_context: {
        ...btc.setup_context,
        setup: { ...btc.setup_context.setup, symbol: "BTCUSDT", pattern: "Wrong Pattern" },
      },
    };
    const fetchMock = vi.fn().mockImplementation(async (url: string) =>
      new Response(JSON.stringify({
        ...finrezResponse,
        period: (new URL(url, "http://localhost").searchParams.get("period") ?? "DAY"),
        closed_episodes: [btc, eth],
      }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<DiaryOverlay accountKey="paper:mass-patterns" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    expect(await screen.findByText("Клин ↘")).toBeInTheDocument();
    expect(screen.getByText("не установлен")).toBeInTheDocument();
    expect(screen.queryByText("Wrong Pattern")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Подробности сделки" })).toHaveLength(2);
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/episode-facts")))
      .toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Неделя" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=WEEK",
    ));
    expect(await screen.findByText("Клин ↘")).toBeInTheDocument();
  });

  it("groups exact D2 patterns separately by management cohort and opens filtered deals", async () => {
    const linked = (id: string, pattern: string, pnl_usdt: string,
      cohort: "ROBOT" | "JOINT_MANAGEMENT" = "ROBOT", origin = "ROBOT") => ({
      trade_episode_id: "te_" + id.repeat(24), symbol: "BTCUSDT", side: "LONG",
      opened_at_ms: 1_793_001_000_000, closed_at_ms: 1_793_002_000_000,
      pnl_usdt, execution_count: 2, cohort, replay_evidence: "EPISODE_INDEX_ONLY",
      opening_controller: "ROBOT",
      setup_context: {
        status: "EXACT_D2_LINK", source: "TRADING_DIARY_D2",
        consistency: "INDEPENDENT_READ_SNAPSHOT_NOT_ATOMIC_WITH_PAPER",
        decision_scope: "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG",
        setup: {
          setup_id: "candidate-" + id, symbol: "BTCUSDT", direction: "LONG",
          origin, pattern, timeframe: "5", strategy_version: "v1",
          created_at_ms: 1_793_000_000_000,
        },
      },
    });
    const deals = [
      linked("a", "Falling Wedge", "-2.5012345678"),
      linked("b", "Falling Wedge", "1.1"),
      linked("c", "Falling Wedge", "20.2", "JOINT_MANAGEMENT"),
      linked("d", "Triangle Compression", "3"),
      linked("e", "Falling Wedge", "-999", "ROBOT", "TERMINAL_MANUAL"),
    ];
    const fetchMock = vi.fn().mockImplementation(async (url: string) => new Response(JSON.stringify({
      ...finrezResponse,
      period: (new URL(url, "http://localhost").searchParams.get("period") ?? "DAY"),
      closed_episodes: deals,
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<DiaryOverlay accountKey="paper:patterns" initialSection="PATTERNS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    const region = await screen.findByRole("region", { name: "Паттерны по подтверждённым сделкам" });
    expect(region).toHaveTextContent("С подтверждённым паттерном: 4 из 5");
    expect(region).toHaveTextContent("Робот · сделок: 2 · прибыльных: 1 · убыточных: 1");
    expect(screen.getByTitle("-1.4012345678 USDT")).toHaveTextContent("-1,40 USDT");
    expect(screen.getByTitle("20.2 USDT")).toHaveTextContent("+20,20 USDT");
    const rankedCards = Array.from(region.querySelectorAll(".diary-pattern-card"));
    expect(rankedCards.map((card) => card.querySelector("span[title$='USDT']")?.textContent?.trim()))
      .toEqual(["+20,20 USDT", "+3,00 USDT", "-1,40 USDT"]);
    const patternDistribution = screen.getByRole("group", { name: "Распределение результатов паттернов" });
    expect(patternDistribution).toHaveTextContent("Прибыльных: 2");
    expect(patternDistribution).toHaveTextContent("Убыточных: 1");
    expect(patternDistribution).toHaveTextContent("Всего: 3");
    expect(patternDistribution.querySelector(".diary-outcome-segment.profit")).toHaveStyle({ width: "66.66666666666666%" });
    fireEvent.click(screen.getByRole("button", { name: "Прибыльные паттерны" }));
    expect(region.querySelectorAll(".diary-pattern-card")).toHaveLength(2);
    expect(patternDistribution).toHaveTextContent("Всего: 3");
    fireEvent.click(screen.getByRole("button", { name: "Убыточные паттерны" }));
    expect(region.querySelectorAll(".diary-pattern-card")).toHaveLength(1);
    expect(region.querySelector(".diary-pattern-card")).toHaveTextContent("-1,40 USDT");
    fireEvent.click(screen.getByRole("button", { name: "Показать все паттерны" }));
    expect(region.querySelectorAll(".diary-pattern-card")).toHaveLength(3);
    expect(screen.queryByTitle("-999 USDT")).not.toBeInTheDocument();
    const openWedge = screen.getAllByRole("button", { name: "Показать все сделки по паттерну Falling Wedge" });
    expect(openWedge).toHaveLength(2);
    fireEvent.click(openWedge[0]);
    expect(await screen.findAllByText("Клин ↘")).toHaveLength(3);
    expect(screen.getByRole("combobox", { name: "Выбор паттерна" })).toHaveValue("Falling Wedge");
    expect(screen.getAllByRole("button", { name: /BTCUSDT/ })
      .every((row) => !row.textContent?.includes("Triangle Compression"))).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Неделя" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=WEEK",
    ));
    expect(screen.getByRole("combobox", { name: "Выбор паттерна" })).toHaveValue("Falling Wedge");

    fireEvent.click(screen.getByRole("button", { name: "Убыточные" }));
    expect(screen.getAllByText("Клин ↘")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Паттерны" }));
    await screen.findByRole("region", { name: "Паттерны по подтверждённым сделкам" });
    fireEvent.click(screen.getAllByRole("button", {
      name: "Показать все сделки по паттерну Falling Wedge",
    })[0]);
    expect(await screen.findByRole("button", { name: "Убыточные" })).toHaveAttribute("aria-pressed", "false");
    expect(await screen.findAllByText("Клин ↘")).toHaveLength(3);
  });


  it("ranks every evidence-backed pattern name and drills into its own deals", async () => {
    const patterns = [
      ["IKIGAI_BOX", "2"], ["L-shape", "-1"], ["Falling Wedge", "-8"],
      ["Rising Wedge", "5"], ["Triangle Compression", "0.5"],
      ["Double Top", "-2"], ["Double Bottom", "-3"], ["MIRROR", "1"],
    ] as const;
    const episodes = patterns.map(([pattern, pnl_usdt], index) => {
      const id = (index + 10).toString(16).padStart(24, "0");
      return {
        trade_episode_id: "te_" + id, symbol: "BTCUSDT", side: "LONG",
        pnl_usdt, opened_at_ms: 1_793_001_000_000,
        closed_at_ms: 1_793_002_000_000, execution_count: 2,
        cohort: "ROBOT", replay_evidence: "EPISODE_INDEX_ONLY",
        opening_controller: "ROBOT",
        setup_context: {
          status: "EXACT_D2_LINK", source: "TRADING_DIARY_D2",
          consistency: "INDEPENDENT_READ_SNAPSHOT_NOT_ATOMIC_WITH_PAPER",
          decision_scope: "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG",
          setup: {
            setup_id: "candidate-" + id, symbol: "BTCUSDT", direction: "LONG",
            origin: "ROBOT", pattern, timeframe: "5", strategy_version: "v1",
            created_at_ms: 1_793_000_000_000,
          },
        },
      };
    });
    // Each navigation requests a new one-shot HTTP body.
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => new Response(JSON.stringify({
      ...finrezResponse, closed_episodes: episodes,
    }), { status: 200 })));
    render(<DiaryOverlay accountKey="paper:all-proven-patterns" initialSection="PATTERNS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    const region = await screen.findByRole("region", { name: "Паттерны по подтверждённым сделкам" });
    const cards = () => Array.from(region.querySelectorAll(".diary-pattern-card"));
    expect(cards().map((card) => card.querySelector(".diary-pattern-label strong")?.textContent))
      .toEqual(["Rising Wedge", "IKIGAI_BOX", "MIRROR", "Triangle Compression",
        "L-shape", "Double Top", "Double Bottom", "Falling Wedge"]);
    const bar = screen.getByRole("group", { name: "Распределение результатов паттернов" });
    expect(bar).toHaveTextContent("Прибыльных: 4");
    expect(bar).toHaveTextContent("Убыточных: 4");
    expect(bar).toHaveTextContent("Всего: 8");
    fireEvent.click(screen.getByRole("button", { name: "Убыточные паттерны" }));
    expect(cards()).toHaveLength(4);
    expect(cards().map((card) => card.querySelector(".diary-pattern-label strong")?.textContent))
      .toEqual(["Falling Wedge", "Double Bottom", "Double Top", "L-shape"]);
    fireEvent.click(screen.getByRole("button", { name: "Показать все сделки по паттерну Double Bottom" }));
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Выбор паттерна" }))
      .toHaveValue("Double Bottom"));
    const dealBar = screen.getByRole("group", { name: "Распределение результатов сделок" });
    expect(dealBar).toHaveTextContent("Всего: 1");
    expect(dealBar).toHaveTextContent("Убыточных: 1");
    expect(screen.getByRole("button", { name: "Убыточные" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /BTCUSDT/ })).toHaveTextContent("Double Bottom");
  });

  it("from all-time red patterns opens only the losing episodes of a mixed-result pattern", async () => {
    const linked = (id: string, pattern: string, pnl_usdt: string) => ({
      trade_episode_id: "te_" + id.repeat(24), symbol: "BTCUSDT", side: "LONG",
      opened_at_ms: 1_793_001_000_000, closed_at_ms: 1_793_002_000_000,
      pnl_usdt, execution_count: 2, cohort: "ROBOT",
      replay_evidence: "EPISODE_INDEX_ONLY", opening_controller: "ROBOT",
      setup_context: {
        status: "EXACT_D2_LINK", source: "TRADING_DIARY_D2",
        consistency: "INDEPENDENT_READ_SNAPSHOT_NOT_ATOMIC_WITH_PAPER",
        decision_scope: "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG",
        setup: {
          setup_id: "candidate-" + id, symbol: "BTCUSDT", direction: "LONG",
          origin: "ROBOT", pattern, timeframe: "5", strategy_version: "v1",
          created_at_ms: 1_793_000_000_000,
        },
      },
    });
    const fetchMock = vi.fn().mockImplementation(async (url: string) => new Response(JSON.stringify({
      ...finrezResponse,
      period: new URL(url, "http://localhost").searchParams.get("period") ?? "DAY",
      closed_episodes: [
        linked("a", "Falling Wedge", "-8"),
        linked("b", "Falling Wedge", "2"),
        linked("c", "Double Bottom", "-3"),
        linked("d", "IKIGAI_BOX", "7"),
      ],
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<DiaryOverlay accountKey="paper:worst-pattern-handoff" initialSection="PATTERNS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Всё время" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=ALL",
    ));
    const region = await screen.findByRole("region", { name: "Паттерны по подтверждённым сделкам" });
    const cards = () => Array.from(region.querySelectorAll(".diary-pattern-card"));
    expect(cards().map((card) => card.querySelector(".diary-pattern-label strong")?.textContent))
      .toEqual(["IKIGAI_BOX", "Double Bottom", "Falling Wedge"]);
    const bar = screen.getByRole("group", { name: "Распределение результатов паттернов" });
    expect(bar).toHaveTextContent("Убыточных: 2");
    fireEvent.click(screen.getByRole("button", { name: "Убыточные паттерны" }));
    expect(cards().map((card) => card.querySelector(".diary-pattern-label strong")?.textContent))
      .toEqual(["Falling Wedge", "Double Bottom"]);
    expect(bar).toHaveTextContent("Всего: 3");
    fireEvent.click(screen.getByRole("button", { name: "Показать все сделки по паттерну Falling Wedge" }));
    expect(await screen.findByRole("combobox", { name: "Выбор паттерна" }))
      .toHaveValue("Falling Wedge");
    const dealBar = screen.getByRole("group", { name: "Распределение результатов сделок" });
    expect(dealBar).toHaveTextContent("Всего: 2");
    expect(dealBar).toHaveTextContent("Прибыльных: 1");
    expect(dealBar).toHaveTextContent("Убыточных: 1");
    expect(screen.getByRole("button", { name: "Убыточные" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getAllByRole("button", { name: "Подробности сделки" })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Подробности сделки" }));
    expect(await screen.findByRole("button", { name: "Открыть в Симуляторе" }))
      .toBeInTheDocument();
  });

  it("never shows an unknown pattern as a zero result and respects ticker filtering", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ...finrezResponse,
      closed_episodes: [{
        trade_episode_id: "te_" + "f".repeat(24), symbol: "BTCUSDT", side: "SHORT",
        opened_at_ms: 1_793_001_000_000, closed_at_ms: 1_793_002_000_000,
        pnl_usdt: "-50.001", execution_count: 2, cohort: "ROBOT",
        replay_evidence: "EPISODE_INDEX_ONLY",
      }],
      attribution_coverage: {
        status: "PARTIAL", excluded_unattributed_episode_count: 1,
        excluded_unattributed_execution_count: 2,
      },
    }), { status: 200 })));
    render(<DiaryOverlay accountKey="paper:unverified-patterns" initialSection="PATTERNS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    const region = await screen.findByRole("region", { name: "Паттерны по подтверждённым сделкам" });
    expect(region).toHaveTextContent("С подтверждённым паттерном: 0 из 1");
    expect(region).toHaveTextContent("неполное покрытие атрибуции");
    expect(region).toHaveTextContent("Нет сделок с подтверждённым паттерном");
    expect(region).not.toHaveTextContent("0 USDT");
    const emptyPatternBar = screen.getByRole("group", { name: "Распределение результатов паттернов" });
    expect(emptyPatternBar).toHaveTextContent("Всего: 0");
    expect(emptyPatternBar.querySelector(".diary-outcome-track")).toHaveTextContent("");
    expect(screen.getByRole("button", { name: "Прибыльные паттерны" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Убыточные паттерны" })).toBeDisabled();
    fireEvent.change(screen.getByRole("searchbox", { name: "Поиск по тикеру" }), {
      target: { value: "ETH" },
    });
    expect(region).toHaveTextContent("С подтверждённым паттерном: 0 из 0");
  });

  it("shows the ticker ranking with five periods, reuses the Diary modal and defers other sections", async () => {
    const fetchMock = vi.fn().mockImplementation(async (url: string) => new Response(JSON.stringify({
      ...finrezResponse,
      period: (new URL(url, "http://localhost").searchParams.get("period") ?? "DAY"),
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<DiaryOverlay accountKey="paper:1" initialSection="FINREZ"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    expect(screen.getByRole("dialog", { name: "Статистика" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "День" })).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByText("+7,20 USDT")).toBeInTheDocument();
    expect(screen.getByText("-2,50 USDT")).toBeInTheDocument();
    expect(screen.getByText("ETHUSDT")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=DAY");
    for (const [label, period] of [["Неделя", "WEEK"], ["Месяц", "MONTH"], ["Год", "YEAR"]] as const) {
      fireEvent.click(screen.getByRole("button", { name: label }));
      await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
        `/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=${period}`
      ));
      expect(screen.getByRole("button", { name: label })).toHaveAttribute("aria-pressed", "true");
    }
    fireEvent.click(screen.getByRole("button", { name: "Всё время" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=ALL"));
    fireEvent.click(screen.getByRole("button", { name: "Паттерны" }));
    expect(await screen.findByText(/Нет сделок с подтверждённым паттерном/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Сделки" }));
    expect(await screen.findByText(/Нет подтверждённых закрытых сделок/)).toBeInTheDocument();
  });

  it("combines ticker, period and exact verified pattern selection without guessing patterns", async () => {
    const linked = (id: string, symbol: string, pattern: string, origin = "ROBOT") => ({
      trade_episode_id: "te_" + id.repeat(24), symbol, side: "LONG",
      opened_at_ms: 1_793_001_000_000, closed_at_ms: 1_793_002_000_000,
      pnl_usdt: "-2.5", execution_count: 2, cohort: "ROBOT",
      replay_evidence: "EPISODE_INDEX_ONLY", opening_controller: "ROBOT",
      setup_context: {
        status: "EXACT_D2_LINK", source: "TRADING_DIARY_D2",
        consistency: "INDEPENDENT_READ_SNAPSHOT_NOT_ATOMIC_WITH_PAPER",
        decision_scope: "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG",
        setup: {
          setup_id: "candidate-" + id, symbol, direction: "LONG",
          origin, pattern, timeframe: "5", strategy_version: "v1",
          created_at_ms: 1_793_000_000_000,
        },
      },
    });
    const btc = linked("a", "BTCUSDT", "Falling Wedge");
    const eth = linked("b", "ETHUSDT", "Triangle Compression");
    // The textual label alone never qualifies: source origin conflicts.
    const unproven = linked("c", "XRPUSDT", "Falling Wedge", "TERMINAL_MANUAL");
    const mockFetch = vi.fn().mockImplementation(async (url: string) => new Response(JSON.stringify({
      ...finrezResponse,
      period: (new URL(url, "http://localhost").searchParams.get("period") ?? "DAY"),
      closed_episodes: [btc, eth, unproven],
    }), { status: 200 }));
    vi.stubGlobal("fetch", mockFetch);
    render(<DiaryOverlay accountKey="paper:pattern-select" initialSection="FINREZ"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);

    expect(await screen.findByText("BTCUSDT")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Выбор паттерна" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Сделки" }));
    expect(await screen.findByText("Клин ↘")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Triangle Compression" })).toBeInTheDocument();
    expect(screen.getByText("не установлен")).toBeInTheDocument();
    const pattern = screen.getByRole("combobox", { name: "Выбор паттерна" });
    const ticker = screen.getByRole("searchbox", { name: "Поиск по тикеру" });

    fireEvent.change(pattern, { target: { value: "Falling Wedge" } });
    expect(screen.getByText("BTCUSDT")).toBeInTheDocument();
    expect(screen.queryByText("ETHUSDT")).not.toBeInTheDocument();
    expect(screen.queryByText("XRPUSDT")).not.toBeInTheDocument();

    fireEvent.change(ticker, { target: { value: "eth" } });
    expect(await screen.findByText("По выбранным фильтрам сделок нет")).toBeInTheDocument();
    expect(pattern).toHaveValue("Falling Wedge");
    fireEvent.change(pattern, { target: { value: "Triangle Compression" } });
    expect(screen.getByText("ETHUSDT")).toBeInTheDocument();
    expect(screen.queryByText("BTCUSDT")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Неделя" }));
    await waitFor(() => expect(mockFetch).toHaveBeenCalledWith(
      "/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=WEEK",
    ));
    expect(await screen.findByRole("button", { name: /ETHUSDT/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Triangle Compression" })).toBeInTheDocument();
    expect(pattern).toHaveValue("Triangle Compression");
    expect(ticker).toHaveValue("ETH");

    // The pattern selector is Deals-only and preserves its exact selection across sections.
    fireEvent.click(screen.getByRole("button", { name: "Финрез" }));
    expect(screen.queryByRole("combobox", { name: "Выбор паттерна" })).not.toBeInTheDocument();
    expect(await screen.findByText("+7,20 USDT")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Сделки" }));
    expect(await screen.findByRole("button", { name: /ETHUSDT/ })).toBeInTheDocument();
    const reopenedPattern = screen.getByRole("combobox", { name: "Выбор паттерна" });
    const reopenedTicker = screen.getByRole("searchbox", { name: "Поиск по тикеру" });
    expect(reopenedPattern).toHaveValue("Triangle Compression");

    fireEvent.change(reopenedTicker, { target: { value: "" } });
    fireEvent.change(reopenedPattern, { target: { value: "__NO_VERIFIED_PATTERN__" } });
    expect(screen.getByText("XRPUSDT")).toBeInTheDocument();
    expect(screen.queryByText("BTCUSDT")).not.toBeInTheDocument();
    fireEvent.change(reopenedPattern, { target: { value: "" } });
    expect(screen.getByText("BTCUSDT")).toBeInTheDocument();
    expect(screen.getByText("ETHUSDT")).toBeInTheDocument();
    expect(screen.getByText("XRPUSDT")).toBeInTheDocument();
    expect(mockFetch.mock.calls.filter(([url]) => String(url).includes("/episode-facts"))).toHaveLength(0);
  });

  it("rounds ticker PnL and opens only that ticker's confirmed episodes on click", async () => {
    const btc = {
      trade_episode_id: "te_" + "a".repeat(24), symbol: "BTCUSDT", side: "LONG",
      opened_at_ms: 1_793_001_000_000, closed_at_ms: 1_793_002_000_000,
      pnl_usdt: "-2.5012345678", execution_count: 2,
      cohort: "ROBOT", replay_evidence: "EPISODE_INDEX_ONLY",
    };
    const eth = { ...btc, trade_episode_id: "te_" + "b".repeat(24), symbol: "ETHUSDT" };
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({
      ...finrezResponse,
      tickers: [
        { symbol: "BTCUSDT", pnl_usdt: "-2.5012345678", trade_count: 1 },
        { symbol: "ETHUSDT", pnl_usdt: "7.2012345678", trade_count: 1 },
      ],
      closed_episodes: [btc, eth],
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<DiaryOverlay accountKey="paper:finrez-filter" initialSection="FINREZ"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    expect(await screen.findByText("+7,20 USDT")).toBeInTheDocument();
    expect(screen.getByText("-2,50 USDT")).toBeInTheDocument();
    expect(screen.queryByText(/2\.5012345678/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Показать сделки по BTCUSDT" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(await screen.findByText("Сделки по BTCUSDT")).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Поиск по тикеру" })).toHaveValue("BTCUSDT");
    expect(screen.getByText("BTCUSDT")).toBeInTheDocument();
    expect(screen.queryByText("ETHUSDT")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Подробности сделки" })).toBeInTheDocument();
    expect(screen.getByText("не установлен")).toBeInTheDocument();
    expect(screen.getByText("(—)")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "← Все сделки" }));
    expect(screen.getByText("ETHUSDT")).toBeInTheDocument();
    expect(screen.queryByText("Сделки по BTCUSDT")).not.toBeInTheDocument();
  });


  it("filters aggregate ticker rows and exact closed episodes through the shared search", async () => {
    const btc = {
      trade_episode_id: "te_" + "c".repeat(24), symbol: "BTCUSDT", side: "LONG",
      opened_at_ms: 1_793_001_000_000, closed_at_ms: 1_793_002_000_000,
      pnl_usdt: "-2.5", execution_count: 2, cohort: "ROBOT",
      replay_evidence: "EPISODE_INDEX_ONLY",
    };
    const eth = { ...btc, trade_episode_id: "te_" + "d".repeat(24), symbol: "ETHUSDT" };
    const fetchMock = vi.fn().mockImplementation(async (url: string) => new Response(JSON.stringify({
      ...finrezResponse,
      period: (new URL(url, "http://localhost").searchParams.get("period") ?? "DAY"),
      closed_episodes: [btc, eth],
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<DiaryOverlay accountKey="paper:search" initialSection="FINREZ"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);

    const search = screen.getByRole("searchbox", { name: "Поиск по тикеру" });
    expect(await screen.findByText("+7,20 USDT")).toBeInTheDocument();
    fireEvent.change(search, { target: { value: "btc" } });
    expect(search).toHaveValue("BTC");
    expect(screen.getByText("BTCUSDT")).toBeInTheDocument();
    expect(screen.queryByText("ETHUSDT")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Всё время" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=ALL",
    ));
    expect(search).toHaveValue("BTC");
    fireEvent.click(screen.getByRole("button", { name: "Показать сделки по BTCUSDT" }));
    await screen.findByText("Сделки по BTCUSDT");
    expect(screen.getByRole("button", { name: "Всё время" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByText("ETHUSDT")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Подробности сделки" })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("searchbox", { name: "Поиск по тикеру" }), {
      target: { value: "ETH" },
    });
    expect(await screen.findByText("Сделки по ETH")).toBeInTheDocument();
    expect(screen.queryByText("BTCUSDT")).not.toBeInTheDocument();
    expect(screen.getByText("ETHUSDT")).toBeInTheDocument();
  });

  it("shows the exact money-weighted Finrez split above tickers and filters without changing period totals", async () => {
    const episode = (id: string, symbol: string, pnl_usdt: string,
      cohort: "ROBOT" | "ROBOT_MANUAL_CLOSE" | "JOINT_MANAGEMENT" = "ROBOT") => ({
      trade_episode_id: "te_" + id.repeat(24), symbol, side: "LONG" as const,
      opened_at_ms: 1_793_001_000_000, closed_at_ms: 1_793_002_000_000,
      pnl_usdt, execution_count: 2, cohort,
      replay_evidence: "EPISODE_INDEX_ONLY" as const,
    });
    const fetchMock = vi.fn().mockImplementation(async (url: string) => new Response(JSON.stringify({
      ...finrezResponse,
      period: new URL(url, "http://localhost").searchParams.get("period") ?? "DAY",
      tickers: [
        { symbol: "ETHUSDT", pnl_usdt: "4.0", trade_count: 2 },
        { symbol: "BTCUSDT", pnl_usdt: "-3", trade_count: 1 },
      ],
      closed_episodes: [
        episode("a", "ETHUSDT", "6.0"),
        episode("b", "ETHUSDT", "-2.0"),
        episode("c", "BTCUSDT", "-3"),
        episode("d", "EXCLUDEDUSDT", "-90", "ROBOT_MANUAL_CLOSE"),
        episode("e", "SHAREDUSDT", "+25", "JOINT_MANAGEMENT"),
      ],
      manual_interventions: [{ symbol: "EXCLUDEDUSDT", pnl_usdt: "-90", trade_count: 1 }],
      joint_management: [{ symbol: "SHAREDUSDT", pnl_usdt: "25", trade_count: 1 }],
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<DiaryOverlay accountKey="paper:finrez-money" initialSection="FINREZ"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    const money = await screen.findByRole("group", { name: "Финрез: прибыль и убыток в USDT" });
    expect(money).toHaveTextContent("Прибыль: +6,00 USDT");
    expect(money).toHaveTextContent("Убыток: -5,00 USDT");
    expect(screen.getByRole("button", { name: "Показать все тикеры" })).toHaveTextContent("Итог+1,00 USDT");
    const profitSegment = screen.getByRole("button", { name: "Прибыль за период" });
    const lossSegment = screen.getByRole("button", { name: "Убыток за период" });
    expect(Number.parseFloat(profitSegment.style.width)).toBeCloseTo(600 / 11, 4);
    expect(Number.parseFloat(lossSegment.style.width)).toBeCloseTo(500 / 11, 4);
    fireEvent.click(profitSegment);
    expect(profitSegment).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("ETHUSDT")).toBeInTheDocument();
    expect(screen.queryByText("BTCUSDT")).not.toBeInTheDocument();
    expect(money).toHaveTextContent("Итог+1,00 USDT");
    fireEvent.click(screen.getByRole("button", { name: "Показать все тикеры" }));
    expect(screen.getByText("BTCUSDT")).toBeInTheDocument();
    fireEvent.click(lossSegment);
    expect(screen.queryByText("ETHUSDT")).not.toBeInTheDocument();
    expect(screen.getByText("BTCUSDT")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("searchbox", { name: "Поиск по тикеру" }), {
      target: { value: "ETH" },
    });
    expect(screen.getByText("Нет тикеров с выбранным результатом")).toBeInTheDocument();
    expect(money).toHaveTextContent("Итог+1,00 USDT");
    fireEvent.click(screen.getByRole("button", { name: "Неделя" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=WEEK",
    ));
    expect(await screen.findByRole("group", { name: "Финрез: прибыль и убыток в USDT" }))
      .toHaveTextContent("Итог+1,00 USDT");
  });

  it("withholds an unreconciled Finrez total rather than summing unverified ticker rows", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ...finrezResponse,
      closed_episodes: [{
        trade_episode_id: "te_" + "a".repeat(24), symbol: "ETHUSDT", side: "LONG",
        opened_at_ms: 1_793_001_000_000, closed_at_ms: 1_793_002_000_000,
        pnl_usdt: "6", execution_count: 2, cohort: "ROBOT",
        replay_evidence: "EPISODE_INDEX_ONLY",
      }],
    }), { status: 200 })));
    render(<DiaryOverlay accountKey="paper:finrez-unreconciled" initialSection="FINREZ"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    expect(await screen.findByText(/Полоса прибыли и убытка пока недоступна/)).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Финрез: прибыль и убыток в USDT" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Показать все тикеры" })).not.toBeInTheDocument();
    expect(screen.getByText("ETHUSDT")).toBeInTheDocument();
  });

  it("displays compact, exact-tooltip Finrez PnL for all management cohorts", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ...finrezResponse,
      tickers: [
        { symbol: "GIGADEVICEUSDT", pnl_usdt: "4.3583303660000000000004", trade_count: 1 },
        { symbol: "TINYUSDT", pnl_usdt: "0.0000000004", trade_count: 1 },
        { symbol: "ZEROUSDT", pnl_usdt: "0", trade_count: 1 },
      ],
      manual_interventions: [
        { symbol: "JASMYUSDT", pnl_usdt: "-0.0026140884", trade_count: 1 },
      ],
      joint_management: [
        { symbol: "CASHCATUSDT", pnl_usdt: "-1.8162218600000000000000", trade_count: 1 },
      ],
    }), { status: 200 })));
    render(<DiaryOverlay accountKey="paper:compact" initialSection="FINREZ"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    expect(await screen.findByTitle("GIGADEVICEUSDT")).toHaveTextContent("GIGADEVICEUSDT");
    expect(screen.getByTitle("4.3583303660000000000004 USDT")).toHaveTextContent("+4,36 USDT");
    expect(screen.getByTitle("0.0000000004 USDT")).toHaveTextContent("+<0,01 USDT");
    expect(screen.getByTitle("0 USDT")).toHaveTextContent("0 USDT");
    expect(screen.getByTitle("-0.0026140884 USDT")).toHaveTextContent("-<0,01 USDT");
    expect(screen.getByTitle("-1.8162218600000000000000 USDT")).toHaveTextContent("-1,82 USDT");
  });

  it("never shows foreign-account ranking or silently falls back to manual", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ ...finrezResponse, owner: "MANUAL" }), { status: 200 },
    ));
    vi.stubGlobal("fetch", fetchMock);
    render(<DiaryOverlay accountKey="paper:1" initialSection="FINREZ"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    expect(await screen.findByText("Не удалось загрузить статистику выбранного счёта")).toBeInTheDocument();
    expect(screen.queryByText("ETHUSDT")).not.toBeInTheDocument();
  });
  it("shows robot-initiated manually closed deals separately and never includes them in autonomous PnL", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ...finrezResponse,
      tickers: [],
      manual_interventions: [{ symbol: "BTCUSDT", pnl_usdt: "-4.5", trade_count: 1 }],
    }), { status: 200 })));
    render(<DiaryOverlay accountKey="paper:2" initialSection="FINREZ"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    expect(await screen.findByRole("region", { name: "Ручные закрытия сделок робота" })).toBeInTheDocument();
    expect(screen.getByText("Робот · ручное вмешательство")).toBeInTheDocument();
    expect(screen.getByText("-4,50 USDT")).toBeInTheDocument();
    expect(screen.getByText("Сегодня с 00:00 МСК нет подтверждённых закрытых сделок Робота")).toBeInTheDocument();
    expect(screen.getByText(/В PnL полностью роботизированных сделок не включён/)).toBeInTheDocument();
  });

  it("rejects mixed-controller rows in MANUAL response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ...finrezResponse,
      owner: "MANUAL",
      tickers: [],
      manual_interventions: [{ symbol: "BTCUSDT", pnl_usdt: "-2", trade_count: 1 }],
    }), { status: 200 })));
    render(<DiaryOverlay accountKey="paper:3" initialSection="FINREZ"
      statisticsScope={{ accountId: "paper", owner: "MANUAL" }} onClose={() => {}} />);
    expect(await screen.findByText("Не удалось загрузить статистику выбранного счёта")).toBeInTheDocument();
    expect(screen.queryByText("-2 USDT")).not.toBeInTheDocument();
  });

  it("explicitly warns about partial attribution and never calls an unknown result zero", async () => {
    const fetchMock = vi.fn().mockImplementation(async (url: string) => new Response(JSON.stringify({
      ...finrezResponse,
      period: (new URL(url, "http://localhost").searchParams.get("period") ?? "DAY"),
      tickers: [],
      attribution_coverage: url.includes("period=ALL") ? {
        status: "PARTIAL",
        excluded_unattributed_episode_count: 3,
        excluded_unattributed_execution_count: 11,
      } : finrezResponse.attribution_coverage,
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<DiaryOverlay accountKey="paper:4" initialSection="FINREZ"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    expect(await screen.findByText("Сегодня с 00:00 МСК нет подтверждённых закрытых сделок Робота")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Всё время" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=ALL"));
    const coverage = await screen.findByText(/Не все сделки учтены/);
    expect(coverage).toHaveTextContent("Не все сделки учтены");
    expect(coverage).toHaveTextContent("у 3 закрытых");
    expect(coverage).toHaveTextContent("11 исполнений");
    expect(coverage).toHaveTextContent("только по проверенным сделкам");
    expect(screen.getByText(/Нет достоверно атрибутированных закрытых сделок/)).toBeInTheDocument();
    expect(screen.queryByText("Сегодня с 00:00 МСК нет подтверждённых закрытых сделок Робота")).not.toBeInTheDocument();
  });

  it("shows the same shared economic episode in both scopes without claiming either owned it", async () => {
    const shared = [{ symbol: "BTCUSDT", pnl_usdt: "-11.4", trade_count: 1 }];
    const fetchMock = vi.fn().mockImplementation(async (url: string) => new Response(JSON.stringify({
      ...finrezResponse,
      owner: url.includes("owner=MANUAL") ? "MANUAL" : "ROBOT",
      tickers: [],
      joint_management: shared,
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const current = render(<DiaryOverlay accountKey="paper:joint-robot" initialSection="FINREZ"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    const section = await screen.findByRole("region", { name: "Совместно управляемые сделки" });
    expect(section).toHaveTextContent("-11,40 USDT");
    expect(section).toHaveTextContent("не складывайте его дважды");
    expect(screen.getByText("Сегодня с 00:00 МСК нет подтверждённых закрытых сделок Робота")).toBeInTheDocument();
    current.rerender(<DiaryOverlay accountKey="paper:joint-manual" initialSection="FINREZ"
      statisticsScope={{ accountId: "paper", owner: "MANUAL" }} onClose={() => {}} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/diary/ticker-finrez?account_id=paper&owner=MANUAL&period=DAY",
    ));
    expect(await screen.findByRole("region", { name: "Совместно управляемые сделки" })).toHaveTextContent("-11,40 USDT");
    expect(screen.getAllByText("-11,40 USDT")).toHaveLength(1);
  });

  it("rejects a missing or invalid shared-management contract", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ...finrezResponse,
      joint_management: [{ symbol: "BTCUSDT", pnl_usdt: "NaN", trade_count: 1 }],
    }), { status: 200 })));
    render(<DiaryOverlay accountKey="paper:joint-invalid" initialSection="FINREZ"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    expect(await screen.findByText("Не удалось загрузить статистику выбранного счёта")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Совместно управляемые сделки" })).not.toBeInTheDocument();
  });

  it("rejects missing or contradictory coverage instead of showing an apparently complete report", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ...finrezResponse,
      attribution_coverage: { status: "COMPLETE",
        excluded_unattributed_episode_count: 2,
        excluded_unattributed_execution_count: 2 },
    }), { status: 200 })));
    render(<DiaryOverlay accountKey="paper:5" initialSection="FINREZ"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    expect(await screen.findByText("Не удалось загрузить статистику выбранного счёта")).toBeInTheDocument();
    expect(screen.queryByText("ETHUSDT")).not.toBeInTheDocument();
  });

});

describe("shared statistics trade action standard", () => {
  it("compacts wedge cards with independent direction and profit colors", async () => {
    const makeDeal = (id: string, symbol: string, side: "LONG" | "SHORT",
      pattern: "Falling Wedge" | "Rising Wedge", pnl_usdt: string,
      pnl_pct: string, entry_notional_usdt: string) => ({
      trade_episode_id: "te_" + id.repeat(24), symbol, side,
      opened_at_ms: 1_793_001_000_000, closed_at_ms: 1_793_002_000_000,
      pnl_usdt, pnl_pct, entry_notional_usdt,
      pnl_pct_basis: "KNOWN_COST_PNL_OVER_EXECUTED_ENTRY_NOTIONAL",
      execution_count: 8, cohort: "ROBOT", opening_controller: "ROBOT",
      replay_evidence: "EPISODE_INDEX_ONLY",
      setup_context: {
        status: "EXACT_D2_LINK", source: "TRADING_DIARY_D2",
        consistency: "INDEPENDENT_READ_SNAPSHOT_NOT_ATOMIC_WITH_PAPER",
        decision_scope: "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG",
        setup: {
          setup_id: "candidate-" + id, symbol, direction: side, origin: "ROBOT",
          pattern, timeframe: "5", strategy_version: "robot-v2",
          created_at_ms: 1_793_000_000_000,
        },
      },
    });
    const longLoss = makeDeal("a", "BEATUSDT", "LONG", "Falling Wedge",
      "-0.2727", "-0.63", "43.285714285714286");
    const shortProfit = makeDeal("b", "TESTUSDT", "SHORT", "Rising Wedge",
      "1.1684", "0.62", "188.4516129032258");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ...finrezResponse, closed_episodes: [longLoss, shortProfit],
    }), { status: 200 })));
    render(<DiaryOverlay accountKey="paper:compact-deals" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);

    const longRow = await screen.findByRole("button", { name: /BEATUSDT/ });
    expect(longRow).toHaveClass("diary-closed-deal-row", "pnl-negative");
    expect(longRow.querySelector(".diary-trade-heading")).toHaveTextContent("Клин ↘");
    expect(longRow.querySelector(".diary-trade-side.long")).toHaveTextContent("LONG");
    expect(longRow.querySelector(".diary-trade-meta")).toHaveTextContent(/Робот.*→/);
    expect(longRow).toHaveTextContent("PnL: -0,27 USDT (-0,63%)");
    expect(longRow).toHaveTextContent("Исполнений: 8");
    expect(longRow).not.toHaveTextContent("Паттерн:");

    const shortRow = screen.getByRole("button", { name: /TESTUSDT/ });
    expect(shortRow).toHaveClass("diary-closed-deal-row", "pnl-positive");
    expect(shortRow.querySelector(".diary-trade-heading")).toHaveTextContent("Клин ↗");
    expect(shortRow.querySelector(".diary-trade-side.short")).toHaveTextContent("SHORT");
    expect(shortRow).toHaveTextContent("PnL: +1,17 USDT (+0,62%)");
  });

  it("renders source-verified entry-notional return, not guessed leveraged ROI", async () => {
    const base = {
      trade_episode_id: "te_" + "a".repeat(24), symbol: "BTCUSDT", side: "LONG",
      opened_at_ms: 1_793_001_000_000, closed_at_ms: 1_793_002_000_000,
      pnl_usdt: "4.8", execution_count: 2, cohort: "ROBOT",
      replay_evidence: "EPISODE_INDEX_ONLY",
    };
    const matched = {
      ...base, pnl_pct: "2.4",
      entry_notional_usdt: "200",
      pnl_pct_basis: "KNOWN_COST_PNL_OVER_EXECUTED_ENTRY_NOTIONAL",
    };
    const unsupported = {
      ...base, trade_episode_id: "te_" + "b".repeat(24), symbol: "ETHUSDT",
      pnl_pct: "50", entry_notional_usdt: "200",
      pnl_pct_basis: "KNOWN_COST_PNL_OVER_EXECUTED_ENTRY_NOTIONAL",
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ...finrezResponse, closed_episodes: [matched, unsupported],
    }), { status: 200 })));
    render(<DiaryOverlay accountKey="paper:percent" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    expect(await screen.findByText("(+2,40%)")).toBeInTheDocument();
    expect(screen.getByText("(—)")).toHaveAttribute(
      "title", "Процент недоступен без подтверждённой базы расчёта",
    );
    expect(screen.getByText("(+2,40%)")).toHaveAttribute("title",
      expect.stringContaining("Не ROI на маржу"));
    fireEvent.click(screen.getByRole("button", { name: /BTCUSDT/ }));
    expect(screen.getByText("PnL % от номинала входа")).toBeInTheDocument();
    expect(screen.getByText("+2,40%")).toBeInTheDocument();
    expect(screen.getByText("Фактический номинал входов")).toBeInTheDocument();
    expect(screen.getByText("200,00 USDT")).toBeInTheDocument();
  });


  it("shows only exact, source-checked D2 pattern on the selected closed episode and remembers it in the list", async () => {
    const deal = {
      trade_episode_id: "te_" + "1".repeat(24), symbol: "BTCUSDT", side: "LONG",
      opened_at_ms: 1_793_001_000_000, closed_at_ms: 1_793_002_000_000,
      pnl_usdt: "-1.25", execution_count: 1, cohort: "ROBOT",
      replay_evidence: "EPISODE_INDEX_ONLY",
    };
    const context = {
      status: "EXACT_D2_LINK", source: "TRADING_DIARY_D2",
      consistency: "INDEPENDENT_READ_SNAPSHOT_NOT_ATOMIC_WITH_PAPER",
      decision_scope: "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG",
      geometry_status: "NOT_EXPORTED",
      setup: {
        setup_id: "candidate-1", symbol: "BTCUSDT", direction: "LONG",
        origin: "ROBOT", pattern: "Falling Wedge", timeframe: "5",
        strategy_version: "robot-v2", created_at_ms: deal.opened_at_ms - 1000,
      },
    };
    const facts = {
      ok: true, schema: "BYBITSCANNER_CLOSED_EPISODE_FACTS_V1",
      namespace: "PAPER_READ_ONLY", source: "PAPER_EXECUTIONS_ATTRIBUTED",
      account_id: "paper", owner: "ROBOT", source_revision: 3,
      trade_episode_id: deal.trade_episode_id, symbol: deal.symbol, side: deal.side,
      cohort: deal.cohort, opened_at_ms: deal.opened_at_ms,
      closed_at_ms: deal.closed_at_ms, pnl_usdt: deal.pnl_usdt,
      replay_evidence: "EXECUTION_FACTS_ONLY_NO_DECISIONS_OR_CANDLES",
      execution_allocations: [{
        execution_id: "fill-1", controller: "ROBOT", execution_price: "101",
        occurred_at_ms: deal.opened_at_ms + 100,
      }],
      setup_context: context,
    };
    const fetchMock = vi.fn().mockImplementation(async (url: string) =>
      new Response(JSON.stringify(url.includes("/episode-facts") ? facts :
        { ...finrezResponse, closed_episodes: [deal] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    render(<DiaryOverlay accountKey="paper:exact-d2" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    expect(await screen.findByText("не установлен")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Подробности сделки" }));
    const section = await screen.findByRole("region", { name: "Связь сделки с паттерном" });
    await waitFor(() => expect(section).toHaveTextContent("Falling Wedge"));
    expect(section).toHaveTextContent("candidate-1");
    expect(section).toHaveTextContent("robot-v2");
    expect(section).toHaveTextContent("не полный журнал решений Робота");
    fireEvent.click(screen.getByRole("button", { name: "← К сделкам" }));
    expect(screen.getByText("Клин ↘")).toBeInTheDocument();
    expect(screen.getByText("(—)")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/episode-facts"))).toHaveLength(1);
  });

  it("refuses contradictory D2 pattern despite otherwise valid execution evidence", async () => {
    const deal = {
      trade_episode_id: "te_" + "2".repeat(24), symbol: "BTCUSDT", side: "LONG",
      opened_at_ms: 1_793_001_000_000, closed_at_ms: 1_793_002_000_000,
      pnl_usdt: "-1.25", execution_count: 1, cohort: "ROBOT",
      replay_evidence: "EPISODE_INDEX_ONLY",
    };
    const facts = {
      ok: true, schema: "BYBITSCANNER_CLOSED_EPISODE_FACTS_V1",
      namespace: "PAPER_READ_ONLY", source: "PAPER_EXECUTIONS_ATTRIBUTED",
      account_id: "paper", owner: "ROBOT", source_revision: 3,
      trade_episode_id: deal.trade_episode_id, symbol: deal.symbol, side: deal.side,
      cohort: deal.cohort, opened_at_ms: deal.opened_at_ms,
      closed_at_ms: deal.closed_at_ms, pnl_usdt: deal.pnl_usdt,
      replay_evidence: "EXECUTION_FACTS_ONLY_NO_DECISIONS_OR_CANDLES",
      execution_allocations: [{
        execution_id: "fill-1", controller: "ROBOT", execution_price: "101",
        occurred_at_ms: deal.opened_at_ms + 100,
      }],
      setup_context: {
        status: "EXACT_D2_LINK", source: "TRADING_DIARY_D2",
        consistency: "INDEPENDENT_READ_SNAPSHOT_NOT_ATOMIC_WITH_PAPER",
        decision_scope: "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG",
        setup: {
          setup_id: "candidate-wrong", symbol: "ETHUSDT", direction: "LONG",
          origin: "ROBOT", pattern: "Triangle Compression", timeframe: "5",
          strategy_version: "robot-v2", created_at_ms: deal.opened_at_ms - 1000,
        },
      },
    };
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async (url: string) =>
      new Response(JSON.stringify(url.includes("/episode-facts") ? facts :
        { ...finrezResponse, closed_episodes: [deal] }), { status: 200 })));
    render(<DiaryOverlay accountKey="paper:contradictory-d2" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "Подробности сделки" }));
    expect(await screen.findByText("Связь с паттерном по точному ID не подтверждена."))
      .toBeInTheDocument();
    expect(screen.queryByText("Triangle Compression")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "← К сделкам" }));
    expect(screen.getByText("не установлен")).toBeInTheDocument();
  });

  it("formats only visible deal PnL to two decimal places", () => {
    expect(displayTradePnl("-1.81622186")).toBe("-1,82");
    expect(displayTradePnl("7.2")).toBe("7,20");
    expect(displayTradePnl("0")).toBe("0,00");
    expect(displayTradePnl(null)).toBe("—");
    expect(displayTradePnl("NaN")).toBe("—");
  });

  it("draws only matched execution prices without inventing candles", async () => {
    const episodeId = "te_" + "d".repeat(24);
    const deal = {
      trade_episode_id: episodeId, symbol: "BTCUSDT", side: "LONG",
      opened_at_ms: 1_793_001_000_000, closed_at_ms: 1_793_002_000_000,
      pnl_usdt: "1.2378", execution_count: 2,
      cohort: "ROBOT", replay_evidence: "EPISODE_INDEX_ONLY",
    };
    const facts = {
      ok: true, schema: "BYBITSCANNER_CLOSED_EPISODE_FACTS_V1",
      namespace: "PAPER_READ_ONLY", source: "PAPER_EXECUTIONS_ATTRIBUTED",
      account_id: "paper", owner: "ROBOT", source_revision: 3,
      trade_episode_id: episodeId, symbol: "BTCUSDT", side: "LONG",
      cohort: "ROBOT", opened_at_ms: deal.opened_at_ms,
      closed_at_ms: deal.closed_at_ms, pnl_usdt: deal.pnl_usdt,
      replay_evidence: "EXECUTION_FACTS_ONLY_NO_DECISIONS_OR_CANDLES",
      execution_allocations: [
        { execution_id: "fill-a", execution_price: "101.259",
          occurred_at_ms: 1_793_001_010_000 },
        { execution_id: "fill-b", execution_price: "101.985",
          occurred_at_ms: 1_793_001_950_000 },
      ],
    };
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
      new Response(JSON.stringify(String(input).includes("episode-facts") ? facts :
        { ...finrezResponse, closed_episodes: [deal] }), { status: 200 }));
    render(<DiaryOverlay accountKey="paper:chart" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    const magnifier = await screen.findByRole("button", { name: "Подробности сделки" });
    fireEvent.click(magnifier);
    expect(await screen.findByRole("img", {
      name: "Фактические цены исполнений сделки по времени",
    })).toBeInTheDocument();
    expect(screen.getByText("График цен исполнений · не свечной график")).toBeInTheDocument();
    expect(screen.getByText(/Это не воспроизведение/)).toBeInTheDocument();
  });

  it("filmstrip requests one exact verified JSON without launching a guessed local URI", async () => {
    const episodeId = "te_" + "c".repeat(24);
    const requestId = "d".repeat(32);
    const clicked: string[] = [];
    vi.stubGlobal("navigator", { userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" });
    const anchor = vi.spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        clicked.push(this.getAttribute("href") || "");
      });
    try {
      const fetchMock = vi.fn().mockImplementation(async (url: string) => {
        if (url.endsWith("/simulator-bridge/request")) return new Response(JSON.stringify({
          ok: true, state: "QUEUED", request_id: requestId,
        }), { status: 200 });
        if (url.endsWith("/simulator-bridge/status")) return new Response(JSON.stringify({
          ok: true, state: "LAUNCHED", request_id: requestId,
        }), { status: 200 });
        return new Response(JSON.stringify({
          ...finrezResponse,
          closed_episodes: [{
            trade_episode_id: episodeId, symbol: "BTCUSDT", side: "LONG",
            opened_at_ms: 1_793_001_000_000, closed_at_ms: 1_793_002_000_000,
            pnl_usdt: "-2.501234567", execution_count: 2,
            cohort: "ROBOT", replay_evidence: "EPISODE_INDEX_ONLY",
          }],
        }), { status: 200 });
      });
      vi.stubGlobal("fetch", fetchMock);
      render(<DiaryOverlay accountKey="paper:film" initialSection="DEALS"
        statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
      const film = await screen.findByRole("button", { name: "Открыть сделку в Симуляторе" });
      expect(film).toBeEnabled();
      fireEvent.click(film);
      expect(await screen.findByText(/Локальный адаптер сохранил JSON исполнений/))
        .toHaveTextContent("Полный журнал решений Робота не подтверждён");
      expect(clicked).toEqual([]);
      expect(fetchMock).toHaveBeenCalledWith("/api/diary/simulator-bridge/request", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          episode_id: episodeId, owner: "ROBOT", source_revision: 3,
        }),
      });
      expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/local-replay/history")))
        .toHaveLength(0); // Public M5 is fetched ONLY by the local viewer.
    } finally {
      anchor.mockRestore();
    }
  });

  it("shares the two-button layout with other account scopes without changing raw PnL", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      ...tradesResponse, active_account_id: "bybit-main", environment: "LIVE",
      trades: [{ ...tradesResponse.trades[0], environment: "LIVE", pnl: "0.125001" }],
    }), { status: 200 }));
    render(<DiaryOverlay accountKey="bybit-main" initialSection="TRADES"
      statisticsScope={{ accountId: "bybit-main", owner: "MANUAL" }} onClose={() => {}} />);
    const row = await screen.findByRole("button", { name: /BTCUSDT/ });
    expect(row).toHaveTextContent("PnL 0,13");
    const magnifier = screen.getByRole("button", { name: "Подробности сделки" });
    expect(magnifier).toBeEnabled();
    expect(screen.getByRole("button", { name: "Открыть сделку в Симуляторе" })).toBeDisabled();
    fireEvent.click(magnifier);
    expect(screen.getByText("Эпизод сделки")).toBeInTheDocument();
  });

  it("keeps two icon action slots on every closed deal without faking full replay", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        ...finrezResponse,
        closed_episodes: [
          { trade_episode_id: "episode-shared", symbol: "XRPUSDT", side: "SHORT",
            opened_at_ms: 1_793_001_500_000, closed_at_ms: 1_793_003_000_000,
            pnl_usdt: "-1.81622186", execution_count: 7,
            cohort: "JOINT_MANAGEMENT", replay_evidence: "EPISODE_INDEX_ONLY" },
          { trade_episode_id: "episode-robot", symbol: "BTCUSDT", side: "LONG",
            opened_at_ms: 1_793_001_000_000, closed_at_ms: 1_793_002_000_000,
            pnl_usdt: "-4.8", execution_count: 2,
            cohort: "ROBOT", replay_evidence: "EPISODE_INDEX_ONLY" },
        ],
      }), { status: 200 }),
    );
    render(<DiaryOverlay accountKey="paper" onClose={() => {}} initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} />);
    expect((await screen.findAllByRole("button", { name: "Подробности сделки" })).length).toBe(2);
    const replay = screen.getAllByRole("button", { name: "Открыть сделку в Симуляторе" });
    expect(replay).toHaveLength(2);
    replay.forEach((button) => {
      expect(button).toBeDisabled();
      expect(button).toHaveAttribute("title", expect.stringContaining("нужен подтверждённый PAPER episode"));
      const filmstrip = button.querySelector("svg.diary-filmstrip-icon");
      expect(filmstrip).toHaveAttribute("viewBox", "0 0 24 24");
      expect(filmstrip?.querySelector("rect")).toHaveAttribute("width", "19.6");
      expect(filmstrip?.querySelector("rect")).toHaveAttribute("height", "16");
      expect(filmstrip?.querySelectorAll("rect")).toHaveLength(7);
      expect(filmstrip?.querySelectorAll("path")).toHaveLength(1);
    });
    expect(screen.getByText(/PnL: -1,82 USDT/)).toHaveAttribute("title", "-1.81622186");
  });
});

describe("Verified Wedge lineage in Statistics", () => {
  const episodeId = "te_" + "a".repeat(24);
  const verified = {
    trade_episode_id: episodeId,
    source_revision: 3, candidate_id: "candidate-42",
    pattern: "Falling Wedge", source_timeframe: "M5",
    provenance: "DURABLE_ROBOT_TRADE_METADATA_NOT_ORIGINAL_GEOMETRY",
    evidence_scope: "EXACT_WEDGE_CANDIDATE_ENTRY_ORDER_EXECUTION_EPISODE",
    status: "PROVEN",
  };
  const deal = {
    trade_episode_id: episodeId, symbol: "BTCUSDT", side: "LONG",
    opened_at_ms: 1_793_001_000_000, closed_at_ms: 1_793_002_000_000,
    pnl_usdt: "-2.5", execution_count: 2, cohort: "ROBOT",
    replay_evidence: "EPISODE_INDEX_ONLY",
    setup_context: { status: "NO_EXACT_EPISODE_LINK" },
    verified_signal: verified,
  };
  const mockReport = (deals: unknown[], owner = "ROBOT") => ({
    ...finrezResponse, owner, closed_episodes: deals,
  });

  it("groups proven Wedge without D2, filters its deals and shows distinct provenance", async () => {
    const fetchMock = vi.fn().mockImplementation(async (url: string) =>
      new Response(JSON.stringify({
        ...mockReport([deal]),
        period: new URL(url, "http://localhost").searchParams.get("period") ?? "DAY",
      }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<DiaryOverlay accountKey="paper:wedge" initialSection="PATTERNS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    const region = await screen.findByRole("region", { name: "Паттерны по подтверждённым сделкам" });
    expect(region).toHaveTextContent("С подтверждённым паттерном: 1 из 1");
    expect(region).toHaveTextContent("Wedge: 1");
    expect(region).toHaveTextContent("Робот · сделок: 1 · прибыльных: 0 · убыточных: 1");
    expect(screen.getByTitle("-2.5 USDT")).toHaveTextContent("-2,50 USDT");
    fireEvent.click(screen.getByRole("button", { name: "Показать все сделки по паттерну Falling Wedge" }));
    expect(await screen.findByText("Клин ↘")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Выбор паттерна" })).toHaveValue("Falling Wedge");
    fireEvent.click(screen.getByRole("button", { name: /BTCUSDT/ }));
    expect(screen.getByText("candidate-42")).toBeInTheDocument();
    expect(screen.getByText(/Не D2, без исходной геометрии/)).toBeInTheDocument();
    expect(screen.queryByText("Версия стратегии")).not.toBeInTheDocument();
  });

  it("accepts exact non-Wedge Robot entry proof without inventing original geometry", async () => {
    const example = {
      ...deal,
      verified_signal: {
        ...verified, pattern: "Double Bottom",
        evidence_scope: "EXACT_ROBOT_CANDIDATE_ENTRY_ORDER_EXECUTION_EPISODE",
      },
    };
    const fetchMock = vi.fn().mockImplementation(async (url: string) => {
      if (url.startsWith("/api/diary/episode-facts")
          || url.startsWith("/api/workspace/signal-geometry")) {
        return new Response("", { status: 404 });
      }
      return new Response(JSON.stringify(mockReport([example])), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<DiaryOverlay accountKey="paper:nonwedge-source" initialSection="PATTERNS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    const region = await screen.findByRole("region", { name: "Паттерны по подтверждённым сделкам" });
    expect(region).toHaveTextContent("С подтверждённым паттерном: 1 из 1");
    expect(region).toHaveTextContent("Robot ID: 1");
    fireEvent.click(screen.getByRole("button", { name: "Показать все сделки по паттерну Double Bottom" }));
    expect(await screen.findByRole("combobox", { name: "Выбор паттерна" })).toHaveValue("Double Bottom");
    fireEvent.click(screen.getByRole("button", { name: /BTCUSDT/ }));
    expect(await screen.findByText("candidate-42")).toBeInTheDocument();
    expect(screen.getByText(/точная цепочка Robot candidate/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) =>
      String(url).startsWith("/api/workspace/signal-geometry"))).toBe(true);
  });

  it("requests an immutable original chart for proven Robot candidate lineage", async () => {
    const fetchMock = vi.fn().mockImplementation(async (url: string) => {
      if (url.startsWith("/api/workspace/signal-geometry")
          || url.startsWith("/api/diary/episode-facts"))
        return new Response("", { status: 404 });
      return new Response(JSON.stringify(mockReport([deal])), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const view = render(<DiaryOverlay accountKey="paper:source-chart" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: /BTCUSDT/ }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) =>
      String(url) === "/api/workspace/signal-geometry?signal_id=candidate-42")).toBe(true));
    expect(screen.getByText("Свечной график · исходный сигнал Робота")).toBeInTheDocument();
    view.unmount();

    fetchMock.mockClear();
    const unproven = { ...deal, verified_signal: { ...verified, source_revision: 99 } };
    fetchMock.mockImplementation(async (url: string) =>
      new Response(JSON.stringify(mockReport([unproven])), { status: 200 }));
    render(<DiaryOverlay accountKey="paper:source-chart-unproven" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: /BTCUSDT/ }));
    expect(await screen.findByText(/нет доказанной связи сделки с исходным сигналом/))
      .toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) =>
      String(url).startsWith("/api/workspace/signal-geometry"))).toBe(false);
  });

  it("rejects mismatched or unproven Wedge metadata, preserving actual PnL", async () => {
    const changes = [
      { source_revision: 4 }, { trade_episode_id: "te_" + "b".repeat(24) },
      { status: "UNPROVEN" }, { provenance: "GUESSED_FROM_TIME" },
      { evidence_scope: "MATCHED_BY_SYMBOL" }, { candidate_id: "" },
      { pattern: "Triangle Compression" },
    ];
    const deals = changes.map((change, i) => {
      const id = "te_" + (i + 1).toString(16).repeat(24);
      return {
        ...deal, trade_episode_id: id,
        symbol: ["ADAUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "DOGEUSDT", "LTCUSDT", "BNBUSDT"][i],
        verified_signal: { ...verified, trade_episode_id: id, ...change },
      };
    });
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => new Response(JSON.stringify(
      mockReport(deals),
    ), { status: 200 })));
    render(<DiaryOverlay accountKey="paper:wedge-unproven" initialSection="PATTERNS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    const region = await screen.findByRole("region", { name: "Паттерны по подтверждённым сделкам" });
    expect(region).toHaveTextContent("С подтверждённым паттерном: 0 из 7");
    expect(region).not.toHaveTextContent("-2,50 USDT");
    fireEvent.click(screen.getByRole("button", { name: "Сделки" }));
    expect(await screen.findAllByText("не установлен")).toHaveLength(7);
    expect(screen.getAllByText(/PnL: -2,50 USDT/)).toHaveLength(7);
  });

  it("does not allow a Robot verified_signal in a manual report", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(
      mockReport([{ ...deal, cohort: "MANUAL" }], "MANUAL"),
    ), { status: 200 })));
    render(<DiaryOverlay accountKey="paper:manual-wedge" initialSection="PATTERNS"
      statisticsScope={{ accountId: "paper", owner: "MANUAL" }} onClose={() => {}} />);
    expect(await screen.findByText(/С подтверждённым паттерном: 0 из 1/)).toBeInTheDocument();
  });

  it("keeps an existing exact D2 setup authoritative when Wedge metadata also exists", async () => {
    const d2 = {
      ...deal, opening_controller: "ROBOT",
      setup_context: {
        status: "EXACT_D2_LINK", source: "TRADING_DIARY_D2",
        consistency: "INDEPENDENT_READ_SNAPSHOT_NOT_ATOMIC_WITH_PAPER",
        decision_scope: "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG",
        setup: {
          setup_id: "d2-setup", symbol: "BTCUSDT", direction: "LONG",
          origin: "ROBOT", pattern: "Triangle Compression", timeframe: "5",
          strategy_version: "v1", created_at_ms: 1_793_000_000_000,
        },
      },
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(
      mockReport([d2]),
    ), { status: 200 })));
    render(<DiaryOverlay accountKey="paper:d2-priority" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    const row = await screen.findByRole("button", { name: /BTCUSDT/ });
    expect(row.querySelector(".diary-deal-pattern")).toHaveTextContent("Triangle Compression");
    expect(row).not.toHaveTextContent("Клин ↘");
  });
});

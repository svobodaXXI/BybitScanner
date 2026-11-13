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

  it("filters losses by exact closed-deal PnL, prioritizes biggest losses and keeps filters across periods", async () => {
    const episode = (id: string, symbol: string, pnl_usdt: string, closed_at_ms = 1_793_002_000_000) => ({
      ...robotDeal, trade_episode_id: "te_" + id.repeat(24), symbol, pnl_usdt, closed_at_ms,
    });
    const deals = [
      episode("a", "ETHUSDT", "3.1"),
      episode("b", "BTCUSDT", "-0.0026140884"),
      episode("c", "ADAUSDT", "-12.3"),
      episode("d", "XRPUSDT", "-0.0000000004"),
      episode("e", "DOGEUSDT", "0"),
    ];
    const fetchMock = vi.fn().mockImplementation(async (url: string) => new Response(JSON.stringify({
      ...finrezResponse,
      period: new URL(url, "http://localhost").searchParams.get("period") ?? "DAY",
      closed_episodes: deals,
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<DiaryOverlay accountKey="paper:loss-sort" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    await screen.findByRole("button", { name: /ETHUSDT/ });

    const orderedSymbols = () => screen.getAllByRole("button", {
      name: /ETHUSDT|BTCUSDT|ADAUSDT|XRPUSDT|DOGEUSDT/,
    }).map((row) => row.querySelector(".diary-trade-heading strong")?.textContent);
    const toggle = screen.getByRole("button", { name: "Убыточные" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(orderedSymbols()).toEqual(["ETHUSDT", "BTCUSDT", "ADAUSDT", "XRPUSDT", "DOGEUSDT"]);

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    expect(orderedSymbols()).toEqual(["ADAUSDT", "BTCUSDT", "XRPUSDT"]);
    expect(screen.getByRole("button", { name: /ADAUSDT/ })).toHaveTextContent("PnL -12,30 USDT");
    expect(screen.getByRole("button", { name: /XRPUSDT/ })).toHaveTextContent("PnL -<0,000001 USDT");

    fireEvent.click(screen.getByRole("button", { name: /BTCUSDT/ }));
    expect(screen.getByText(episode("b", "BTCUSDT", "-0.0026140884").trade_episode_id)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /К сделкам/ }));
    expect(orderedSymbols()).toEqual(["ADAUSDT", "BTCUSDT", "XRPUSDT"]);

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
    fireEvent.click(screen.getByRole("button", { name: "Убыточные" }));
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
    expect(row).toHaveTextContent("PnL -0,002614 USDT");
    expect(screen.getByTitle("-0.0026140884")).toBeInTheDocument();
    const tinyRow = screen.getByRole("button", { name: /XRPUSDT/ });
    expect(tinyRow).toHaveTextContent("PnL -<0,000001 USDT");
    expect(screen.getByTitle("-0.0000000004")).toBeInTheDocument();

    fireEvent.click(row);
    expect(screen.getByText("-0,002614 USDT")).toHaveAttribute("title", "-0.0026140884");
    fireEvent.click(screen.getByRole("button", { name: /К сделкам/ }));
    fireEvent.click(await screen.findByRole("button", { name: /XRPUSDT/ }));
    expect(screen.getByText("-<0,000001 USDT")).toHaveAttribute("title", "-0.0000000004");
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

  it("uses only typed Windows URI locator, with no PAPER data in launch URL", async () => {
    const episodeId = "te_" + "a".repeat(24);
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
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
        ...finrezResponse,
        closed_episodes: [{ ...robotDeal, trade_episode_id: episodeId }],
      }), { status: 200 })));
      render(<DiaryOverlay accountKey="paper:deals" initialSection="DEALS"
        statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
      fireEvent.click(await screen.findByRole("button", { name: /BTCUSDT/ }));
      fireEvent.click(screen.getByRole("button", { name: "Открыть в Симуляторе" }));
      await waitFor(() => expect(launches).toEqual([
        "bybitscanner-simulator://open?episode=" + episodeId,
      ]));
      expect(copy).toHaveBeenCalledWith(episodeId);
      expect(await screen.findByText(/Запрос открытия утилиты отправлен Windows/)).toHaveTextContent(
        "Результат пока не подтверждён.",
      );
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
    expect(await screen.findByText(/Локальная утилита подтвердила запрос открытия/))
      .toHaveTextContent("Идентификатор скопирован.");
    expect(copy).toHaveBeenCalledWith(episodeId);
    expect(fetchMock).toHaveBeenCalledWith("/api/diary/simulator-bridge/request", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ episode_id: episodeId }),
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
    expect(await screen.findByText(/Нет доступа к локальному Симулятору или адаптеру VPS/))
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
    expect(await screen.findByText("Паттерн: Falling Wedge")).toBeInTheDocument();
    expect(screen.getByText("Паттерн: не установлен")).toBeInTheDocument();
    expect(screen.queryByText("Wrong Pattern")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Подробности сделки" })).toHaveLength(2);
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/episode-facts")))
      .toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Неделя" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=WEEK",
    ));
    expect(await screen.findByText("Паттерн: Falling Wedge")).toBeInTheDocument();
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
    expect(region).toHaveTextContent("Паттерн подтверждён для 4 из 5");
    expect(region).toHaveTextContent("Робот · сделок: 2 · прибыльных: 1 · убыточных: 1");
    expect(screen.getByTitle("-1.4012345678 USDT")).toHaveTextContent("-1,4012 USDT");
    expect(screen.getByTitle("20.2 USDT")).toHaveTextContent("+20,20 USDT");
    expect(screen.queryByTitle("-999 USDT")).not.toBeInTheDocument();
    const openWedge = screen.getAllByRole("button", { name: "Показать все сделки по паттерну Falling Wedge" });
    expect(openWedge).toHaveLength(2);
    fireEvent.click(openWedge[0]);
    expect(screen.getByRole("searchbox", { name: "Поиск по паттерну" })).toHaveValue("Falling Wedge");
    expect(await screen.findAllByText("Паттерн: Falling Wedge")).toHaveLength(3);
    expect(screen.queryByText("Паттерн: Triangle Compression")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Неделя" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=WEEK",
    ));
    expect(screen.getByRole("searchbox", { name: "Поиск по паттерну" })).toHaveValue("Falling Wedge");
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
    expect(region).toHaveTextContent("Паттерн подтверждён для 0 из 1");
    expect(region).toHaveTextContent("неполное покрытие атрибуции");
    expect(region).toHaveTextContent("Нет сделок с подтверждённым паттерном");
    expect(region).not.toHaveTextContent("0 USDT");
    fireEvent.change(screen.getByRole("searchbox", { name: "Поиск по тикеру" }), {
      target: { value: "ETH" },
    });
    expect(region).toHaveTextContent("Паттерн подтверждён для 0 из 0");
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

  it("combines ticker, period and case-insensitive verified pattern search without guessing patterns", async () => {
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
    render(<DiaryOverlay accountKey="paper:pattern-search" initialSection="FINREZ"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);

    expect(await screen.findByText("BTCUSDT")).toBeInTheDocument();
    expect(screen.queryByRole("searchbox", { name: "Поиск по паттерну" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Сделки" }));
    expect(await screen.findByText("Паттерн: Falling Wedge")).toBeInTheDocument();
    expect(screen.getByText("Паттерн: Triangle Compression")).toBeInTheDocument();
    expect(screen.getByText("Паттерн: не установлен")).toBeInTheDocument();
    const pattern = screen.getByRole("searchbox", { name: "Поиск по паттерну" });
    const ticker = screen.getByRole("searchbox", { name: "Поиск по тикеру" });

    fireEvent.change(pattern, { target: { value: "  wEdGe " } });
    expect(screen.getByText("BTCUSDT")).toBeInTheDocument();
    expect(screen.queryByText("ETHUSDT")).not.toBeInTheDocument();
    expect(screen.queryByText("XRPUSDT")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Подробности сделки" })).toBeInTheDocument();

    fireEvent.change(ticker, { target: { value: "eth" } });
    expect(await screen.findByText("По выбранным фильтрам сделок нет")).toBeInTheDocument();
    expect(pattern).toHaveValue("  wEdGe ");
    fireEvent.change(pattern, { target: { value: "TRIANGLE" } });
    expect(screen.getByText("ETHUSDT")).toBeInTheDocument();
    expect(screen.queryByText("BTCUSDT")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Неделя" }));
    await waitFor(() => expect(mockFetch).toHaveBeenCalledWith(
      "/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=WEEK",
    ));
    expect(await screen.findByText("Паттерн: Triangle Compression")).toBeInTheDocument();
    expect(pattern).toHaveValue("TRIANGLE");
    expect(ticker).toHaveValue("ETH");

    // The pattern query applies to Deals only, not the aggregated Finrez.
    fireEvent.click(screen.getByRole("button", { name: "Финрез" }));
    expect(screen.queryByRole("searchbox", { name: "Поиск по паттерну" })).not.toBeInTheDocument();
    expect(await screen.findByText("+7,20 USDT")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Сделки" }));
    expect(await screen.findByText("Паттерн: Triangle Compression")).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Поиск по паттерну" })).toHaveValue("TRIANGLE");
    fireEvent.change(screen.getByRole("searchbox", { name: "Поиск по паттерну" }), {
      target: { value: "не установлен" },
    });
    expect(screen.getByText("По выбранным фильтрам сделок нет")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("searchbox", { name: "Поиск по паттерну" }), {
      target: { value: "" },
    });
    expect(screen.getByText("ETHUSDT")).toBeInTheDocument();
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
    expect(await screen.findByText("+7,2012 USDT")).toBeInTheDocument();
    expect(screen.getByText("-2,5012 USDT")).toBeInTheDocument();
    expect(screen.queryByText(/2\.5012345678/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Показать сделки по BTCUSDT" }));
    expect(screen.getByRole("alertdialog", { name: "Переход к сделкам" }))
      .toHaveTextContent("Открыть все сделки по BTCUSDT за выбранный период?");
    expect(screen.queryByText("Сделки по BTCUSDT")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Отмена" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Показать сделки по BTCUSDT" }));
    fireEvent.click(screen.getByRole("button", { name: "Открыть сделки" }));
    expect(await screen.findByText("Сделки по BTCUSDT")).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Поиск по тикеру" })).toHaveValue("BTCUSDT");
    expect(screen.getByText("BTCUSDT")).toBeInTheDocument();
    expect(screen.queryByText("ETHUSDT")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Подробности сделки" })).toBeInTheDocument();
    expect(screen.getByText("Паттерн: не установлен")).toBeInTheDocument();
    expect(screen.getByText("PnL %: —")).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole("button", { name: "Открыть сделки" }));
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
    expect(screen.getByTitle("4.3583303660000000000004 USDT")).toHaveTextContent("+4,3583 USDT");
    expect(screen.getByTitle("0.0000000004 USDT")).toHaveTextContent("+<0,000001 USDT");
    expect(screen.getByTitle("0 USDT")).toHaveTextContent("0 USDT");
    expect(screen.getByTitle("-0.0026140884 USDT")).toHaveTextContent("-0,002614 USDT");
    expect(screen.getByTitle("-1.8162218600000000000000 USDT")).toHaveTextContent("-1,8162 USDT");
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
    expect(screen.getByText("Нет закрытых сделок этого типа за выбранный период")).toBeInTheDocument();
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
    expect(await screen.findByText("Нет закрытых сделок этого типа за выбранный период")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Всё время" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=ALL"));
    const coverage = await screen.findByRole("status");
    expect(coverage).toHaveTextContent("История неполная");
    expect(coverage).toHaveTextContent("исключено 3 закрытых");
    expect(coverage).toHaveTextContent("11 исполнений");
    expect(coverage).toHaveTextContent("не полный результат за период");
    expect(screen.getByText(/Нет достоверно атрибутированных закрытых сделок/)).toBeInTheDocument();
    expect(screen.queryByText("Нет закрытых сделок этого типа за выбранный период")).not.toBeInTheDocument();
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
    expect(screen.getByText("Нет закрытых сделок этого типа за выбранный период")).toBeInTheDocument();
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
    expect(await screen.findByText("PnL %: +2,40%")).toBeInTheDocument();
    expect(screen.getByText("PnL %: —")).toHaveAttribute(
      "title", "Процент недоступен без подтверждённой базы расчёта",
    );
    expect(screen.getByText("PnL %: +2,40%")).toHaveAttribute("title",
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
    expect(await screen.findByText("Паттерн: не установлен")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Подробности сделки" }));
    const section = await screen.findByRole("region", { name: "Связь сделки с паттерном" });
    await waitFor(() => expect(section).toHaveTextContent("Falling Wedge"));
    expect(section).toHaveTextContent("candidate-1");
    expect(section).toHaveTextContent("robot-v2");
    expect(section).toHaveTextContent("не полный журнал решений Робота");
    fireEvent.click(screen.getByRole("button", { name: "← К сделкам" }));
    expect(screen.getByText("Паттерн: Falling Wedge")).toBeInTheDocument();
    expect(screen.getByText("PnL %: —")).toBeInTheDocument();
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
    expect(screen.getByText("Паттерн: не установлен")).toBeInTheDocument();
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

  it("filmstrip opens local Simulator with exact PAPER ID, without requiring candle history", async () => {
    const episodeId = "te_" + "c".repeat(24);
    const clicked: string[] = [];
    const copy = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", {
      userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
      clipboard: { writeText: copy },
    });
    const a = vi.spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        clicked.push(this.getAttribute("href") || "");
      });
    try {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
        ...finrezResponse,
        closed_episodes: [{
          trade_episode_id: episodeId, symbol: "BTCUSDT", side: "LONG",
          opened_at_ms: 1_793_001_000_000, closed_at_ms: 1_793_002_000_000,
          pnl_usdt: "-2.501234567", execution_count: 2,
          cohort: "ROBOT", replay_evidence: "EPISODE_INDEX_ONLY",
        }],
      }), { status: 200 })));
      render(<DiaryOverlay accountKey="paper:film" initialSection="DEALS"
        statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
      const film = await screen.findByRole("button", { name: "Открыть сделку в Симуляторе" });
      expect(film).toBeEnabled();
      fireEvent.click(film);
      expect(clicked).toEqual(["bybitscanner-simulator://open?episode=" + episodeId]);
      expect(screen.getByRole("status")).toHaveTextContent("Свечи и решения не переданы");
    } finally {
      a.mockRestore();
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
    });
    expect(screen.getByText(/PnL -1,8162 USDT/)).toHaveAttribute("title", "-1.81622186");
  });
});

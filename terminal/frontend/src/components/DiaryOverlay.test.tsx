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
  period: "TODAY" as const,
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

  it("displays exact robot episode identifiers and keeps shared PnL labelled separately", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ...finrezResponse, closed_episodes: [sharedDeal, robotDeal],
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<DiaryOverlay accountKey="paper:deals" initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    const row = await screen.findByRole("button", { name: /BTCUSDT/ });
    expect(screen.getByRole("button", { name: /XRPUSDT/ })).toHaveTextContent("Робот + ручное управление");
    expect(row).toHaveTextContent("-4.8 USDT");
    fireEvent.click(row);
    expect(screen.getByText("robot-episode-42")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("не воспроизведение");
    expect(screen.queryByRole("button", { name: /Открыть сделку в Симуляторе/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /К сделкам/ }));
    expect(await screen.findByRole("button", { name: /BTCUSDT/ })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=TODAY",
    );
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
  it("shows Автопилот above Статистика for the robot scope, without a duplicated account caption", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(finrezResponse), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const { container } = render(<DiaryOverlay accountKey="paper:robot" initialSection="FINREZ"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    const heading = container.querySelector(".diary-context-heading")!;
    expect(heading.querySelector("p")).toHaveTextContent("Автопилот");
    expect(heading.querySelector("h2")).toHaveTextContent("Статистика");
    expect(heading).not.toHaveTextContent("PAPER");
    expect(heading).not.toHaveTextContent("раздельная статистика");
    await screen.findByText("ETHUSDT");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=TODAY",
    );
  });
});

describe("Finrez first-screen UI", () => {
  it("shows the ticker ranking with two periods, reuses the Diary modal and defers other sections", async () => {
    const fetchMock = vi.fn().mockImplementation(async (url: string) => new Response(JSON.stringify({
      ...finrezResponse,
      period: url.includes("period=ALL") ? "ALL" : "TODAY",
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<DiaryOverlay accountKey="paper:1" initialSection="FINREZ"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} onClose={() => {}} />);
    expect(screen.getByRole("dialog", { name: "Статистика" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Сегодня" })).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByText("+7.2 USDT")).toBeInTheDocument();
    expect(screen.getByText("-2.5 USDT")).toBeInTheDocument();
    expect(screen.getByText("ETHUSDT")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=TODAY");
    fireEvent.click(screen.getByRole("button", { name: "Всё время" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/diary/ticker-finrez?account_id=paper&owner=ROBOT&period=ALL"));
    fireEvent.click(screen.getByRole("button", { name: "Паттерны" }));
    expect(await screen.findByText(/Паттерны — второй этап/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Сделки" }));
    expect(await screen.findByText(/Нет подтверждённых закрытых сделок/)).toBeInTheDocument();
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
    expect(screen.getByText("-4.5 USDT")).toBeInTheDocument();
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
      period: url.includes("period=ALL") ? "ALL" : "TODAY",
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
    expect(section).toHaveTextContent("-11.4 USDT");
    expect(section).toHaveTextContent("не складывайте его дважды");
    expect(screen.getByText("Нет закрытых сделок этого типа за выбранный период")).toBeInTheDocument();
    current.rerender(<DiaryOverlay accountKey="paper:joint-manual" initialSection="FINREZ"
      statisticsScope={{ accountId: "paper", owner: "MANUAL" }} onClose={() => {}} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/diary/ticker-finrez?account_id=paper&owner=MANUAL&period=TODAY",
    ));
    expect(await screen.findByRole("region", { name: "Совместно управляемые сделки" })).toHaveTextContent("-11.4 USDT");
    expect(screen.getAllByText("-11.4 USDT")).toHaveLength(1);
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
  it("formats only visible deal PnL to two decimal places", () => {
    expect(displayTradePnl("-1.81622186")).toBe("-1,82");
    expect(displayTradePnl("7.2")).toBe("7,20");
    expect(displayTradePnl("0")).toBe("0,00");
    expect(displayTradePnl(null)).toBe("—");
    expect(displayTradePnl("NaN")).toBe("—");
  });

  it("keeps two icon action slots on every closed deal without faking full replay", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        ...finrezResponse,
        closed_episodes: [sharedDeal, robotDeal],
      }), { status: 200 }),
    );
    render(<DiaryOverlay onClose={() => {}} initialSection="DEALS"
      statisticsScope={{ accountId: "paper", owner: "ROBOT" }} />);
    expect((await screen.findAllByRole("button", { name: "Подробности сделки" })).length).toBe(2);
    const replay = screen.getAllByRole("button", { name: "Открыть сделку в Симуляторе" });
    expect(replay).toHaveLength(2);
    replay.forEach((button) => expect(button).toBeDisabled());
    expect(screen.getByText(/PnL -1,82 USDT/)).toHaveAttribute("title", "-1.81622186");
  });
});

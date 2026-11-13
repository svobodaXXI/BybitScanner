import { useCallback, useEffect, useMemo, useRef, useState, type ComponentProps } from "react";
import { marketApiRoutes } from "../marketData/apiRoutes";
import { AccountMenu } from "./AccountMenu";
import "./DiaryOverlay.css";

export type DiarySection = "FINREZ" | "PATTERNS" | "DEALS" | "TRADES" | "SETUPS" | "STATISTICS" | "MIRROR";
export type DiaryAccountMenuProps = Pick<ComponentProps<typeof AccountMenu>,
  "workspaceProjection" | "mode" | "selectedAccountId" | "onSelectAccount" | "modeAccountError">;
type FinrezPeriod = "DAY" | "WEEK" | "MONTH" | "YEAR" | "ALL";
type DiaryFilter = "ALL" | "OPEN" | "CLOSED" | "ATTENTION";
type SetupFilter = "ALL" | "ATTENTION";

type TradeDetails = {
  identity: {
    trade_episode_id: string;
    symbol: string;
    side: "LONG" | "SHORT";
    environment: "PAPER" | "LIVE" | "HISTORICAL_REPLAY";
    controller_origin: string | null;
  };
  decision: {
    controller_origin: string | null;
    setup_id: string | null;
    strategy: string | null;
    decision_reason: string | null;
  };
  risk: {
    initial_risk: string | null;
    stop: string | null;
    take_profit: string | null;
  };
  orders_executions: Array<{
    execution_id: string;
    role: string;
    quantity: string;
    fee: string;
    occurred_at_ms: number;
  }>;
  management: {
    opening_price: string;
    average_entry: string;
    open_quantity: string;
  };
  outcome: {
    status: "OPEN" | "CLOSED";
    realized_price_pnl: string;
    execution_fees: string;
    net_pnl: string | null;
    readiness: "OPEN" | "CLOSED_INCOMPLETE" | "CLOSED_READY";
    missing_reasons: string[];
  };
  automatic_factors: null;
  notes: null;
};

type DiaryTrade = {
  trade_episode_id: string;
  symbol: string;
  side: "LONG" | "SHORT";
  environment: "PAPER" | "LIVE" | "HISTORICAL_REPLAY";
  controller_origin: string | null;
  opened_at_ms: number;
  closed_at_ms: number | null;
  opening_price: string;
  average_entry: string;
  exit_price: string | null;
  open_quantity: string;
  pnl: string | null;
  holding_duration_ms: number;
  readiness: "OPEN" | "CLOSED_INCOMPLETE" | "CLOSED_READY";
  needs_attention: boolean;
  missing_reasons: string[];
  details: TradeDetails;
};

type DiarySetup = {
  setup_instance_id: string;
  setup_id: string;
  symbol: string;
  timeframe: string;
  pattern: string;
  direction: "LONG" | "SHORT";
  strategy_version: string;
  hypothesis_id: string | null;
  entry_mode: string;
  origin: string;
  created_at_ms: number;
  status: string;
  decision_state: string | null;
  reason_code: string | null;
  controller: string | null;
  latest_decision_at_ms: number | null;
  trade_episode_ids: string[];
  needs_attention: boolean;
  missing_evidence: string[];
};

type MirrorLevelRow = {
  symbol: string;
  timeframe: string;
  level_id: string;
  status: string;
  lifecycle: string;
  candidate: boolean | null;
  freshness: string | null;
  rejection_reason: string | null;
  breakout: { direction: string; campaign_direction: string; open_time_ms: number; open: number; close: number } | null;
  breakout_evidence: { kind: string; body_atr: number | null } | null;
  level_label: string;
  level_geometry_text: string;
  first_retest_text: string;
  imbalance_text: string;
  sources_text: string;
  parent_patterns: Array<{ pattern: string; formation_id: string | null }>;
  robot: { mode: string; risk_reason: string; paper_admission: string; paper_blockers: string[] } | null;
};

type MirrorLevelsResponse = {
  ok: boolean;
  levels: MirrorLevelRow[];
  counts: Record<string, number>;
  paper_admission: string;
  paper_blockers: string[];
};

type FactorCoverage = {
  eligible_closed: number;
  observed: number;
  coverage_ratio: string;
};

type DiaryStatistics = {
  sample: {
    total: number;
    eligible_closed_ready: number;
    excluded_open: number;
    excluded_incomplete: number;
  };
  pnl: {
    net_pnl: string | null;
    average_net_pnl: string | null;
    wins: number;
    losses: number;
    breakeven: number;
    win_rate: string | null;
    average_win: string | null;
    average_loss: string | null;
    payoff_ratio: string | null;
    profit_factor: string | null;
  };
  holding: {
    average_duration_ms: string | null;
  };
  coverage: {
    pnl_ready_ratio: string;
    post_trade_factors: Record<string, FactorCoverage>;
  };
};

type ClosedEpisodeLocator = {
  trade_episode_id: string;
  symbol: string;
  side: "LONG" | "SHORT";
  opened_at_ms: number;
  closed_at_ms: number;
  pnl_usdt: string;
  execution_count: number;
  cohort: "ROBOT" | "MANUAL" | "ROBOT_MANUAL_CLOSE" | "JOINT_MANAGEMENT";
  replay_evidence: "EPISODE_INDEX_ONLY";
  opening_controller?: "ROBOT" | "MANUAL";
  setup_context?: unknown;
};

type FinrezTicker = { symbol: string; pnl_usdt: string; trade_count: number };
type FinrezResponse = {
  ok: boolean;
  account_id: string;
  owner: "MANUAL" | "ROBOT";
  period: FinrezPeriod;
  period_start_ms: number;
  as_of_ms: number;
  source_revision: number;
  source: "PAPER_EXECUTIONS_ATTRIBUTED";
  pnl_basis: "REALIZED_PRICE_MINUS_EXECUTION_FEES";
  tickers: FinrezTicker[];
  closed_episodes?: ClosedEpisodeLocator[];
  manual_interventions: FinrezTicker[];
  joint_management: FinrezTicker[];
  attribution_coverage: {
    status: "COMPLETE" | "PARTIAL";
    excluded_unattributed_episode_count: number;
    excluded_unattributed_execution_count: number;
  };
};

type DiaryTradesResponse = {
  ok: boolean;
  active_account_id: string;
  session_generation: number;
  environment: DiaryTrade["environment"];
  trades: DiaryTrade[];
};

type DiarySetupsResponse = {
  ok: boolean;
  source: "TRADING_DIARY_D2";
  setups: DiarySetup[];
};

export type DiaryStatisticsScope = {
  accountId: string;
  owner: "MANUAL" | "ROBOT";
};

type DiaryStatisticsResponse = {
  ok: boolean;
  account_id: string;
  owner: "MANUAL" | "ROBOT";
  source_revision: number;
  statistics: DiaryStatistics;
};

const tradeFilters: ReadonlyArray<{ id: DiaryFilter; label: string }> = [
  { id: "ALL", label: "Все" },
  { id: "OPEN", label: "Открытые" },
  { id: "CLOSED", label: "Закрытые" },
  { id: "ATTENTION", label: "Требуют внимания" },
];

const setupFilters: ReadonlyArray<{ id: SetupFilter; label: string }> = [
  { id: "ALL", label: "Все" },
  { id: "ATTENTION", label: "Требуют внимания" },
];

function formatDate(value: number | null): string {
  if (value === null) return "—";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatDuration(value: number): string {
  if (!Number.isFinite(value) || value < 0) return "—";
  const minutes = Math.floor(value / 60_000);
  if (minutes < 60) return `${minutes}м`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  if (hours < 24) return remainder ? `${hours}ч ${remainder}м` : `${hours}ч`;
  const days = Math.floor(hours / 24);
  return `${days}д ${hours % 24}ч`;
}

function formatRatio(value: string | null): string {
  if (value === null) return "—";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return value;
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(numeric * 100) + "%";
}

function formatDurationValue(value: string | null): string {
  if (value === null) return "—";
  return formatDuration(Number(value));
}

function sideLabel(side: "LONG" | "SHORT"): string {
  return side === "LONG" ? "ЛОНГ" : "ШОРТ";
}

function readinessLabel(trade: DiaryTrade): string {
  if (trade.readiness === "OPEN") return "ОТКРЫТА";
  if (trade.readiness === "CLOSED_READY") return "ГОТОВО";
  return "Нужны данные";
}

function matchesTradeFilter(trade: DiaryTrade, filter: DiaryFilter): boolean {
  if (filter === "OPEN") return trade.closed_at_ms === null;
  if (filter === "CLOSED") return trade.closed_at_ms !== null;
  if (filter === "ATTENTION") return trade.needs_attention;
  return true;
}


/** Display-only rounding. Immutable source strings remain untouched. */
export function displayTradePnl(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const numeric = Number(value);
  if (!value.trim() || !Number.isFinite(numeric)) return "—";
  return new Intl.NumberFormat("ru-RU", {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(numeric);
}

/** The filmstrip carries only a typed ID, never a claimed full replay. */
function requestSimulatorLocator(episodeId: string, onNotice: (message: string) => void) {
  if (!/^te_[0-9a-f]{24}$/.test(episodeId)) {
    onNotice("Нет подтверждённого ID формата te_… для локального Симулятора.");
    return;
  }
  try {
    if (/\bWindows\b/i.test(navigator.userAgent)) {
      const link = document.createElement("a");
      link.href = "bybitscanner-simulator://open?episode=" + episodeId;
      link.rel = "noopener noreferrer";
      link.target = "_blank";
      document.body.appendChild(link);
      try { link.click(); } finally { link.remove(); }
      onNotice("Windows получила запрос открыть Симулятор по ID " + episodeId
        + ". Свечи и решения не переданы; результат запуска не подтверждён.");
    } else {
      const clipboard = navigator.clipboard;
      if (typeof clipboard?.writeText !== "function") {
        onNotice("Скопируйте ID вручную для Симулятора: " + episodeId);
      } else {
        void clipboard.writeText(episodeId).then(
          () => onNotice("ID сделки скопирован для Симулятора: " + episodeId),
          () => onNotice("Скопируйте ID вручную для Симулятора: " + episodeId),
        );
      }
    }
  } catch {
    onNotice("Не удалось передать ID автоматически. Скопируйте: " + episodeId);
  }
}

/** Same action placement and icons for every statistics account/owner scope. */
function TradeActionButtons({ onDetails, onReplay }: {
  onDetails: () => void;
  onReplay?: () => void;
}) {
  return (
    <div className="diary-trade-actions" role="group" aria-label="Действия со сделкой">
      <button type="button" className="diary-trade-icon" aria-label="Подробности сделки"
        title="Подробности сделки" onClick={onDetails}>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="10.6" cy="10.6" r="6.6" /><path d="m15.5 15.5 5.2 5.2" />
        </svg>
      </button>
      <button type="button" className="diary-trade-icon"
        aria-label="Открыть сделку в Симуляторе" title={onReplay
          ? "Открыть локальный Симулятор по ID без передачи свечей и решений"
          : "Для открытия по ID нужен подтверждённый PAPER episode te_…"}
        disabled={!onReplay} onClick={onReplay}>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <rect x="3.5" y="3" width="17" height="18" rx="1.5" />
          <path d="M8 3v18M16 3v18M3.5 8h4.5M3.5 15h4.5M16 8h4.5M16 15h4.5" />
        </svg>
      </button>
    </div>
  );
}


type VerifiedEpisodeSetup = {
  pattern: string;
  timeframe: string;
  setupId: string;
  strategyVersion: string;
};

/** D2 is a separate observational store, not a reconstructed Robot decision.
 * Never infer a pattern by ticker/time or from execution-only facts.
 */
function exactD2Setup(facts: Record<string, unknown>, deal: ClosedEpisodeLocator): VerifiedEpisodeSetup | null {
  const context = facts.setup_context;
  if (!context || typeof context !== "object") return null;
  const d2 = context as Record<string, unknown>;
  if (d2.status !== "EXACT_D2_LINK" || d2.source !== "TRADING_DIARY_D2"
    || d2.consistency !== "INDEPENDENT_READ_SNAPSHOT_NOT_ATOMIC_WITH_PAPER"
    || d2.decision_scope !== "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG"
    || !d2.setup || typeof d2.setup !== "object") return null;
  const setup = d2.setup as Record<string, unknown>;
  const allocations = facts.execution_allocations;
  if (!Array.isArray(allocations) || allocations.length < 1) return null;
  const first = allocations[0];
  if (!first || typeof first !== "object") return null;
  const openingController = (first as Record<string, unknown>).controller;
  if (openingController !== "ROBOT" && openingController !== "MANUAL") return null;
  if (setup.origin !== (openingController === "ROBOT" ? "ROBOT" : "TERMINAL_MANUAL")
    || setup.symbol !== deal.symbol || setup.direction !== deal.side
    || typeof setup.created_at_ms !== "number" || !Number.isSafeInteger(setup.created_at_ms)
    || setup.created_at_ms < 0 || setup.created_at_ms > deal.opened_at_ms) return null;
  const fields = [setup.pattern, setup.timeframe, setup.setup_id, setup.strategy_version];
  if (fields.some((value) => typeof value !== "string" || !value.trim() || value.length > 256)) return null;
  return {
    pattern: setup.pattern as string, timeframe: setup.timeframe as string,
    setupId: setup.setup_id as string, strategyVersion: setup.strategy_version as string,
  };
}

type TradeExecutionPoint = { at: number; price: number };

function TradeExecutionPriceChart({ points }: { points: readonly TradeExecutionPoint[] }) {
  if (points.length < 1) return (
    <p className="diary-finrez-basis">Свечной график пока недоступен: нужен проверенный архив исторических свечей.</p>
  );
  const ordered = [...points].sort((a, b) => a.at - b.at);
  const first = ordered[0].at, last = ordered[ordered.length - 1].at;
  const prices = ordered.map((point) => point.price);
  const min = Math.min(...prices), max = Math.max(...prices);
  const x = (at: number) => 18 + (at - first) / Math.max(1, last - first) * 284;
  const y = (price: number) => 105 - (price - min) / Math.max(0.00000001, max - min) * 88;
  return (
    <section className="diary-detail-section">
      <h3>График цен исполнений · не свечной график</h3>
      <svg className="diary-execution-price-chart" viewBox="0 0 320 122" role="img"
        aria-label="Фактические цены исполнений сделки по времени">
        <path d={ordered.map((point, i) => `${i ? "L" : "M"} ${x(point.at)} ${y(point.price)}`).join(" ")}
          fill="none" stroke="currentColor" strokeWidth="1.6" />
        {ordered.map((point, i) => <circle key={i} cx={x(point.at)} cy={y(point.price)} r="3.3"
          fill="currentColor">
          <title>{point.price} · {formatDate(point.at)}</title>
        </circle>)}
      </svg>
      <small>Показаны только подтверждённые исполнения, без подстановки рыночных свечей.</small>
    </section>
  );
}

function Value({ value }: { value: string | null | undefined }) {
  return <span>{value ?? "—"}</span>;
}

/** Owner click routes only a typed ID: local Windows link or paired VPS relay.
 * Neither path transfers PAPER facts or implies a complete historical replay.
 */
function SimulatorLaunchAction({ episodeId, allowLocalLaunch }: {
  episodeId: string; allowLocalLaunch: boolean;
}) {
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [pairingBusy, setPairingBusy] = useState(false);
  const [pairingUrl, setPairingUrl] = useState<string | null>(null);
  const [pairingNotice, setPairingNotice] = useState("");

  function copyEpisodeId() {
    // Copy only the visible identifier. No network request or protocol launch.
    try {
      if (typeof navigator.clipboard?.writeText !== "function") {
        setNotice("Копирование недоступно. Выделите ID вручную: " + episodeId);
        return;
      }
      void navigator.clipboard.writeText(episodeId).then(
        () => setNotice("ID сделки скопирован: " + episodeId),
        () => setNotice("Копирование недоступно. Выделите ID вручную: " + episodeId),
      );
    } catch {
      setNotice("Копирование недоступно. Выделите ID вручную: " + episodeId);
    }
  }

  async function preparePairing(deviceId: "owner-pc" | "owner-laptop") {
    if (pairingBusy || !allowLocalLaunch) return;
    setPairingBusy(true); setPairingUrl(null); setPairingNotice("");
    try {
      // Owner-authenticated HTTPS request, never an unauthenticated device
      // endpoint. Existing provisioned device slot; no new enrollment state.
      const response = await fetch("/api/diary/simulator-bridge/pair", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_id: deviceId }),
      });
      if (!response.ok) throw new Error("pairing_unavailable");
      const raw: unknown = await response.json();
      const pair = raw as Record<string, unknown>;
      if (!raw || typeof raw !== "object" || pair.ok !== true
          || pair.device_id !== deviceId || typeof pair.token !== "string"
          || !/^[A-Za-z0-9_-]{48,256}$/.test(pair.token))
        throw new Error("pairing_invalid_response");
      setPairingUrl("bybitscanner-simulator://pair?device_id="
        + encodeURIComponent(deviceId) + "&token=" + encodeURIComponent(pair.token));
      setPairingNotice("Ключ подготовлен. Нажмите «Подтвердить подключение» на этом компьютере.");
    } catch {
      setPairingNotice("Подключение пока недоступно. Обычный запуск Симулятора и копирование ID работают.");
    } finally {
      setPairingBusy(false);
    }
  }

  function openPairingLink() {
    if (!pairingUrl) return;
    // Native protocol must open synchronously after this owner click. The
    // local app verifies the device key against its pre-pinned HTTPS origin.
    try {
      const link = document.createElement("a");
      link.href = pairingUrl;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      document.body.appendChild(link);
      try { link.click(); } finally { link.remove(); }
      setPairingNotice("Запрос сопряжения передан Windows. Успешное подключение пока не подтверждено.");
    } catch {
      setPairingNotice("Не удалось открыть локальный адаптер. Копирование ID остаётся доступным.");
    } finally {
      setPairingUrl(null);
    }
  }

  async function requestLaunch() {
    if (busy) return;
    setBusy(true);
    // Clipboard permission belongs to the initial owner click, not an HTTP
    // response. Even when unavailable, display the exact ID for manual copy.
    let copied: Promise<boolean>;
    try {
      copied = typeof navigator.clipboard?.writeText === "function"
        ? navigator.clipboard.writeText(episodeId).then(() => true, () => false)
        : Promise.resolve(false);
    } catch {
      copied = Promise.resolve(false);
    }
    const allowed = allowLocalLaunch && /^te_[0-9a-f]{24}$/.test(episodeId);
    const onWindows = /\bWindows\b/i.test(navigator.userAgent);
    // Launch custom Windows URI synchronously in the actual click handler.
    // Awaiting clipboard permission first can lose browser user activation.
    let windowsError = false;
    if (allowed && onWindows) {
      try {
        const link = document.createElement("a");
        link.href = "bybitscanner-simulator://open?episode=" + episodeId;
        link.rel = "noopener noreferrer";
        link.target = "_blank";
        document.body.appendChild(link);
        try { link.click(); } finally { link.remove(); }
      } catch {
        windowsError = true;
      }
    }
    const suffix = (await copied)
      ? " Идентификатор скопирован."
      : " Автоматическое копирование ID недоступно.";
    try {
      if (allowed && onWindows) {
        setNotice((windowsError
          ? "Windows не смогла принять запрос открытия локальной утилиты."
          : "Запрос открытия утилиты отправлен Windows. Результат пока не подтверждён.") + suffix);
      } else if (allowed) {
        // Same-origin HTTPS owner UI. Nginx controls owner access; the relay
        // independently checks Origin. The paired PC supplies a separate
        // scoped token when it contacts the VPS (never given to this page).
        const response = await fetch("/api/diary/simulator-bridge/request", {
          method: "POST", credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ episode_id: episodeId }),
        });
        if (!response.ok) throw new Error("simulator_bridge_unavailable");
        const result: unknown = await response.json();
        const receipt = result as Record<string, unknown>;
        if (!result || typeof result !== "object" || receipt.ok !== true
          || receipt.state !== "QUEUED" || typeof receipt.request_id !== "string"
          || !/^[0-9a-f]{32}$/.test(receipt.request_id))
          throw new Error("invalid_simulator_bridge_receipt");
        setNotice("Запрос передан подключённому устройству. Проверяю подтверждение." + suffix);
        let state = "QUEUED";
        for (let attempt = 0; attempt < 8; attempt++) {
          // Check once immediately: an already connected adapter may have
          // acknowledged the job. Only subsequent checks need a delay.
          if (attempt > 0)
            await new Promise<void>((resolve) => window.setTimeout(resolve, 1000));
          const check = await fetch("/api/diary/simulator-bridge/status", {
            method: "POST", credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ request_id: receipt.request_id }),
          });
          if (!check.ok) throw new Error("simulator_bridge_status_unavailable");
          const raw: unknown = await check.json();
          const status = raw as Record<string, unknown>;
          if (!raw || typeof raw !== "object" || status.ok !== true
            || status.request_id !== receipt.request_id
            || !["QUEUED", "DELIVERED", "LAUNCHED", "FAILED", "EXPIRED"].includes(String(status.state)))
            throw new Error("invalid_simulator_bridge_status");
          state = String(status.state);
          if (state === "LAUNCHED" || state === "FAILED" || state === "EXPIRED") break;
        }
        if (state === "LAUNCHED")
          setNotice("Локальная утилита подтвердила запрос открытия. Полная история ещё не передана." + suffix);
        else
          setNotice("Нет подтверждения открытия Симулятора на ПК или ноутбуке." + suffix);
      } else {
        setNotice("Автоматический запуск этой сделки недоступен." + suffix);
      }
    } catch {
      setNotice("Нет доступа к локальному Симулятору или адаптеру VPS." + suffix);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="diary-simulator-launch">
      <button className="diary-detail-back" type="button" disabled={busy}
        onClick={() => void requestLaunch()}>
        {busy ? "Проверяю Симулятор…" : "Открыть в Симуляторе"}
      </button>
      <button className="diary-detail-back" type="button" onClick={copyEpisodeId}>
        Скопировать ID
      </button>
      {notice ? <p className="diary-finrez-coverage" role="status">{notice} ID: {episodeId}</p> : null}
      {allowLocalLaunch && /\bWindows\b/i.test(navigator.userAgent) ? (
        <div className="diary-simulator-pairing">
          <button type="button" className="diary-detail-back" disabled={pairingBusy}
            onClick={() => void preparePairing("owner-pc")}>Связать ПК</button>
          <button type="button" className="diary-detail-back" disabled={pairingBusy}
            onClick={() => void preparePairing("owner-laptop")}>Связать ноутбук</button>
          {pairingUrl ? <button type="button" className="diary-detail-back"
            onClick={openPairingLink}>Подтвердить подключение</button> : null}
          {pairingNotice ? <p className="diary-finrez-coverage" role="status">{pairingNotice}</p> : null}
        </div>
      ) : null}
    </div>
  );
}

function TradeDetailsView({ trade, onBack }: { trade: DiaryTrade; onBack: () => void }) {
  const details = trade.details;
  return (
    <div className="diary-detail">
      <button className="diary-detail-back" onClick={onBack} type="button">← Сделки</button>

      <SimulatorLaunchAction episodeId={trade.trade_episode_id}
        allowLocalLaunch={trade.environment === "PAPER"} />
      <div className="diary-detail-title">
        <strong>{trade.symbol}</strong>
        <span className={`diary-trade-side ${trade.side.toLowerCase()}`}>{sideLabel(trade.side)}</span>
        <span>{trade.environment}</span>
        <span>{readinessLabel(trade)}</span>
      </div>

      <section className="diary-detail-section">
        <h3>Идентификация</h3>
        <dl>
          <div><dt>Эпизод сделки</dt><dd>{details.identity.trade_episode_id}</dd></div>
          <div><dt>Открыта</dt><dd>{formatDate(trade.opened_at_ms)}</dd></div>
          <div><dt>Закрыта</dt><dd>{formatDate(trade.closed_at_ms)}</dd></div>
          <div><dt>Контроллер / источник</dt><dd><Value value={details.identity.controller_origin} /></dd></div>
        </dl>
      </section>

      <section className="diary-detail-section">
        <h3>Решение</h3>
        <dl>
          <div><dt>Сетап</dt><dd><Value value={details.decision.setup_id} /></dd></div>
          <div><dt>Стратегия</dt><dd><Value value={details.decision.strategy} /></dd></div>
          <div><dt>Причина</dt><dd><Value value={details.decision.decision_reason} /></dd></div>
        </dl>
      </section>

      <section className="diary-detail-section">
        <h3>Риск</h3>
        <dl>
          <div><dt>Начальный риск</dt><dd><Value value={details.risk.initial_risk} /></dd></div>
          <div><dt>Стоп</dt><dd><Value value={details.risk.stop} /></dd></div>
          <div><dt>Тейк</dt><dd><Value value={details.risk.take_profit} /></dd></div>
        </dl>
      </section>

      <section className="diary-detail-section">
        <h3>Ордера / исполнения</h3>
        {details.orders_executions.length ? (
          <div className="diary-executions">
            {details.orders_executions.map((execution) => (
              <div key={`${execution.execution_id}:${execution.role}:${execution.occurred_at_ms}`}>
                <strong>{execution.role}</strong>
                <span>{execution.execution_id}</span>
                <span>{formatDate(execution.occurred_at_ms)}</span>
                <span>Количество {execution.quantity}</span>
                <span>Комиссия {execution.fee}</span>
              </div>
            ))}
          </div>
        ) : <p className="diary-missing">—</p>}
      </section>

      <section className="diary-detail-section">
        <h3>Ведение</h3>
        <dl>
          <div><dt>Цена открытия</dt><dd>{details.management.opening_price}</dd></div>
          <div><dt>Средняя цена входа</dt><dd>{details.management.average_entry}</dd></div>
          <div><dt>Открытый объём</dt><dd>{details.management.open_quantity}</dd></div>
        </dl>
      </section>

      <section className="diary-detail-section">
        <h3>Результат</h3>
        <dl>
          <div><dt>Статус</dt><dd>{details.outcome.status === "OPEN" ? "ОТКРЫТА" : "ЗАКРЫТА"}</dd></div>
          <div><dt>PnL по цене</dt><dd>{details.outcome.realized_price_pnl}</dd></div>
          <div><dt>Комиссии</dt><dd>{details.outcome.execution_fees}</dd></div>
          <div><dt>Чистый PnL</dt><dd><Value value={details.outcome.net_pnl} /></dd></div>
        </dl>
        {details.outcome.missing_reasons.length ? <small>{details.outcome.missing_reasons.join(", ")}</small> : null}
      </section>

      <section className="diary-detail-section">
        <h3>Автоматические факторы</h3>
        <p className="diary-missing">—</p>
      </section>

      <section className="diary-detail-section">
        <h3>Заметки / аннотации</h3>
        <p className="diary-missing">—</p>
      </section>
    </div>
  );
}

function SetupList({ setups }: { setups: DiarySetup[] }) {
  return (
    <div className="diary-setups-list">
      {setups.map((setup) => (
        <article className={`diary-setup-row ${setup.direction.toLowerCase()}`} key={setup.setup_instance_id}>
          <div className="diary-trade-heading">
            <strong>{setup.symbol}</strong>
            <span className="diary-trade-side">{sideLabel(setup.direction)}</span>
            <span>{setup.pattern}</span>
            <span>{setup.timeframe}</span>
            <span className={setup.needs_attention ? "attention" : ""}>{setup.status}</span>
          </div>

          <div className="diary-setup-metrics">
            <span>Создан {formatDate(setup.created_at_ms)}</span>
            <span>Режим входа {setup.entry_mode}</span>
            <span>Решение {setup.decision_state ?? "—"}</span>
            <span>Причина {setup.reason_code ?? "—"}</span>
          </div>

          <div className="diary-setup-metrics">
            <span>Сетап {setup.setup_id}</span>
            <span>Стратегия {setup.strategy_version}</span>
            <span>Контроллер {setup.controller ?? "—"}</span>
            <span>Сделка {setup.trade_episode_ids.length ? setup.trade_episode_ids.join(", ") : "—"}</span>
          </div>

          {setup.missing_evidence.length ? (
            <small className="diary-attention-detail">Не хватает данных: {setup.missing_evidence.join(", ")}</small>
          ) : null}
        </article>
      ))}
    </div>
  );
}

function MirrorList({ levels }: { levels: MirrorLevelRow[] }) {
  return (
    <div className="diary-setups-list">
      {levels.map((row) => (
        <article className={`diary-setup-row ${row.breakout?.campaign_direction?.toLowerCase() ?? ""}`} key={`${row.symbol}:${row.timeframe}:${row.level_id}`}>
          <div className="diary-trade-heading">
            <strong>{row.symbol}</strong>
            <span>{row.timeframe}m</span>
            <span className="diary-trade-side">{row.breakout ? `Пробой ${row.breakout.direction === "UP" ? "вверх" : "вниз"}` : "Ждёт пробоя"}</span>
            <span className={row.candidate ? "attention" : ""}>{row.candidate ? "КАНДИДАТ" : row.status}</span>
          </div>
          <div className="diary-setup-metrics">
            <span>Уровень {row.level_label}: {row.level_geometry_text}</span>
          </div>
          <div className="diary-setup-metrics">
            <span>Свеча пробоя {row.breakout ? `${formatDate(row.breakout.open_time_ms)} O ${row.breakout.open} C ${row.breakout.close}` : "—"}</span>
            <span>{row.breakout_evidence ? `${row.breakout_evidence.kind}${row.breakout_evidence.body_atr === null ? "" : ` ${row.breakout_evidence.body_atr.toFixed(2)} ATR`}` : "—"}</span>
          </div>
          <div className="diary-setup-metrics">
            <span>Ретест: {row.first_retest_text}</span>
            <span>Свежесть {row.freshness ?? "—"}</span>
            <span>Причина {row.rejection_reason ?? "—"}</span>
          </div>
          <div className="diary-setup-metrics">
            <span>FVG: {row.imbalance_text}</span>
          </div>
          <div className="diary-setup-metrics">
            <span>Источники {row.sources_text}</span>
            <span>Паттерн {row.parent_patterns.length ? row.parent_patterns.map((parent) => parent.pattern).join(", ") : "нет (swing)"}</span>
          </div>
          {row.robot ? <small className="diary-attention-detail">Робот: {row.robot.mode}, PAPER {row.robot.paper_admission} ({row.robot.paper_blockers.join(", ")})</small> : null}
        </article>
      ))}
    </div>
  );
}

function StatisticsView({ statistics }: { statistics: DiaryStatistics }) {
  const mae = statistics.coverage.post_trade_factors["trade.mae_pct"];
  const mfe = statistics.coverage.post_trade_factors["trade.mfe_pct"];
  const capture = statistics.coverage.post_trade_factors["trade.exit_capture_ratio"];
  return (
    <div className="diary-detail">
      <section className="diary-detail-section">
        <h3>Выборка</h3>
        <dl>
          <div><dt>Всего сделок</dt><dd>{statistics.sample.total}</dd></div>
          <div><dt>Готовы для чистого PnL</dt><dd>{statistics.sample.eligible_closed_ready}</dd></div>
          <div><dt>Открытые</dt><dd>{statistics.sample.excluded_open}</dd></div>
          <div><dt>Закрытые с неполными данными</dt><dd>{statistics.sample.excluded_incomplete}</dd></div>
        </dl>
      </section>

      <section className="diary-detail-section">
        <h3>Результативность</h3>
        <dl>
          <div><dt>Чистый PnL</dt><dd><Value value={statistics.pnl.net_pnl} /></dd></div>
          <div><dt>Средний PnL на сделку</dt><dd><Value value={statistics.pnl.average_net_pnl} /></dd></div>
          <div><dt>Прибыльные / убыточные / в ноль</dt><dd>{statistics.pnl.wins} / {statistics.pnl.losses} / {statistics.pnl.breakeven}</dd></div>
          <div><dt>Доля прибыльных</dt><dd>{formatRatio(statistics.pnl.win_rate)}</dd></div>
          <div><dt>Средняя прибыль</dt><dd><Value value={statistics.pnl.average_win} /></dd></div>
          <div><dt>Средний убыток</dt><dd><Value value={statistics.pnl.average_loss} /></dd></div>
          <div><dt>Средняя прибыль / средний убыток</dt><dd><Value value={statistics.pnl.payoff_ratio} /></dd></div>
          <div><dt>Профит-фактор</dt><dd><Value value={statistics.pnl.profit_factor} /></dd></div>
        </dl>
      </section>

      <section className="diary-detail-section">
        <h3>Удержание позиции</h3>
        <dl>
          <div><dt>Среднее время в сделке</dt><dd>{formatDurationValue(statistics.holding.average_duration_ms)}</dd></div>
        </dl>
      </section>

      <section className="diary-detail-section">
        <h3>Полнота данных</h3>
        <dl>
          <div><dt>Готовность чистого PnL</dt><dd>{formatRatio(statistics.coverage.pnl_ready_ratio)}</dd></div>
          <div><dt>Покрытие MAE</dt><dd>{mae ? `${mae.observed}/${mae.eligible_closed} (${formatRatio(mae.coverage_ratio)})` : "—"}</dd></div>
          <div><dt>Покрытие MFE</dt><dd>{mfe ? `${mfe.observed}/${mfe.eligible_closed} (${formatRatio(mfe.coverage_ratio)})` : "—"}</dd></div>
          <div><dt>Покрытие качества выхода</dt><dd>{capture ? `${capture.observed}/${capture.eligible_closed} (${formatRatio(capture.coverage_ratio)})` : "—"}</dd></div>
        </dl>
      </section>
    </div>
  );
}

function validClosedEpisodes(report: FinrezResponse): boolean {
  if (!Array.isArray(report.closed_episodes)) return false;
  const seen = new Set<string>();
  const owners = report.owner === "ROBOT"
    ? ["ROBOT", "ROBOT_MANUAL_CLOSE", "JOINT_MANAGEMENT"]
    : ["MANUAL", "JOINT_MANAGEMENT"];
  return report.closed_episodes.every((deal) => {
    if (!deal || typeof deal.trade_episode_id !== "string" || !deal.trade_episode_id.trim()
      || seen.has(deal.trade_episode_id) || typeof deal.symbol !== "string"
      || !/^[A-Z0-9]{3,30}$/.test(deal.symbol)
      || !["LONG", "SHORT"].includes(deal.side)
      || !owners.includes(deal.cohort)
      || deal.replay_evidence !== "EPISODE_INDEX_ONLY"
      || !Number.isSafeInteger(deal.opened_at_ms) || deal.opened_at_ms < 0
      || !Number.isSafeInteger(deal.closed_at_ms) || deal.closed_at_ms < deal.opened_at_ms
      || deal.closed_at_ms < report.period_start_ms || deal.closed_at_ms > report.as_of_ms
      || !Number.isSafeInteger(deal.execution_count) || deal.execution_count < 1
      || typeof deal.pnl_usdt !== "string" || !deal.pnl_usdt.trim()
      || !Number.isFinite(Number(deal.pnl_usdt))) return false;
    seen.add(deal.trade_episode_id);
    return true;
  });
}

const dealLabels: Record<ClosedEpisodeLocator["cohort"], string> = {
  ROBOT: "Робот",
  MANUAL: "Ручная сделка",
  ROBOT_MANUAL_CLOSE: "Робот · ручное закрытие",
  JOINT_MANAGEMENT: "Робот + ручное управление",
};

function ClosedDealsView({ report, symbolFilter, patternFilter, onClearSymbolFilter }: {
  report: FinrezResponse; symbolFilter: string; patternFilter: string;
  onClearSymbolFilter: () => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const tickerQuery = symbolFilter.trim().toUpperCase();
  const patternQuery = patternFilter.trim().toLocaleLowerCase("ru-RU");
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState("");
  const [verifiedExport, setVerifiedExport] = useState<{ episodeId: string; json: string } | null>(null);
  const [copyNotice, setCopyNotice] = useState("");
  const [showExportText, setShowExportText] = useState(false);
  const [filmNotice, setFilmNotice] = useState("");

  const [executionPoints, setExecutionPoints] = useState<TradeExecutionPoint[]>([]);
  const [verifiedSetups, setVerifiedSetups] = useState<Record<string, VerifiedEpisodeSetup | null>>({});
  const indexedVerifiedSetups = useMemo(() => {
    const proven: Record<string, VerifiedEpisodeSetup> = {};
    for (const deal of report.closed_episodes ?? []) {
      if (deal.opening_controller !== "ROBOT" && deal.opening_controller !== "MANUAL") continue;
      const setup = exactD2Setup({
        setup_context: deal.setup_context,
        execution_allocations: [{ controller: deal.opening_controller }],
      }, deal);
      if (setup) proven[deal.trade_episode_id] = setup;
    }
    return proven;
  }, [report.closed_episodes]);
  const setupFor = (episodeId: string): VerifiedEpisodeSetup | null =>
    Object.prototype.hasOwnProperty.call(verifiedSetups, episodeId)
      ? verifiedSetups[episodeId] : indexedVerifiedSetups[episodeId] ?? null;
  const deals = useMemo(() => (report.closed_episodes ?? []).filter((deal) => {
    if (!deal.symbol.includes(tickerQuery)) return false;
    if (!patternQuery) return true;
    const setup = Object.prototype.hasOwnProperty.call(verifiedSetups, deal.trade_episode_id)
      ? verifiedSetups[deal.trade_episode_id]
      : indexedVerifiedSetups[deal.trade_episode_id];
    return !!setup?.pattern.toLocaleLowerCase("ru-RU").includes(patternQuery);
  }), [report.closed_episodes, tickerQuery, patternQuery, verifiedSetups, indexedVerifiedSetups]);
  const selected = deals.find((deal) => deal.trade_episode_id === selectedId);
  const selectedSetup = selected ? setupFor(selected.trade_episode_id) : null;
  useEffect(() => {
    const deal = deals.find((entry) => entry.trade_episode_id === selectedId);
    setExecutionPoints([]);
    if (!deal) return;
    let active = true;
    void fetch(marketApiRoutes.diaryEpisodeFacts(
      report.account_id, report.owner, deal.trade_episode_id, report.source_revision,
    ), { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) return null;
        const value: unknown = await response.json();
        if (!value || typeof value !== "object") return null;
        const facts = value as Record<string, unknown>;
        if (facts.ok !== true || facts.schema !== "BYBITSCANNER_CLOSED_EPISODE_FACTS_V1"
          || facts.namespace !== "PAPER_READ_ONLY"
          || facts.source !== "PAPER_EXECUTIONS_ATTRIBUTED"
          || facts.account_id !== report.account_id || facts.owner !== report.owner
          || facts.trade_episode_id !== deal.trade_episode_id
          || facts.source_revision !== report.source_revision
          || facts.symbol !== deal.symbol || facts.side !== deal.side
          || facts.cohort !== deal.cohort
          || facts.opened_at_ms !== deal.opened_at_ms
          || facts.closed_at_ms !== deal.closed_at_ms
          || facts.pnl_usdt !== deal.pnl_usdt
          || facts.replay_evidence !== "EXECUTION_FACTS_ONLY_NO_DECISIONS_OR_CANDLES"
          || !Array.isArray(facts.execution_allocations)
          || facts.execution_allocations.length !== deal.execution_count
          || facts.execution_allocations.length > 5000) return null;
        const points: TradeExecutionPoint[] = [];
        for (const row of facts.execution_allocations) {
          if (!row || typeof row !== "object") return null;
          const entry = row as Record<string, unknown>;
          const price = Number(entry.execution_price);
          const at = entry.occurred_at_ms;
          if (typeof entry.execution_id !== "string" || !entry.execution_id ||
              typeof entry.execution_price !== "string" ||
              !Number.isFinite(price) || price <= 0 ||
              typeof at !== "number" || !Number.isSafeInteger(at) ||
              at < deal.opened_at_ms || at > deal.closed_at_ms) return null;
          points.push({ price, at });
        }
        return { points, setup: exactD2Setup(facts, deal) };
      })
      .then((result) => {
        if (!active || !result) return;
        setExecutionPoints(result.points);
        setVerifiedSetups((prior) => ({
          ...prior, [deal.trade_episode_id]: result.setup,
        }));
      })
      .catch(() => { /* No synthetic market data on archive errors. */ });
    return () => { active = false; };
  }, [selectedId, report.account_id, report.owner, report.source_revision, deals]);


  async function downloadFacts(deal: ClosedEpisodeLocator) {
    if (downloading) return;
    setDownloading(true);
    setDownloadError("");
    setVerifiedExport(null);
    setCopyNotice("");
    setShowExportText(false);
    try {
      const response = await fetch(marketApiRoutes.diaryEpisodeFacts(
        report.account_id, report.owner, deal.trade_episode_id, report.source_revision,
      ), { cache: "no-store" });
      if (response.status === 409) throw new Error("История обновилась — откройте Статистику заново.");
      if (!response.ok) throw new Error("Фактические исполнения этой сделки недоступны.");
      const raw: unknown = await response.json();
      if (!raw || typeof raw !== "object") throw new Error("Неверный формат истории сделки.");
      const facts = raw as Record<string, unknown>;
      if (facts.ok !== true || facts.schema !== "BYBITSCANNER_CLOSED_EPISODE_FACTS_V1"
        || facts.namespace !== "PAPER_READ_ONLY" || facts.source !== "PAPER_EXECUTIONS_ATTRIBUTED"
        || facts.account_id !== report.account_id || facts.owner !== report.owner
        || facts.source_revision !== report.source_revision
        || facts.trade_episode_id !== deal.trade_episode_id
        || facts.symbol !== deal.symbol || facts.side !== deal.side || facts.cohort !== deal.cohort
        || facts.opened_at_ms !== deal.opened_at_ms || facts.closed_at_ms !== deal.closed_at_ms
        || facts.pnl_usdt !== deal.pnl_usdt
        || facts.replay_evidence !== "EXECUTION_FACTS_ONLY_NO_DECISIONS_OR_CANDLES"
        || !Array.isArray(facts.execution_allocations)
        || facts.execution_allocations.length !== deal.execution_count
        || facts.execution_allocations.some((item: unknown) =>
          !item || typeof item !== "object" || !("execution_id" in item)
          || typeof item.execution_id !== "string" || !("execution_price" in item)
          || typeof item.execution_price !== "string"
        )) throw new Error("История сделки не совпала с выбранным эпизодом.");

      const json = JSON.stringify(facts, null, 2) + "\n";
      setVerifiedExport({ episodeId: deal.trade_episode_id, json });
      const blob = new Blob([json], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      try {
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `episode-${deal.trade_episode_id}.json`;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
      } finally {
        window.setTimeout(() => URL.revokeObjectURL(url), 0);
      }
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : "Не удалось выгрузить сделку.");
    } finally {
      setDownloading(false);
    }
  }

  if (selected) {
    return (
      <div className="diary-detail" aria-label="Детали закрытой сделки">
        <button className="diary-detail-back" onClick={() => setSelectedId(null)} type="button">← К сделкам</button>
        <div className="diary-detail-title">
          <strong>{selected.symbol}</strong>
          <span>{sideLabel(selected.side)}</span>
          <span>{dealLabels[selected.cohort]}</span>
        </div>
        <section className="diary-detail-section">
          <h3>Исторический эпизод</h3>
          <dl>
            <div><dt>ID сделки</dt><dd>{selected.trade_episode_id}</dd></div>
            <div><dt>Открыта</dt><dd>{formatDate(selected.opened_at_ms)}</dd></div>
            <div><dt>Закрыта</dt><dd>{formatDate(selected.closed_at_ms)}</dd></div>
            <div><dt>Исполнений</dt><dd>{selected.execution_count}</dd></div>
            <div><dt>PnL после комиссий</dt><dd title={selected.pnl_usdt}>{displayTradePnl(selected.pnl_usdt)} USDT</dd></div>
          </dl>
        </section>
        <section className="diary-detail-section" aria-label="Связь сделки с паттерном">
          <h3>Сетап и паттерн</h3>
          {selectedSetup ? (
            <dl>
              <div><dt>Паттерн</dt><dd>{selectedSetup.pattern}</dd></div>
              <div><dt>Таймфрейм</dt><dd>{selectedSetup.timeframe}</dd></div>
              <div><dt>ID сетапа</dt><dd>{selectedSetup.setupId}</dd></div>
              <div><dt>Версия стратегии</dt><dd>{selectedSetup.strategyVersion}</dd></div>
            </dl>
          ) : <p className="diary-finrez-basis">Связь с паттерном по точному ID не подтверждена.</p>}
          <small>Источник при наличии связи: отдельные наблюдения Trading Diary D2, не полный журнал решений Робота.</small>
        </section>
        <TradeExecutionPriceChart points={executionPoints} />
        <SimulatorLaunchAction episodeId={selected.trade_episode_id}
          allowLocalLaunch={report.account_id === "paper"} />
        <button className="diary-detail-back" type="button" disabled={downloading}
          onClick={() => void downloadFacts(selected)}>
          {downloading ? "Выгружаю факты…" : "Скачать JSON исполнений"}
        </button>
        {downloadError ? <p className="diary-finrez-coverage" role="alert">{downloadError}</p> : null}
        {verifiedExport?.episodeId === selected.trade_episode_id ? (
          <div className="diary-detail-section">
            <p>Если Telegram не сохранил файл, скопируйте проверенный JSON сделки.</p>
            <button className="diary-detail-back" type="button" onClick={() => {
              setCopyNotice("");
              void (async () => {
                try {
                  if (!navigator.clipboard?.writeText) throw new Error("clipboard unavailable");
                  await navigator.clipboard.writeText(verifiedExport.json);
                  setCopyNotice("JSON скопирован в буфер обмена.");
                } catch {
                  setShowExportText(true);
                  setCopyNotice("Копирование недоступно. Выделите JSON ниже и скопируйте вручную.");
                }
              })();
            }}>Скопировать JSON</button>
            {copyNotice ? <p role="status">{copyNotice}</p> : null}
            {showExportText ? <textarea readOnly aria-label="Проверенный JSON сделки"
              value={verifiedExport.json} rows={8} style={{ width: "100%" }} /> : null}
          </div>
        ) : null}
        <p className="diary-finrez-basis" role="status">
          Это не воспроизведение. JSON содержит только реальные зарегистрированные исполнения. Свечи, решения робота
          и полное воспроизведение в локальном Симуляторе пока не подключены.
        </p>
      </div>
    );
  }
  return (
    <div className="diary-detail" aria-label="Закрытые сделки по эпизодам">
      {tickerQuery !== "" ? (
        <div className="diary-finrez-filter">
          <button type="button" className="diary-detail-back" onClick={onClearSymbolFilter}>
            {patternQuery ? "← Все тикеры" : "← Все сделки"}
          </button>
          <span>Сделки по {tickerQuery}</span>
        </div>
      ) : null}
      {report.attribution_coverage.status === "PARTIAL" ? (
        <p className="diary-finrez-coverage" role="status">
          История неполная: исключено {report.attribution_coverage.excluded_unattributed_episode_count} эпизодов
          с неизвестным источником исполнений.
        </p>
      ) : null}
      {deals.length === 0 ? <p className="diary-state">
        {patternQuery ? "По выбранным фильтрам сделок нет" : "Нет подтверждённых закрытых сделок за выбранный период"}
      </p> : (
        <div className="diary-trades-list">
          {deals.map((deal) => (
            <div className={`diary-trade-entry ${deal.side.toLowerCase()}`} key={deal.trade_episode_id}>
              <button className={`diary-trade-row ${deal.side.toLowerCase()}`}
                type="button" onClick={() => setSelectedId(deal.trade_episode_id)}>
              <div className="diary-trade-heading">
                <strong>{deal.symbol}</strong>
                <span className="diary-deal-pattern"
                  title={setupFor(deal.trade_episode_id)
                    ? "Точная связь эпизода с наблюдательным сетапом Diary D2"
                    : "Связь сделки с паттерном пока не подтверждена"}>
                  {"Паттерн: " + (setupFor(deal.trade_episode_id)?.pattern ?? "не установлен")}
                </span>
                <span>{sideLabel(deal.side)}</span><span>{dealLabels[deal.cohort]}</span>
              </div>
              <div className="diary-trade-times">
                <span>{formatDate(deal.opened_at_ms)}</span><span>→</span><span>{formatDate(deal.closed_at_ms)}</span>
              </div>
              <div className="diary-trade-metrics">
                <span className={Number(deal.pnl_usdt) > 0 ? "profit" : Number(deal.pnl_usdt) < 0 ? "loss" : ""}
                  title={deal.pnl_usdt}>PnL {displayTradePnl(deal.pnl_usdt)} USDT</span>
                <span title="Процент недоступен без подтверждённой базы расчёта">PnL %: —</span>
                <span>Исполнений: {deal.execution_count}</span>
              </div>
              </button>
              <TradeActionButtons onDetails={() => setSelectedId(deal.trade_episode_id)}
                onReplay={/^te_[0-9a-f]{24}$/.test(deal.trade_episode_id) && report.account_id === "paper"
                  ? () => requestSimulatorLocator(deal.trade_episode_id, setFilmNotice) : undefined} />
            </div>
          ))}
        </div>
      )}
      {filmNotice ? <p className="diary-finrez-coverage" role="status">{filmNotice}</p> : null}
      {downloadError ? <p className="diary-finrez-coverage" role="alert">{downloadError}</p> : null}
      <p className="diary-finrez-basis">
        Киноплёнка передаёт в локальный Симулятор только ID сделки. История свечей и решения робота автоматически не загружаются. Фактические исполнения доступны через JSON в карточке сделки.
      </p>
    </div>
  );
}

function FinrezTickerRow({ ticker, onSelectTicker }: {
  ticker: FinrezTicker; onSelectTicker: (symbol: string) => void;
}) {
  return (
    <div className="diary-finrez-row">
      <strong>{ticker.symbol}</strong>
      <span className={Number(ticker.pnl_usdt) > 0 ? "profit" : Number(ticker.pnl_usdt) < 0 ? "loss" : ""}>
        {Number(ticker.pnl_usdt) > 0 ? "+" : ""}{displayTradePnl(ticker.pnl_usdt)} USDT
      </span>
      <button type="button" className="diary-finrez-list-button"
        aria-label={`Показать сделки по ${ticker.symbol}`}
        title="Показать отдельные сделки по тикеру"
        onClick={() => onSelectTicker(ticker.symbol)}>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01" />
        </svg>
      </button>
    </div>
  );
}

function FinrezView({ report, symbolFilter, onSelectTicker }: {
  report: FinrezResponse; symbolFilter: string; onSelectTicker: (symbol: string) => void;
}) {
  const tickerQuery = symbolFilter.trim().toUpperCase();
  const matchesTicker = (ticker: FinrezTicker) => ticker.symbol.includes(tickerQuery);
  return (
    <div className="diary-finrez" aria-label="Финансовый результат по тикерам">
      <p className="diary-finrez-basis">
        {report.owner === "ROBOT" ? "Только полностью роботизированные сделки" : "Только ручные сделки"}
        {" · "}Реализованный PnL (цена − комиссии исполнений) · USDT
      </p>
      {report.attribution_coverage.status === "PARTIAL" ? (
        <p className="diary-finrez-coverage" role="status">
          История неполная: исключено {report.attribution_coverage.excluded_unattributed_episode_count} закрытых
          { " " }эпизодов ({report.attribution_coverage.excluded_unattributed_execution_count} исполнений
          { " " }без подтверждённого происхождения). Показанный PnL — только по достоверно
          атрибутированным сделкам, не полный результат за период.
        </p>
      ) : null}
      {report.tickers.filter(matchesTicker).length === 0 ? (
        <p className="diary-state">
          {report.tickers.length > 0
            ? "По заданному тикеру результатов нет"
            : report.attribution_coverage.status === "PARTIAL"
              ? "Нет достоверно атрибутированных закрытых сделок этого типа за выбранный период"
              : "Нет закрытых сделок этого типа за выбранный период"}
        </p>
      ) : (
        <div className="diary-finrez-list">
          {report.tickers.filter(matchesTicker).map((ticker) => (
            <FinrezTickerRow key={ticker.symbol} ticker={ticker} onSelectTicker={onSelectTicker} />
          ))}
        </div>
      )}
      {report.manual_interventions.length > 0 ? (
        <section className="diary-finrez-interventions" aria-label="Ручные закрытия сделок робота">
          <h3>Робот · ручное вмешательство</h3>
          <p className="diary-finrez-basis">
            Результат сделок, открытых роботом и закрытых вручную, показан отдельно.
            В PnL полностью роботизированных сделок не включён.
          </p>
          <div className="diary-finrez-list">
            {report.manual_interventions.filter(matchesTicker).map((ticker) => (
            <FinrezTickerRow key={ticker.symbol} ticker={ticker} onSelectTicker={onSelectTicker} />
          ))}
          </div>
        </section>
      ) : null}
      {report.joint_management.length > 0 ? (
        <section className="diary-finrez-interventions" aria-label="Совместно управляемые сделки">
          <h3>Совместное управление · ROBOT + MANUAL</h3>
          <p className="diary-finrez-basis">
            Общий PnL позиции, увеличенной вручную после входа робота и закрытой роботом.
            Не входит в итоги ROBOT или MANUAL. Одинаковый результат показан в обоих разделах — не складывайте его дважды.
          </p>
          <div className="diary-finrez-list">
            {report.joint_management.filter(matchesTicker).map((ticker) => (
            <FinrezTickerRow key={ticker.symbol} ticker={ticker} onSelectTicker={onSelectTicker} />
          ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

export function DiaryOverlay({
  accountKey,
  onClose,
  initialSection = "TRADES",
  initialTradeEpisodeId = null,
  statisticsScope = null,
  accountMenu = null,
}: {
  accountKey: string;
  onClose: () => void;
  initialSection?: DiarySection;
  initialTradeEpisodeId?: string | null;
  statisticsScope?: DiaryStatisticsScope | null;
  accountMenu?: DiaryAccountMenuProps | null;
}) {
  const [section, setSection] = useState<DiarySection>(
    initialTradeEpisodeId === null ? initialSection : "TRADES",
  );
  const [trades, setTrades] = useState<DiaryTrade[]>([]);
  const [setups, setSetups] = useState<DiarySetup[]>([]);
  const [statistics, setStatistics] = useState<DiaryStatistics | null>(null);
  const [finrez, setFinrez] = useState<FinrezResponse | null>(null);
  const [finrezPeriod, setFinrezPeriod] = useState<FinrezPeriod>("DAY");
  const [finrezSymbolFilter, setFinrezSymbolFilter] = useState("");
  const [finrezPatternFilter, setFinrezPatternFilter] = useState("");
  const [pendingFinrezTicker, setPendingFinrezTicker] = useState<string | null>(null);
  const [mirrorLevels, setMirrorLevels] = useState<MirrorLevelRow[]>([]);
  const [tradeFilter, setTradeFilter] = useState<DiaryFilter>("ALL");
  const [setupFilter, setSetupFilter] = useState<SetupFilter>("ALL");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [accountId, setAccountId] = useState("");
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const [selectedTradeId, setSelectedTradeId] = useState<string | null>(null);
  const [tradeFilmNotice, setTradeFilmNotice] = useState("");
  const [requestedTradeMissing, setRequestedTradeMissing] = useState(false);
  const initialTradeRequest = useRef<string | null>(initialTradeEpisodeId);
  const requestSequence = useRef(0);

  const refresh = useCallback(async () => {
    const token = ++requestSequence.current;
    const current = () => token === requestSequence.current;
    setLoading(true);
    setLoadError(false);
    if (section === "STATISTICS") setStatistics(null);
    if (section === "FINREZ" || section === "DEALS") setFinrez(null);
    try {
      if (section === "FINREZ" || section === "DEALS") {
        if (!statisticsScope) throw new Error("finrez scope required");
        const response = await fetch(marketApiRoutes.diaryTickerFinrez(
          statisticsScope.accountId, statisticsScope.owner, finrezPeriod,
        ));
        if (!response.ok) throw new Error("finrez report unavailable");
        const result = (await response.json()) as FinrezResponse;
        if (!current()) return;
        const seen = new Set<string>();
        if (!result.ok || result.account_id !== statisticsScope.accountId
          || result.owner !== statisticsScope.owner || result.period !== finrezPeriod
          || result.source !== "PAPER_EXECUTIONS_ATTRIBUTED"
          || result.pnl_basis !== "REALIZED_PRICE_MINUS_EXECUTION_FEES"
          || !Number.isSafeInteger(result.source_revision) || result.source_revision < 1
          || !Number.isSafeInteger(result.period_start_ms) || result.period_start_ms < 0
          || !Number.isSafeInteger(result.as_of_ms) || result.as_of_ms < result.period_start_ms
          || !result.attribution_coverage
          || !["COMPLETE", "PARTIAL"].includes(result.attribution_coverage.status)
          || !Number.isSafeInteger(result.attribution_coverage.excluded_unattributed_episode_count)
          || result.attribution_coverage.excluded_unattributed_episode_count < 0
          || !Number.isSafeInteger(result.attribution_coverage.excluded_unattributed_execution_count)
          || result.attribution_coverage.excluded_unattributed_execution_count < 0
          || (result.attribution_coverage.status === "COMPLETE"
            && (result.attribution_coverage.excluded_unattributed_episode_count !== 0
              || result.attribution_coverage.excluded_unattributed_execution_count !== 0))
          || (result.attribution_coverage.status === "PARTIAL"
            && (result.attribution_coverage.excluded_unattributed_episode_count === 0
              || result.attribution_coverage.excluded_unattributed_execution_count === 0
              || result.attribution_coverage.excluded_unattributed_execution_count
                < result.attribution_coverage.excluded_unattributed_episode_count))
          || !Array.isArray(result.tickers) || result.tickers.some((row) => {
            if (typeof row.symbol !== "string" || !row.symbol || seen.has(row.symbol)
              || typeof row.pnl_usdt !== "string" || !row.pnl_usdt.trim()
              || !Number.isFinite(Number(row.pnl_usdt))
              || !Number.isSafeInteger(row.trade_count) || row.trade_count < 1) return true;
            seen.add(row.symbol);
            return false;
          })
          || !Array.isArray(result.manual_interventions)
          || (result.owner !== "ROBOT" && result.manual_interventions.length > 0)
          || result.manual_interventions.some((row, index) =>
            typeof row.symbol !== "string" || !row.symbol
            || result.manual_interventions.slice(0, index).some((item) => item.symbol === row.symbol)
            || typeof row.pnl_usdt !== "string" || !row.pnl_usdt.trim()
            || !Number.isFinite(Number(row.pnl_usdt))
            || !Number.isSafeInteger(row.trade_count) || row.trade_count < 1
          )
          || !Array.isArray(result.joint_management)
          || result.joint_management.some((row, index) =>
            typeof row.symbol !== "string" || !row.symbol
            || result.joint_management.slice(0, index).some((item) => item.symbol === row.symbol)
            || typeof row.pnl_usdt !== "string" || !row.pnl_usdt.trim()
            || !Number.isFinite(Number(row.pnl_usdt))
            || !Number.isSafeInteger(row.trade_count) || row.trade_count < 1
          ) || (section === "DEALS" && !validClosedEpisodes(result))) throw new Error("finrez scope/data mismatch");
        setRequestedTradeMissing(false);
        setFinrez(result);
        setAccountId(result.account_id);
      } else if (section === "PATTERNS") {
        // Pattern tab intentionally deferred until owner visual acceptance.
        setRequestedTradeMissing(false);
      } else if (section === "TRADES") {
        const response = await fetch(marketApiRoutes.diaryTrades);
        if (!response.ok) throw new Error("diary request failed");
        const result = (await response.json()) as DiaryTradesResponse;
        if (!current()) return;
        if (!result.ok || !Array.isArray(result.trades)) throw new Error("diary response is invalid");
        if (statisticsScope && result.active_account_id !== statisticsScope.accountId) {
          throw new Error("diary account mismatch");
        }
        setTrades(result.trades);
        setAccountId(result.active_account_id);
        const requestedTradeId = initialTradeRequest.current;
        if (requestedTradeId !== null) {
          initialTradeRequest.current = null;
          const linkedTrade = result.trades.find((trade) => trade.trade_episode_id === requestedTradeId);
          setSelectedTradeId(linkedTrade?.trade_episode_id ?? null);
          setRequestedTradeMissing(linkedTrade === undefined);
        } else {
          setRequestedTradeMissing(false);
          setSelectedTradeId((value) => value && result.trades.some((trade) => trade.trade_episode_id === value) ? value : null);
        }
      } else if (section === "SETUPS") {
        const response = await fetch(marketApiRoutes.diarySetups);
        if (!response.ok) throw new Error("diary setups request failed");
        const result = (await response.json()) as DiarySetupsResponse;
        if (!current()) return;
        if (!result.ok || !Array.isArray(result.setups)) throw new Error("diary setups response is invalid");
        setRequestedTradeMissing(false);
        setSetups(result.setups);
      } else if (section === "MIRROR") {
        const response = await fetch(marketApiRoutes.scannerMirrorLevels);
        if (!response.ok) throw new Error("mirror levels request failed");
        const result = (await response.json()) as MirrorLevelsResponse;
        if (!current()) return;
        if (!result.ok || !Array.isArray(result.levels)) throw new Error("mirror levels response is invalid");
        setRequestedTradeMissing(false);
        setMirrorLevels(result.levels);
      } else {
        // No legacy global-statistics fallback: a missing account/owner is an
        // unavailable report, not permission to display unrelated PnL.
        if (!statisticsScope) throw new Error("diary scope required");
        const response = await fetch(marketApiRoutes.diaryScopedStatistics(
          statisticsScope.accountId, statisticsScope.owner,
        ));
        if (!response.ok) throw new Error("scoped statistics unavailable");
        const result = (await response.json()) as DiaryStatisticsResponse;
        if (!current()) return;
        if (!result.ok || result.account_id !== statisticsScope.accountId
          || result.owner !== statisticsScope.owner
          || !Number.isSafeInteger(result.source_revision) || result.source_revision < 1
          || !result.statistics) {
          throw new Error("diary statistics scope mismatch");
        }
        setRequestedTradeMissing(false);
        setStatistics(result.statistics);
        setAccountId(result.account_id);
      }
    } catch {
      if (current()) setLoadError(true);
    } finally {
      if (current()) setLoading(false);
    }
  }, [section, statisticsScope?.accountId, statisticsScope?.owner, finrezPeriod]);

  useEffect(() => {
    setStatistics(null);
    setFinrez(null);
    setTrades([]);
    setSelectedTradeId(null);
    setRequestedTradeMissing(false);
    setAccountId(statisticsScope?.accountId ?? "");
    void refresh();
    return () => { ++requestSequence.current; };
  }, [accountKey, refresh, statisticsScope?.accountId, statisticsScope?.owner]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (selectedTradeId !== null) setSelectedTradeId(null);
        else onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, selectedTradeId]);

  const visibleTrades = useMemo(() => trades.filter((trade) => matchesTradeFilter(trade, tradeFilter)), [tradeFilter, trades]);
  const visibleSetups = useMemo(() => setups.filter((setup) => setupFilter === "ALL" || setup.needs_attention), [setupFilter, setups]);
  const selectedTrade = useMemo(() => trades.find((trade) => trade.trade_episode_id === selectedTradeId) ?? null, [selectedTradeId, trades]);

  return (
    <div className="diary-backdrop" role="presentation">
      <section className="diary-shell" role="dialog" aria-modal="true" aria-label="Статистика">
        <header className="diary-header">
          {accountMenu ? (
            <AccountMenu {...accountMenu} open={accountMenuOpen}
              onToggle={() => setAccountMenuOpen((open) => !open)} />
          ) : (
            <button className="diary-account-unavailable" type="button" disabled
              aria-label="Переключение счёта недоступно">
              Счёт: {statisticsScope?.accountId ?? accountId ?? "не выбран"}
            </button>
          )}
          <button aria-label="Закрыть статистику" onClick={onClose} type="button">×</button>
        </header>

        <div className="diary-context-heading">
          <p>{statisticsScope?.owner === "ROBOT" ? "Автопилот" : "Терминал"}</p>
          <h2>Статистика</h2>
        </div>

        <div className="diary-navigation">
          {(section === "FINREZ" || section === "PATTERNS" || section === "DEALS") ? (
            <nav className="diary-period-nav" aria-label="Период статистики">
              {([
                ["DAY", "День"], ["WEEK", "Неделя"],
                ["MONTH", "Месяц"], ["YEAR", "Год"], ["ALL", "Всё время"],
              ] as const).map(([period, label]) => (
                <button key={period} aria-pressed={finrezPeriod === period} type="button"
                  onClick={() => { setPendingFinrezTicker(null); setFinrezPeriod(period); }}>{label}</button>
              ))}
            </nav>
          ) : null}
          <nav className="diary-primary-nav" aria-label="Разделы статистики">
            <button aria-current={section === "FINREZ" || section === "STATISTICS" ? "page" : undefined} onClick={() => { setSelectedTradeId(null); setPendingFinrezTicker(null); setSection("FINREZ"); }} type="button">Финрез</button>
            <button aria-current={section === "PATTERNS" || section === "SETUPS" ? "page" : undefined} onClick={() => { setSelectedTradeId(null); setPendingFinrezTicker(null); setSection("PATTERNS"); }} type="button">Паттерны</button>
            <button aria-current={section === "DEALS" || section === "TRADES" ? "page" : undefined} onClick={() => { setSelectedTradeId(null); setPendingFinrezTicker(null); setSection("DEALS"); }} type="button">Сделки</button>
          </nav>
          {(section === "FINREZ" || section === "PATTERNS" || section === "DEALS") ? (
            <div className="diary-ticker-search">
              <input aria-label="Поиск по тикеру" type="search" placeholder="Поиск тикера"
                value={finrezSymbolFilter}
                onChange={(event) => setFinrezSymbolFilter(event.target.value.toUpperCase())} />
              {section === "DEALS" ? (
                <input aria-label="Поиск по паттерну" type="search"
                  placeholder="Поиск паттерна" value={finrezPatternFilter}
                  onChange={(event) => setFinrezPatternFilter(event.target.value)} />
              ) : null}
            </div>
          ) : null}
          {!selectedTrade && (section === "TRADES" || section === "SETUPS") ? (
            <div className="diary-filter-bar" aria-label={section === "TRADES" ? "Фильтры сделок" : "Фильтры сетапов"}>
              {(section === "TRADES" ? tradeFilters : setupFilters).map((candidate) => {
                const pressed = section === "TRADES" ? tradeFilter === candidate.id : setupFilter === candidate.id;
                return (
                  <button aria-pressed={pressed} key={candidate.id}
                    onClick={() => section === "TRADES" ? setTradeFilter(candidate.id as DiaryFilter) : setSetupFilter(candidate.id as SetupFilter)}
                    type="button">{candidate.label}</button>
                );
              })}
            </div>
          ) : null}
        </div>

        <div className="diary-content">
          {pendingFinrezTicker !== null ? (
            <div className="diary-finrez-confirm" role="alertdialog" aria-label="Переход к сделкам">
              <p>Открыть все сделки по {pendingFinrezTicker} за выбранный период?</p>
              <div>
                <button type="button" onClick={() => {
                  setFinrezSymbolFilter(pendingFinrezTicker);
                  setPendingFinrezTicker(null);
                  setSection("DEALS");
                }}>Открыть сделки</button>
                <button type="button" onClick={() => setPendingFinrezTicker(null)}>Отмена</button>
              </div>
            </div>
          ) : null}
          {loading ? <p className="diary-state">Загрузка...</p> : null}
          {!loading && loadError ? (
            <div className="diary-state">
              <p>Не удалось загрузить статистику выбранного счёта</p>
              <button onClick={() => void refresh()} type="button">Повторить</button>
            </div>
          ) : null}

          {!loading && !loadError && !selectedTrade && section === "FINREZ" && finrez ? <FinrezView report={finrez}
            symbolFilter={finrezSymbolFilter} onSelectTicker={setPendingFinrezTicker} /> : null}
          {!loading && !loadError && !selectedTrade && section === "PATTERNS" ? <p className="diary-state">Паттерны — второй этап после визуальной приёмки «Финреза»</p> : null}
          {!loading && !loadError && !selectedTrade && section === "DEALS" && finrez ? (
            <ClosedDealsView key={`${finrez.account_id}:${finrez.owner}:${finrez.period}:${finrez.source_revision}:${finrezSymbolFilter}:${finrezPatternFilter}`}
              report={finrez} symbolFilter={finrezSymbolFilter} patternFilter={finrezPatternFilter}
              onClearSymbolFilter={() => setFinrezSymbolFilter("")} />
          ) : null}
          {!loading && !loadError && selectedTrade ? <TradeDetailsView trade={selectedTrade} onBack={() => { setRequestedTradeMissing(false); setSelectedTradeId(null); }} /> : null}
          {!loading && !loadError && requestedTradeMissing && section === "TRADES" ? <p className="diary-state">Сделка недоступна в текущем дневнике</p> : null}
          {!loading && !loadError && !requestedTradeMissing && !selectedTrade && section === "TRADES" && visibleTrades.length === 0 ? <p className="diary-state">Нет сделок в этом фильтре</p> : null}
          {!loading && !loadError && !selectedTrade && section === "SETUPS" && visibleSetups.length === 0 ? <p className="diary-state">Нет сетапов в этом фильтре</p> : null}

          {tradeFilmNotice && section === "TRADES" && !selectedTrade
            ? <p className="diary-finrez-coverage" role="status">{tradeFilmNotice}</p> : null}

          {!loading && !loadError && !requestedTradeMissing && !selectedTrade && section === "TRADES" && visibleTrades.length > 0 ? (
            <div className="diary-trades-list">
              {visibleTrades.map((trade) => (
                <div className={`diary-trade-entry ${trade.side.toLowerCase()}`} key={trade.trade_episode_id}>
                <button className={`diary-trade-row ${trade.side.toLowerCase()}`} onClick={() => setSelectedTradeId(trade.trade_episode_id)} type="button">
                  <div className="diary-trade-heading">
                    <strong>{trade.symbol}</strong>
                    <span className="diary-trade-side">{sideLabel(trade.side)}</span>
                    <span>{trade.environment}</span>
                    <span className={trade.needs_attention ? "attention" : ""}>{readinessLabel(trade)}</span>
                  </div>
                  <div className="diary-trade-times">
                    <span>{formatDate(trade.opened_at_ms)}</span>
                    <span>→</span>
                    <span>{trade.closed_at_ms === null ? "Открыта" : formatDate(trade.closed_at_ms)}</span>
                    <span>{formatDuration(trade.holding_duration_ms)}</span>
                  </div>
                  <div className="diary-trade-metrics">
                    <span>Вход {trade.average_entry || "—"}</span>
                    <span>{trade.closed_at_ms === null ? `Открыто ${trade.open_quantity}` : `Выход ${trade.exit_price ?? "—"}`}</span>
                    <span className={trade.pnl !== null && Number(trade.pnl) > 0 ? "profit" : trade.pnl !== null && Number(trade.pnl) < 0 ? "loss" : ""} title={trade.pnl ?? undefined}>PnL {displayTradePnl(trade.pnl)}</span>
                  </div>
                  {trade.controller_origin ? <small>Источник: {trade.controller_origin}</small> : null}
                </button>
                <TradeActionButtons onDetails={() => setSelectedTradeId(trade.trade_episode_id)}
                  onReplay={trade.environment === "PAPER" && /^te_[0-9a-f]{24}$/.test(trade.trade_episode_id)
                    ? () => requestSimulatorLocator(trade.trade_episode_id, setTradeFilmNotice) : undefined} />
                </div>
              ))}
            </div>
          ) : null}

          {!loading && !loadError && !selectedTrade && section === "SETUPS" && visibleSetups.length > 0 ? <SetupList setups={visibleSetups} /> : null}
          {!loading && !loadError && !selectedTrade && section === "STATISTICS" && statistics ? <StatisticsView statistics={statistics} /> : null}
          {!loading && !loadError && !selectedTrade && section === "MIRROR" && mirrorLevels.length === 0 ? <p className="diary-state">Нет MIRROR-уровней с пробоем</p> : null}
          {!loading && !loadError && !selectedTrade && section === "MIRROR" && mirrorLevels.length > 0 ? <MirrorList levels={mirrorLevels} /> : null}
        </div>
      </section>
    </div>
  );
}

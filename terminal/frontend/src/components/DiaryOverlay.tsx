import { useCallback, useEffect, useMemo, useState } from "react";
import { marketApiRoutes } from "../marketData/apiRoutes";
import "./DiaryOverlay.css";

type DiarySection = "TRADES" | "SETUPS";
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
  if (hours < 24) {
    return remainder ? `${hours}ч ${remainder}м` : `${hours}ч`;
  }

  const days = Math.floor(hours / 24);
  return `${days}д ${hours % 24}ч`;
}

function readinessLabel(trade: DiaryTrade): string {
  if (trade.readiness === "OPEN") return "OPEN";
  if (trade.readiness === "CLOSED_READY") return "READY";
  return "Нужны данные";
}

function matchesTradeFilter(
  trade: DiaryTrade,
  filter: DiaryFilter,
): boolean {
  if (filter === "OPEN") return trade.closed_at_ms === null;
  if (filter === "CLOSED") return trade.closed_at_ms !== null;
  if (filter === "ATTENTION") return trade.needs_attention;
  return true;
}

function Value({ value }: { value: string | null | undefined }) {
  return <span>{value ?? "—"}</span>;
}

function TradeDetailsView({
  trade,
  onBack,
}: {
  trade: DiaryTrade;
  onBack: () => void;
}) {
  const details = trade.details;
  return (
    <div className="diary-detail">
      <button className="diary-detail-back" onClick={onBack} type="button">
        ← Trades
      </button>

      <div className="diary-detail-title">
        <strong>{trade.symbol}</strong>
        <span className={`diary-trade-side ${trade.side.toLowerCase()}`}>
          {trade.side}
        </span>
        <span>{trade.environment}</span>
        <span>{readinessLabel(trade)}</span>
      </div>

      <section className="diary-detail-section">
        <h3>Identity</h3>
        <dl>
          <div><dt>Trade episode</dt><dd>{details.identity.trade_episode_id}</dd></div>
          <div><dt>Открыта</dt><dd>{formatDate(trade.opened_at_ms)}</dd></div>
          <div><dt>Закрыта</dt><dd>{formatDate(trade.closed_at_ms)}</dd></div>
          <div><dt>Controller / origin</dt><dd><Value value={details.identity.controller_origin} /></dd></div>
        </dl>
      </section>

      <section className="diary-detail-section">
        <h3>Decision</h3>
        <dl>
          <div><dt>Setup</dt><dd><Value value={details.decision.setup_id} /></dd></div>
          <div><dt>Strategy</dt><dd><Value value={details.decision.strategy} /></dd></div>
          <div><dt>Reason</dt><dd><Value value={details.decision.decision_reason} /></dd></div>
        </dl>
      </section>

      <section className="diary-detail-section">
        <h3>Risk</h3>
        <dl>
          <div><dt>Initial risk</dt><dd><Value value={details.risk.initial_risk} /></dd></div>
          <div><dt>STOP</dt><dd><Value value={details.risk.stop} /></dd></div>
          <div><dt>TAKE</dt><dd><Value value={details.risk.take_profit} /></dd></div>
        </dl>
      </section>

      <section className="diary-detail-section">
        <h3>Orders / Executions</h3>
        {details.orders_executions.length ? (
          <div className="diary-executions">
            {details.orders_executions.map((execution) => (
              <div key={`${execution.execution_id}:${execution.role}:${execution.occurred_at_ms}`}>
                <strong>{execution.role}</strong>
                <span>{execution.execution_id}</span>
                <span>{formatDate(execution.occurred_at_ms)}</span>
                <span>Qty {execution.quantity}</span>
                <span>Fee {execution.fee}</span>
              </div>
            ))}
          </div>
        ) : <p className="diary-missing">—</p>}
      </section>

      <section className="diary-detail-section">
        <h3>Management</h3>
        <dl>
          <div><dt>Opening price</dt><dd>{details.management.opening_price}</dd></div>
          <div><dt>Average entry</dt><dd>{details.management.average_entry}</dd></div>
          <div><dt>Open quantity</dt><dd>{details.management.open_quantity}</dd></div>
        </dl>
      </section>

      <section className="diary-detail-section">
        <h3>Outcome</h3>
        <dl>
          <div><dt>Status</dt><dd>{details.outcome.status}</dd></div>
          <div><dt>Price PnL</dt><dd>{details.outcome.realized_price_pnl}</dd></div>
          <div><dt>Execution fees</dt><dd>{details.outcome.execution_fees}</dd></div>
          <div><dt>Net PnL</dt><dd><Value value={details.outcome.net_pnl} /></dd></div>
        </dl>
        {details.outcome.missing_reasons.length ? (
          <small>{details.outcome.missing_reasons.join(", ")}</small>
        ) : null}
      </section>

      <section className="diary-detail-section">
        <h3>Automatic factors</h3>
        <p className="diary-missing">—</p>
      </section>

      <section className="diary-detail-section">
        <h3>Notes / annotations</h3>
        <p className="diary-missing">—</p>
      </section>
    </div>
  );
}

function SetupList({ setups }: { setups: DiarySetup[] }) {
  return (
    <div className="diary-setups-list">
      {setups.map((setup) => (
        <article
          className={`diary-setup-row ${setup.direction.toLowerCase()}`}
          key={setup.setup_instance_id}
        >
          <div className="diary-trade-heading">
            <strong>{setup.symbol}</strong>
            <span className="diary-trade-side">{setup.direction}</span>
            <span>{setup.pattern}</span>
            <span>{setup.timeframe}</span>
            <span className={setup.needs_attention ? "attention" : ""}>{setup.status}</span>
          </div>

          <div className="diary-setup-metrics">
            <span>Создан {formatDate(setup.created_at_ms)}</span>
            <span>Entry {setup.entry_mode}</span>
            <span>Decision {setup.decision_state ?? "—"}</span>
            <span>Reason {setup.reason_code ?? "—"}</span>
          </div>

          <div className="diary-setup-metrics">
            <span>Setup {setup.setup_id}</span>
            <span>Strategy {setup.strategy_version}</span>
            <span>Controller {setup.controller ?? "—"}</span>
            <span>Trade {setup.trade_episode_ids.length ? setup.trade_episode_ids.join(", ") : "—"}</span>
          </div>

          {setup.missing_evidence.length ? (
            <small className="diary-attention-detail">
              Не хватает данных: {setup.missing_evidence.join(", ")}
            </small>
          ) : null}
        </article>
      ))}
    </div>
  );
}

export function DiaryOverlay({
  accountKey,
  onClose,
}: {
  accountKey: string;
  onClose: () => void;
}) {
  const [section, setSection] = useState<DiarySection>("TRADES");
  const [trades, setTrades] = useState<DiaryTrade[]>([]);
  const [setups, setSetups] = useState<DiarySetup[]>([]);
  const [tradeFilter, setTradeFilter] = useState<DiaryFilter>("ALL");
  const [setupFilter, setSetupFilter] = useState<SetupFilter>("ALL");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [accountId, setAccountId] = useState("");
  const [selectedTradeId, setSelectedTradeId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setLoadError(false);

    try {
      if (section === "TRADES") {
        const response = await fetch(marketApiRoutes.diaryTrades);
        if (!response.ok) throw new Error("diary request failed");

        const result = (await response.json()) as DiaryTradesResponse;
        if (!result.ok || !Array.isArray(result.trades)) {
          throw new Error("diary response is invalid");
        }

        setTrades(result.trades);
        setAccountId(result.active_account_id);
        setSelectedTradeId((current) =>
          current && result.trades.some((trade) => trade.trade_episode_id === current)
            ? current
            : null,
        );
      } else {
        const response = await fetch(marketApiRoutes.diarySetups);
        if (!response.ok) throw new Error("diary setups request failed");

        const result = (await response.json()) as DiarySetupsResponse;
        if (!result.ok || !Array.isArray(result.setups)) {
          throw new Error("diary setups response is invalid");
        }
        setSetups(result.setups);
      }
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [section]);

  useEffect(() => {
    setSelectedTradeId(null);
    void refresh();
  }, [accountKey, refresh]);

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

  const visibleTrades = useMemo(
    () => trades.filter((trade) => matchesTradeFilter(trade, tradeFilter)),
    [tradeFilter, trades],
  );
  const visibleSetups = useMemo(
    () => setups.filter((setup) => setupFilter === "ALL" || setup.needs_attention),
    [setupFilter, setups],
  );
  const selectedTrade = useMemo(
    () => trades.find((trade) => trade.trade_episode_id === selectedTradeId) ?? null,
    [selectedTradeId, trades],
  );

  return (
    <div className="diary-backdrop" role="presentation">
      <section className="diary-shell" role="dialog" aria-modal="true" aria-label="Торговый дневник">
        <header className="diary-header">
          <div>
            <p className="eyebrow">Trading Workspace</p>
            <h2>Дневник</h2>
            {accountId ? <small>{accountId}</small> : null}
          </div>
          <button aria-label="Закрыть дневник" onClick={onClose} type="button">×</button>
        </header>

        <nav className="diary-primary-nav" aria-label="Разделы дневника">
          <button
            aria-current={section === "TRADES" ? "page" : undefined}
            onClick={() => { setSection("TRADES"); setSelectedTradeId(null); }}
            type="button"
          >
            Trades
          </button>
          <button
            aria-current={section === "SETUPS" ? "page" : undefined}
            onClick={() => { setSection("SETUPS"); setSelectedTradeId(null); }}
            type="button"
          >
            Setups
          </button>
          <button aria-disabled="true" disabled title="D6.4" type="button">Statistics</button>
        </nav>

        {!selectedTrade ? (
          <div className="diary-filter-bar" aria-label={section === "TRADES" ? "Фильтры сделок" : "Фильтры сетапов"}>
            {(section === "TRADES" ? tradeFilters : setupFilters).map((candidate) => {
              const pressed = section === "TRADES"
                ? tradeFilter === candidate.id
                : setupFilter === candidate.id;
              return (
                <button
                  aria-pressed={pressed}
                  key={candidate.id}
                  onClick={() => {
                    if (section === "TRADES") setTradeFilter(candidate.id as DiaryFilter);
                    else setSetupFilter(candidate.id as SetupFilter);
                  }}
                  type="button"
                >
                  {candidate.label}
                </button>
              );
            })}
          </div>
        ) : <div className="diary-filter-placeholder" />}

        <div className="diary-content">
          {loading ? <p className="diary-state">Загрузка...</p> : null}

          {!loading && loadError ? (
            <div className="diary-state">
              <p>Не удалось загрузить дневник</p>
              <button onClick={() => void refresh()} type="button">Повторить</button>
            </div>
          ) : null}

          {!loading && !loadError && selectedTrade ? (
            <TradeDetailsView trade={selectedTrade} onBack={() => setSelectedTradeId(null)} />
          ) : null}

          {!loading && !loadError && !selectedTrade && section === "TRADES" && visibleTrades.length === 0 ? (
            <p className="diary-state">Нет сделок в этом фильтре</p>
          ) : null}

          {!loading && !loadError && !selectedTrade && section === "SETUPS" && visibleSetups.length === 0 ? (
            <p className="diary-state">Нет сетапов в этом фильтре</p>
          ) : null}

          {!loading && !loadError && !selectedTrade && section === "TRADES" && visibleTrades.length > 0 ? (
            <div className="diary-trades-list">
              {visibleTrades.map((trade) => (
                <button
                  className={`diary-trade-row ${trade.side.toLowerCase()}`}
                  key={trade.trade_episode_id}
                  onClick={() => setSelectedTradeId(trade.trade_episode_id)}
                  type="button"
                >
                  <div className="diary-trade-heading">
                    <strong>{trade.symbol}</strong>
                    <span className="diary-trade-side">{trade.side}</span>
                    <span>{trade.environment}</span>
                    <span className={trade.needs_attention ? "attention" : ""}>
                      {readinessLabel(trade)}
                    </span>
                  </div>

                  <div className="diary-trade-times">
                    <span>{formatDate(trade.opened_at_ms)}</span>
                    <span>→</span>
                    <span>{trade.closed_at_ms === null ? "Открыта" : formatDate(trade.closed_at_ms)}</span>
                    <span>{formatDuration(trade.holding_duration_ms)}</span>
                  </div>

                  <div className="diary-trade-metrics">
                    <span>Вход {trade.average_entry || "—"}</span>
                    <span>
                      {trade.closed_at_ms === null
                        ? `Открыто ${trade.open_quantity}`
                        : `Выход ${trade.exit_price ?? "—"}`}
                    </span>
                    <span
                      className={
                        trade.pnl !== null && Number(trade.pnl) > 0
                          ? "profit"
                          : trade.pnl !== null && Number(trade.pnl) < 0
                            ? "loss"
                            : ""
                      }
                    >
                      PnL {trade.pnl ?? "—"}
                    </span>
                  </div>

                  {trade.controller_origin ? <small>Источник: {trade.controller_origin}</small> : null}
                </button>
              ))}
            </div>
          ) : null}

          {!loading && !loadError && !selectedTrade && section === "SETUPS" && visibleSetups.length > 0 ? (
            <SetupList setups={visibleSetups} />
          ) : null}
        </div>
      </section>
    </div>
  );
}

import { useCallback, useEffect, useMemo, useState } from "react";
import { marketApiRoutes } from "../marketData/apiRoutes";
import "./DiaryOverlay.css";

type DiaryFilter = "ALL" | "OPEN" | "CLOSED" | "ATTENTION";

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
};

type DiaryTradesResponse = {
  ok: boolean;
  active_account_id: string;
  session_generation: number;
  environment: DiaryTrade["environment"];
  trades: DiaryTrade[];
};

const filters: ReadonlyArray<{ id: DiaryFilter; label: string }> = [
  { id: "ALL", label: "???" },
  { id: "OPEN", label: "????????" },
  { id: "CLOSED", label: "????????" },
  { id: "ATTENTION", label: "??????? ????????" },
];

function formatDate(value: number | null): string {
  if (value === null) return "?";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "?";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatDuration(value: number): string {
  if (!Number.isFinite(value) || value < 0) return "?";
  const minutes = Math.floor(value / 60_000);
  if (minutes < 60) return `${minutes}?`;

  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  if (hours < 24) {
    return remainder ? `${hours}? ${remainder}?` : `${hours}?`;
  }

  const days = Math.floor(hours / 24);
  return `${days}? ${hours % 24}?`;
}

function readinessLabel(trade: DiaryTrade): string {
  if (trade.readiness === "OPEN") return "OPEN";
  if (trade.readiness === "CLOSED_READY") return "READY";
  return "????? ??????";
}

function matchesFilter(
  trade: DiaryTrade,
  filter: DiaryFilter,
): boolean {
  if (filter === "OPEN") return trade.closed_at_ms === null;
  if (filter === "CLOSED") return trade.closed_at_ms !== null;
  if (filter === "ATTENTION") return trade.needs_attention;
  return true;
}

export function DiaryOverlay({
  accountKey,
  onClose,
}: {
  accountKey: string;
  onClose: () => void;
}) {
  const [trades, setTrades] = useState<DiaryTrade[]>([]);
  const [filter, setFilter] = useState<DiaryFilter>("ALL");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [accountId, setAccountId] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setLoadError(false);

    try {
      const response = await fetch(marketApiRoutes.diaryTrades);
      if (!response.ok) throw new Error("diary request failed");

      const result =
        (await response.json()) as DiaryTradesResponse;

      if (!result.ok || !Array.isArray(result.trades)) {
        throw new Error("diary response is invalid");
      }

      setTrades(result.trades);
      setAccountId(result.active_account_id);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [accountKey, refresh]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const visibleTrades = useMemo(
    () => trades.filter((trade) => matchesFilter(trade, filter)),
    [filter, trades],
  );

  return (
    <div className="diary-backdrop" role="presentation">
      <section
        className="diary-shell"
        role="dialog"
        aria-modal="true"
        aria-label="???????? ???????"
      >
        <header className="diary-header">
          <div>
            <p className="eyebrow">Trading Workspace</p>
            <h2>???????</h2>
            {accountId ? <small>{accountId}</small> : null}
          </div>

          <button
            aria-label="??????? ???????"
            onClick={onClose}
            type="button"
          >
            ?
          </button>
        </header>

        <nav
          className="diary-primary-nav"
          aria-label="??????? ????????"
        >
          <button aria-current="page" type="button">
            Trades
          </button>
          <button
            aria-disabled="true"
            disabled
            title="D6.3"
            type="button"
          >
            Setups
          </button>
          <button
            aria-disabled="true"
            disabled
            title="D6.4"
            type="button"
          >
            Statistics
          </button>
        </nav>

        <div
          className="diary-filter-bar"
          aria-label="??????? ??????"
        >
          {filters.map((candidate) => (
            <button
              aria-pressed={filter === candidate.id}
              key={candidate.id}
              onClick={() => setFilter(candidate.id)}
              type="button"
            >
              {candidate.label}
            </button>
          ))}
        </div>

        <div className="diary-content">
          {loading ? (
            <p className="diary-state">????????...</p>
          ) : null}

          {!loading && loadError ? (
            <div className="diary-state">
              <p>?? ??????? ???????? ??????</p>
              <button
                onClick={() => void refresh()}
                type="button"
              >
                ?????????
              </button>
            </div>
          ) : null}

          {!loading &&
          !loadError &&
          visibleTrades.length === 0 ? (
            <p className="diary-state">
              ??? ?????? ? ???? ???????
            </p>
          ) : null}

          {!loadError && visibleTrades.length > 0 ? (
            <div className="diary-trades-list">
              {visibleTrades.map((trade) => (
                <article
                  className={`diary-trade-row ${trade.side.toLowerCase()}`}
                  key={trade.trade_episode_id}
                >
                  <div className="diary-trade-heading">
                    <strong>{trade.symbol}</strong>
                    <span className="diary-trade-side">
                      {trade.side}
                    </span>
                    <span>{trade.environment}</span>
                    <span
                      className={
                        trade.needs_attention
                          ? "attention"
                          : ""
                      }
                    >
                      {readinessLabel(trade)}
                    </span>
                  </div>

                  <div className="diary-trade-times">
                    <span>{formatDate(trade.opened_at_ms)}</span>
                    <span>?</span>
                    <span>
                      {trade.closed_at_ms === null
                        ? "??????"
                        : formatDate(trade.closed_at_ms)}
                    </span>
                    <span>
                      {formatDuration(
                        trade.holding_duration_ms,
                      )}
                    </span>
                  </div>

                  <div className="diary-trade-metrics">
                    <span>
                      ???? {trade.average_entry || "?"}
                    </span>

                    <span>
                      {trade.closed_at_ms === null
                        ? `??????? ${trade.open_quantity}`
                        : `????? ${trade.exit_price ?? "?"}`}
                    </span>

                    <span
                      className={
                        trade.pnl !== null &&
                        Number(trade.pnl) > 0
                          ? "profit"
                          : trade.pnl !== null &&
                              Number(trade.pnl) < 0
                            ? "loss"
                            : ""
                      }
                    >
                      PnL {trade.pnl ?? "?"}
                    </span>
                  </div>

                  {trade.controller_origin ? (
                    <small>
                      ????????: {trade.controller_origin}
                    </small>
                  ) : null}
                </article>
              ))}
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}

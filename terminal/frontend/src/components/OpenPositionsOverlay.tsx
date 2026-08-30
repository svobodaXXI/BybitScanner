import { useCallback, useEffect, useRef, useState } from "react";
import type {
  CloseAllCommandRequest,
  CloseAllCommandResponse,
  CommandMutationResponse,
  FullCloseCommandRequest,
  PaperOpenPosition,
  PaperOpenPositionsResponse,
  PaperState,
} from "../contracts/trading";
import { marketApiRoutes } from "../marketData/apiRoutes";
import {
  formatPositionPnlPercent,
  formatPositionPrice,
  positionPnlPercent,
} from "../marketData/positionPnl";

type MutationRunner = <T>(key: string, operation: () => Promise<T>) => Promise<T>;

export function OpenPositionsOverlay({
  activeSymbol,
  onClose,
  onNavigate,
  runPaperMutation,
  applyPaperState,
}: {
  activeSymbol: string;
  onClose: () => void;
  onNavigate: (symbol: string) => void;
  runPaperMutation: MutationRunner;
  applyPaperState: (state: PaperState) => boolean;
}) {
  const [positions, setPositions] = useState<PaperOpenPosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [confirmPosition, setConfirmPosition] = useState<PaperOpenPosition | null>(null);
  const [navigatePosition, setNavigatePosition] = useState<PaperOpenPosition | null>(null);
  const [confirmAll, setConfirmAll] = useState(false);
  const [pendingSymbol, setPendingSymbol] = useState<string | null>(null);
  const [bulkPending, setBulkPending] = useState(false);
  const [statusBySymbol, setStatusBySymbol] = useState<Record<string, string>>({});
  const actionIds = useRef(new Map<string, string>());
  const ambiguousSymbols = useRef(new Set<string>());
  const bulkActionId = useRef<string | null>(null);
  const bulkTargetSymbols = useRef(new Set<string>());
  const activePositionIndex = positions.findIndex(
    (position) => position.symbol === activeSymbol,
  );
  const displayedPositions = activePositionIndex <= 0
    ? positions
    : [
        positions[activePositionIndex],
        ...positions.slice(0, activePositionIndex),
        ...positions.slice(activePositionIndex + 1),
      ];

  const refresh = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const response = await fetch(marketApiRoutes.openPositions);
      if (!response.ok) throw new Error("inventory request failed");
      const result = (await response.json()) as PaperOpenPositionsResponse;
      if (!result.ok || !Array.isArray(result.positions)) {
        throw new Error("inventory response is invalid");
      }
      setPositions(result.positions);
      const openSymbols = new Set(result.positions.map((item) => item.symbol));
      for (const symbol of [...ambiguousSymbols.current]) {
        if (!openSymbols.has(symbol)) ambiguousSymbols.current.delete(symbol);
      }
      for (const symbol of [...bulkTargetSymbols.current]) {
        if (!openSymbols.has(symbol)) bulkTargetSymbols.current.delete(symbol);
      }
      if (bulkTargetSymbols.current.size === 0) bulkActionId.current = null;
      const settledSymbols = [...actionIds.current.keys()].filter(
        (symbol) => !result.positions.some((item) => item.symbol === symbol),
      );
      if (settledSymbols.length > 0) {
        for (const symbol of settledSymbols) {
          ambiguousSymbols.current.delete(symbol);
          actionIds.current.delete(symbol);
        }
        setStatusBySymbol((current) => {
          const next = { ...current };
          for (const symbol of settledSymbols) delete next[symbol];
          return next;
        });
      }
      return result.positions;
    } catch {
      setLoadError(true);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const closePosition = async (position: PaperOpenPosition) => {
    const symbol = position.symbol;
    if (ambiguousSymbols.current.has(symbol)) return;
    const actionId = actionIds.current.get(symbol)
      ?? `paper-inventory-full-close-${symbol.toLowerCase()}-${Date.now()}`;
    actionIds.current.set(symbol, actionId);
    setConfirmPosition(null);
    setPendingSymbol(symbol);
    setStatusBySymbol((current) => ({ ...current, [symbol]: "Закрытие..." }));

    await runPaperMutation(`FULL_CLOSE:${symbol}`, async () => {
      try {
        const request: FullCloseCommandRequest = {
          client_action_id: actionId,
          symbol,
        };
        const response = await fetch("/api/full-close", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(request),
        });
        if (!response.ok) throw new Error("full close request failed");
        const result = (await response.json()) as CommandMutationResponse;
        if (result.status === "completed") {
          applyPaperState(result.paper_state);
          const latest = await refresh();
          setStatusBySymbol((current) => {
            const next = { ...current };
            if (latest?.some((item) => item.symbol === symbol)) {
              ambiguousSymbols.current.add(symbol);
              next[symbol] = "Позиция ещё открыта";
            } else if (latest) {
              ambiguousSymbols.current.delete(symbol);
              actionIds.current.delete(symbol);
              delete next[symbol];
            } else {
              ambiguousSymbols.current.add(symbol);
              next[symbol] = "Закрытие не подтверждено — повтор заблокирован";
            }
            return next;
          });
          return;
        }
        const definitiveFailure = ["blocked", "rejected", "validation_error"]
          .includes(result.status);
        if (!definitiveFailure || result.reconciliation_required) {
          ambiguousSymbols.current.add(symbol);
          const latest = await refresh();
          if (latest && !latest.some((item) => item.symbol === symbol)) {
            ambiguousSymbols.current.delete(symbol);
            actionIds.current.delete(symbol);
            setStatusBySymbol((current) => {
              const next = { ...current };
              delete next[symbol];
              return next;
            });
          } else {
            setStatusBySymbol((current) => ({
              ...current,
              [symbol]: "Результат неизвестен — повтор заблокирован",
            }));
          }
        } else {
          actionIds.current.delete(symbol);
          setStatusBySymbol((current) => ({
            ...current,
            [symbol]: "Закрытие не выполнено",
          }));
          await refresh();
        }
      } catch {
        ambiguousSymbols.current.add(symbol);
        const latest = await refresh();
        if (latest && !latest.some((item) => item.symbol === symbol)) {
          ambiguousSymbols.current.delete(symbol);
          actionIds.current.delete(symbol);
          setStatusBySymbol((current) => {
            const next = { ...current };
            delete next[symbol];
            return next;
          });
        } else {
          setStatusBySymbol((current) => ({
            ...current,
            [symbol]: "Связь прервана — повтор заблокирован",
          }));
        }
      } finally {
        setPendingSymbol((current) => current === symbol ? null : current);
      }
    });
  };

  const closeAll = async () => {
    if (positions.length === 0 || bulkPending || ambiguousSymbols.current.size > 0) return;
    const targets = positions.map((position) => position.symbol);
    const actionId = bulkActionId.current ?? `paper-close-all-${Date.now()}`;
    bulkActionId.current = actionId;
    bulkTargetSymbols.current = new Set(targets);
    setConfirmAll(false);
    setBulkPending(true);
    for (const symbol of targets) ambiguousSymbols.current.add(symbol);
    setStatusBySymbol((current) => ({
      ...current,
      ...Object.fromEntries(targets.map((symbol) => [symbol, "Закрытие..."])),
    }));

    await runPaperMutation("CLOSE_ALL", async () => {
      try {
        const request: CloseAllCommandRequest = { client_action_id: actionId };
        const response = await fetch("/api/close-all", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(request),
        });
        if (!response.ok) throw new Error("close all request failed");
        const result = (await response.json()) as CloseAllCommandResponse;
        if (!result.ok || !Array.isArray(result.positions) || !Array.isArray(result.results)) {
          throw new Error("close all response is invalid");
        }
        setPositions(result.positions);
        const stillOpen = new Set(result.positions.map((position) => position.symbol));
        const resultByAction = new Map(result.results.map((item) => [item.client_action_id, item]));
        setStatusBySymbol((current) => {
          const next = { ...current };
          for (const symbol of targets) {
            if (!stillOpen.has(symbol)) {
              ambiguousSymbols.current.delete(symbol);
              bulkTargetSymbols.current.delete(symbol);
              delete next[symbol];
            } else {
              const unresolved = [...resultByAction.values()].some(
                (item) => item.status === "unknown" || item.reconciliation_required,
              );
              next[symbol] = unresolved
                ? "Результат неизвестен — повтор заблокирован"
                : "Позиция ещё открыта";
            }
          }
          return next;
        });
        if (bulkTargetSymbols.current.size === 0) bulkActionId.current = null;
      } catch {
        const latest = await refresh();
        if (latest) {
          const stillOpen = new Set(latest.map((position) => position.symbol));
          for (const symbol of targets) {
            if (!stillOpen.has(symbol)) {
              ambiguousSymbols.current.delete(symbol);
              bulkTargetSymbols.current.delete(symbol);
            }
          }
          if (bulkTargetSymbols.current.size === 0) bulkActionId.current = null;
        }
        setStatusBySymbol((current) => ({
          ...current,
          ...Object.fromEntries(targets
            .filter((symbol) => ambiguousSymbols.current.has(symbol))
            .map((symbol) => [symbol, "Закрытие не подтверждено — повтор заблокирован"])),
        }));
      } finally {
        setBulkPending(false);
      }
    });
  };

  const formatPnl = (position: PaperOpenPosition) => {
    const value = position.unrealized_pnl;
    if (value === null || !Number.isFinite(Number(value))) return "PnL —";
    const numeric = Number(value);
    const percent = positionPnlPercent(
      position.position_side,
      position.average_entry === null ? null : Number(position.average_entry),
      position.current_price === null ? null : Number(position.current_price),
    );
    const percentage = percent === null ? "" : ` (${formatPositionPnlPercent(percent)})`;
    return `PnL ${numeric > 0 ? "+" : numeric < 0 ? "−" : ""}${Math.abs(numeric).toFixed(2)} USDT${percentage}`;
  };

  return (
    <div className="paper-open-positions-backdrop" role="presentation">
      <section className="paper-open-positions" aria-label="Открытые позиции">
        <header>
          <div className="paper-open-positions-title">
            <h2>Открытые позиции</h2>
            <button
              className="paper-open-positions-close-all"
              disabled={positions.length === 0 || bulkPending || pendingSymbol !== null || ambiguousSymbols.current.size > 0}
              onClick={() => setConfirmAll(true)}
              type="button"
            >Закрыть все</button>
          </div>
          <div className="paper-open-positions-actions">
            <button
              aria-label="Закрыть список позиций"
              disabled={pendingSymbol !== null || bulkPending || ambiguousSymbols.current.size > 0}
              onClick={onClose}
              type="button"
            >×</button>
          </div>
        </header>

        {loading ? <p className="paper-open-positions-state">Загрузка...</p> : null}
        {!loading && loadError && positions.length === 0 ? (
          <div className="paper-open-positions-state">
            <p>Не удалось получить позиции</p>
            <button onClick={() => void refresh()} type="button">Повторить</button>
          </div>
        ) : null}
        {!loading && !loadError && positions.length === 0 ? (
          <p className="paper-open-positions-state">Нет открытых позиций</p>
        ) : null}

        {positions.length > 0 ? (
          <div className="paper-open-positions-list">
            {displayedPositions.map((position) => {
              const sideClass = position.position_side === "Long" ? "long" : "short";
              const activeSymbolClass = position.symbol === activeSymbol
                ? " active-symbol"
                : "";
              const disabled = bulkPending || pendingSymbol === position.symbol
                || ambiguousSymbols.current.has(position.symbol);
              return (
                <article
                  className={`paper-open-position-row ${sideClass}${activeSymbolClass}`}
                  key={position.symbol}
                  aria-label={`Открыть позицию ${position.symbol} в терминале`}
                  onClick={() => setNavigatePosition(position)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setNavigatePosition(position);
                    }
                  }}
                  role="button"
                  tabIndex={0}
                >
                  <div className="paper-open-position-heading">
                    <strong>{position.symbol}</strong>
                    <span>{position.position_side.toUpperCase()}</span>
                  </div>
                  <button
                    aria-label={`Закрыть позицию ${position.symbol}`}
                    className="paper-open-position-close"
                    disabled={disabled}
                    onClick={(event) => {
                      event.stopPropagation();
                      setConfirmPosition(position);
                    }}
                    type="button"
                  >×</button>
                  <div className="paper-open-position-metrics">
                    <span>Объем: {Number(position.engaged_notional_usdt).toFixed(2)} USDT</span>
                    <span>⚔ {Number(position.engaged_wv).toFixed(1)}</span>
                    <span className={Number(position.unrealized_pnl) > 0 ? "profit" : Number(position.unrealized_pnl) < 0 ? "loss" : ""}>
                      {formatPnl(position)}
                    </span>
                  </div>
                  <span className="paper-open-position-average">
                    Ср. цена: {position.average_entry === null
                      ? "—"
                      : formatPositionPrice(position.average_entry, position.tick_size)}
                  </span>
                  {statusBySymbol[position.symbol] ? (
                    <small>{statusBySymbol[position.symbol]}</small>
                  ) : null}
                </article>
              );
            })}
          </div>
        ) : null}

        {confirmPosition ? (
          <div className="paper-open-position-confirm" role="presentation">
            <section role="dialog" aria-modal="true" aria-label={`Закрыть всю позицию ${confirmPosition.symbol} по рынку?`}>
              <strong>Закрыть всю позицию {confirmPosition.symbol} по рынку?</strong>
              <div>
                <button onClick={() => void closePosition(confirmPosition)} type="button">Закрыть</button>
                <button onClick={() => setConfirmPosition(null)} type="button">Отмена</button>
              </div>
            </section>
          </div>
        ) : null}
        {navigatePosition ? (
          <div className="paper-open-position-confirm" role="presentation">
            <section role="dialog" aria-modal="true" aria-label={`Перейти в терминал ${navigatePosition.symbol}?`}>
              <strong>Перейти в терминал {navigatePosition.symbol}?</strong>
              <div>
                <button onClick={() => onNavigate(navigatePosition.symbol)} type="button">Перейти</button>
                <button onClick={() => setNavigatePosition(null)} type="button">Отмена</button>
              </div>
            </section>
          </div>
        ) : null}
        {confirmAll ? (
          <div className="paper-open-position-confirm" role="presentation">
            <section role="dialog" aria-modal="true" aria-label="Закрыть все открытые позиции по рынку?">
              <strong>Закрыть все открытые PAPER позиции по рынку?</strong>
              <div>
                <button className="danger" onClick={() => void closeAll()} type="button">Закрыть все позиции</button>
                <button onClick={() => setConfirmAll(false)} type="button">Отмена</button>
              </div>
            </section>
          </div>
        ) : null}
      </section>
    </div>
  );
}

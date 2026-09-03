import { useMemo } from "react";
import { createPortal } from "react-dom";
import type { AccountWorkspaceProjection } from "../accountWorkspace/accountWorkspaceStore";
import { formatPositionPnlPercent, positionPnlPercentFromEntryNotional } from "../marketData/positionPnl";
import { baseAssetFromSymbol } from "../marketData/symbol";

const text = (value: unknown) => typeof value === "string" && value ? value : "—";
const side = (value: unknown) => {
  const normalized = text(value).toUpperCase();
  return normalized === "LONG" || normalized === "SHORT" ? normalized : "—";
};
const pnlTone = (value: unknown) => {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0
    ? "profit" : Number.isFinite(numeric) && numeric < 0 ? "loss" : "";
};

const formatUsdt = (value: unknown) => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  if (numeric !== 0 && Math.abs(numeric) < 0.01) {
    return numeric.toFixed(6).replace(/(\.\d*?[1-9])0+$|\.0+$/, "$1");
  }
  return numeric.toFixed(2);
};

const formatPrice = (value: unknown) => {
  const raw = text(value);
  const numeric = Number(raw);
  return Number.isFinite(numeric) ? raw : "—";
};

const positionValue = (position: Record<string, unknown>) => {
  const value = Math.abs(Number(position.size) * Number(position.mark_price));
  return Number.isFinite(value) ? value : 0;
};

const authoritativeEngagedWv = (value: unknown) => {
  if (typeof value !== "string" && typeof value !== "number") return null;
  if (typeof value === "string" && !value.trim()) return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
};

export function LiveAccountInventory({
  projection, activeAccountName, activeSymbol, onClose, onNavigate,
}: {
  projection: AccountWorkspaceProjection | null;
  activeAccountName: string;
  activeSymbol: string;
  onClose: () => void;
  onNavigate: (symbol: string) => void;
}) {
  const positions = useMemo(() => {
    if (!projection) return [];
    return projection.positions
      .map((position, originalIndex) => ({ position, originalIndex }))
      .sort((left, right) => {
        const leftActive = text(left.position.symbol) === activeSymbol;
        const rightActive = text(right.position.symbol) === activeSymbol;
        if (leftActive !== rightActive) return leftActive ? -1 : 1;
        const valueDifference = positionValue(right.position) - positionValue(left.position);
        return valueDifference || left.originalIndex - right.originalIndex;
      });
  }, [activeSymbol, projection]);
  const activePositionPinned = positions.length > 1 && text(positions[0]?.position.symbol) === activeSymbol;
  const totalPositionValue = positions.reduce((total, item) => total + positionValue(item.position), 0);
  const engagedValues = positions
    .map(({ position }) => authoritativeEngagedWv(position.engaged_wv))
    .filter((value): value is number => value !== null);
  const totalEngagedWv = positions.length === 0
    ? 0
    : engagedValues.length > 0
      ? engagedValues.reduce((total, value) => total + value, 0) : null;
  return createPortal(
    <div className="live-positions-surface" data-testid="live-positions-surface" role="presentation">
      <section aria-label="Открытые позиции" role="dialog">
        <header>
          <button aria-label="Назад к графику" onClick={onClose} type="button">‹</button>
          <div><h2>Открытые позиции</h2><span>{activeAccountName || projection?.account_id || "Активный счёт"}</span></div>
        </header>
        {projection ? <div className="live-positions-summary" aria-label="Сводка активного счёта">
          <span>Wallet<strong>{formatUsdt(projection.wallet_balance_usdt)}</strong></span>
          <span>Equity<strong>{formatUsdt(projection.total_equity_usdt)}</strong></span>
          <span>⚔ {totalEngagedWv === null ? "—" : totalEngagedWv.toFixed(1)}<strong>{formatUsdt(totalPositionValue)} USDT</strong></span>
        </div> : null}
        <div className="live-positions-scroll">
          {!projection ? <p role="status">Позиции временно недоступны</p>
            : positions.length === 0 ? <p role="status">Нет открытых позиций</p>
              : positions.map(({ position, originalIndex }, index) => {
                const symbol = text(position.symbol);
                const normalizedSide = side(position.side);
                const percent = positionPnlPercentFromEntryNotional(
                  Number(position.unrealized_pnl), Number(position.size), Number(position.average_entry),
                );
                const value = positionValue(position);
                const navigate = () => symbol !== "—" && onNavigate(symbol);
                return <article
                  className={`live-position-row ${normalizedSide.toLowerCase()} ${symbol === activeSymbol ? "active-symbol" : ""} ${index === 0 && activePositionPinned ? "active-separated" : ""}`}
                  key={`${projection.account_id}:${projection.session_generation}:${symbol}:${originalIndex}`}
                >
                  <button aria-label={`Открыть ${symbol} в Trading Workspace`}
                    className="live-position-select" onClick={navigate} type="button" />
                  <span className="live-position-primary"><strong>{symbol}</strong><b>{normalizedSide}</b></span>
                  <span className={`live-position-pnl ${pnlTone(position.unrealized_pnl)}`}>
                    <strong>{formatUsdt(position.unrealized_pnl)} USDT</strong>
                    <small>{percent === null ? "—" : formatPositionPnlPercent(percent)}</small>
                  </span>
                  <span className="live-position-details">
                    Объём {text(position.size)} {baseAssetFromSymbol(symbol)}
                    {positionValue(position) > 0 ? ` · ${formatUsdt(value)} USDT` : ""}
                  </span>
                  <span className="live-position-mark">
                    <span>Цена {formatPrice(position.average_entry)}</span>
                    {text(position.mark_price) !== "—" ? <span>Mark {formatPrice(position.mark_price)}</span> : null}
                  </span>
                </article>;
              })}
        </div>
      </section>
    </div>, document.body,
  );
}

import type { CSSProperties } from "react";
import type { NormalizedOrderBook, TradePrint } from "../contracts/marketData";
import {
  DOM_ROW_HEIGHT_REM,
  DOM_VISIBLE_ROWS,
  type DomViewportGeometry,
  displaySweptRows,
  executionPriceToLadderRow,
} from "../marketData/domProjection";
import {
  formatPositionPnlPercent,
  positionPnlPercent,
} from "../marketData/positionPnl";

export { formatPositionPnlPercent, positionPnlPercent } from "../marketData/positionPnl";

export const printWidthPx = (notionalUsdt: number) =>
  Math.min(22.8, Math.max(10.8, 10.8 + 1.95 * Math.log1p(notionalUsdt / 100)));

const formatNotional = (notional: number) => {
  if (notional >= 1000) {
    const thousands = notional / 1000;
    return `${thousands >= 10 ? thousands.toFixed(0) : thousands.toFixed(1)}k`;
  }
  return Math.round(notional).toString();
};

export function TapePanel({
  book: _book,
  centerPrice,
  trades,
  positionSide,
  averageEntryPrice,
  currentPrice,
  compression,
  viewportGeometry = {
    visibleRows: DOM_VISIBLE_ROWS,
    rowHeightPx: DOM_ROW_HEIGHT_REM * 16,
    viewportHeightPx: DOM_ROW_HEIGHT_REM * 16 * DOM_VISIBLE_ROWS,
  },
}: {
  book: NormalizedOrderBook;
  centerPrice: number | null;
  trades: readonly TradePrint[];
  positionSide: "Long" | "Short" | "Flat";
  averageEntryPrice?: number | null;
  currentPrice?: number | null;
  compression: number;
  viewportGeometry?: DomViewportGeometry;
}) {
  const { rowHeightPx, visibleRows, viewportHeightPx } = viewportGeometry;
  const pnlPercent = positionPnlPercent(
    positionSide,
    averageEntryPrice,
    currentPrice,
  );
  const pnlTone = pnlPercent === null || pnlPercent === 0
    ? "neutral"
    : pnlPercent > 0 ? "positive" : "negative";

  return (
    <section
      className="tape-panel prints-panel workspace-panel"
      aria-label="Live trade prints"
    >
      <div className="panel-header prints-header-spacer" aria-hidden="true" />
      <div className="prints-field">
        {positionSide !== "Flat" ? (
          <div
            className={`prints-position-indicator ${positionSide.toLowerCase()}`}
            aria-label={`Open ${positionSide} position`}
          >
            <span className="position-arrow">
              {positionSide === "Long" ? "\u2191" : "\u2193"}
            </span>
            {pnlPercent !== null ? (
              <span className={`position-pnl ${pnlTone}`}>
                {formatPositionPnlPercent(pnlPercent)}
              </span>
            ) : null}
          </div>
        ) : null}
        <div
          className="prints-stream"
          style={{ "--dom-viewport-height": `${viewportHeightPx}px` } as CSSProperties}
        >
          {trades.map((trade) => {
            const width = printWidthPx(trade.totalNotionalUsdt);
            const height =
              displaySweptRows(trade.sweptTicks, compression) * rowHeightPx;
            const rowOffset =
              executionPriceToLadderRow(
                trade.lastExecutionPrice,
                trade.side,
                trade.tickSize,
                centerPrice,
                compression,
                visibleRows,
              ) ?? 0;

            return (
              <div
                className={`trade-print-bubble ${trade.side.toLowerCase()}`}
                key={trade.id}
                style={
                  {
                    "--print-width": `${width}px`,
                    "--print-height": `${height}px`,
                    "--print-y": `${rowOffset * rowHeightPx}px`,
                  } as CSSProperties
                }
                title={`${trade.tradeCount} trades · ${trade.sweptTicks} ticks`}
              >
                <span>{formatNotional(trade.totalNotionalUsdt)}</span>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

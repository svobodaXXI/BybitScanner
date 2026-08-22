import type { Candle } from "../contracts/marketData";
export function ChartPanel({
  candles,
  onZoom,
  zoom,
}: {
  candles: readonly Candle[];
  onZoom: (zoom: number) => void;
  zoom: number;
}) {
  const prices = candles.flatMap((candle) => [candle.high, candle.low]);
  const high = Math.max(...prices);
  const low = Math.min(...prices);
  const range = high - low || 1;
  const y = (price: number) => 250 - ((price - low) / range) * 210;
  const candleWidth = Math.max(3, 12 * zoom);
  return (
    <section
      className="chart-panel workspace-panel"
      aria-label="Candlestick chart"
    >
      <header className="panel-header">
        <div>
          <span>Chart · 5m</span>
          <small>Graphite prototype</small>
        </div>
        <div className="zoom-controls">
          <button
            aria-label="Zoom out"
            onClick={() => onZoom(Math.max(0.75, zoom - 0.25))}
            type="button"
          >
            −
          </button>
          <output aria-label="Chart zoom">{zoom.toFixed(2)}×</output>
          <button
            aria-label="Zoom in"
            onClick={() => onZoom(Math.min(1.75, zoom + 0.25))}
            type="button"
          >
            +
          </button>
        </div>
      </header>
      <svg
        aria-label="Development candlestick series"
        className="chart-canvas"
        role="img"
        viewBox="0 0 720 280"
      >
        <title>Deterministic development candlestick chart</title>
        <g className="chart-grid-lines">
          {[50, 100, 150, 200, 250].map((line) => (
            <line key={line} x1="0" x2="720" y1={line} y2={line} />
          ))}
        </g>
        {candles.map((candle, index) => {
          const x = 26 + index * 28;
          const bullish = candle.close >= candle.open;
          const top = y(Math.max(candle.open, candle.close));
          const bodyHeight = Math.max(
            2,
            Math.abs(y(candle.open) - y(candle.close)),
          );
          return (
            <g
              className={bullish ? "candle bullish" : "candle bearish"}
              key={candle.time}
            >
              <line x1={x} x2={x} y1={y(candle.high)} y2={y(candle.low)} />
              <rect
                height={bodyHeight}
                width={candleWidth}
                x={x - candleWidth / 2}
                y={top}
              />
            </g>
          );
        })}
      </svg>
    </section>
  );
}

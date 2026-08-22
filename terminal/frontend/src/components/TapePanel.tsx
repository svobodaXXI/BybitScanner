import type { TradePrint } from "../contracts/marketData";
export function TapePanel({ trades }: { trades: readonly TradePrint[] }) {
  return (
    <section
      className="tape-panel workspace-panel"
      aria-label="Tape time and sales"
    >
      <header className="panel-header">
        <span>Tape</span>
        <small>Time &amp; Sales</small>
      </header>
      <div className="tape-list">
        {trades.map((trade) => (
          <div
            className={`tape-row ${trade.side.toLowerCase()}`}
            key={trade.id}
          >
            <time>{trade.time}</time>
            <span>{trade.price.toFixed(1)}</span>
            <strong>{trade.quantity.toFixed(3)}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

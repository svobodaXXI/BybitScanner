import type { AccountWorkspaceProjection } from "../accountWorkspace/accountWorkspaceStore";

const text = (value: unknown) => typeof value === "string" ? value : "—";

export function LiveAccountInventory({
  projection, onNavigate,
}: {
  projection: AccountWorkspaceProjection;
  onNavigate: (symbol: string) => void;
}) {
  if (projection.provider !== "BYBIT") return null;
  return (
    <section className="live-account-inventory" aria-label="LIVE account positions and orders">
      <header>
        <strong>LIVE · {projection.status}</strong>
        <span>Equity {projection.total_equity_usdt} · Wallet {projection.wallet_balance_usdt} USDT</span>
      </header>
      <div>
        <section aria-label="LIVE positions">
          <strong>Positions ({projection.positions.length})</strong>
          {projection.positions.map((position, index) => {
            const symbol = text(position.symbol);
            return <button key={`${symbol}:${index}`} onClick={() => onNavigate(symbol)} type="button">
              {symbol} · {text(position.side)} · {text(position.size)}
            </button>;
          })}
        </section>
        <section aria-label="LIVE active orders">
          <strong>Active orders ({projection.orders.length})</strong>
          {projection.orders.map((order, index) => {
            const symbol = text(order.symbol);
            return <button key={`${text(order.order_id)}:${index}`} onClick={() => onNavigate(symbol)} type="button">
              {symbol} · {text(order.side)} · {text(order.quantity)} @ {text(order.price)}
            </button>;
          })}
        </section>
      </div>
    </section>
  );
}

import { type CSSProperties, useMemo, useRef, useState } from "react";
import type { NormalizedOrderBook, OwnOrder } from "../contracts/marketData";

export function DomPanel({
  book,
  ownOrders,
}: {
  book: NormalizedOrderBook;
  ownOrders: readonly OwnOrder[];
}) {
  const [offset, setOffset] = useState(0);
  const [locked, setLocked] = useState(false);
  const [visibleOrders, setVisibleOrders] = useState(ownOrders);
  const dragY = useRef<number | null>(null);
  const levels = useMemo(
    () => [...book.asks.slice(0, 8).reverse(), ...book.bids.slice(0, 8)],
    [book],
  );
  const manualMove = (delta: number) => {
    setOffset((current) => Math.max(-6, Math.min(6, current + delta)));
    setLocked(false);
  };
  const center = () => setOffset(0);
  return (
    <section className="dom-panel workspace-panel" aria-label="DOM order book">
      <header className="panel-header dom-header">
        <div>
          <span>DOM</span>
          <small>Depth 50 contract · showing 16</small>
        </div>
        <button
          aria-pressed={locked}
          className={locked ? "center-button locked" : "center-button"}
          onClick={center}
          onDoubleClick={() => {
            center();
            setLocked((current) => !current);
          }}
          type="button"
        >
          CENTER
        </button>
      </header>
      <div
        className="dom-ladder"
        data-offset={offset}
        onPointerDown={(event) => {
          dragY.current = event.clientY;
        }}
        onPointerMove={(event) => {
          if (
            dragY.current === null ||
            Math.abs(event.clientY - dragY.current) < 12
          )
            return;
          manualMove(event.clientY > dragY.current ? -1 : 1);
          dragY.current = event.clientY;
        }}
        onPointerUp={() => {
          dragY.current = null;
        }}
        onWheel={(event) => {
          event.preventDefault();
          manualMove(event.deltaY > 0 ? 1 : -1);
        }}
      >
        <div className="dom-columns">
          <span>Own USDT</span>
          <span>Price</span>
          <span>Size</span>
        </div>
        {levels.map((level, index) => {
          const side = index < 8 ? "SELL" : "BUY";
          const orders = visibleOrders.filter(
            (order) => order.price === level.price && order.side === side,
          );
          const aggregate = orders.reduce(
            (sum, order) => sum + order.notionalUsdt,
            0,
          );
          const depth = `${Math.min(100, level.quantity * 7)}%`;
          return (
            <div
              className={`dom-row ${side.toLowerCase()}`}
              key={`${side}-${level.price}`}
            >
              <span className="own-orders">
                {aggregate > 0 ? <strong>{aggregate} USDT</strong> : null}
                <span className="order-dots">
                  {orders.map((order) => (
                    <button
                      aria-label={`Cancel fixture order ${order.id}`}
                      className="order-dot"
                      key={order.id}
                      onClick={(event) => {
                        event.stopPropagation();
                        setVisibleOrders((current) =>
                          current.filter((item) => item.id !== order.id),
                        );
                      }}
                      title={`${order.notionalUsdt} USDT development fixture`}
                      type="button"
                    />
                  ))}
                </span>
              </span>
              <span className="dom-price">
                {(level.price + offset * 0.5).toFixed(1)}
              </span>
              <span
                className="dom-size"
                style={{ "--depth": depth } as CSSProperties}
              >
                {level.quantity.toFixed(3)}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

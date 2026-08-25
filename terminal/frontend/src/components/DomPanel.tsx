import { type CSSProperties, useMemo, useRef, useState } from "react";
import type { NormalizedOrderBook, OwnOrder } from "../contracts/marketData";
import {
  projectDomBook,
  projectPriceToDisplayBucket,
  recommendedLadderCenter,
} from "../marketData/domProjection";

const formatPrice = (price: number) =>
  price.toLocaleString("en-US", {
    maximumFractionDigits: 8,
    useGrouping: false,
  });

export function DomPanel({
  book,
  centerPrice,
  onCenterPriceChange,
  ownOrders,
}: {
  book: NormalizedOrderBook;
  centerPrice: number | null;
  onCenterPriceChange: (price: number | null) => void;
  ownOrders: readonly OwnOrder[];
}) {
  const [offset, setOffset] = useState(0);
  const [locked, setLocked] = useState(false);
  const [visibleOrders, setVisibleOrders] = useState(ownOrders);
  const dragY = useRef<number | null>(null);
  const projection = useMemo(
    () => projectDomBook(book, centerPrice),
    [book, centerPrice],
  );
  const levels = projection.levels;
  const maxVisibleQuantity = useMemo(
    () => Math.max(0, ...levels.map((level) => level.quantity)),
    [levels],
  );
  const manualMove = (delta: number) => {
    setOffset((current) => Math.max(-6, Math.min(6, current + delta)));
    if (projection.centerPrice !== null && projection.displayStep > 0) {
      onCenterPriceChange(
        projection.centerPrice + delta * projection.displayStep,
      );
    }
    setLocked(false);
  };
  const center = () => {
    setOffset(0);
    onCenterPriceChange(recommendedLadderCenter(book));
  };
  return (
    <section className="dom-panel workspace-panel" aria-label="DOM order book">
      <header className="panel-header dom-header">
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
        {book.health !== "READY" || levels.length === 0 ? (
          <div className="dom-unavailable" role="status">
            LIVE BOOK UNAVAILABLE
          </div>
        ) : null}
        {levels.map((level) => {
          const orders = visibleOrders.filter(
            (order) =>
              projectPriceToDisplayBucket(
                order.price,
                order.side,
                projection.nativeTickSize,
              ) === level.price,
          );
          const side = level.side ?? orders[0]?.side ?? null;
          const aggregate = orders.reduce(
            (sum, order) => sum + order.notionalUsdt,
            0,
          );
          const depth = `${
            maxVisibleQuantity > 0
              ? Math.min(100, (level.quantity / maxVisibleQuantity) * 100)
              : 0
          }%`;
          return (
            <div
              className={`dom-row${side ? ` ${side.toLowerCase()}` : " empty"}${level.isBest ? " best" : ""}`}
              key={level.price}
            >
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
              <span
                className="dom-body"
                style={{ "--depth": depth } as CSSProperties}
              >
                {aggregate > 0 ? (
                  <strong className="own-order-total">{aggregate}</strong>
                ) : (
                  <span />
                )}
                <span className="dom-size">
                  {level.quantity > 0 ? level.quantity.toFixed(3) : ""}
                </span>
              </span>
              <span className="dom-price">{formatPrice(level.price)}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

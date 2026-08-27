import { type CSSProperties, useEffect, useMemo, useRef, useState } from "react";
import type { NormalizedOrderBook, OwnOrder } from "../contracts/marketData";
import {
  dragDeltaToCenterStep,
  projectDomBook,
  projectPriceToDisplayBucket,
  recommendedLadderCenter,
} from "../marketData/domProjection";
import { formatDomSize } from "./domSizeFormat";

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
  compression,
  onCompressionChange,
  fastLimitActive = false,
  onFastLimitPriceSelect,
}: {
  book: NormalizedOrderBook;
  centerPrice: number | null;
  onCenterPriceChange: (price: number | null) => void;
  ownOrders: readonly OwnOrder[];
  compression: number;
  onCompressionChange: (compression: number) => void;
  fastLimitActive?: boolean;
  onFastLimitPriceSelect?: (price: string) => void;
}) {
  const [offset, setOffset] = useState(0);
  const [locked, setLocked] = useState(false);
  const [visibleOrders, setVisibleOrders] = useState(ownOrders);
  const [compressionEditing, setCompressionEditing] = useState(false);
  const [compressionDraft, setCompressionDraft] = useState(String(compression));
  const dragY = useRef<number | null>(null);
  const centerPriceRef = useRef(centerPrice);
  centerPriceRef.current = centerPrice;
  const projection = useMemo(
    () => projectDomBook(book, centerPrice, compression),
    [book, centerPrice, compression],
  );
  const levels = projection.levels;
  const maxVisibleQuantity = useMemo(
    () => Math.max(0, ...levels.map((level) => level.quantity)),
    [levels],
  );
  const manualMove = (delta: number) => {
    setOffset((current) => Math.max(-6, Math.min(6, current + delta)));
    if (centerPriceRef.current !== null && projection.displayStep > 0) {
      const nextCenterPrice =
        centerPriceRef.current + delta * projection.displayStep;
      centerPriceRef.current = nextCenterPrice;
      onCenterPriceChange(nextCenterPrice);
    }
    setLocked(false);
  };
  const center = () => {
    setOffset(0);
    const nextCenterPrice = recommendedLadderCenter(book, compression);
    centerPriceRef.current = nextCenterPrice;
    onCenterPriceChange(nextCenterPrice);
  };

  useEffect(() => {
    if (!locked) return;

    setOffset(0);
    const nextCenterPrice = recommendedLadderCenter(book, compression);
    centerPriceRef.current = nextCenterPrice;
    onCenterPriceChange(nextCenterPrice);
  }, [book, compression, locked, onCenterPriceChange]);


  return (
    <section className="dom-panel workspace-panel" aria-label="DOM order book">
      <div className="dom-compression-control">
        {compressionEditing ? (
          <input
            autoFocus
            aria-label="DOM compression"
            className="dom-compression-input"
            inputMode="numeric"
            value={compressionDraft}
            onFocus={(event) => event.currentTarget.select()}
            onChange={(event) => setCompressionDraft(event.target.value)}
            onBlur={() => {
              const next = Number.parseInt(compressionDraft, 10);
              if (Number.isFinite(next) && next >= 1 && next <= 100) {
                onCompressionChange(next);
              } else {
                setCompressionDraft(String(compression));
              }
              setCompressionEditing(false);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.currentTarget.blur();
              }
              if (event.key === "Escape") {
                setCompressionDraft(String(compression));
                setCompressionEditing(false);
              }
            }}
          />
        ) : (
          <button
            aria-label="DOM compression"
            className="dom-compression-button"
            type="button"
            onClick={() => {
              setCompressionDraft(String(compression));
              setCompressionEditing(true);
            }}
          >
            x{compression}
          </button>
        )}
      </div>
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
          manualMove(dragDeltaToCenterStep(event.clientY - dragY.current));
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
                compression,
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
                  {level.quantity > 0 ? formatDomSize(level.quantity) : ""}
                </span>
              </span>
              <span
  className={locked ? "dom-price center-locked" : "dom-price"}
  onClick={(event) => {
    event.stopPropagation();
    if (fastLimitActive && onFastLimitPriceSelect) {
      onFastLimitPriceSelect(formatPrice(level.price));
      return;
    }
    center();
  }}
  onDoubleClick={(event) => {
    event.stopPropagation();
    center();
    setLocked(true);
  }}
>
  {formatPrice(level.price)}
</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

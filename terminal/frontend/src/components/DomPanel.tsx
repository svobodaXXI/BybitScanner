import { type CSSProperties, useEffect, useMemo, useRef, useState } from "react";
import type { NormalizedOrderBook, OwnOrder } from "../contracts/marketData";
import {
  DOM_ROW_HEIGHT_REM,
  DOM_VISIBLE_ROWS,
  domViewportGeometry,
  type DomViewportGeometry,
  dragDeltaToCenterStep,
  projectDomBook,
  projectPriceToDisplayBucket,
  recommendedLadderCenter,
} from "../marketData/domProjection";
import { formatDomSize } from "./domSizeFormat";
import { TradingControlButton } from "../interactions/useTradingControlActivation";

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
  onOwnOrderCancel = () => {},
  onViewportGeometryChange,
}: {
  book: NormalizedOrderBook;
  centerPrice: number | null;
  onCenterPriceChange: (price: number | null) => void;
  ownOrders: readonly OwnOrder[];
  compression: number;
  onCompressionChange: (compression: number) => void;
  fastLimitActive?: boolean;
  onFastLimitPriceSelect?: (price: string) => void;
  onOwnOrderCancel?: (orderId: string) => void;
  onViewportGeometryChange?: (geometry: DomViewportGeometry) => void;
}) {
  const [viewportGeometry, setViewportGeometry] = useState<DomViewportGeometry>({
    visibleRows: DOM_VISIBLE_ROWS,
    rowHeightPx: DOM_ROW_HEIGHT_REM * 16,
    viewportHeightPx: DOM_ROW_HEIGHT_REM * 16 * DOM_VISIBLE_ROWS,
  });
  const [offset, setOffset] = useState(0);
  const [locked, setLocked] = useState(false);
  const [compressionEditing, setCompressionEditing] = useState(false);
  const [compressionDraft, setCompressionDraft] = useState(String(compression));
  const dragY = useRef<number | null>(null);
  const fastLimitBodyPointer = useRef<{
    pointerId: number;
    price: string;
    startY: number;
    moved: boolean;
    pointerType: string;
  } | null>(null);
  const suppressFastLimitBodyClick = useRef(false);
  const centerPriceRef = useRef(centerPrice);
  const ladderViewportRef = useRef<HTMLDivElement | null>(null);
  centerPriceRef.current = centerPrice;
  const projection = useMemo(
    () => projectDomBook(book, centerPrice, compression, viewportGeometry.visibleRows),
    [book, centerPrice, compression, viewportGeometry.visibleRows],
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
    const ladderViewport = ladderViewportRef.current;
    if (!ladderViewport || typeof ResizeObserver === "undefined") return;
    const update = (height: number) => {
      const rootFontSize = Number.parseFloat(getComputedStyle(document.documentElement).fontSize);
      const nextGeometry = domViewportGeometry(height, DOM_ROW_HEIGHT_REM * rootFontSize);
      setViewportGeometry(nextGeometry);
      onViewportGeometryChange?.(nextGeometry);
    };
    const observer = new ResizeObserver(([entry]) => update(entry.contentRect.height));
    observer.observe(ladderViewport);
    const viewportStyle = getComputedStyle(ladderViewport);
    const paddingTop = Number.parseFloat(viewportStyle.paddingTop) || 0;
    const paddingBottom = Number.parseFloat(viewportStyle.paddingBottom) || 0;
    update(
      ladderViewport.clientHeight -
        paddingTop -
        paddingBottom,
    );
    return () => observer.disconnect();
  }, [onViewportGeometryChange]);

  useEffect(() => {
    if (!locked) return;

    setOffset(0);
    const nextCenterPrice = recommendedLadderCenter(book, compression);
    centerPriceRef.current = nextCenterPrice;
    onCenterPriceChange(nextCenterPrice);
  }, [book, compression, locked, onCenterPriceChange]);

  return (
    <section className="dom-panel workspace-panel" aria-label="DOM order book">
      <div
        className="dom-ladder-viewport"
        ref={ladderViewportRef}
        style={{ "--dom-row-height": `${viewportGeometry.rowHeightPx}px` } as CSSProperties}
      >
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
          const levelPrice = formatPrice(level.price);
          const activateLevel = () => {
            if (fastLimitActive && onFastLimitPriceSelect) {
              onFastLimitPriceSelect(levelPrice);
              return;
            }
            center();
          };
          const orders = ownOrders.filter(
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
                    aria-label={`Cancel Limit ${order.id}`}
                    className={`order-dot ${order.side.toLowerCase()}`}
                    key={order.id}
                    onClick={(event) => {
                      event.stopPropagation();
                      onOwnOrderCancel(order.id);
                    }}
                    title={`${order.notionalUsdt} USDT`}
                    type="button"
                  />
                ))}
              </span>
              <span
                className="dom-body"
                style={{ "--depth": depth } as CSSProperties}
                onPointerDown={(event) => {
                  if (!fastLimitActive || event.button !== 0) return;
                  fastLimitBodyPointer.current = {
                    pointerId: event.pointerId,
                    price: levelPrice,
                    startY: event.clientY,
                    moved: false,
                    pointerType: event.pointerType,
                  };
                }}
                onPointerMove={(event) => {
                  const pointer = fastLimitBodyPointer.current;
                  if (
                    pointer?.pointerId === event.pointerId &&
                    Math.abs(event.clientY - pointer.startY) >= 12
                  ) {
                    pointer.moved = true;
                  }
                }}
                onPointerUp={(event) => {
                  const pointer = fastLimitBodyPointer.current;
                  if (pointer?.pointerId !== event.pointerId) return;
                  if (pointer.pointerType !== "mouse") {
                    suppressFastLimitBodyClick.current = true;
                    fastLimitBodyPointer.current = null;
                    if (!pointer.moved && onFastLimitPriceSelect) {
                      onFastLimitPriceSelect(pointer.price);
                    }
                  }
                }}
                onPointerCancel={() => {
                  fastLimitBodyPointer.current = null;
                }}
                onClick={() => {
                  if (suppressFastLimitBodyClick.current) {
                    suppressFastLimitBodyClick.current = false;
                    return;
                  }
                  const pointer = fastLimitBodyPointer.current;
                  fastLimitBodyPointer.current = null;
                  if (
                    fastLimitActive &&
                    pointer &&
                    !pointer.moved &&
                    onFastLimitPriceSelect
                  ) {
                    onFastLimitPriceSelect(pointer.price);
                  }
                }}
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
              <TradingControlButton
  className={locked ? "dom-price center-locked" : "dom-price"}
  type="button"
  onTap={activateLevel}
  onDoubleClick={(event) => {
    event.stopPropagation();
    if (!fastLimitActive) {
      center();
      setLocked(true);
    }
  }}
>
  {levelPrice}
</TradingControlButton>
            </div>
          );
        })}
        </div>
        </div>
    </section>
  );
}

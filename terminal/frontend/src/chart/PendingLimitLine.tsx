import type { MarketSide } from "../contracts/trading";

export function PendingLimitLine({
  side,
  price,
  top,
  rightOffset = 0,
  onDragClientY,
  onSelect,
  onDismiss,
  onConfirm,
  selected = false,
  confirmDisabled = false,
}: {
  side: MarketSide;
  price: string;
  top: number | null;
  rightOffset?: number;
  onDragClientY: (clientY: number) => void;
  onSelect?: () => void;
  onDismiss?: () => void;
  onConfirm?: () => void;
  selected?: boolean;
  confirmDisabled?: boolean;
}) {
  if (top === null) return null;

  return (
    <div
      className={`pending-limit-line ${side.toLowerCase()}${selected ? " selected" : ""}`}
      data-pending-limit-line
      aria-label={`Pending ${side} Limit at ${price}`}
      role="slider"
      aria-valuenow={Number(price)}
      style={{
        top,
        right: rightOffset,
        "--pending-limit-price-scale-width": `${rightOffset}px`,
      } as React.CSSProperties}
      onPointerDown={(event) => {
        onSelect?.();
        event.currentTarget.setPointerCapture(event.pointerId);
        event.stopPropagation();
      }}
      onPointerMove={(event) => {
        if (event.currentTarget.hasPointerCapture(event.pointerId)) {
          onDragClientY(event.clientY);
          event.preventDefault();
          event.stopPropagation();
        }
      }}
      onPointerUp={(event) => {
        if (event.currentTarget.hasPointerCapture(event.pointerId)) {
          event.currentTarget.releasePointerCapture(event.pointerId);
        }
        event.stopPropagation();
      }}
    >
      <span>{price}</span>
      <button
        type="button"
        className="pending-limit-confirm"
        aria-label={`Confirm pending ${side} Limit`}
        disabled={confirmDisabled || !onConfirm}
        onPointerDown={(event) => event.stopPropagation()}
        onClick={(event) => {
          event.stopPropagation();
          onConfirm?.();
        }}
      >
        ✓
      </button>
      <button
        type="button"
        className="pending-limit-dismiss"
        aria-label={`Dismiss pending ${side} Limit`}
        onPointerDown={(event) => event.stopPropagation()}
        onClick={(event) => {
          event.stopPropagation();
          onDismiss?.();
        }}
      >
        &times;
      </button>
    </div>
  );
}

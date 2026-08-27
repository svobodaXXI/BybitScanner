import type { MarketSide } from "../contracts/trading";

export function PendingLimitLine({
  side,
  price,
  top,
  onDragClientY,
  onConfirm,
  confirmDisabled = false,
}: {
  side: MarketSide;
  price: string;
  top: number | null;
  onDragClientY: (clientY: number) => void;
  onConfirm?: () => void;
  confirmDisabled?: boolean;
}) {
  if (top === null) return null;

  return (
    <div
      className={`pending-limit-line ${side.toLowerCase()}`}
      data-pending-limit-line
      aria-label={`Pending ${side} Limit at ${price}`}
      role="slider"
      aria-valuenow={Number(price)}
      style={{ top }}
      onPointerDown={(event) => {
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
    </div>
  );
}

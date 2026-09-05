import type { MarketSide } from "../contracts/trading";
import { useTradingControlActivation } from "../interactions/useTradingControlActivation";

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
  liveSubmitStatus,
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
  liveSubmitStatus?: "submitting" | "ambiguous";
}) {
  const submitLabel = liveSubmitStatus === "submitting"
    ? "SUBMITTING…"
    : liveSubmitStatus === "ambiguous" ? "RECONCILING — DO NOT RETRY" : null;
  const confirmActivation = useTradingControlActivation({
    onTap: onConfirm,
    disabled: !!submitLabel || confirmDisabled || !onConfirm,
  });
  const dismissActivation = useTradingControlActivation({ onTap: onDismiss });

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
      {submitLabel && (
        <output role="status" aria-live="polite" style={{
          position: "absolute", right: "4rem", bottom: "1rem",
          whiteSpace: "nowrap", background: "#11181f", padding: "0.2rem",
          fontSize: "0.7rem", fontWeight: 700, pointerEvents: "none",
        }}>{submitLabel}</output>
      )}
      <button
        type="button"
        className="pending-limit-confirm"
        aria-label={`Confirm pending ${side} Limit`}
        disabled={!!submitLabel || confirmDisabled || !onConfirm}
        {...confirmActivation}
      >
        ✓
      </button>
      <button
        type="button"
        className="pending-limit-dismiss"
        aria-label={`Dismiss pending ${side} Limit`}
        {...dismissActivation}
      >
        &times;
      </button>
    </div>
  );
}

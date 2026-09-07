import { useEffect, useRef, useState } from "react";
import { TradingControlButton } from "../interactions/useTradingControlActivation";

export function StopLine({
  leg = "STOP",
  price,
  top,
  rightOffset,
  mode,
  submitting = false,
  onDragClientY,
  onConfirm,
  onCancel,
  onEdit,
  onDelete,
}: {
  leg?: "STOP" | "TAKE";
  price: string;
  top: number | null;
  rightOffset: number;
  mode: "ACTIVE" | "CREATE" | "EDIT";
  submitting?: boolean;
  onDragClientY?: (clientY: number) => void;
  onConfirm?: () => void;
  onCancel?: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [activeSelected, setActiveSelected] = useState(false);
  const draft = mode !== "ACTIVE";

  useEffect(() => {
    if (draft || !activeSelected) return;
    const dismiss = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Node && rootRef.current?.contains(target)) return;
      setActiveSelected(false);
    };
    document.addEventListener("pointerdown", dismiss, true);
    return () => document.removeEventListener("pointerdown", dismiss, true);
  }, [activeSelected, draft]);

  if (top === null) return null;
  const targetsStopAction = (target: EventTarget | null) =>
    target instanceof Element && target.closest(".stop-line-actions") !== null;
  return (
    <div
      ref={rootRef}
      aria-label={`${mode === "ACTIVE" ? "Active" : "Pending"} ${leg} at ${price}`}
      className={`stop-line ${leg.toLowerCase()} ${draft ? "draft" : "active"}${!draft && activeSelected ? " selected" : ""}`}
      data-protection-line
      data-protection-leg={leg}
      data-protection-mode={mode}
      data-stop-line={leg === "STOP" ? "" : undefined}
      role={draft ? "slider" : undefined}
      aria-valuenow={draft ? Number(price) : undefined}
      style={{ top, right: rightOffset }}
      onPointerDown={(event) => {
        if (!draft) {
          if (!submitting && !targetsStopAction(event.target)) setActiveSelected(true);
          event.stopPropagation();
          return;
        }
        if (submitting || targetsStopAction(event.target)) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        event.stopPropagation();
      }}
      onPointerMove={(event) => {
        if (targetsStopAction(event.target)) return;
        if (draft && event.currentTarget.hasPointerCapture(event.pointerId)) {
          onDragClientY?.(event.clientY);
          event.preventDefault();
          event.stopPropagation();
        }
      }}
      onPointerUp={(event) => {
        if (targetsStopAction(event.target)) return;
        if (event.currentTarget.hasPointerCapture(event.pointerId)) {
          event.currentTarget.releasePointerCapture(event.pointerId);
        }
        event.stopPropagation();
      }}
    >
      <span>{price}</span>
      {draft || activeSelected ? (
        <div className="stop-line-actions">
          {draft ? (
            <>
              <TradingControlButton
                aria-label={`Confirm ${leg}`}
                className="stop-line-confirm"
                disabled={submitting}
                onTap={() => {
                  setActiveSelected(true);
                  onConfirm?.();
                }}
              >✓</TradingControlButton>
              <TradingControlButton
                aria-label={`Cancel ${leg} draft`}
                className="stop-line-cancel"
                disabled={submitting}
                onTap={onCancel}
              >×</TradingControlButton>
            </>
          ) : (
            <>
              <TradingControlButton
                aria-label={`Edit ${leg}`}
                className="stop-line-edit"
                onTap={onEdit}
              >✎</TradingControlButton>
              <TradingControlButton
                aria-label={`Delete ${leg}`}
                className="stop-line-delete"
                onTap={onDelete}
              >×</TradingControlButton>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}

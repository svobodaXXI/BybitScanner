import {
  type ButtonHTMLAttributes,
  createElement,
  type MouseEvent,
  type PointerEvent,
  useRef,
} from "react";

type ActivationOptions = {
  onTap?: () => void;
  onHoldStart?: () => void;
  onHoldEnd?: () => void;
  onCancel?: () => void;
  holdMs?: number;
  disabled?: boolean;
};

export function useTradingControlActivation({
  onTap,
  onHoldStart,
  onHoldEnd,
  onCancel,
  holdMs = 500,
  disabled = false,
}: ActivationOptions) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activePointer = useRef<number | null>(null);
  const held = useRef(false);
  const suppressCompatibilityClick = useRef(false);

  const clearTimer = () => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
  };

  const cancel = () => {
    const wasActive = activePointer.current !== null;
    clearTimer();
    activePointer.current = null;
    if (held.current) onHoldEnd?.();
    held.current = false;
    if (wasActive) onCancel?.();
  };

  return {
    onPointerDown: (event: PointerEvent<HTMLButtonElement>) => {
      if (disabled || activePointer.current !== null || event.button !== 0)
        return;
      if (event.pointerType === "mouse")
        suppressCompatibilityClick.current = false;
      activePointer.current = event.pointerId;
      event.stopPropagation();
      held.current = false;
      event.currentTarget.setPointerCapture?.(event.pointerId);
      if (onHoldStart) {
        timer.current = setTimeout(() => {
          if (activePointer.current !== event.pointerId) return;
          held.current = true;
          timer.current = null;
          onHoldStart();
        }, holdMs);
      }
    },
    onPointerUp: (event: PointerEvent<HTMLButtonElement>) => {
      if (activePointer.current !== event.pointerId) return;
      event.stopPropagation();
      clearTimer();
      activePointer.current = null;
      if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
        event.currentTarget.releasePointerCapture?.(event.pointerId);
      }
      if (held.current) {
        held.current = false;
        onHoldEnd?.();
        suppressCompatibilityClick.current = true;
      } else if (event.pointerType !== "mouse") {
        suppressCompatibilityClick.current = true;
        onTap?.();
      }
    },
    onPointerCancel: cancel,
    onClick: (event: MouseEvent<HTMLButtonElement>) => {
      event.stopPropagation();
      if (disabled) return;
      if (suppressCompatibilityClick.current) {
        suppressCompatibilityClick.current = false;
        return;
      }
      onTap?.();
    },
    onContextMenu: (event: MouseEvent<HTMLButtonElement>) =>
      event.preventDefault(),
  };
}

export function TradingControlButton({
  onTap,
  onHoldStart,
  onHoldEnd,
  onCancel,
  holdMs,
  disabled,
  ...buttonProps
}: ButtonHTMLAttributes<HTMLButtonElement> & ActivationOptions) {
  const activation = useTradingControlActivation({
    onTap,
    onHoldStart,
    onHoldEnd,
    onCancel,
    holdMs,
    disabled,
  });
  return createElement("button", {
    type: "button",
    ...buttonProps,
    ...activation,
    disabled,
  });
}

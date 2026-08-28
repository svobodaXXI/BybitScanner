import {
  useRef,
  type FocusEvent,
  type KeyboardEvent,
  type PointerEvent,
} from "react";

export function useTradingNumericInputFocusPolicy() {
  const boundaryRef = useRef<HTMLDivElement>(null);
  const completionActive = useRef(false);

  const finishEditing = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    event.stopPropagation();
    completionActive.current = true;
    boundaryRef.current?.focus({ preventScroll: true });
  };

  const rejectImplicitInputFocus = (event: FocusEvent<HTMLDivElement>) => {
    if (
      completionActive.current &&
      event.target instanceof Element &&
      event.target.matches("[data-trading-numeric-input]")
    ) boundaryRef.current?.focus({ preventScroll: true });
  };

  const beginExplicitInteraction = (event: PointerEvent<HTMLDivElement>) => {
    if (
      event.target instanceof Element &&
      event.target.closest("[data-trading-numeric-input]")
    ) completionActive.current = false;
  };

  return {
    boundaryProps: {
      ref: boundaryRef,
      tabIndex: -1,
      onFocusCapture: rejectImplicitInputFocus,
      onPointerDownCapture: beginExplicitInteraction,
    },
    inputProps: {
      "data-trading-numeric-input": true,
      enterKeyHint: "done" as const,
      onKeyDown: finishEditing,
    },
  };
}

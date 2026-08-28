import type { MouseEvent, PointerEvent } from "react";

export function dismissPopupFromBackdrop(
  event: PointerEvent<HTMLElement>,
  dismiss: () => void,
) {
  if (event.target === event.currentTarget) dismiss();
}

export function shieldPopupPointerInteraction(event: PointerEvent<HTMLElement>) {
  event.stopPropagation();
}

export function shieldPopupClickInteraction(event: MouseEvent<HTMLElement>) {
  event.stopPropagation();
}

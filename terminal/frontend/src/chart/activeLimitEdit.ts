import { useEffect, useRef, useState, type PointerEvent } from "react";
import type { MarketSide } from "../contracts/trading";

export const ACTIVE_LIMIT_EDIT_HOLD_MS = 300;

export type ActiveLimitEditState =
  | { mode: "ACTIVE" }
  | { mode: "PRESSING" | "EDITING"; orderId: string; side: MarketSide; originalPrice: string; candidatePrice: string; pointerId: number }
  | { mode: "PENDING_CONFIRM" | "AMENDING"; orderId: string; side: MarketSide; originalPrice: string; candidatePrice: string };

export function useActiveLimitEdit({ priceAtClientY, normalizePrice, amend }: {
  priceAtClientY: (clientY: number) => string | null;
  normalizePrice: (price: string, side: MarketSide) => string | null;
  amend: (orderId: string, price: string) => Promise<void>;
}) {
  const [state, setState] = useState<ActiveLimitEditState>({ mode: "ACTIVE" });
  const stateRef = useRef(state);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const confirmInFlightRef = useRef(false);
  stateRef.current = state;
  const clearTimer = () => { if (timerRef.current !== null) clearTimeout(timerRef.current); timerRef.current = null; };
  const cancel = () => { clearTimer(); setState({ mode: "ACTIVE" }); };

  useEffect(() => () => clearTimer(), []);
  useEffect(() => {
    if (state.mode !== "PENDING_CONFIRM") return;
    const dismissOutside = (event: globalThis.PointerEvent) => {
      const target = event.target;
      if (target instanceof Element && target.closest(`[data-active-limit-edit="${state.orderId}"]`)) return;
      cancel();
    };
    document.addEventListener("pointerdown", dismissOutside);
    return () => document.removeEventListener("pointerdown", dismissOutside);
  }, [state]);

  const pointerDown = (event: PointerEvent<HTMLDivElement>, order: { order_id: string; side: MarketSide; price: string }) => {
    if (event.button !== 0 || stateRef.current.mode !== "ACTIVE") return;
    event.stopPropagation();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    const pressing: ActiveLimitEditState = { mode: "PRESSING", orderId: order.order_id, side: order.side, originalPrice: order.price, candidatePrice: order.price, pointerId: event.pointerId };
    setState(pressing);
    clearTimer();
    timerRef.current = setTimeout(() => {
      const current = stateRef.current;
      if (current.mode === "PRESSING" && current.orderId === order.order_id && current.pointerId === event.pointerId) setState({ ...current, mode: "EDITING" });
      timerRef.current = null;
    }, ACTIVE_LIMIT_EDIT_HOLD_MS);
  };
  const pointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const current = stateRef.current;
    if (current.mode !== "EDITING" || current.pointerId !== event.pointerId) return;
    event.stopPropagation(); event.preventDefault();
    const raw = priceAtClientY(event.clientY);
    const candidatePrice = raw === null ? null : normalizePrice(raw, current.side);
    if (candidatePrice !== null) setState({ ...current, candidatePrice });
  };
  const pointerUp = (event: PointerEvent<HTMLDivElement>) => {
    const current = stateRef.current;
    if ((current.mode !== "PRESSING" && current.mode !== "EDITING") || current.pointerId !== event.pointerId) return;
    event.stopPropagation(); clearTimer();
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) event.currentTarget.releasePointerCapture?.(event.pointerId);
    setState(current.mode === "EDITING" ? { mode: "PENDING_CONFIRM", orderId: current.orderId, side: current.side, originalPrice: current.originalPrice, candidatePrice: current.candidatePrice } : { mode: "ACTIVE" });
  };
  const pointerCancel = (event: PointerEvent<HTMLDivElement>) => {
    const current = stateRef.current;
    if ((current.mode === "PRESSING" || current.mode === "EDITING") && current.pointerId === event.pointerId) { event.stopPropagation(); cancel(); }
  };
  const confirm = async () => {
    const current = stateRef.current;
    if (current.mode !== "PENDING_CONFIRM" || confirmInFlightRef.current) return;
    confirmInFlightRef.current = true;
    setState({ ...current, mode: "AMENDING" });
    try { await amend(current.orderId, current.candidatePrice); } finally {
      confirmInFlightRef.current = false;
      setState({ mode: "ACTIVE" });
    }
  };
  return { state, pointerDown, pointerMove, pointerUp, pointerCancel, cancel, confirm };
}

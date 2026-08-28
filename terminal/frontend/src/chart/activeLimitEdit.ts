import { useEffect, useRef, useState, type PointerEvent } from "react";
import type { MarketSide } from "../contracts/trading";
import { CROSSHAIR_MOVE_TOLERANCE_PX } from "./crosshairInteraction";

export const ACTIVE_LIMIT_EDIT_HOLD_MS = 300;
export const ACTIVE_LIMIT_GLOBAL_CANDIDATE_BOUNDARY = "[data-active-limit-global-actions]";
export type EditedActiveLimitCandidate = { orderId: string; candidatePrice: string };

export async function confirmVisibleLimitCandidates({ draftIds, activeCandidate, confirmDraft, confirmEditedActive }: {
  draftIds: readonly string[];
  activeCandidate: EditedActiveLimitCandidate | null;
  confirmDraft: (draftId: string) => void | Promise<void>;
  confirmEditedActive: (candidate: EditedActiveLimitCandidate) => void | Promise<void>;
}) {
  for (const draftId of draftIds) await confirmDraft(draftId);
  if (activeCandidate) await confirmEditedActive(activeCandidate);
}

export async function cancelVisibleLimitCandidates({ draftIds, activeCandidate, dismissDrafts, cancelEditedActive }: {
  draftIds: readonly string[];
  activeCandidate: EditedActiveLimitCandidate | null;
  dismissDrafts: () => void;
  cancelEditedActive: (candidate: EditedActiveLimitCandidate) => void | Promise<void>;
}) {
  if (draftIds.length > 0) dismissDrafts();
  if (activeCandidate) await cancelEditedActive(activeCandidate);
}

export type ActiveLimitEditState =
  | { mode: "ACTIVE" }
  | { mode: "ACTIVE_CANCEL"; orderId: string; side: MarketSide; originalPrice: string; candidatePrice: string }
  | { mode: "PRESSING"; orderId: string; side: MarketSide; originalPrice: string; candidatePrice: string; pointerId: number; startX: number; startY: number; aborted: boolean }
  | { mode: "EDITING"; orderId: string; side: MarketSide; originalPrice: string; candidatePrice: string; pointerId: number; resumed: boolean }
  | { mode: "PENDING_CONFIRM" | "AMENDING"; orderId: string; side: MarketSide; originalPrice: string; candidatePrice: string }
  | { mode: "CANCELLING"; orderId: string; side: MarketSide; originalPrice: string; candidatePrice: string; presentation: "ACTIVE" | "EDIT" };

export function useActiveLimitEdit({ priceAtClientY, normalizePrice, amend, cancelOrder }: {
  priceAtClientY: (clientY: number) => string | null;
  normalizePrice: (price: string, side: MarketSide) => string | null;
  amend: (orderId: string, price: string) => Promise<void>;
  cancelOrder: (orderId: string) => Promise<unknown>;
}) {
  const [state, setState] = useState<ActiveLimitEditState>({ mode: "ACTIVE" });
  const stateRef = useRef(state);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const confirmInFlightRef = useRef(false);
  stateRef.current = state;
  const transition = (next: ActiveLimitEditState) => {
    stateRef.current = next;
    setState(next);
  };
  const clearTimer = () => { if (timerRef.current !== null) clearTimeout(timerRef.current); timerRef.current = null; };
  const dismiss = () => { clearTimer(); transition({ mode: "ACTIVE" }); };

  useEffect(() => () => clearTimer(), []);
  useEffect(() => {
    if (state.mode !== "EDITING" && state.mode !== "PENDING_CONFIRM" && state.mode !== "ACTIVE_CANCEL") return;
    const dismissOutside = (event: globalThis.PointerEvent) => {
      const target = event.target;
      if (target instanceof Element && target.closest(`[data-active-limit-edit="${state.orderId}"]`)) return;
      if (state.mode !== "ACTIVE_CANCEL" && target instanceof Element && target.closest(ACTIVE_LIMIT_GLOBAL_CANDIDATE_BOUNDARY)) return;
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      dismiss();
    };
    document.addEventListener("pointerdown", dismissOutside, true);
    return () => document.removeEventListener("pointerdown", dismissOutside, true);
  }, [state]);

  const pointerDown = (event: PointerEvent<HTMLDivElement>, order: { order_id: string; side: MarketSide; price: string }) => {
    if (event.button !== 0) return;
    const current = stateRef.current;
    if (current.mode === "PENDING_CONFIRM" && current.orderId === order.order_id) {
      event.stopPropagation(); event.preventDefault();
      event.currentTarget.setPointerCapture?.(event.pointerId);
      transition({ ...current, mode: "EDITING", pointerId: event.pointerId, resumed: true });
      return;
    }
    if (current.mode !== "ACTIVE" && !(current.mode === "ACTIVE_CANCEL" && current.orderId === order.order_id)) return;
    event.stopPropagation();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    const pressing: ActiveLimitEditState = { mode: "PRESSING", orderId: order.order_id, side: order.side, originalPrice: order.price, candidatePrice: order.price, pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, aborted: false };
    transition(pressing);
    clearTimer();
    timerRef.current = setTimeout(() => {
      const current = stateRef.current;
      if (current.mode === "PRESSING" && !current.aborted && current.orderId === order.order_id && current.pointerId === event.pointerId) transition({ mode: "EDITING", orderId: current.orderId, side: current.side, originalPrice: current.originalPrice, candidatePrice: current.candidatePrice, pointerId: current.pointerId, resumed: false });
      timerRef.current = null;
    }, ACTIVE_LIMIT_EDIT_HOLD_MS);
  };
  const pointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const current = stateRef.current;
    if (current.mode === "PRESSING" && current.pointerId === event.pointerId) {
      event.stopPropagation(); event.preventDefault();
      if (!current.aborted && Math.hypot(event.clientX - current.startX, event.clientY - current.startY) > CROSSHAIR_MOVE_TOLERANCE_PX) {
        clearTimer();
        transition({ ...current, aborted: true });
      }
      return;
    }
    if (current.mode !== "EDITING" || current.pointerId !== event.pointerId) return;
    event.stopPropagation(); event.preventDefault();
    const raw = priceAtClientY(event.clientY);
    const candidatePrice = raw === null ? null : normalizePrice(raw, current.side);
    if (candidatePrice !== null) transition({ ...current, candidatePrice });
  };
  const pointerUp = (event: PointerEvent<HTMLDivElement>) => {
    const current = stateRef.current;
    if ((current.mode !== "PRESSING" && current.mode !== "EDITING") || current.pointerId !== event.pointerId) return;
    event.stopPropagation(); clearTimer();
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) event.currentTarget.releasePointerCapture?.(event.pointerId);
    transition(current.mode === "EDITING"
      ? { mode: "PENDING_CONFIRM", orderId: current.orderId, side: current.side, originalPrice: current.originalPrice, candidatePrice: current.candidatePrice }
      : current.aborted
        ? { mode: "ACTIVE" }
        : { mode: "ACTIVE_CANCEL", orderId: current.orderId, side: current.side, originalPrice: current.originalPrice, candidatePrice: current.candidatePrice });
  };
  const pointerCancel = (event: PointerEvent<HTMLDivElement>) => {
    const current = stateRef.current;
    if ((current.mode !== "PRESSING" && current.mode !== "EDITING") || current.pointerId !== event.pointerId) return;
    event.stopPropagation();
    if (current.mode === "EDITING" && current.resumed) {
      transition({ mode: "PENDING_CONFIRM", orderId: current.orderId, side: current.side, originalPrice: current.originalPrice, candidatePrice: current.candidatePrice });
    } else {
      dismiss();
    }
  };
  const confirm = async () => {
    const current = stateRef.current;
    if (current.mode !== "PENDING_CONFIRM" || confirmInFlightRef.current) return;
    confirmInFlightRef.current = true;
    transition({ ...current, mode: "AMENDING" });
    try { await amend(current.orderId, current.candidatePrice); } finally {
      confirmInFlightRef.current = false;
      transition({ mode: "ACTIVE" });
    }
  };
  const cancel = async () => {
    const current = stateRef.current;
    if ((current.mode !== "PENDING_CONFIRM" && current.mode !== "ACTIVE_CANCEL") || confirmInFlightRef.current) return;
    confirmInFlightRef.current = true;
    transition({ ...current, mode: "CANCELLING", presentation: current.mode === "PENDING_CONFIRM" ? "EDIT" : "ACTIVE" });
    try { await cancelOrder(current.orderId); } finally {
      confirmInFlightRef.current = false;
      transition({ mode: "ACTIVE" });
    }
  };
  const activeCandidate = state.mode === "PENDING_CONFIRM"
    ? { orderId: state.orderId, candidatePrice: state.candidatePrice }
    : null;
  return { state, activeCandidate, pointerDown, pointerMove, pointerUp, pointerCancel, dismiss, cancel, confirm };
}

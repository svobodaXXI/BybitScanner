import type { PaperState } from "../contracts/trading";
import { normalizeLimitDraftPrice } from "./limitDraft";

export type StopDraft = {
  symbol: string;
  mode: "CREATE" | "EDIT";
  price: string;
  originalPrice: string | null;
  status: "editing" | "submitting";
  proposalSignalId?: string;
};

export type StopDraftAction =
  | { type: "begin-create"; symbol: string; price: string; proposalSignalId?: string }
  | { type: "begin-edit"; symbol: string; authoritativePrice: string }
  | { type: "update-price"; price: string }
  | { type: "submitting" }
  | { type: "restore-editing" }
  | { type: "clear" };

export function stopDraftReducer(
  state: StopDraft | null,
  action: StopDraftAction,
): StopDraft | null {
  if (action.type === "begin-create") {
    return {
      symbol: action.symbol,
      mode: "CREATE",
      price: action.price,
      originalPrice: null,
      status: "editing",
      proposalSignalId: action.proposalSignalId,
    };
  }
  if (action.type === "begin-edit") {
    return {
      symbol: action.symbol,
      mode: "EDIT",
      price: action.authoritativePrice,
      originalPrice: action.authoritativePrice,
      status: "editing",
    };
  }
  if (action.type === "clear") return null;
  if (state === null) return state;
  if (action.type === "update-price") return { ...state, price: action.price };
  if (action.type === "submitting") return { ...state, status: "submitting" };
  if (action.type === "restore-editing") return { ...state, status: "editing" };
  return state;
}

export function initialStopCandidate(
  side: PaperState["position_side"],
  averageEntry: string | null,
  tickSize: string | null,
): string | null {
  const average = Number(averageEntry);
  if (
    (side !== "Long" && side !== "Short") ||
    !Number.isFinite(average) ||
    average <= 0
  ) return null;
  const requested = average * (side === "Long" ? 0.98 : 1.02);
  const closingSide = side === "Long" ? "Sell" : "Buy";
  return normalizeLimitDraftPrice(String(requested), tickSize, closingSide);
}

export function authoritativeStopPrice(state: PaperState | null): string | null {
  if (
    !state?.ok ||
    state.position_side === "Flat" ||
    state.protection?.status !== "confirmed_active"
  ) return null;
  return state.protection.stop_loss;
}

export function authoritativeTakePrice(state: PaperState | null): string | null {
  if (
    !state?.ok ||
    state.position_side === "Flat" ||
    state.protection?.status !== "confirmed_active"
  ) return null;
  return state.protection.take_profit;
}

export function shouldClearStopDraft(
  draft: StopDraft | null,
  state: PaperState | null,
  symbol: string,
): boolean {
  if (draft === null) return false;
  if (draft.symbol !== symbol) return true;
  return state?.ok === true && state.position_side === "Flat";
}

export function paperStateNeedsPolling(state: PaperState | null): boolean {
  if (!state?.ok) return true;
  return state.active_limit_orders.length > 0
    || authoritativeStopPrice(state) !== null
    || authoritativeTakePrice(state) !== null;
}

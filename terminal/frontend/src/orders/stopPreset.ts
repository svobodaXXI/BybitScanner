import type { PaperState } from "../contracts/trading";
import { normalizeLimitDraftPrice } from "./limitDraft";

export const DEFAULT_STOP_PRESET_PERCENT = "2";
export const DEFAULT_TAKE_PRESET_PERCENT = "3";
export type ProtectionLeg = "STOP" | "TAKE";
const presetStorageKey = (leg: ProtectionLeg) =>
  `bybitscanner:paper-${leg.toLowerCase()}-preset-percent:v1`;

const positiveNumber = (value: string | null): number | null => {
  const parsed = Number(value);
  return value !== null && Number.isFinite(parsed) && parsed > 0 ? parsed : null;
};

export function loadProtectionPreset(
  leg: ProtectionLeg,
  storage: Pick<Storage, "getItem"> | null = globalThis.localStorage,
): string {
  const saved = storage?.getItem(presetStorageKey(leg)) ?? null;
  const fallback = leg === "STOP" ? DEFAULT_STOP_PRESET_PERCENT : DEFAULT_TAKE_PRESET_PERCENT;
  return positiveNumber(saved) === null ? fallback : saved!;
}

export function saveProtectionPreset(
  leg: ProtectionLeg,
  percent: string,
  storage: Pick<Storage, "setItem"> | null = globalThis.localStorage,
): void {
  if (positiveNumber(percent) !== null) storage?.setItem(presetStorageKey(leg), percent);
}

export function protectionPriceFromPercent(
  leg: ProtectionLeg,
  side: PaperState["position_side"],
  referencePrice: string | null,
  percent: string,
  tickSize: string | null,
): string | null {
  const reference = positiveNumber(referencePrice);
  const distance = positiveNumber(percent);
  if ((side !== "Long" && side !== "Short") || reference === null || distance === null) return null;
  const below = (leg === "STOP" && side === "Long") || (leg === "TAKE" && side === "Short");
  const multiplier = below ? 1 - distance / 100 : 1 + distance / 100;
  if (multiplier <= 0) return null;
  return normalizeLimitDraftPrice(
    String(reference * multiplier),
    tickSize,
    side === "Long" ? "Sell" : "Buy",
  );
}

export function protectionPercentFromPrice(
  leg: ProtectionLeg,
  side: PaperState["position_side"],
  referencePrice: string | null,
  price: string | null,
): string | null {
  const reference = positiveNumber(referencePrice);
  const normalizedPrice = positiveNumber(price);
  if ((side !== "Long" && side !== "Short") || reference === null || normalizedPrice === null) return null;
  const below = (leg === "STOP" && side === "Long") || (leg === "TAKE" && side === "Short");
  const percent = below
    ? (1 - normalizedPrice / reference) * 100
    : (normalizedPrice / reference - 1) * 100;
  if (!Number.isFinite(percent) || percent <= 0) return null;
  return String(Number(percent.toFixed(8)));
}

export const loadStopPreset = (storage: Pick<Storage, "getItem"> | null = globalThis.localStorage) =>
  loadProtectionPreset("STOP", storage);
export const loadTakePreset = (storage: Pick<Storage, "getItem"> | null = globalThis.localStorage) =>
  loadProtectionPreset("TAKE", storage);
export const saveStopPreset = (percent: string, storage: Pick<Storage, "setItem"> | null = globalThis.localStorage) =>
  saveProtectionPreset("STOP", percent, storage);
export const saveTakePreset = (percent: string, storage: Pick<Storage, "setItem"> | null = globalThis.localStorage) =>
  saveProtectionPreset("TAKE", percent, storage);
export const stopPriceFromPercent = (
  side: PaperState["position_side"], referencePrice: string | null,
  percent: string, tickSize: string | null,
) => protectionPriceFromPercent("STOP", side, referencePrice, percent, tickSize);
export const takePriceFromPercent = (
  side: PaperState["position_side"], referencePrice: string | null,
  percent: string, tickSize: string | null,
) => protectionPriceFromPercent("TAKE", side, referencePrice, percent, tickSize);
export const stopPercentFromPrice = (
  side: PaperState["position_side"], referencePrice: string | null, price: string | null,
) => protectionPercentFromPrice("STOP", side, referencePrice, price);

export function normalizeStopPrice(
  side: PaperState["position_side"],
  price: string,
  tickSize: string | null,
): string | null {
  if (side !== "Long" && side !== "Short") return null;
  return normalizeLimitDraftPrice(price, tickSize, side === "Long" ? "Sell" : "Buy");
}

export function isImprovingStop(
  side: PaperState["position_side"],
  candidate: string,
  currentStop: string,
): boolean {
  const next = positiveNumber(candidate);
  const current = positiveNumber(currentStop);
  if (next === null || current === null) return false;
  return side === "Long" ? next > current : side === "Short" ? next < current : false;
}

export function shouldCloseStopSettings(
  settingsSymbol: string | null,
  state: Pick<PaperState, "ok" | "position_side"> | null,
  workspaceSymbol: string,
): boolean {
  if (settingsSymbol === null) return false;
  if (settingsSymbol !== workspaceSymbol) return true;
  return state?.ok === true && state.position_side === "Flat";
}

import type { PaperState } from "../contracts/trading";
import { normalizeStopPrice, takePriceFromPercent } from "./stopPreset";

export type ScannerSignalContext = {
  signalId: string;
  symbol: string;
  targetPrice: string | null;
};

const handledKey = (signalId: string) =>
  `bybitscanner:signal-take-proposal-handled:v1:${encodeURIComponent(signalId)}`;

export function readScannerSignalContext(
  location: Pick<Location, "search" | "hash"> = globalThis.location,
): ScannerSignalContext | null {
  const search = new URLSearchParams(location.search);
  const hashText = location.hash.startsWith("#") ? location.hash.slice(1) : location.hash;
  const hash = new URLSearchParams(hashText);
  const value = (name: string) => search.get(name) ?? hash.get(name);
  const signalId = value("signal_id")?.trim();
  const symbol = value("symbol")?.trim().toUpperCase();
  if (!signalId || !symbol) return null;
  return { signalId, symbol, targetPrice: value("target_price")?.trim() || null };
}

export function isSignalTakeProposalHandled(
  signalId: string,
  storage: Pick<Storage, "getItem"> | null = globalThis.localStorage,
): boolean {
  return storage?.getItem(handledKey(signalId)) === "1";
}

export function markSignalTakeProposalHandled(
  signalId: string,
  storage: Pick<Storage, "setItem"> | null = globalThis.localStorage,
): void {
  storage?.setItem(handledKey(signalId), "1");
}

export function signalTakeProposalPrice({
  signal,
  state,
  activeTakePrice,
  presetPercent,
  tickSize,
  workspaceSymbol,
  handled,
}: {
  signal: ScannerSignalContext | null;
  state: PaperState | null;
  activeTakePrice: string | null;
  presetPercent: string;
  tickSize: string | null;
  workspaceSymbol: string;
  handled: boolean;
}): string | null {
  if (
    signal === null || handled || activeTakePrice !== null || !state?.ok ||
    state.position_side === "Flat" || state.average_entry === null ||
    signal.symbol !== workspaceSymbol || state.symbol !== workspaceSymbol
  ) return null;
  if (signal.targetPrice !== null) {
    const normalized = normalizeStopPrice(state.position_side, signal.targetPrice, tickSize);
    const target = Number(normalized);
    const average = Number(state.average_entry);
    const validDirection = state.position_side === "Long" ? target > average : target < average;
    if (normalized !== null && Number.isFinite(target) && validDirection) return normalized;
  }
  return takePriceFromPercent(
    state.position_side, state.average_entry, presetPercent, tickSize,
  );
}

export function shouldClearSignalTakeProposal(
  proposalSignalId: string | undefined,
  state: PaperState | null,
  workspaceSymbol: string,
  activeTakePrice: string | null,
): boolean {
  if (proposalSignalId === undefined) return false;
  return activeTakePrice !== null || state?.ok === true && (
    state.position_side === "Flat" || state.symbol !== workspaceSymbol
  );
}

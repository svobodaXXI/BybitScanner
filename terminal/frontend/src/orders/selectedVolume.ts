import type { MarketSide } from "../contracts/trading";

export type SelectedSideVolumes = Record<MarketSide, string>;

export function isValidSelectedVolume(value: string): boolean {
  const amount = Number(value);
  return value.trim() !== "" && Number.isFinite(amount) && amount > 0;
}

export function updateSelectedVolume(
  current: SelectedSideVolumes,
  side: MarketSide,
  value: string,
): SelectedSideVolumes {
  return { ...current, [side]: value };
}

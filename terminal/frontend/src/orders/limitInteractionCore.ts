import type { MarketSide } from "../contracts/trading";
import type { LimitDraft, LimitDraftOrigin } from "./limitDraft";
import { canConfirmLimitDraft } from "./limitDraft";
import { isValidSelectedVolume } from "./selectedVolume";

export type LimitInteractionIntent = {
  side: MarketSide;
  volumeUsdt: string;
  origin: LimitDraftOrigin;
};

export function captureLimitInteractionIntent(input: {
  side: MarketSide;
  selectedVolumeUsdt: string;
  defaultOneWvUsdt: string;
  origin: LimitDraftOrigin;
}): LimitInteractionIntent | null {
  const volumeUsdt = isValidSelectedVolume(input.selectedVolumeUsdt)
    ? input.selectedVolumeUsdt
    : input.defaultOneWvUsdt;
  if (!isValidSelectedVolume(volumeUsdt)) return null;
  return { side: input.side, volumeUsdt, origin: input.origin };
}

export function limitDraftVolumeUsdt(draft: LimitDraft): string {
  return draft.volume.unit === "usdt" ? draft.volume.amount : "";
}

export function canConfirmLimitInteractionDraft(draft: LimitDraft): boolean {
  return canConfirmLimitDraft(draft) && isValidSelectedVolume(limitDraftVolumeUsdt(draft));
}

export function sideDraftVolumesValid(
  drafts: readonly LimitDraft[],
  side: MarketSide,
  fallbackSelectedVolume: string,
): boolean {
  const sideDrafts = drafts.filter((draft) => draft.side === side);
  if (sideDrafts.length === 0) return isValidSelectedVolume(fallbackSelectedVolume);
  return sideDrafts.every((draft) => isValidSelectedVolume(limitDraftVolumeUsdt(draft)));
}

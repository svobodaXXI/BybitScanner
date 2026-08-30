import { useEffect, useState } from "react";
import type { PaperState } from "../contracts/trading";
import {
  normalizeStopPrice,
  protectionPercentFromPrice,
  protectionPriceFromPercent,
  type ProtectionLeg,
} from "../orders/stopPreset";

export function StopSettings({
  leg = "STOP",
  side,
  referencePrice,
  tickSize,
  presetPercent,
  onPresetChange,
  onApply,
  onClose,
}: {
  leg?: ProtectionLeg;
  side: PaperState["position_side"];
  referencePrice: string;
  tickSize: string | null;
  presetPercent: string;
  onPresetChange: (percent: string) => void;
  onApply: (price: string, percent: string) => void;
  onClose: () => void;
}) {
  const [reference] = useState(referencePrice);
  const initialPrice = protectionPriceFromPercent(leg, side, reference, presetPercent, tickSize) ?? "";
  const [price, setPrice] = useState(initialPrice);
  const [percent, setPercent] = useState(
    protectionPercentFromPrice(leg, side, reference, initialPrice) ?? presetPercent,
  );

  useEffect(() => {
    const nextPrice = protectionPriceFromPercent(leg, side, reference, presetPercent, tickSize) ?? "";
    setPrice(nextPrice);
    setPercent(protectionPercentFromPrice(leg, side, reference, nextPrice) ?? presetPercent);
  }, [leg, presetPercent, reference, side, tickSize]);

  const changePercent = (raw: string) => {
    const nextPrice = protectionPriceFromPercent(leg, side, reference, raw, tickSize);
    if (nextPrice === null) return;
    const actualPercent = protectionPercentFromPrice(leg, side, reference, nextPrice) ?? raw;
    setPrice(nextPrice);
    setPercent(actualPercent);
    onPresetChange(actualPercent);
  };
  const changePrice = (raw: string) => {
    const nextPrice = normalizeStopPrice(side, raw, tickSize);
    if (nextPrice === null) return;
    const actualPercent = protectionPercentFromPrice(leg, side, reference, nextPrice) ?? percent;
    setPrice(nextPrice);
    setPercent(actualPercent);
    onPresetChange(actualPercent);
  };

  return (
    <div className="paper-stop-settings" role="dialog" aria-label={`${leg} settings`}>
      <div className="paper-stop-settings-reference">Reference <strong>{reference}</strong></div>
      <label>Percent<input aria-label={`${leg} Percent`} inputMode="decimal" value={percent} onChange={(event) => changePercent(event.target.value)} /></label>
      <label>Price<input aria-label={`${leg} Price`} inputMode="decimal" value={price} onChange={(event) => changePrice(event.target.value)} /></label>
      <div className="paper-stop-settings-actions">
        <button type="button" onClick={() => price && onApply(price, percent)}>Apply</button>
        <button type="button" onClick={onClose}>Close</button>
      </div>
    </div>
  );
}

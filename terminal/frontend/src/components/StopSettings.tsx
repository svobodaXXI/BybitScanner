import { useEffect, useState } from "react";
import type { PaperState } from "../contracts/trading";
import {
  normalizeStopPrice,
  protectionPercentFromPrice,
  protectionPriceFromPercent,
  type ProtectionLeg,
} from "../orders/stopPreset";

const tickPrecision = (tickSize: string | null) => {
  if (!tickSize) return null;
  const numeric = Number(tickSize);
  if (!Number.isFinite(numeric) || numeric <= 0) return null;
  for (let precision = 0; precision <= 12; precision += 1) {
    const scaled = numeric * 10 ** precision;
    if (Math.abs(scaled - Math.round(scaled)) < 1e-9) return precision;
  }
  return null;
};

const formatReferencePrice = (price: string, tickSize: string | null) => {
  const numeric = Number(price);
  const precision = tickPrecision(tickSize);
  if (!Number.isFinite(numeric) || precision === null) return price;
  return numeric.toFixed(precision);
};

const formatProtectionPercent = (raw: string) => {
  const numeric = Number(raw);
  return Number.isFinite(numeric) ? numeric.toFixed(1) : raw;
};

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
    formatProtectionPercent(
      protectionPercentFromPrice(leg, side, reference, initialPrice) ?? presetPercent,
    ),
  );

  useEffect(() => {
    const nextPrice = protectionPriceFromPercent(leg, side, reference, presetPercent, tickSize) ?? "";
    setPrice(nextPrice);
    setPercent(formatProtectionPercent(
      protectionPercentFromPrice(leg, side, reference, nextPrice) ?? presetPercent,
    ));
  }, [leg, presetPercent, reference, side, tickSize]);

  const changePercent = (raw: string) => {
    const nextPrice = protectionPriceFromPercent(leg, side, reference, raw, tickSize);
    if (nextPrice === null) return;
    const actualPercent = formatProtectionPercent(
      protectionPercentFromPrice(leg, side, reference, nextPrice) ?? raw,
    );
    setPrice(nextPrice);
    setPercent(actualPercent);
    onPresetChange(actualPercent);
  };
  const changePrice = (raw: string) => {
    const nextPrice = normalizeStopPrice(side, raw, tickSize);
    if (nextPrice === null) return;
    const actualPercent = formatProtectionPercent(
      protectionPercentFromPrice(leg, side, reference, nextPrice) ?? percent,
    );
    setPrice(nextPrice);
    setPercent(actualPercent);
    onPresetChange(actualPercent);
  };

  return (
    <div className="paper-stop-settings" role="dialog" aria-label={`${leg} settings`}>
      <div className="paper-stop-settings-reference">
        Тек. цена <strong>{formatReferencePrice(reference, tickSize)}</strong>
      </div>
      <label>Percent<input aria-label={`${leg} Percent`} inputMode="decimal" value={percent} onChange={(event) => changePercent(event.target.value)} /></label>
      <label>Price<input aria-label={`${leg} Price`} inputMode="decimal" value={price} onChange={(event) => changePrice(event.target.value)} /></label>
      <div className="paper-stop-settings-actions">
        <button
          type="button"
          aria-label={`Confirm ${leg}`}
          onClick={() => price && onApply(price, percent)}
        >✓</button>
        <button
          type="button"
          aria-label={`Cancel ${leg} draft`}
          onClick={onClose}
        >×</button>
      </div>
    </div>
  );
}

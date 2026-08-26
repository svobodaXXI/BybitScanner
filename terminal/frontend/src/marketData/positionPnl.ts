export type PaperPositionSide = "Long" | "Short" | "Flat";

export const positionPnlPercent = (
  side: PaperPositionSide,
  averageEntryPrice: number | null | undefined,
  currentPrice: number | null | undefined,
) => {
  if (
    side === "Flat" ||
    !Number.isFinite(averageEntryPrice) ||
    !(averageEntryPrice! > 0) ||
    !Number.isFinite(currentPrice) ||
    !(currentPrice! > 0)
  ) {
    return null;
  }
  const direction = side === "Long" ? 1 : -1;
  const value = direction * ((currentPrice! - averageEntryPrice!) / averageEntryPrice!) * 100;
  return Number.isFinite(value) ? value : null;
};

export const formatPositionPnlPercent = (value: number) =>
  `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value).toFixed(2)}%`;

export const formatPositionAverageEntry = (value: number) =>
  value.toFixed(5);

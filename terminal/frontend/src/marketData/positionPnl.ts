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

export const tickSizePrecision = (tickSize: string) => {
  const normalized = tickSize.trim().toLowerCase();
  const [coefficient, exponentText] = normalized.split("e");
  const exponent = exponentText === undefined ? 0 : Number(exponentText);
  const decimals = coefficient.includes(".")
    ? coefficient.length - coefficient.indexOf(".") - 1
    : 0;
  return Number.isInteger(exponent) ? Math.max(0, decimals - exponent) : null;
};

export const formatPositionPrice = (value: string, tickSize: string) => {
  const numeric = Number(value);
  const precision = tickSizePrecision(tickSize);
  return Number.isFinite(numeric) && precision !== null && precision <= 12
    ? numeric.toFixed(precision)
    : "—";
};

export const formatPositionAverageEntry = (value: number) => value.toFixed(5);

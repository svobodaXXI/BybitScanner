import type { AccountWorkspaceProjection } from "../accountWorkspace/accountWorkspaceStore";

export type LiveProtectionPosition = {
  side: "Long" | "Short";
  averageEntry: string | null;
  stopLoss: string | null;
  takeProfit: string | null;
};

const positiveStringOrNull = (value: unknown): string | null => {
  if (typeof value !== "string") return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? value : null;
};

export function projectLiveProtectionPosition(
  projection: AccountWorkspaceProjection | null,
  symbol: string,
): LiveProtectionPosition | null {
  if (!projection || projection.provider !== "BYBIT") return null;
  const source = projection.positions.find((position) =>
    position.symbol === symbol
    && (position.side === "Long" || position.side === "Short")
    && Number(position.size) > 0,
  );
  if (!source || (source.side !== "Long" && source.side !== "Short")) return null;
  return {
    side: source.side,
    averageEntry: positiveStringOrNull(source.average_entry),
    stopLoss: positiveStringOrNull(source.stop_loss),
    takeProfit: positiveStringOrNull(source.take_profit),
  };
}

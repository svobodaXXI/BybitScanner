import type { AccountWorkspaceProjection } from "./accountWorkspaceStore";

/**
 * Convert one immutable MAIN read snapshot to the existing positions UI shape.
 * Never turn a read snapshot into trading authority. Reject stale/cross-account
 * data rather than showing positions of an unrelated account.
 */
export function manualMainReadProjection(
  accountId: string, raw: unknown,
): AccountWorkspaceProjection | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  if (data.account_id !== accountId || data.environment !== "MAINNET"
    || !["READY", "READ_ONLY"].includes(String(data.status))
    || typeof data.refresh_generation !== "number"
    || !Number.isSafeInteger(data.refresh_generation)
    || data.refresh_generation < 1
    || typeof data.wallet_balance_usdt !== "string"
    || typeof data.total_equity_usdt !== "string"
    || typeof data.available_balance_usdt !== "string"
    || !Array.isArray(data.positions) || !Array.isArray(data.orders)
    || data.positions.some((p: unknown) =>
      !p || typeof p !== "object" || (p as Record<string, unknown>).account_id !== accountId
    )
    || data.orders.some((o: unknown) =>
      !o || typeof o !== "object" || (o as Record<string, unknown>).account_id !== accountId
    )) return null;

  const tradeEnabled = data.trading_enabled === true && data.status === "READY";
  return {
    ok: true, account_id: accountId, provider: "BYBIT", environment: "MAINNET",
    status: String(data.status), read_only: !tradeEnabled,
    session_generation: data.refresh_generation,
    projection_generation: data.refresh_generation,
    wallet_balance_usdt: data.wallet_balance_usdt,
    total_equity_usdt: data.total_equity_usdt,
    available_balance_usdt: data.available_balance_usdt,
    positions: data.positions as Array<Record<string, unknown>>,
    orders: data.orders as Array<Record<string, unknown>>,
    paper_state: null,
    capabilities: { market: tradeEnabled, limit: tradeEnabled, stop: tradeEnabled, take: tradeEnabled, full_close: tradeEnabled },
  };
}

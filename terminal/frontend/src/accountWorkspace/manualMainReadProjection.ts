import { useEffect, useState } from "react";
import { marketApiRoutes } from "../marketData/apiRoutes";
import type { RobotTradeMarker } from "../chart/robotTradeMarkers";
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
    one_wv_usdt: typeof data.one_wv_usdt === "string" && /^[1-9][0-9]*$/.test(data.one_wv_usdt)
      && Number.isFinite(Number(data.one_wv_usdt)) ? data.one_wv_usdt : null,
    total_equity_usdt: data.total_equity_usdt,
    available_balance_usdt: data.available_balance_usdt,
    positions: data.positions as Array<Record<string, unknown>>,
    orders: data.orders as Array<Record<string, unknown>>,
    paper_state: null,
    capabilities: { market: tradeEnabled, limit: tradeEnabled, stop: tradeEnabled, take: tradeEnabled, full_close: tradeEnabled },
  };
}

const HISTORY_MS = 7 * 24 * 60 * 60 * 1000;
const EMPTY_MARKERS: readonly RobotTradeMarker[] = [];

export function parseMainExecutionHistory(accountId: string, symbol: string, raw: unknown) {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  const start = data.start_ms, end = data.end_ms;
  if (data.ok !== true || data.account_id !== accountId || data.symbol !== symbol ||
      typeof start !== "number" || typeof end !== "number" ||
      !Number.isSafeInteger(start) || !Number.isSafeInteger(end) ||
      start < 0 || end - start !== HISTORY_MS || !Array.isArray(data.executions) ||
      data.executions.length > 2000) return null;
  const markers = new Map<string, RobotTradeMarker>();
  for (const row of data.executions) {
    if (!row || typeof row !== "object" || typeof row.exec_id !== "string" || !row.exec_id ||
        typeof row.time_ms !== "number" || !Number.isSafeInteger(row.time_ms) ||
        row.time_ms < start || row.time_ms > end || typeof row.price !== "string" ||
        !Number.isFinite(Number(row.price)) || Number(row.price) <= 0 ||
        (row.side !== "Buy" && row.side !== "Sell")) return null;
    const marker: RobotTradeMarker = { time_ms: row.time_ms, price: row.price, side: row.side, filled: true };
    const prior = markers.get(row.exec_id);
    if (prior && JSON.stringify(prior) !== JSON.stringify(marker)) return null;
    markers.set(row.exec_id, marker);
  }
  return { start, end, markers: [...markers.values()] };
}

// A verified fill is immutable history, not current position or order authority.
// Keep it through brief transport outages only; never retain rejected evidence.
const STALE_HISTORY_MS = 90_000;

export function useMainExecutionHistory(accountId: string | null, symbol: string) {
  const scope = accountId === null ? null : JSON.stringify([accountId, symbol]);
  const [snapshot, setSnapshot] = useState<{
    scope: string; markers: readonly RobotTradeMarker[]; status: "ready" | "stale" | "unavailable";
  } | null>(null);
  useEffect(() => {
    setSnapshot(null);
    if (accountId === null || scope === null) return;
    const controller = new AbortController();
    let timer: number | undefined;
    let expiry: number | undefined;
    let verified: { markers: readonly RobotTradeMarker[]; at: number } | null = null;
    const cancelExpiry = () => {
      if (expiry !== undefined) window.clearTimeout(expiry);
      expiry = undefined;
    };
    const unavailable = () => {
      if (controller.signal.aborted) return;
      cancelExpiry();
      verified = null;
      setSnapshot({ scope, markers: EMPTY_MARKERS, status: "unavailable" });
    };
    const transientFailure = () => {
      if (controller.signal.aborted) return;
      const remaining = verified ? STALE_HISTORY_MS - (Date.now() - verified.at) : 0;
      if (!verified || remaining <= 0) { unavailable(); return; }
      cancelExpiry();
      const markers = verified.markers.filter(marker => marker.time_ms >= Date.now() - HISTORY_MS);
      setSnapshot({ scope, markers, status: "stale" });
      expiry = window.setTimeout(unavailable, remaining);
    };
    const read = async () => {
      try {
        let response: Response;
        try {
          response = await fetch(marketApiRoutes.manualMainExecutions(accountId, symbol),
            { signal: controller.signal, cache: "no-store" });
        } catch {
          transientFailure();
          return;
        }
        if (!response.ok) {
          if (response.status >= 500 && response.status <= 599) transientFailure();
          else unavailable();
          return;
        }
        // Invalid JSON or contradictory scope/identity must fail closed.
        const history = parseMainExecutionHistory(accountId, symbol, await response.json());
        if (controller.signal.aborted) return;
        if (!history) { unavailable(); return; }
        cancelExpiry();
        verified = { markers: history.markers, at: Date.now() };
        setSnapshot({ scope, markers: history.markers, status: "ready" });
      } catch {
        unavailable();
      } finally {
        if (!controller.signal.aborted) timer = window.setTimeout(read, 30_000);
      }
    };
    void read();
    return () => {
      controller.abort();
      cancelExpiry();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [accountId, symbol, scope]);
  return snapshot?.scope === scope ? snapshot : { markers: EMPTY_MARKERS, status: "loading" as const };
}

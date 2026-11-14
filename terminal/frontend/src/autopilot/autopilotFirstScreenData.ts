import type {
  PaperOpenPosition,
  PaperOpenPositionsResponse,
  PaperProtection,
  PaperState,
} from "../contracts/trading";
import { marketApiRoutes } from "../marketData/apiRoutes";

/**
 * AUTOPILOT first screen (AUTOPILOT_FIRST_SCREEN_AND_TRADE_DETAILS_DECISION.md).
 *
 * Read-only: every value comes from an existing GET route. A value the backend
 * does not expose is reported as a missing source, never inferred or invented.
 */

export type Loadable<T> =
  | { status: "loading" }
  | { status: "ready"; value: T }
  | { status: "error" };

export type AutopilotModeState = {
  mode: string;
  reason: string | null;
  version: number;
};

export type RobotRuntimeState = {
  mode: string;
  recoveryStatus: string;
};

/** Exact canonical PAPER Robot state; day trade totals are not a runtime indicator. */
export async function loadRobotRuntimeState(): Promise<RobotRuntimeState> {
  const body = await getJson(marketApiRoutes.robotState);
  if (typeof body.mode !== "string" || !body.mode ||
      typeof body.recovery_status !== "string" || !body.recovery_status)
    throw new Error("Canonical Robot state unavailable");
  return { mode: body.mode, recoveryStatus: body.recovery_status };
}

export type RuntimeHealth = {
  backendOnline: boolean;
  robotAdmissionReady: boolean | null;
  paperLiveSafe: boolean | null;
};

export type ProtectionHealth = {
  healthy: boolean | null;
  unhealthySymbols: string[];
};

export type PositionProtection = Loadable<PaperProtection | null>;

export type DiaryTradeSummaryRow = {
  closed_at_ms: number | null;
  pnl: string | null;
  details?: { decision?: { decision_reason?: string | null } } | null;
  symbol: string;
  trade_episode_id?: string;
  readiness: string;
  controller_origin?: string | null;
};

export type RobotDaySummary = {
  dayStartMs: number;
  closedTrades: number;
  tradesWithoutPnl: number;
  netPnl: number | null;
};

export async function loadRobotDaySummary(): Promise<RobotDaySummary> {
  const body = await getJson(marketApiRoutes.robotDaySummary);
  if (
    body.account_id !== "paper" || body.source !== "robot_trades" ||
    typeof body.day_start_ms !== "number" || !Number.isFinite(body.day_start_ms) ||
    typeof body.closed_trades !== "number" || !Number.isSafeInteger(body.closed_trades) ||
    body.closed_trades < 0 ||
    typeof body.trades_without_pnl !== "number" ||
    !Number.isSafeInteger(body.trades_without_pnl) ||
    body.trades_without_pnl < 0 || body.trades_without_pnl > body.closed_trades ||
    (body.net_pnl_usdt !== null && (
      typeof body.net_pnl_usdt !== "string" ||
      !Number.isFinite(Number(body.net_pnl_usdt))
    )) ||
    (body.net_pnl_usdt === null) !== (body.trades_without_pnl > 0)
  ) throw new Error("Robot day summary is incomplete or untrusted");
  return {
    dayStartMs: body.day_start_ms,
    closedTrades: body.closed_trades,
    tradesWithoutPnl: body.trades_without_pnl,
    netPnl: body.net_pnl_usdt === null ? null : Number(body.net_pnl_usdt),
  };
}

export type DaySummary = {
  dayStartMs: number;
  closedTrades: number;
  /** Sum of net PnL; null when any closed trade of the day has no PnL. */
  netPnl: number | null;
  tradesWithoutPnl: number;
};

const MSK_OFFSET_MS = 3 * 60 * 60 * 1000;
const DAY_MS = 24 * 60 * 60 * 1000;

/** 00:00 MSK of the business day containing ``nowMs`` (same boundary as the daily-loss gate). */
export function mskDayStartMs(nowMs: number): number {
  return Math.floor((nowMs + MSK_OFFSET_MS) / DAY_MS) * DAY_MS - MSK_OFFSET_MS;
}

export function summarizeDay(
  trades: DiaryTradeSummaryRow[],
  nowMs: number,
): DaySummary {
  const dayStartMs = mskDayStartMs(nowMs);
  const closed = trades.filter(
    (trade) => trade.closed_at_ms !== null &&
      Number.isFinite(trade.closed_at_ms) &&
      trade.closed_at_ms >= dayStartMs &&
      trade.closed_at_ms <= nowMs,
  );
  let total = 0;
  let tradesWithoutPnl = 0;
  for (const trade of closed) {
    const value = trade.pnl === null ? Number.NaN : Number(trade.pnl);
    if (Number.isFinite(value)) total += value;
    else tradesWithoutPnl += 1;
  }
  return {
    dayStartMs,
    closedTrades: closed.length,
    netPnl: tradesWithoutPnl > 0 ? null : total,
    tradesWithoutPnl,
  };
}

async function getJson(url: string, signal?: AbortSignal): Promise<Record<string, unknown>> {
  const response = signal ? await fetch(url, { signal }) : await fetch(url);
  if (!response.ok) throw new Error(`${url} failed`);
  const body = (await response.json()) as Record<string, unknown>;
  if (body.ok !== true) throw new Error(`${url} returned ok=false`);
  return body;
}

const optionalBoolean = (value: unknown) =>
  typeof value === "boolean" ? value : null;

export async function loadAutopilotMode(): Promise<AutopilotModeState> {
  const body = await getJson(marketApiRoutes.robotAutopilot);
  if (typeof body.mode !== "string")
    throw new Error("autopilot mode is missing");
  return {
    mode: body.mode,
    reason: typeof body.reason === "string" ? body.reason : null,
    version: typeof body.version === "number" ? body.version : 0,
  };
}

export async function loadRuntimeHealth(): Promise<RuntimeHealth> {
  const body = await getJson(marketApiRoutes.health);
  return {
    backendOnline: true,
    robotAdmissionReady: optionalBoolean(body.robot_admission_ready),
    paperLiveSafe: optionalBoolean(body.paper_live_safe),
  };
}

export async function loadProtectionHealth(): Promise<ProtectionHealth> {
  const body = await getJson(marketApiRoutes.robotProtectionHealth);
  const unhealthy = body.unhealthy_symbols;
  return {
    healthy: optionalBoolean(body.healthy),
    unhealthySymbols:
      unhealthy && typeof unhealthy === "object"
        ? Object.keys(unhealthy as object)
        : [],
  };
}

export async function loadOpenPositions(signal?: AbortSignal): Promise<PaperOpenPosition[]> {
  const body = (await getJson(
    marketApiRoutes.openPositions, signal,
  )) as unknown as PaperOpenPositionsResponse;
  if (!Array.isArray(body.positions)) throw new Error("positions are missing");
  return body.positions;
}

export async function loadPositionProtection(
  symbol: string,
): Promise<PaperProtection | null> {
  const body = (await getJson(
    marketApiRoutes.paperState(symbol),
  )) as unknown as PaperState;
  return body.protection ?? null;
}

export async function loadDiaryTrades(accountKey?: string): Promise<DiaryTradeSummaryRow[]> {
  const body = await getJson(marketApiRoutes.diaryTrades);
  if (!Array.isArray(body.trades)) throw new Error("diary trades are missing");
  if (accountKey !== undefined && `${body.active_account_id}:${body.session_generation}` !== accountKey) {
    throw new Error("diary account identity mismatch");
  }
  return body.trades as DiaryTradeSummaryRow[];
}

/** Entry basis recorded by the Diary for an open position, when one exists. */
export function entryBasisFor(
  symbol: string,
  trades: DiaryTradeSummaryRow[],
): string | null {
  const open = trades.find(
    (trade) => trade.symbol === symbol && trade.closed_at_ms === null,
  );
  const reason = open?.details?.decision?.decision_reason;
  return typeof reason === "string" && reason.trim() ? reason : null;
}

/** Never link a symbol to an ambiguous open trading episode. */
export function uniqueOpenEpisodeId(symbol: string, trades: DiaryTradeSummaryRow[]): string | null {
  const matches = trades.filter((trade) => trade.symbol === symbol && trade.closed_at_ms === null);
  if (matches.length !== 1) return null;
  const id = matches[0].trade_episode_id;
  return typeof id === "string" && id.trim() ? id : null;
}

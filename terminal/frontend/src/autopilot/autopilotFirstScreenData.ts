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
  readiness: string;
};

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
      Number.isFinite(trade.closed_at_ms) &&\n      trade.closed_at_ms >= dayStartMs &&\n      trade.closed_at_ms <= nowMs,
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

async function getJson(url: string): Promise<Record<string, unknown>> {
  const response = await fetch(url);
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

export async function loadOpenPositions(): Promise<PaperOpenPosition[]> {
  const body = (await getJson(
    marketApiRoutes.openPositions,
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

export async function loadDiaryTrades(): Promise<DiaryTradeSummaryRow[]> {
  const body = await getJson(marketApiRoutes.diaryTrades);
  if (!Array.isArray(body.trades)) throw new Error("diary trades are missing");
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

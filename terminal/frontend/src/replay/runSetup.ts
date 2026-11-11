/** Pure configuration for a single-symbol, LOCAL SIMULATION-only replay.
 * This selects intended research components. It does NOT admit trading.
 */
export type StrategyId =
  | "NAKED_RETURN" | "NAKED_RETEST" | "MIRROR_LEVELS"
  | "WEDGE_RISING" | "WEDGE_FALLING" | "IKIGAI_BOX"
  | "H1_TREND" | "L_SHAPE" | "TRIANGLE";

export type StrategyOption = { id: StrategyId; label: string };
export const MIRROR_OPTIONS: readonly StrategyOption[] = [
  { id: "NAKED_RETURN", label: "Голая свеча — возврат" },
  { id: "NAKED_RETEST", label: "Голая свеча — ретест" },
  { id: "MIRROR_LEVELS", label: "Зеркальные уровни" },
  { id: "WEDGE_RISING", label: "Восходящий клин" },
  { id: "WEDGE_FALLING", label: "Нисходящий клин" },
  { id: "IKIGAI_BOX", label: "Ikigai Box" },
];
export const OTHER_OPTIONS: readonly StrategyOption[] = [
  { id: "H1_TREND", label: "Трендовые H1/M5" },
  { id: "L_SHAPE", label: "L-shape" },
  { id: "TRIANGLE", label: "Triangle" },
];
export const PLANNED_OPTIONS = [
  "Двойная вершина", "Двойное дно",
  "Голова и плечи", "Перевёрнутая голова и плечи",
  "Разворотные свечные формации (общий признак)",
] as const;
export const ALL_SELECTABLE = [...MIRROR_OPTIONS, ...OTHER_OPTIONS].map(x => x.id);

export type RunSelection = {
  mirror: boolean;
  selected: readonly StrategyId[];
};
export function selectAll(): RunSelection {
  return { mirror: true, selected: [...ALL_SELECTABLE] };
}
export function clearAll(): RunSelection {
  return { mirror: false, selected: [] };
}
export function toggleMirror(current: RunSelection, enabled: boolean): RunSelection {
  const ids = new Set(current.selected);
  for (const option of MIRROR_OPTIONS) {
    if (enabled) ids.add(option.id);
    else ids.delete(option.id);
  }
  return { mirror: enabled, selected: ALL_SELECTABLE.filter(id => ids.has(id)) };
}
export function toggleStrategy(current: RunSelection, id: StrategyId, enabled: boolean): RunSelection {
  if (!ALL_SELECTABLE.includes(id)) throw new Error("Unsupported strategy");
  const ids = new Set(current.selected);
  if (enabled) ids.add(id);
  else ids.delete(id);
  return {
    mirror: current.mirror || (enabled && MIRROR_OPTIONS.some(x => x.id === id)),
    selected: ALL_SELECTABLE.filter(option => ids.has(option)),
  };
}
export function onlyWedges(): RunSelection {
  return { mirror: false, selected: ["WEDGE_RISING", "WEDGE_FALLING"] };
}
export function isAllSelected(selection: RunSelection): boolean {
  return selection.mirror && ALL_SELECTABLE.every(id => selection.selected.includes(id));
}

// datetime-local strings are treated as UTC wall clock, NEVER browser local timezone.
// A "month" preset is the agreed 30-day test interval; 3 months is 90 days.
export type PeriodPreset = "DAY" | "WEEK" | "MONTH" | "THREE_MONTHS";
export type PeriodIncrement = "HOUR" | "DAY" | "WEEK" | "MONTH";

/** The Source card and input share one reversible UTC coordinate format. */
export function formatRunCoordinates(
  symbol: string, start: string, endInclusive: string,
): string {
  return `${symbol} | ${start} | ${endInclusive} UTC`;
}
/** Also accept the legacy Source-card em dash, without relaxing UTC validation. */
export function parseRunCoordinates(value: string): {
  symbol: string; start_utc: string; end_utc_inclusive: string;
} {
  const format = "Формат: XRPUSDT | 2026-09-11T00:00 | 2026-09-11T23:59";
  if (value.length > 200) throw new Error(format);
  const stripped = value.trim().replace(/\s+UTC$/i, "");
  const legacy = /^([^|]+?)\s*\|\s*(\S+)\s+[—–]\s+(\S+)$/.exec(stripped);
  const parts = legacy ? legacy.slice(1) : stripped.split(/\s*\|\s*/);
  if (parts.length !== 3) throw new Error(format);
  const [symbol, start_utc, end_utc_inclusive] = parts.map(x => x.trim());
  if (!/^[A-Z0-9]{2,25}USDT$/.test(symbol))
    throw new Error("В координатах должен быть один USDT-тикер");
  const window = validateInclusiveWindow(start_utc, end_utc_inclusive);
  if (window.minutes > 90 * 1440) throw new Error("Максимальный прогон — 90 дней");
  return { symbol, start_utc, end_utc_inclusive };
}
/** Human-readable exact inclusive duration. A month equals 30 days in this simulator. */
export function formatRunDuration(minutes: number): string {
  if (!Number.isSafeInteger(minutes) || minutes <= 0)
    throw new Error("Неверная продолжительность прогона");
  const suffix = (count: number, one: string, two: string, many: string) => {
    const lastTwo = count % 100;
    const last = count % 10;
    return lastTwo >= 11 && lastTwo <= 14 ? many :
      last === 1 ? one : last >= 2 && last <= 4 ? two : many;
  };
  const units = [
    [30 * 1440, "месяц", "месяца", "месяцев"],
    [1440, "день", "дня", "дней"],
    [60, "час", "часа", "часов"],
    [1, "минута", "минуты", "минут"],
  ] as const;
  let remaining = minutes;
  const parts: string[] = [];
  for (const [unit, one, two, many] of units) {
    const value = Math.floor(remaining / unit);
    remaining %= unit;
    if (value) parts.push(`${value} ${suffix(value, one, two, many)}`);
  }
  return parts.join(" ");
}
const INCREMENT_MINUTES: Record<PeriodIncrement, number> = {
  HOUR: 60, DAY: 1440, WEEK: 7 * 1440, MONTH: 30 * 1440,
};
const PRESET_DAYS: Record<PeriodPreset, number> = {
  DAY: 1, WEEK: 7, MONTH: 30, THREE_MONTHS: 90,
};
export function parseUtcMinute(value: string): number {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) throw new Error("Укажите дату, час и минуту UTC");
  const [year, month, day, hour, minute] = match.slice(1).map(Number);
  const time = Date.UTC(year, month - 1, day, hour, minute);
  const iso = new Date(time).toISOString().slice(0, 16);
  if (!Number.isFinite(time) || iso !== value) throw new Error("Некорректная дата или время UTC");
  return time;
}
export function presetEndInclusive(start: string, preset: PeriodPreset): string {
  const time = parseUtcMinute(start);
  return new Date(time + (PRESET_DAYS[preset] * 1440 - 1) * 60_000).toISOString().slice(0, 16);
}
/** Extend the existing inclusive UTC range without changing its start.
 * "Month" intentionally means 30 days, matching the legacy selector.
 */
export function adjustInclusiveWindow(
  start: string, endInclusive: string, increment: PeriodIncrement,
  direction: 1 | -1,
): string {
  const window = validateInclusiveWindow(start, endInclusive);
  const minutes = window.minutes + direction * INCREMENT_MINUTES[increment];
  if (minutes <= 0) throw new Error("Продолжительность должна быть хотя бы 1 минута");
  if (minutes > 90 * 1440) throw new Error("Максимальный прогон — 90 дней");
  return new Date(window.startMs + (minutes - 1) * 60_000)
    .toISOString().slice(0, 16);
}
export function extendInclusiveWindow(
  start: string, endInclusive: string, increment: PeriodIncrement,
): string {
  return adjustInclusiveWindow(start, endInclusive, increment, 1);
}

export function validateInclusiveWindow(start: string, endInclusive: string): {
  startMs: number; endExclusiveMs: number; minutes: number;
} {
  const startMs = parseUtcMinute(start);
  const end = parseUtcMinute(endInclusive);
  if (end < startMs) throw new Error("Конец прогона раньше начала");
  const endExclusiveMs = end + 60_000;
  if (!Number.isSafeInteger(endExclusiveMs)) throw new Error("Время за пределами допустимого диапазона");
  return { startMs, endExclusiveMs, minutes: (endExclusiveMs - startMs) / 60_000 };
}


/** Only these two original Wedge Scanner/Robot detectors exist in local mode. */
export const RUNNABLE_WEDGE_IDS = ["WEDGE_RISING", "WEDGE_FALLING"] as const;
export function runnableWedgeSelection(selection: RunSelection): boolean {
  return selection.selected.length > 0 && selection.selected.every(
    id => RUNNABLE_WEDGE_IDS.some(wedge => wedge === id),
  );
}
export function makeWedgeRunRequest(
  selection: RunSelection, symbol: string, start: string,
  endInclusive: string, initialBalance: string,
): {
  symbol: string; start_utc: string; end_utc_inclusive: string;
  selected_strategies: StrategyId[]; initial_balance: string;
} {
  if (!runnableWedgeSelection(selection)) {
    throw new Error("Пока доступны только восходящий и нисходящий клинья");
  }
  const { minutes } = validateInclusiveWindow(start, endInclusive);
  if (minutes > 90 * 1440) throw new Error("Максимальный прогон — 90 дней");
  const ticker = symbol.trim().toUpperCase();
  if (!/^[A-Z0-9]{2,25}USDT$/.test(ticker)) throw new Error("Укажите один USDT-тикер");
  if (!/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(initialBalance) ||
      !(Number(initialBalance) > 0) || !Number.isFinite(Number(initialBalance))) {
    throw new Error("Укажите положительный виртуальный депозит");
  }
  return {
    symbol: ticker, start_utc: start, end_utc_inclusive: endInclusive,
    selected_strategies: [...selection.selected], initial_balance: initialBalance,
  };
}

export type LocalWedgeStatus = {
  namespace: "SIMULATION";
  can_attempt: boolean;
  wedge_engine_available: boolean;
  python_dependencies_available: boolean;
  archive_files_present: boolean;
  wedge_risk_profile_present: boolean;
  archive_hint?: {
    symbol: string; start_utc: string; end_utc_inclusive: string;
  };
};
export function parseWedgeStatus(raw: unknown): LocalWedgeStatus {
  if (!raw || typeof raw !== "object") throw new Error("Недостоверный статус симулятора");
  const x = raw as Record<string, unknown>;
  if (x.namespace !== "SIMULATION" ||
      ["can_attempt", "wedge_engine_available", "python_dependencies_available",
       "archive_files_present", "wedge_risk_profile_present"].some(k => typeof x[k] !== "boolean")) {
    throw new Error("Неверный ответ локального SIMULATION");
  }
  if (x.archive_hint !== undefined) {
    const hint = x.archive_hint;
    if (!hint || typeof hint !== "object") throw new Error("Неверная подсказка архива");
    const h = hint as Record<string, unknown>;
    if (typeof h.symbol !== "string" || !/^[A-Z0-9]{2,25}USDT$/.test(h.symbol) ||
        typeof h.start_utc !== "string" || typeof h.end_utc_inclusive !== "string") {
      throw new Error("Неверный тикер или период архива");
    }
    const window = validateInclusiveWindow(h.start_utc, h.end_utc_inclusive);
    if (window.minutes !== 1440) throw new Error("Подсказка должна охватывать полный день");
  }
  return x as LocalWedgeStatus;
}

export type LocalWedgeResult = {
  namespace: "SIMULATION"; symbol: string; scenario_type: string;
  requested_minutes: number; scanner_wedge_observations: number;
  robot_retests_in_period: number; submitted_protected_limits: number;
  virtual_fills: number; stop_exits: number; take_exits: number;
  realized_net_pnl: string; unrealized_pnl: string; total_net_pnl: string;
  total_fees: string; return_percent: string; max_drawdown_percent: string;
  risk_terms_status: string; source_id: string;
};
export function parseWedgeResult(raw: unknown): LocalWedgeResult {
  if (!raw || typeof raw !== "object") throw new Error("Недостоверный отчёт SIMULATION");
  const x = raw as Record<string, unknown>;
  if (x.namespace !== "SIMULATION" ||
      x.scenario_type !== "ORIGINAL_WEDGE_SCANNER_ROBOT_LOCAL_OHLC_SIMULATION" ||
      x.risk_terms_status !== "EXPLICIT_RESEARCH_ASSUMPTIONS_NOT_EXCHANGE_VERIFIED") {
    throw new Error("Отчёт не соответствует локальному прогону клиньев");
  }
  for (const key of ["symbol", "source_id", "realized_net_pnl", "unrealized_pnl",
    "total_net_pnl", "total_fees", "return_percent", "max_drawdown_percent"]) {
    if (typeof x[key] !== "string") throw new Error("В отчёте отсутствует " + key);
  }
  for (const key of ["requested_minutes", "scanner_wedge_observations",
    "robot_retests_in_period", "submitted_protected_limits", "virtual_fills",
    "stop_exits", "take_exits"]) {
    if (!Number.isSafeInteger(x[key]) || (x[key] as number) < 0) {
      throw new Error("Неверное количество событий в отчёте");
    }
  }
  return x as LocalWedgeResult;
}

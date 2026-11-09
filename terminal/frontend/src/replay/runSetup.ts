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

/** Metadata from the same proven PAPER Robot trade as chart execution markers. */
export type RobotPositionOrigin = {
  pattern: string | null;
  candidate_id: string;
  signal_timeframe_minutes: number | null;
  mirror_campaign: boolean;
  mirror_level_source: string | null;
  mirror_pattern: string | null;
  reentry_attempt_index: number | null;
};

/** Unknown or partial backend data is never presented as a verified signal. */
export function parseRobotPositionOrigin(value: unknown): RobotPositionOrigin | null {
  if (!value || typeof value !== "object") return null;
  const item = value as Record<string, unknown>;
  const optionalText = (field: unknown) => field === null || typeof field === "string";
  if (typeof item.candidate_id !== "string" || item.candidate_id.length === 0 ||
      !optionalText(item.pattern) || !optionalText(item.mirror_level_source) ||
      !optionalText(item.mirror_pattern) || typeof item.mirror_campaign !== "boolean" ||
      (item.signal_timeframe_minutes !== null &&
        (!Number.isSafeInteger(item.signal_timeframe_minutes) || Number(item.signal_timeframe_minutes) <= 0)) ||
      (item.reentry_attempt_index !== null &&
        (!Number.isSafeInteger(item.reentry_attempt_index) || Number(item.reentry_attempt_index) < 0))) return null;
  return item as RobotPositionOrigin;
}

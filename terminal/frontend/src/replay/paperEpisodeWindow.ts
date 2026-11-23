/** One bounded public M5 interval for an exact, validated PAPER episode.
 *
 * Prefer the earliest verified original archive anchor when that window fits
 * the existing 7-day history limit. Never move a bar, fabricate a segment or
 * change immutable PAPER execution facts.
 */
const M5_MS = 300_000;
const HOUR_MS = 3_600_000;
const MAX_HISTORY_MS = 7 * 86_400_000;

export type EpisodeWindowFacts = {
  opened_at_ms: number;
  closed_at_ms: number;
  setup_context?: {
    status: string;
    geometry_status: string;
    original_geometry?: {
      boundaries: ReadonlyArray<{
        anchors: ReadonlyArray<{ bar_open_time_ms: number }>;
      }>;
    };
  };
};

export function verifiedEpisodeHistoryWindow(facts: EpisodeWindowFacts, nowMs: number): {
  startMs: number;
  endExclusive: number;
  episodeEndExclusive: number;
  originalAnchorsOutsideWindow: boolean;
} {
  const baseStart = Math.max(M5_MS,
    Math.floor((facts.opened_at_ms - HOUR_MS) / M5_MS) * M5_MS);
  const requestedEnd = Math.ceil((facts.closed_at_ms + HOUR_MS) / M5_MS) * M5_MS;
  const lastClosedEnd = Math.floor(nowMs / M5_MS) * M5_MS;
  const endExclusive = Math.min(requestedEnd, lastClosedEnd);
  const episodeEndExclusive = Math.ceil(facts.closed_at_ms / M5_MS) * M5_MS;
  const geometry = facts.setup_context?.status === "EXACT_D2_LINK" &&
      facts.setup_context.geometry_status === "ORIGINAL_ARCHIVE_HASH_VERIFIED"
    ? facts.setup_context.original_geometry : undefined;
  const anchorTimes = geometry?.boundaries.flatMap(boundary =>
    boundary.anchors.map(anchor => anchor.bar_open_time_ms)) ?? [];
  const earliestAnchor = anchorTimes.length ? Math.min(...anchorTimes) : null;
  const anchoredStart = earliestAnchor === null ? baseStart
    : Math.max(M5_MS, Math.floor(earliestAnchor / M5_MS) * M5_MS - M5_MS);
  const extendForGeometry = anchoredStart < baseStart &&
    endExclusive > anchoredStart && endExclusive - anchoredStart <= MAX_HISTORY_MS;
  return {
    startMs: extendForGeometry ? anchoredStart : baseStart,
    endExclusive,
    episodeEndExclusive,
    originalAnchorsOutsideWindow: anchoredStart < baseStart && !extendForGeometry,
  };
}

import { describe, expect, it } from "vitest";
import { verifiedEpisodeHistoryWindow, type EpisodeWindowFacts } from "./paperEpisodeWindow";

const five = 300_000;
const hour = 3_600_000;
const opened = Date.UTC(2026, 10, 23, 3, 0);
const closed = opened + 30 * 60_000;
const now = closed + 2 * hour;

function episode(anchor?: number): EpisodeWindowFacts {
  return {
    opened_at_ms: opened, closed_at_ms: closed,
    ...(anchor === undefined ? {} : {
      setup_context: {
        status: "EXACT_D2_LINK",
        geometry_status: "ORIGINAL_ARCHIVE_HASH_VERIFIED",
        original_geometry: {
          boundaries: [{ anchors: [
            { bar_open_time_ms: anchor }, { bar_open_time_ms: anchor + five },
          ] }],
        },
      },
    }),
  };
}

describe("exact PAPER episode public-M5 history window", () => {
  it("includes historical original segment anchors older than the entry's one-hour context", () => {
    const anchor = opened - 3 * hour;
    const result = verifiedEpisodeHistoryWindow(episode(anchor), now);
    expect(result.startMs).toBe(anchor - five);
    expect(result.endExclusive).toBe(closed + hour);
    expect(result.episodeEndExclusive).toBe(closed);
    expect(result.originalAnchorsOutsideWindow).toBe(false);
  });

  it("keeps the established one-hour context when no original source geometry exists", () => {
    const result = verifiedEpisodeHistoryWindow(episode(), now);
    expect(result.startMs).toBe(opened - hour);
    expect(result.endExclusive).toBe(closed + hour);
    expect(result.originalAnchorsOutsideWindow).toBe(false);
  });

  it("never enlarges automatic public M5 loading beyond seven days", () => {
    const result = verifiedEpisodeHistoryWindow(episode(opened - 9 * 86_400_000), now);
    expect(result.startMs).toBe(opened - hour);
    expect(result.originalAnchorsOutsideWindow).toBe(true);
  });

  it("does not trust a geometry payload when the D2 linkage is unproven", () => {
    const unproven = episode(opened - 3 * hour);
    unproven.setup_context!.status = "NO_EXACT_EPISODE_LINK";
    const result = verifiedEpisodeHistoryWindow(unproven, now);
    expect(result.startMs).toBe(opened - hour);
    expect(result.originalAnchorsOutsideWindow).toBe(false);
  });

  it("caps newly closed episodes at the last actually closed five-minute candle", () => {
    const result = verifiedEpisodeHistoryWindow(episode(opened - 2 * hour), closed - 60_000);
    expect(result.endExclusive).toBe(closed - five);
    expect(result.episodeEndExclusive).toBe(closed);
  });
});

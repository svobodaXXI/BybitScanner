import { describe, expect, it } from "vitest";
import { parseRobotPositionOrigin } from "./robotPositionOrigin";

const origin = {
  pattern: "Falling Wedge", candidate_id: "candidate-1",
  signal_timeframe_minutes: 5, mirror_campaign: false,
  mirror_level_source: null, mirror_pattern: null, reentry_attempt_index: null,
};
describe("verified Robot position origin", () => {
  it("accepts exact typed provenance", () => {
    expect(parseRobotPositionOrigin(origin)).toEqual(origin);
  });
  it("rejects a partial or mismatched origin instead of guessing", () => {
    expect(parseRobotPositionOrigin({ ...origin, candidate_id: "" })).toBeNull();
    expect(parseRobotPositionOrigin({ ...origin, signal_timeframe_minutes: "5" })).toBeNull();
    expect(parseRobotPositionOrigin({ ...origin, mirror_campaign: "true" })).toBeNull();
    expect(parseRobotPositionOrigin(undefined)).toBeNull();
  });
});

import { describe, expect, it } from "vitest";
import {
  activateTouchCrosshair,
  moveTouchCrosshair,
  releaseTouchCrosshair,
  type TouchCrosshairState,
} from "./crosshairInteraction";

describe("touch crosshair interaction", () => {
  it("turns movement before hold activation into pan", () => {
    const pending: TouchCrosshairState = {
      mode: "PENDING",
      start: { x: 10, y: 10 },
    };
    expect(moveTouchCrosshair(pending, { x: 30, y: 10 })).toEqual({
      mode: "PANNING",
    });
    expect(activateTouchCrosshair({ mode: "PANNING" })).toEqual({
      mode: "PANNING",
    });
  });

  it("activates inspection after hold and pins on release", () => {
    const inspecting = activateTouchCrosshair({
      mode: "PENDING",
      start: { x: 10, y: 10 },
    });
    expect(moveTouchCrosshair(inspecting, { x: 40, y: 50 })).toEqual({
      mode: "INSPECTING",
    });
    expect(releaseTouchCrosshair(inspecting)).toEqual({ mode: "PINNED" });
  });

  it("a subsequent tap clears the pinned state", () => {
    expect(releaseTouchCrosshair({ mode: "PINNED" })).toEqual({ mode: "IDLE" });
  });
});

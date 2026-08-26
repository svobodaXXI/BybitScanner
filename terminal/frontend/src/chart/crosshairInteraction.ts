export const CROSSHAIR_HOLD_MS = 500;
export const CROSSHAIR_MOVE_TOLERANCE_PX = 8;

export type TouchCrosshairState =
  | { mode: "IDLE" }
  | { mode: "PENDING"; start: { x: number; y: number } }
  | { mode: "PANNING" }
  | { mode: "INSPECTING" }
  | { mode: "PINNED" };

export function moveTouchCrosshair(
  state: TouchCrosshairState,
  point: { x: number; y: number },
): TouchCrosshairState {
  if (state.mode !== "PENDING") return state;
  return Math.hypot(point.x - state.start.x, point.y - state.start.y)
    > CROSSHAIR_MOVE_TOLERANCE_PX
    ? { mode: "PANNING" }
    : state;
}

export function activateTouchCrosshair(
  state: TouchCrosshairState,
): TouchCrosshairState {
  return state.mode === "PENDING" ? { mode: "INSPECTING" } : state;
}

export function releaseTouchCrosshair(
  state: TouchCrosshairState,
): TouchCrosshairState {
  return state.mode === "INSPECTING" ? { mode: "PINNED" } : { mode: "IDLE" };
}

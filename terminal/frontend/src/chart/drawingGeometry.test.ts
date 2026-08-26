import { describe, expect, it } from "vitest";
import { rayEndPoint } from "./drawingGeometry";

describe("ray geometry", () => {
  it("starts at the origin and extends only forward through direction", () => {
    expect(
      rayEndPoint({ x: 20, y: 30 }, { x: 40, y: 40 }, { width: 100, height: 100 }),
    ).toEqual({ x: 100, y: 70 });
    expect(
      rayEndPoint({ x: 80, y: 60 }, { x: 60, y: 50 }, { width: 100, height: 100 }),
    ).toEqual({ x: 0, y: 20 });
  });
});

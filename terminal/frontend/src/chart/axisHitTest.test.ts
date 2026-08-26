import { describe, expect, it } from "vitest";
import { chartAxisTarget } from "./axisHitTest";

describe("chart double-click axis targeting", () => {
  it("recognizes only the bottom strip as the time scale", () => {
    expect(chartAxisTarget({ x: 200, y: 390 }, 500, 400, 64, 30)).toBe("TIME");
    expect(chartAxisTarget({ x: 490, y: 200 }, 500, 400, 64, 30)).toBe("PRICE");
    expect(chartAxisTarget({ x: 200, y: 200 }, 500, 400, 64, 30)).toBe("PLOT");
  });

  it("gives the bottom time scale priority at the lower-right corner", () => {
    expect(chartAxisTarget({ x: 490, y: 390 }, 500, 400, 64, 30)).toBe("TIME");
  });
});

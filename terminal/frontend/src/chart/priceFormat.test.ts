import { describe, expect, it } from "vitest";
import { chartPriceFormat } from "./priceFormat";

describe("authoritative chart tick size", () => {
  it("configures native ONGUSDT precision and minimum move", () => {
    const format = chartPriceFormat(0.00001);
    expect(format).toMatchObject({
      type: "custom",
      precision: 5,
      minMove: 0.00001,
    });
    expect(format?.formatter(0.169)).toBe(".16900");
  });

  it("supports non-power-of-ten tick sizes", () => {
    const format = chartPriceFormat(0.25);
    expect(format).toMatchObject({
      type: "custom",
      precision: 2,
      minMove: 0.25,
    });
    expect(format?.formatter(64_000.5)).toBe("64000.50");
  });
});

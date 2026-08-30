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
    expect(format?.formatter(0.169)).toBe("0.16900");
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

  it("compacts only prices with at least two leading fractional zeros", () => {
    expect(chartPriceFormat(0.00001)?.formatter(0.11203)).toBe("0.11203");
    expect(chartPriceFormat(0.00001)?.formatter(0.01234)).toBe("0.01234");
    expect(chartPriceFormat(0.000001)?.formatter(0.003367)).toBe("(2)3367");
    expect(chartPriceFormat(0.0000001)?.formatter(0.0003367)).toBe("(3)3367");
    expect(chartPriceFormat(0.00000001)?.formatter(0.00003367)).toBe("(4)3367");
  });
});

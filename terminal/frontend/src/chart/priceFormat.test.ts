import { describe, expect, it } from "vitest";
import { chartPriceFormat } from "./priceFormat";

describe("authoritative chart tick size", () => {
  it("configures native ONGUSDT precision and minimum move", () => {
    expect(chartPriceFormat(0.00001)).toEqual({
      type: "price",
      precision: 5,
      minMove: 0.00001,
    });
  });

  it("supports non-power-of-ten tick sizes", () => {
    expect(chartPriceFormat(0.25)).toEqual({
      type: "price",
      precision: 2,
      minMove: 0.25,
    });
  });
});

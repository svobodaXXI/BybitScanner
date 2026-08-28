import { describe, expect, it } from "vitest";
import { isValidSelectedVolume, updateSelectedVolume } from "./selectedVolume";

describe("selected side volume", () => {
  it("accepts only finite positive numeric text", () => {
    expect(isValidSelectedVolume("125.5")).toBe(true);
    expect(isValidSelectedVolume("")).toBe(false);
    expect(isValidSelectedVolume("0")).toBe(false);
    expect(isValidSelectedVolume("-1")).toBe(false);
    expect(isValidSelectedVolume("Infinity")).toBe(false);
  });

  it("updates one side without changing the other", () => {
    expect(updateSelectedVolume({ Buy: "100", Sell: "200" }, "Buy", "125"))
      .toEqual({ Buy: "125", Sell: "200" });
    expect(updateSelectedVolume({ Buy: "100", Sell: "200" }, "Sell", "225"))
      .toEqual({ Buy: "100", Sell: "225" });
  });
});

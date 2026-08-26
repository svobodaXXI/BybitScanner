import { describe, expect, it } from "vitest";
import { marketApiRoutes } from "./apiRoutes";

describe("LAN-safe market API routes", () => {
  it("keeps every browser request on the frontend origin", () => {
    const routes = [
      marketApiRoutes.book("ONGUSDT"),
      marketApiRoutes.trades("ONGUSDT"),
      marketApiRoutes.candles("ONGUSDT", "D"),
      marketApiRoutes.paperState("ONGUSDT"),
    ];
    expect(routes.every((route) => route.startsWith("/api/"))).toBe(true);
    expect(routes.join(" ")).not.toMatch(/127\.0\.0\.1|localhost|https?:\/\//);
  });
});

import { describe, expect, it } from "vitest";
import { loadSignalGeometry, projectBoundaries } from "./signalGeometryClient";

const T0 = Date.parse("2026-10-19T00:00:00.000Z");
const candles = [0, 1, 2, 3].map((i) => ({
  time: new Date(T0 + i * 300_000).toISOString(), open: 1, high: 2, low: 0.5, close: 1.5,
}));
const body = {
  ok: true, signal_id: "sig1", symbol: "AVAUSDT",
  boundaries: [
    { boundary_id: "sig1:upper", kind: "upper", anchors: [
      { bar_open_time_ms: T0, price: 2 }, { bar_open_time_ms: T0 + 900_000, price: 1.8 }] },
    { boundary_id: "sig1:lower", kind: "lower", anchors: [
      { bar_open_time_ms: T0 + 300_000, price: 1 }, { bar_open_time_ms: T0 + 600_000, price: 1.2 }] },
  ],
};
const reply = (status: number, json: unknown) =>
  (async () => new Response(JSON.stringify(json), { status })) as unknown as typeof fetch;

describe("signal geometry client", () => {
  it("returns both frozen boundaries and projects them onto matching candles", async () => {
    const result = await loadSignalGeometry("sig1", "AVAUSDT", reply(200, body));
    expect(result.status).toBe("ready");
    if (result.status !== "ready") return;
    const { drawings, error } = projectBoundaries(result.boundaries, candles);
    expect(error).toBeNull();
    expect(drawings).toHaveLength(2);
    expect(drawings.map((d) => d.anchors.map((a) => a.logical))).toEqual([[0, 3], [1, 2]]);
    expect(drawings.every((d) => d.locked)).toBe(true);
  });

  it("reports an anchor candle outside the chart window instead of drawing a guess", async () => {
    const result = await loadSignalGeometry("sig1", "AVAUSDT", reply(200, body));
    if (result.status !== "ready") throw new Error("expected ready");
    const projected = projectBoundaries(result.boundaries, candles.slice(2));
    expect(projected.drawings).toEqual([]);
    expect(projected.error).toMatch(/вне загруженного окна/);
  });

  it("explains unavailable geometry and rejects a response for another signal", async () => {
    const unproven = await loadSignalGeometry("sig1", "AVAUSDT",
      reply(422, { ok: false, error: "geometry_unavailable", reason: "index_time_mapping_unproven" }));
    expect(unproven).toEqual({ status: "unavailable", message: expect.stringContaining("не подтверждено") });
    const missing = await loadSignalGeometry("sig1", "AVAUSDT", reply(404, { ok: false }));
    expect(missing.status).toBe("unavailable");
    const other = await loadSignalGeometry("sig1", "AVAUSDT", reply(200, { ...body, signal_id: "sig2" }));
    expect(other.status).toBe("unavailable");
    const wrongSymbol = await loadSignalGeometry("sig1", "BTCUSDT", reply(200, body));
    expect(wrongSymbol.status).toBe("unavailable");
  });

  it("rejects malformed anchors and a network failure", async () => {
    const broken = { ...body, boundaries: [{ boundary_id: "x", anchors: [{ bar_open_time_ms: 0, price: 1 }] }, body.boundaries[1]] };
    expect((await loadSignalGeometry("sig1", "AVAUSDT", reply(200, broken))).status).toBe("unavailable");
    const failing = (async () => { throw new Error("down"); }) as unknown as typeof fetch;
    expect((await loadSignalGeometry("sig1", "AVAUSDT", failing)).status).toBe("unavailable");
  });
});

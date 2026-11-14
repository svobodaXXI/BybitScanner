import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useRobotSignalGeometry } from "./useRobotSignalGeometry";

const first = Date.UTC(2026, 10, 9, 10);
const second = first + 300_000;
const candles = [
  { time: new Date(first).toISOString(), open: 100, high: 103, low: 99, close: 101 },
  { time: new Date(second).toISOString(), open: 101, high: 104, low: 100, close: 103 },
];
const origin = {
  pattern: "Falling Wedge", candidate_id: "candidate-btc",
  signal_timeframe_minutes: 5, mirror_campaign: false,
  mirror_level_source: null, mirror_pattern: null, reentry_attempt_index: null,
};
const archive = {
  ok: true,
  snapshot: {
    schema_version: 1, signal_id: "candidate-btc", symbol: "BTCUSDT", timeframe: "5",
    bars: [{ open_time_ms: first }, { open_time_ms: second }],
    boundaries: [{ boundary_id: "ray-1", kind: "ray", anchors: [
      { bar_open_time_ms: first, price: 100 },
      { bar_open_time_ms: second, price: 101 },
    ] }],
  },
};
const markers = { symbol: "BTCUSDT", tradeId: "robot-btc", markers: [], origin };
const args = { observing: true, tradeId: "robot-btc" as string | null,
  symbol: "BTCUSDT", markers: markers as typeof markers | null,
  timeframe: "5m", candles };

afterEach(() => { vi.unstubAllGlobals(); });

describe("selected Robot source geometry", () => {
  it("loads only the immutable exact candidate and hides old source on trade switch", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(archive), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const view = renderHook((props: typeof args) => useRobotSignalGeometry(props),
      { initialProps: args });
    await waitFor(() => expect(view.result.current.drawings).toHaveLength(1));
    expect(view.result.current.drawings?.[0].anchors).toEqual([
      { logical: 0, price: 100 }, { logical: 1, price: 101 },
    ]);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workspace/signal-geometry?signal_id=candidate-btc",
      expect.objectContaining({ credentials: "same-origin", signal: expect.any(AbortSignal) }),
    );

    view.rerender({ ...args, tradeId: "robot-eth", markers: null });
    expect(view.result.current.drawings).toBeNull();
    expect(view.result.current.origin).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    view.unmount();
  });

  it("aborts pending source requests when leaving Robot observation", async () => {
    let finish!: (response: Response) => void;
    const pending = new Promise<Response>((resolve) => { finish = resolve; });
    const fetchMock = vi.fn((_url: string, _options?: RequestInit) => pending);
    vi.stubGlobal("fetch", fetchMock);
    const view = renderHook((props: typeof args) => useRobotSignalGeometry(props),
      { initialProps: args });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const signal = fetchMock.mock.calls[0][1]?.signal;
    view.unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () => {
      finish(new Response(JSON.stringify(archive), { status: 200 }));
      await Promise.resolve();
    });
  });

  it("does not redraw on a different timeframe or missing live pivot candle", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(archive), { status: 200 })));
    const view = renderHook((props: typeof args) => useRobotSignalGeometry(props),
      { initialProps: args });
    await waitFor(() => expect(view.result.current.drawings).toHaveLength(1));
    view.rerender({ ...args, timeframe: "1m" });
    expect(view.result.current.drawings).toBeNull();
    view.rerender({ ...args, candles: candles.slice(1) });
    expect(view.result.current.drawings).toBeNull();
    view.unmount();
  });
});

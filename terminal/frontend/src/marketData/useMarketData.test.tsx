import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  setSymbol: vi.fn(),
  start: vi.fn(),
  dispose: vi.fn(),
  snapshot: { book: { symbol: "ONGUSDT" } },
}));

vi.mock("./marketDataStore", () => ({
  marketDataStore: {
    setSymbol: mocks.setSymbol,
    start: mocks.start,
    dispose: mocks.dispose,
    getSnapshot: () => mocks.snapshot,
    subscribe: () => () => {},
    setTimeframe: vi.fn(),
  },
}));

import { setMarketSymbol, useMarketData } from "./useMarketData";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("workspace bootstrap versus confirmed symbol activation", () => {
  it("does not override deep-link activation with a stale startup response", async () => {
    let resolveFetch!: (response: {
      ok: boolean;
      json: () => Promise<unknown>;
    }) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise((resolve) => {
      resolveFetch = resolve;
    })));
    const view = renderHook(() => useMarketData());
    act(() => setMarketSymbol("ETHUSDT", 101));
    await act(async () => {
      resolveFetch({ ok: true, json: async () => ({
        ok: true, workspace: { active_symbol: "ONGUSDT", active_generation: 1 },
      }) });
      await Promise.resolve();
    });
    expect(mocks.setSymbol).toHaveBeenCalledWith("ETHUSDT", 101);
    expect(mocks.setSymbol).not.toHaveBeenCalledWith("ONGUSDT", 1);
    expect(mocks.start).toHaveBeenCalledOnce();
    view.unmount();
  });

  it("hydrates the backend's current symbol when no newer activation exists", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, json: async () => ({
        ok: true, workspace: { active_symbol: "BTCUSDT", active_generation: 7 },
      }),
    })));
    const view = renderHook(() => useMarketData());
    await act(async () => { await Promise.resolve(); });
    expect(mocks.setSymbol).toHaveBeenCalledWith("BTCUSDT", 7);
    expect(mocks.start).toHaveBeenCalledOnce();
    view.unmount();
  });
});

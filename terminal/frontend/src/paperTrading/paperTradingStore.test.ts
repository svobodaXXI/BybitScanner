import { afterEach, describe, expect, it, vi } from "vitest";
import type { PaperState } from "../contracts/trading";
import { PaperTradingStore } from "./paperTradingStore";

const state = (revision: number, symbol = "ONGUSDT"): PaperState => ({
  ok: true,
  state_revision: revision,
  account_id: "paper",
  symbol,
  initial_deposit_usdt: "5000",
  equity_usdt: "5000",
  one_wv_usdt: "250",
  position_side: "Flat",
  position_quantity: "0",
  average_entry: null,
  engaged_notional_usdt: "0",
  engaged_wv: "0.0",
  active_limit_orders: [],
});

const response = (value: PaperState) => ({
  ok: true,
  json: async () => value,
}) as Response;

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, reject, resolve };
};

afterEach(() => vi.unstubAllGlobals());

describe("PaperTradingStore", () => {
  it("coalesces refresh requests during one in-flight request into one follow-up", async () => {
    const first = deferred<Response>();
    const fetcher = vi.fn()
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(response(state(2)));
    vi.stubGlobal("fetch", fetcher);
    const store = new PaperTradingStore();
    store.setSymbol("ONGUSDT");

    const refresh = store.refresh();
    expect(store.refresh()).toBe(refresh);
    expect(store.refresh()).toBe(refresh);
    first.resolve(response(state(1)));
    await refresh;

    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(store.getSnapshot().paperState?.state_revision).toBe(2);
  });

  it("does not allow an older poll response to overwrite mutation state", async () => {
    const poll = deferred<Response>();
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(poll.promise));
    const store = new PaperTradingStore();
    store.setSymbol("ONGUSDT");

    const refresh = store.refresh();
    expect(store.applyPaperState(state(4))).toBe(true);
    poll.resolve(response(state(3)));
    await refresh;

    expect(store.getSnapshot().paperState?.state_revision).toBe(4);
  });

  it("accepts an equal revision so authoritative active orders replace stale content", () => {
    const store = new PaperTradingStore();
    const listener = vi.fn();
    store.setSymbol("ONGUSDT");
    store.subscribe(listener);
    expect(store.applyPaperState(state(2))).toBe(true);
    listener.mockClear();

    const activeOrder = {
      order_id: "paper-limit-1",
      order_link_id: "paper-link-1",
      symbol: "ONGUSDT",
      side: "Buy" as const,
      price: "0.09",
      quantity: "100",
      filled_quantity: "0",
      remaining_quantity: "100",
      status: "open" as const,
      time_in_force: "GTC" as const,
      created_at_ms: 1,
      updated_at_ms: 1,
    };
    expect(store.applyPaperState({
      ...state(2),
      active_limit_orders: [activeOrder],
    })).toBe(true);
    expect(store.getSnapshot().paperState?.active_limit_orders).toEqual([activeOrder]);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("waits for the follow-up refresh after a symbol switch and rejects the old response", async () => {
    const oldSymbol = deferred<Response>();
    const fetcher = vi.fn()
      .mockReturnValueOnce(oldSymbol.promise)
      .mockResolvedValueOnce(response(state(1, "ETHUSDT")));
    vi.stubGlobal("fetch", fetcher);
    const store = new PaperTradingStore();
    store.setSymbol("ONGUSDT");

    const refresh = store.refresh();
    store.setSymbol("ETHUSDT");
    oldSymbol.resolve(response(state(9, "ONGUSDT")));
    await refresh;

    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(store.getSnapshot().paperState?.symbol).toBe("ETHUSDT");
    expect(store.getSnapshot().paperState?.state_revision).toBe(1);
  });

  it("performs the required follow-up after the in-flight refresh fails", async () => {
    const failed = deferred<Response>();
    const fetcher = vi.fn()
      .mockReturnValueOnce(failed.promise)
      .mockResolvedValueOnce(response(state(1)));
    vi.stubGlobal("fetch", fetcher);
    const store = new PaperTradingStore();
    store.setSymbol("ONGUSDT");

    const refresh = store.refresh();
    store.refresh();
    failed.reject(new Error("network"));
    await refresh;

    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(store.getSnapshot().paperState?.state_revision).toBe(1);
  });

  it("releases only the completed operation", async () => {
    const first = deferred<string>();
    const second = deferred<string>();
    const store = new PaperTradingStore();

    const firstMutation = store.runMutation("CANCEL_LIMIT:1", () => first.promise);
    const secondMutation = store.runMutation("AMEND_LIMIT:2", () => second.promise);
    first.resolve("cancelled");
    await firstMutation;

    expect(store.getSnapshot().pendingActions.has("CANCEL_LIMIT:1")).toBe(false);
    expect(store.getSnapshot().pendingActions.has("AMEND_LIMIT:2")).toBe(true);
    second.resolve("amended");
    await secondMutation;
    expect(store.getSnapshot().pendingActions.size).toBe(0);
  });

  it("deduplicates one mutation key and releases it after failure", async () => {
    const failed = deferred<string>();
    const operation = vi.fn(() => failed.promise);
    const store = new PaperTradingStore();

    const first = store.runMutation("CANCEL_LIMIT:1", operation);
    const repeated = store.runMutation("CANCEL_LIMIT:1", operation);
    expect(repeated).toBe(first);
    expect(store.getSnapshot().pendingActions.has("CANCEL_LIMIT:1")).toBe(true);
    failed.reject(new Error("network"));

    await expect(first).rejects.toThrow("network");
    expect(operation).toHaveBeenCalledTimes(1);
    expect(store.getSnapshot().pendingActions.has("CANCEL_LIMIT:1")).toBe(false);
  });
});

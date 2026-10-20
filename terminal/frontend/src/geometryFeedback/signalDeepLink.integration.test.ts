import { describe, expect, it, vi } from "vitest";
import { parseSignalWorkspaceLink } from "./signalDeepLink";
import { requestWorkspaceActivation } from "../marketData/workspaceSwitch";

// Exercise the same parser -> activation acknowledgement -> symbol setter boundary
// as App, without a PAPER backend, Telegram, network or trading runtime.
describe("Telegram workspace link mocked activation integration", () => {
  for (const [mode, symbol, timeframe, generation] of [
    ["EDITOR", "BTCUSDT", "15m", 11],
    ["TERMINAL", "ETHUSDT", "5m", 12],
  ] as const) {
    it(`${mode} applies ${symbol} only after acknowledged generation`, async () => {
      const link = parseSignalWorkspaceLink(`?mode=${mode}&symbol=${symbol}&timeframe=${timeframe}`);
      expect(link).toMatchObject({ mode, symbol, timeframe });
      if (!link) throw new Error("valid link rejected");
      const setSymbol = vi.fn();
      const setTimeframe = vi.fn();
      const fetcher = vi.fn(async (_url: string, init: RequestInit) => {
        expect(init.method).toBe("POST");
        expect(JSON.parse(String(init.body))).toEqual({ symbol });
        return { ok: true, json: async () => ({ ok: true, symbol, generation }) };
      }) as unknown as typeof fetch;
      setTimeframe(link.timeframe);
      const ack = await requestWorkspaceActivation(link.symbol, "/api/workspace/symbol", fetcher);
      if (ack.ok) setSymbol(ack.symbol, ack.generation);
      expect(ack).toEqual({ ok: true, symbol, generation });
      expect(setSymbol).toHaveBeenCalledExactlyOnceWith(symbol, generation);
      expect(setTimeframe).toHaveBeenCalledExactlyOnceWith(timeframe);
    });
  }

  it("keeps previous symbol if mock backend is unavailable or ACK mismatches", async () => {
    const link = parseSignalWorkspaceLink("?mode=EDITOR&symbol=BTCUSDT&timeframe=5m");
    expect(link).not.toBeNull();
    const setSymbol = vi.fn();
    for (const reply of [
      { ok: false, json: async () => ({ ok: false }) },
      { ok: true, json: async () => ({ ok: true, symbol: "ONGUSDT", generation: 13 }) },
    ]) {
      const fetcher = vi.fn(async () => reply) as unknown as typeof fetch;
      const ack = await requestWorkspaceActivation(link!.symbol, "/api/workspace/symbol", fetcher);
      if (ack.ok) setSymbol(ack.symbol, ack.generation);
      expect(ack.ok).toBe(false);
    }
    setSymbol.mock.calls.length === 0 || (() => { throw new Error("Unconfirmed symbol activated"); })();
    expect(setSymbol).not.toHaveBeenCalled();
  });
});

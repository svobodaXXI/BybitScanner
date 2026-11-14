import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import {
  OriginalEpisodeSignalChart, parseOriginalTradeSignal, parseOriginalTradeContinuation,
} from "./OriginalEpisodeSignalChart";

const interval = 300_000;
const t = Date.UTC(2026, 10, 13);
const identity = {
  candidateId: "candidate-42", symbol: "BTCUSDT", timeframe: "5",
  pattern: "Falling Wedge", openedAtMs: t + 2 * interval + 2500,
};
const snapshot = {
  signal_id: "candidate-42", symbol: "BTCUSDT", timeframe: "5",
  bars: [
    { open_time_ms: t, open: 100, high: 101, low: 99, close: 100.5 },
    { open_time_ms: t + interval, open: 100.5, high: 102, low: 99, close: 101 },
  ],
  boundaries: [{
    boundary_id: "lower-ray", kind: "ray",
    anchors: [
      { bar_open_time_ms: t, price: 99 },
      { bar_open_time_ms: t + interval, price: 99.2 },
    ],
  }],
};
const archived = {
  ok: true, snapshot, snapshot_revision: "a".repeat(64),
  original_pattern: "Falling Wedge",
  latest_review: { corrected_boundaries: [{
    boundary_id: "lower-ray", kind: "horizontal",
    anchors: [{ bar_open_time_ms: t, price: 123456 }],
  }] },
};
const props = {
  ...identity, side: "LONG" as const, closedAtMs: t + 4 * interval + 2000,
  executions: [
    { at: t + 2 * interval + 2500, price: 100 },
    { at: t + 4 * interval + 2000, price: 100.5 },
  ],
};
const extension = {
  ok: true, signal_id: "candidate-42", source_revision: "a".repeat(64),
  as_of_ms: t + 21 * interval, bars_sha256: "b".repeat(64),
  bars: Array.from({ length: 20 }, (_, index) => ({
    open_time_ms: t + (index + 2) * interval,
    open: 100, high: 102, low: 98, close: 100.5,
  })),
};
afterEach(() => { vi.unstubAllGlobals(); });

describe("original signal on a closed deal", () => {
  it("accepts exact source identity, ignores Editor corrections and preserves original ray", () => {
    const source = parseOriginalTradeSignal(archived, identity);
    expect(source?.snapshot.boundaries).toEqual(snapshot.boundaries);
    expect(JSON.stringify(source)).not.toContain("corrected_boundaries");
    expect(JSON.stringify(source)).not.toContain("123456");
    expect(parseOriginalTradeSignal({ ...archived, snapshot: {
      ...snapshot, symbol: "ETHUSDT",
    } }, identity)).toBeNull();
    expect(parseOriginalTradeSignal({ ...archived, original_pattern: "Rising Wedge" }, identity)).toBeNull();
    expect(parseOriginalTradeSignal({ ...archived, snapshot: {
      ...snapshot, boundaries: [{ ...snapshot.boundaries[0], anchors: [
        { bar_open_time_ms: t + 12345, price: 99 },
        { bar_open_time_ms: t + interval, price: 99.2 },
      ] }],
    } }, identity)).toBeNull();
    expect(parseOriginalTradeSignal(archived, {
      ...identity, openedAtMs: t + interval + 1,
    })).toBeNull(); // Would reveal a candle not yet closed at Robot entry.
  });

  it("rejects public continuation gaps, wrong revisions, wrong source IDs and old windows", () => {
    const source = parseOriginalTradeSignal(archived, identity)!;
    expect(parseOriginalTradeContinuation(extension, source, t + interval)).toHaveLength(20);
    expect(parseOriginalTradeContinuation({
      ...extension, source_revision: "b".repeat(64),
    }, source, t + interval)).toBeNull();
    expect(parseOriginalTradeContinuation({
      ...extension, signal_id: "another-candidate",
    }, source, t + interval)).toBeNull();
    expect(parseOriginalTradeContinuation({
      ...extension, bars: extension.bars.slice(1),
    }, source, t + interval)).toBeNull();
    expect(parseOriginalTradeContinuation(extension, source, t + 22 * interval)).toBeNull();
  });

  it("shows archived rays and public closed candles with actual execution markers", async () => {
    const fetchMock = vi.fn(async (url: string) => new Response(JSON.stringify(
      url.includes("/continuation") ? extension : archived,
    ), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<OriginalEpisodeSignalChart {...props} />);
    expect(await screen.findByRole("img", {
      name: /Закрытые свечи и исходные линии сигнала Робота/,
    })).toBeInTheDocument();
    await screen.findByText(/до выхода получены/);
    expect(screen.getByText(/Кружки: фактические исполнения.*\(2\/2\)/)).toBeInTheDocument();
    expect(screen.queryByText(/123456/)).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workspace/signal-geometry?signal_id=candidate-42", expect.any(Object),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workspace/signal-geometry/continuation?signal_id=candidate-42&after_ms=" + (t + interval),
      expect.any(Object),
    );
  });

  it("never requests unrelated source geometry without an exact candidate", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<OriginalEpisodeSignalChart {...props} candidateId={null} />);
    expect(await screen.findByText(/нет доказанной связи сделки/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not substitute edited lines or fabricate candles on missing archive", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("", { status: 404 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<OriginalEpisodeSignalChart {...props} />);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/недоступны/));
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

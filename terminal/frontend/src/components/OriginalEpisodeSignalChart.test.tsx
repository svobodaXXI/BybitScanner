import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  OriginalEpisodeSignalChart, parseOriginalTradeSignal, parseOriginalTradeContinuation,
  parseOriginalTradeTimeframe,
} from "./OriginalEpisodeSignalChart";


vi.mock("lightweight-charts", () => ({
  CandlestickSeries: "Candlestick", LineSeries: "Line",
  ColorType: { Solid: "solid" }, CrosshairMode: { Normal: 0 },
  createChart: vi.fn(() => {
    const scale = {
      getVisibleLogicalRange: vi.fn(() => null),
      setVisibleLogicalRange: vi.fn(), setVisibleRange: vi.fn(), fitContent: vi.fn(),
    };
    return {
      addSeries: vi.fn(() => ({ setData: vi.fn() })),
      removeSeries: vi.fn(), remove: vi.fn(), timeScale: () => scale,
    };
  }),
}));

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
const secondPage = {
  ...extension,
  as_of_ms: t + 41 * interval,
  bars: [...extension.bars, ...extension.bars.map(bar => ({
    ...bar, open_time_ms: bar.open_time_ms + 20 * interval,
  }))],
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
    const first = parseOriginalTradeContinuation(extension, source, t + interval)!;
    expect(first).toHaveLength(20);
    const accepted = [...source.snapshot.bars, ...first];
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
    expect(parseOriginalTradeContinuation(secondPage, source, t + 21 * interval, accepted)).toHaveLength(20);
    expect(parseOriginalTradeContinuation(secondPage, source, t + 21 * interval)).toBeNull();
    expect(parseOriginalTradeContinuation(secondPage, source, t + 20 * interval, accepted)).toBeNull();
    expect(parseOriginalTradeContinuation({
      ...secondPage, bars: secondPage.bars.slice(1),
    }, source, t + 21 * interval, accepted)).toBeNull();
    expect(parseOriginalTradeContinuation({
      ...secondPage, bars: [{ ...extension.bars[0], high: 999 }, ...secondPage.bars.slice(1)],
    }, source, t + 21 * interval, accepted)).toBeNull(); // Changed historical overlap.
    expect(parseOriginalTradeContinuation({
      ...secondPage, as_of_ms: t + 40 * interval,
    }, source, t + 21 * interval, accepted)).toBeNull();
  });

  it("loads 20 closed candles only on each click and keeps original lines unchanged", async () => {
    const firstUrl = "/api/workspace/signal-geometry/continuation?signal_id=candidate-42&after_ms="
      + (t + interval);
    const secondUrl = "/api/workspace/signal-geometry/continuation?signal_id=candidate-42&after_ms="
      + (t + 21 * interval);
    const fetchMock = vi.fn(async (url: string) => new Response(JSON.stringify(
      url === firstUrl ? extension : url === secondUrl ? secondPage : archived,
    ), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<OriginalEpisodeSignalChart {...props} />);
    expect(await screen.findByRole("application", {
      name: "Интерактивный свечной график сделки",
    })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Фактические исполнения на загруженных свечах: 0\/2/))
      .toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Показать следующие свечи" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock).toHaveBeenCalledWith(firstUrl, expect.any(Object));
    await waitFor(() => expect(screen.getByText(/Фактические исполнения на загруженных свечах: 2\/2/))
      .toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Показать следующие свечи" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(fetchMock).toHaveBeenCalledWith(secondUrl, expect.any(Object));
    await waitFor(() => expect(screen.getByText("Следующие закрытые свечи добавлены."))
      .toBeInTheDocument());
    expect(screen.queryByText(/123456/)).not.toBeInTheDocument();
  });

  it("switches to real M1 historical candles without resampling M5", async () => {
    const minute = 60_000;
    const lastBeforeEntry = t + 9 * minute;
    const afterMs = lastBeforeEntry - 20 * minute;
    const intervalUrl = "/api/workspace/signal-geometry/candles?signal_id=candidate-42&interval=1&after_ms="
      + afterMs;
    const response = {
      ok: true, signal_id: "candidate-42", source_revision: "a".repeat(64),
      interval: "1", as_of_ms: lastBeforeEntry,
      bars: Array.from({ length: 20 }, (_, i) => ({
        open_time_ms: afterMs + (i + 1) * minute,
        open: 100, high: 102, low: 98, close: 100.5,
      })),
    };
    const source = parseOriginalTradeSignal(archived, identity)!;
    expect(parseOriginalTradeTimeframe(response, source, "1", afterMs)).toHaveLength(20);
    expect(parseOriginalTradeTimeframe({ ...response, interval: "5" }, source, "1", afterMs)).toBeNull();
    expect(parseOriginalTradeTimeframe({ ...response, bars: response.bars.slice(1) }, source, "1", afterMs))
      .toBeNull();
    const fetchMock = vi.fn(async (url: string) => new Response(JSON.stringify(
      url === intervalUrl ? response : archived,
    ), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<OriginalEpisodeSignalChart {...props} />);
    await screen.findByRole("application", { name: "Интерактивный свечной график сделки" });
    fireEvent.click(screen.getByRole("button", { name: "M1" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(intervalUrl, expect.any(Object)));
    await waitFor(() => expect(screen.getByRole("button", { name: "M1" }))
      .toHaveAttribute("aria-pressed", "true"));
    fireEvent.click(screen.getByRole("button", { name: "M5" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "M5" }))
      .toHaveAttribute("aria-pressed", "true"));
    expect(fetchMock).toHaveBeenCalledTimes(2);
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
    await waitFor(() => expect(screen.getByText(/Исходная геометрия недоступна или не совпадает с сигналом сделки/)).toBeInTheDocument());
    expect(screen.queryByRole("application")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

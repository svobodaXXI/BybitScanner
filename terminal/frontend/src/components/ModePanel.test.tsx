import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ModePanel } from "./ModePanel";

afterEach(() => vi.unstubAllGlobals());

const paperState = (overrides = {}) => ({
  ok: true,
  engaged_wv: "0",
  engaged_notional_usdt: "0",
  one_wv_usdt: "250",
  ...overrides,
});

describe("ModePanel PAPER Market amounts", () => {
  it("initializes independent amounts and shows authoritative position notional", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue(
        paperState({ engaged_wv: "1.25", engaged_notional_usdt: "312.5" }),
      ),
    }));

    render(<ModePanel mode="TERMINAL" onModeChange={vi.fn()} />);

    expect(await screen.findAllByDisplayValue("250")).toHaveLength(2);
    expect(screen.getByText("313 USDT")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("BUY amount"), {
      target: { value: "300" },
    });
    expect(screen.getByLabelText("BUY amount")).toHaveValue(300);
    expect(screen.getByLabelText("SELL amount")).toHaveValue(250);
  });

  it("submits USDT notional and preserves an edited amount after refresh", async () => {
    let paperStateReads = 0;
    const fetchMock = vi.fn((url: string, _options?: RequestInit) => {
      if (url.startsWith("/api/paper-state")) {
        paperStateReads += 1;
        return Promise.resolve({
          ok: true,
          json: vi.fn().mockResolvedValue(paperState({
            engaged_wv: paperStateReads === 1 ? "0" : "1.2",
            engaged_notional_usdt: paperStateReads === 1 ? "0" : "300",
            one_wv_usdt: paperStateReads === 1 ? "250" : "260",
          })),
        });
      }
      return Promise.resolve({
        ok: true,
        json: vi.fn().mockResolvedValue({ status: "completed" }),
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ModePanel mode="TERMINAL" onModeChange={vi.fn()} />);
    const buyAmount = await screen.findByLabelText("BUY amount");
    fireEvent.change(buyAmount, { target: { value: "300" } });
    fireEvent.click(screen.getByRole("button", { name: "BUY" }));

    expect(await screen.findByText("PAPER BUY completed")).toBeInTheDocument();
    expect(buyAmount).toHaveValue(300);
    expect(screen.getByLabelText("SELL amount")).toHaveValue(260);
    expect(screen.getByText("300 USDT")).toBeInTheDocument();

    const [, options] = fetchMock.mock.calls.find(
      ([requestUrl]) => requestUrl === "/api/market",
    )!;
    expect(JSON.parse(options!.body as string)).toEqual({
      client_action_id: expect.stringMatching(/^paper-market-buy-\d+$/),
      symbol: "BTCUSDT",
      side: "Buy",
      volume: { unit: "usdt", amount: "300" },
      sizing_reference_price: "64250",
      slippage_type: "Percent",
      slippage_value: "0.5",
    });
  });

  it.each(["", "0", "-1"])("does not submit invalid amount %j", async (amount) => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue(paperState()),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ModePanel mode="TERMINAL" onModeChange={vi.fn()} />);
    const sellAmount = await screen.findByLabelText("SELL amount");
    fireEvent.change(sellAmount, { target: { value: amount } });
    fireEvent.click(screen.getByRole("button", { name: "SELL" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls.some(([url]) => url === "/api/market")).toBe(false);
  });

  it("shows the sizing-precision failure in Russian", async () => {
    const fetchMock = vi.fn((url: string) => Promise.resolve({
      ok: true,
      json: vi.fn().mockResolvedValue(
        url.startsWith("/api/paper-state")
          ? paperState()
          : { status: "blocked", reason_code: "insufficient_sizing_precision" },
      ),
    }));
    vi.stubGlobal("fetch", fetchMock);

    render(<ModePanel mode="TERMINAL" onModeChange={vi.fn()} />);
    await screen.findAllByDisplayValue("250");
    fireEvent.click(screen.getByRole("button", { name: "BUY" }));

    expect(await screen.findByText("Сумма слишком мала для шага объёма")).toBeInTheDocument();
  });

  it.each(["BUY", "SELL"])("shows a generic %s cancellation", async (side) => {
    const fetchMock = vi.fn((url: string) => Promise.resolve({
      ok: true,
      json: vi.fn().mockResolvedValue(
        url.startsWith("/api/paper-state")
          ? paperState()
          : { status: "blocked", reason_code: "offline" },
      ),
    }));
    vi.stubGlobal("fetch", fetchMock);

    render(<ModePanel mode="TERMINAL" onModeChange={vi.fn()} />);
    await screen.findAllByDisplayValue("250");
    fireEvent.click(screen.getByRole("button", { name: side }));

    expect(await screen.findByText(`${side} отменено`)).toBeInTheDocument();
  });
});

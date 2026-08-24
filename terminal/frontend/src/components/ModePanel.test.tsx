import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ModePanel } from "./ModePanel";

describe("BUY", () => {
  it("guards pending submission, resets after failure, and handles completed retry", async () => {
    let rejectFirstRequest: (reason: Error) => void = () => {};
    const firstRequest = new Promise((_, reject) => {
      rejectFirstRequest = reject;
    });
    let marketAttempts = 0;
    let paperStateReads = 0;
    const fetchMock = vi.fn((url: string, _options?: RequestInit) => {
      if (url.startsWith("/api/paper-state")) {
        paperStateReads += 1;
        return Promise.resolve({
          ok: true,
          json: vi.fn().mockResolvedValue({
            ok: true,
            engaged_wv: paperStateReads === 1 ? "0" : "1",
          }),
        });
      }
      marketAttempts += 1;
      if (marketAttempts === 1) return firstRequest;
      return Promise.resolve({
        json: vi.fn().mockResolvedValue({ status: "completed" }),
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ModePanel mode="TERMINAL" onModeChange={vi.fn()} />);
    const buyButton = screen.getByRole("button", { name: "BUY" });
    fireEvent.click(buyButton);
    fireEvent.click(buyButton);

    expect(marketAttempts).toBe(1);
    expect(buyButton).toBeDisabled();
    rejectFirstRequest(new Error("network unavailable"));
    expect(await screen.findByText("PAPER execution unavailable")).toBeInTheDocument();
    await waitFor(() => expect(buyButton).toBeEnabled());

    fireEvent.click(buyButton);

    expect(await screen.findByText("PAPER BUY completed")).toBeInTheDocument();
    expect(marketAttempts).toBe(2);
    expect(await screen.findByText("⚔️ 1.0")).toBeInTheDocument();
    const [url, options] = fetchMock.mock.calls.filter(
      ([requestUrl]) => requestUrl === "/api/market",
    )[1];
    expect(url).toBe("/api/market");
    expect(options).toMatchObject({
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    expect(JSON.parse(options!.body as string)).toEqual({
      client_action_id: expect.stringMatching(/^paper-market-buy-\d+$/),
      symbol: "BTCUSDT",
      side: "Buy",
      volume: { unit: "working_volume", amount: "1" },
      sizing_reference_price: "64250",
      slippage_type: "Percent",
      slippage_value: "0.5",
    });
  });

it("sends PAPER Market SELL with the correct payload", async () => {
  const fetchMock = vi.fn((url: string, _options?: RequestInit) => {
    if (url.startsWith("/api/paper-state")) {
      return Promise.resolve({
        ok: true,
        json: vi.fn().mockResolvedValue({ ok: true, engaged_wv: "0" }),
      });
    }
    return Promise.resolve({
      json: vi.fn().mockResolvedValue({ status: "completed" }),
    });
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<ModePanel mode="TERMINAL" onModeChange={vi.fn()} />);

  const sellButton = screen.getByRole("button", { name: "SELL" });
  fireEvent.click(sellButton);

  expect(await screen.findByText("PAPER SELL completed")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith("/api/paper-state?symbol=BTCUSDT");

  const [url, options] = fetchMock.mock.calls.find(
    ([requestUrl]) => requestUrl === "/api/market",
  )!;
  expect(url).toBe("/api/market");

  expect(JSON.parse(options!.body as string)).toEqual({
    client_action_id: expect.stringMatching(/^paper-market-sell-\d+$/),
    symbol: "BTCUSDT",
    side: "Sell",
    volume: { unit: "working_volume", amount: "1" },
    sizing_reference_price: "64250",
    slippage_type: "Percent",
    slippage_value: "0.5",
  });
});
});

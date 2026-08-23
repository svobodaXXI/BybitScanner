import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ModePanel } from "./ModePanel";

describe("BUY", () => {
  it("guards pending submission, resets after failure, and handles completed retry", async () => {
    let rejectFirstRequest: (reason: Error) => void = () => {};
    const firstRequest = new Promise((_, reject) => {
      rejectFirstRequest = reject;
    });
    const fetchMock = vi
      .fn()
      .mockReturnValueOnce(firstRequest)
      .mockResolvedValueOnce({
        json: vi.fn().mockResolvedValue({ status: "completed" }),
      });
    vi.stubGlobal("fetch", fetchMock);

    render(<ModePanel mode="TERMINAL" onModeChange={vi.fn()} />);
    const buyButton = screen.getByRole("button", { name: "BUY" });
    fireEvent.click(buyButton);
    fireEvent.click(buyButton);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(buyButton).toBeDisabled();
    rejectFirstRequest(new Error("network unavailable"));
    expect(await screen.findByText("PAPER execution unavailable")).toBeInTheDocument();
    await waitFor(() => expect(buyButton).toBeEnabled());

    fireEvent.click(buyButton);

    expect(await screen.findByText("PAPER BUY completed")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [url, options] = fetchMock.mock.calls[1];
    expect(url).toBe("/api/market");
    expect(options).toMatchObject({
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    expect(JSON.parse(options.body)).toEqual({
      client_action_id: expect.stringMatching(/^paper-market-buy-\d+$/),
      symbol: "BTCUSDT",
      side: "Buy",
      volume: { unit: "usdt", amount: "100" },
      sizing_reference_price: "64250",
      slippage_type: "Percent",
      slippage_value: "0.5",
    });
  });

it("sends PAPER Market SELL with the correct payload", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    json: vi.fn().mockResolvedValue({ status: "completed" }),
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<ModePanel mode="TERMINAL" onModeChange={vi.fn()} />);

  const sellButton = screen.getByRole("button", { name: "SELL" });
  fireEvent.click(sellButton);

  expect(await screen.findByText("PAPER SELL completed")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);

  const [url, options] = fetchMock.mock.calls[0];
  expect(url).toBe("/api/market");

  expect(JSON.parse(options.body)).toEqual({
    client_action_id: expect.stringMatching(/^paper-market-sell-\d+$/),
    symbol: "BTCUSDT",
    side: "Sell",
    volume: { unit: "usdt", amount: "100" },
    sizing_reference_price: "64250",
    slippage_type: "Percent",
    slippage_value: "0.5",
  });
});
});

import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { expect, it, vi } from "vitest";
import { TradingControlButton } from "../interactions/useTradingControlActivation";
import { ChartPanel } from "./ChartPanel";

const coordinateToPrice = vi.fn<() => number | null>(() => 100.5);

vi.mock("lightweight-charts", () => ({
  CandlestickSeries: {},
  ColorType: { Solid: "Solid" },
  CrosshairMode: { Normal: 0 },
  createChart: () => ({
    addSeries: () => ({
      coordinateToPrice,
      priceToCoordinate: () => 100,
      setData: vi.fn(),
      applyOptions: vi.fn(),
    }),
    timeScale: () => ({
      subscribeVisibleLogicalRangeChange: vi.fn(),
      unsubscribeVisibleLogicalRangeChange: vi.fn(),
      getVisibleLogicalRange: () => ({ from: 0, to: 1 }),
      setVisibleLogicalRange: vi.fn(),
      getScrollPosition: () => 0,
      scrollToPosition: vi.fn(),
      coordinateToLogical: () => 0,
    }),
    priceScale: () => ({
      width: () => 64,
      getVisibleRange: () => ({ from: 90, to: 110 }),
    }),
    remove: vi.fn(),
    clearCrosshairPosition: vi.fn(),
  }),
}));

it("emits one fast-Limit intent when a touch pointer is followed by compatibility touchstart", () => {
  const onFastLimitPriceSelect = vi.fn();
  render(
    <ChartPanel
      candles={[]}
      tickSize={0.5}
      fastLimitActive
      onFastLimitPriceSelect={onFastLimitPriceSelect}
    />,
  );
  const chart = screen.getByRole("application", {
    name: "Interactive market chart",
  });
  Object.defineProperty(chart.firstElementChild, "getBoundingClientRect", {
    value: () => ({ left: 0, top: 0 }),
  });
  fireEvent.pointerDown(chart, {
    pointerId: 2,
    pointerType: "touch",
    button: 0,
    clientX: 50,
    clientY: 80,
  });
  fireEvent.touchStart(chart, {
    changedTouches: [{ identifier: 2, clientX: 50, clientY: 80 }],
    touches: [{ identifier: 2, clientX: 50, clientY: 80 }],
  });

  expect(onFastLimitPriceSelect).toHaveBeenCalledOnce();
  expect(onFastLimitPriceSelect).toHaveBeenCalledWith("100.5");
});

it("uses a second touch pointer on the chart while the first touch holds BUY", () => {
  const onFastLimitPriceSelect = vi.fn();

  function TwoFingerHarness() {
    const [fastLimitActive, setFastLimitActive] = useState(false);
    return (
      <>
        <TradingControlButton
          aria-label="BUY"
          holdMs={200}
          onHoldStart={() => setFastLimitActive(true)}
          onHoldEnd={() => setFastLimitActive(false)}
          onCancel={() => setFastLimitActive(false)}
        >
          BUY
        </TradingControlButton>
        <ChartPanel
          candles={[]}
          tickSize={0.5}
          fastLimitActive={fastLimitActive}
          onFastLimitPriceSelect={onFastLimitPriceSelect}
        />
      </>
    );
  }

  vi.useFakeTimers();
  try {
    render(<TwoFingerHarness />);
    const buy = screen.getByRole("button", { name: "BUY" });
    const chart = screen.getByRole("application", {
      name: "Interactive market chart",
    });
    Object.defineProperty(chart.firstElementChild, "getBoundingClientRect", {
      value: () => ({ left: 0, top: 0 }),
    });

    fireEvent.pointerDown(buy, {
      pointerId: 1,
      pointerType: "touch",
      button: 0,
    });
    act(() => vi.advanceTimersByTime(200));

    fireEvent.pointerDown(chart, {
      pointerId: 2,
      pointerType: "touch",
      button: 0,
      clientX: 50,
      clientY: 80,
    });

    expect(onFastLimitPriceSelect).toHaveBeenCalledOnce();
    expect(onFastLimitPriceSelect).toHaveBeenCalledWith("100.5");
  } finally {
    vi.useRealTimers();
  }
});

it("positions confirm-all popup directly above the shared green button", () => {
  render(
    <ChartPanel
      candles={[]}
      tickSize={0.5}
      pendingLimitDrafts={[{
        draftId: "draft-1",
        symbol: "BTCUSDT",
        side: "Buy",
        origin: "chart-fast",
        volume: { unit: "usdt", amount: "250" },
        sizingReferencePrice: "100",
        price: "99",
        authoritativeTickSize: "0.5",
        status: "draft",
        clientActionId: null,
        rejectionReason: null,
      }]}
    />,
  );

  fireEvent.click(screen.getByRole("button", {
    name: "Confirm all pending Limit drafts",
  }));
  const card = screen.getByText("Confirm all pending limits?").parentElement!;
  expect(card.parentElement).toHaveClass("submit-all");
  expect(card).toHaveStyle({
    position: "absolute",
    right: "105.6px",
    bottom: "54.4px",
  });
});

it("includes limits-popup drafts in the shared confirm-all action", async () => {
  const onPendingLimitConfirm = vi.fn();

  render(
    <ChartPanel
      candles={[]}
      tickSize={0.5}
      onPendingLimitConfirm={onPendingLimitConfirm}
      pendingLimitDrafts={[{
        draftId: "popup-draft-1",
        symbol: "BTCUSDT",
        side: "Buy",
        origin: "limits-popup",
        volume: { unit: "usdt", amount: "250" },
        sizingReferencePrice: "100",
        price: "99",
        authoritativeTickSize: "0.5",
        status: "draft",
        clientActionId: null,
        rejectionReason: null,
      }]}
    />,
  );

  fireEvent.click(screen.getByRole("button", {
    name: "Confirm all pending Limit drafts",
  }));

  fireEvent.click(screen.getByRole("button", {
    name: "CONFIRM ALL",
  }));

  expect(onPendingLimitConfirm).toHaveBeenCalledOnce();
  expect(onPendingLimitConfirm).toHaveBeenCalledWith("popup-draft-1");
});

it("disables a pending Limit confirmation when its side volume is invalid", () => {
  const onPendingLimitConfirm = vi.fn();
  render(
    <ChartPanel
      candles={[]}
      tickSize={0.5}
      pendingLimitVolumeValid={{ Buy: false, Sell: true }}
      onPendingLimitConfirm={onPendingLimitConfirm}
      pendingLimitDrafts={[{
        draftId: "draft-invalid-volume",
        symbol: "BTCUSDT",
        side: "Buy",
        origin: "limits-popup",
        volume: { unit: "usdt", amount: "" },
        sizingReferencePrice: "100",
        price: "99",
        authoritativeTickSize: "0.5",
        status: "draft",
        clientActionId: null,
        rejectionReason: null,
      }]}
    />,
  );

  const confirm = screen.getByRole("button", {
    name: "Confirm pending Buy Limit",
  });
  expect(confirm).toBeDisabled();
  fireEvent.click(confirm);
  expect(onPendingLimitConfirm).not.toHaveBeenCalled();
});

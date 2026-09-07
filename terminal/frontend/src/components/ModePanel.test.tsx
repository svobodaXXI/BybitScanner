import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useCallback, useEffect, useReducer, useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PaperState } from "../contracts/trading";
import { PendingLimitLine } from "../chart/PendingLimitLine";
import {
  EMPTY_LIMIT_DRAFT_STATE,
  limitDraftReducer,
} from "../orders/limitDraft";
import { ModePanel as ModePanelView, type WorkspaceMode } from "./ModePanel";

afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const paperState = (overrides = {}) => ({
  state_revision: 1,
  ok: true,
  account_id: "paper",
  symbol: "BTCUSDT",
  initial_deposit_usdt: "5000",
  equity_usdt: "5000",
  engaged_wv: "0",
  engaged_notional_usdt: "0",
  one_wv_usdt: "250",
  position_side: "Flat",
  position_quantity: "0",
  average_entry: null,
  active_limit_orders: [],
  ...overrides,
});

function ModePanel(props: {
  mode: WorkspaceMode;
  onModeChange: (mode: WorkspaceMode) => void;
  sizingReferencePrice: string;
  onPositionSideChange: (side: PaperState["position_side"]) => void;
}) {
  const [ownedPaperState, setOwnedPaperState] = useState<PaperState | null>(null);
  const [selectedVolumes, setSelectedVolumes] = useState({ Buy: "", Sell: "" });
  const [limitDraftState, dispatchLimitDraft] = useReducer(
    limitDraftReducer,
    EMPTY_LIMIT_DRAFT_STATE,
  );
  const refreshPaperState = useCallback(async () => {
    const response = await fetch("/api/paper-state?symbol=BTCUSDT");
    setOwnedPaperState((await response.json()) as PaperState);
  }, []);

  useEffect(() => {
    void refreshPaperState();
  }, [refreshPaperState]);

  useEffect(() => {
    if (!ownedPaperState?.ok || selectedVolumes.Buy || selectedVolumes.Sell) return;
    setSelectedVolumes({
      Buy: ownedPaperState.one_wv_usdt,
      Sell: ownedPaperState.one_wv_usdt,
    });
  }, [ownedPaperState, selectedVolumes]);

  return (
    <ModePanelView
      {...props}
      symbol="BTCUSDT"
      paperState={ownedPaperState}
      activeLimitOrders={
        ownedPaperState?.ok ? ownedPaperState.active_limit_orders : []
      }
      refreshPaperState={refreshPaperState}
      authoritativeTickSize="0.5"
      limitDraftState={limitDraftState}
      dispatchLimitDraft={dispatchLimitDraft}
      onLimitDraftConfirm={vi.fn()}
      selectedVolumes={selectedVolumes}
      onSelectedVolumeChange={(side, value) =>
        setSelectedVolumes((current) => ({ ...current, [side]: value }))
      }
    />
  );
}

describe("ModePanel PAPER Market amounts", () => {
  const activeLimit = {
    order_id: "paper-limit-1",
    order_link_id: "link-1",
    symbol: "BTCUSDT",
    side: "Buy" as const,
    price: "64000",
    quantity: "0.005",
    time_in_force: "GTC" as const,
  };

  const renderLimitPopup = (onLimitDraftConfirm = vi.fn()) => {
    const state = paperState() as PaperState;
    const PopupHarness = () => {
      const [selectedVolumes, setSelectedVolumes] = useState({ Buy: "250", Sell: "250" });
      const [limitDraftState, dispatchLimitDraft] = useReducer(
        limitDraftReducer,
        EMPTY_LIMIT_DRAFT_STATE,
      );
      return (
        <>
          <ModePanelView
            mode="TERMINAL"
            onModeChange={vi.fn()}
            symbol="BTCUSDT"
            paperState={state}
            activeLimitOrders={state.active_limit_orders}
            refreshPaperState={vi.fn()}
            sizingReferencePrice="64250"
            authoritativeTickSize="0.5"
            limitDraftState={limitDraftState}
            dispatchLimitDraft={dispatchLimitDraft}
            onLimitDraftConfirm={onLimitDraftConfirm}
            selectedVolumes={selectedVolumes}
            onSelectedVolumeChange={(side, value) =>
              setSelectedVolumes((current) => ({ ...current, [side]: value }))
            }
            onPositionSideChange={vi.fn()}
          />
          {limitDraftState.draft ? (
            <PendingLimitLine
              side={limitDraftState.draft.side}
              price={limitDraftState.draft.price}
              top={120}
              onDragClientY={() =>
                dispatchLimitDraft({ type: "update-price", price: "63000.4" })
              }
              onConfirm={() => onLimitDraftConfirm(limitDraftState.draft?.draftId)}
              popupLinked={limitDraftState.draft.origin === "limits-popup"}
            />
          ) : null}
        </>
      );
    };
    render(<PopupHarness />);
    fireEvent.click(screen.getByRole("button", { name: "BUY LIMITS 0" }));
    return screen.getByRole("dialog", { name: "New Buy Limit" });
  };

  it.each([
    ["Buy", true, false], ["Sell", true, false],
    ["Buy", false, true], ["Sell", false, true],
    ["Buy", false, false], ["Sell", false, false],
  ] as const)("gates %s fast-Limit hold with PAPER=%s LIVE Limit=%s", (side, mutationsAllowed, liveLimitAllowed) => {
    vi.useFakeTimers();
    const onFastLimitHoldChange = vi.fn();
    const vibrate = vi.fn();
    Object.defineProperty(navigator, "vibrate", {
      configurable: true,
      value: vibrate,
    });
    const state = paperState() as PaperState;
    render(
      <ModePanelView
        mode="TERMINAL"
        onModeChange={vi.fn()}
        symbol="BTCUSDT"
        paperState={state}
        activeLimitOrders={[]}
        refreshPaperState={vi.fn()}
        sizingReferencePrice="64250"
        authoritativeTickSize="0.5"
        limitDraftState={EMPTY_LIMIT_DRAFT_STATE}
        dispatchLimitDraft={vi.fn()}
        onLimitDraftConfirm={vi.fn()}
        onFastLimitHoldChange={onFastLimitHoldChange}
        onPositionSideChange={vi.fn()}
        mutationsAllowed={mutationsAllowed}
        liveLimitAllowed={liveLimitAllowed}
        liveMarketAllowed
      />,
    );

    fireEvent.pointerDown(screen.getByRole("button", { name: side.toUpperCase() }));
    vi.advanceTimersByTime(199);
    expect(onFastLimitHoldChange).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    if (!mutationsAllowed && !liveLimitAllowed) {
      expect(onFastLimitHoldChange).not.toHaveBeenCalled();
      expect(vibrate).not.toHaveBeenCalled();
      return;
    }
    expect(vibrate).toHaveBeenCalledWith(20);
    expect(onFastLimitHoldChange).toHaveBeenCalledWith({
      side,
      volumeUsdt: "250",
    });
  });

  it("opens the BUY short-tap popup with the normalized LONG default", () => {
    const popup = renderLimitPopup();
    expect(within(popup).getByLabelText("LONG Limit volume")).toHaveValue(250);
    expect(within(popup).getByLabelText("LONG Limit price")).toHaveValue("62965");
    expect(within(popup).getByRole("button", { name: "Confirm LONG Limit" })).toBeEnabled();
    expect(within(popup).queryByText("SHORT")).not.toBeInTheDocument();
  });

  it("keeps the popup open for inside interaction", () => {
    const popup = renderLimitPopup();
    fireEvent.pointerDown(popup);
    fireEvent.click(within(popup).getByText("LONG"));

    expect(screen.getByRole("dialog", { name: "New Buy Limit" })).toBeInTheDocument();
    expect(within(popup).getByText("LONG").closest(".paper-limit-popup-row")).toHaveClass("selected");
  });

  it("keeps the pending line and popup on one normalized draft price", () => {
    const popup = renderLimitPopup();
    fireEvent.click(within(popup).getByText("LONG"));
    const line = screen.getByRole("slider", {
      name: "Pending Buy Limit at 62965",
    });
    Object.assign(line, {
      setPointerCapture: vi.fn(),
      hasPointerCapture: vi.fn(() => true),
      releasePointerCapture: vi.fn(),
    });

    fireEvent.pointerDown(line, { pointerId: 1, clientY: 120 });
    fireEvent.pointerMove(line, { pointerId: 1, clientY: 140 });

    expect(
      screen.getByRole("slider", { name: "Pending Buy Limit at 63000.4" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("dialog", { name: "New Buy Limit" }),
    ).toBeInTheDocument();
    expect(within(popup).getByLabelText("LONG Limit price")).toHaveValue("63000.4");
  });

  it("routes popup and chart checkmarks to the same limits-popup draft identity", () => {
    const onSubmit = vi.fn();
    const popup = renderLimitPopup(onSubmit);
    fireEvent.click(within(popup).getByText("LONG"));

    const chartConfirm = screen.getByRole("button", {
      name: "Confirm pending Buy Limit",
    });

    fireEvent.click(
      within(popup).getByRole("button", { name: "Confirm LONG Limit" }),
    );
    fireEvent.click(chartConfirm);

    expect(onSubmit).toHaveBeenCalledTimes(2);
    expect(onSubmit.mock.calls[0][0]).toBe(onSubmit.mock.calls[1][0]);
    expect(onSubmit.mock.calls[0][0]).toMatch(/^limit-draft-BTCUSDT-buy-/);
  });

  it("closes outside and dismisses the selected shared draft", () => {
    const popup = renderLimitPopup();
    fireEvent.click(within(popup).getByText("LONG"));
    fireEvent.pointerDown(document.body);

    expect(screen.queryByRole("dialog", { name: "New Buy Limit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("slider", { name: /Pending Buy Limit/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "BUY LIMITS 0" }));
    const reopened = screen.getByRole("dialog", { name: "New Buy Limit" });
    expect(within(reopened).getByText("LONG").closest(".paper-limit-popup-row")).toHaveClass("selected");
  });

  it("shows side-specific LIMITS N from authoritative active orders", () => {
    const state = paperState({ active_limit_orders: [activeLimit] }) as PaperState;
    render(
      <ModePanelView
        mode="TERMINAL"
        onModeChange={vi.fn()}
        symbol="BTCUSDT"
        paperState={state}
        activeLimitOrders={state.active_limit_orders}
        refreshPaperState={vi.fn()}
        sizingReferencePrice="64250"
        authoritativeTickSize="0.5"
        limitDraftState={EMPTY_LIMIT_DRAFT_STATE}
        dispatchLimitDraft={vi.fn()}
        onLimitDraftConfirm={vi.fn()}
        onPositionSideChange={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "BUY LIMITS 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "SELL LIMITS 0" })).toBeInTheDocument();
  });

  it("opens symbol-wide Limit cancellation confirmation from the separate cross", () => {
    const state = paperState({ active_limit_orders: [activeLimit] }) as PaperState;
    render(
      <ModePanelView
        mode="TERMINAL"
        onModeChange={vi.fn()}
        symbol="BTCUSDT"
        paperState={state}
        activeLimitOrders={state.active_limit_orders}
        refreshPaperState={vi.fn()}
        sizingReferencePrice="64250"
        authoritativeTickSize="0.5"
        limitDraftState={EMPTY_LIMIT_DRAFT_STATE}
        dispatchLimitDraft={vi.fn()}
        onLimitDraftConfirm={vi.fn()}
        onPositionSideChange={vi.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Cancel all Buy Limit orders for BTCUSDT",
      }),
    );

    expect(
      screen.getByRole("dialog", {
        name: "Cancel all LONG Limit orders for BTCUSDT?",
      }),
    ).toBeInTheDocument();
  });

  it("initializes independent amounts and shows authoritative position notional", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue(
        paperState({ engaged_wv: "1.25", engaged_notional_usdt: "312.5" }),
      ),
    }));

    render(<ModePanel mode="TERMINAL" onModeChange={vi.fn()} sizingReferencePrice="0.094" onPositionSideChange={vi.fn()} />);

    await waitFor(() => expect(screen.getAllByDisplayValue("250")).toHaveLength(2));
    expect(document.querySelector(".paper-wv-position")).toHaveTextContent("313USDT");
    fireEvent.change(screen.getByLabelText("BUY amount"), {
      target: { value: "300" },
    });
    expect(screen.getByLabelText("BUY amount")).toHaveValue(300);
    expect(screen.getByLabelText("SELL amount")).toHaveValue(250);
  });

  it("submits USDT notional and preserves an edited amount", async () => {
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

    render(<ModePanel mode="TERMINAL" onModeChange={vi.fn()} sizingReferencePrice="64250" onPositionSideChange={vi.fn()} />);
    const buyAmount = await screen.findByLabelText("BUY amount");
    await waitFor(() => expect(buyAmount).toHaveValue(250));
    fireEvent.change(buyAmount, { target: { value: "300" } });
    fireEvent.click(screen.getByRole("button", { name: "BUY" }));

    expect(await screen.findByText("PAPER BUY completed")).toBeInTheDocument();
    expect(buyAmount).toHaveValue(300);
    await waitFor(() =>
      expect(screen.getByLabelText("SELL amount")).toHaveValue(250),
    );
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

    render(<ModePanel mode="TERMINAL" onModeChange={vi.fn()} sizingReferencePrice="0.094" onPositionSideChange={vi.fn()} />);
    const sellAmount = await screen.findByLabelText("SELL amount");
    await waitFor(() => expect(sellAmount).toHaveValue(250));
    fireEvent.change(sellAmount, { target: { value: amount } });
    fireEvent.click(screen.getByRole("button", { name: "SELL" }));

    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => url.startsWith("/api/paper-state"))).toBe(true),
    );
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

    render(<ModePanel mode="TERMINAL" onModeChange={vi.fn()} sizingReferencePrice="0.094" onPositionSideChange={vi.fn()} />);
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

    render(<ModePanel mode="TERMINAL" onModeChange={vi.fn()} sizingReferencePrice="0.094" onPositionSideChange={vi.fn()} />);
    await screen.findAllByDisplayValue("250");
    fireEvent.click(screen.getByRole("button", { name: side }));

    expect(await screen.findByText(`${side} отменено`)).toBeInTheDocument();
  });

  it("submits backend-authoritative Full Close after confirmation", async () => {
    let stateReads = 0;
    const fetchMock = vi.fn((url: string, _options?: RequestInit) => {
      if (url.startsWith("/api/paper-state")) {
        stateReads += 1;
        return Promise.resolve({
          ok: true,
          json: vi.fn().mockResolvedValue(paperState({
            engaged_wv: stateReads === 1 ? "1.2" : "0.0",
            engaged_notional_usdt: stateReads === 1 ? "300" : "0",
            position_side: stateReads === 1 ? "Long" : "Flat",
            position_quantity: stateReads === 1 ? "0.005" : "0",
          })),
        });
      }
      return Promise.resolve({
        ok: true,
        json: vi.fn().mockResolvedValue({ status: "completed", reason_code: "completed" }),
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ModePanel mode="TERMINAL" onModeChange={vi.fn()} sizingReferencePrice="0.094" onPositionSideChange={vi.fn()} />);
    await waitFor(() =>
      expect(document.querySelector(".paper-wv-position")).toHaveTextContent("300USDT"),
    );
    fireEvent.click(screen.getByRole("button", { name: "Закрыть позицию" }));
    const closeDialog = screen.getByRole("dialog", { name: "Закрыть позицию?" });
    fireEvent.click(
      within(closeDialog).getByRole("button", { name: "ЗАКРЫТЬ ПОЗИЦИЮ" }),
    );

    expect(await screen.findByText("PAPER позиция закрыта")).toBeInTheDocument();
    const [, options] = fetchMock.mock.calls.find(
      ([requestUrl]) => requestUrl === "/api/full-close",
    )!;
    expect(JSON.parse(options!.body as string)).toEqual({
      client_action_id: expect.stringMatching(/^paper-full-close-\d+$/),
      symbol: "BTCUSDT",
    });
  });

  it("cancels authoritative Buy GTC PAPER limits from the side-specific control", async () => {
    const state = paperState({ active_limit_orders: [activeLimit] }) as PaperState;
    const onLimitCancel = vi.fn().mockResolvedValue({
      status: "completed",
      reason_code: "completed",
    });
    render(
      <ModePanelView
        mode="TERMINAL"
        onModeChange={vi.fn()}
        symbol="BTCUSDT"
        paperState={state}
        activeLimitOrders={state.active_limit_orders}
        refreshPaperState={vi.fn()}
        sizingReferencePrice="64250"
        authoritativeTickSize="0.5"
        limitDraftState={EMPTY_LIMIT_DRAFT_STATE}
        dispatchLimitDraft={vi.fn()}
        onLimitDraftConfirm={vi.fn()}
        onLimitCancel={onLimitCancel}
        onPositionSideChange={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Cancel all Buy Limit orders for BTCUSDT" }));
    const cancelDialog = screen.getByRole("dialog", {
      name: "Cancel all LONG Limit orders for BTCUSDT?",
    });
    fireEvent.click(within(cancelDialog).getByRole("button", { name: "CANCEL" }));
    await waitFor(() => expect(onLimitCancel).toHaveBeenCalledWith("paper-limit-1"));
  });

  it.each([["0", "321"], ["64000", "0"]])(
    "does not submit invalid LIMIT price %s amount %s", async (price, amount) => {
      const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: vi.fn().mockResolvedValue(paperState()) });
      vi.stubGlobal("fetch", fetchMock);
      render(<ModePanel mode="TERMINAL" onModeChange={vi.fn()} sizingReferencePrice="64250" onPositionSideChange={vi.fn()} />);
      await screen.findAllByDisplayValue("250");
      fireEvent.click(screen.getByRole("button", { name: "BUY LIMITS 0" }));
      fireEvent.change(screen.getByLabelText("LONG Limit price"), { target: { value: price } });
      fireEvent.change(screen.getByLabelText("LONG Limit volume"), { target: { value: amount } });
      fireEvent.click(screen.getByRole("button", { name: "Confirm LONG Limit" }));
      expect(fetchMock.mock.calls.some(([url]) => url === "/api/limit")).toBe(false);
    },
  );
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useCallback, useEffect, useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PaperState } from "../contracts/trading";
import { ModePanel as ModePanelView, type WorkspaceMode } from "./ModePanel";

afterEach(() => vi.unstubAllGlobals());

const paperState = (overrides = {}) => ({
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
  const refreshPaperState = useCallback(async () => {
    const response = await fetch("/api/paper-state?symbol=BTCUSDT");
    setOwnedPaperState((await response.json()) as PaperState);
  }, []);

  useEffect(() => {
    void refreshPaperState();
  }, [refreshPaperState]);

  return (
    <ModePanelView
      {...props}
      symbol="BTCUSDT"
      paperState={ownedPaperState}
      activeLimitOrders={
        ownedPaperState?.ok ? ownedPaperState.active_limit_orders : []
      }
      refreshPaperState={refreshPaperState}
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

  it("shows LIMITS N from authoritative active orders", () => {
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
        onPositionSideChange={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "LIMITS 1" })).toBeInTheDocument();
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
        onPositionSideChange={vi.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Cancel all Limit orders for BTCUSDT",
      }),
    );

    expect(
      screen.getByRole("dialog", {
        name: "Cancel all Limit orders for BTCUSDT?",
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

    await waitFor(() => expect(screen.getAllByDisplayValue("250")).toHaveLength(3));
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

    render(<ModePanel mode="TERMINAL" onModeChange={vi.fn()} sizingReferencePrice="64250" onPositionSideChange={vi.fn()} />);
    const buyAmount = await screen.findByLabelText("BUY amount");
    fireEvent.change(buyAmount, { target: { value: "300" } });
    fireEvent.click(screen.getByRole("button", { name: "BUY" }));

    expect(await screen.findByText("PAPER BUY completed")).toBeInTheDocument();
    expect(buyAmount).toHaveValue(300);
    await waitFor(() =>
      expect(screen.getByLabelText("SELL amount")).toHaveValue(260),
    );
    expect(document.querySelector(".paper-wv-position")).toHaveTextContent(
      "300USDT",
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

  it("submits backend-authoritative Full Close and refreshes zero exposure", async () => {
    let stateReads = 0;
    const fetchMock = vi.fn((url: string, _options?: RequestInit) => {
      if (url.startsWith("/api/paper-state")) {
        stateReads += 1;
        return Promise.resolve({
          ok: true,
          json: vi.fn().mockResolvedValue(paperState({
            engaged_wv: stateReads === 1 ? "1.2" : "0.0",
            engaged_notional_usdt: stateReads === 1 ? "300" : "0",
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
    await screen.findByText("300 USDT");
    fireEvent.click(screen.getByRole("button", { name: "Закрыть позицию" }));

    expect(await screen.findByText("PAPER позиция закрыта")).toBeInTheDocument();
    expect(screen.getByText("0 USDT")).toBeInTheDocument();
    expect(screen.getByText("⚔️ 0.0")).toBeInTheDocument();
    const [, options] = fetchMock.mock.calls.find(
      ([requestUrl]) => requestUrl === "/api/full-close",
    )!;
    expect(JSON.parse(options!.body as string)).toEqual({
      client_action_id: expect.stringMatching(/^paper-full-close-\d+$/),
      symbol: "BTCUSDT",
    });
  });

  it("creates and cancels an authoritative GTC PAPER limit", async () => {
    let active = false;
    let price = "64000";
    const fetchMock = vi.fn((url: string, options?: RequestInit) => {
      if (url.startsWith("/api/paper-state")) return Promise.resolve({
        ok: true,
        json: vi.fn().mockResolvedValue(paperState({
          active_limit_orders: active ? [{
            order_id: "paper-limit-1", order_link_id: "link-1", symbol: "BTCUSDT",
            side: "Buy", price, quantity: "0.005", time_in_force: "GTC",
          }] : [],
        })),
      });
      if (url === "/api/limit") active = true;
      if (url === "/api/limit/amend") {
        price = JSON.parse(options!.body as string).limit_price;
      }
      if (url === "/api/limit/cancel") active = false;
      return Promise.resolve({
        ok: true,
        json: vi.fn().mockResolvedValue({ status: "completed", reason_code: "completed" }),
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ModePanel mode="TERMINAL" onModeChange={vi.fn()} sizingReferencePrice="0.094" onPositionSideChange={vi.fn()} />);
    await screen.findAllByDisplayValue("250");
    fireEvent.change(screen.getByLabelText("LIMIT price"), { target: { value: "64000" } });
    fireEvent.change(screen.getByLabelText("LIMIT amount"), { target: { value: "321" } });
    fireEvent.click(screen.getByRole("button", { name: "Создать LIMIT" }));
    expect(await screen.findByText("Buy 0.005 @ 64000 GTC")).toBeInTheDocument();
    const createOptions = fetchMock.mock.calls.find(([url]) => url === "/api/limit")![1];
    expect(JSON.parse(createOptions!.body as string)).toMatchObject({
      side: "Buy", limit_price: "64000", time_in_force: "GTC",
      volume: { unit: "usdt", amount: "321" },
    });
    fireEvent.change(screen.getByLabelText("Новая цена paper-limit-1"), { target: { value: "64100" } });
    fireEvent.click(screen.getByRole("button", { name: "Изменить paper-limit-1" }));
    expect(await screen.findByText("Buy 0.005 @ 64100 GTC")).toBeInTheDocument();
    const amendOptions = fetchMock.mock.calls.find(([url]) => url === "/api/limit/amend")![1];
    expect(JSON.parse(amendOptions!.body as string)).toMatchObject({
      symbol: "BTCUSDT", order_id: "paper-limit-1", limit_price: "64100",
    });
    fireEvent.click(screen.getByRole("button", { name: "Отменить paper-limit-1" }));
    await waitFor(() => expect(screen.queryByText("Buy 0.005 @ 64100 GTC")).not.toBeInTheDocument());
  });

  it.each([["0", "321"], ["64000", "0"]])(
    "does not submit invalid LIMIT price %s amount %s", async (price, amount) => {
      const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: vi.fn().mockResolvedValue(paperState()) });
      vi.stubGlobal("fetch", fetchMock);
      render(<ModePanel mode="TERMINAL" onModeChange={vi.fn()} sizingReferencePrice="0.094" onPositionSideChange={vi.fn()} />);
      await screen.findAllByDisplayValue("250");
      fireEvent.change(screen.getByLabelText("LIMIT price"), { target: { value: price } });
      fireEvent.change(screen.getByLabelText("LIMIT amount"), { target: { value: amount } });
      fireEvent.click(screen.getByRole("button", { name: "Создать LIMIT" }));
      expect(fetchMock.mock.calls.some(([url]) => url === "/api/limit")).toBe(false);
    },
  );
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PaperState } from "../contracts/trading";
import { EMPTY_LIMIT_DRAFT_STATE } from "../orders/limitDraft";
import { ModePanel } from "./ModePanel";

afterEach(() => vi.unstubAllGlobals());

describe("ModePanel position PnL data flow", () => {
  const renderPosition = (
    positionSide: "Long" | "Short" | "Flat",
    averageEntry: string | null,
    sizingReferencePrice: string,
  ) => {
    const state: PaperState = {
      account_id: "paper",
      initial_deposit_usdt: "5000",
      equity_usdt: "5000",
      ok: true,
      symbol: "ONGUSDT",
      one_wv_usdt: "250",
      engaged_wv: positionSide === "Flat" ? "0" : "1",
      engaged_notional_usdt: positionSide === "Flat" ? "0" : "250",
      position_side: positionSide,
      position_quantity: positionSide === "Flat" ? "0" : "1576",
      average_entry: averageEntry,
      active_limit_orders: [],
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue(state),
    });
    vi.stubGlobal("fetch", fetchMock);
    const onAverageEntryChange = vi.fn();

    render(
      <ModePanel
        mode="TERMINAL"
        onModeChange={vi.fn()}
        symbol="ONGUSDT"
        paperState={state}
        activeLimitOrders={state.active_limit_orders}
        refreshPaperState={async () => {
          await fetch("/api/paper-state?symbol=ONGUSDT");
        }}
        sizingReferencePrice={sizingReferencePrice}
        authoritativeTickSize="0.00001"
        limitDraftState={EMPTY_LIMIT_DRAFT_STATE}
        dispatchLimitDraft={vi.fn()}
        onLimitDraftConfirm={vi.fn()}
        onPositionSideChange={vi.fn()}
        onPositionAverageEntryChange={onAverageEntryChange}
      />,
    );
    return { fetchMock, onAverageEntryChange };
  };

  it("renders LONG cross, authoritative position details, and live profit", async () => {
    const { fetchMock, onAverageEntryChange } = renderPosition("Long", "0.1586559", "0.16");

    expect(await screen.findByRole("button", { name: "Закрыть позицию" })).toBeInTheDocument();
    expect(screen.getByText("ONGUSDT")).toBeInTheDocument();
    expect(screen.getByText("0.15866")).toBeInTheDocument();
    expect(screen.getByText("+0.85%")).toHaveClass("positive");
    expect(onAverageEntryChange).toHaveBeenCalledWith(0.1586559);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("shows position quantity with the base asset derived from ONGUSDT", async () => {
    renderPosition("Long", "0.1586559", "0.16");
    await screen.findByText("ONGUSDT");
    fireEvent.pointerDown(document.querySelector(".paper-position-notional-hold")!);
    expect(await screen.findByRole("tooltip", {}, { timeout: 800 })).toHaveTextContent(
      "1576 ONG",
    );
    expect(screen.queryByText("1576 BTC")).toBeNull();
  });

  it("keeps trade, position, and protection controls in their structural groups", async () => {
    renderPosition("Long", "100", "101");
    await screen.findByText("ONGUSDT");

    const actions = screen.getByRole("button", { name: "BUY" }).closest(".paper-market-actions")!;
    const tradeGroup = screen.getByLabelText("PAPER trade sides");
    const positionGroup = screen.getByLabelText("PAPER position controls");
    const utilityGroup = screen.getByLabelText("PAPER utility controls");
    const protectionGroup = screen.getByRole("button", { name: "STOP" }).parentElement!;
    const workingVolume = screen.getByLabelText("Engaged working volume");
    const primaryPositionControls = workingVolume.querySelector(".paper-wv-primary")!;
    const close = screen.getByRole("button", { name: "Закрыть позицию" });
    const positionInfo = screen.getByLabelText("Current PAPER position");

    expect(tradeGroup).toContainElement(screen.getByRole("button", { name: "BUY" }));
    expect(tradeGroup).toContainElement(screen.getByRole("button", { name: "SELL" }));
    expect(positionGroup).toContainElement(workingVolume);
    expect(positionGroup).toContainElement(close);
    expect(positionGroup).toContainElement(positionInfo);
    expect(Array.from(primaryPositionControls.children)).toEqual([
      primaryPositionControls.querySelector(".paper-wv-value"),
      close,
    ]);
    expect(Array.from(positionGroup.children)).toEqual([workingVolume, positionInfo]);
    expect(utilityGroup).toContainElement(utilityGroup.querySelector(".paper-position-list-button"));
    expect(utilityGroup).toContainElement(utilityGroup.querySelector(".paper-autopilot-button"));
    expect(protectionGroup).toContainElement(screen.getByRole("button", { name: "STOP" }));
    expect(protectionGroup).toContainElement(screen.getByRole("button", { name: "TAKE" }));
    const groups = Array.from(actions.children);
    expect(groups.indexOf(tradeGroup)).toBeLessThan(groups.indexOf(positionGroup));
    expect(groups.indexOf(positionGroup)).toBeLessThan(groups.indexOf(utilityGroup));
    expect(groups.indexOf(utilityGroup)).toBeLessThan(groups.indexOf(protectionGroup));
    expect(Array.from(tradeGroup.children)).toEqual([
      screen.getByRole("button", { name: "BUY" }).parentElement,
      screen.getByRole("button", { name: "SELL" }).parentElement,
    ]);
  });

  it("renders SHORT loss with the shared PnL sign and formula", async () => {
    renderPosition("Short", "100", "101");

    expect(await screen.findByRole("button", { name: "Закрыть позицию" })).toBeInTheDocument();
    expect(screen.getByLabelText("Current PAPER position")).toBeInTheDocument();
    expect(screen.getByText("−1.00%")).toHaveClass("negative");
  });

  it("hides close and position info when PAPER is FLAT", async () => {
    renderPosition("Flat", null, "100");

    await screen.findByText("⚔️ 0.0");
    expect(screen.queryByRole("button", { name: "Закрыть позицию" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Current PAPER position")).not.toBeInTheDocument();
    expect(screen.getByLabelText("PAPER trade sides")).toContainElement(
      screen.getByRole("button", { name: "BUY" }),
    );
    expect(screen.getByLabelText("PAPER position controls")).toContainElement(
      screen.getByLabelText("Engaged working volume"),
    );
    expect(screen.getByLabelText("PAPER utility controls")).toContainElement(
      document.querySelector(".paper-autopilot-button"),
    );
    expect(screen.getByRole("button", { name: "STOP" }).parentElement).toContainElement(
      screen.getByRole("button", { name: "TAKE" }),
    );
  });

  it.each([null, "invalid", "0", "Infinity"])(
    "keeps symbol but omits invalid average entry and PnL: %s",
    async (averageEntry) => {
      renderPosition("Long", averageEntry, "101");

      expect(await screen.findByText("ONGUSDT")).toBeInTheDocument();
      expect(screen.queryByText(/NaN|Infinity/)).not.toBeInTheDocument();
      expect(screen.queryByText(/%/)).not.toBeInTheDocument();
    },
  );

  it("uses the relocated cross to call the existing full-close endpoint", async () => {
    const { fetchMock } = renderPosition("Long", "100", "101");
    await screen.findByText("ONGUSDT");

    fireEvent.click(screen.getByRole("button", { name: "Закрыть позицию" }));
    fireEvent.click(screen.getByRole("button", { name: "ЗАКРЫТЬ ПОЗИЦИЮ" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/full-close",
      expect.objectContaining({ method: "POST" }),
    ));
    expect(screen.getAllByRole("button", { name: "Закрыть позицию" })).toHaveLength(1);
  });
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EMPTY_LIMIT_DRAFT_STATE } from "../orders/limitDraft";
import { ModePanel } from "./ModePanel";

const projection = {
  ok: true as const, account_id: "bybit-main", provider: "BYBIT" as const,
  environment: "MAINNET", status: "READY", session_generation: 7,
  projection_generation: 2, read_only: false, wallet_balance_usdt: "100",
  total_equity_usdt: "100", available_balance_usdt: "100",
  capabilities: { market: true, limit: false, stop: false, take: false, full_close: false },
  positions: [], orders: [], paper_state: null,
};

function renderLive(onFastLimitHoldChange = vi.fn()) {
  render(<ModePanel mode="TERMINAL" onModeChange={vi.fn()} symbol="BTCUSDT"
    paperState={null} activeLimitOrders={[]} refreshPaperState={vi.fn()}
    sizingReferencePrice="50000" authoritativeTickSize="0.1"
    limitDraftState={EMPTY_LIMIT_DRAFT_STATE} dispatchLimitDraft={vi.fn()}
    onLimitDraftConfirm={vi.fn()} onPositionSideChange={vi.fn()}
    selectedVolumes={{ Buy: "10", Sell: "11" }} mutationsAllowed={false}
    liveMarketAllowed={true} accountWorkspaceProjection={projection}
    onFastLimitHoldChange={onFastLimitHoldChange} />);
}

describe("ModePanel LIVE MARKET capability", () => {
  it("single-flights a double confirmation tap with one client action", async () => {
    let release!: () => void;
    const response = new Promise<{ json: () => Promise<object> }>((resolve) => {
      release = () => resolve({ json: async () => ({
        status: "accepted_pending", reason_code: "accepted_pending",
        command_id: "cmd", order_link_id: "tw", reconciliation_required: false,
      }) });
    });
    const fetcher = vi.fn().mockReturnValue(response);
    vi.stubGlobal("fetch", fetcher);
    renderLive();
    fireEvent.click(screen.getByRole("button", { name: "BUY" }));
    const confirm = screen.getByRole("button", { name: "CONFIRM LIVE MARKET" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    const liveCalls = fetcher.mock.calls.filter((call) => call[0] === "/api/live/market");
    expect(liveCalls).toHaveLength(1);
    const body = JSON.parse(liveCalls[0][1].body);
    expect(new Set(liveCalls.map((call) => JSON.parse(call[1].body).client_action_id))).toEqual(
      new Set([body.client_action_id]),
    );
    expect(body.client_action_id).toEqual(expect.any(String));
    expect(screen.getByRole("button", { name: "LIVE MARKET SUBMITTING" })).toBeDisabled();
    release();
    await waitFor(() => expect(screen.queryByRole("dialog", {
      name: "Confirm LIVE Market order",
    })).not.toBeInTheDocument());
  });

  it("confirms explicit account/session action and keeps LIVE Limit disabled", async () => {
    const fetcher = vi.fn().mockResolvedValue({ json: async () => ({
      status: "accepted_pending", reason_code: "accepted_pending",
      command_id: "cmd", order_link_id: "tw", reconciliation_required: false,
    }) });
    vi.stubGlobal("fetch", fetcher);
    renderLive();
    fireEvent.click(screen.getByRole("button", { name: "BUY" }));
    const dialog = screen.getByRole("dialog", { name: "Confirm LIVE Market order" });
    expect(dialog).toHaveTextContent("Main Bybit / LIVE");
    expect(dialog).toHaveTextContent("BUY MARKET BTCUSDT");
    expect(screen.getByRole("button", { name: "BUY LIMITS 0" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "STOP" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "TAKE" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "CONFIRM LIVE MARKET" }));
    await waitFor(() => expect(fetcher.mock.calls.some((call) => call[0] === "/api/live/market")).toBe(true));
    const liveCall = fetcher.mock.calls.find((call) => call[0] === "/api/live/market")!;
    expect(fetcher.mock.calls.filter((call) => call[0] === "/api/live/market")).toHaveLength(1);
    const body = JSON.parse(liveCall[1].body);
    expect(body).toMatchObject({ account_id: "bybit-main", session_generation: 7 });
  });

  it("does not turn a LIVE BUY hold into fast Limit", () => {
    vi.useFakeTimers();
    const onFastLimitHoldChange = vi.fn();
    renderLive(onFastLimitHoldChange);
    fireEvent.pointerDown(screen.getByRole("button", { name: "BUY" }), {
      pointerId: 1, pointerType: "touch", button: 0,
    });
    vi.advanceTimersByTime(250);
    expect(onFastLimitHoldChange).not.toHaveBeenCalled();
    vi.useRealTimers();
  });
});

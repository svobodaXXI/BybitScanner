import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { PaperState } from "../contracts/trading";
import { executePaperStopCreate } from "../orders/paperStopCommand";
import { StopLine } from "./StopLine";

describe("StopLine", () => {
  it("renders draggable dashed draft with confirm and discard", () => {
    const onDragClientY = vi.fn();
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(<StopLine
      price="98" top={100} rightOffset={64} mode="CREATE"
      onDragClientY={onDragClientY} onConfirm={onConfirm} onCancel={onCancel}
    />);
    const line = screen.getByRole("slider", { name: "Pending STOP at 98" });
    Object.assign(line, {
      setPointerCapture: vi.fn(), hasPointerCapture: vi.fn(() => true),
      releasePointerCapture: vi.fn(),
    });
    fireEvent.pointerDown(line, { pointerId: 1 });
    fireEvent.pointerMove(line, { pointerId: 1, clientY: 120 });
    fireEvent.click(screen.getByRole("button", { name: "Confirm STOP" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel STOP draft" }));
    expect(line).toHaveClass("draft");
    expect(onDragClientY).toHaveBeenCalledWith(120);
    expect(onConfirm).toHaveBeenCalledOnce();
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("renders solid authoritative line with edit and delete controls", () => {
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    render(<StopLine
      price="98" top={100} rightOffset={64} mode="ACTIVE"
      onEdit={onEdit} onDelete={onDelete}
    />);
    const line = screen.getByLabelText("Active STOP at 98");
    expect(line).toHaveClass("active");
    fireEvent.click(screen.getByRole("button", { name: "Edit STOP" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete STOP" }));
    expect(onEdit).toHaveBeenCalledOnce();
    expect(onDelete).toHaveBeenCalledOnce();
  });

  it("sends one STOP create on touch pointerup plus detail-zero compatibility click without drag", async () => {
    const paperState = {
      ok: true, state_revision: 2, account_id: "paper", symbol: "BTCUSDT",
      initial_deposit_usdt: "5000", equity_usdt: "5000", one_wv_usdt: "250",
      position_side: "Long", position_quantity: "2", average_entry: "100",
      engaged_notional_usdt: "200", engaged_wv: "1", active_limit_orders: [],
      protection: {
        status: "confirmed_active", take_profit: null, stop_loss: "98",
        trailing_stop: null, pending_command_id: null, warning: null,
        effective_quantity: "2",
      },
    } satisfies PaperState;
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        client_action_id: "touch-stop", status: "completed", reason_code: "created",
        paper_state: paperState,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const onConfirm = vi.fn(() => executePaperStopCreate({
      client_action_id: "touch-stop", symbol: "BTCUSDT", trigger_price: "98",
    }, { applyPaperState: () => true }));
    const onDragClientY = vi.fn();
    render(<StopLine
      price="98" top={100} rightOffset={64} mode="CREATE"
      onConfirm={onConfirm} onDragClientY={onDragClientY}
    />);
    const confirm = screen.getByRole("button", { name: "Confirm STOP" });
    fireEvent.pointerDown(confirm, {
      button: 0, pointerId: 9, pointerType: "touch", clientY: 100,
    });
    fireEvent.pointerMove(confirm, {
      pointerId: 9, pointerType: "touch", clientY: 112,
    });
    fireEvent.pointerUp(confirm, {
      pointerId: 9, pointerType: "touch", clientY: 112,
    });
    fireEvent.click(confirm, { detail: 0 });
    expect(onConfirm).toHaveBeenCalledOnce();
    expect(onDragClientY).not.toHaveBeenCalled();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    expect(fetchMock).toHaveBeenCalledWith("/api/stop", expect.objectContaining({
      method: "POST",
    }));
    vi.unstubAllGlobals();
  });

  it("parameterizes the same lifecycle as a turquoise TAKE line", () => {
    render(<StopLine leg="TAKE" price="103" top={80} rightOffset={64} mode="CREATE" />);
    const line = screen.getByRole("slider", { name: "Pending TAKE at 103" });
    expect(line).toHaveClass("take", "draft");
    expect(screen.getByRole("button", { name: "Confirm TAKE" })).toBeInTheDocument();
  });
});

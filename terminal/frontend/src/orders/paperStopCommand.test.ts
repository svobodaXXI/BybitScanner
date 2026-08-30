import { describe, expect, it, vi } from "vitest";
import type { PaperState, PaperStopMutationResponse } from "../contracts/trading";
import {
  executePaperStopAmend,
  executePaperStopCreate,
  executePaperStopDelete,
  executePaperTakeAmend,
  executePaperTakeCreate,
  executePaperTakeDelete,
} from "./paperStopCommand";

const paperState = (stop: string | null): PaperState => ({
  ok: true, state_revision: 2, account_id: "paper", symbol: "BTCUSDT",
  initial_deposit_usdt: "5000", equity_usdt: "5000", one_wv_usdt: "250",
  position_side: "Long", position_quantity: "2", average_entry: "100",
  engaged_notional_usdt: "200", engaged_wv: "1", active_limit_orders: [],
  protection: {
    status: stop === null ? "no_protection_configured" : "confirmed_active",
    take_profit: null, stop_loss: stop, trailing_stop: null,
    pending_command_id: null, warning: null, effective_quantity: stop ? "2" : null,
  },
});

describe("PAPER TAKE commands", () => {
  it("reuses authoritative create, amend and delete mutation flow", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => response("98") });
    vi.stubGlobal("fetch", fetchMock);
    const applyPaperState = vi.fn(() => true);
    const request = { client_action_id: "take", symbol: "BTCUSDT", trigger_price: "103" };
    await executePaperTakeCreate(request, { applyPaperState });
    await executePaperTakeAmend(request, { applyPaperState });
    await executePaperTakeDelete({ client_action_id: "delete-take", symbol: "BTCUSDT" }, { applyPaperState });
    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
      "/api/take", "/api/take/amend", "/api/take/delete",
    ]);
    expect(applyPaperState).toHaveBeenCalledTimes(3);
    vi.unstubAllGlobals();
  });
});

const response = (stop: string | null): PaperStopMutationResponse => ({
  client_action_id: "action", status: "completed", reason_code: "ok",
  paper_state: paperState(stop),
});

describe("PAPER STOP commands", () => {
  it("routes create and amend and applies only their authoritative resulting state", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => response("98") })
      .mockResolvedValueOnce({ ok: true, json: async () => response("97") });
    vi.stubGlobal("fetch", fetchMock);
    const applyPaperState = vi.fn(() => true);
    const request = { client_action_id: "action", symbol: "BTCUSDT", trigger_price: "98" };

    await executePaperStopCreate(request, { applyPaperState });
    await executePaperStopAmend({ ...request, trigger_price: "97" }, { applyPaperState });

    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual(["/api/stop", "/api/stop/amend"]);
    expect(applyPaperState).toHaveBeenNthCalledWith(1, paperState("98"));
    expect(applyPaperState).toHaveBeenNthCalledWith(2, paperState("97"));
    vi.unstubAllGlobals();
  });

  it("keeps authoritative STOP until delete response confirms absence", async () => {
    let resolve!: (value: unknown) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise((next) => { resolve = next; })));
    const applyPaperState = vi.fn(() => true);
    const pending = executePaperStopDelete(
      { client_action_id: "delete", symbol: "BTCUSDT" }, { applyPaperState },
    );
    expect(applyPaperState).not.toHaveBeenCalled();
    resolve({ ok: true, json: async () => response(null) });
    await pending;
    expect(applyPaperState).toHaveBeenCalledWith(paperState(null));
    vi.unstubAllGlobals();
  });
});

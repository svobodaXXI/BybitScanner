import { describe, expect, it, vi } from "vitest";
import type { PaperState, PaperStopMutationResponse } from "../contracts/trading";
import { PaperProtectionMutationController } from "./paperProtectionMutationSubmission";

const paperState = (): PaperState => ({
  ok: true,
  state_revision: 3,
  account_id: "paper",
  symbol: "BTCUSDT",
  initial_deposit_usdt: "5000",
  equity_usdt: "5000",
  one_wv_usdt: "250",
  position_side: "Long",
  position_quantity: "2",
  average_entry: "100",
  engaged_notional_usdt: "200",
  engaged_wv: "1",
  active_limit_orders: [],
  protection: {
    status: "confirmed_active",
    take_profit: null,
    stop_loss: "98",
    trailing_stop: null,
    pending_command_id: null,
    warning: null,
    effective_quantity: "2",
  },
});

const response = (): PaperStopMutationResponse => ({
  client_action_id: "first-id",
  status: "completed",
  reason_code: "ok",
  paper_state: paperState(),
});

describe("PaperProtectionMutationController", () => {
  it("allocates one durable id and one runMutation for a duplicated semantic attempt", async () => {
    const controller = new PaperProtectionMutationController();
    let resolve!: (value: PaperStopMutationResponse) => void;
    const fetchMock = vi.fn<typeof fetch>(() => new Promise((next) => {
      resolve = (value) => next({
        ok: true,
        json: async () => value,
      } as Response);
    }));
    vi.stubGlobal("fetch", fetchMock);

    const createClientActionId = vi.fn()
      .mockReturnValueOnce("first-id")
      .mockReturnValueOnce("second-id");
    const runMutation = vi.fn(async <T>(_key: string, mutation: () => Promise<T>) => mutation());
    const applyPaperState = vi.fn(() => true);
    const input = {
      leg: "STOP" as const,
      operation: "CREATE" as const,
      symbol: "BTCUSDT",
      triggerPrice: "98",
    };

    const first = controller.submit(input, {
      createClientActionId,
      applyPaperState,
      runMutation,
    });
    const duplicate = controller.submit(input, {
      createClientActionId,
      applyPaperState,
      runMutation,
    });

    expect(duplicate).toBe(first);
    expect(createClientActionId).toHaveBeenCalledTimes(1);
    expect(runMutation).toHaveBeenCalledTimes(1);
    expect(runMutation.mock.calls[0][0]).toBe("CREATE_STOP:first-id");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    resolve(response());
    await expect(first).resolves.toEqual(response());
    vi.unstubAllGlobals();
  });

  it("separates STOP and TAKE semantic ownership", async () => {
    const controller = new PaperProtectionMutationController();
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue({
      ok: true,
      json: async () => response(),
    } as Response);
    vi.stubGlobal("fetch", fetchMock);
    const createClientActionId = vi.fn()
      .mockReturnValueOnce("stop-id")
      .mockReturnValueOnce("take-id");
    const runMutation = vi.fn(async <T>(_key: string, mutation: () => Promise<T>) => mutation());
    const applyPaperState = vi.fn(() => true);

    await Promise.all([
      controller.submit({
        leg: "STOP", operation: "CREATE", symbol: "BTCUSDT", triggerPrice: "98",
      }, { createClientActionId, applyPaperState, runMutation }),
      controller.submit({
        leg: "TAKE", operation: "CREATE", symbol: "BTCUSDT", triggerPrice: "103",
      }, { createClientActionId, applyPaperState, runMutation }),
    ]);

    expect(createClientActionId).toHaveBeenCalledTimes(2);
    expect(runMutation).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    vi.unstubAllGlobals();
  });

  it("clear lets a replacement semantic attempt own the same key", async () => {
    const controller = new PaperProtectionMutationController();
    let resolveFirst!: (value: PaperStopMutationResponse) => void;
    const fetchMock = vi.fn<typeof fetch>()
      .mockImplementationOnce(() => new Promise((next) => {
        resolveFirst = (value) => next({ ok: true, json: async () => value } as Response);
      }))
      .mockResolvedValueOnce({ ok: true, json: async () => response() } as Response);
    vi.stubGlobal("fetch", fetchMock);
    const createClientActionId = vi.fn()
      .mockReturnValueOnce("first-id")
      .mockReturnValueOnce("replacement-id");
    const runMutation = vi.fn(async <T>(_key: string, mutation: () => Promise<T>) => mutation());
    const applyPaperState = vi.fn(() => true);
    const input = {
      leg: "STOP" as const,
      operation: "DELETE" as const,
      symbol: "BTCUSDT",
    };

    const first = controller.submit(input, { createClientActionId, applyPaperState, runMutation });
    controller.clear();
    const replacement = controller.submit(input, { createClientActionId, applyPaperState, runMutation });

    await expect(replacement).resolves.toEqual(response());
    resolveFirst(response());
    await expect(first).resolves.toEqual(response());
    expect(fetchMock).toHaveBeenCalledTimes(2);
    vi.unstubAllGlobals();
  });
});

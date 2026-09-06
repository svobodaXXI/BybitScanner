import { describe, expect, it, vi } from "vitest";
import { LiveProtectionMutationController } from "./liveProtectionMutationSubmission";

const authority = { accountId: "bybit-main", sessionGeneration: 7 };

function accepted(commandId = "command-1") {
  return new Response(JSON.stringify({
    status: "accepted_pending",
    reason_code: "accepted_pending",
    command_id: commandId,
    reconciliation_required: false,
  }));
}

describe("LiveProtectionMutationController", () => {
  it("single-flights duplicate semantic attempts with one durable client action id", async () => {
    const controller = new LiveProtectionMutationController();
    let resolveFetch!: (value: Response) => void;
    const fetcher = vi.fn<typeof fetch>(() => new Promise<Response>((resolve) => { resolveFetch = resolve; }));
    const createClientActionId = vi.fn(() => "action-1");
    const refreshActiveLive = vi.fn(async () => undefined);
    const dependencies = {
      currentAuthority: () => authority,
      createClientActionId,
      refreshActiveLive,
      fetcher,
    };
    const intent = {
      leg: "STOP" as const,
      operation: "CREATE" as const,
      symbol: "BTCUSDT",
      triggerPrice: "62000",
      currentStopLoss: null,
      currentTakeProfit: "65000",
    };

    const first = controller.submit(intent, dependencies);
    const second = controller.submit(intent, dependencies);

    expect(first).toBe(second);
    expect(createClientActionId).toHaveBeenCalledTimes(1);
    expect(fetcher).toHaveBeenCalledTimes(1);
    resolveFetch(accepted());
    await expect(first).resolves.toMatchObject({ status: "accepted_pending" });
    expect(refreshActiveLive).toHaveBeenCalledTimes(1);
  });

  it("preserves the opposite protection leg and clears only the deleted leg", async () => {
    const controller = new LiveProtectionMutationController();
    const fetcher = vi.fn<typeof fetch>(async () => accepted());

    await controller.submit({
      leg: "TAKE",
      operation: "DELETE",
      symbol: "BTCUSDT",
      currentStopLoss: "62000",
      currentTakeProfit: "65000",
    }, {
      currentAuthority: () => authority,
      createClientActionId: () => "action-2",
      refreshActiveLive: async () => undefined,
      fetcher,
    });

    const [url, options] = fetcher.mock.calls[0];
    expect(url).toBe("/api/live/take/delete");
    expect(JSON.parse(options!.body as string)).toEqual({
      client_action_id: "action-2",
      account_id: "bybit-main",
      session_generation: 7,
      symbol: "BTCUSDT",
      take_profit: null,
      stop_loss: "62000",
      tp_trigger_by: "MarkPrice",
      sl_trigger_by: "MarkPrice",
    });
  });

  it("retains UNKNOWN ownership until authority reconciliation clears it", async () => {
    const controller = new LiveProtectionMutationController();
    const fetcher = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({
      status: "unknown",
      reason_code: "mutation_unknown",
      command_id: "command-unknown",
      reconciliation_required: true,
    })));
    const createClientActionId = vi
      .fn()
      .mockReturnValueOnce("action-1")
      .mockReturnValueOnce("action-2");
    const dependencies = {
      currentAuthority: () => authority,
      createClientActionId,
      refreshActiveLive: async () => undefined,
      fetcher,
    };
    const intent = {
      leg: "STOP" as const,
      operation: "AMEND" as const,
      symbol: "BTCUSDT",
      triggerPrice: "62100",
      currentStopLoss: "62000",
      currentTakeProfit: "65000",
    };

    const first = await controller.submit(intent, dependencies);
    const second = await controller.submit(intent, dependencies);

    expect(first).toMatchObject({ status: "unknown", reconciliation_required: true });
    expect(second).toBe(first);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(createClientActionId).toHaveBeenCalledTimes(1);

    controller.clear();
    await controller.submit(intent, dependencies);
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(createClientActionId).toHaveBeenCalledTimes(2);
  });

  it("fails before allocation or dispatch when LIVE authority is unavailable", () => {
    const controller = new LiveProtectionMutationController();
    const createClientActionId = vi.fn(() => "action-1");
    const fetcher = vi.fn<typeof fetch>();

    expect(() => controller.submit({
      leg: "STOP",
      operation: "CREATE",
      symbol: "BTCUSDT",
      triggerPrice: "62000",
      currentStopLoss: null,
      currentTakeProfit: null,
    }, {
      currentAuthority: () => null,
      createClientActionId,
      refreshActiveLive: async () => undefined,
      fetcher,
    })).toThrow("stale_live_authority");

    expect(createClientActionId).not.toHaveBeenCalled();
    expect(fetcher).not.toHaveBeenCalled();
  });
});

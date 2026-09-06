import { describe, expect, it, vi } from "vitest";
import { LimitOrderMutationController } from "./limitOrderMutation";

describe("LimitOrderMutationController", () => {
  it("deduplicates the same operation/order attempt and preserves client identity", async () => {
    let resolveAttempt!: (value: { status: string }) => void;
    const promise = new Promise<{ status: string }>((resolve) => {
      resolveAttempt = resolve;
    });
    const startAttempt = vi.fn(() => ({ clientActionId: "stable-action", promise }));
    const controller = new LimitOrderMutationController<{ status: string }>();

    const first = controller.submit("AMEND_LIMIT", "order-1", {
      startAttempt,
      classifyResult: () => "release",
      classifyError: () => "retain",
    });
    const second = controller.submit("AMEND_LIMIT", "order-1", {
      startAttempt,
      classifyResult: () => "release",
      classifyError: () => "retain",
    });

    expect(second).toBe(first);
    expect(second.clientActionId).toBe("stable-action");
    expect(startAttempt).toHaveBeenCalledTimes(1);

    resolveAttempt({ status: "completed" });
    await first.promise;
  });

  it("keeps AMEND and CANCEL ownership independent for the same order", async () => {
    const startAmend = vi.fn(() => ({
      clientActionId: "amend-action",
      promise: Promise.resolve({ status: "completed" }),
    }));
    const startCancel = vi.fn(() => ({
      clientActionId: "cancel-action",
      promise: Promise.resolve({ status: "completed" }),
    }));
    const controller = new LimitOrderMutationController<{ status: string }>();

    const amend = controller.submit("AMEND_LIMIT", "order-1", {
      startAttempt: startAmend,
      classifyResult: () => "release",
      classifyError: () => "retain",
    });
    const cancel = controller.submit("CANCEL_LIMIT", "order-1", {
      startAttempt: startCancel,
      classifyResult: () => "release",
      classifyError: () => "retain",
    });

    expect(amend).not.toBe(cancel);
    expect(startAmend).toHaveBeenCalledTimes(1);
    expect(startCancel).toHaveBeenCalledTimes(1);
    await Promise.all([amend.promise, cancel.promise]);
  });

  it("releases a definitive attempt so a later user action may start a new command", async () => {
    const startAttempt = vi
      .fn()
      .mockImplementationOnce(() => ({
        clientActionId: "first-action",
        promise: Promise.resolve({ status: "completed" }),
      }))
      .mockImplementationOnce(() => ({
        clientActionId: "second-action",
        promise: Promise.resolve({ status: "completed" }),
      }));
    const controller = new LimitOrderMutationController<{ status: string }>();
    const dependencies = {
      startAttempt,
      classifyResult: () => "release" as const,
      classifyError: () => "retain" as const,
    };

    const first = controller.submit("CANCEL_LIMIT", "order-1", dependencies);
    await first.promise;
    const second = controller.submit("CANCEL_LIMIT", "order-1", dependencies);

    expect(second.clientActionId).toBe("second-action");
    expect(startAttempt).toHaveBeenCalledTimes(2);
    await second.promise;
  });

  it("retains an ambiguous resolved outcome and prevents blind redispatch", async () => {
    const startAttempt = vi.fn(() => ({
      clientActionId: "ambiguous-action",
      promise: Promise.resolve({ status: "unknown" }),
    }));
    const controller = new LimitOrderMutationController<{ status: string }>();
    const dependencies = {
      startAttempt,
      classifyResult: () => "retain" as const,
      classifyError: () => "retain" as const,
    };

    const first = controller.submit("AMEND_LIMIT", "order-1", dependencies);
    await first.promise;
    const second = controller.submit("AMEND_LIMIT", "order-1", dependencies);

    expect(second).toBe(first);
    expect(startAttempt).toHaveBeenCalledTimes(1);
  });

  it("retains a transport failure when the provider classifies it as ambiguous", async () => {
    const transportError = new Error("network timeout");
    const startAttempt = vi.fn(() => ({
      clientActionId: "ambiguous-action",
      promise: Promise.reject(transportError),
    }));
    const controller = new LimitOrderMutationController<never>();
    const dependencies = {
      startAttempt,
      classifyResult: () => "release" as const,
      classifyError: () => "retain" as const,
    };

    const first = controller.submit("CANCEL_LIMIT", "order-1", dependencies);
    await expect(first.promise).rejects.toBe(transportError);
    const second = controller.submit("CANCEL_LIMIT", "order-1", dependencies);

    expect(second).toBe(first);
    expect(startAttempt).toHaveBeenCalledTimes(1);
  });

  it("does not latch a synchronous provider preflight failure", () => {
    const startAttempt = vi.fn(() => {
      throw new Error("stale authority");
    });
    const controller = new LimitOrderMutationController<never>();
    const dependencies = {
      startAttempt,
      classifyResult: () => "release" as const,
      classifyError: () => "retain" as const,
    };

    expect(() => controller.submit("AMEND_LIMIT", "order-1", dependencies)).toThrow(
      "stale authority",
    );
    expect(() => controller.submit("AMEND_LIMIT", "order-1", dependencies)).toThrow(
      "stale authority",
    );
    expect(startAttempt).toHaveBeenCalledTimes(2);
  });
});

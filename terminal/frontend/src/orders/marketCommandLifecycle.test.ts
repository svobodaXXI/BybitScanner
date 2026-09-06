import { describe, expect, it, vi } from "vitest";
import { MarketCommandLifecycleController } from "./marketCommandLifecycle";

describe("MarketCommandLifecycleController", () => {
  it("reuses one in-flight attempt for the same client_action_id", async () => {
    let resolveAttempt!: (value: string) => void;
    const startAttempt = vi.fn(() => new Promise<string>((resolve) => {
      resolveAttempt = resolve;
    }));
    const controller = new MarketCommandLifecycleController<string>();

    const first = controller.submit("action-1", {
      startAttempt,
      classifyResult: () => "release",
      releaseOnError: true,
    });
    const duplicate = controller.submit("action-1", {
      startAttempt,
      classifyResult: () => "release",
      releaseOnError: true,
    });

    expect(duplicate).toBe(first);
    expect(startAttempt).toHaveBeenCalledTimes(1);

    resolveAttempt("completed");
    await expect(first).resolves.toBe("completed");
  });

  it("retains ambiguous ownership and prevents blind redispatch", async () => {
    const startAttempt = vi.fn().mockResolvedValue("unknown");
    const controller = new MarketCommandLifecycleController<string>();

    const first = controller.submit("action-2", {
      startAttempt,
      classifyResult: () => "retain",
      releaseOnError: false,
    });
    await expect(first).resolves.toBe("unknown");

    const duplicate = controller.submit("action-2", {
      startAttempt,
      classifyResult: () => "release",
      releaseOnError: true,
    });

    expect(duplicate).toBe(first);
    expect(startAttempt).toHaveBeenCalledTimes(1);
  });

  it("does not let a late cleared attempt release replacement ownership", async () => {
    let resolveOld!: (value: string) => void;
    let resolveNew!: (value: string) => void;
    const controller = new MarketCommandLifecycleController<string>();

    const oldAttempt = controller.submit("action-3", {
      startAttempt: () => new Promise<string>((resolve) => { resolveOld = resolve; }),
      classifyResult: () => "release",
      releaseOnError: true,
    });

    controller.clear();

    const newStart = vi.fn(() => new Promise<string>((resolve) => { resolveNew = resolve; }));
    const replacement = controller.submit("action-3", {
      startAttempt: newStart,
      classifyResult: () => "retain",
      releaseOnError: false,
    });

    resolveOld("completed");
    await expect(oldAttempt).resolves.toBe("completed");

    const duplicate = controller.submit("action-3", {
      startAttempt: newStart,
      classifyResult: () => "release",
      releaseOnError: true,
    });
    expect(duplicate).toBe(replacement);
    expect(newStart).toHaveBeenCalledTimes(1);

    resolveNew("unknown");
    await expect(replacement).resolves.toBe("unknown");
  });
});

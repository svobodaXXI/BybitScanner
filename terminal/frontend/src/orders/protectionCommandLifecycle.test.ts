import { describe, expect, it, vi } from "vitest";
import { ProtectionCommandLifecycleController } from "./protectionCommandLifecycle";

describe("ProtectionCommandLifecycleController", () => {
  it("reuses one in-flight semantic attempt", async () => {
    let resolveAttempt!: (value: string) => void;
    const startAttempt = vi.fn(() => new Promise<string>((resolve) => {
      resolveAttempt = resolve;
    }));
    const controller = new ProtectionCommandLifecycleController<string>();

    const first = controller.submit("STOP:CREATE:BTCUSDT:98", {
      startAttempt,
      classifyResult: () => "release",
      releaseOnError: true,
    });
    const duplicate = controller.submit("STOP:CREATE:BTCUSDT:98", {
      startAttempt,
      classifyResult: () => "release",
      releaseOnError: true,
    });

    expect(duplicate).toBe(first);
    expect(startAttempt).toHaveBeenCalledTimes(1);

    resolveAttempt("completed");
    await expect(first).resolves.toBe("completed");
  });

  it("retains ambiguous ownership and prevents redispatch", async () => {
    const startAttempt = vi.fn().mockResolvedValue("unknown");
    const controller = new ProtectionCommandLifecycleController<string>();

    const first = controller.submit("TAKE:EDIT:BTCUSDT:103", {
      startAttempt,
      classifyResult: () => "retain",
      releaseOnError: false,
    });
    await expect(first).resolves.toBe("unknown");

    const duplicate = controller.submit("TAKE:EDIT:BTCUSDT:103", {
      startAttempt,
      classifyResult: () => "release",
      releaseOnError: true,
    });

    expect(duplicate).toBe(first);
    expect(startAttempt).toHaveBeenCalledTimes(1);
  });

  it("does not let late completion release replacement ownership after clear", async () => {
    let resolveOld!: (value: string) => void;
    let resolveNew!: (value: string) => void;
    const controller = new ProtectionCommandLifecycleController<string>();

    const oldAttempt = controller.submit("STOP:DELETE:BTCUSDT", {
      startAttempt: () => new Promise<string>((resolve) => { resolveOld = resolve; }),
      classifyResult: () => "release",
      releaseOnError: true,
    });

    controller.clear();

    const newStart = vi.fn(() => new Promise<string>((resolve) => { resolveNew = resolve; }));
    const replacement = controller.submit("STOP:DELETE:BTCUSDT", {
      startAttempt: newStart,
      classifyResult: () => "retain",
      releaseOnError: false,
    });

    resolveOld("completed");
    await expect(oldAttempt).resolves.toBe("completed");

    const duplicate = controller.submit("STOP:DELETE:BTCUSDT", {
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

import { describe, expect, it } from "vitest";
import { FullCloseCommandLifecycleController } from "./fullCloseCommandLifecycle";

describe("FullCloseCommandLifecycleController", () => {
  it("reuses the first owned attempt for the same semantic key", async () => {
    const controller = new FullCloseCommandLifecycleController<string>();
    let starts = 0;
    let resolve!: (value: string) => void;
    const deferred = new Promise<string>((done) => { resolve = done; });

    const first = controller.submit("FULL_CLOSE:BTCUSDT", {
      startAttempt: () => {
        starts += 1;
        return deferred;
      },
      classifyResult: () => "release",
      releaseOnError: true,
    });
    const duplicate = controller.submit("FULL_CLOSE:BTCUSDT", {
      startAttempt: () => {
        starts += 1;
        return Promise.resolve("duplicate");
      },
      classifyResult: () => "release",
      releaseOnError: true,
    });

    expect(duplicate).toBe(first);
    expect(starts).toBe(1);
    resolve("done");
    await expect(first).resolves.toBe("done");
  });

  it("releases completed attempts so a later close can start", async () => {
    const controller = new FullCloseCommandLifecycleController<string>();
    let starts = 0;
    const dependencies = {
      startAttempt: async () => `done-${++starts}`,
      classifyResult: () => "release" as const,
      releaseOnError: true,
    };

    await expect(controller.submit("FULL_CLOSE:BTCUSDT", dependencies)).resolves.toBe("done-1");
    await expect(controller.submit("FULL_CLOSE:BTCUSDT", dependencies)).resolves.toBe("done-2");
    expect(starts).toBe(2);
  });

  it("keeps replacement ownership when an old attempt completes after clear", async () => {
    const controller = new FullCloseCommandLifecycleController<string>();
    let resolveOld!: (value: string) => void;
    let resolveNew!: (value: string) => void;
    const oldDeferred = new Promise<string>((done) => { resolveOld = done; });
    const newDeferred = new Promise<string>((done) => { resolveNew = done; });

    const oldAttempt = controller.submit("FULL_CLOSE:BTCUSDT", {
      startAttempt: () => oldDeferred,
      classifyResult: () => "release",
      releaseOnError: true,
    });
    controller.clear();
    const replacement = controller.submit("FULL_CLOSE:BTCUSDT", {
      startAttempt: () => newDeferred,
      classifyResult: () => "release",
      releaseOnError: true,
    });

    resolveOld("old");
    await expect(oldAttempt).resolves.toBe("old");

    const duplicate = controller.submit("FULL_CLOSE:BTCUSDT", {
      startAttempt: () => Promise.resolve("wrong"),
      classifyResult: () => "release",
      releaseOnError: true,
    });
    expect(duplicate).toBe(replacement);

    resolveNew("new");
    await expect(replacement).resolves.toBe("new");
  });
});

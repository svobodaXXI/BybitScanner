import { describe, expect, it, vi } from "vitest";
import { createFrameBatcher } from "./frameBatcher";

describe("chart imperative frame batching", () => {
  it("applies only the latest pointer update once per animation frame", () => {
    const frames: FrameRequestCallback[] = [];
    const request = vi.fn((callback: FrameRequestCallback) => {
      frames.push(callback);
      return 1;
    });
    const first = vi.fn();
    const latest = vi.fn();
    const batcher = createFrameBatcher(request, vi.fn());
    batcher.schedule(first);
    batcher.schedule(latest);
    expect(request).toHaveBeenCalledOnce();
    frames[0](0);
    expect(first).not.toHaveBeenCalled();
    expect(latest).toHaveBeenCalledOnce();
  });
});

export function createFrameBatcher(
  requestFrame: (callback: FrameRequestCallback) => number,
  cancelFrame: (handle: number) => void,
) {
  let handle: number | null = null;
  let pending: (() => void) | null = null;
  return {
    schedule(callback: () => void) {
      pending = callback;
      if (handle !== null) return;
      handle = requestFrame(() => {
        handle = null;
        const next = pending;
        pending = null;
        next?.();
      });
    },
    cancel() {
      if (handle !== null) cancelFrame(handle);
      handle = null;
      pending = null;
    },
  };
}

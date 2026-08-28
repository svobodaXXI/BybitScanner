import { useEffect, useSyncExternalStore } from "react";
import type { PaperState } from "../contracts/trading";
import { marketApiRoutes } from "../marketData/apiRoutes";

const PAPER_STATE_REQUEST_TIMEOUT_MS = 5_000;

type PaperTradingSnapshot = {
  paperState: PaperState | null;
  pendingActions: ReadonlySet<string>;
};

export class PaperTradingStore {
  private symbol: string | null = null;
  private snapshot: PaperTradingSnapshot = {
    paperState: null,
    pendingActions: new Set(),
  };
  private readonly listeners = new Set<() => void>();
  private readonly mutations = new Map<string, Promise<unknown>>();
  private refreshPromise: Promise<void> | null = null;
  private refreshPending = false;

  getSnapshot = () => this.snapshot;

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  setSymbol = (symbol: string) => {
    if (this.symbol === symbol) return;
    this.symbol = symbol;
    this.refreshPending = this.refreshPromise !== null;
    this.snapshot = { ...this.snapshot, paperState: null };
    this.emit();
  };

  applyPaperState = (state: PaperState) => {
    if (!state.ok || state.symbol !== this.symbol) return false;
    const currentRevision = this.snapshot.paperState?.state_revision ?? -1;
    if (state.state_revision < currentRevision) return false;
    this.snapshot = { ...this.snapshot, paperState: state };
    this.emit();
    return true;
  };

  refresh = () => {
    if (this.refreshPromise) {
      this.refreshPending = true;
      return this.refreshPromise;
    }
    this.refreshPromise = this.runRefreshLoop().finally(() => {
      this.refreshPromise = null;
    });
    return this.refreshPromise;
  };

  runMutation = <T,>(key: string, operation: () => Promise<T>): Promise<T> => {
    const existing = this.mutations.get(key);
    if (existing) return existing as Promise<T>;

    const promise = Promise.resolve().then(operation).finally(() => {
      if (this.mutations.get(key) !== promise) return;
      this.mutations.delete(key);
      this.publishPendingActions();
    });
    this.mutations.set(key, promise);
    this.publishPendingActions();
    return promise;
  };

  private async runRefreshLoop() {
    do {
      this.refreshPending = false;
      const symbol = this.symbol;
      if (!symbol) return;
      const controller = new AbortController();
      const timeout = globalThis.setTimeout(
        () => controller.abort(),
        PAPER_STATE_REQUEST_TIMEOUT_MS,
      );
      try {
        const response = await fetch(marketApiRoutes.paperState(symbol), {
          signal: controller.signal,
        });
        if (response.ok) {
          this.applyPaperState((await response.json()) as PaperState);
        }
      } catch {
        // Preserve the last authoritative state; polling will reconcile later.
      } finally {
        globalThis.clearTimeout(timeout);
      }
    } while (this.refreshPending);
  }

  private publishPendingActions() {
    this.snapshot = {
      ...this.snapshot,
      pendingActions: new Set(this.mutations.keys()),
    };
    this.emit();
  }

  private emit() {
    for (const listener of this.listeners) listener();
  }
}

export const paperTradingStore = new PaperTradingStore();

export function usePaperTrading(symbol: string) {
  const snapshot = useSyncExternalStore(
    paperTradingStore.subscribe,
    paperTradingStore.getSnapshot,
  );

  useEffect(() => {
    paperTradingStore.setSymbol(symbol);
  }, [symbol]);

  return snapshot;
}

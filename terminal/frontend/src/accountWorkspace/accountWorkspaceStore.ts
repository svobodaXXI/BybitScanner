import { useEffect, useSyncExternalStore } from "react";
import { marketApiRoutes } from "../marketData/apiRoutes";

export type AccountWorkspaceProjection = {
  ok: true;
  account_id: string;
  provider: "PAPER" | "BYBIT";
  environment: string;
  status: string;
  session_generation: number;
  projection_generation: number;
  read_only: boolean;
  capabilities?: {
    market: boolean;
    limit: boolean;
    stop: boolean;
    take: boolean;
    full_close: boolean;
  };
  wallet_balance_usdt: string;
  total_equity_usdt: string;
  available_balance_usdt: string;
  balance_source_fields?: {
    wallet_balance_usdt: string;
    total_equity_usdt: string;
    available_balance_usdt: string;
    account_type: "UNIFIED";
    unit: "USD";
  };
  balance_provenance?: Record<string, string | null>;
  positions: Array<Record<string, unknown>>;
  orders: Array<Record<string, unknown>>;
  paper_state: Record<string, unknown> | null;
};

type Snapshot = {
  projection: AccountWorkspaceProjection | null;
  switching: boolean;
  bootstrapUnavailable: boolean;
};

const BOOTSTRAP_MAX_ATTEMPTS = 3;
const BOOTSTRAP_RETRY_DELAY_MS = 1_000;

export class AccountWorkspaceStore {
  private snapshot: Snapshot = { projection: null, switching: false, bootstrapUnavailable: false };
  private listeners = new Set<() => void>();
  private symbol: string | null = null;
  private authority: { accountId: string; generation: number } | null = null;
  private switchAttempt = 0;
  private refreshAttempt = 0;
  private liveRefreshInFlight = false;
  private bootstrapAttempts = 0;
  private bootstrapRetryTimer: ReturnType<typeof setTimeout> | null = null;
  private bootstrapGeneration = 0;
  private stopped = false;

  getSnapshot = () => this.snapshot;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  setSymbol(symbol: string) {
    const symbolChanged = this.symbol !== symbol;
    this.stopped = false;
    if (!symbolChanged && this.snapshot.projection) return;
    this.symbol = symbol;
    this.cancelBootstrapRetry();
    const generation = ++this.bootstrapGeneration;
    this.bootstrapAttempts = 0;
    this.snapshot = { ...this.snapshot, bootstrapUnavailable: false };
    if (symbolChanged && this.snapshot.projection) {
      void this.refresh();
      return;
    }
    void this.runBootstrapAttempt(generation);
  }

  dispose() {
    this.stopped = true;
    ++this.bootstrapGeneration;
    ++this.refreshAttempt;
    this.cancelBootstrapRetry();
  }

  async activate(
    accountId: string,
    expected: { accountId: string; generation: number },
  ) {
    if (this.snapshot.switching) throw new Error("account_switch_in_progress");
    const attempt = ++this.switchAttempt;
    ++this.refreshAttempt;
    this.snapshot = { ...this.snapshot, switching: true };
    this.emit();
    try {
      const response = await fetch(marketApiRoutes.accountActivate(accountId), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_active_account_id: expected.accountId,
          expected_session_generation: expected.generation,
        }),
      });
      const result = await response.json() as {
        ok?: boolean; active_account_id?: string; session_generation?: number; error?: string;
      };
      if (!response.ok || result.ok !== true || typeof result.active_account_id !== "string"
        || !Number.isInteger(result.session_generation)) {
        throw new Error(result.error ?? "account_activation_failed");
      }
      if (attempt !== this.switchAttempt) throw new Error("stale_account_switch");
      if (result.active_account_id !== accountId || (this.authority
        && result.session_generation! <= this.authority.generation)) {
        throw new Error("stale_account_switch");
      }
      this.authority = { accountId: result.active_account_id, generation: result.session_generation! };
      this.snapshot = { projection: null, switching: false, bootstrapUnavailable: false };
      this.emit();
      try {
        await this.refresh();
      } catch {
        // Activation is already authoritative; keep the old projection inaccessible.
      }
      return result;
    } catch (error) {
      if (attempt === this.switchAttempt) {
        this.snapshot = { ...this.snapshot, switching: false };
        this.emit();
      }
      throw error;
    }
  }

  async refresh(): Promise<boolean> {
    const symbol = this.symbol;
    if (!symbol || this.stopped) return false;
    const attempt = ++this.refreshAttempt;
    const captured = this.authority;
    const response = await fetch(marketApiRoutes.workspaceAccount(symbol));
    if (!response.ok) return false;
    const result = await response.json() as AccountWorkspaceProjection;
    if (attempt !== this.refreshAttempt || result.ok !== true || this.stopped) return false;
    if (captured && (
      this.authority !== captured
      || result.account_id !== captured.accountId
      || result.session_generation !== captured.generation
    )) return false;
    if (this.authority && (
      result.account_id !== this.authority.accountId
      || result.session_generation !== this.authority.generation
    )) return false;
    const current = this.snapshot.projection;
    if (current
      && current.account_id === result.account_id
      && current.session_generation === result.session_generation
      && result.projection_generation < current.projection_generation) return false;
    this.authority = { accountId: result.account_id, generation: result.session_generation };
    this.snapshot = { ...this.snapshot, projection: result, bootstrapUnavailable: false };
    this.emit();
    this.cancelBootstrapRetry();
    return true;
  }

  async refreshActiveLive() {
    const current = this.snapshot.projection;
    const captured = this.authority;
    if (!current || current.provider !== "BYBIT" || !captured
      || this.snapshot.switching || this.liveRefreshInFlight) return;
    this.liveRefreshInFlight = true;
    try {
      const response = await fetch(marketApiRoutes.accountRefresh(current.account_id), {
        method: "POST",
      });
      if (!response.ok
        || this.snapshot.switching
        || this.authority !== captured
        || this.snapshot.projection?.account_id !== current.account_id
        || this.snapshot.projection?.session_generation !== current.session_generation) return;
      await this.refresh();
    } catch {
      // Preserve the last valid account-scoped projection on transient REST failure.
    } finally {
      this.liveRefreshInFlight = false;
    }
  }

  private emit() {
    for (const listener of this.listeners) listener();
  }

  private async runBootstrapAttempt(generation: number) {
    if (this.stopped || generation !== this.bootstrapGeneration
      || this.snapshot.projection || this.bootstrapAttempts >= BOOTSTRAP_MAX_ATTEMPTS) return;
    ++this.bootstrapAttempts;
    let recovered = false;
    try {
      recovered = await this.refresh();
    } catch {
      recovered = false;
    }
    if (recovered || this.stopped || generation !== this.bootstrapGeneration
      || this.snapshot.projection) return;
    if (this.bootstrapAttempts >= BOOTSTRAP_MAX_ATTEMPTS) {
      this.snapshot = { ...this.snapshot, bootstrapUnavailable: true };
      this.emit();
      return;
    }
    this.bootstrapRetryTimer = setTimeout(() => {
      this.bootstrapRetryTimer = null;
      void this.runBootstrapAttempt(generation);
    }, BOOTSTRAP_RETRY_DELAY_MS);
  }

  private cancelBootstrapRetry() {
    if (this.bootstrapRetryTimer) clearTimeout(this.bootstrapRetryTimer);
    this.bootstrapRetryTimer = null;
  }
}

export const accountWorkspaceStore = new AccountWorkspaceStore();

export function useAccountWorkspace(symbol: string) {
  const snapshot = useSyncExternalStore(
    accountWorkspaceStore.subscribe, accountWorkspaceStore.getSnapshot,
  );
  useEffect(() => {
    accountWorkspaceStore.setSymbol(symbol);
    const timer = window.setInterval(() => {
      void accountWorkspaceStore.refreshActiveLive();
    }, 30_000);
    return () => {
      window.clearInterval(timer);
      accountWorkspaceStore.dispose();
    };
  }, [symbol]);
  return snapshot;
}

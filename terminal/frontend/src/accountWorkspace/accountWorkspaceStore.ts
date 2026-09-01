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
};

export class AccountWorkspaceStore {
  private snapshot: Snapshot = { projection: null, switching: false };
  private listeners = new Set<() => void>();
  private symbol: string | null = null;
  private authority: { accountId: string; generation: number } | null = null;
  private switchAttempt = 0;
  private refreshAttempt = 0;
  private liveRefreshInFlight = false;

  getSnapshot = () => this.snapshot;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  setSymbol(symbol: string) {
    if (this.symbol === symbol) return;
    this.symbol = symbol;
    void this.refresh();
  }

  async activate(accountId: string) {
    if (this.snapshot.switching) throw new Error("account_switch_in_progress");
    const attempt = ++this.switchAttempt;
    ++this.refreshAttempt;
    this.snapshot = { ...this.snapshot, switching: true };
    this.emit();
    try {
      const response = await fetch(marketApiRoutes.accountActivate(accountId), { method: "POST" });
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
      this.snapshot = { projection: null, switching: false };
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

  async refresh() {
    const symbol = this.symbol;
    if (!symbol) return;
    const attempt = ++this.refreshAttempt;
    const captured = this.authority;
    const response = await fetch(marketApiRoutes.workspaceAccount(symbol));
    if (!response.ok) return;
    const result = await response.json() as AccountWorkspaceProjection;
    if (attempt !== this.refreshAttempt || result.ok !== true) return;
    if (captured && (
      this.authority !== captured
      || result.account_id !== captured.accountId
      || result.session_generation !== captured.generation
    )) return;
    if (this.authority && (
      result.account_id !== this.authority.accountId
      || result.session_generation !== this.authority.generation
    )) return;
    const current = this.snapshot.projection;
    if (current
      && current.account_id === result.account_id
      && current.session_generation === result.session_generation
      && result.projection_generation < current.projection_generation) return;
    this.authority = { accountId: result.account_id, generation: result.session_generation };
    this.snapshot = { ...this.snapshot, projection: result };
    this.emit();
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
}

export const accountWorkspaceStore = new AccountWorkspaceStore();

export function useAccountWorkspace(symbol: string) {
  const snapshot = useSyncExternalStore(
    accountWorkspaceStore.subscribe, accountWorkspaceStore.getSnapshot,
  );
  useEffect(() => {
    accountWorkspaceStore.setSymbol(symbol);
    void accountWorkspaceStore.refresh();
    const timer = window.setInterval(() => {
      void accountWorkspaceStore.refreshActiveLive();
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [symbol]);
  return snapshot;
}

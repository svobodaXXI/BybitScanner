import { useEffect, useRef, useState } from "react";
import { marketApiRoutes } from "../marketData/apiRoutes";
import { accountWorkspaceStore } from "../accountWorkspace/accountWorkspaceStore";
import type { AccountWorkspaceProjection } from "../accountWorkspace/accountWorkspaceStore";
import { manualMainReadProjection } from "../accountWorkspace/manualMainReadProjection";
import type { AccountMode, ModeAccountDescriptor } from "../accountWorkspace/modeAccountSelection";
import { LiveAccountInventory } from "./LiveAccountInventory";
import {
  dismissPopupFromBackdrop,
  shieldPopupClickInteraction,
  shieldPopupPointerInteraction,
} from "../interactions/popupInteractionBoundary";
import { TradingControlButton } from "../interactions/useTradingControlActivation";

type AccountDescriptor = {
  id: string;
  display_name: string;
  provider: string;
  environment: string;
  status: string;
};

type AccountCatalog = {
  active_account_id: string;
  session_generation: number;
  accounts: AccountDescriptor[];
};

type LiveAccountSummary = {
  account_id: string;
  status: string;
  wallet_balance_usdt: string;
  total_equity_usdt: string;
  position_count: number;
  order_count: number;
};

function validCatalog(value: unknown): value is AccountCatalog {
  if (!value || typeof value !== "object") return false;
  const catalog = value as Partial<AccountCatalog>;
  return typeof catalog.active_account_id === "string"
    && Number.isInteger(catalog.session_generation)
    && Array.isArray(catalog.accounts)
    && catalog.accounts.length > 0
    && catalog.accounts.every((account) =>
      account && typeof account.id === "string"
      && typeof account.display_name === "string"
      && typeof account.provider === "string"
      && typeof account.environment === "string"
      && typeof account.status === "string",
    );
}

export function AccountMenu({
  open, onToggle, workspaceProjection = null, onActiveAccountChange,
  mode, selectedAccountId, onSelectAccount, modeAccountError,
}: {
  open: boolean;
  onToggle: () => void;
  workspaceProjection?: AccountWorkspaceProjection | null;
  onActiveAccountChange?: (account: { id: string; name: string } | null) => void;
  mode?: AccountMode;
  selectedAccountId?: string | null;
  onSelectAccount?: (mode: AccountMode, account: ModeAccountDescriptor) => Promise<void>;
  modeAccountError?: string | null;
}) {
  const [catalog, setCatalog] = useState<AccountCatalog | null>(null);
  const [catalogError, setCatalogError] = useState(false);
  const [manualMain, setManualMain] = useState<AccountDescriptor[]>([]);
  const [manualMainUnavailable, setManualMainUnavailable] = useState(false);
  const [mainInventory, setMainInventory] = useState<{ name: string; projection: AccountWorkspaceProjection } | null>(null);
  const [mainInventoryError, setMainInventoryError] = useState("");
  const [mainInventoryLoading, setMainInventoryLoading] = useState<string | null>(null);
  const mainInventoryRequest = useRef(0);
  const [addOpen, setAddOpen] = useState(false);
  const [name, setName] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [balanceOpen, setBalanceOpen] = useState(false);
  const [refreshingAccount, setRefreshingAccount] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<Record<string, string>>({});
  const [confirmAccount, setConfirmAccount] = useState<AccountDescriptor | null>(null);
  const [switching, setSwitching] = useState(false);
  const [switchError, setSwitchError] = useState("");
  const submitInFlight = useRef(false);
  const catalogRequestInFlight = useRef<Promise<void> | null>(null);

  const refreshCatalog = () => {
    if (catalogRequestInFlight.current) return catalogRequestInFlight.current;
    const request = (async () => {
      const response = await fetch(marketApiRoutes.accounts);
      if (!response.ok) throw new Error("account catalog unavailable");
      const payload: unknown = await response.json();
      const candidate = (payload as { ok?: unknown }).ok === true ? payload : null;
      if (!validCatalog(candidate)) throw new Error("invalid account catalog");
      setCatalog(candidate);
      setCatalogError(false);
    })().finally(() => {
      if (catalogRequestInFlight.current === request) catalogRequestInFlight.current = null;
    });
    catalogRequestInFlight.current = request;
    return request;
  };

  const refreshManualMain = async () => {
    try {
      const response = await fetch(marketApiRoutes.manualMainAccounts, { cache: "no-store" });
      if (!response.ok) throw new Error("manual_main_unavailable");
      const result = await response.json() as { ok?: boolean; accounts?: AccountDescriptor[] };
      if (result.ok !== true || !Array.isArray(result.accounts)
        || result.accounts.some((a) => a.provider !== "BYBIT" || a.environment !== "MAINNET")) {
        throw new Error("invalid_main_catalog");
      }
      setManualMain(result.accounts);
      setManualMainUnavailable(false);
    } catch {
      setManualMain([]);
      setManualMainUnavailable(true);
    }
  };

  const openMainInventory = async (account: AccountDescriptor) => {
    const request = ++mainInventoryRequest.current;
    setMainInventory(null);
    setMainInventoryError("");
    setMainInventoryLoading(account.id);
    try {
      const refreshed = await fetch(marketApiRoutes.manualMainRefresh(account.id), { method: "POST" });
      if (!refreshed.ok) throw new Error("main_refresh_failed");
      const response = await fetch(marketApiRoutes.manualMainSummary(account.id), { cache: "no-store" });
      if (!response.ok) throw new Error("main_summary_unavailable");
      const payload = await response.json() as { ok?: boolean; summary?: unknown };
      const projection = payload.ok === true ? manualMainReadProjection(account.id, payload.summary) : null;
      if (!projection) throw new Error("main_snapshot_invalid");
      if (request === mainInventoryRequest.current) setMainInventory({ name: account.display_name, projection });
    } catch {
      if (request === mainInventoryRequest.current) setMainInventoryError("MAIN positions unavailable. PAPER was not changed.");
    } finally {
      if (request === mainInventoryRequest.current) setMainInventoryLoading(null);
    }
  };

  const requestLiveAccountRefresh = async (accountId: string) => {
    const response = await fetch(marketApiRoutes.accountRefresh(accountId), { method: "POST" });
    const payload = await response.json() as { ok?: boolean; summary?: LiveAccountSummary };
    if (!response.ok || payload.ok !== true || !payload.summary) {
      throw new Error("account_reconciliation_failed");
    }
    return payload.summary;
  };

  useEffect(() => {
    void refreshCatalog().catch(() => {
      setCatalog(null);
      setCatalogError(true);
    });
  }, []);

  useEffect(() => {
    if (open || (mode === "TERMINAL" && selectedAccountId?.startsWith("bybit-")))
      void refreshManualMain();
  }, [open, mode, selectedAccountId]);

  useEffect(() => {
    if (!open || (catalog && !catalogError)) return;
    void refreshCatalog().catch(() => {
      setCatalog(null);
      setCatalogError(true);
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const dismissOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onToggle();
    };
    window.addEventListener("keydown", dismissOnEscape);
    return () => window.removeEventListener("keydown", dismissOnEscape);
  }, [onToggle, open]);

  const active = catalog?.accounts.find((account) => account.id === catalog.active_account_id) ?? null;
  const selected = mode
    ? [...(catalog?.accounts ?? []), ...manualMain].find((account) => account.id === selectedAccountId) ?? null
    : active;
  const selectedVerified = !mode || Boolean(workspaceProjection &&
    workspaceProjection.account_id === selectedAccountId);
  useEffect(() => {
    onActiveAccountChange?.(selected ? { id: selected.id, name: selected.display_name } : null);
  }, [selected?.display_name, selected?.id, onActiveAccountChange]);
  const closeAdd = () => {
    setAddOpen(false);
    setName("");
    setApiKey("");
    setApiSecret("");
    setSubmitError("");
  };

  const submitAccount = async () => {
    if (submitInFlight.current) return;
    submitInFlight.current = true;
    setSubmitting(true);
    setSubmitError("");
    try {
      const response = await fetch(marketApiRoutes.manualMainAccounts, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: name.trim(), api_key: apiKey.trim(), api_secret: apiSecret }),
      });
      const payload = await response.json() as {
        ok?: boolean; error?: string; account_id?: string;
      };
      if (!response.ok || payload.ok !== true || !payload.account_id) {
        const messages: Record<string, string> = {
          bybit_validation_failed: "Bybit rejected these credentials.",
          credential_storage_failed: "Secure credential storage is unavailable.",
          invalid_account_payload: "Complete all account fields.",
          main_account_ineligible: "Only eligible Bybit MAINNET accounts can be connected.",
          origin_required: "Open the authenticated HTTPS terminal before adding an account.",
        };
        setSubmitError(messages[payload.error ?? ""] ?? "Account could not be added.");
        return;
      }
      closeAdd();
      await refreshManualMain();
    } catch {
      setSubmitError("Account could not be added.");
    } finally {
      submitInFlight.current = false;
      setSubmitting(false);
    }
  };

  const refreshLiveAccount = async (accountId: string) => {
    setRefreshingAccount(accountId);
    setRefreshError((current) => ({ ...current, [accountId]: "" }));
    try {
      await requestLiveAccountRefresh(accountId);
      await refreshCatalog();
    } catch {
      setRefreshError((current) => ({ ...current, [accountId]: "Refresh failed; account is not ready." }));
      try { await refreshCatalog(); } catch { setCatalogError(true); }
    } finally {
      setRefreshingAccount(null);
    }
  };

  const activateAccount = async () => {
    if (!confirmAccount || switching) return;
    setSwitching(true);
    setSwitchError("");
    try {
      if (mode) {
        if (!onSelectAccount) throw new Error("mode_selection_unavailable");
        await onSelectAccount(mode, confirmAccount);
        setConfirmAccount(null);
        return;
      }
      if (confirmAccount.provider === "BYBIT"
        && !["READY", "READ_ONLY"].includes(confirmAccount.status)) {
        if (!["DISCONNECTED", "ERROR"].includes(confirmAccount.status)) {
          throw new Error("account_activation_not_ready");
        }
        await requestLiveAccountRefresh(confirmAccount.id);
      }
      if (!catalog) throw new Error("stale_account_session");
      await accountWorkspaceStore.activate(confirmAccount.id, {
        accountId: catalog.active_account_id,
        generation: catalog.session_generation,
      });
      setConfirmAccount(null);
      try {
        await refreshCatalog();
      } catch {
        setCatalog(null);
        setCatalogError(true);
      }
    } catch (error) {
      const code = error instanceof Error ? error.message : "account_activation_failed";
      setSwitchError(code === "account_reconciliation_failed"
        ? "Reconnect failed; the previous account remains Current."
        : code === "stale_account_session"
          ? "Account selection changed; review Current account and try again."
        : code === "account_activation_not_ready"
          ? "Refresh/Reconnect this account before switching."
          : "Account switch failed; the previous account remains Current.");
      if (code === "stale_account_session") {
        try { await refreshCatalog(); } catch { setCatalogError(true); }
      }
    } finally {
      setSwitching(false);
    }
  };

  return (
    <div className="paper-account-control">
      <TradingControlButton
        aria-expanded={open}
        aria-label="Open account selection"
        className="account-switch-button"
        onHoldEnd={() => setBalanceOpen(false)}
        onHoldStart={() => setBalanceOpen(true)}
        onTap={onToggle}
      >
        {!open ? <span className="account-switch-key" aria-hidden="true">
          <span className="account-key-head" />
          <span className="account-key-shaft" />
        </span> : null}
        <span className="account-switch-label">
          <strong>{selected && selectedVerified
            ? selected.provider === "PAPER" ? "PAPER" : selected.display_name
            : mode ? "UNAVAILABLE" : catalogError ? "UNAVAILABLE" : "LOADING"}</strong>
          <small>{selected && selectedVerified
            ? `${selected.provider} · ${selected.status}`
            : mode ? "SELECTED ACCOUNT UNAVAILABLE" : "ACCOUNT STATUS"}</small>
        </span>
      </TradingControlButton>
      {balanceOpen ? (
        <div aria-label="Account balance" className="account-balance-popover" role="tooltip">
          {workspaceProjection ? (
            <>
              <span><strong>Deposit</strong> {workspaceProjection.wallet_balance_usdt} USD</span>
              <span><strong>Available</strong> {workspaceProjection.available_balance_usdt} USD</span>
            </>
          ) : (
            <span>{catalogError || active?.status === "ERROR" || active?.status === "DISCONNECTED"
              ? "Balance unavailable" : "Balance loading…"}</span>
          )}
        </div>
      ) : null}
      {open ? (
        <div
          className="account-menu-backdrop"
          data-testid="account-menu-backdrop"
          onPointerDown={(event) => dismissPopupFromBackdrop(event, onToggle)}
          role="presentation"
        >
          <section
            aria-label="Accounts"
            aria-modal="true"
            className="account-menu"
            onClick={shieldPopupClickInteraction}
            onPointerDown={shieldPopupPointerInteraction}
            role="dialog"
          >
            <header>
              <strong>Accounts</strong>
              <button aria-label="Close Accounts" className="account-menu-close" onClick={onToggle} type="button">×</button>
            </header>
            {catalogError || !catalog || !active ? <p role="alert">Account catalog unavailable</p> : catalog.accounts
              .filter((account) => !mode || account.provider === "PAPER")
              .map((account) => (
              <article
                className={`account-card ${account.environment.toLowerCase()} status-${account.status.toLowerCase()}`}
                key={account.id}
                onClick={() => account.id !== (mode ? selectedAccountId : catalog.active_account_id)
                  && !switching && setConfirmAccount(account)}
              >
                <div className="account-card-title">
                  <strong>{account.display_name}</strong>
                  {account.id === (mode ? selectedAccountId : catalog.active_account_id) ? <span
                    aria-label="Current account golden key"
                    className="account-switch-key account-current-key"
                    role="img"
                  ><span className="account-key-head" /><span className="account-key-shaft" /></span> : null}
                </div>
                <small>{account.provider} · {account.environment} · {account.status}</small>
                {account.id === (mode ? selectedAccountId : catalog.active_account_id) ? <span>Current</span> : null}
                {refreshError[account.id] ? <small className="account-refresh-error" role="alert">{refreshError[account.id]}</small> : null}
                {account.provider === "BYBIT" ? <button
                  className="account-refresh-button"
                  disabled={refreshingAccount === account.id}
                  onClick={(event) => { event.stopPropagation(); void refreshLiveAccount(account.id); }}
                  type="button"
                >{refreshingAccount === account.id ? "Refreshing…" : account.status === "DISCONNECTED" || account.status === "ERROR" ? "Reconnect" : "Refresh"}</button> : null}
              </article>
            ))}
            {mode !== "AUTOPILOT" && manualMain.map((account) => (
              <article className="account-card mainnet" key={account.id} aria-label="Manual MAIN account">
                <strong>{account.display_name}</strong>
                <small>BYBIT · MAINNET · {account.status} · Separate MAIN service</small>
                <small>Read-only MAIN. Real order execution remains disabled.</small>
                {mode === "TERMINAL" && account.id !== selectedAccountId ? (
                  <button type="button" disabled={switching}
                    onClick={() => setConfirmAccount(account)}>Select MAIN (read-only)</button>
                ) : null}
                <button type="button" disabled={mainInventoryLoading === account.id}
                  onClick={() => void openMainInventory(account)}>
                  {mainInventoryLoading === account.id ? "Loading positions…" : "All MAIN positions"}
                </button>
                {refreshError[account.id] ? <small role="alert">{refreshError[account.id]}</small> : null}
                <button type="button" disabled={refreshingAccount === account.id}
                  onClick={() => void (async () => {
                    setRefreshingAccount(account.id);
                    try {
                      const response = await fetch(marketApiRoutes.manualMainRefresh(account.id), { method: "POST" });
                      if (!response.ok) throw new Error("main_refresh_failed");
                      await refreshManualMain();
                      setRefreshError((current) => ({ ...current, [account.id]: "" }));
                    } catch {
                      setRefreshError((current) => ({ ...current, [account.id]: "MAIN refresh failed." }));
                    } finally { setRefreshingAccount(null); }
                  })()}>Refresh MAIN</button>
              </article>
            ))}
            {mainInventoryError ? <small role="alert">{mainInventoryError}</small> : null}
            {modeAccountError ? <small role="alert">{modeAccountError}</small> : null}
            {mode !== "AUTOPILOT" && manualMainUnavailable ? <small role="status">Separate MAIN service unavailable; PAPER unchanged.</small> : null}
            {mode !== "AUTOPILOT" ? <button className="account-add-button" onClick={() => setAddOpen(true)} type="button">+ Add MAIN account</button> : null}
          </section>
        </div>
      ) : null}
      {mainInventory ? <LiveAccountInventory
        activeAccountName={mainInventory.name + " · MAIN · READ ONLY"}
        activeSymbol=""
        projection={mainInventory.projection}
        onClose={() => { ++mainInventoryRequest.current; setMainInventory(null); }}
        onNavigate={() => { ++mainInventoryRequest.current; setMainInventory(null); }}
      /> : null}
      {confirmAccount ? (
        <div className="account-dialog-backdrop" role="presentation">
          <section aria-label="Confirm account switch" aria-modal="true" className="account-dialog" role="dialog">
            <header><strong>Switch workspace account?</strong></header>
            <p>{confirmAccount.display_name}</p>
            <small>{confirmAccount.provider} · {confirmAccount.environment} · {confirmAccount.status}</small>
            <p>{mode
              ? "Only this mode's account preference changes. MAIN is read-only; LIVE remains disabled."
              : "The entire account-scoped workspace will switch. LIVE trading remains disabled."}</p>
            {switchError ? <p role="alert">{switchError}</p> : null}
            <div className="account-switch-confirm-actions">
              <button className="account-switch-confirm-accept" disabled={switching || confirmAccount.status === "RECONCILING"} onClick={() => void activateAccount()} type="button">
                {switching ? "Switching…" : ["DISCONNECTED", "ERROR"].includes(confirmAccount.status)
                  ? "Reconnect & switch account" : "Switch account"}
              </button>
              <button className="account-switch-confirm-cancel" disabled={switching} onClick={() => { setConfirmAccount(null); setSwitchError(""); }} type="button">Cancel</button>
            </div>
          </section>
        </div>
      ) : null}
      {addOpen ? (
        <div className="account-dialog-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) closeAdd();
        }}>
          <section aria-label="Add account" aria-modal="true" className="account-dialog" role="dialog">
            <header><strong>Add Bybit MAIN account</strong><button aria-label="Close add account" onClick={closeAdd} type="button">×</button></header>
            <small>Keys are sent only to the separate MAIN service. No real orders can be placed yet.</small>
            <label>Account name<input value={name} onChange={(event) => setName(event.target.value)} /></label>
            <label>API Key<input value={apiKey} onChange={(event) => setApiKey(event.target.value)} /></label>
            <label>API Secret<input autoComplete="new-password" type="password" value={apiSecret} onChange={(event) => setApiSecret(event.target.value)} /></label>
            {submitError ? <p role="alert">{submitError}</p> : null}
            <button disabled={submitting || !name.trim() || !apiKey.trim() || !apiSecret.trim()} onClick={submitAccount} type="button">
              {submitting ? "Validating…" : "Add account"}
            </button>
          </section>
        </div>
      ) : null}
    </div>
  );
}

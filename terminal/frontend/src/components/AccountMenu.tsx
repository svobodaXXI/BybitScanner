import { useEffect, useRef, useState } from "react";
import { marketApiRoutes } from "../marketData/apiRoutes";
import { accountWorkspaceStore } from "../accountWorkspace/accountWorkspaceStore";
import type { AccountWorkspaceProjection } from "../accountWorkspace/accountWorkspaceStore";
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
}: {
  open: boolean;
  onToggle: () => void;
  workspaceProjection?: AccountWorkspaceProjection | null;
  onActiveAccountChange?: (account: { id: string; name: string } | null) => void;
}) {
  const [catalog, setCatalog] = useState<AccountCatalog | null>(null);
  const [catalogError, setCatalogError] = useState(false);
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
  useEffect(() => {
    onActiveAccountChange?.(active ? { id: active.id, name: active.display_name } : null);
  }, [active?.display_name, active?.id, onActiveAccountChange]);
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
      const response = await fetch(marketApiRoutes.accounts, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: name.trim(), api_key: apiKey.trim(), api_secret: apiSecret }),
      });
      const payload = await response.json() as {
        ok?: boolean; error?: string; account?: AccountDescriptor;
      };
      if (!response.ok || payload.ok !== true || !payload.account) {
        const messages: Record<string, string> = {
          bybit_validation_failed: "Bybit rejected these credentials.",
          credential_storage_failed: "Secure credential storage is unavailable.",
          invalid_account_payload: "Complete all account fields.",
        };
        setSubmitError(messages[payload.error ?? ""] ?? "Account could not be added.");
        return;
      }
      closeAdd();
      try {
        await refreshCatalog();
      } catch {
        setCatalog(null);
        setCatalogError(true);
      }
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
          <strong>{active
            ? active.provider === "PAPER" ? "PAPER" : active.display_name
            : catalogError ? "UNAVAILABLE" : "LOADING"}</strong>
          <small>{active ? `${active.provider} · ${active.status}` : "ACCOUNT STATUS"}</small>
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
            {catalogError || !catalog || !active ? <p role="alert">Account catalog unavailable</p> : catalog.accounts.map((account) => (
              <article
                className={`account-card ${account.environment.toLowerCase()} status-${account.status.toLowerCase()}`}
                key={account.id}
                onClick={() => account.id !== catalog.active_account_id && !switching && setConfirmAccount(account)}
              >
                <div className="account-card-title">
                  <strong>{account.display_name}</strong>
                  {account.id === catalog.active_account_id ? <span
                    aria-label="Current account golden key"
                    className="account-switch-key account-current-key"
                    role="img"
                  ><span className="account-key-head" /><span className="account-key-shaft" /></span> : null}
                </div>
                <small>{account.provider} · {account.environment} · {account.status}</small>
                {account.id === catalog.active_account_id ? <span>Current</span> : null}
                {refreshError[account.id] ? <small className="account-refresh-error" role="alert">{refreshError[account.id]}</small> : null}
                {account.provider === "BYBIT" ? <button
                  className="account-refresh-button"
                  disabled={refreshingAccount === account.id}
                  onClick={(event) => { event.stopPropagation(); void refreshLiveAccount(account.id); }}
                  type="button"
                >{refreshingAccount === account.id ? "Refreshing…" : account.status === "DISCONNECTED" || account.status === "ERROR" ? "Reconnect" : "Refresh"}</button> : null}
              </article>
            ))}
            <button className="account-add-button" onClick={() => setAddOpen(true)} type="button">+ Add account</button>
          </section>
        </div>
      ) : null}
      {confirmAccount ? (
        <div className="account-dialog-backdrop" role="presentation">
          <section aria-label="Confirm account switch" aria-modal="true" className="account-dialog" role="dialog">
            <header><strong>Switch workspace account?</strong></header>
            <p>{confirmAccount.display_name}</p>
            <small>{confirmAccount.provider} · {confirmAccount.environment} · {confirmAccount.status}</small>
            <p>The entire account-scoped workspace will switch. LIVE trading remains disabled.</p>
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
            <header><strong>Add account</strong><button aria-label="Close add account" onClick={closeAdd} type="button">×</button></header>
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

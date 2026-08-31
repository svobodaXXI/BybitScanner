import { useEffect, useState } from "react";
import { marketApiRoutes } from "../marketData/apiRoutes";

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

export function AccountMenu({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const [catalog, setCatalog] = useState<AccountCatalog | null>(null);
  const [catalogError, setCatalogError] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [name, setName] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");

  const refreshCatalog = async () => {
    const response = await fetch(marketApiRoutes.accounts);
    if (!response.ok) throw new Error("account catalog unavailable");
    const payload: unknown = await response.json();
    const candidate = (payload as { ok?: unknown }).ok === true ? payload : null;
    if (!validCatalog(candidate)) throw new Error("invalid account catalog");
    setCatalog(candidate);
    setCatalogError(false);
  };

  useEffect(() => {
    const controller = new AbortController();
    void fetch(marketApiRoutes.accounts, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("account catalog unavailable");
        const payload: unknown = await response.json();
        const candidate = (payload as { ok?: unknown }).ok === true ? payload : null;
        if (!validCatalog(candidate)) throw new Error("invalid account catalog");
        setCatalog(candidate);
        setCatalogError(false);
      })
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") {
          setCatalog(null);
          setCatalogError(true);
        }
      });
    return () => controller.abort();
  }, []);

  const active = catalog?.accounts.find((account) => account.id === catalog.active_account_id) ?? null;
  const closeAdd = () => {
    setAddOpen(false);
    setName("");
    setApiKey("");
    setApiSecret("");
    setSubmitError("");
  };

  const submitAccount = async () => {
    setSubmitting(true);
    setSubmitError("");
    try {
      const response = await fetch(marketApiRoutes.accounts, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: name.trim(), api_key: apiKey.trim(), api_secret: apiSecret }),
      });
      const payload = await response.json() as { ok?: boolean; error?: string };
      if (!response.ok || payload.ok !== true) {
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
      setSubmitting(false);
    }
  };

  return (
    <div className="paper-account-control">
      <button
        aria-expanded={open}
        aria-label="Open account selection"
        className="account-switch-button"
        onClick={onToggle}
        type="button"
      >
        <span className="account-switch-key" aria-hidden="true">
          <span className="account-key-head" />
          <span className="account-key-shaft" />
        </span>
        <span className="account-switch-label">
          <strong>{active?.display_name ?? (catalogError ? "UNAVAILABLE" : "LOADING")}</strong>
          <small>{active ? `${active.provider} · ${active.status}` : "ACCOUNT STATUS"}</small>
        </span>
      </button>
      {open ? (
        <section className="account-menu" aria-label="Accounts">
          <header><strong>Accounts</strong></header>
          {catalogError || !catalog || !active ? <p role="alert">Account catalog unavailable</p> : catalog.accounts.map((account) => (
            <article className={`account-card ${account.environment.toLowerCase()} status-${account.status.toLowerCase()}`} key={account.id}>
              <strong>{account.display_name}</strong>
              <small>{account.provider} · {account.environment} · {account.status}</small>
              {account.id === catalog.active_account_id ? <span>Current</span> : null}
            </article>
          ))}
          <button className="account-add-button" onClick={() => setAddOpen(true)} type="button">+ Add account</button>
        </section>
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

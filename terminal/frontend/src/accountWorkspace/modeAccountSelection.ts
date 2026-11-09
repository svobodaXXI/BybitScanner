import { useCallback, useEffect, useRef, useState } from "react";
import { manualMainReadProjection } from "./manualMainReadProjection";
import type { AccountWorkspaceProjection } from "./accountWorkspaceStore";
import { marketApiRoutes } from "../marketData/apiRoutes";

export type AccountMode = "TERMINAL" | "AUTOPILOT";
export type ModeAccountDescriptor = {
  id: string;
  display_name: string;
  provider: string;
  environment: string;
  status: string;
};
type Preferences = Record<AccountMode, string | null>;

const MAIN_DEVICE_KEY = "bybitscanner.terminal.manualMainAccountId.v1";
const MAIN_ACCOUNT_ID = /^bybit-[a-z0-9-]{1,58}$/;

export function scopedProjection(
  mode: AccountMode | "EDITOR",
  selectedAccountId: string | null,
  paperProjection: AccountWorkspaceProjection | null,
  mainProjection: AccountWorkspaceProjection | null,
): AccountWorkspaceProjection | null {
  if (mode === "EDITOR" || !selectedAccountId) return null;
  if (selectedAccountId === "paper") {
    return paperProjection?.account_id === "paper" && paperProjection.provider === "PAPER"
      && paperProjection.environment === "PAPER" ? paperProjection : null;
  }
  return mode === "TERMINAL" && mainProjection?.account_id === selectedAccountId
    && mainProjection.provider === "BYBIT"
    && (mainProjection.read_only === true || (mainProjection.read_only === false
      && mainProjection.capabilities?.market === true))
    ? mainProjection : null;
}

function readDeviceMainId(): string | null {
  const id = window.localStorage.getItem(MAIN_DEVICE_KEY);
  if (!id) return null;
  if (!MAIN_ACCOUNT_ID.test(id)) throw new Error("invalid_stored_main_account");
  return id;
}

async function mainProjectionFor(accountId: string, refresh: boolean): Promise<AccountWorkspaceProjection> {
  if (!MAIN_ACCOUNT_ID.test(accountId)) throw new Error("invalid_main_account");
  const catalogResponse = await fetch(marketApiRoutes.manualMainAccounts, { cache: "no-store" });
  if (!catalogResponse.ok) throw new Error("main_catalog_unavailable");
  const catalog = await catalogResponse.json() as { ok?: boolean; accounts?: ModeAccountDescriptor[] };
  const entry = catalog.ok === true && Array.isArray(catalog.accounts)
    ? catalog.accounts.find((account) => account.id === accountId
      && account.provider === "BYBIT" && account.environment === "MAINNET") : null;
  if (!entry) throw new Error("main_account_not_found");
  // A previous snapshot is not proof of a READY current MAIN session.
  if (!refresh && !["READY", "READ_ONLY"].includes(entry.status))
    throw new Error("main_account_not_ready");
  if (refresh) {
    const renewed = await fetch(marketApiRoutes.manualMainRefresh(accountId), { method: "POST" });
    if (!renewed.ok) throw new Error("main_refresh_unavailable");
  }
  const summaryResponse = await fetch(marketApiRoutes.manualMainSummary(accountId), { cache: "no-store" });
  if (!summaryResponse.ok) throw new Error("main_summary_unavailable");
  const payload = await summaryResponse.json() as { ok?: boolean; summary?: unknown };
  const projection = payload.ok === true ? manualMainReadProjection(accountId, payload.summary) : null;
  if (!projection) throw new Error("main_account_projection_unavailable");
  return projection;
}

/** Display preference only: never calls /activate or an order route. */
export function useModeAccountSelection() {
  const [preferences, setPreferences] = useState<Preferences>({ TERMINAL: null, AUTOPILOT: null });
  const [ready, setReady] = useState(false);
  const [pending, setPending] = useState(false);
  const [pendingMode, setPendingMode] = useState<AccountMode | null>(null);
  const [mainProjection, setMainProjection] = useState<AccountWorkspaceProjection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const request = useRef(0);
  const busy = useRef(false);

  useEffect(() => {
    const sequence = ++request.current;
    void (async () => {
      try {
        const response = await fetch(marketApiRoutes.modeAccountPreferences, { cache: "no-store" });
        if (!response.ok) throw new Error("mode_preferences_unavailable");
        const payload = await response.json() as { ok?: boolean; preferences?: Preferences };
        const selected = payload.preferences;
        if (payload.ok !== true || !selected
          || (selected.TERMINAL !== null && typeof selected.TERMINAL !== "string")
          || (selected.AUTOPILOT !== null && selected.AUTOPILOT !== "paper"))
          throw new Error("invalid_mode_preferences");
        const localMain = readDeviceMainId();
        const next: Preferences = {
          TERMINAL: localMain ?? selected.TERMINAL ?? "paper",
          AUTOPILOT: selected.AUTOPILOT ?? "paper",
        };
        if (sequence === request.current) {
          setPreferences(next);
          setReady(true);
        }
      } catch {
        if (sequence === request.current) {
          // The independent MAIN gateway must not depend on PAPER preferences.
          let localMain: string | null = null;
          try { localMain = readDeviceMainId(); } catch { /* fail closed */ }
          if (localMain) {
            setPreferences({ TERMINAL: localMain, AUTOPILOT: null });
            setError("PAPER preferences unavailable; MAIN requires independent verification.");
            setReady(true);
          } else {
            setError("Saved account selection unavailable. Trading is disabled.");
            setReady(false);
          }
        }
      }
    })();
    return () => { ++request.current; };
  }, []);

  const mainId = ready && preferences.TERMINAL !== "paper" ? preferences.TERMINAL : null;
  const currentMainId = useRef<string | null>(null);
  currentMainId.current = mainId;
  const refreshMain = useCallback(async () => {
    const accountId = currentMainId.current;
    if (!accountId) throw new Error("main_account_not_selected");
    const projection = await mainProjectionFor(accountId, true);
    if (currentMainId.current !== accountId) throw new Error("main_account_changed");
    setMainProjection(projection);
  }, []);
  useEffect(() => {
    let live = true;
    if (!mainId) {
      setMainProjection(null);
      return () => { live = false; };
    }
    // A successful explicit selection already contains a verified snapshot.
    if (mainProjection?.account_id === mainId) return () => { live = false; };
    setMainProjection(null);
    // After a gateway restart, its catalog is DISCONNECTED until a read-only
    // refresh. Reconcile on restore rather than showing a stale saved snapshot.
    void mainProjectionFor(mainId, true).then((projection) => {
      if (live) setMainProjection(projection);
    }).catch(() => {
      if (live) setError("Selected MAIN account unavailable; no fallback to PAPER.");
    });
    return () => { live = false; };
  }, [mainId]);

  const selectAccount = useCallback(async (mode: AccountMode, account: ModeAccountDescriptor) => {
    if (!ready || busy.current) throw new Error("account_switch_in_progress");
    if (mode === "AUTOPILOT" && account.id !== "paper")
      throw new Error("autopilot_paper_only");
    busy.current = true;
    setPending(true);
    setPendingMode(mode);
    setError(null);
    try {
      if (account.id === "paper") {
        if (account.provider !== "PAPER" || account.environment !== "PAPER"
          || account.status !== "READY") throw new Error("paper_account_not_ready");
        const response = await fetch(marketApiRoutes.modeAccountPreferences, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode, account_id: account.id }),
        });
        const result = await response.json() as { ok?: boolean; mode?: string; account_id?: string };
        if (!response.ok || result.ok !== true || result.mode !== mode
          || result.account_id !== "paper") throw new Error("mode_preference_not_saved");
        if (mode === "TERMINAL") window.localStorage.removeItem(MAIN_DEVICE_KEY);
        setPreferences((current) => ({ ...current, [mode]: "paper" }));
      } else {
        if (mode !== "TERMINAL" || account.provider !== "BYBIT"
          || account.environment !== "MAINNET") throw new Error("main_not_allowed");
        const projection = await mainProjectionFor(account.id, true);
        // Only a credential-free identity is stored on the current device.
        window.localStorage.setItem(MAIN_DEVICE_KEY, account.id);
        setMainProjection(projection);
        setPreferences((current) => ({ ...current, TERMINAL: account.id }));
      }
    } catch (reason) {
      setError("Account switch unconfirmed; previous selection retained.");
      throw reason;
    } finally {
      busy.current = false;
      setPending(false);
      setPendingMode(null);
    }
  }, [ready]);

  return { preferences, ready, pending, pendingMode, mainProjection, error, selectAccount, refreshMain };
}

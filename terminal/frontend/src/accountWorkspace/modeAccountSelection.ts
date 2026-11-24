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
  try {
    const id = window.localStorage.getItem(MAIN_DEVICE_KEY);
    return id && MAIN_ACCOUNT_ID.test(id) ? id : null;
  } catch { return null; }
}

function clearLegacyMainId() {
  try { window.localStorage.removeItem(MAIN_DEVICE_KEY); } catch { /* server is authoritative */ }
}

async function readTerminalPreference(): Promise<string | null> {
  const response = await fetch(marketApiRoutes.terminalAccountPreference, { cache: "no-store" });
  if (!response.ok) throw new Error("terminal_preference_unavailable");
  const data = await response.json() as { ok?: boolean; account_id?: unknown };
  if (data.ok !== true || (data.account_id !== null && data.account_id !== "paper" &&
      (typeof data.account_id !== "string" || !MAIN_ACCOUNT_ID.test(data.account_id))))
    throw new Error("invalid_terminal_preference");
  return data.account_id as string | null;
}

async function saveTerminalPreference(accountId: string) {
  const response = await fetch(marketApiRoutes.terminalAccountPreference, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account_id: accountId }),
  });
  const data = await response.json() as { ok?: boolean; account_id?: unknown };
  if (!response.ok || data.ok !== true || data.account_id !== accountId)
    throw new Error("terminal_preference_not_saved");
  clearLegacyMainId();
}

async function restoreTerminalPreference(): Promise<string> {
  const saved = await readTerminalPreference();
  if (saved !== null) {
    clearLegacyMainId();
    return saved;
  }
  const legacy = readDeviceMainId();
  if (legacy) {
    // The server validates the existing configured identity. A disconnect
    // does not erase an established display binding.
    await saveTerminalPreference(legacy);
    return legacy;
  }
  return "paper";
}

async function readAutopilotPreference(): Promise<string> {
  const response = await fetch(marketApiRoutes.modeAccountPreferences, { cache: "no-store" });
  if (!response.ok) throw new Error("mode_preferences_unavailable");
  const data = await response.json() as { ok?: boolean; preferences?: Preferences };
  if (data.ok !== true || !data.preferences ||
      (data.preferences.AUTOPILOT !== null && data.preferences.AUTOPILOT !== "paper"))
    throw new Error("invalid_mode_preferences");
  return "paper";
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
    let timer: number | undefined;
    let retryDelay = 1000;
    let terminalResolved = false;
    let autopilotResolved = false;
    // The two display authorities restore independently; neither waits for
    // the other's network response. An unknown MAIN binding never means PAPER.
    const restore = async () => {
      if (sequence !== request.current) return;
      if (busy.current) {
        timer = window.setTimeout(restore, 1000);
        return;
      }
      const jobs: Promise<void>[] = [];
      if (!terminalResolved) jobs.push(restoreTerminalPreference().then((selected) => {
        if (sequence !== request.current || busy.current) return;
        terminalResolved = true;
        setPreferences(current => ({ ...current, TERMINAL: current.TERMINAL ?? selected }));
        setReady(true);
      }).catch(() => {
        if (sequence === request.current) setError("Terminal account binding unavailable; no PAPER fallback.");
      }));
      if (!autopilotResolved) jobs.push(readAutopilotPreference().then((selected) => {
        if (sequence !== request.current || busy.current) return;
        autopilotResolved = true;
        setPreferences(current => ({ ...current, AUTOPILOT: current.AUTOPILOT ?? selected }));
        setReady(true);
      }).catch(() => {
        if (sequence === request.current) setError("Autopilot preference unavailable.");
      }));
      await Promise.all(jobs);
      if (sequence !== request.current) return;
      if (terminalResolved && autopilotResolved) {
        setError(null);
        return;
      }
      timer = window.setTimeout(restore, retryDelay);
      retryDelay = Math.min(30_000, retryDelay * 2);
    };
    void restore();
    return () => { ++request.current; if (timer !== undefined) window.clearTimeout(timer); };
  }, []);

  const mainId = ready && preferences.TERMINAL !== "paper" ? preferences.TERMINAL : null;
  const currentMainId = useRef<string | null>(null);
  currentMainId.current = mainId;
  const refreshMain = useCallback(async () => {
    const accountId = currentMainId.current;
    if (!accountId) throw new Error("main_account_not_selected");
    try {
      const projection = await mainProjectionFor(accountId, true);
      if (currentMainId.current !== accountId) throw new Error("main_account_changed");
      setMainProjection(projection);
    } catch (reason) {
      if (currentMainId.current === accountId) setMainProjection(null);
      throw reason;
    }
  }, []);
  useEffect(() => {
    let live = true;
    let timer: number | undefined;
    let delay = 1000;
    if (!mainId) {
      setMainProjection(null);
      return () => { live = false; };
    }
    if (mainProjection?.account_id === mainId) return () => { live = false; };
    setMainProjection(null);
    const reconnect = async () => {
      if (!live) return;
      if (busy.current) {
        timer = window.setTimeout(reconnect, 1000);
        return;
      }
      try {
        const projection = await mainProjectionFor(mainId, true);
        if (live && currentMainId.current === mainId && !busy.current) {
          setMainProjection(projection);
          setError(null);
          return;
        }
      } catch {
        if (live) setError("Selected MAIN account unavailable; reconnecting without PAPER fallback.");
      }
      if (live) {
        timer = window.setTimeout(reconnect, delay);
        delay = Math.min(30_000, delay * 2);
      }
    };
    void reconnect();
    return () => { live = false; if (timer !== undefined) window.clearTimeout(timer); };
  }, [mainId, mainProjection?.account_id]);

  // Keep the selected read-only inventory fresh after reconnect. A writable
  // session has separate order/confirmation generation fences; never poll it
  // here and accidentally invalidate an in-flight manual action.
  useEffect(() => {
    if (!mainId || mainProjection?.account_id !== mainId || !mainProjection.read_only) return;
    const previous = mainProjection;
    let live = true;
    let timer: number | undefined;
    const refreshInventory = async () => {
      if (!live || currentMainId.current !== mainId) return;
      if (busy.current) {
        timer = window.setTimeout(refreshInventory, 1000);
        return;
      }
      try {
        const next = await mainProjectionFor(mainId, true);
        if (!live || currentMainId.current !== mainId) return;
        if (busy.current) {
          timer = window.setTimeout(refreshInventory, 1000);
          return;
        }
        setMainProjection(current => current === previous ? next : current);
      } catch {
        if (!live || currentMainId.current !== mainId) return;
        if (busy.current) {
          timer = window.setTimeout(refreshInventory, 1000);
          return;
        }
        // Existing reconnect effect handles the next attempt, without PAPER fallback.
        setMainProjection(current => current === previous ? null : current);
        setError("Selected MAIN account unavailable; reconnecting without PAPER fallback.");
      }
    };
    timer = window.setTimeout(refreshInventory, 15_000);
    return () => { live = false; if (timer !== undefined) window.clearTimeout(timer); };
  }, [mainId, mainProjection]);

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
        if (mode === "TERMINAL") {
          await saveTerminalPreference("paper");
        } else {
          const response = await fetch(marketApiRoutes.modeAccountPreferences, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mode, account_id: account.id }),
          });
          const result = await response.json() as { ok?: boolean; mode?: string; account_id?: string };
          if (!response.ok || result.ok !== true || result.mode !== mode
            || result.account_id !== "paper") throw new Error("mode_preference_not_saved");
        }
        setPreferences((current) => ({ ...current, [mode]: "paper" }));
      } else {
        if (mode !== "TERMINAL" || account.provider !== "BYBIT"
          || account.environment !== "MAINNET") throw new Error("main_not_allowed");
        const projection = await mainProjectionFor(account.id, true);
        await saveTerminalPreference(account.id);
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

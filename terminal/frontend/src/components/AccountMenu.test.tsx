import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AccountMenu } from "./AccountMenu";

const catalog = {
  ok: true,
  active_account_id: "paper",
  session_generation: 1,
  accounts: [{ id: "paper", display_name: "Paper / Virtual", provider: "PAPER", environment: "PAPER", status: "READY" }],
};

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("AccountMenu", () => {
  it("renders the active account name beside the one canonical key", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => catalog }));
    const { unmount } = render(<AccountMenu open={false} onToggle={vi.fn()} />);
    const control = screen.getByRole("button", { name: "Open account selection" });
    expect(await within(control).findByText("PAPER")).toBeInTheDocument();
    expect(control.querySelectorAll(".account-switch-key")).toHaveLength(1);

    unmount();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({
      ...catalog,
      active_account_id: "bybit-main",
      accounts: [{ id: "bybit-main", display_name: "Main Bybit", provider: "BYBIT",
        environment: "MAINNET", status: "READY" }],
    }) }));
    render(<AccountMenu open={false} onToggle={vi.fn()} />);
    await screen.findByText("Main Bybit");
    expect(within(screen.getByRole("button", { name: "Open account selection" }))
      .getByText("Main Bybit")).toBeInTheDocument();
  });

  it("opens Accounts on a short key tap", () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => catalog }));
    function Harness() {
      const [open, setOpen] = useState(false);
      return <AccountMenu open={open} onToggle={() => setOpen((current) => !current)} />;
    }
    render(<Harness />);
    const key = screen.getByRole("button", { name: "Open account selection" });
    fireEvent.pointerDown(key, { button: 0, pointerId: 1, pointerType: "touch" });
    fireEvent.pointerUp(key, { pointerId: 1, pointerType: "touch" });
    expect(screen.getByRole("dialog", { name: "Accounts" })).toBeInTheDocument();
  });

  it("shows only compact projection balance on hold without opening Accounts", () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => catalog }));
    function Harness() {
      const [open, setOpen] = useState(false);
      return <AccountMenu
        open={open}
        onToggle={() => setOpen((current) => !current)}
        workspaceProjection={{
          ok: true, account_id: "paper", provider: "PAPER", environment: "PAPER",
          status: "READY", session_generation: 1, projection_generation: 2, read_only: false,
          wallet_balance_usdt: "5000", total_equity_usdt: "5100",
          available_balance_usdt: "4900", positions: [], orders: [], paper_state: null,
        }}
      />;
    }
    render(<Harness />);
    const heldKey = screen.getByRole("button", { name: "Open account selection" });
    fireEvent.pointerDown(heldKey, { button: 0, pointerId: 2, pointerType: "touch" });
    act(() => vi.advanceTimersByTime(500));
    const balance = screen.getByRole("tooltip", { name: "Account balance" });
    expect(balance).toHaveTextContent("Deposit 5000 USD");
    expect(balance).toHaveTextContent("Available 4900 USD");
    expect(balance).not.toHaveTextContent(/positions|orders|wallet/i);
    expect(screen.queryByRole("dialog", { name: "Accounts" })).not.toBeInTheDocument();
    fireEvent.pointerUp(heldKey, { pointerId: 2, pointerType: "touch" });
    fireEvent.click(heldKey);
    expect(screen.queryByRole("tooltip", { name: "Account balance" })).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Accounts" })).not.toBeInTheDocument();
  });

  it("uses the active LIVE projection for the compact hold balance", () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({
      ...catalog,
      active_account_id: "bybit-main",
      accounts: [{ id: "bybit-main", display_name: "Main Bybit", provider: "BYBIT", environment: "MAINNET", status: "READY" }],
    }) }));
    render(<AccountMenu open={false} onToggle={vi.fn()} workspaceProjection={{
      ok: true, account_id: "bybit-main", provider: "BYBIT", environment: "MAINNET",
      status: "READY", session_generation: 8, projection_generation: 3, read_only: true,
      wallet_balance_usdt: "90", total_equity_usdt: "100",
      available_balance_usdt: "70", positions: [{ symbol: "BTCUSDT" }],
      orders: [{ order_id: "o1" }], paper_state: null,
    }} />);
    const key = screen.getByRole("button", { name: "Open account selection" });
    fireEvent.pointerDown(key, { button: 0, pointerId: 4, pointerType: "touch" });
    act(() => vi.advanceTimersByTime(500));
    const balance = screen.getByRole("tooltip", { name: "Account balance" });
    expect(balance).toHaveTextContent("Deposit 90 USD");
    expect(balance).toHaveTextContent("Available 70 USD");
    expect(balance).not.toHaveTextContent(/100|BTCUSDT|o1/);
  });

  it("dismisses PAPER Accounts only by explicit close, backdrop, or Escape", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => catalog });
    vi.stubGlobal("fetch", fetchMock);
    function Harness() {
      const [open, setOpen] = useState(true);
      return <AccountMenu open={open} onToggle={() => setOpen((current) => !current)} />;
    }
    render(<Harness />);
    const dialog = await screen.findByRole("dialog", { name: "Accounts" });
    const backdrop = screen.getByTestId("account-menu-backdrop");
    expect(backdrop).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close Accounts" }).parentElement)
      .toBe(dialog.querySelector("header"));

    fireEvent.pointerDown(dialog);
    expect(screen.getByRole("dialog", { name: "Accounts" })).toBeInTheDocument();
    fireEvent.pointerDown(backdrop);
    expect(screen.queryByTestId("account-menu-backdrop")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Open account selection" }));
    expect(await screen.findByText("Current")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close Accounts" }));
    expect(screen.queryByTestId("account-menu-backdrop")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Open account selection" }));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByTestId("account-menu-backdrop")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls.every(([, options]) => options?.method === undefined)).toBe(true);
  });

  it("renders the authoritative account and keeps add-account credentials ephemeral", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => catalog }));
    const { rerender } = render(<AccountMenu open onToggle={vi.fn()} />);
    expect(await screen.findAllByText("Paper / Virtual")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Open account selection" })).toHaveTextContent("PAPER");
    expect(screen.getByText("Current")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Current account golden key" }).closest("article"))
      .toHaveTextContent("Paper / Virtual");
    expect(document.querySelectorAll(".account-switch-key")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "+ Add account" }));
    fireEvent.change(screen.getByLabelText("API Secret"), { target: { value: "never-store-me" } });
    expect(screen.getByLabelText("API Secret")).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "Add account" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Close add account" }));
    fireEvent.click(screen.getByRole("button", { name: "+ Add account" }));
    expect(screen.getByLabelText("API Secret")).toHaveValue("");
    rerender(<AccountMenu open={false} onToggle={vi.fn()} />);
  });

  it("fails closed when the catalog is invalid", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true, accounts: [] }) }));
    function Harness() {
      const [open, setOpen] = useState(true);
      return <AccountMenu open={open} onToggle={() => setOpen((current) => !current)} />;
    }
    render(<Harness />);
    await waitFor(() => expect(screen.getAllByText("UNAVAILABLE").length).toBeGreaterThan(0));
    expect(screen.getByRole("alert")).toHaveTextContent("Account catalog unavailable");
  });

  it("submits credentials once, refreshes catalog, and clears the dialog on success", async () => {
    const withBybit = { ...catalog, accounts: [...catalog.accounts, {
      id: "bybit-1", display_name: "Main", provider: "BYBIT", environment: "MAINNET", status: "READY",
    }] };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => catalog })
      .mockResolvedValueOnce({ ok: true, json: async () => ({
        ok: true, account_id: "bybit-1", created: true,
        account: { id: "bybit-1", display_name: "Main", provider: "BYBIT", environment: "MAINNET", status: "READY" },
      }) })
      .mockResolvedValueOnce({ ok: true, json: async () => withBybit });
    vi.stubGlobal("fetch", fetchMock);
    render(<AccountMenu open onToggle={vi.fn()} />);
    await screen.findByText("Current");
    fireEvent.click(screen.getByRole("button", { name: "+ Add account" }));
    fireEvent.change(screen.getByLabelText("Account name"), { target: { value: "Main" } });
    fireEvent.change(screen.getByLabelText("API Key"), { target: { value: "key" } });
    fireEvent.change(screen.getByLabelText("API Secret"), { target: { value: "secret" } });
    fireEvent.click(screen.getByRole("button", { name: "Add account" }));
    await screen.findByText("Main");
    expect(screen.queryByRole("dialog", { name: "Add account" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls[1][1].body).toContain('"api_secret":"secret"');
    expect(screen.getAllByText("Current")).toHaveLength(1);
  });

  it("keeps the dialog open and uses a normalized safe error message", async () => {
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => catalog })
      .mockResolvedValueOnce({ ok: false, json: async () => ({ ok: false, error: "bybit_validation_failed" }) }));
    render(<AccountMenu open onToggle={vi.fn()} />);
    await screen.findByText("Current");
    fireEvent.click(screen.getByRole("button", { name: "+ Add account" }));
    for (const [label, value] of [["Account name", "Main"], ["API Key", "key"], ["API Secret", "secret"]]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    }
    fireEvent.click(screen.getByRole("button", { name: "Add account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bybit rejected these credentials.");
    expect(screen.getByLabelText("API Secret")).toHaveValue("secret");
  });

  it("visually classifies non-tradable and unverified account statuses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({
      ...catalog,
      accounts: [
        ...catalog.accounts,
        { id: "read", display_name: "Read only", provider: "BYBIT", environment: "MAINNET", status: "READ_ONLY" },
        { id: "cold", display_name: "Needs validation", provider: "BYBIT", environment: "TESTNET", status: "DISCONNECTED" },
      ],
    }) }));
    render(<AccountMenu open onToggle={vi.fn()} />);
    expect((await screen.findByText("Read only")).closest("article")).toHaveClass("status-read_only");
    expect(screen.getByText("Needs validation").closest("article")).toHaveClass("status-disconnected");
    expect(screen.getAllByText("Current")).toHaveLength(1);
  });

  it("reconciles an inactive Bybit account without switching PAPER", async () => {
    const disconnected = { ...catalog, accounts: [...catalog.accounts, {
      id: "bybit-1", display_name: "Main", provider: "BYBIT", environment: "MAINNET", status: "DISCONNECTED",
    }] };
    const ready = { ...disconnected, accounts: [disconnected.accounts[0], { ...disconnected.accounts[1], status: "READY" }] };
    const summary = {
      account_id: "bybit-1", status: "READY", wallet_balance_usdt: "99",
      total_equity_usdt: "101", position_count: 2, order_count: 3,
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => disconnected })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, summary }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ready });
    vi.stubGlobal("fetch", fetchMock);
    render(<AccountMenu open onToggle={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Reconnect" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Refresh" })).toBeInTheDocument());
    expect(screen.queryByText(/Equity 101 USDT/)).not.toBeInTheDocument();
    expect(screen.queryByText(/2 positions · 3 orders/)).not.toBeInTheDocument();
    expect(screen.getAllByText("Current")).toHaveLength(1);
    expect(fetchMock.mock.calls[1][0]).toBe("/api/accounts/bybit-1/refresh");
    expect(fetchMock.mock.calls[1][1]).toEqual({ method: "POST" });
  });

  it("reconnects and activates a disconnected account by canonical id after confirmation", async () => {
    const account = {
      id: "bybit-canonical-42", display_name: "Main Bybit", provider: "BYBIT",
      environment: "MAINNET", status: "DISCONNECTED",
    };
    const before = { ...catalog, accounts: [...catalog.accounts, account] };
    const summary = {
      account_id: account.id, status: "READY", wallet_balance_usdt: "90",
      total_equity_usdt: "100", position_count: 1, order_count: 2,
    };
    const after = {
      ...before, active_account_id: account.id, session_generation: 20,
      accounts: [{ ...account, status: "READY" }, before.accounts[0]],
    };
    let activated = false;
    const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
      if (url === `/api/accounts/${account.id}/refresh`) {
        return { ok: true, json: async () => ({ ok: true, summary }) };
      }
      if (url === `/api/accounts/${account.id}/activate`) {
        activated = true;
        return { ok: true, json: async () => ({
          ok: true, active_account_id: account.id, session_generation: 20, status: "READY",
        }) };
      }
      if (url.startsWith("/api/workspace/account?")) {
        return { ok: true, json: async () => ({
          ok: true, account_id: account.id, provider: "BYBIT", environment: "MAINNET",
          status: "READY", session_generation: 20, projection_generation: 1,
          read_only: true, wallet_balance_usdt: "90", total_equity_usdt: "100",
          available_balance_usdt: "70", positions: [], orders: [], paper_state: null,
        }) };
      }
      if (url === "/api/accounts" && options?.method === undefined) {
        return { ok: true, json: async () => activated ? after : before };
      }
      return { ok: false, json: async () => ({}) };
    });
    vi.stubGlobal("fetch", fetchMock);
    function Harness() {
      const [open, setOpen] = useState(true);
      return <AccountMenu open={open} onToggle={() => setOpen((current) => !current)} />;
    }
    render(<Harness />);

    fireEvent.click((await screen.findByText("Main Bybit")).closest("article")!);
    fireEvent.click(screen.getByRole("button", { name: "Reconnect & switch account" }));

    await waitFor(() => expect(screen.getAllByText("Current")).toHaveLength(1));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/accounts/bybit-canonical-42/refresh", { method: "POST" },
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/accounts/bybit-canonical-42/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_active_account_id: "paper", expected_session_generation: 1,
        }),
      },
    );
    expect(fetchMock.mock.calls.map(([url]) => url)).not.toContain(
      "/api/accounts/Main%20Bybit/activate",
    );
    expect(document.querySelectorAll(".account-switch-key")).toHaveLength(1);
    expect(screen.getByRole("img", { name: "Current account golden key" }).closest("article"))
      .toHaveTextContent("Main Bybit");
    expect(within(screen.getByRole("dialog", { name: "Accounts" }))
      .getByText("Main Bybit").closest("article")).toHaveTextContent("Current");
    const requestsBeforeClose = fetchMock.mock.calls.length;
    expect(screen.getByTestId("account-menu-backdrop")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close Accounts" }));
    expect(screen.queryByTestId("account-menu-backdrop")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open account selection" }));
    expect(within(screen.getByRole("dialog", { name: "Accounts" }))
      .getByText("Main Bybit").closest("article")).toHaveTextContent("Current");
    expect(fetchMock.mock.calls).toHaveLength(requestsBeforeClose);
  });

  it("keeps failed reconciliation visibly non-ready", async () => {
    const disconnected = { ...catalog, accounts: [...catalog.accounts, {
      id: "bybit-1", display_name: "Main", provider: "BYBIT", environment: "MAINNET", status: "DISCONNECTED",
    }] };
    const failed = { ...disconnected, accounts: [disconnected.accounts[0], { ...disconnected.accounts[1], status: "ERROR" }] };
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => disconnected })
      .mockResolvedValueOnce({ ok: false, json: async () => ({ ok: false, error: "live_account_reconciliation_failed" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => failed }));
    render(<AccountMenu open onToggle={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Reconnect" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Refresh failed; account is not ready.");
    expect(screen.getByText("BYBIT · MAINNET · ERROR")).toBeInTheDocument();
  });

  it("confirms an eligible switch, then renders only the backend Current first with one golden key", async () => {
    const before = { ...catalog, accounts: [...catalog.accounts, {
      id: "bybit-1", display_name: "Main", provider: "BYBIT", environment: "MAINNET", status: "READY",
    }] };
    const after = {
      ...before, active_account_id: "bybit-1", session_generation: 21,
      accounts: [before.accounts[1], before.accounts[0]],
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => before })
      .mockResolvedValueOnce({ ok: true, json: async () => ({
        ok: true, active_account_id: "bybit-1", session_generation: 21, status: "READY",
      }) })
      .mockResolvedValueOnce({ ok: true, json: async () => after });
    vi.stubGlobal("fetch", fetchMock);
    render(<AccountMenu open onToggle={vi.fn()} />);
    fireEvent.click((await screen.findByText("Main")).closest("article")!);
    expect(screen.getByRole("dialog", { name: "Confirm account switch" })).toHaveTextContent("MAINNET");
    fireEvent.click(screen.getByRole("button", { name: "Switch account" }));
    await waitFor(() => expect(screen.getAllByText("Current")).toHaveLength(1));
    expect(document.querySelectorAll(".account-switch-key")).toHaveLength(1);
    expect(screen.getByRole("img", { name: "Current account golden key" }).closest("article"))
      .toHaveTextContent("Main");
    const accountList = screen.getByRole("dialog", { name: "Accounts" });
    expect(within(accountList).getByText("Main").closest("article")).toHaveTextContent("Current");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/accounts/bybit-1/activate");
    expect(fetchMock.mock.calls[1][1]).toEqual({
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expected_active_account_id: "paper", expected_session_generation: 1,
      }),
    });
  });

  it("does not restore stale Current UI when catalog reload fails after a successful switch", async () => {
    const before = { ...catalog, accounts: [...catalog.accounts, {
      id: "bybit-1", display_name: "Main", provider: "BYBIT", environment: "MAINNET", status: "READY",
    }] };
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => before })
      .mockResolvedValueOnce({ ok: true, json: async () => ({
        ok: true, active_account_id: "bybit-1", session_generation: 22, status: "READY",
      }) })
      .mockResolvedValueOnce({ ok: false, json: async () => ({}) }));
    render(<AccountMenu open onToggle={vi.fn()} />);
    fireEvent.click((await screen.findByText("Main")).closest("article")!);
    fireEvent.click(screen.getByRole("button", { name: "Switch account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Account catalog unavailable");
    expect(screen.queryByText("Current")).not.toBeInTheDocument();
    expect(screen.queryByText("previous account remains Current")).not.toBeInTheDocument();
  });
});

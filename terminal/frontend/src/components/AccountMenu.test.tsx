import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AccountMenu } from "./AccountMenu";

const catalog = {
  ok: true,
  active_account_id: "paper",
  session_generation: 1,
  accounts: [{ id: "paper", display_name: "Paper / Virtual", provider: "PAPER", environment: "PAPER", status: "READY" }],
};

afterEach(() => vi.restoreAllMocks());

describe("AccountMenu", () => {
  it("renders the authoritative account and keeps add-account credentials ephemeral", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => catalog }));
    const { rerender } = render(<AccountMenu open onToggle={vi.fn()} />);
    expect(await screen.findAllByText("Paper / Virtual")).toHaveLength(2);
    expect(screen.getByText("Current")).toBeInTheDocument();
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
    render(<AccountMenu open onToggle={vi.fn()} />);
    await waitFor(() => expect(screen.getAllByText("UNAVAILABLE").length).toBeGreaterThan(0));
    expect(screen.getByRole("alert")).toHaveTextContent("Account catalog unavailable");
  });

  it("submits credentials once, refreshes catalog, and clears the dialog on success", async () => {
    const withBybit = { ...catalog, accounts: [...catalog.accounts, {
      id: "bybit-1", display_name: "Main", provider: "BYBIT", environment: "MAINNET", status: "READY",
    }] };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => catalog })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, account_id: "bybit-1", created: true }) })
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
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
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
    expect(await screen.findByText(/Equity 101 USDT/)).toBeInTheDocument();
    expect(screen.getByText(/2 positions · 3 orders/)).toBeInTheDocument();
    expect(screen.getAllByText("Current")).toHaveLength(1);
    expect(fetchMock.mock.calls[1][0]).toBe("/api/accounts/bybit-1/refresh");
    expect(fetchMock.mock.calls[1][1]).toEqual({ method: "POST" });
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
});

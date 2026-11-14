import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AccountMenu } from "./AccountMenu";

const paper = { id: "paper", display_name: "Paper / Virtual", provider: "PAPER", environment: "PAPER", status: "READY" };
const main = { id: "bybit-test", display_name: "My MAIN", provider: "BYBIT", environment: "MAINNET", status: "READY" };
const projection = {
  ok: true as const, account_id: "paper", provider: "PAPER" as const,
  environment: "PAPER", status: "READY", session_generation: 1,
  projection_generation: 1, read_only: false, wallet_balance_usdt: "5000",
  total_equity_usdt: "5000", available_balance_usdt: "5000",
  positions: [], orders: [], paper_state: null,
};

afterEach(() => vi.unstubAllGlobals());

describe("mode-specific account selector", () => {
  function mockCatalog() {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/accounts") return { ok: true, json: async () => ({
        ok: true, active_account_id: "paper", session_generation: 1, accounts: [paper],
      }) };
      if (url === "/api/manual-main/accounts") return { ok: true, json: async () => ({
        ok: true, accounts: [main],
      }) };
      throw new Error(`unexpected endpoint ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("selects MAIN in TERMINAL without ever calling global account activation", async () => {
    const fetchMock = mockCatalog();
    const onSelectAccount = vi.fn(async () => undefined);
    render(<AccountMenu open onToggle={vi.fn()} mode="TERMINAL"
      selectedAccountId="paper" onSelectAccount={onSelectAccount} workspaceProjection={projection} />);
    const select = await screen.findByRole("button", { name: "Select MAIN" });
    fireEvent.click(select);
    expect(screen.getByRole("dialog", { name: "Confirm account switch" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Switch account" }));
    await waitFor(() => expect(onSelectAccount).toHaveBeenCalledWith("TERMINAL", main));
    expect(fetchMock.mock.calls.every(([url]) => !String(url).includes("/activate"))).toBe(true);
  });

  it("AUTOPILOT offers only PAPER, no MAIN account or provisioning", async () => {
    mockCatalog();
    render(<AccountMenu open onToggle={vi.fn()} mode="AUTOPILOT"
      selectedAccountId="paper" onSelectAccount={vi.fn()} workspaceProjection={projection} />);
    await screen.findByRole("dialog", { name: "Accounts" });
    expect(screen.getByText("Paper / Virtual")).toBeInTheDocument();
    expect(screen.queryByText("My MAIN")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Select MAIN|Add MAIN account/ })).not.toBeInTheDocument();
  });
});

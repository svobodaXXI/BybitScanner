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

  it("offers refresh for a disconnected MAIN, reports progress, and leaves PAPER selected", async () => {
    let connected = false;
    let resolveRefresh!: () => void;
    const pendingRefresh = new Promise<void>((resolve) => { resolveRefresh = resolve; });
    const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
      if (url === "/api/accounts") return { ok: true, json: async () => ({
        ok: true, active_account_id: "paper", session_generation: 1, accounts: [paper],
      }) };
      if (url === "/api/manual-main/accounts") return { ok: true, json: async () => ({
        ok: true, accounts: [{ ...main, status: connected ? "READ_ONLY" : "DISCONNECTED" }],
      }) };
      if (url === "/api/manual-main/accounts/bybit-test/refresh" && options?.method === "POST") {
        await pendingRefresh;
        connected = true;
        return { ok: true, json: async () => ({ ok: true }) };
      }
      throw new Error("unexpected endpoint");
    });
    vi.stubGlobal("fetch", fetchMock);
    const onSelectAccount = vi.fn(async () => undefined);
    render(<AccountMenu open onToggle={vi.fn()} mode="TERMINAL"
      selectedAccountId="paper" onSelectAccount={onSelectAccount} workspaceProjection={projection} />);
    const refresh = await screen.findByRole("button", { name: "Refresh MAIN" });
    expect(refresh).toBeEnabled();
    expect(screen.getByRole("button", { name: "Select MAIN" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "All MAIN positions" })).toBeEnabled();
    expect(screen.getByLabelText("Manual MAIN account")).toHaveClass("status-disconnected");
    fireEvent.click(refresh);
    expect(screen.getByRole("button", { name: "Refreshing MAIN…" })).toBeDisabled();
    resolveRefresh();
    await waitFor(() => expect(screen.getByRole("button", { name: "Refresh MAIN" })).toBeEnabled());
    expect(screen.getByLabelText("Manual MAIN account")).toHaveClass("status-read_only");
    expect(screen.getByText("Текущий")).toBeInTheDocument();
    expect(onSelectAccount).not.toHaveBeenCalled();
    expect(fetchMock.mock.calls.filter(([, options]) => options?.method === "POST")).toEqual([
      ["/api/manual-main/accounts/bybit-test/refresh", { method: "POST" }],
    ]);
  });

  it("marks only the selected account current in each workspace", async () => {
    const fetchMock = mockCatalog();
    const onSelectAccount = vi.fn(async () => undefined);
    const onToggle = vi.fn();
    const mainProjection = { ...projection, account_id: main.id, provider: "BYBIT" as const,
      environment: "MAINNET" as const, read_only: true };
    const { rerender, container } = render(<AccountMenu open onToggle={onToggle} mode="TERMINAL"
      selectedAccountId="paper" onSelectAccount={onSelectAccount} workspaceProjection={projection} />);
    await screen.findByRole("button", { name: "Select MAIN" });
    const paperCard = screen.getByText("Paper / Virtual").closest("article");
    const mainCard = screen.getByLabelText("Manual MAIN account");
    expect(paperCard).toHaveClass("is-verified-current");
    expect(paperCard).toHaveTextContent("PAPER · READY");
    expect(paperCard).not.toHaveTextContent("PAPER · PAPER");
    expect(paperCard).not.toHaveTextContent("Подключён к Роботу");
    expect(mainCard).not.toHaveClass("is-current");
    rerender(<AccountMenu open onToggle={onToggle} mode="TERMINAL"
      selectedAccountId={main.id} otherWorkspaceAccountId="paper" onSelectAccount={onSelectAccount} workspaceProjection={mainProjection} />);
    expect(mainCard).toHaveClass("is-verified-current");
    expect(paperCard).not.toHaveClass("is-current");
    expect(paperCard).toHaveTextContent("Подключён к Роботу");
    expect(paperCard).not.toHaveTextContent("Текущий");
    expect(paperCard?.querySelector(".account-ready-status")).toHaveTextContent("READY");
    expect(paperCard?.querySelector(".account-role-connected")).toHaveTextContent("Подключён к Роботу");
    expect(container.querySelector(".account-card")).toBe(mainCard);
    expect(container.querySelectorAll('[aria-current="true"]')).toHaveLength(1);
    expect(screen.getAllByText("Текущий")).toHaveLength(1);
    rerender(<AccountMenu open onToggle={onToggle} mode="TERMINAL"
      selectedAccountId={main.id} otherWorkspaceAccountId="paper" onSelectAccount={onSelectAccount} workspaceProjection={null} />);
    expect(mainCard).toHaveClass("is-current");
    expect(mainCard).not.toHaveClass("is-verified-current");
    expect(paperCard).not.toHaveClass("is-current");
    rerender(<AccountMenu open onToggle={onToggle} mode="AUTOPILOT"
      selectedAccountId="paper" otherWorkspaceAccountId={main.id} onSelectAccount={onSelectAccount} workspaceProjection={projection} />);
    expect(paperCard).toHaveClass("is-verified-current");
    expect(paperCard).not.toHaveTextContent("Подключён к Роботу");
    expect(screen.getByLabelText("Manual MAIN account")).toHaveTextContent("Подключён к Терминалу");
    expect(container.querySelector(".account-card")).toBe(paperCard);
    expect(screen.queryByRole("button", { name: /Select MAIN|Refresh MAIN|All MAIN positions/ })).not.toBeInTheDocument();
    expect(container.querySelectorAll('[aria-current="true"]')).toHaveLength(1);
    expect(onSelectAccount).not.toHaveBeenCalled();
    expect(fetchMock.mock.calls.every(([url]) => !String(url).includes("/activate"))).toBe(true);
  });

  it("AUTOPILOT shows MAIN for information only, without MAIN controls or provisioning", async () => {
    mockCatalog();
    render(<AccountMenu open onToggle={vi.fn()} mode="AUTOPILOT"
      selectedAccountId="paper" onSelectAccount={vi.fn()} workspaceProjection={projection} />);
    await screen.findByRole("dialog", { name: "Accounts" });
    expect(screen.getByText("Paper / Virtual")).toBeInTheDocument();
    expect(await screen.findByText("My MAIN")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Select MAIN|Refresh MAIN|All MAIN positions|Add New Account/ })).not.toBeInTheDocument();
  });
});

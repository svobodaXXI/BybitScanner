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
});

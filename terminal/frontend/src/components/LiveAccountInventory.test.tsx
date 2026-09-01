import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AccountWorkspaceProjection } from "../accountWorkspace/accountWorkspaceStore";
import { LiveAccountInventory } from "./LiveAccountInventory";

const projection: AccountWorkspaceProjection = {
  ok: true,
  account_id: "bybit-main",
  provider: "BYBIT",
  environment: "MAINNET",
  status: "READY",
  session_generation: 2,
  projection_generation: 7,
  read_only: true,
  wallet_balance_usdt: "90",
  total_equity_usdt: "100",
  available_balance_usdt: "70",
  positions: [{ symbol: "BTCUSDT", side: "Long", size: "1" }],
  orders: [{ order_id: "o1", symbol: "ETHUSDT", side: "Buy", quantity: "2", price: "2000" }],
  paper_state: null,
};

describe("LiveAccountInventory", () => {
  it("provides symbol navigation only and exposes no PAPER mutation controls", () => {
    const onNavigate = vi.fn();
    render(<LiveAccountInventory projection={projection} onNavigate={onNavigate} />);

    fireEvent.click(screen.getByRole("button", { name: /BTCUSDT/ }));
    fireEvent.click(screen.getByRole("button", { name: /ETHUSDT/ }));
    expect(onNavigate.mock.calls).toEqual([["BTCUSDT"], ["ETHUSDT"]]);
    expect(screen.queryByRole("button", { name: /close|cancel/i })).not.toBeInTheDocument();
    expect(screen.getByText(/Equity 100 · Wallet 90 USDT/)).toBeInTheDocument();
  });
});

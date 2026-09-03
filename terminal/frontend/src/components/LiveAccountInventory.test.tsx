import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AccountWorkspaceProjection } from "../accountWorkspace/accountWorkspaceStore";
import { LiveAccountInventory } from "./LiveAccountInventory";

const projection: AccountWorkspaceProjection = {
  ok: true, account_id: "bybit-main", provider: "BYBIT", environment: "MAINNET", status: "READY",
  session_generation: 2, projection_generation: 7, read_only: false,
  one_wv_usdt: "50",
  wallet_balance_usdt: "342.75481", total_equity_usdt: "89.7867", available_balance_usdt: "89.7867",
  positions: [
    { symbol: "HOMEUSDT", side: "Long", size: "35300", average_entry: "0.0103691", mark_price: "0.0061085", unrealized_pnl: "-150.34638063", engaged_wv: "1.2" },
    { symbol: "ETHUSDT", side: "Short", size: "2", average_entry: "3500", mark_price: "3400", unrealized_pnl: "200", engaged_wv: "2.3" },
  ], orders: [], paper_state: null,
};
const props = { activeAccountName: "Main Bybit", activeSymbol: "HOMEUSDT", onClose: vi.fn(), onNavigate: vi.fn() };

describe("LiveAccountInventory", () => {
  it("renders a body-level mobile surface with positions and account summary", () => {
    render(<main data-testid="workspace"><LiveAccountInventory projection={projection} {...props} /></main>);
    expect(screen.getByTestId("live-positions-surface").parentElement).toBe(document.body);
    expect(screen.getByRole("dialog", { name: "Открытые позиции" })).toHaveTextContent("Main Bybit");
    const summary = screen.getByLabelText("Сводка активного счёта");
    expect(summary).toHaveTextContent(/Wallet.*342\.75.*Equity.*89\.79.*⚔ 3\.5.*7015\.63 USDT/);
    expect(summary).not.toHaveTextContent("Available");
    const home = screen.getByRole("button", { name: /^Открыть HOMEUSDT/ }).closest("article")!;
    expect(home.querySelector(".live-position-pnl strong")).toHaveTextContent("-150.35 USDT");
    expect(home.querySelector(".live-position-pnl small")).toHaveTextContent("−41.07%");
    expect(home).toHaveTextContent("Объём 35300 HOME · 215.63 USDT");
    expect(home).toHaveTextContent("Цена 0.0103691Mark 0.0061085");
    expect(home).not.toHaveTextContent(/\bSize\b|\bEntry\b/);
    expect(screen.getByRole("button", { name: /^Открыть ETHUSDT/ }).closest("article")).toHaveTextContent("ETHUSDTSHORT");
    expect(screen.queryByRole("button", { name: /Wallet|Equity|РО|Mark Price/ })).not.toBeInTheDocument();
  });

  it("shows neutral states and replaces stale account/session rows", () => {
    const onNavigate = vi.fn();
    const renderProps = { ...props, onNavigate };
    const { rerender } = render(<LiveAccountInventory projection={null} {...renderProps} />);
    expect(screen.getByRole("status")).toHaveTextContent("Позиции временно недоступны");
    rerender(<LiveAccountInventory projection={{ ...projection, positions: [] }} {...renderProps} />);
    expect(screen.getByRole("status")).toHaveTextContent("Нет открытых позиций");
    expect(screen.getByLabelText("Сводка активного счёта")).toHaveTextContent(/⚔ 0\.0.*0\.00 USDT/);
    rerender(<LiveAccountInventory projection={{ ...projection, account_id: "bybit-next", session_generation: 3,
      positions: [{ symbol: "SOLUSDT", side: "Long", size: "4", average_entry: "100", mark_price: "110", unrealized_pnl: "40", engaged_wv: "0.4" }] }} {...renderProps} />);
    expect(screen.queryByText("BTCUSDT")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Сводка активного счёта")).toHaveTextContent(/⚔ 0\.4.*440\.00 USDT/);
    expect(screen.getByLabelText("Сводка активного счёта")).not.toHaveTextContent("⚔ 3.5");
    fireEvent.click(screen.getByRole("button", { name: /^Открыть SOLUSDT/ }));
    expect(onNavigate).toHaveBeenCalledWith("SOLUSDT");
  });

  it("fails closed when authoritative engaged WV is unavailable", () => {
    render(<LiveAccountInventory projection={{ ...projection, positions: [
      { symbol: "BTCUSDT", side: "Long", size: "10", average_entry: "100", mark_price: "110", unrealized_pnl: "100", engaged_wv: null },
    ] }} {...props} activeSymbol="BTCUSDT" />);

    const summary = screen.getByLabelText("Сводка активного счёта");
    expect(summary).toHaveTextContent(/⚔ —.*1100\.00 USDT/);
    expect(summary).not.toHaveTextContent("⚔ 22.0");
  });

  it("renders numeric total from valid authoritative engaged WV payload fields", () => {
    render(<LiveAccountInventory projection={{ ...projection, positions: [
      { symbol: "BTCUSDT", size: "1", mark_price: "100", engaged_wv: 2.4 },
      { symbol: "ETHUSDT", size: "1", mark_price: "26.35", engaged_wv: "5.0" },
      { symbol: "SOLUSDT", size: "1", mark_price: "0", engaged_wv: null },
    ] }} {...props} />);

    expect(screen.getByLabelText("Сводка активного счёта")).toHaveTextContent(/⚔ 7\.4.*126\.35 USDT/);
  });

  it("pins the active symbol then sorts a derived view by absolute current value", () => {
    const sourcePositions = [
      { symbol: "ETHUSDT", side: "Short", size: "-2", mark_price: "200", average_entry: "210", unrealized_pnl: "20", engaged_wv: "1" },
      { symbol: "SOLUSDT", side: "Long", size: "3", mark_price: "100", average_entry: "90", unrealized_pnl: "30", engaged_wv: "1" },
      { symbol: "HOMEUSDT", side: "Long", size: "1", mark_price: "1", average_entry: "1", unrealized_pnl: "0", engaged_wv: "1" },
      { symbol: "XRPUSDT", side: "Short", size: "-50", mark_price: "2", average_entry: "2.1", unrealized_pnl: "5", engaged_wv: "1" },
    ];
    const originalOrder = sourcePositions.map((position) => position.symbol);
    const orderedProjection = { ...projection, positions: sourcePositions };
    const { rerender } = render(<LiveAccountInventory projection={orderedProjection} {...props} />);

    const symbols = () => screen.getAllByRole("button", { name: /^Открыть .* в Trading Workspace$/ })
      .map((button) => button.getAttribute("aria-label")?.split(" ")[1]);
    expect(symbols()).toEqual(["HOMEUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]);
    expect(screen.getByRole("button", { name: /^Открыть HOMEUSDT/ }).closest("article"))
      .toHaveClass("active-separated");
    expect(sourcePositions.map((position) => position.symbol)).toEqual(originalOrder);

    rerender(<LiveAccountInventory projection={orderedProjection} {...props} activeSymbol="XRPUSDT" />);
    expect(symbols()).toEqual(["XRPUSDT", "ETHUSDT", "SOLUSDT", "HOMEUSDT"]);
    expect(screen.getByRole("button", { name: /^Открыть XRPUSDT/ }).closest("article"))
      .toHaveClass("active-separated");

    rerender(<LiveAccountInventory projection={orderedProjection} {...props} activeSymbol="BTCUSDT" />);
    expect(symbols()).toEqual(["ETHUSDT", "SOLUSDT", "XRPUSDT", "HOMEUSDT"]);
    expect(document.querySelector(".active-separated")).not.toBeInTheDocument();
  });
});

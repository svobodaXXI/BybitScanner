import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceHeader } from "./WorkspaceHeader";

describe("workspace header", () => {
  it("shows tappable ticker and timeframe without the former account strip control", () => {
    const onSymbolClick = vi.fn();
    const onTimeframeChange = vi.fn();
    render(
      <WorkspaceHeader
        instruments={["ONGUSDT", "BTCUSDT", "ETHUSDT"]}
        onSymbolSelect={onSymbolClick}
        onTimeframeChange={onTimeframeChange}
        symbol="ONGUSDT"
        timeframe="5m"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Select symbol ONGUSDT" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Поиск инструмента" }), { target: { value: "btc" } });
    expect(screen.getAllByRole("option").map((item) => item.textContent)).toEqual(["BTCUSDT"]);
    expect(onSymbolClick).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("option", { name: "BTCUSDT" }));
    expect(onSymbolClick).toHaveBeenCalledWith("BTCUSDT");
    expect(screen.getByText("5m")).toBeInTheDocument();
    expect(screen.queryByText(/TRADING WORKSPACE/i)).toBeNull();
    expect(screen.queryByRole("button", { name: "Open account selection" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Select chart timeframe" }));
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
      "15s", "1m", "5m", "15m", "1h", "1d",
    ]);
    fireEvent.click(screen.getByRole("menuitem", { name: "15m" }));
    expect(onTimeframeChange).toHaveBeenCalledWith("15m");
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("dismisses the timeframe menu only on outside pointer or Escape", () => {
    render(
      <WorkspaceHeader
        instruments={["ONGUSDT"]}
        onSymbolSelect={vi.fn()}
        onTimeframeChange={vi.fn()}
        symbol="ONGUSDT"
        timeframe="5m"
      />,
    );
    const trigger = screen.getByRole("button", { name: "Select chart timeframe" });
    fireEvent.click(trigger);
    fireEvent.pointerDown(screen.getByRole("menu"));
    expect(screen.getByRole("menu")).toBeInTheDocument();
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("menu")).toBeNull();
    fireEvent.click(trigger);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    fireEvent.click(trigger);
    fireEvent.click(trigger);
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("formats only the display label while preserving canonical symbol selection", () => {
    const onSymbolSelect = vi.fn();
    const { rerender } = render(
      <WorkspaceHeader
        instruments={["BTCUSDT", "BTCUSD"]}
        onSymbolSelect={onSymbolSelect}
        onTimeframeChange={vi.fn()}
        symbol="BTCUSDT"
        timeframe="5m"
      />,
    );
    expect(screen.getByRole("button", { name: "Select symbol BTCUSDT" })).toHaveTextContent("BTC");
    fireEvent.click(screen.getByRole("button", { name: "Select symbol BTCUSDT" }));
    fireEvent.click(screen.getByRole("option", { name: "BTCUSDT" }));
    expect(onSymbolSelect).toHaveBeenCalledWith("BTCUSDT");

    rerender(
      <WorkspaceHeader
        instruments={["BTCUSD"]}
        onSymbolSelect={onSymbolSelect}
        onTimeframeChange={vi.fn()}
        symbol="BTCUSD"
        timeframe="5m"
      />,
    );
    expect(screen.getByRole("button", { name: "Select symbol BTCUSD" })).toHaveTextContent("BTCUSD");
  });
});

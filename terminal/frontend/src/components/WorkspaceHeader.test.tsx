import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceHeader } from "./WorkspaceHeader";

describe("workspace header", () => {
  it("shows only tappable ticker, timeframe, and account control", () => {
    const onSymbolClick = vi.fn();
    const onTimeframeChange = vi.fn();
    render(
      <WorkspaceHeader
        accountOpen={false}
        onAccountToggle={vi.fn()}
        onSymbolClick={onSymbolClick}
        onTimeframeChange={onTimeframeChange}
        symbol="ONGUSDT"
        timeframe="5m"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Select symbol ONGUSDT" }));
    expect(onSymbolClick).toHaveBeenCalledOnce();
    expect(screen.getByText("5m")).toBeInTheDocument();
    expect(screen.queryByText(/TRADING WORKSPACE/i)).toBeNull();
    expect(screen.getByRole("button", { name: "Open account selection" })).toBeInTheDocument();

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
        accountOpen={false}
        onAccountToggle={vi.fn()}
        onSymbolClick={vi.fn()}
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
});

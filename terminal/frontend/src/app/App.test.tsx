import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createDemoMarketData } from "../marketData/demoFeed";
import { App } from "./App";

describe("Trading Workspace runnable prototype", () => {
  it("switches modes while keeping the shared chart mounted", () => {
    render(<App />);
    expect(
      screen.getByLabelText("Interactive market chart"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "AUTOPILOT" }));
    expect(screen.getByLabelText("AUTOPILOT controls")).toBeInTheDocument();
    expect(
      screen.getByLabelText("Interactive market chart"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "BTCUSDT" }),
    ).toBeInTheDocument();
  });

  it("centers, locks, and unlocks CENTER on manual DOM movement", () => {
    render(<App />);
    const center = screen.getByRole("button", { name: "CENTER" });
    fireEvent.doubleClick(center);
    expect(center).toHaveAttribute("aria-pressed", "true");
    fireEvent.wheel(
      screen
        .getByLabelText("DOM order book")
        .querySelector(".dom-ladder") as Element,
      { deltaY: 10 },
    );
    expect(center).toHaveAttribute("aria-pressed", "false");
  });

  it("keeps ordinary DOM clicks non-trading and cancels only a selected fixture dot", () => {
    render(<App />);
    expect(screen.getByText("500 USDT")).toBeInTheDocument();
    const dots = screen.getAllByRole("button", {
      name: /Cancel fixture order paper-buy/,
    });
    const dom = screen.getByLabelText("DOM order book");
    fireEvent.click(within(dom).getByText("64249.0"));
    expect(
      screen.getAllByRole("button", { name: /Cancel fixture order paper-buy/ }),
    ).toHaveLength(3);
    fireEvent.click(dots[1]);
    expect(screen.getByText("350 USDT")).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: /Cancel fixture order paper-buy/ }),
    ).toHaveLength(2);
  });

  it("provides a depth-extensible normalized development adapter", () => {
    const snapshot = createDemoMarketData();
    expect(snapshot.source).toBe("DEVELOPMENT");
    expect(snapshot.book.availableDepth).toBe(50);
    expect(snapshot.book.bids).toHaveLength(50);
    expect(snapshot.book.asks).toHaveLength(50);
    expect(snapshot.trades.length).toBeGreaterThan(0);
  });
});

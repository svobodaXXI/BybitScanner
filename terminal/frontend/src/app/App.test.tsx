import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "./App";

describe("Trading Workspace foundation", () => {
  it("renders the paper-only structural shell", () => {
    render(<App />);

    expect(
      screen.getByRole("heading", { name: "BTCUSDT" }),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("Execution mode: paper, non-live"),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Chart" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "DOM / Order book" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Trading controls" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Execution: PAPER foundation only"),
    ).toBeInTheDocument();
  });
});

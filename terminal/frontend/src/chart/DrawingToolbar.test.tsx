import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DrawingToolbar } from "./DrawingToolbar";

describe("drawing toolbar", () => {
  it("exposes active tools, magnet state, and selection actions", () => {
    const onTool = vi.fn();
    const onMagnet = vi.fn();
    render(
      <DrawingToolbar
        activeTool="trend"
        magnet={true}
        selected={false}
        onTool={onTool}
        onMagnet={onMagnet}
        onDelete={vi.fn()}
        onUndo={vi.fn()}
        onRedo={vi.fn()}
        onClear={vi.fn()}
        onLock={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Trend line" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Magnet" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(
      screen.getByRole("button", { name: "Delete selected drawing" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Horizontal line" }));
    fireEvent.click(screen.getByRole("button", { name: "Magnet" }));
    expect(onTool).toHaveBeenCalledWith("horizontal");
    expect(onMagnet).toHaveBeenCalledOnce();
  });
});

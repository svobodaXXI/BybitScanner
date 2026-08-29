import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DrawingToolbar } from "./DrawingToolbar";

describe("drawing toolbar", () => {
  it("exposes only the approved drawing controls", () => {
    const onTool = vi.fn();
    const onMagnet = vi.fn();
    render(
      <DrawingToolbar
        activeTool="trend"
        magnet={true}
        selected={false}
        onTool={onTool}
        onMagnet={onMagnet}
        onUndo={vi.fn()}
        onDelete={vi.fn()}
        onClear={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Straight line" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Magnet" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getAllByRole("button").map((button) => button.getAttribute("aria-label"))).toEqual([
      "Hide drawing tools",
      "Crosshair / chart interaction",
      "Straight line",
      "Horizontal line",
      "Ray",
      "Horizontal ray",
      "Fibonacci grid",
      "Magnet",
      "Undo drawing",
      "Clear drawings",
    ]);
    expect(screen.queryByRole("button", { name: "Vertical line" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Ruler" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Rectangle" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Redo drawing" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Lock selected drawing" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete selected drawing" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Horizontal line" }));
    fireEvent.click(screen.getByRole("button", { name: "Magnet" }));
    expect(onTool).toHaveBeenCalledWith("horizontal");
    expect(onMagnet).toHaveBeenCalledOnce();
  });

  it("shows delete selected only while a drawing is selected", () => {
    const onDelete = vi.fn();
    render(
      <DrawingToolbar
        activeTool="select"
        magnet={false}
        selected={true}
        onTool={vi.fn()}
        onMagnet={vi.fn()}
        onUndo={vi.fn()}
        onDelete={onDelete}
        onClear={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete selected drawing" }));
    expect(onDelete).toHaveBeenCalledOnce();
  });

  it("collapses to one compact toggle and restores the drawing controls", () => {
    render(
      <DrawingToolbar
        activeTool="select"
        magnet={false}
        selected={false}
        onTool={vi.fn()}
        onMagnet={vi.fn()}
        onUndo={vi.fn()}
        onDelete={vi.fn()}
        onClear={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Hide drawing tools" }));
    expect(screen.queryByRole("navigation", { name: "Drawing tools" })).toBeNull();
    expect(screen.getAllByRole("button")).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "Show drawing tools" }));
    expect(screen.getByRole("navigation", { name: "Drawing tools" })).toBeInTheDocument();
  });
});

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DrawingClearConfirmation } from "./DrawingClearConfirmation";

describe("drawing clear confirmation", () => {
  it("cancels or confirms through custom controls", () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    render(
      <DrawingClearConfirmation onCancel={onCancel} onConfirm={onConfirm} />,
    );
    expect(screen.getByText("Удалить все фигуры?")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Отмена" }));
    fireEvent.click(screen.getByRole("button", { name: "Удалить" }));
    expect(onCancel).toHaveBeenCalledOnce();
    expect(onConfirm).toHaveBeenCalledOnce();
  });
});

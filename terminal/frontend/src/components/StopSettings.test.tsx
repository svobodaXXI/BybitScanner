import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { StopSettings } from "./StopSettings";

it("links Percent and Price and applies only through its local callback", () => {
  const onApply = vi.fn();
  const onPresetChange = vi.fn();
  render(
    <StopSettings side="Long" referencePrice="100" tickSize="0.5" presetPercent="2" onPresetChange={onPresetChange} onApply={onApply} onClose={vi.fn()} />,
  );
  expect(screen.getByText("100")).toBeInTheDocument();
  expect(screen.getByLabelText("STOP Price")).toHaveValue("98");

  fireEvent.change(screen.getByLabelText("STOP Percent"), { target: { value: "3" } });
  expect(screen.getByLabelText("STOP Price")).toHaveValue("97");
  expect(onPresetChange).toHaveBeenLastCalledWith("3");
  fireEvent.change(screen.getByLabelText("STOP Price"), { target: { value: "96.7" } });
  expect(screen.getByLabelText("STOP Price")).toHaveValue("97");
  expect(screen.getByLabelText("STOP Percent")).toHaveValue("3");
  expect(onPresetChange).toHaveBeenLastCalledWith("3");

  fireEvent.click(screen.getByRole("button", { name: "Apply" }));
  expect(onApply).toHaveBeenCalledWith("97", "3");
});

it("reuses linked normalized settings for TAKE", () => {
  const onApply = vi.fn();
  render(
    <StopSettings leg="TAKE" side="Short" referencePrice="100" tickSize="0.5" presetPercent="3" onPresetChange={vi.fn()} onApply={onApply} onClose={vi.fn()} />,
  );
  expect(screen.getByLabelText("TAKE Price")).toHaveValue("97");
  fireEvent.change(screen.getByLabelText("TAKE Percent"), { target: { value: "4" } });
  expect(screen.getByLabelText("TAKE Price")).toHaveValue("96");
  fireEvent.click(screen.getByRole("button", { name: "Apply" }));
  expect(onApply).toHaveBeenCalledWith("96", "4");
});

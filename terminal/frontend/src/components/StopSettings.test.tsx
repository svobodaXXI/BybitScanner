import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { StopSettings } from "./StopSettings";

it("links Percent and Price and confirms STOP through the checkmark", () => {
  const onApply = vi.fn();
  const onPresetChange = vi.fn();
  const onClose = vi.fn();
  render(
    <StopSettings side="Long" referencePrice="100.037" tickSize="0.5" presetPercent="2" onPresetChange={onPresetChange} onApply={onApply} onClose={onClose} />,
  );
  expect(screen.getByText("Тек. цена")).toBeInTheDocument();
  expect(screen.getByText("100.0")).toBeInTheDocument();
  expect(screen.getByLabelText("STOP Percent")).toHaveValue("1.5");
  expect(screen.getByLabelText("STOP Price")).toHaveValue("98.5");

  fireEvent.change(screen.getByLabelText("STOP Percent"), { target: { value: "3" } });
  expect(screen.getByLabelText("STOP Price")).toHaveValue("97.5");
  expect(screen.getByLabelText("STOP Percent")).toHaveValue("2.5");
  expect(onPresetChange).toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("STOP Price"), { target: { value: "96.7" } });
  expect(screen.getByLabelText("STOP Price")).toHaveValue("97");
  expect(screen.getByLabelText("STOP Percent")).toHaveValue("3.0");

  fireEvent.click(screen.getByRole("button", { name: "Confirm STOP" }));
  expect(onApply).toHaveBeenCalledWith("97", "3.0");
  fireEvent.click(screen.getByRole("button", { name: "Cancel STOP draft" }));
  expect(onClose).toHaveBeenCalledTimes(1);
});

it("mirrors linked normalized settings and checkmark controls for TAKE", () => {
  const onApply = vi.fn();
  const onClose = vi.fn();
  render(
    <StopSettings leg="TAKE" side="Short" referencePrice="100" tickSize="0.5" presetPercent="3" onPresetChange={vi.fn()} onApply={onApply} onClose={onClose} />,
  );
  expect(screen.getByLabelText("TAKE Percent")).toHaveValue("3.0");
  expect(screen.getByLabelText("TAKE Price")).toHaveValue("97");
  fireEvent.change(screen.getByLabelText("TAKE Percent"), { target: { value: "4" } });
  expect(screen.getByLabelText("TAKE Price")).toHaveValue("96");
  expect(screen.getByLabelText("TAKE Percent")).toHaveValue("4.0");
  fireEvent.click(screen.getByRole("button", { name: "Confirm TAKE" }));
  expect(onApply).toHaveBeenCalledWith("96", "4.0");
  fireEvent.click(screen.getByRole("button", { name: "Cancel TAKE draft" }));
  expect(onClose).toHaveBeenCalledTimes(1);
});

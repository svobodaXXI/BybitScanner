import { expect, test } from "@playwright/test";

test("chart workspace renders tools and remains usable at mobile width", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByLabel("Interactive market chart")).toBeVisible();
  await expect(page.getByLabel("Drawing tools")).toBeVisible();
  await page.getByRole("button", { name: "Horizontal line" }).click();
  await expect(
    page.getByRole("button", { name: "Horizontal line" }),
  ).toHaveAttribute("aria-pressed", "true");
  const chart = page.getByLabel("Interactive market chart");
  const box = await chart.boundingBox();
  expect(box?.width).toBeLessThanOrEqual(390);
  if (box)
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await expect(
    page.getByRole("button", { name: "Delete selected drawing" }),
  ).toBeEnabled();
});

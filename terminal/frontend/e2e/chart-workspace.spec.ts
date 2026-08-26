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

test("follow-latest button returns the chart to realtime", async ({ page }) => {
  await page.setViewportSize({ width: 1200, height: 800 });
  await page.goto("/");
  const chart = page.getByLabel("Interactive market chart");
  const box = await chart.boundingBox();
  if (!box) throw new Error("chart box unavailable");
  await page.mouse.move(box.x + box.width * 0.55, box.y + box.height * 0.5);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.85, box.y + box.height * 0.5, {
    steps: 8,
  });
  await page.mouse.up();
  const button = page.getByRole("button", { name: "Snap to latest candle" });
  await expect(button).toBeVisible();
  await button.click();
  await page.waitForTimeout(100);
  await expect(button).toBeHidden();
});

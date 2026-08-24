import { type APIRequestContext, expect, test } from "@playwright/test";

const backendUrl = process.env.PAPER_BACKEND_URL;
if (!backendUrl) throw new Error("PAPER_BACKEND_URL is required");

type PaperState = {
  ok: boolean;
  position_side: "Flat" | "Long" | "Short";
  position_quantity: string;
  engaged_notional_usdt: string;
  one_wv_usdt: string;
  engaged_wv: string;
};

async function paperState(request: APIRequestContext) {
  const response = await request.get(
    `${backendUrl}/api/paper-state?symbol=BTCUSDT`,
  );
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as PaperState;
}

test("real PAPER workspace preserves edits and enforces authoritative no-flip behavior", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await expect(page.getByText("Execution: PAPER / non-live")).toBeVisible();

  const initial = await paperState(request);
  expect(initial.ok).toBe(true);
  expect(initial.position_side).toBe("Flat");
  await expect(page.getByLabel("BUY amount")).toHaveValue(initial.one_wv_usdt);
  await expect(page.getByText("0 USDT", { exact: true })).toBeVisible();

  const buyAmount = page.getByLabel("BUY amount");
  await buyAmount.fill("321");
  await page.getByRole("button", { name: "BUY", exact: true }).click();
  await expect(page.getByText("PAPER BUY completed")).toBeVisible();
  await expect(buyAmount).toHaveValue("321");

  const longState = await paperState(request);
  expect(longState.position_side).toBe("Long");
  expect(Number(longState.position_quantity)).toBeGreaterThan(0);
  const displayedNotional = String(
    Math.round(Number(longState.engaged_notional_usdt)),
  );
  await expect(
    page.getByText(`${displayedNotional} USDT`, { exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Закрыть позицию" }).click();
  await expect(page.getByText("PAPER позиция закрыта")).toBeVisible();
  const flatState = await paperState(request);
  expect(flatState.position_side).toBe("Flat");
  expect(Number(flatState.position_quantity)).toBe(0);
  expect(Number(flatState.engaged_notional_usdt)).toBe(0);
  expect(Number(flatState.engaged_wv)).toBe(0);
  await expect(page.getByText("0 USDT", { exact: true })).toBeVisible();
  await expect(page.getByText("⚔️ 0.0", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Закрыть позицию" }).click();
  await expect(page.getByText("PAPER позиция закрыта")).toBeVisible();
  const repeatedFlatState = await paperState(request);
  expect(repeatedFlatState.position_side).toBe("Flat");
  expect(Number(repeatedFlatState.position_quantity)).toBe(0);

  await page.getByLabel("BUY amount").fill("40");
  await page.getByRole("button", { name: "BUY", exact: true }).click();
  await expect(
    page.getByText("Сумма слишком мала для шага объёма"),
  ).toBeVisible();
  const rejectedState = await paperState(request);
  expect(rejectedState.position_side).toBe("Flat");
  expect(Number(rejectedState.position_quantity)).toBe(0);
});

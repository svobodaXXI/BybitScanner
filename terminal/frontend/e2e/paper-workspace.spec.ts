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
  active_limit_orders: Array<{
    order_id: string;
    side: "Buy" | "Sell";
    price: string;
    quantity: string;
    time_in_force: "GTC";
  }>;
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
  await expect(page.getByText("Execution: PAPER / non-live")).toHaveCount(0);

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

  await page.getByLabel("LIMIT side").selectOption("Buy");
  await page.getByLabel("LIMIT price").fill("64000");
  await page.getByLabel("LIMIT amount").fill("321");
  await page.getByRole("button", { name: "Создать LIMIT" }).click();
  await expect(page.getByText("PAPER LIMIT создан")).toBeVisible();
  const withLimit = await paperState(request);
  expect(withLimit.active_limit_orders).toHaveLength(1);
  expect(withLimit.active_limit_orders[0]).toMatchObject({
    side: "Buy", price: "64000", time_in_force: "GTC",
  });
  const orderId = withLimit.active_limit_orders[0].order_id;
  const originalQuantity = withLimit.active_limit_orders[0].quantity;
  await expect(page.getByText(`Buy ${withLimit.active_limit_orders[0].quantity} @ 64000 GTC`)).toBeVisible();
  await page.getByLabel(`Новая цена ${orderId}`).fill("64100");
  await page.getByRole("button", { name: `Изменить ${orderId}` }).click();
  await expect(page.getByText("PAPER LIMIT изменён")).toBeVisible();
  const amended = await paperState(request);
  expect(amended.active_limit_orders).toHaveLength(1);
  expect(amended.active_limit_orders[0]).toMatchObject({
    order_id: orderId, side: "Buy", price: "64100",
    quantity: originalQuantity, time_in_force: "GTC",
  });
  await expect(page.getByText(`Buy ${originalQuantity} @ 64100 GTC`)).toBeVisible();
  await page.getByRole("button", { name: `Отменить ${orderId}` }).click();
  await expect(page.getByText("PAPER LIMIT отменён")).toBeVisible();
  expect((await paperState(request)).active_limit_orders).toHaveLength(0);

  const repeatCancel = await request.post(`${backendUrl}/api/limit/cancel`, {
    data: { client_action_id: "e2e-repeat-cancel", symbol: "BTCUSDT", order_id: orderId },
  });
  expect(repeatCancel.ok()).toBeTruthy();
  expect((await repeatCancel.json()).status).toBe("completed");
  expect((await paperState(request)).active_limit_orders).toHaveLength(0);

  for (const invalid of [
    { price: "0", amount: "321" },
    { price: "64000", amount: "0" },
  ]) {
    const response = await request.post(`${backendUrl}/api/limit`, { data: {
      client_action_id: `e2e-invalid-${invalid.price}-${invalid.amount}`,
      symbol: "BTCUSDT", side: "Sell",
      volume: { unit: "usdt", amount: invalid.amount },
      sizing_reference_price: invalid.price, limit_price: invalid.price,
      time_in_force: "GTC",
    } });
    if (response.status() === 200) {
      expect((await response.json()).status).toBe("blocked");
    } else {
      expect(response.status()).toBe(400);
    }
  }
  expect((await paperState(request)).active_limit_orders).toHaveLength(0);
});

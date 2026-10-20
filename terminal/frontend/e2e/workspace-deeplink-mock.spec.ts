import { test, expect } from "@playwright/test";

for (const [mode, symbol, timeframe] of [
  ["EDITOR", "BTCUSDT", "15m"],
  ["TERMINAL", "ETHUSDT", "5m"],
] as const) {
  test(`deep-link ${mode}/${symbol} requires mock activation ACK`, async ({ page }) => {
    const posts: string[] = [];
    await page.route("**/api/**", async (route) => {
      const request = route.request();
      const pathname = new URL(request.url()).pathname;
      if (pathname === "/api/workspace/symbol" && request.method() === "POST") {
        const body = request.postDataJSON() as { symbol: string };
        posts.push(body.symbol);
        await route.fulfill({ status: 200, contentType: "application/json",
          body: JSON.stringify({ ok: true, symbol: body.symbol, generation: 101 }) });
        return;
      }
      if (pathname === "/api/workspace/state") {
        await route.fulfill({ status: 200, contentType: "application/json",
          body: JSON.stringify({ ok: true, workspace: { active_symbol: "ONGUSDT", active_generation: 1 } }) });
        return;
      }
      await route.fulfill({ status: 503, contentType: "application/json", body: '{"ok":false}' });
    });
    await page.goto(`/?mode=${mode}&symbol=${symbol}&timeframe=${timeframe}`);
    await expect(page.getByText("Active mode", { exact: false })).toBeVisible();
    await expect(page.getByRole("heading", { name: mode })).toBeVisible();
    await expect.poll(() => posts).toContain(symbol);
    await expect(page.getByText(symbol, { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "BUY", exact: true })).toBeDisabled().catch(() => {
      // In EDITOR the trading controls are intentionally absent.
      if (mode !== "EDITOR") throw new Error("BUY unexpectedly enabled");
    });
  });
}

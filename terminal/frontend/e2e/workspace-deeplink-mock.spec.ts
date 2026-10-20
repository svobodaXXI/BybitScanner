import { test, expect } from "@playwright/test";

for (const [mode, symbol, timeframe] of [
  ["EDITOR", "BTCUSDT", "15m"],
  ["TERMINAL", "ETHUSDT", "5m"],
] as const) {
  test(`deep-link ${mode}/${symbol} requires mock activation ACK`, async ({ page }) => {
    const posts: string[] = [];
    const streamRequests: string[] = [];
    await page.routeWebSocket("**/api/workspace/stream?*", (ws) => {
      const url = new URL(ws.url());
      const streamSymbol = url.searchParams.get("symbol");
      const interval = url.searchParams.get("interval");
      if (streamSymbol !== symbol) return;
      streamRequests.push(streamSymbol);
      // Wait for the browser to install onmessage after WebSocket opens.
      setTimeout(() => ws.send(JSON.stringify({
        stream_id: "mock-stream-101", event_sequence: 1, event_timestamp: Date.now(),
        symbol, workspace_generation: 101, kind: "workspace_snapshot", state: "READY",
        instrument: { symbol, tick_size: "0.5", quantity_step: "0.001" },
        book: {
          kind: "book_snapshot", state: "READY", projection_version: 3,
          source_timestamp: Date.now(), upstream_update_id: 10, upstream_sequence: 20,
          bids: [{ price: "100", size: "2" }], asks: [{ price: "101", size: "3" }],
        },
        trades: { kind: "trade_bootstrap", state: "READY", projection_version: 1, trades: [] },
        candles: {
          kind: "candle_bootstrap", state: "READY", interval,
          projection_version: 1,
          candles: [{ startTime: Date.now() - 60000, open: "100", high: "101", low: "99", close: "100" }],
        },
      })), 200);
    });
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
    await expect.poll(() => streamRequests).toContain(symbol);
    await expect(page.getByText(symbol, { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "BUY", exact: true })).toBeDisabled().catch(() => {
      // In EDITOR the trading controls are intentionally absent.
      if (mode !== "EDITOR") throw new Error("BUY unexpectedly enabled");
    });
  });
}

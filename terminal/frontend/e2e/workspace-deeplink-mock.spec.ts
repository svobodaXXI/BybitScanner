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
    await expect(page.getByRole("button", { name: `Select symbol ${symbol}` })).toBeVisible();
    await expect(page.getByRole("button", { name: "BUY", exact: true })).toBeDisabled().catch(() => {
      // In EDITOR the trading controls are intentionally absent.
      if (mode !== "EDITOR") throw new Error("BUY unexpectedly enabled");
    });
  });
}


test("frozen Editor geometry renders and accepts owner feedback without live WebSocket", async ({ page }) => {
  const signalId = "source:BTCUSDT:5:historic-wedge";
  const posted: unknown[] = [];
  await page.addInitScript(() => {
    const observations = { reference: 0, editable: 0 };
    Object.assign(window, { __editorRayStrokes: observations });
    const stroke = CanvasRenderingContext2D.prototype.stroke;
    CanvasRenderingContext2D.prototype.stroke = function (...args) {
      if (this.strokeStyle === "#8195aa") observations.reference++;
      if (this.strokeStyle === "#e0b45b") observations.editable++;
      return stroke.apply(this, args);
    };
  });
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    if (pathname === "/api/workspace/signal-geometry") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        ok: true,
        snapshot_revision: "a".repeat(64),
        bars_sha256: "b".repeat(64),
        latest_review: null,
        snapshot: {
          schema_version: 1, signal_id: signalId, symbol: "BTCUSDT", timeframe: "5",
          bars: [
            { open_time_ms: 1800000000000, open: 100, high: 115, low: 95, close: 110 },
            { open_time_ms: 1800000300000, open: 110, high: 116, low: 96, close: 102 },
            { open_time_ms: 1800000600000, open: 102, high: 117, low: 97, close: 111 },
          ],
          boundaries: [
            { boundary_id: "upper", kind: "ray", anchors: [
              { bar_open_time_ms: 1800000000000, price: 115 },
              { bar_open_time_ms: 1800000600000, price: 117 },
            ] },
            { boundary_id: "lower", kind: "ray", anchors: [
              { bar_open_time_ms: 1800000000000, price: 95 },
              { bar_open_time_ms: 1800000600000, price: 97 },
            ] },
          ],
        },
      }) });
      return;
    }
    if (pathname === "/api/workspace/geometry-feedback" && request.method() === "POST") {
      posted.push(request.postDataJSON());
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        ok: true, review: { review_id: "review-verified", submission: { signal_id: signalId } },
      }) });
      return;
    }
    if (pathname === "/api/workspace/symbol" && request.method() === "POST") {
      await route.fulfill({ status: 200, contentType: "application/json",
        body: JSON.stringify({ ok: true, symbol: "BTCUSDT", generation: 101 }) });
      return;
    }
    if (pathname === "/api/workspace/state") {
      await route.fulfill({ status: 200, contentType: "application/json",
        body: JSON.stringify({ ok: true, workspace: { active_symbol: "ONGUSDT", active_generation: 1 } }) });
      return;
    }
    await route.fulfill({ status: 503, contentType: "application/json", body: '{"ok":false}' });
  });

  // No /api/workspace/stream WebSocket stub: historical source is self-contained.
  await page.goto("/?mode=EDITOR&symbol=BTCUSDT&timeframe=5m&signal_id=" + encodeURIComponent(signalId));
  const save = page.getByRole("button", { name: "Передать исправление" });
  await expect(save).toBeVisible();
  await expect(save).toBeEnabled();
  await expect.poll(() => page.evaluate(() => {
    const strokes = (window as unknown as { __editorRayStrokes: { reference: number; editable: number } }).__editorRayStrokes;
    return strokes.reference > 0 && strokes.editable > 0;
  })).toBe(true);
  await page.getByRole("combobox", { name: "Оценка сигнала" }).selectOption("CONFIRMED");
  await save.click();
  await expect(page.getByText(/Исправление сохранено в дневнике обратной связи/)).toBeVisible();
  expect(posted).toHaveLength(1);
  expect(posted[0]).toMatchObject({
    signal_id: signalId, label: "CONFIRMED",
    snapshot_revision: "a".repeat(64), bars_sha256: "b".repeat(64),
    corrected_boundaries: [],
  });
});

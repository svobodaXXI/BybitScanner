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
  const posted: Array<{ idempotency_key: string; [key: string]: unknown }> = [];
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
      const submitted = request.postDataJSON() as {
        idempotency_key: string; signal_id: string; snapshot_revision: string;
        bars_sha256: string; label: string;
      };
      posted.push(submitted);
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        ok: true, review: {
          review_id: "c".repeat(64),
          submission: {
            ...submitted,
            // First reply swaps in an unrequested boundary: never report success.
            corrected_boundaries: posted.length === 1
              ? [{ boundary_id: "foreign", kind: "ray", anchors: [] }]
              : [],
          },
        },
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
  await expect(page.getByText(/Не удалось сохранить: Сервер не подтвердил точное сохранение отзыва/)).toBeVisible();
  await expect(page.getByText(/Сохранённый отзыв:/)).toHaveCount(0);
  await save.click();
  await expect(page.getByText(/Исправление сохранено в дневнике обратной связи/)).toBeVisible();
  await expect(page.getByText(/Сохранённый отзыв: c{12}.*Верный сигнал/)).toBeVisible();
  expect(posted).toHaveLength(2);
  expect(posted[0].idempotency_key).toBe(posted[1].idempotency_key);
  expect(posted[0]).toMatchObject({
    signal_id: signalId, label: "CONFIRMED",
    snapshot_revision: "a".repeat(64), bars_sha256: "b".repeat(64),
    corrected_boundaries: [],
  });
});


test("Editor saved correction survives a fresh open with original Scanner rays unchanged", async ({ page }) => {
  const signalId = "source:BTCUSDT:5:saved-review-roundtrip";
  const original = [
    { boundary_id: "upper", kind: "ray", anchors: [
      { bar_open_time_ms: 1800000000000, price: 115 },
      { bar_open_time_ms: 1800000600000, price: 117 },
    ] },
    { boundary_id: "lower", kind: "ray", anchors: [
      { bar_open_time_ms: 1800000000000, price: 95 },
      { bar_open_time_ms: 1800000600000, price: 97 },
    ] },
  ];
  const candleBars = [
    { open_time_ms: 1800000000000, open: 100, high: 115, low: 95, close: 110 },
    { open_time_ms: 1800000300000, open: 110, high: 116, low: 96, close: 102 },
    { open_time_ms: 1800000600000, open: 102, high: 117, low: 97, close: 111 },
  ];
  const frozen = {
    schema_version: 1, signal_id: signalId, symbol: "BTCUSDT", timeframe: "5",
    bars: candleBars, boundaries: original,
  };
  let savedReview: {
    review_id: string;
    submission: {
      signal_id: string; snapshot_revision: string; label: string;
      corrected_boundaries: Array<{ boundary_id: string; kind: string; anchors: Array<{ bar_open_time_ms: number; price: number }> }>;
    };
  } | null = null;
  let writes = 0;
  let correctedPrice: number | null = null;
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    if (pathname === "/api/workspace/signal-geometry") {
      await route.fulfill({ status: 200, contentType: "application/json",
        body: JSON.stringify({
          ok: true, snapshot: frozen, latest_review: savedReview,
          snapshot_revision: "a".repeat(64), bars_sha256: "b".repeat(64),
        }) });
      return;
    }
    if (pathname === "/api/workspace/geometry-feedback" && request.method() === "POST") {
      writes++;
      const body = request.postDataJSON() as {
        schema_version: 1; note: string;
        signal_id: string; label: string; snapshot_revision: string;
        bars_sha256: string; idempotency_key: string;
        corrected_boundaries: Array<{ id: string; type: string; anchors: Array<{ bar_open_time_ms: number; price: number }> }>;
      };
      expect(body.signal_id).toBe(signalId);
      expect(body.label).toBe("GEOMETRY_CORRECTED");
      expect(body.corrected_boundaries).toHaveLength(2);
      correctedPrice = body.corrected_boundaries[0].anchors[0].price;
      expect(Number.isFinite(correctedPrice)).toBe(true);
      expect(correctedPrice).not.toBe(115);
      expect(body.corrected_boundaries[0].anchors[0].bar_open_time_ms).toBe(1800000000000);
      expect(body.corrected_boundaries[1].anchors[0]).toEqual({
        bar_open_time_ms: 1800000000000, price: 95,
      });
      savedReview = {
        review_id: "d".repeat(64),
        submission: {
          signal_id: signalId, snapshot_revision: body.snapshot_revision, label: body.label,
          corrected_boundaries: body.corrected_boundaries.map((item) => ({
            boundary_id: item.id, kind: item.type, anchors: item.anchors,
          })),
        },
      };
      await route.fulfill({ status: 200, contentType: "application/json",
        body: JSON.stringify({ ok: true, review: { review_id: savedReview.review_id,
          submission: {
            schema_version: body.schema_version, note: body.note,
            signal_id: signalId, snapshot_revision: body.snapshot_revision,
            bars_sha256: body.bars_sha256, label: body.label,
            idempotency_key: body.idempotency_key,
            corrected_boundaries: savedReview.submission.corrected_boundaries,
          } } }) });
      return;
    }
    if (pathname === "/api/workspace/symbol" && request.method() === "POST") {
      await route.fulfill({ status: 200, contentType: "application/json",
        body: JSON.stringify({ ok: true, symbol: "BTCUSDT", generation: 101 }) });
      return;
    }
    if (pathname === "/api/workspace/state") {
      await route.fulfill({ status: 200, contentType: "application/json",
        body: JSON.stringify({ ok: true, workspace: {
          active_symbol: "ONGUSDT", active_generation: 1,
        } }) });
      return;
    }
    await route.fulfill({ status: 503, contentType: "application/json", body: '{"ok":false}' });
  });

  // Observe the first editable ray's canvas origin, then physically drag it.
  // This exercises the actual DrawingOverlay pointer path (not localStorage seeding).
  await page.addInitScript(() => {
    const clear = CanvasRenderingContext2D.prototype.clearRect;
    CanvasRenderingContext2D.prototype.clearRect = function (...args) {
      if (this.canvas.classList.contains("drawing-overlay")) {
        (window as typeof window & { __editableRay?: { x: number; y: number } }).__editableRay = undefined;
      }
      return clear.apply(this, args);
    };
    const original = CanvasRenderingContext2D.prototype.moveTo;
    CanvasRenderingContext2D.prototype.moveTo = function (x, y) {
      if (this.canvas.classList.contains("drawing-overlay") && this.strokeStyle === "#e0b45b") {
        const marker = window as typeof window & { __editableRay?: { x: number; y: number } };
        // The upper Scanner boundary is rendered before the lower boundary.
        if (marker.__editableRay === undefined) marker.__editableRay = { x, y };
      }
      return original.call(this, x, y);
    };
  });
  const url = "/?mode=EDITOR&symbol=BTCUSDT&timeframe=5m&signal_id=" + encodeURIComponent(signalId);
  await page.goto(url);
  await expect(page.getByRole("button", { name: "Передать исправление" })).toBeEnabled();
  await expect.poll(() => page.evaluate(() => (
    (window as typeof window & { __editableRay?: { x: number; y: number } }).__editableRay ?? null
  ))).not.toBeNull();
  const rayStart = await page.evaluate(() => (
    (window as typeof window & { __editableRay: { x: number; y: number } }).__editableRay
  ));
  const canvas = page.getByRole("application", { name: "Interactive market chart" }).locator("canvas.drawing-overlay");
  const rect = await canvas.boundingBox();
  expect(rect).not.toBeNull();
  const x = rect!.x + rayStart.x;
  const y = rect!.y + rayStart.y;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + 2, y + 50, { steps: 6 });
  await page.mouse.up();
  const startKey = `bybitscanner:editor-drawings:v1:BTCUSDT:5m:${signalId}`;
  await expect.poll(() => page.evaluate((key) => {
    const raw = localStorage.getItem(key);
    const upper = raw ? JSON.parse(raw).drawings.find((item: { id: string }) => item.id === "editable:upper") : null;
    return upper?.anchors[0] ?? null;
  }, startKey)).not.toEqual({ logical: 0, price: 115 });
  await expect(page.getByLabel("Сравнение линий Scanner и исправления")).toContainText("Δ точка 1");
  await expect(page.getByLabel("Несохранённый отзыв")).toContainText("Новые изменения не сохранены");
  // "Confirmed" cannot silently discard an already moved Scanner boundary.
  await page.getByRole("combobox", { name: "Оценка сигнала" }).selectOption("CONFIRMED");
  await page.getByRole("button", { name: "Передать исправление" }).click();
  await expect(page.locator(".editor-correction-export output[role=status]").last())
    .toContainText("Линии изменены");
  expect(writes).toBe(0);
  await page.getByRole("combobox", { name: "Оценка сигнала" }).selectOption("GEOMETRY_CORRECTED");
  await page.getByRole("button", { name: "Передать исправление" }).click();
  await expect(page.locator(".editor-correction-export output[role=status]").last())
    .toContainText("Исправление сохранено в дневнике обратной связи");
  expect(writes).toBe(1);
  await expect(page.getByText(/Сохранённый отзыв: d{12}.*Исправлена геометрия/)).toBeVisible();
  await expect(page.getByLabel("Несохранённый отзыв")).toHaveCount(0);
  // Changing the review AFTER the server's confirmation must not imply that
  // the newly edited note has already been saved with the old geometry.
  await page.getByRole("textbox", { name: "Комментарий к исправлению" }).fill("New note after receipt");
  await expect(page.getByLabel("Несохранённый отзыв")).toContainText("Новые изменения не сохранены");
  await expect(page.getByText(/Сохранённый отзыв: d{12}.*предыдущая версия/)).toBeVisible();
  expect(writes).toBe(1);

  await page.reload();
  await expect(page.getByLabel("Несохранённый отзыв")).toHaveCount(0);
  await expect(page.getByText(/Сохранённый отзыв: d{12}.*Исправлена геометрия/)).toBeVisible();
  await expect.poll(() => page.evaluate((id) => {
    const savedKey = `bybitscanner:editor-drawings:v1:BTCUSDT:5m:${id}:review-${"d".repeat(64)}`;
    const raw = localStorage.getItem(savedKey);
    return raw ? JSON.parse(raw).drawings.map((item: { id: string; anchors: Array<{ price: number }> }) => ({
      id: item.id, price: item.anchors[0].price,
    })) : null;
  }, signalId)).toEqual([
    { id: "editable:upper", price: correctedPrice },
    { id: "editable:lower", price: 95 },
  ]);
  expect(original[0].anchors[0].price).toBe(115);
  expect(writes).toBe(1); // Reload is read-only, never resubmits a correction.
});

import { expect, test } from "@playwright/test";

test("EDITOR opens exact frozen signal, preserves source rays and exports a manual drawing draft", async ({
  page, context,
}) => {
  const signalId = "source-original:browser-fixture-001";
  const bars = [
    { open_time_ms: 1792368000000, open: 100, high: 103, low: 98, close: 101 },
    { open_time_ms: 1792368300000, open: 101, high: 104, low: 99, close: 102 },
    { open_time_ms: 1792368600000, open: 102, high: 105, low: 100, close: 103 },
  ];
  const source = [
    { boundary_id: "upper", kind: "ray", anchors: [
      { bar_open_time_ms: bars[0].open_time_ms, price: 103 },
      { bar_open_time_ms: bars[2].open_time_ms, price: 105 },
    ] },
    { boundary_id: "lower", kind: "ray", anchors: [
      { bar_open_time_ms: bars[0].open_time_ms, price: 98 },
      { bar_open_time_ms: bars[2].open_time_ms, price: 100 },
    ] },
  ];
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.routeWebSocket("**/api/workspace/stream?*", (ws) => {
    const url = new URL(ws.url());
    if (url.searchParams.get("symbol") !== "BTCUSDT") return;
    setTimeout(() => ws.send(JSON.stringify({
      stream_id: "editor-fixture-stream", event_sequence: 1, event_timestamp: Date.now(),
      symbol: "BTCUSDT", workspace_generation: 101, kind: "workspace_snapshot", state: "READY",
      instrument: { symbol: "BTCUSDT", tick_size: "0.5", quantity_step: "0.001" },
      book: {
        kind: "book_snapshot", state: "READY", projection_version: 3,
        source_timestamp: Date.now(), upstream_update_id: 10, upstream_sequence: 20,
        bids: [{ price: "100", size: "2" }], asks: [{ price: "101", size: "3" }],
      },
      trades: { kind: "trade_bootstrap", state: "READY", projection_version: 1, trades: [] },
      candles: {
        kind: "candle_bootstrap", state: "READY", interval: "5",
        projection_version: 1, candles: [
          { startTime: Date.now() - 300000, open: "100", high: "101", low: "99", close: "100" },
        ],
      },
    })), 200);
  });
  const geometryRequests: string[] = [];
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/workspace/signal-geometry") {
      geometryRequests.push(url.searchParams.get("signal_id") ?? "");
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        ok: true, snapshot: {
          schema_version: 1, signal_id: signalId, symbol: "BTCUSDT", timeframe: "5",
          bars, boundaries: source,
        },
      }) });
    }
    if (url.pathname === "/api/workspace/symbol" && request.method() === "POST")
      return route.fulfill({ status: 200, contentType: "application/json",
        body: '{"ok":true,"symbol":"BTCUSDT","generation":101}' });
    if (url.pathname === "/api/workspace/state")
      return route.fulfill({ status: 200, contentType: "application/json",
        body: '{"ok":true,"workspace":{"active_symbol":"BTCUSDT","active_generation":101}}' });
    return route.fulfill({ status: 503, contentType: "application/json", body: '{"ok":false}' });
  });
  await page.goto(`/?mode=EDITOR&symbol=BTCUSDT&timeframe=5m&signal_id=${encodeURIComponent(signalId)}`);
  await expect(page.getByRole("heading", { name: "EDITOR" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Скопировать исправленную геометрию" })).toBeVisible();
  await expect(page.getByLabel("Drawing layer")).toBeVisible();
  await expect.poll(() => geometryRequests.length).toBeGreaterThan(0);
  expect(geometryRequests.every((requested) => requested === signalId)).toBe(true);

  const stored = () => page.evaluate((id) => {
    const raw = localStorage.getItem(`bybitscanner:editor-drawings:v1:BTCUSDT:5m:${id}`);
    return raw ? JSON.parse(raw) as { drawings: Array<{ id: string; anchors: unknown[] }> } : null;
  }, signalId);
  await expect.poll(async () => (await stored())?.drawings.length).toBe(2);
  const initial = await stored();
  expect(initial?.drawings.map((line) => line.id)).toEqual(["editable:upper", "editable:lower"]);

  await page.getByRole("button", { name: "Horizontal line" }).click();
  const box = await page.getByLabel("Interactive market chart").boundingBox();
  if (!box) throw new Error("Missing interactive chart");
  await page.mouse.click(box.x + box.width * 0.5, box.y + box.height * 0.5);
  await expect.poll(async () => (await stored())?.drawings.length).toBe(3);

  await page.getByRole("button", { name: "Скопировать исправленную геометрию" }).click();
  console.log("EDITOR_DRAWINGS", JSON.stringify(await stored()));
  console.log("EDITOR_EXPORT_STATUS", await page.locator(".editor-correction-export").innerText());
  await expect(page.getByText("Черновик коррекции скопирован.", { exact: false })).toBeVisible();
  const copied = JSON.parse(await page.evaluate(() => navigator.clipboard.readText())) as {
    signal_id: string; label: string; status: string;
    corrected_boundaries: Array<{ id: string; type: string; anchors: Array<{ bar_open_time_ms: number; price: number }> }>;
  };
  expect(copied).toMatchObject({ signal_id: signalId, label: "GEOMETRY_CORRECTED", status: "DRAFT_ONLY" });
  expect(copied.corrected_boundaries).toHaveLength(3);
  expect(copied.corrected_boundaries[0].anchors).toEqual(source[0].anchors);
  expect(copied.corrected_boundaries[1].anchors).toEqual(source[1].anchors);
  expect(copied.corrected_boundaries[2].type).toBe("horizontal");
});

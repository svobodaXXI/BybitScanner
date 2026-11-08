/** Real historical acceptance in Chromium: validated official Bybit prints
 * -> immutable MARKET_ONLY JSON -> actual standalone local chart.
 * No synthetic candles, requests to PAPER, or trading actions.
 */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { readFile, mkdir } from "node:fs/promises";
import { basename, join } from "node:path";
import { chromium } from "@playwright/test";

const archivePath = process.env.LOCAL_REPLAY_REAL_ARCHIVE;
const serverPath = process.env.LOCAL_REPLAY_PACKAGED_SERVER;
const screenshotDir = process.env.LOCAL_REPLAY_E2E_SCREENSHOTS;
assert.ok(archivePath && serverPath && screenshotDir, "CI requires the verified archive and local package");
const archive = JSON.parse(await readFile(archivePath, "utf8"));
assert.equal(archive.source, "SIMULATION");
assert.equal(archive.mode, "MARKET_ONLY");
assert.equal(archive.symbol, "GRASSUSDT");
assert.equal(archive.market_data_source, "BYBIT_OFFICIAL_PUBLIC_TRADES_DERIVED_5M");
assert.equal(archive.events.length, 2016);
assert.ok(archive.hourly_prior_breaks.length > 0, "at least one actual closed H1 prior break is required");
const breaks = archive.hourly_prior_breaks;
const byEventTime = new Map(archive.events.map((event, index) => [event.time_ms, index]));
const yellow = archive.geometry.filter(item => item.kind === "MAIN_1H");
assert.ok(yellow.length >= 2, "at least one frozen H1 main movement and an opposite are required");
const proven = breaks.flatMap((event, i) => {
  const next = breaks[i + 1]?.confirmed_at_ms ?? Infinity;
  const opposite = yellow.find(line =>
    line.side === event.new_side && line.available_at_ms >= event.confirmed_at_ms &&
    line.available_at_ms < next);
  return opposite ? [{ event, i, opposite }] : [];
});
assert.ok(proven.length > 0,
  "an actual confirmed close/next-open break followed by four-pivot opposite H1 must exist");
await mkdir(screenshotDir, { recursive: true });

const server = spawn("python", [serverPath, "--no-browser"], { stdio: ["ignore", "pipe", "pipe"] });
let stderr = "";
server.stderr.on("data", chunk => { stderr += chunk.toString(); });
let browser;
async function localUrl() {
  let output = "";
  return await new Promise((resolve, reject) => {
    const watchdog = setTimeout(() => reject(new Error("local viewer start timed out: " + stderr)), 15000);
    server.once("exit", code => {
      clearTimeout(watchdog);
      reject(new Error("local viewer exited " + code + ": " + stderr));
    });
    server.stdout.on("data", chunk => {
      output += chunk.toString();
      const uri = output.match(/http:\/\/127\.0\.0\.1:\d+\/replay\.html/);
      if (uri) {
        clearTimeout(watchdog);
        resolve(uri[0]);
      }
    });
  });
}
try {
  const url = await localUrl();
  browser = await chromium.launch({
    headless: true,
    ...(process.env.LOCAL_REPLAY_CHROME ? {
      executablePath: process.env.LOCAL_REPLAY_CHROME,
    } : {}),
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 920 }, deviceScaleFactor: 1 });
  const errors = [], requests = [];
  page.on("pageerror", e => errors.push(e.message));
  page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
  page.on("request", req => requests.push(req.url()));
  await page.goto(url, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Машина времени" }).waitFor();
  await page.locator('input[type="file"]').setInputFiles(archivePath);
  await page.waitForFunction(() =>
    document.querySelector('input[aria-label="Инструмент"]')?.value === "GRASSUSDT" ||
    document.querySelector('[role="alert"]') !== null,
  null, { timeout: 15000 });
  const importError = page.getByRole("alert");
  if (await importError.count()) {
    throw new Error("Real Bybit MARKET_ONLY archive rejected by viewer: " +
      await importError.first().innerText());
  }
  assert.equal(await page.getByRole("textbox", { name: "Инструмент" }).inputValue(), "GRASSUSDT");
  assert.equal(await page.locator('input[type="date"]').nth(0).inputValue(),
    new Date(archive.from_ms).toISOString().slice(0, 10));
  assert.equal(await page.locator('input[type="date"]').nth(1).inputValue(),
    new Date(archive.until_ms).toISOString().slice(0, 10));
  assert.equal(await page.locator(".replay-note").count(), 0,
    "obsolete yellow market archive banner must be absent");
  assert.match(await page.locator("body").innerText(), /GRASSUSDT/,
    "real official-archive instrument stays identified in metadata");
  assert.equal(await page.getByRole("slider", { name: "Перемотка графика по закрытым свечам" }).inputValue(), "0");
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-fills"), "0");
  // Reference implementation: chart's H1 axis includes the ORIGINAL
  // already-closed warmup OHLC bars. The first frozen MAIN source anchor
  // must therefore exist as an actual chart candle, not an offscreen ray.
  const firstMain = yellow[0];
  assert.ok(archive.context_1h.some(bar => bar.start_ms === firstMain.from_ms),
    "real first H1 line must have a genuine context source candle");
  await page.getByRole("button", { name: "H1", exact: true }).click();
  const chartShell = page.locator(".replay-chart-shell");
  await page.waitForFunction(expected =>
    document.querySelector(".replay-chart-shell")?.getAttribute("data-context-hourly-candles") === String(expected),
  archive.context_1h.length);
  assert.equal(Number(await chartShell.getAttribute("data-first-chart-candle-ms")),
    archive.context_1h[0].start_ms,
    "first actual context H1 candle must be on the chart time scale");
  assert.equal(Number(await chartShell.getAttribute("data-displayed-candles")),
    archive.context_1h.length, "the initial playhead must still contain zero replay candles");
  assert.match(await page.locator(".replay-chart-watermark").innerText(),
    /Серые свечи — предыстория H1/);
  await page.getByRole("button", { name: "M5", exact: true }).click();
  assert.equal(await chartShell.getAttribute("data-context-hourly-candles"), "0");
  // Owner UTC clock now lives on the drawing toolbar. Selecting a clock
  // timestamp must seek the ORIGINAL replay stream, not download fresh
  // candles, wipe manual drawing state or expose an incomplete H1.
  const utcClock = page.getByRole("textbox", { name: "Время рынка UTC — вставить дату и время" });
  const calendar = page.getByLabel("Время рынка UTC — календарь");
  assert.equal(await utcClock.count(), 1);
  assert.equal(await calendar.count(), 1);
  const inputTime = ms => {
    const iso = new Date(ms).toISOString();
    return iso.slice(8, 10) + "." + iso.slice(5, 7) + "." +
      iso.slice(0, 4) + ", " + iso.slice(11, 16);
  };
  await utcClock.fill(inputTime(archive.events[23].time_ms));
  await utcClock.press("Enter");
  await page.waitForFunction(() =>
    document.querySelector(".replay-chart-shell")?.getAttribute("data-displayed-candles") === "24");
  assert.equal(await utcClock.inputValue(), inputTime(archive.events[23].time_ms));
  // A malformed paste must stay editable with a visible error and leave
  // the cursor/candles unchanged.
  await utcClock.fill("31.02.2026, 12:00");
  await utcClock.press("Enter");
  assert.equal(await utcClock.getAttribute("aria-invalid"), "true");
  assert.equal(await page.locator(".replay-chart-shell").getAttribute("data-displayed-candles"), "24");
  await utcClock.fill(inputTime(archive.events[18].time_ms));
  await page.getByRole("button", { name: "H1", exact: true }).click();
  await utcClock.press("Enter");
  await page.waitForFunction(expected =>
    document.querySelector(".replay-chart-shell")?.getAttribute("data-displayed-candles") === String(expected),
  archive.context_1h.length + 1);
  await page.getByRole("button", { name: "M5", exact: true }).click();
  await page.getByRole("button", { name: "В начало", exact: true }).click();
  await page.waitForFunction(() =>
    document.querySelector(".replay-chart-shell")?.getAttribute("data-displayed-candles") === "0");
  console.log("REAL_OWNER_UTC_TOOLBAR_SEEK_OK");
  // The owner removed the banner and event sidebar to widen the REAL chart.
  assert.equal(await page.locator(".replay-note").count(), 0,
    "the obsolete yellow text banner must not consume vertical chart space");
  assert.equal(await page.locator(".replay-events").count(), 0,
    "no event sidebar may consume chart width");
  const gridAndChart = await page.evaluate(() => {
    const grid = document.querySelector(".replay-grid").getBoundingClientRect();
    const pane = document.querySelector(".replay-chart-panel").getBoundingClientRect();
    return { grid: grid.width, pane: pane.width };
  });
  assert.ok(gridAndChart.pane >= gridAndChart.grid - 2,
    "the chart must occupy the whole available grid width");
  const scrubber = page.getByRole("slider", { name: "Перемотка графика по закрытым свечам" });
  assert.equal(await scrubber.count(), 1);
  assert.equal(await scrubber.getAttribute("max"), String(
    archive.events.filter(event => event.kind === "CANDLE_CLOSED").length));
  await scrubber.focus();
  await scrubber.press("End");
  await page.waitForFunction(expected =>
    document.querySelector(".replay-chart-shell")?.getAttribute("data-displayed-candles") === String(expected),
  archive.events.filter(event => event.kind === "CANDLE_CLOSED").length);
  await scrubber.press("Home");
  await page.waitForFunction(() =>
    document.querySelector(".replay-chart-shell")?.getAttribute("data-displayed-candles") === "0");
  await scrubber.press("ArrowRight");
  await page.waitForFunction(() =>
    document.querySelector(".replay-chart-shell")?.getAttribute("data-displayed-candles") === "1");
  await page.getByRole("button", { name: "H1", exact: true }).click();
  await scrubber.press("ArrowRight");
  await page.waitForFunction(expected =>
    document.querySelector(".replay-chart-shell")?.getAttribute("data-displayed-candles") === String(expected),
  archive.context_1h.length);
  await scrubber.press("End");
  const hours = Math.floor(archive.events.filter(event => event.kind === "CANDLE_CLOSED").length / 12);
  await page.waitForFunction(expected =>
    document.querySelector(".replay-chart-shell")?.getAttribute("data-displayed-candles") === String(expected),
  archive.context_1h.length + hours);
  await page.getByRole("button", { name: "M5", exact: true }).click();
  await scrubber.press("Home");
  await page.waitForFunction(() =>
    document.querySelector(".replay-chart-shell")?.getAttribute("data-displayed-candles") === "0");
  console.log("REAL_OWNER_FULL_WIDTH_SCRUBBER_OK");


  // Semantic status nodes intentionally live inside a CLOSED diagnostics
  // disclosure. Open it just as the owner would before reading prior events.
  await page.getByText("Диагностика", { exact: true }).click();

  const forward = page.getByRole("button", { name: "Шаг вперёд ▶", exact: true });
  const backward = page.getByRole("button", { name: "◀ Шаг назад", exact: true });
  let position = 0;
  async function advanceTo(n) {
    assert.ok(n >= position && n <= archive.events.length, "ordered candle steps only");
    // The actual React button updates the same cursor as owner clicks.
    // Batch the genuine button handler calls to avoid a 35-second timer wait
    // or changing the product with a test-only seek API.
    const amount = n - position;
    if (amount) {
      await forward.evaluate((button, count) => {
        for (let i = 0; i < count; i++) button.click();
      }, amount);
    }
    await page.waitForFunction(expected =>
      document.querySelector(".replay-chart-shell")?.getAttribute("data-displayed-candles") === String(expected),
    n, { timeout: 30000 });
    position = n;
    assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-fills"), "0");
  }
  const overlay = page.locator(".replay-execution-overlay");
  // The owner first reported an implausible upward H1 ray at the INITIAL
  // GRASS publication. Capture that exact causal instant with original
  // candle anchors loaded, not merely the later opposite trend.
  const firstH1Index = byEventTime.get(firstMain.available_at_ms);
  assert.ok(Number.isInteger(firstH1Index), "initial H1 main publication must be a real M5 close");
  await advanceTo(firstH1Index + 1);
  await page.getByRole("button", { name: "H1", exact: true }).click();
  await page.waitForFunction(expected =>
    document.querySelector(".replay-chart-shell")?.getAttribute("data-displayed-candles") === String(expected),
  archive.context_1h.length + 11);
  assert.ok(Number(await overlay.getAttribute("data-painted-geometry")) >= 2,
    "initial H1 main and target must render against their real context OHLC");
  const wickProjections = JSON.parse(await overlay.getAttribute("data-h1-main-wick-supports") ?? "[]");
  const startingMain = wickProjections.find(line => line.origin_ms === firstMain.from_ms);
  assert.ok(startingMain, "first H1 main must be drawn at its original source wick");
  assert.equal(startingMain.adjusted, false,
    "published H1 main must not substitute a later wick for its structural third pivot");
  assert.equal(startingMain.support_ms, firstMain.to_ms,
    "the frozen first H1 slope must retain its actual confirmed second LOW");
  assert.equal(startingMain.price, Number(firstMain.to_price));
  console.log("REAL_FIRST_H1_STRUCTURAL_ANCHORS_OK " + JSON.stringify(startingMain));
  // The real first frame previously showed a BLUE M5 continuation ray
  // crossing the entire H1 pane. Keep its history, but only through its
  // own M5 confirmation time on the coarser H1 chart.
  const blueBeforeFirstH1 = archive.geometry.some(line =>
    line.kind === "REFERENCE_5M" && line.available_at_ms <= firstMain.available_at_ms);
  if (blueBeforeFirstH1) {
    await page.waitForFunction(() =>
      Number(document.querySelector(".replay-execution-overlay")
        ?.getAttribute("data-painted-m5-on-h1")) > 0);
    const earlySpans = JSON.parse(await overlay.getAttribute("data-m5-h1-spans") ?? "[]");
    await page.evaluate(() => new Promise(resolve =>
      requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const blueSpans = JSON.parse(await overlay.getAttribute("data-m5-h1-spans") ?? "[]");
    console.log("FIRST_H1_M5_SPANS_INITIAL " + JSON.stringify(earlySpans));
    console.log("FIRST_H1_M5_SPANS_STABLE " + JSON.stringify(blueSpans));
    await page.screenshot({
      path: join(screenshotDir, "real-h1-first-anchors.png"), fullPage: true,
    });
    assert.ok(blueSpans.length > 0, "expected actual M5 history on H1, not a hidden layer");
    for (const span of blueSpans) {
      assert.ok(span.to_x >= span.from_x && span.to_x - span.from_x < 150,
        "the M5 source-local segment must not become an H1 pane-wide blue ray: " +
        JSON.stringify(span));
      assert.ok(span.until_ms <= firstMain.available_at_ms,
        "H1 chart revealed a future M5 visual segment");
    }
    console.log("FIRST_H1_M5_PROJECTION_OK " + JSON.stringify(blueSpans));
  }
  await page.screenshot({
    path: join(screenshotDir, "real-h1-first-anchors.png"), fullPage: true,
  });
  await page.getByRole("button", { name: "M5", exact: true }).click();
  await page.waitForFunction(() =>
    document.querySelector(".replay-chart-shell")?.getAttribute("data-chart-timeframe") === "5m");
  assert.equal(await overlay.getAttribute("data-painted-m5-on-h1"), "0",
    "M5 native timeframe must never use the H1-only shortened projection");
  assert.equal(await overlay.getAttribute("data-m5-h1-spans"), "[]",
    "M5's own blue reference must never inherit the H1 visual cap");
  const m5RayEnds = JSON.parse(await overlay.getAttribute("data-active-m5-ray-ends") ?? "[]");
  assert.ok(m5RayEnds.length > 0,
    "real GRASS first confirmed blue reference must render as an active M5 ray");
  for (const ray of m5RayEnds) {
    assert.ok(ray.end_x <= ray.pane_width &&
      ray.end_x >= ray.last_candle_x &&
      ray.end_x - ray.last_candle_x <= 36.01,
    "active blue M5 ray must stop near last price candle: " + JSON.stringify(ray));
  }
  console.log("REAL_ACTIVE_M5_RAY_SHORT_OK " + JSON.stringify(m5RayEnds));

  // A newly confirmed LOWER LOW must unlock its preceding confirmed
  // LOWER HIGH as the real next BEAR support, not keep the obsolete
  // 27 Aug source when that source would pierce subsequent H1 wicks.
  const descendingVersions = [
    [Date.UTC(2026, 7, 29, 6), Date.UTC(2026, 7, 28, 9),
      Date.UTC(2026, 7, 28, 23), 0.3566],
    [Date.UTC(2026, 7, 29, 11), Date.UTC(2026, 7, 28, 9),
      Date.UTC(2026, 7, 29, 5), 0.3546],
  ];
  for (const [publishedAt, originAt, supportAt, supportPrice] of descendingVersions) {
    const version = yellow.find(line =>
      line.side === "BEAR" && line.available_at_ms === publishedAt &&
      line.from_ms === originAt && line.to_ms === supportAt &&
      Number(line.to_price) === supportPrice);
    assert.ok(version,
      "confirmed GRASS lower-low must publish next frozen lower-high: " + publishedAt);
    const movedPrior = archive.hourly_prior_updates.find(level =>
      level.side === "BEAR" && level.available_at_ms === publishedAt &&
      level.trend_version === publishedAt &&
      level.at_ms === supportAt && Number(level.price) === supportPrice);
    assert.ok(movedPrior,
      "purple BEAR prior must move with the new confirmed lower-high: " + publishedAt);
  }
  const lastBearBreak = breaks.find(event =>
    event.previous_side === "BEAR" &&
    event.confirmed_at_ms === Date.UTC(2026, 7, 29, 13, 5));
  assert.ok(lastBearBreak &&
    Number(lastBearBreak.prior_price) === 0.3546 &&
    lastBearBreak.prior_at_ms === Date.UTC(2026, 7, 29, 5),
    "29 Aug next-hour OPEN must break the last moved purple prior 0.35460");
  for (const { event, i, opposite } of proven) {
    const index = byEventTime.get(event.confirmed_at_ms);
    assert.ok(Number.isInteger(index), "kernel break must be attached to an actual M5 close");
    const firstYellowIndex = byEventTime.get(opposite.available_at_ms);
    assert.ok(firstYellowIndex > index, "new yellow main line must NOT predate the break");
    if (event.previous_side === "BEAR" &&
        event.confirmed_at_ms === Date.UTC(2026, 7, 29, 13, 5)) {
      for (const [publishedAt, originAt, supportAt, supportPrice] of descendingVersions) {
        const structuralIndex = byEventTime.get(publishedAt);
        assert.ok(Number.isInteger(structuralIndex) && structuralIndex >= position);
        await advanceTo(structuralIndex + 1);
        await page.getByRole("button", { name: "H1", exact: true }).click();
        const supports = JSON.parse(await overlay.getAttribute("data-h1-main-wick-supports") ?? "[]");
        assert.equal(supports.length, 1,
          "new confirmed lower-high/low must replace old visible yellow slope, not add a second");
        const version = supports.find(x =>
          x.origin_ms === originAt && x.support_ms === supportAt &&
          x.price === supportPrice && x.adjusted === false);
        assert.ok(version,
          "real browser must paint the new BEAR lower-high at its confirmed H1 wick");
        assert.match(await page.getByRole("status", { name: "Приор H1" }).innerText(),
          new RegExp(supportPrice.toFixed(4).replace(".", "\\.")),
          "visible purple prior must equal the newest confirmed lower-high");
        await page.screenshot({
          path: join(screenshotDir, "real-h1-bear-lower-high-" + publishedAt + ".png"),
          fullPage: true,
        });
        await page.getByRole("button", { name: "M5", exact: true }).click();
      }
      console.log("REAL_GRASS_BEAR_LOWER_HIGH_VERSIONS_OK");
    }
    await advanceTo(index);
    const priorText = await page.getByRole("status", { name: "Приор H1" }).innerText();
    assert.match(priorText, new RegExp(String(Number(event.prior_price)).replace(".", "\\.")));
    assert.doesNotMatch(priorText, /Исторический \(сломанный\)/);
    assert.equal(await overlay.getAttribute("data-visible-early-geometry"), "0",
      "canonical Python archive must never show a three-pivot preview");
    await advanceTo(index + 1);
    const waitingText = await page.getByRole("status", { name: "Подтверждение слома приора H1" }).innerText();
    assert.match(waitingText,
      new RegExp(String(Number(event.prior_price)).replace(".", "\\.")));
    assert.match(waitingText, /жёлтая H1-линия ещё не подтверждена/);
    assert.match(await page.getByRole("status", { name: "Приор H1" }).innerText(),
      /Исторический \(сломанный\)/);
    assert.equal(await overlay.getAttribute("data-visible-geometry"), "0",
      "broken yellow movement must be retired, no fabricated opposite slope");
    await page.screenshot({
      path: join(screenshotDir, `real-h1-break-${i + 1}.png`), fullPage: true,
    });
    await advanceTo(firstYellowIndex + 1);
    assert.equal(await overlay.getAttribute("data-visible-early-geometry"), "0",
      "a published canonical four-pivot H1 must not backfill provisional M5/H1 lines");
    assert.ok(Number(await overlay.getAttribute("data-visible-geometry")) >= 2,
      "opposite confirmed MAIN_1H and TARGET_1H must actually render");
    assert.ok(Number(await overlay.getAttribute("data-painted-geometry")) >= 2,
      "real H1 yellow lines must be painted on the browser canvas");
    assert.match(await page.getByRole("status", { name: "Статус трендовой геометрии" }).innerText(),
      /полная подтверждённая часовая пара 1–3 \/ 2–4/,
      "full four-pivot diagnostics must replace the earlier provisional wording");
    assert.match(await page.getByRole("status", { name: "Подтверждение слома приора H1" }).innerText(),
      /жёлтая H1-линия подтверждена и отображается/);
    assert.doesNotMatch(await page.getByRole("status", { name: "Приор H1" }).innerText(),
      /Исторический \(сломанный\)/);
    await page.getByRole("button", { name: "H1", exact: true }).click();
    assert.equal(await page.locator(".replay-chart-shell").getAttribute("data-chart-timeframe"), "1h");
    if (opposite.side === "BULL" &&
        opposite.from_ms === Date.UTC(2026, 7, 29, 8)) {
      const slopes = JSON.parse(await overlay.getAttribute("data-h1-main-wick-supports") ?? "[]");
      const mainIII = slopes.find(x => x.origin_ms === opposite.from_ms);
      assert.ok(mainIII, "owner's new BULL III must be visible in real H1");
      assert.equal(mainIII.support_ms, Date.UTC(2026, 7, 30, 6));
      assert.equal(mainIII.price, 0.3606,
        "after earlier BEAR prior break, BULL III must retain its first confirmed HIGHER LOW");
      assert.equal(mainIII.adjusted, false);
      console.log("REAL_GRASS_H1_III_SUPPORT_UNCHANGED_OK " + JSON.stringify(mainIII));
    }
    await page.screenshot({
      path: join(screenshotDir, `real-h1-opposite-${i + 1}.png`), fullPage: true,
    });
    await page.getByRole("button", { name: "M5", exact: true }).click();
    assert.equal(await page.locator(".replay-chart-shell").getAttribute("data-chart-timeframe"), "5m");
    await backward.click();
    await page.waitForFunction(expected =>
      document.querySelector(".replay-chart-shell")?.getAttribute("data-displayed-candles") === String(expected),
    firstYellowIndex, { timeout: 15000 });
    assert.equal(await overlay.getAttribute("data-visible-geometry"), "0",
      "rewinding one M5 must undo first confirmed opposite yellow");
    const rewoundStatus = await page.getByRole("status", { name: "Подтверждение слома приора H1" }).innerText();
    assert.match(rewoundStatus, /жёлтая H1-линия ещё не подтверждена|полной пары ещё нет/,
      "rewind must remove the future four-pivot opposite H1 pair");
    assert.doesNotMatch(rewoundStatus, /жёлтая H1-линия подтверждена и отображается/,
      "no future four-pivot state after rewinding");
    await forward.click();
    await page.waitForFunction(expected =>
      document.querySelector(".replay-chart-shell")?.getAttribute("data-displayed-candles") === String(expected),
    firstYellowIndex + 1, { timeout: 15000 });
    assert.ok(Number(await overlay.getAttribute("data-visible-geometry")) >= 2,
      "forward step must reproduce identical real H1 geometry");
    position = firstYellowIndex + 1;
  }
  // The owner's earlier IV=0.35890 interpretation was made BEFORE the
  // subsequently supplied lower-low correction. The newly confirmed BEAR
  // lower-high retires the old descending movement earlier (29 Aug), so the
  // following BULL 1--3/2--4 is published sooner. This is a NEW diagnostic
  // timeline, not a claim of owner visual acceptance.
  const revisedBullMain = yellow.find(line =>
    line.side === "BULL" &&
    line.from_ms === Date.UTC(2026, 7, 29, 8) &&
    line.to_ms === Date.UTC(2026, 7, 30, 6) &&
    Number(line.to_price) === 0.3606);
  const revisedPrior = archive.hourly_prior_updates.find(level =>
    level.side === "BULL" && level.at_ms === revisedBullMain?.to_ms &&
    Number(level.price) === 0.3606);
  const revisedBreak = breaks.find(event =>
    event.previous_side === "BULL" && Number(event.prior_price) === 0.3606 &&
    event.next_hour_open_ms === Date.UTC(2026, 7, 31, 0));
  assert.ok(revisedBullMain && revisedPrior && revisedBreak,
    "earlier BEAR lower-high requires a causal NEW BULL main/prior/break timeline");
  assert.equal(Number(revisedBullMain.from_price), 0.3437);
  assert.equal(revisedBreak.prior_at_ms, revisedBullMain.to_ms);
  assert.ok(revisedBullMain.available_at_ms < revisedBreak.confirmed_at_ms);
  assert.ok(revisedPrior.available_at_ms < revisedBreak.confirmed_at_ms);
  const openingCandle = archive.events.find(event =>
    event.candle?.start_ms === revisedBreak.next_hour_open_ms)?.candle;
  assert.ok(openingCandle && Number(openingCandle.open) < 0.3606 &&
    Number(openingCandle.close) > 0.3606,
    "first M5 OPEN must be below prior even though that very M5 CLOSE already reclaims");
  const breakIndex = byEventTime.get(revisedBreak.confirmed_at_ms);
  assert.ok(breakIndex >= position);
  await advanceTo(breakIndex);
  assert.doesNotMatch(await page.getByRole("status", { name: "Приор H1" }).innerText(),
    /Исторический \(сломанный\)/, "BULL prior must stay active until the next OPEN");
  await advanceTo(breakIndex + 1);
  assert.match(await page.getByRole("status", { name: "Приор H1" }).innerText(),
    /Исторический \(сломанный\)/,
    "an M5 closing above prior must not undo break confirmed by next-hour OPEN");
  assert.equal(await overlay.getAttribute("data-visible-geometry"), "0",
    "do not fabricate an opposite four-pivot trend from the first recovering M5");
  const laterIndex = archive.events.findIndex(event =>
    event.time_ms > revisedBreak.confirmed_at_ms &&
    event.time_ms < revisedBreak.next_hour_open_ms + 3_600_000 &&
    Number(event.candle?.close) > 0.3606);
  assert.ok(laterIndex > breakIndex);
  await advanceTo(laterIndex + 1);
  assert.match(await page.getByRole("status", { name: "Приор H1" }).innerText(),
    /Исторический \(сломанный\)/,
    "the reclaimed price never resurrects a structurally broken BULL prior");
  await page.getByRole("button", { name: "H1", exact: true }).click();
  await page.screenshot({
    path: join(screenshotDir, "real-h1-revised-IV-reclaim.png"), fullPage: true,
  });
  await page.getByRole("button", { name: "M5", exact: true }).click();
  console.log("REAL_GRASS_REVISED_I_IV_RECLAIM_OK " + JSON.stringify({
    main_from_ms: revisedBullMain.from_ms, main_to_ms: revisedBullMain.to_ms,
    prior_at_ms: revisedPrior.at_ms, prior_price: revisedPrior.price,
    break_at_ms: revisedBreak.confirmed_at_ms,
    reclaim_at_ms: revisedBreak.confirmed_at_ms,
  }));
  assert.deepEqual(errors, [], "browser runtime errors");
  assert.ok(requests.every(uri => {
    const host = new URL(uri).hostname;
    return host === "127.0.0.1" || host === "localhost";
  }), "browser contacted a remote host, disallowed in isolated research");
  assert.ok(requests.every(uri => !new URL(uri).pathname.startsWith("/api")),
    "browser contacted a protected PAPER/backend API");
  console.log("REAL_BYBIT_H1_BROWSER_OK: " + proven.length +
    " real four-pivot opposite H1 sequence(s), no three-pivot preview, M5/H1 and reversible step");
  console.log("Read-only audit file: " + basename(archivePath));
} finally {
  if (browser) await browser.close();
  server.kill();
}

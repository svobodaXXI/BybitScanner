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
assert.equal(archive.hourly_prior_breaks.length, 3, "Three actual H1 reversals must be present");
const breaks = archive.hourly_prior_breaks;
const byEventTime = new Map(archive.events.map((event, index) => [event.time_ms, index]));
const yellow = archive.geometry.filter(item => item.kind === "MAIN_1H");
assert.equal(yellow.length, 4);
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
  await page.getByText("GRASSUSDT", { exact: false }).first().waitFor();
  assert.equal(await page.getByRole("textbox", { name: "Инструмент" }).inputValue(), "GRASSUSDT");
  assert.equal(await page.locator('input[type="date"]').nth(0).inputValue(), "2026-08-20");
  assert.equal(await page.locator('input[type="date"]').nth(1).inputValue(), "2026-08-27");
  assert.match(await page.locator("body").innerText(), /официального публичного архива/);
  assert.equal(await page.locator('[role="progressbar"]').getAttribute("aria-valuenow"), "0");
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-fills"), "0");
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
  for (let i = 0; i < breaks.length; i++) {
    const event = breaks[i];
    const index = byEventTime.get(event.confirmed_at_ms);
    assert.ok(Number.isInteger(index), "kernel break must be attached to an actual M5 close");
    const next = breaks[i + 1]?.confirmed_at_ms ?? Infinity;
    const opposite = yellow.find(line =>
      line.side === event.new_side &&
      line.available_at_ms >= event.confirmed_at_ms &&
      line.available_at_ms < next);
    assert.ok(opposite, "published opposite line must follow break and precede any next break");
    const firstYellowIndex = byEventTime.get(opposite.available_at_ms);
    assert.ok(firstYellowIndex > index, "new yellow main line must NOT predate the break");
    await advanceTo(index);
    const priorText = await page.getByRole("status", { name: "Приор H1" }).innerText();
    assert.match(priorText, new RegExp(String(Number(event.prior_price)).replace(".", "\\.")));
    assert.doesNotMatch(priorText, /Исторический \(сломанный\)/);
    if (i === 0) {
      assert.equal(await page.getByRole("status", { name: "Подтверждение слома приора H1" }).count(), 0);
    }
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
    if (i === 2) {
      // On the real audited GRASSUSDT reversal, the LOW-HIGH-LOW H1
      // main is confirmed at 05:00 UTC, six hours BEFORE the fourth
      // pivot licenses the full 1-3/2-4 pair at 11:00 UTC.
      const earlyH1Time = Date.UTC(2026, 7, 24, 5, 0);
      const earlyH1Index = byEventTime.get(earlyH1Time);
      assert.ok(earlyH1Index < firstYellowIndex);
      await advanceTo(earlyH1Index);
      // Earlier slopes must remain visible rather than vanish when the
      // current preview changes. Only this new version is still future.
      const beforeEarlyH1 = Number(await overlay.getAttribute("data-visible-early-geometry"));
      await advanceTo(earlyH1Index + 1);
      const afterEarlyH1 = Number(await overlay.getAttribute("data-visible-early-geometry"));
      assert.ok(afterEarlyH1 > beforeEarlyH1,
        "new H1 preview must be appended to previously drawn early history");
      await backward.click();
      assert.equal(Number(await overlay.getAttribute("data-visible-early-geometry")), beforeEarlyH1,
        "rewind one candle hides the just-published H1 line but preserves older lines");
      await forward.click();
      assert.equal(Number(await overlay.getAttribute("data-visible-early-geometry")), afterEarlyH1,
        "forward redraws the same frozen history without duplicating lines");
      assert.ok(Number(await overlay.getAttribute("data-painted-geometry")) >= 1,
        "early H1 main must be painted, not merely calculated");
      assert.match(await page.getByRole("status", { name: "Статус трендовой геометрии" }).innerText(),
        /показана предварительная жёлтая H1 по трём подтверждённым экстремумам/,
        "diagnostics must describe the actually painted three-pivot provisional H1");
      assert.match(await page.getByRole("status", { name: "Подтверждение слома приора H1" }).innerText(),
        /Предварительная противоположная жёлтая H1-линия показана/,
        "prior-break status must not claim no opposite H1 is painted");
      await page.getByRole("button", { name: "H1", exact: true }).click();
      await page.screenshot({ path: join(screenshotDir, "real-h1-early-main.png"), fullPage: true });
      await page.getByRole("button", { name: "M5", exact: true }).click();
      const earlyBlueIndex = byEventTime.get(Date.UTC(2026, 7, 24, 7, 5));
      assert.ok(earlyBlueIndex > earlyH1Index && earlyBlueIndex < firstYellowIndex);
      await advanceTo(earlyBlueIndex + 1);
      assert.ok(Number(await overlay.getAttribute("data-visible-early-geometry")) >= 2,
        "early M5 reference must be visible before four-pivot H1 confirmation");
      assert.match(await page.getByRole("status", { name: "Статус трендовой геометрии" }).innerText(),
        /Ранних синих M5: [1-9][0-9]*\./,
        "diagnostics must acknowledge actual early M5 blue candidates");
      await page.screenshot({ path: join(screenshotDir, "real-m5-early-reference.png"), fullPage: true });
    }
    await advanceTo(firstYellowIndex + 1);
    if (i === 2) {
      assert.ok(Number(await overlay.getAttribute("data-visible-early-geometry")) >= 1,
        "earlier M5 guide history survives full H1 confirmation");
    }
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
      "rewind must remove the fully confirmed pair, but may retain an earlier three-pivot preview");
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
  assert.deepEqual(errors, [], "browser runtime errors");
  assert.ok(requests.every(uri => {
    const host = new URL(uri).hostname;
    return host === "127.0.0.1" || host === "localhost";
  }), "browser contacted a remote host, disallowed in isolated research");
  assert.ok(requests.every(uri => !new URL(uri).pathname.startsWith("/api")),
    "browser contacted a protected PAPER/backend API");
  console.log("REAL_BYBIT_H1_BROWSER_OK: three confirmed reversals, prior break, new H1 canvas, M5/H1 and reversible step");
  console.log("Read-only audit file: " + basename(archivePath));
} finally {
  if (browser) await browser.close();
  server.kill();
}

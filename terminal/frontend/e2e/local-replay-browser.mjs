/** Browser acceptance of the standalone LOCAL-only simulator, not the terminal. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chromium } from "@playwright/test";

const screenshotDir = await mkdtemp(join(tmpdir(), "machine-time-ui-"));
const server = spawn("python", ["../../research/local_replay_viewer/server.py"], {
  stdio: ["ignore", "pipe", "pipe"],
});
let browser;
let stderr = "";
server.stderr.on("data", (chunk) => { stderr += chunk.toString(); });

async function waitForLocalUrl() {
  let stdout = "";
  return await new Promise((resolve, reject) => {
    const watchdog = setTimeout(() => reject(new Error("Local server startup timeout: " + stderr)), 15000);
    const onExit = (code) => {
      clearTimeout(watchdog);
      reject(new Error("Local server exited " + code + ": " + stderr));
    };
    server.once("exit", onExit);
    server.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
      const match = stdout.match(/http:\/\/127\.0\.0\.1:\d+\/replay\.html/);
      if (!match) return;
      clearTimeout(watchdog);
      server.off("exit", onExit);
      resolve(match[0]);
    });
  });
}

try {
  const localUrl = await waitForLocalUrl();
  browser = await chromium.launch({
    headless: true,
    ...(process.env.LOCAL_REPLAY_CHROME ? { executablePath: process.env.LOCAL_REPLAY_CHROME } : {}),
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 920 }, deviceScaleFactor: 1 });
  const errors = [];
  const requests = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (req) => requests.push(req.url()));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });

  await page.goto(localUrl, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Машина времени" }).waitFor();
  assert.match(await page.locator("body").innerText(), /SIMULATION ONLY/);
  assert.match(await page.locator("body").innerText(), /Синтетический пример/);
  await page.waitForFunction(() => document.querySelectorAll(".replay-chart canvas").length > 0);
  assert.equal(await page.locator('[role="progressbar"]').getAttribute("aria-valuenow"), "0");
  const progress = page.locator('[role="progressbar"]');
  const forward = page.getByRole("button", { name: "Шаг вперёд ▶", exact: true });
  const backward = page.getByRole("button", { name: "◀ Шаг назад", exact: true });
  assert.equal(await backward.isDisabled(), true);
  await forward.click();
  const firstStep = Number(await progress.getAttribute("aria-valuenow"));
  assert.ok(firstStep > 0);
  await forward.click();
  const secondStep = Number(await progress.getAttribute("aria-valuenow"));
  assert.ok(secondStep > firstStep, "second closed candle advances the recording");
  await backward.click();
  assert.equal(Number(await progress.getAttribute("aria-valuenow")), firstStep);
  await forward.click();
  assert.equal(Number(await progress.getAttribute("aria-valuenow")), secondStep);
  await page.getByRole("button", { name: "В начало" }).click();
  assert.equal(await page.locator('[role="progressbar"]').getAttribute("aria-valuenow"), "0");

  // The synthetic demo now contains enough true closed candles to show ADX
  // after its 14/14 warmup. Check TRUE-price markers, not shifted chart arrows.
  const demoIndicator = page.getByRole("group", { name: "Индикатор ADX DMI" });
  await page.locator(".replay-rate input").fill("60");
  await page.getByRole("button", { name: "Пуск", exact: false }).click();
  await page.waitForFunction(() => document.querySelector('[role="progressbar"]')?.getAttribute("aria-valuenow") === "100");
  assert.match(await demoIndicator.innerText(), /\+DI [0-9]/);
  assert.match(await demoIndicator.innerText(), /−DI [0-9]/);
  assert.match(await demoIndicator.innerText(), /ADX [0-9]/);
  assert.match(await page.locator("body").innerText(), /64 \/ 1 \/ 1/);
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-fills"), "2");
  assert.equal(await page.locator(".replay-chart .series-markers").count(), 0);
  await page.getByRole("button", { name: "В начало" }).click();
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-fills"), "0");

  // Public history response is mocked at the HTTP boundary. A separate Python
  // fixture covers the real server handler and unsigned public GET adapter.
  const t = Date.UTC(2026, 9, 1);
  const history = {
    source: "SIMULATION",
    simulation_run_id: "browser_fixture",
    mode: "MARKET_ONLY",
    market_data_source: "BYBIT_PUBLIC_KLINE",
    symbol: "BTCUSDT",
    timeframe: "5m",
    events: Array.from({ length: 40 }, (_, i) => ({
      source: "SIMULATION", simulation_run_id: "browser_fixture",
      sequence: i + 1, kind: "CANDLE_CLOSED",
      time_ms: t + (i + 1) * 300000,
      candle: {
        start_ms: t + i * 300000, end_ms: t + (i + 1) * 300000,
        open: "100", high: "102", low: "98", close: i === 33 ? "101.5" : "101", volume: "100",
      },
    })),
    dmi_5m: {
      source: "SIMULATION", timeframe: "5m", di_length: 14, adx_smoothing: 14,
      points: Array.from({ length: 40 }, (_, i) => ({
        time_ms: t + (i + 1) * 300000,
        plus_di: i < 14 ? null : String(20 + i / 10),
        minus_di: i < 14 ? null : i === 30 ? "20.5" : String(10 + i / 20),
        adx: i < 27 ? null : String(15 + i / 5),
        crossings: i === 30 ? [
          { time_ms: t + (i + 1) * 300000, side: "MINUS",
            direction: "UP", comparator: "LEVEL_20" },
        ] : undefined,
      })),
    },
    geometry_warmup_hours: 72,
    geometry: [{
      kind: "MAIN_1H", side: "BULL",
      available_at_ms: t + 900000, from_ms: t - 12*300000,
      to_ms: t - 6*300000,
      from_price: "99", to_price: "99.1",
      trend_version: t + 900000, classification: "UNVALIDATED_GEOMETRY_ONLY",
    }, {
      kind: "TARGET_1H", side: "BULL",
      available_at_ms: t + 900000, from_ms: t - 12*300000,
      to_ms: t - 6*300000, from_price: "105", to_price: "105",
      trend_version: t + 900000, classification: "UNVALIDATED_GEOMETRY_ONLY",
    }, {
      kind: "REFERENCE_5M", side: "BULL",
      available_at_ms: t + 1200000, from_ms: t - 12*300000,
      to_ms: t - 6*300000, from_price: "99", to_price: "99",
      trend_version: t + 900000, classification: "UNVALIDATED_GEOMETRY_ONLY",
    }],
    h017_blue_risk_previews: [{
      source: "SIMULATION", kind: "BLUE_5M_OPEN",
      classification: "UNVALIDATED_GEOMETRY_ONLY",
      time_ms: t + 11*300000, open_ms: t + 10*300000,
      blue_available_at_ms: t + 1200000, trend_version: t + 900000,
      side: "LONG", entry_price: "100", blue_price: "99",
      target_price: "105", risk_status: "RISK_PASS",
      stop_price: "99.3", quantity: "0.1",
    }],
    observations: [
      { kind: "MAIN_1H_TOUCH", side: "BULL",
        time_ms: t + 33 * 300000, price: "101", line_price: "99.75",
        trend_version: t + 900000, classification: "UNVALIDATED_GEOMETRY_ONLY" },
      { kind: "MAIN_1H_REACTION", side: "BULL",
        time_ms: t + 34 * 300000, touch_time_ms: t + 33 * 300000,
        price: "101.5", line_price: "99.7666666667",
        trend_version: t + 900000, classification: "UNVALIDATED_GEOMETRY_ONLY" },
    ],
  };
  await page.route("**/local-replay/history?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(history),
    });
  });
  await page.getByRole("button", { name: "Загрузить Bybit (без сделок)" }).click();
  await page.getByText("РЕАЛЬНЫЕ СВЕЧИ BYBIT", { exact: false }).waitFor();
  assert.match(await page.locator("body").innerText(), /browser_fixture/);
  const indicator = page.getByRole("group", { name: "Индикатор ADX DMI" });
  assert.match(await indicator.innerText(), /ADX\/DMI \(14, 14\)/);
  assert.match(await indicator.innerText(), /Уровень 20/);
  assert.match(await indicator.innerText(), /ADX —/);
  await page.getByRole("button", { name: "Пуск", exact: false }).click();
  await page.waitForFunction(() => document.querySelector('[role="progressbar"]')?.getAttribute("aria-valuenow") === "100");
  assert.match(await page.locator("body").innerText(), /40 \/ 0 \/ 0/);
  assert.match(await indicator.innerText(), /\+DI 23\.9/);
  assert.match(await indicator.innerText(), /ADX 22\.8/);
  assert.ok((await page.locator(".replay-chart canvas").count()) >= 4);
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-fills"), "0");
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-geometry"), "3");
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-painted-geometry"), "3");
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-priors"), "1");
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-painted-priors"), "1");
  // Diagnostics and geometry observation decorations stay hidden until requested.
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-observations"), "0");
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-blue-risk"), "0");
  await page.getByText("Диагностика", { exact: true }).click();
  await page.getByLabel("Показать опорные маркеры").check();
  await page.waitForFunction(() => document.querySelector(".replay-execution-overlay")?.dataset.visibleObservations === "2");
  assert.match(await page.getByRole("status", { name: "Приор H1" }).innerText(), /99\.1/);
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-blue-risk"), "1");
  assert.match(await page.getByRole("status", { name: "H-017 риск синей M5" }).innerText(),
    /открытий за линией 1, из них риск ≥1:1 — 1/);
  assert.match(await page.getByRole("status", { name: "H-017 сравнение DMI и исходов" }).innerText(),
    /цель раньше стопа 0, стоп раньше цели 1, оба в одной M5 0, ещё не определено 0/);
  assert.match(await page.getByRole("status", { name: "Пересечения ADX/DMI" }).innerText(),
    /пересечений на закрытых M5: 1/);
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-observations"), "2");
  assert.match(await page.getByRole("status", { name: "Статус трендовой геометрии" }).innerText(),
    /Касаний 1–3: 1; движений от линии: 1/);
  assert.match(await page.getByRole("status", { name: "Статус трендовой геометрии" }).innerText(), /Предыстория.*72 ч/);
  await page.getByLabel("Показать опорные маркеры").uncheck();
  await page.getByText("Диагностика", { exact: true }).click();
  await page.mouse.move(620, 660); // Crosshair must not create DMI dots.
  await page.screenshot({ path: join(screenshotDir, "machine-time-browser.png"), fullPage: true });

  assert.deepEqual(errors, [], "Browser runtime errors: " + errors.join("; "));
  assert.ok(requests.every((u) => {
    const parsed = new URL(u);
    return parsed.hostname === "127.0.0.1" || parsed.hostname === "localhost";
  }), "Viewer must not contact VPS/PAPER/external accounts");
  assert.ok(requests.every((u) => !new URL(u).pathname.startsWith("/api")), "No PAPER API requests");
  console.log("LOCAL_REPLAY_BROWSER_OK (real Chromium, local server, chart, controls, isolated market-only data)");
  console.log("UI screenshot: " + join(screenshotDir, "machine-time-browser.png"));
} finally {
  if (browser) await browser.close();
  server.kill();
  // The screenshot is copied by CI before its temporary directory is removed.
  // CI can pass an output directory to keep the visual evidence.
  if (process.env.LOCAL_REPLAY_E2E_SCREENSHOTS) {
    const { mkdir, copyFile } = await import("node:fs/promises");
    await mkdir(process.env.LOCAL_REPLAY_E2E_SCREENSHOTS, { recursive: true });
    await copyFile(
      join(screenshotDir, "machine-time-browser.png"),
      join(process.env.LOCAL_REPLAY_E2E_SCREENSHOTS, "machine-time-browser.png"),
    ).catch(() => {});
  }
  await rm(screenshotDir, { recursive: true, force: true });
}

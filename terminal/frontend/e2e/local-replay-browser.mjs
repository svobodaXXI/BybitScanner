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
  await page.getByRole("button", { name: "Шаг" }).click();
  assert.ok(Number(await page.locator('[role="progressbar"]').getAttribute("aria-valuenow")) > 0);
  await page.getByRole("button", { name: "В начало" }).click();
  assert.equal(await page.locator('[role="progressbar"]').getAttribute("aria-valuenow"), "0");

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
        open: "100", high: "102", low: "98", close: "101", volume: "100",
      },
    })),
    dmi_5m: {
      source: "SIMULATION", timeframe: "5m", di_length: 14, adx_smoothing: 14,
      points: Array.from({ length: 40 }, (_, i) => ({
        time_ms: t + (i + 1) * 300000,
        plus_di: i < 14 ? null : String(20 + i / 10),
        minus_di: i < 14 ? null : String(10 + i / 20),
        adx: i < 27 ? null : String(15 + i / 5),
      })),
    },
    geometry: [{
      kind: "MAIN_1H", side: "BULL",
      available_at_ms: t + 900000, from_ms: t, to_ms: t + 300000,
      from_price: "98", to_price: "99",
      trend_version: t + 900000, classification: "UNVALIDATED_GEOMETRY_ONLY",
    }],
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

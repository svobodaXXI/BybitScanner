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

  let simEnabled = false;
  await page.route("**/local-replay/simulation/status", async route => {
    await route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({
        namespace: "SIMULATION", can_attempt: simEnabled,
        wedge_engine_available: simEnabled,
        python_dependencies_available: simEnabled,
        archive_files_present: simEnabled,
        wedge_risk_profile_present: simEnabled,
      }),
    });
  });
  await page.goto(localUrl, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Машина времени" }).waitFor();
  assert.match(await page.locator("body").innerText(), /SIMULATION ONLY/);
  assert.match(await page.locator("body").innerText(), /Синтетический пример/);
  await page.waitForFunction(() => document.querySelectorAll(".replay-chart canvas").length > 0);

  // Universal setup config changes only local React state, never live/PAPER IO.
  const setup = page.getByRole("region", { name: "Настройка стратегий и периода" });
  const all = setup.getByRole("checkbox", { name: "Все стратегии" });
  await all.check();
  assert.equal(await setup.getByRole("checkbox", { name: "Mirror — комплекс" }).isChecked(), true);
  assert.equal(await setup.getByRole("checkbox", { name: "Восходящий клин" }).isChecked(), true);
  assert.equal(await setup.getByRole("checkbox", { name: "Ikigai Box" }).isChecked(), true);
  await setup.getByRole("checkbox", { name: "Ikigai Box" }).uncheck();
  assert.equal(await setup.getByRole("checkbox", { name: "Mirror — комплекс" }).isChecked(), true);
  await setup.getByRole("button", { name: "Только клинья" }).click();
  assert.equal(await setup.getByRole("checkbox", { name: "Mirror — комплекс" }).isChecked(), false);
  assert.equal(await setup.getByRole("checkbox", { name: "Восходящий клин" }).isChecked(), true);
  assert.equal(await setup.getByRole("checkbox", { name: "Нисходящий клин" }).isChecked(), true);
  assert.equal(await setup.getByRole("checkbox", { name: "Зеркальные уровни" }).isChecked(), false);
  const startUtc = setup.getByLabel("Начало прогона UTC");
  const endUtc = setup.getByLabel("Конец прогона UTC");
  await startUtc.fill("2026-10-01T12:34");
  const incrementBar = setup.getByRole("group", { name: "Продлить период прогона" });
  assert.equal(await endUtc.inputValue(), "2026-10-02T12:33");
  const duration = setup.getByRole("status", { name: "Продолжительность прогона" });
  assert.match(await duration.innerText(), /1 день/);
  await incrementBar.getByRole("button", { name: "+1 час", exact: true }).click();
  assert.match(await duration.innerText(), /1 день 1 час/);
  assert.equal(await endUtc.inputValue(), "2026-10-02T13:33");
  await incrementBar.getByRole("button", { name: "+1 день", exact: true }).click();
  assert.equal(await endUtc.inputValue(), "2026-10-03T13:33");
  await incrementBar.getByRole("button", { name: "+1 неделя", exact: true }).click();
  assert.equal(await endUtc.inputValue(), "2026-10-10T13:33");
  await incrementBar.getByRole("button", { name: "+1 месяц", exact: true }).click();
  assert.equal(await endUtc.inputValue(), "2026-11-09T13:33");
  assert.match(await duration.innerText(), /1 месяц 9 дней 1 час/);
  await endUtc.fill("2026-10-11T18:45");
  assert.match(await duration.innerText(), /10 дней 6 часов 12 минут/);
  assert.equal(await incrementBar.getByRole("button", { name: "3 месяца · 90 дней" }).getAttribute("aria-pressed"), "false");
  const coordinates = setup.getByRole("textbox", { name: "Координаты прогона" });
  await coordinates.fill("XRPUSDT | 2026-09-11T00:00 | 2026-09-11T23:59");
  await setup.getByRole("button", { name: "Применить" }).click();
  assert.equal(await page.getByRole("textbox", { name: "Инструмент" }).inputValue(), "XRPUSDT");
  assert.equal(await startUtc.inputValue(), "2026-09-11T00:00");
  assert.equal(await endUtc.inputValue(), "2026-09-11T23:59");
  assert.match(await duration.innerText(), /1 день/);
  await coordinates.fill("PAPER | 2026-09-11T00:00 | 2026-09-11T23:59");
  await setup.getByRole("button", { name: "Применить" }).click();
  assert.equal(await page.getByRole("textbox", { name: "Инструмент" }).inputValue(), "XRPUSDT",
    "invalid pasted coordinates must not overwrite accepted symbol");
  await coordinates.fill("BTCUSDT | 2026-10-01T12:34 | 2026-10-11T18:45");
  await setup.getByRole("button", { name: "Применить" }).click();
  assert.equal(await page.getByRole("textbox", { name: "Инструмент" }).inputValue(), "BTCUSDT");
  const runWedge = setup.getByRole("button", { name: /Запустить клинья/ });
  assert.equal(await runWedge.isDisabled(), true,
    "no local verified archive and native risk profile => no virtual trading");
  // A loopback-only fixture verifies the UI transport; the actual engine's
  // checksum and original Robot integration are independently Python-tested.
  simEnabled = true;
  const posted = [];
  await page.route("**/local-replay/simulation/wedge", async route => {
    const data = route.request();
    posted.push({
      url: data.url(), method: data.method(),
      header: data.headers()["x-local-simulation"],
      body: data.postDataJSON(),
    });
    await route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({
        namespace: "SIMULATION", symbol: "BTCUSDT",
        scenario_type: "ORIGINAL_WEDGE_SCANNER_ROBOT_LOCAL_OHLC_SIMULATION",
        risk_terms_status: "EXPLICIT_RESEARCH_ASSUMPTIONS_NOT_EXCHANGE_VERIFIED",
        source_id: "BYBIT_PUBLIC_TRADES_RANGE_BROWSER_TEST_ONLY",
        requested_minutes: 1008, scanner_wedge_observations: 1,
        robot_retests_in_period: 1, submitted_protected_limits: 1,
        virtual_fills: 2, stop_exits: 0, take_exits: 1,
        realized_net_pnl: "3.71", unrealized_pnl: "0", total_net_pnl: "3.71",
        total_fees: "0.29", return_percent: "0.371", max_drawdown_percent: "0.1",
      }),
    });
  });
  await page.reload({ waitUntil: "networkidle" });
  const readySetup = page.getByRole("region", { name: "Настройка стратегий и периода" });
  await readySetup.getByRole("button", { name: "Только клинья" }).click();
  await readySetup.getByLabel("Начало прогона UTC").fill("2026-10-01T12:34");
  await readySetup.getByLabel("Конец прогона UTC").fill("2026-10-02T05:21");
  await readySetup.getByLabel("Виртуальный депозит").fill("1000");
  const runnable = readySetup.getByRole("button", { name: /Запустить клинья/ });
  assert.equal(await runnable.isDisabled(), false);
  await runnable.click();
  await readySetup.getByRole("status", { name: "Результаты виртуального прогона" }).waitFor();
  assert.match(await readySetup.innerText(), /3\.71 USDT/);
  assert.equal(posted.length, 1);
  assert.equal(posted[0].method, "POST");
  assert.equal(posted[0].header, "wedge");
  assert.deepEqual(posted[0].body, {
    symbol: "BTCUSDT", start_utc: "2026-10-01T12:34",
    end_utc_inclusive: "2026-10-02T05:21",
    selected_strategies: ["WEDGE_RISING", "WEDGE_FALLING"],
    initial_balance: "1000",
  });
  await readySetup.getByRole("checkbox", { name: "Все стратегии" }).check();
  assert.equal(await runnable.isDisabled(), true,
    "all strategies cannot be passed to wedge-only backend");
  assert.equal(requests.filter(url => url.includes("/api/") || url.includes("/v5/")).length, 0);

  // The entire replay control surface belongs beside the M5/H1 switch,
  // never in the file-import row above the chart.
  const controlBar = page.getByRole("group", { name: "Таймфрейм графика" });
  const playbackBar = controlBar.getByRole("group", { name: "Управление воспроизведением" });
  for (const [caption, symbol] of [["Пуск", "play"], ["Шаг назад", "backward"],
      ["Шаг вперёд", "forward"], ["В начало", "beginning"]]) {
    const button = playbackBar.getByRole("button", { name: caption, exact: true });
    assert.equal(await button.count(), 1);
    assert.equal((await button.innerText()).trim(), "");
    assert.equal(await button.locator('svg[data-player-icon="' + symbol + '"]').count(), 1);
  }
  assert.equal(await playbackBar.locator(".replay-rate input[type=range]").count(), 1);
  assert.equal(await page.locator(".replay-controls .replay-rate").count(), 0);
  const drawingBar = page.getByRole("group", { name: "Инструменты рисования" });
  const trendTool = drawingBar.getByRole("button", { name: "Трендовая" });
  assert.equal(await trendTool.getAttribute("title"), "Трендовая");
  assert.equal((await trendTool.innerText()).trim(), "", "drawing tool must have no visible text caption");
  assert.equal(await trendTool.locator('svg[data-tool-icon="trend"] path').count(), 1,
    "trendline has a graphical SVG pictogram");
  const fibTool = drawingBar.getByRole("button", { name: "Fibonacci" });
  assert.equal((await fibTool.innerText()).trim(), "", "Fibonacci uses a pictogram, not a text word");
  assert.equal(await fibTool.locator('svg[data-tool-icon="fibonacci"] path').count(), 1);
  assert.equal(await drawingBar.locator('button[aria-label] svg.replay-tool-icon').count(), 12,
    "ten drawing tools plus undo and delete all have true graphical icons");
  assert.equal(await page.locator('[role="progressbar"]').getAttribute("aria-valuenow"), "0");
  const progress = page.locator('[role="progressbar"]');
  const forward = page.getByRole("button", { name: "Шаг вперёд", exact: true });
  const backward = page.getByRole("button", { name: "Шаг назад", exact: true });
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
  const scrub = page.getByRole("slider", { name: "Перемотка воспроизведения" });
  await scrub.fill("12");
  assert.equal(await scrub.inputValue(), "12");
  assert.equal(await page.locator(".replay-chart-shell").getAttribute("data-displayed-candles"), "12");
  await backward.click();
  assert.equal(await scrub.inputValue(), "11");
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
  assert.equal(await page.locator(".replay-chart-shell").getAttribute("data-displayed-candles"), "40");
  await page.getByRole("button", { name: "H1", exact: true }).click();
  await page.waitForFunction(() => document.querySelector(".replay-chart-shell")?.dataset.displayedCandles === "3");
  assert.equal(await page.locator(".replay-chart-shell").getAttribute("data-chart-timeframe"), "1h");
  assert.equal(await page.getByRole("progressbar").getAttribute("aria-valuenow"), "100");
  await page.getByRole("button", { name: "M5", exact: true }).click();
  await page.waitForFunction(() => document.querySelector(".replay-chart-shell")?.dataset.displayedCandles === "40");
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-fills"), "0");
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-geometry"), "3");
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-painted-geometry"), "3");
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-priors"), "1");
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-painted-priors"), "1");
  // Manual annotations use the same UTC anchor across real M5/H1 candles;
  // they survive replay rewind and can be deleted without altering geometry.
  await page.getByRole("button", { name: "Горизонталь", exact: true }).click();
  await page.locator(".replay-drawing-layer canvas").click({ position: { x: 280, y: 160 } });
  assert.equal(await page.locator(".replay-drawing-layer").getAttribute("data-drawing-count"), "1");
  const undo = page.getByRole("button", { name: "Отменить последнюю фигуру" });
  assert.equal(await undo.isDisabled(), false);
  assert.equal(await undo.locator('svg[data-tool-icon="undo"] path').count(), 1);
  await page.locator(".replay-drawing-layer canvas").click({ position: { x: 280, y: 230 } });
  assert.equal(await page.locator(".replay-drawing-layer").getAttribute("data-drawing-count"), "2");
  await undo.click();
  assert.equal(await page.locator(".replay-drawing-layer").getAttribute("data-drawing-count"), "1");
  await page.getByRole("button", { name: "H1", exact: true }).click();
  await page.waitForFunction(() => document.querySelector(".replay-chart-shell")?.dataset.displayedCandles === "3");
  assert.equal(await page.locator(".replay-drawing-layer").getAttribute("data-drawing-count"), "1");
  await page.getByRole("button", { name: "M5", exact: true }).click();
  await backward.click();
  assert.match(await page.locator(".replay-drawing-count").innerText(), /1/);
  await forward.click();
  assert.equal(await page.locator(".replay-drawing-layer").getAttribute("data-drawing-count"), "1");
  await undo.click();
  assert.equal(await page.locator(".replay-drawing-layer").getAttribute("data-drawing-count"), "0");
  assert.equal(await undo.isDisabled(), true);
  // Undo manipulates only manual annotations, not scanner geometry.
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-geometry"), "3");
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

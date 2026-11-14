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
  assert.equal(await page.locator(".replay-badge").count(), 0,
    "no SIMULATION ONLY header badge");
  assert.equal(await page.locator(".replay-run-heading span").count(), 0,
    "no redundant local simulation/ticker banner");
  assert.equal(await page.locator(".replay-run-disclaimer").count(), 0,
    "no permanent strategy explanation beneath setup controls");
  assert.equal(await page.locator('.replay-note[aria-label="Ожидание нового графика"]').count(), 0,
    "no permanent pre-run hint above status cards");
  assert.equal(await page.locator(".replay-chart canvas").count(), 0,
    "the viewer starts blank; no synthetic candles appear by default");
  assert.equal(await page.locator(".replay-meta").count(), 1);
  assert.match(await page.locator(".replay-meta").innerText(), /Тикер и период не выбраны/);
  assert.equal(await page.getByRole("button", { name: /Запустить клинья/ }).count(), 0);
  assert.equal(await page.getByRole("button", { name: "Пуск" }).isDisabled(), true,
    "▶ becomes available after Apply");

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
  const incrementBar = setup.getByRole("group", { name: "Изменить период прогона" });
  assert.equal(await setup.locator(".replay-run-step").count(), 4);
  for (const unit of ["1 час", "1 день", "1 неделя", "1 месяц"]) {
    const pair = incrementBar.getByRole("group", { name: "Период " + unit });
    assert.equal(await pair.getByRole("button", { name: "Добавить " + unit }).count(), 1);
    assert.equal(await pair.getByRole("button", { name: "Убавить " + unit }).count(), 1);
  }
  assert.equal(await page.locator(".replay-history-controls").count(), 0,
    "obsolete second ticker/date/Bybit panel must never reappear");
  assert.equal(await setup.getByRole("button", { name: "Подгрузить период с Bybit" }).count(), 1);
  assert.equal(await incrementBar.getByRole("button", { name: "Подгрузить период с Bybit" }).count(), 1,
    "Bybit action must be alongside period steppers, not under end date");
  assert.equal(await setup.getByRole("button", { name: "3 месяца · 90 дней" }).count(), 0);
  assert.equal(await endUtc.inputValue(), "2026-10-02T12:33");
  const duration = setup.getByRole("status", { name: "Продолжительность прогона" });
  assert.match(await duration.innerText(), /1 день/);
  await incrementBar.getByRole("button", { name: "Добавить 1 час" }).click();
  assert.match(await duration.innerText(), /1 день 1 час/);
  assert.equal(await endUtc.inputValue(), "2026-10-02T13:33");
  await incrementBar.getByRole("button", { name: "Добавить 1 день" }).click();
  assert.equal(await endUtc.inputValue(), "2026-10-03T13:33");
  await incrementBar.getByRole("button", { name: "Добавить 1 неделя" }).click();
  assert.equal(await endUtc.inputValue(), "2026-10-10T13:33");
  await incrementBar.getByRole("button", { name: "Добавить 1 месяц" }).click();
  assert.equal(await endUtc.inputValue(), "2026-11-09T13:33");
  await incrementBar.getByRole("button", { name: "Убавить 1 месяц" }).click();
  assert.equal(await endUtc.inputValue(), "2026-10-10T13:33");
  await incrementBar.getByRole("button", { name: "Добавить 1 месяц" }).click();
  assert.match(await duration.innerText(), /1 месяц 9 дней 1 час/);
  await incrementBar.getByRole("button", { name: "Убавить 1 час" }).click();
  assert.equal(await endUtc.inputValue(), "2026-11-09T12:33");
  await incrementBar.getByRole("button", { name: "Убавить 1 день" }).click();
  assert.equal(await endUtc.inputValue(), "2026-11-08T12:33");
  await incrementBar.getByRole("button", { name: "Убавить 1 неделя" }).click();
  assert.equal(await endUtc.inputValue(), "2026-11-01T12:33");
  await endUtc.fill("2026-10-11T18:45");
  assert.match(await duration.innerText(), /10 дней 6 часов 12 минут/);
  assert.equal(await incrementBar.getByRole("button", { name: "Добавить 1 месяц" }).count(), 1);
  assert.equal(await incrementBar.getByRole("button", { name: "Убавить 1 месяц" }).count(), 1);
  const coordinates = setup.getByRole("textbox", { name: "Координаты прогона" });
  await coordinates.fill("XRPUSDT | 2026-09-11T00:00 | 2026-09-11T23:59");
  await setup.getByRole("button", { name: "Применить" }).click();
  assert.match(await page.locator(".replay-meta strong").first().innerText(), /XRPUSDT/);
  assert.equal(await startUtc.inputValue(), "2026-09-11T00:00");
  assert.equal(await endUtc.inputValue(), "2026-09-11T23:59");
  assert.match(await duration.innerText(), /1 день/);
  assert.match(await page.locator(".replay-meta").innerText(), /XRPUSDT.*2026-09-11T00:00/);
  const copyableSource = (await page.locator(".replay-meta strong").first().innerText()).trim();
  await coordinates.fill(copyableSource);
  await setup.getByRole("button", { name: "Применить" }).click();
  assert.equal(await setup.getByRole("alert").count(), 0, "copied Source must be accepted");
  assert.equal(await startUtc.inputValue(), "2026-09-11T00:00");
  assert.equal(await endUtc.inputValue(), "2026-09-11T23:59");
  assert.equal(await page.locator(".replay-chart canvas").count(), 0,
    "Apply must clear old candles immediately");
  await coordinates.fill("PAPER | 2026-09-11T00:00 | 2026-09-11T23:59");
  await setup.getByRole("button", { name: "Применить" }).click();
  assert.match(await page.locator(".replay-meta strong").first().innerText(), /XRPUSDT/,
    "invalid pasted coordinates must not overwrite accepted symbol");
  await coordinates.fill("BTCUSDT | 2026-10-01T12:34 | 2026-10-11T18:45");
  await setup.getByRole("button", { name: "Применить" }).click();
  assert.match(await page.locator(".replay-meta strong").first().innerText(), /BTCUSDT/);
  assert.equal(await page.getByRole("button", { name: /Запустить клинья/ }).count(), 0,
    "a second SIMULATION launch button must never reappear");
  assert.match(await page.locator(".replay-meta").innerText(), /BTCUSDT.*2026-10-01T12:34/);
  // A loopback-only fixture verifies the UI transport; the actual engine's
  // checksum and original Robot integration are independently Python-tested.
  simEnabled = true;
  const posted = [];
  await page.route("**/local-replay/simulation/wedge-stream", async route => {
    const data = route.request();
    posted.push({
      url: data.url(), method: data.method(),
      header: data.headers()["x-local-simulation"],
      body: data.postDataJSON(),
    });
    // Allow browser to assert the old DEMO is removed while computing.
    await new Promise(resolve => setTimeout(resolve, 300));
    const fixture = {
        namespace: "SIMULATION", symbol: "BTCUSDT",
        simulation_run_id: "browser_wedge_test",
        replay: {
          source: "SIMULATION", simulation_run_id: "browser_wedge_test",
          mode: "STRATEGY", demo: false, symbol: "BTCUSDT", timeframe: "5m",
          market_data_source: "BYBIT_OFFICIAL_PUBLIC_TRADES_DERIVED_5M",
          events: [
            { source: "SIMULATION", simulation_run_id: "browser_wedge_test",
              sequence: 1, kind: "CANDLE_CLOSED", time_ms: Date.UTC(2026, 9, 1, 12, 40),
              candle: { start_ms: Date.UTC(2026, 9, 1, 12, 35),
                end_ms: Date.UTC(2026, 9, 1, 12, 40),
                open: 40000, high: 40200, low: 39900, close: 40100, volume: 50 } },
            { source: "SIMULATION", simulation_run_id: "browser_wedge_test",
              sequence: 2, kind: "ENTRY_SIGNAL", time_ms: Date.UTC(2026, 9, 1, 12, 40),
              side: "LONG", price: 40100, stop: 39900, take: 40500 },
            { source: "SIMULATION", simulation_run_id: "browser_wedge_test",
              sequence: 3, kind: "ENTRY_FILLED", time_ms: Date.UTC(2026, 9, 1, 12, 41),
              side: "LONG", price: 40100,
              trade_id: "SIMULATION:browser_wedge_test:entry1" },
            { source: "SIMULATION", simulation_run_id: "browser_wedge_test",
              sequence: 4, kind: "EXIT_FILLED", time_ms: Date.UTC(2026, 9, 1, 12, 42),
              side: "LONG", price: 40500, reason: "TAKE",
              trade_id: "SIMULATION:browser_wedge_test:entry1" },
            { source: "SIMULATION", simulation_run_id: "browser_wedge_test",
              sequence: 5, kind: "CANDLE_CLOSED", time_ms: Date.UTC(2026, 9, 1, 12, 45),
              candle: { start_ms: Date.UTC(2026, 9, 1, 12, 40),
                end_ms: Date.UTC(2026, 9, 1, 12, 45),
                open: 40100, high: 40600, low: 40000, close: 40500, volume: 40 } },
          ],
        },
        scenario_type: "ORIGINAL_WEDGE_SCANNER_ROBOT_LOCAL_OHLC_SIMULATION",
        risk_terms_status: "EXPLICIT_RESEARCH_ASSUMPTIONS_NOT_EXCHANGE_VERIFIED",
        source_id: "BYBIT_PUBLIC_TRADES_RANGE_BROWSER_TEST_ONLY",
        requested_minutes: 1008, scanner_wedge_observations: 1,
        robot_retests_in_period: 1, submitted_protected_limits: 1,
        virtual_fills: 2, stop_exits: 0, take_exits: 1,
        realized_net_pnl: "3.71", unrealized_pnl: "0", total_net_pnl: "3.71",
        total_fees: "0.29", return_percent: "0.371", max_drawdown_percent: "0.1",
    };
    const { replay, ...report } = fixture;
    const frames = [
      { type: "start", simulation_run_id: fixture.simulation_run_id,
        symbol: fixture.symbol, start_utc: "2026-10-01T12:34",
        end_utc_inclusive: "2026-10-02T05:21" },
      { type: "events", events: replay.events.slice(0, 1) },
      { type: "events", events: replay.events.slice(1) },
      { type: "complete", report, source_id: fixture.source_id,
        event_count: replay.events.length },
    ];
    await route.fulfill({
      status: 200, contentType: "application/x-ndjson; charset=utf-8",
      body: frames.map(frame => JSON.stringify(frame)).join("\n") + "\n",
    });
  });
  await page.reload({ waitUntil: "networkidle" });
  const readySetup = page.getByRole("region", { name: "Настройка стратегий и периода" });
  await readySetup.getByRole("button", { name: "Только клинья" }).click();
  await readySetup.getByLabel("Начало прогона UTC").fill("2026-10-01T12:34");
  await readySetup.getByLabel("Конец прогона UTC").fill("2026-10-02T05:21");
  await readySetup.getByLabel("Виртуальный депозит").fill("1000");
  const appliedPlay = page.getByRole("button", { name: "Пуск", exact: true });
  assert.equal(await appliedPlay.isDisabled(), true, "no ticker/date applied after reload");
  await readySetup.getByRole("button", { name: "Применить" }).click();
  assert.equal(await appliedPlay.isDisabled(), false);
  assert.equal(posted.length, 0, "Apply prepares data without running virtual strategy");
  assert.match(await page.locator(".replay-meta").innerText(), /BTCUSDT.*2026-10-01T12:34/);
  assert.equal(await page.locator(".replay-meta").innerText().then(x => x.includes("Прогон / рынок")), false);
  assert.equal(await page.locator(".replay-chart canvas").count(), 0,
    "old synthetic chart must not be displayed after Apply");
  assert.equal(await page.locator(".replay-chart-pending").count(), 1);
  await appliedPlay.click(); // The one and only command to start the run.
  assert.equal(await page.getByRole("status", { name: "Ожидание нового графика" }).count(), 0,
    "removed pre-run explanation must remain absent during playback");
  assert.equal(await readySetup.getByRole("status", { name: "Результаты виртуального прогона" }).count(), 0,
    "future PnL must not be shown before the playhead reaches the last candle");
  await page.waitForFunction(() => {
    const meta = document.querySelector(".replay-meta");
    return meta && meta.textContent.includes("BTCUSDT") &&
      !meta.textContent.includes("SYNTHETIC_DEMO") &&
      document.querySelector(".replay-chart canvas");
  });
  await page.waitForFunction(() =>
    document.querySelector('[role="progressbar"]')?.getAttribute("aria-valuenow") === "100");
  await readySetup.getByRole("status", { name: "Результаты виртуального прогона" }).waitFor();
  assert.match(await readySetup.innerText(), /3\.71 USDT/);
  assert.equal(await page.locator(".replay-chart-panel").count(), 1);
  assert.ok((await page.locator(".replay-meta").innerText()).includes("BTCUSDT"));
  await page.getByRole("button", { name: "Пример", exact: true }).click();
  assert.match(await page.locator(".replay-meta").innerText(), /Синтетический пример/);
  assert.equal(await page.locator(".replay-meta").innerText().then(x => x.includes("SYNTHETIC_DEMO")), false);
  assert.equal(posted.length, 1);
  assert.equal(posted[0].method, "POST");
  assert.equal(posted[0].header, "wedge");
  assert.match(posted[0].url, /\/local-replay\/simulation\/wedge-stream$/);
  assert.deepEqual(posted[0].body, {
    symbol: "BTCUSDT", start_utc: "2026-10-01T12:34",
    end_utc_inclusive: "2026-10-02T05:21",
    selected_strategies: ["WEDGE_RISING", "WEDGE_FALLING"],
    initial_balance: "1000",
  });
  await readySetup.getByRole("checkbox", { name: "Все стратегии" }).check();
  await readySetup.getByRole("button", { name: "Применить" }).click();
  assert.match(await readySetup.innerText(), /Пока доступны только/);
  assert.equal(posted.length, 1, "unsupported strategies never cause a backend POST");
  assert.equal(requests.filter(url => url.includes("/api/") || url.includes("/v5/")).length, 0);

  // The entire replay control surface belongs beside the M5/H1 switch,
  // never in the file-import row above the chart.
  const controlBar = page.getByRole("group", { name: "Таймфрейм графика" });
  assert.deepEqual(await controlBar.locator(":scope > button").allTextContents(),
    ["H1", "M5", "M1", "15S"],
    "approved owner timeframe order must not regress");
  const playbackBar = controlBar.getByRole("group", { name: "Управление воспроизведением" });
  const actualOrder = await playbackBar.locator("button.replay-player-button").evaluateAll(
    buttons => buttons.map(button => button.getAttribute("aria-label")),
  );
  assert.deepEqual(actualOrder, ["В начало", "Пуск", "Шаг назад", "Шаг вперёд"],
    "approved player order must be stable");
  for (const [caption, symbol] of [["В начало", "beginning"], ["Пуск", "play"],
      ["Шаг назад", "backward"], ["Шаг вперёд", "forward"]]) {
    const button = playbackBar.getByRole("button", { name: caption, exact: true });
    assert.equal(await button.count(), 1);
    assert.equal((await button.innerText()).trim(), "");
    assert.equal(await button.locator('svg[data-player-icon="' + symbol + '"]').count(), 1);
  }
  assert.equal(await playbackBar.locator(".replay-rate input[type=range]").count(), 1);
  assert.equal(await playbackBar.locator(".replay-seek").count(), 1,
    "seek must live in icon player row");
  assert.equal(await page.locator(".replay-shell > .replay-seek").count(), 0,
    "separate seek above chart must stay removed");
  assert.equal(await playbackBar.locator(".replay-seek").evaluate(el =>
    el.previousElementSibling?.matches(".replay-player-button") &&
    el.nextElementSibling?.matches(".replay-rate")), true,
    "player order: icons → seek → speed");
  assert.equal(await page.locator(".replay-events").count(), 1,
    "owner requested a read-only causal events journal on the right");
  assert.equal(await page.getByRole("heading", { name: "Журнал событий" }).count(), 1);
  assert.equal(await page.getByRole("group", { name: "Таймфрейм графика" })
    .getByText("M1").isDisabled(), true);
  assert.equal(await page.getByRole("group", { name: "Таймфрейм графика" })
    .getByText("15S").isDisabled(), true);
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
  const scrub = playbackBar.getByRole("slider", { name: "Перемотка воспроизведения" });
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
  const completedPlay = page.getByRole("button", { name: "Прогон завершён" });
  assert.equal(await completedPlay.count(), 1);
  assert.equal(await completedPlay.isDisabled(), true,
    "completed playback cannot restart without returning to the beginning");
  await page.getByRole("button", { name: "В начало" }).click();
  assert.equal(await page.getByRole("button", { name: "Пуск", exact: true }).isDisabled(), false);
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
  let publicMarketAttempts = 0;
  let icntHistoryRequests = 0;
  await page.route("**/local-replay/history?*", async (route) => {
    const query = new URL(route.request().url()).searchParams;
    // The L2 import requests PUBLIC M5 prehistory as a chart-only layer.
    // Keep the original Wedge transport fixture separate: no detector options,
    // no live network, and never fabricate execution receipts from these bars.
    if (query.get("symbol") === "ICNTUSDT") {
      icntHistoryRequests++;
      assert.equal(query.has("strategies"), false);
      const first = Date.UTC(2026, 10, 10, 8, 0);
      const events = Array.from({ length: icntHistoryRequests === 1 ? 312 : 325 }, (_, i) => {
        const start_ms = first - 86_400_000 + i * 300_000;
        return {
          source: "SIMULATION", simulation_run_id: "browser_public_context",
          sequence: i + 1, kind: "CANDLE_CLOSED",
          time_ms: start_ms + 300_000,
          candle: {
            start_ms, end_ms: start_ms + 300_000,
            open: 100, high: 101, low: 99, close: 100, volume: 100,
          },
        };
      });
      await route.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify({
          source: "SIMULATION", simulation_run_id: "browser_public_context",
          mode: "MARKET_ONLY", market_data_source: "BYBIT_PUBLIC_KLINE",
          symbol: "ICNTUSDT", timeframe: "5m", events,
        }),
      });
      return;
    }
    publicMarketAttempts++;
    const requested = new URL(route.request().url()).searchParams.get("strategies")?.split(",") ?? [];
    assert.ok(requested.includes("WEDGE_FALLING") && requested.includes("WEDGE_RISING"),
      "the checked native Wedge detectors must reach loopback");
    const observed = requested.includes("IKIGAI_BOX") ? [{
      strategy: "IKIGAI_BOX", timeframe: "5m", pattern: "Ikigai Box",
      signal_id: "5m:LONG:" + (t + 3*300000) + ":" + (t + 7*300000),
      available_at_ms: t + 33*300000, source_candle_start_ms: t + 32*300000,
      close_price: 101, status: "CONFIRMED_STRUCTURE_ONLY",
      reason: "No Robot Box order admission or risk authorization",
      side: "LONG", box_start_ms: t + 8*300000,
      box_end_ms: t + 11*300000, box_low: 98, box_high: 102,
    }] : [];
    await route.fulfill(publicMarketAttempts === 1 ? {
      status: 502, contentType: "text/plain",
      body: "Public Bybit history unavailable; nothing was simulated",
    } : {
      status: 200, contentType: "application/json",
      body: JSON.stringify({
        ...history,
        scanner_research: {
          scope: "PUBLIC_M5_OBSERVATIONS_NO_ROBOT_EXECUTION",
          detectors: requested,
          configuration: "RESEARCH_HUNTER_SCORE50_NATIVE_WEDGE_AND_BOX",
        },
        scanner_observations: observed,
      }),
    });
  });
  const bounds = page.getByRole("region", { name: "Настройка стратегий и периода" });
  // Prior rejection test selected all unsupported strategies: restore a runnable
  // selection before applying a new market-only public-history interval.
  await bounds.getByRole("button", { name: "Только клинья" }).click();
  await bounds.getByRole("textbox", { name: "Координаты прогона" })
    .fill("BTCUSDT | 2026-10-01T00:00 | 2026-10-01T23:59");
  await bounds.getByRole("button", { name: "Применить" }).click();
  // The actual local Python server uses text/plain for HTTP 502 failures.
  // Show the true failed boundary instead of a misleading JSON.parse error,
  // without silently replacing the selected ticker/history by demo candles.
  await bounds.getByRole("button", { name: "Подгрузить период с Bybit" }).click();
  const marketError = page.getByRole("alert").filter({ hasText: "Публичный Bybit M5 недоступен (HTTP 502)" });
  await marketError.waitFor();
  assert.match(await marketError.innerText(), /архив M1 и профиль риска/);
  assert.equal(await page.locator(".replay-chart-shell").count(), 0,
    "failed public market download cannot resurrect old market candles");
  await bounds.getByRole("checkbox", { name: "Ikigai Box" }).check();
  await bounds.getByRole("button", { name: "Подгрузить период с Bybit" }).click();
  await page.getByText("РЕАЛЬНЫЕ СВЕЧИ BYBIT", { exact: false }).waitFor();
  assert.equal(publicMarketAttempts, 2);
  const marketSource = await page.locator(".replay-meta").innerText();
  assert.match(marketSource, /Bybit · публичные свечи · без сделок/,
    "public market-only source must be visible in the retained Source card");
  assert.doesNotMatch(marketSource, /SYNTHETIC_DEMO|Прогон \/ рынок/,
    "deleted synthetic run card must not be resurrected");
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
  const overlay = page.locator(".replay-execution-overlay");
  // Owner regression: "Only wedges" must NOT draw the unrelated H1/M5
  // geometry just because this is a public market-only chart. The Wedge
  // Scanner was NOT invoked by this public Bybit M5 GET.
  const strategyNote = page.getByRole("status", { name: "Статус выбранных стратегий" });
  assert.match(await strategyNote.innerText(), /Трендовые H1\/M5 выключены/);
  assert.match(await strategyNote.innerText(), /Оригинальные локальные детекторы M5 проверены/);
  assert.match(await strategyNote.innerText(), /1 Ikigai Box/);
  assert.match(await page.getByRole("status", { name: "Результат Scanner M5" }).innerText(),
    /1 из 1/);
  await page.waitForFunction(() =>
    document.querySelector(".replay-execution-overlay")?.dataset.visibleScannerObservations === "1");
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-fills"), "0");
  await page.getByRole("button", { name: "В начало" }).click();
  await page.waitForFunction(() =>
    document.querySelector(".replay-execution-overlay")?.dataset.visibleScannerObservations === "0");
  await page.getByRole("button", { name: "Пуск", exact: true }).click();
  await page.waitForFunction(() =>
    document.querySelector(".replay-execution-overlay")?.dataset.visibleScannerObservations === "1");
  // A detection at the 33rd close precedes the end of the 40-bar replay.
  // Continue to the final CLOSED M5 before verifying 100% playback.
  await page.waitForFunction(() =>
    document.querySelector('[role="progressbar"]')?.getAttribute("aria-valuenow") === "100");
  await page.waitForFunction(() =>
    document.querySelector(".replay-execution-overlay")?.dataset.visibleGeometry === "0");
  assert.equal(await overlay.getAttribute("data-painted-geometry"), "0");
  assert.equal(await overlay.getAttribute("data-visible-priors"), "0");
  assert.equal(await overlay.getAttribute("data-visible-early-geometry"), "0");

  // Explicitly enabling H1/M5 reveals ONLY its research overlays, without
  // modifying candles, Wedge choices, the virtual account, or creating fills.
  await bounds.getByRole("checkbox", { name: "Трендовые H1/M5" }).check();
  await page.waitForFunction(() =>
    document.querySelector(".replay-execution-overlay")?.dataset.visibleGeometry === "3");
  assert.match(await strategyNote.innerText(), /Трендовые H1\/M5 выбраны/);
  assert.equal(await overlay.getAttribute("data-visible-fills"), "0");
  assert.equal(await overlay.getAttribute("data-painted-geometry"), "3");
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
  // Disable the strategy again: every automated H1/M5 line, prior and
  // diagnostic disappears immediately. Manual drawing/PAPER facts are not
  // secretly removed and no Scanner or new market fetch is triggered.
  await bounds.getByRole("checkbox", { name: "Трендовые H1/M5" }).uncheck();
  await page.waitForFunction(() =>
    document.querySelector(".replay-execution-overlay")?.dataset.visibleGeometry === "0");
  assert.equal(await overlay.getAttribute("data-painted-geometry"), "0");
  assert.equal(await overlay.getAttribute("data-visible-priors"), "0");
  assert.equal(await overlay.getAttribute("data-painted-priors"), "0");
  assert.equal(await overlay.getAttribute("data-visible-early-geometry"), "0");
  assert.equal(await overlay.getAttribute("data-visible-fills"), "0");
  assert.equal(await bounds.getByRole("checkbox", { name: "Восходящий клин" }).isChecked(), true);
  assert.equal(await bounds.getByRole("checkbox", { name: "Нисходящий клин" }).isChecked(), true);

  // Exported PAPER facts are marked as HOLLOW rings at their original prices,
  // separate from virtual triangles. No extra /api or private exchange call.
  const episodeFacts = {
    ok: true, schema: "BYBITSCANNER_CLOSED_EPISODE_FACTS_V1",
    namespace: "PAPER_READ_ONLY", source: "PAPER_EXECUTIONS_ATTRIBUTED",
    source_revision: 3, account_id: "paper", owner: "ROBOT", cohort: "ROBOT",
    trade_episode_id: "te_" + "a".repeat(24), symbol: "BTCUSDT", side: "LONG",
    opened_at_ms: t + 2 * 300000 + 2000,
    closed_at_ms: t + 7 * 300000 + 2000,
    realized_price_pnl_usdt: "-0.9", known_execution_fees_usdt: "0.1",
    pnl_usdt: "-1.0", pnl_basis: "REALIZED_PRICE_MINUS_EXECUTION_FEES",
    replay_evidence: "EXECUTION_FACTS_ONLY_NO_DECISIONS_OR_CANDLES",
    setup_context: {
      status: "EXACT_D2_LINK", source: "TRADING_DIARY_D2",
      consistency: "INDEPENDENT_READ_SNAPSHOT_NOT_ATOMIC_WITH_PAPER",
      geometry_status: "NOT_EXPORTED",
      decision_scope: "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG",
      setup: {
        setup_instance_id: "setup-1", setup_id: "candidate-42", symbol: "BTCUSDT",
        direction: "LONG", timeframe: "5m", pattern: "Falling Wedge",
        strategy_version: "v1", entry_mode: "breakout_retest",
        origin: "ROBOT", created_at_ms: t + 300000, has_feature_snapshot_ref: true,
      },
      order_plan_id: "plan-1", linked_at_ms: t + 330000,
      decisions: [
        { decision_event_id: "strategy-1", kind: "STRATEGY", previous_state: null,
          next_state: "APPROVED", reason_code: "STRATEGY_OK", controller: "ROBOT",
          origin: "ROBOT", occurred_at_ms: t + 301000 },
        { decision_event_id: "risk-1", kind: "RISK", previous_state: "APPROVED",
          next_state: "APPROVED", reason_code: "RISK_OK", controller: "ROBOT",
          origin: "ROBOT", occurred_at_ms: t + 302000 },
      ],
    },
    execution_allocations: [
      { execution_id: "exec-1", order_id: "order-1", order_side: "Buy",
        execution_price: "100.12345678", allocated_quantity: "2", allocated_fee: "0.05",
        occurred_at_ms: t + 2 * 300000 + 2000, allocation_role: "OPEN", controller: "ROBOT" },
      { execution_id: "exec-2", order_id: "order-2", order_side: "Sell",
        execution_price: "99.5", allocated_quantity: "2", allocated_fee: "0.05",
        occurred_at_ms: t + 7 * 300000 + 2000, allocation_role: "CLOSE", controller: "ROBOT" },
    ],
  };
  episodeFacts.setup_context.geometry_status = "ORIGINAL_ARCHIVE_HASH_VERIFIED";
  episodeFacts.setup_context.original_geometry = {
    schema: "BYBITSCANNER_ARCHIVED_SIGNAL_GEOMETRY_V1",
    source: "ORIGINAL_TELEGRAM_SIGNAL_ARCHIVE",
    linkage_basis: "D2_SETUP_ID_EQUALS_ARCHIVED_CANDIDATE_ID",
    integrity: "LOCAL_ARCHIVE_HASH_ONLY_NOT_CRYPTOGRAPHIC_PROOF",
    signal_id: "candidate-42", sent_at_ms: t + 350000, sha256: "a".repeat(64),
    snapshot: {
      schema_version: 1, signal_id: "candidate-42", symbol: "BTCUSDT", timeframe: "5m",
      bars: [
        { open_time_ms: t, open: 100, high: 102, low: 98, close: 101 },
        { open_time_ms: t + 300000, open: 101, high: 103, low: 100, close: 102 },
      ],
      boundaries: [{ boundary_id: "lower", kind: "segment", anchors: [
        { bar_open_time_ms: t, price: 99 },
        { bar_open_time_ms: t + 300000, price: 100 },
      ] }],
    },
  };
  await page.getByLabel("Импорт JSON сделки PAPER").setInputFiles({
    name: "episode-facts.json", mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(episodeFacts)),
  });
  const factNote = page.getByRole("status", { name: "PAPER факты сделки" });
  await factNote.waitFor();
  const passport = page.getByRole("region", { name: "Паспорт PAPER-сделки" });
  assert.match(await passport.innerText(), /Паттерн исходного сетапа[\s\S]*Falling Wedge/);
  assert.match(await passport.innerText(), /5m[\s\S]*v1[\s\S]*breakout_retest/);
  assert.match(await passport.innerText(), /EXACT_D2_LINK/);
  assert.match(await passport.innerText(), /PnL -1.0 USDT/);
  assert.match(await passport.innerText(), /не полный журнал решений Robot/);
  assert.match(await factNote.innerText(), /Кружки на закрытых свечах/);
  assert.match(await factNote.innerText(), /JSON без криптографической подписи/);
  assert.match(await factNote.innerText(), /Falling Wedge · 5m · версия v1/);
  assert.match(await factNote.innerText(), /архивная исходная геометрия/);
  const d2Journal = page.getByRole("region", { name: "Наблюдения PAPER D2" });
  assert.match(await d2Journal.innerText(), /STRATEGY_OK/);
  assert.match(await d2Journal.innerText(), /RISK_OK/);
  assert.match(await d2Journal.innerText(), /не полный журнал Robot/);
  const journalZone = page.getByRole("group", {name:"Часовой пояс журнала"});
  const d2Clock = d2Journal.locator("time").first();
  assert.match(await d2Clock.innerText(), /\d{2}:\d{2}:\d{2} \(000\) МСК/);
  await journalZone.getByRole("button",{name:"UTC"}).click();
  assert.match(await d2Clock.innerText(), /\d{2}:\d{2}:\d{2} \(000\) UTC/);
  await journalZone.getByRole("button",{name:"МСК"}).click();
  assert.match(await d2Clock.innerText(), /\d{2}:\d{2}:\d{2} \(000\) МСК/);
  await page.waitForFunction(() =>
    document.querySelector(".replay-execution-overlay")?.dataset.visiblePaperFills === "2");
  await page.waitForFunction(() =>
    document.querySelector(".replay-execution-overlay")?.dataset.visibleOriginalGeometry === "1");
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-fills"), "0",
    "a PAPER imported observation never becomes a SIMULATION fill");
  await page.getByRole("button", { name: "В начало" }).click();
  await page.waitForFunction(() =>
    document.querySelector(".replay-execution-overlay")?.dataset.visiblePaperFills === "0");
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-original-geometry"), "0");
  await page.waitForFunction(() => !document.querySelector('[aria-label="Наблюдения PAPER D2"]'));
  assert.doesNotMatch(await factNote.innerText(), /Falling Wedge/);
  assert.match(await passport.innerText(), /Falling Wedge/,
    "retrospective passport remains available at cursor zero; chart signals do not");
  await page.getByRole("button", { name: "Пуск", exact: true }).click();
  await page.waitForFunction(() =>
    document.querySelector(".replay-execution-overlay")?.dataset.visiblePaperFills === "2");
  await page.waitForFunction(() =>
    document.querySelector(".replay-execution-overlay")?.dataset.visibleOriginalGeometry === "1");
  assert.match(await d2Journal.innerText(), /RISK_OK/);
  await page.getByRole("button", { name: "Пауза", exact: true }).click();
  await page.getByRole("button", { name: "Убрать факты PAPER" }).click();
  await passport.waitFor({state:"detached"});
  await page.waitForFunction(() =>
    document.querySelector(".replay-execution-overlay")?.dataset.visiblePaperFills === "0");
  // An unrelated episode or absent D2 evidence cannot inherit prior pattern.
  const noLinkFacts = {
    ...episodeFacts,
    trade_episode_id: "te_" + "b".repeat(24),
    setup_context: {
      status:"NO_EXACT_EPISODE_LINK", source:"TRADING_DIARY_D2",
      geometry_status:"NOT_EXPORTED",
      decision_scope:"D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG",
    },
  };
  await page.getByLabel("Импорт JSON сделки PAPER").setInputFiles({
    name:"episode-no-link.json",mimeType:"application/json",
    buffer:Buffer.from(JSON.stringify(noLinkFacts)),
  });
  await passport.waitFor();
  assert.match(await passport.innerText(),/Паттерн не подтверждён/);
  assert.match(await passport.innerText(),/NO_EXACT_EPISODE_LINK/);
  assert.doesNotMatch(await passport.innerText(),/Falling Wedge/);
  await page.getByRole("button", {name:"Убрать факты PAPER"}).click();
  await passport.waitFor({state:"detached"});
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-original-geometry"), "0");

  // Independent browser proof: import the same *nested* receipt structure the
  // owner already has, without trading, re-running L2 or external requests.
  const l2Start = Date.UTC(2026, 10, 10, 8, 0);
  const l2RunId = "browser_l2_receipt";
  const l2Directions = ["LONG", "LONG", "SHORT", "LONG"];
  const l2Exits = ["100", "101", "101", "101"];
  const l2Reasons = ["STOP", "TAKE", "STOP", "TAKE"];
  const l2Net = ["-1.2", "8.8", "-11.2", "8.8"];
  const l2Episodes = l2Directions.map((direction, i) => ({
    order_id: "IMPULSE_" + (l2Start + i * 10000), direction,
    entry_ms: l2Start + (i === 3 ? 300000 : i * 10000) + 1000,
    exit_ms: l2Start + (i === 3 ? 300000 : i * 10000) + 2000,
    entry_price: "100", exit_price: l2Exits[i],
    entry_fee: "0.6", exit_fee: "0.6", quantity: "10",
    partial_quantity: null, exit_reason: l2Reasons[i],
    net_pnl_usdt: l2Net[i],
  }));
  const l2Events = [];
  for (const row of l2Episodes) {
    const trade_id = "SIMULATION:" + l2RunId + ":" + row.order_id;
    for (const kind of ["ENTRY_FILLED", "EXIT_FILLED"]) {
      l2Events.push({
        source: "SIMULATION", simulation_run_id: l2RunId,
        sequence: l2Events.length + 1, kind, trade_id,
        side: row.direction,
        time_ms: kind === "ENTRY_FILLED" ? row.entry_ms : row.exit_ms,
        price: Number(kind === "ENTRY_FILLED" ? row.entry_price : row.exit_price),
        ...(kind === "EXIT_FILLED" ? {
          reason: row.exit_reason, net_usdt: row.net_pnl_usdt,
          pnl_percent: String(Number(row.net_pnl_usdt) / 10),
        } : {}),
      });
    }
  }
  l2Events.push({
    source: "SIMULATION", simulation_run_id: l2RunId,
    sequence: l2Events.length + 1, kind: "CANDLE_CLOSED",
    time_ms: l2Start + 300000,
    candle: { start_ms: l2Start, end_ms: l2Start + 300000,
      open: 100, high: 103, low: 99, close: 101, volume: 1000 },
  });
  // The fourth original virtual trade occurs after the final SOURCE M5.
  // The public 08:05–08:10 close is required before revealing it.
  l2Events.sort((a, b) => a.time_ms - b.time_ms);
  l2Events.forEach((e, i) => { e.sequence = i + 1; });
  const originalReceipt = {
    state: "VIRTUAL_L2_PROBE_CONDITIONAL",
    scenario: "ONE_BOUNDED_LOCAL_SIMULATION_NOT_REAL_BYBIT_EXECUTIONS",
    code_sha: "389e175c542d8319d245b70357d5e27c50e6f8e6",
    l2_sha256: "79b032aafc5c97ea3790947cdd72347af83c88b9a1360aa219cdef5f5cbe54df",
    trade_gzip_sha256: "47f3d3ea153374fe759adc81d2b340f5557d0fef84e90d28862d1a1239b0718a",
    result: {
      symbol: "ICNTUSDT",
      execution_model: "SIMULATION_HISTORICAL_TAKER_L2_EVENT_TIME_NOT_REAL_BYBIT_FILLS",
      l2_source_sha256: "79b032aafc5c97ea3790947cdd72347af83c88b9a1360aa219cdef5f5cbe54df",
      final_position_quantity: "0", virtual_fills: 8, realized_net_pnl: "5.2",
      l2_episodes: l2Episodes,
      replay: {
        source: "SIMULATION", simulation_run_id: l2RunId,
        mode: "STRATEGY", demo: false, symbol: "ICNTUSDT", timeframe: "5m",
        market_data_source: "PINNED_BYBIT_PUBLIC_TRADES_PLUS_L2_EVENT_TIME_SIMULATION",
        execution_clock: "ORIGINAL_EVENT_TIME_NOT_OHLC_M1",
        execution_certainty: "CONDITIONAL_L2_NOT_REAL_EXCHANGE_FILLS",
        partial_and_be_markers: "EVENTS_ONLY_CONDITIONAL",
        events: l2Events,
      },
    },
  };
  assert.equal(await page.locator(".replay-controls").count(), 0,
    "JSON import controls must move away from former strip");
  const importedActions = page.getByRole("group", { name: "Импорт и отчёты прогона" });
  assert.equal(await importedActions.getByText("Загрузить JSON прогона").count(), 1);
  assert.equal(await importedActions.getByText("Импорт JSON сделки PAPER").count(), 1);
  await page.getByLabel("Загрузить JSON прогона").setInputFiles({
    name: "original-l2-result.json", mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(originalReceipt)),
  });
  await page.getByRole("status").filter({ hasText: "SIMULATION L2" }).waitFor();
  const importedCoordinates = page.getByRole("textbox", { name: "Координаты прогона" });
  await page.waitForFunction(() =>
    document.querySelector('input[aria-label="Координаты прогона"]')?.value ===
      "ICNTUSDT | 2026-11-10T08:00 | 2026-11-10T08:05");
  assert.equal(await page.getByLabel("Начало прогона UTC").inputValue(), "2026-11-10T08:00");
  assert.equal(await page.getByLabel("Конец прогона UTC").inputValue(), "2026-11-10T08:05");
  await page.getByRole("status").filter({ hasText: "Публичная M5: 288 до и 12 после" }).waitFor();
  assert.equal(await page.locator(".replay-chart-shell").getAttribute("data-displayed-candles"), "288",
    "before the first L2 close, only verified closed historical M5 may be drawn");
  assert.match(await page.getByRole("group", { name: "Индикатор ADX DMI" }).innerText(),
    /ADX 0\.0/,
    "L2 public prehistory must restore closed-M5 Wilder ADX even before source replay");
  await page.getByRole("button", { name: "M5", exact: true }).click();
  await page.getByRole("button", { name: "Шаг вперёд" }).click();
  await page.waitForFunction(() =>
    document.querySelector(".replay-execution-overlay")?.dataset.visibleFills === "6");
  assert.match(await page.locator(".replay-meta").innerText(), /1 \/ 3 \/ 3/,
    "last source M5 must not reveal the fourth post-boundary trade");
  await page.getByRole("button", { name: "Шаг вперёд" }).click();
  await page.waitForFunction(() =>
    document.querySelector(".replay-execution-overlay")?.dataset.visibleFills === "8");
  assert.match(await page.locator(".replay-meta").innerText(), /2 \/ 4 \/ 4/);
  assert.equal((await page.locator(".replay-chart-symbol").innerText()).trim(), "ICNT");
  assert.match(await page.getByRole("status").filter({ hasText: "SIMULATION L2" }).innerText(),
    /не доказаны/);
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-paper-fills"), "0");
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-fills"), "8");
  assert.equal(await page.locator(".replay-chart-shell").getAttribute("data-displayed-candles"), "290",
    "public M5 prehistory must not overwrite the original L2 execution candle");
  await page.screenshot({ path: join(screenshotDir, "machine-time-l2-replay.png"), fullPage: true });
  console.log("LOCAL_L2_REPLAY_BROWSER_OK (Chromium, original nested receipt import, 8 event-time marks, no PAPER)");
  // The selected source period is already covered in this local viewer.
  // Clicking Bybit must NOT repeat a public network request.
  const beforeDuplicate = icntHistoryRequests;
  await page.getByRole("button", { name: "Подгрузить период с Bybit" }).click();
  await page.getByRole("status", { name: "Покрытие выбранного периода" })
    .filter({ hasText: "Данные уже загружены локально" }).waitFor();
  assert.equal(icntHistoryRequests, beforeDuplicate,
    "already covered historical M5 must never be downloaded twice");

  // Owner UX: imported coordinates stay editable. Applying the selected
  // interval MUST NOT clear the original L2 receipts or start Robot.
  const selectedWindow = page.getByRole("textbox", { name: "Координаты прогона" });
  await page.getByRole("button", { name: "Добавить 1 час" }).click();
  assert.equal(await page.getByLabel("Конец прогона UTC").inputValue(), "2026-11-10T09:05");
  assert.match(await selectedWindow.inputValue(), /ICNTUSDT \| 2026-11-10T08:00 \| 2026-11-10T09:05/);
  await page.getByRole("button", { name: "Применить", exact: true }).click();
  assert.match(await page.locator(".replay-meta").innerText(), /4 \/ 4/,
    "Apply on imported source must not turn original L2 into a new simulation");
  // The initial public reply already contained the next hour, although
  // only 12 post-window bars were drawn. Retain those 5m for free.
  const cachedRequests = icntHistoryRequests;
  await page.getByRole("button", { name: "Подгрузить период с Bybit" }).click();
  await page.getByRole("status", { name: "Покрытие выбранного периода" })
    .filter({ hasText: "Данные уже загружены локально" }).waitFor();
  assert.equal(icntHistoryRequests, cachedRequests,
    "extended source window must reuse the full public reply, not re-fetch it");
  await page.getByRole("button", { name: "Добавить 1 час" }).click();
  assert.equal(await page.getByLabel("Конец прогона UTC").inputValue(), "2026-11-10T10:05");
  const beforeGapClick = icntHistoryRequests;
  await page.getByRole("button", { name: "Пуск", exact: true }).click();
  await page.getByRole("alert").filter({
    hasText: "Данные для выбранного периода не подгружены",
  }).waitFor();
  assert.equal(icntHistoryRequests, beforeGapClick,
    "Play warning never downloads without explicit Bybit action");
  assert.match(await page.locator(".replay-meta").innerText(), /4 \/ 4/,
    "blocked Play must preserve the original four trades");
  await page.getByRole("button", { name: "Подгрузить период с Bybit" }).click();
  await page.getByRole("status").filter({ hasText: "Исторические taker-сделки/L2-стакан" }).waitFor();
  assert.equal(icntHistoryRequests, beforeGapClick+1,
    "only a truly missing M5 day receives a new Bybit request");
  assert.match(await page.locator(".replay-meta").innerText(), /original-l2-result\.json/,
    "public period extension must preserve the imported JSON source");


  // Owner's original SIMULATION L2 events remain unchanged when selecting
  // trade-derived M1 and 15S. Mocked prints are TEST ONLY; the actual local
  // server independently checks the selected gzip ZIP/raw archive.
  let fineUploads = 0;
  await page.route("**/local-replay/chart-trades?*", async route => {
    fineUploads++;
    const q = new URL(route.request().url()).searchParams;
    assert.equal(q.get("symbol"), "ICNTUSDT");
    assert.equal(q.get("filename"), "ICNTUSDT2026-11-10.csv.gz");
    assert.equal(route.request().method(), "POST");
    const first = Number(q.get("start_ms")), end = Number(q.get("end_ms"));
    assert.equal(first % 60_000, 0);
    assert.ok(end > first && end-first < 6*3_600_000);
    const s15 = Array.from({length:(end-first)/15_000}, (_,i) => ({
      start_ms:first+i*15_000,end_ms:first+(i+1)*15_000,
      open:100,high:101,low:99,close:100,volume:1,
    }));
    const m1 = Array.from({length:(end-first)/60_000}, (_,i) => ({
      start_ms:first+i*60_000,end_ms:first+(i+1)*60_000,
      open:100,high:101,low:99,close:100,volume:4,
    }));
    await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({
      source:"BYBIT_PUBLIC_TRADES_DERIVED_OHLC_LOCAL_ARCHIVE",
      symbol:"ICNTUSDT",start_ms:first,end_ms:end,
      raw_trade_sha256:"47f3d3ea153374fe759adc81d2b340f5557d0fef84e90d28862d1a1239b0718a",
      pinned_original_icnt:true,missing_m1:0,missing_15s:0,
      m1,s15,trades_scanned:10000,l2_executions_unchanged:true,
    })});
  });
  assert.equal(await page.getByRole("button",{name:"M1",exact:true}).isDisabled(),true);
  assert.equal(await page.getByRole("button",{name:"15S",exact:true}).isDisabled(),true);
  await page.getByLabel("Загрузить архив публичных сделок M1 15S").setInputFiles({
    name:"ICNTUSDT2026-11-10.csv.gz",mimeType:"application/octet-stream",
    buffer:Buffer.from("fake trade gzip - backend is mocked only in E2E"),
  });
  await page.getByRole("status",{name:"Статус M1 и 15S"})
    .filter({hasText:"Покрытие полное"}).waitFor();
  assert.equal(fineUploads,1);
  assert.equal(await page.locator(".replay-chart-shell").getAttribute("data-chart-timeframe"),"1m");
  assert.equal(await page.getByRole("button",{name:"15S",exact:true}).isDisabled(),false);
  const seek = page.getByRole("slider",{name:"Перемотка воспроизведения"});
  await seek.focus();
  await seek.press("End");
  const fineState = async () => page.evaluate(() => ({
    fills:document.querySelector(".replay-execution-overlay")?.dataset.visibleFills,
    timeframe:document.querySelector(".replay-chart-shell")?.dataset.chartTimeframe,
    bars:document.querySelector(".replay-chart-shell")?.dataset.displayedCandles,
    seek:document.querySelector(".replay-seek")?.value,
    seekMax:document.querySelector(".replay-seek")?.max,
    meta:document.querySelector(".replay-meta")?.textContent?.slice(0,350),
  }));
  await page.waitForTimeout(500);
  const visibleM1 = Number((await fineState()).fills);
  assert.ok(visibleM1 > 0 && visibleM1 <= 8,
    "M1 must paint original markers inside its current viewport; " +
    "off-screen fills remain in original 4/4 ledger: " + JSON.stringify(await fineState()));
  assert.match(await page.locator(".replay-meta").innerText(),/4 \/ 4/,
    "M1 displays all original L2 event-time fills, not re-simulated fills");
  await page.getByRole("button",{name:"15S",exact:true}).click();
  assert.equal(await page.locator(".replay-chart-shell").getAttribute("data-chart-timeframe"),"15s");
  await page.waitForTimeout(500);
  const visible15S = Number((await fineState()).fills);
  assert.ok(visible15S > 0 && visible15S <= 8,
    "15S must paint original markers inside its current viewport; " +
    "all 4/4 immutable receipts remain in the journal: " + JSON.stringify(await fineState()));
  assert.match(await page.locator(".replay-meta").innerText(),/4 \/ 4/,
    "15S displays the SAME frozen original L2 event-time entries and exits");
  assert.equal(fineUploads,1,"Switching M1 to 15S must not re-upload source trades");
  await page.getByRole("button",{name:"M5",exact:true}).click();
  assert.match(await page.locator(".replay-meta").innerText(),/4 \/ 4/,
    "M5 remains exact after switching to and from verified fine scales");
  console.log("LOCAL_FINE_TF_BROWSER_OK (M1/15s visual only, original 4/4 L2 immutable)");

  await page.mouse.move(620, 660); // Crosshair must not create DMI dots.
  await page.screenshot({ path: join(screenshotDir, "machine-time-browser.png"), fullPage: true });

  // The deliberate HTTP 502 fixture triggers exactly one browser
  // "Failed to load resource" console message. Permit ONLY that observed
  // response, never unrelated JS/runtime or additional network failures.
  const public502 = "Failed to load resource: the server responded with a status of 502 (Bad Gateway)";
  assert.equal(errors.filter(message => message === public502).length, 1,
    "exactly one intentional failed public-market request");
  assert.deepEqual(errors.filter(message => message !== public502), [],
    "Unexpected browser runtime errors: " + errors.join("; "));
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
    await copyFile(
      join(screenshotDir, "machine-time-l2-replay.png"),
      join(process.env.LOCAL_REPLAY_E2E_SCREENSHOTS, "machine-time-l2-replay.png"),
    ).catch(() => {});
  }
  await rm(screenshotDir, { recursive: true, force: true });
}

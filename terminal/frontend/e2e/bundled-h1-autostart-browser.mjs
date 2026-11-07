/** One-click owner acceptance: audited public archive is already loaded at launch.
 * This browser runs against the exact single-package Windows folder.
 */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { chromium } from "@playwright/test";

const serverPath = process.env.LOCAL_REPLAY_PACKAGED_SERVER;
assert.ok(serverPath, "packed local server path required");
const archive = JSON.parse(await readFile(join(dirname(serverPath), "real-h1-august.json"), "utf8"));
assert.equal(archive.symbol, "GRASSUSDT");
assert.equal(archive.mode, "MARKET_ONLY");
const server = spawn("python", [serverPath, "--no-browser"], {
  stdio: ["ignore", "pipe", "pipe"],
});
let browser, stderr = "";
server.stderr.on("data", data => { stderr += String(data); });

async function localUrl() {
  return await new Promise((resolve, reject) => {
    let output = "";
    const timeout = setTimeout(() => reject(new Error("Server timeout: " + stderr)), 15000);
    server.once("exit", code => {
      clearTimeout(timeout);
      reject(new Error("Server terminated " + code + ": " + stderr));
    });
    server.stdout.on("data", chunk => {
      output += String(chunk);
      const url = output.match(/http:\/\/127\.0\.0\.1:\d+\/replay\.html/);
      if (url) {
        clearTimeout(timeout);
        resolve(url[0]);
      }
    });
  });
}
try {
  browser = await chromium.launch({
    headless: true,
    ...(process.env.LOCAL_REPLAY_CHROME
      ? { executablePath: process.env.LOCAL_REPLAY_CHROME } : {}),
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 920 } });
  const errors = [], requests = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", msg => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("request", request => requests.push(request.url()));
  await page.goto(await localUrl(), { waitUntil: "networkidle" });
  await page.getByText("Проверенный публичный архив · GRASSUSDT", { exact: true }).waitFor();
  assert.equal(await page.getByRole("textbox", { name: "Инструмент" }).inputValue(), "GRASSUSDT");
  assert.equal(await page.locator('input[type="date"]').nth(0).inputValue(),
    new Date(archive.from_ms).toISOString().slice(0, 10));
  assert.equal(await page.locator('input[type="date"]').nth(1).inputValue(),
    new Date(archive.until_ms).toISOString().slice(0, 10));
  assert.match(await page.locator("body").innerText(), /2016/);
  assert.match(await page.locator("body").innerText(), /официального публичного архива/);
  assert.equal(await page.getByRole("progressbar").getAttribute("aria-valuenow"), "0");
  assert.equal(await page.locator(".replay-execution-overlay").getAttribute("data-visible-fills"), "0");
  assert.equal(await page.getByRole("group", { name: "Управление воспроизведением" }).count(), 1);
  assert.equal(await page.getByRole("group", { name: "Инструменты рисования" })
    .locator("svg.replay-tool-icon").count(), 13);
  // Manual owner choice must win over the one-time automatic load.
  await page.getByRole("button", { name: "Пример", exact: true }).click();
  assert.match(await page.locator("body").innerText(), /Синтетический пример/);
  await page.getByRole("button", { name: "Шаг вперёд ▶" }).click();
  assert.ok(Number(await page.getByRole("progressbar").getAttribute("aria-valuenow")) > 0);
  assert.deepEqual(errors, [], "browser errors or rejected bundled fetch");
  assert.ok(requests.every(uri => ["localhost", "127.0.0.1"].includes(new URL(uri).hostname)),
    "no remote requests from the standalone owner viewer");
  assert.ok(requests.every(uri => !new URL(uri).pathname.startsWith("/api")),
    "no private/trading route");
  console.log("BUNDLED_REAL_H1_AUTOSTART_OK (GRASSUSDT, provenance, no PAPER, manual override)");
} finally {
  if (browser) await browser.close();
  server.kill();
}

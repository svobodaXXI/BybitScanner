import test from "node:test";
import assert from "node:assert/strict";
import cloudflare from "../deploy/telegram_gateway/cloudflare_proxy_worker.mjs";

const env = {
  GATEWAY_SHARED_SECRET: "x".repeat(48),
  TELEGRAM_BOT_TOKEN: "test-token",
  TELEGRAM_CHAT_ID: "12345",
};
const request = (path, options = {}) =>
  new Request("https://bybitscanner-gateway.example" + path, options);
const authorization = "Bearer " + env.GATEWAY_SHARED_SECRET;

test("Cloudflare entrypoint serves only Gateway health, not Telegram readiness", async () => {
  const response = await cloudflare.fetch(request("/health"), {});
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.status, "up");
  assert.equal(body.delivery_verified, false);
});

test("Cloudflare entrypoint rejects poll without secret before network", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = () => { throw Error("upstream must not be called"); };
  try {
    const response = await cloudflare.fetch(request("/v1/get-updates", {
      method: "POST", headers: {"content-type": "application/json"}, body: "{}",
    }), env);
    assert.equal(response.status, 401);
  } finally { globalThis.fetch = originalFetch; }
});

test("Cloudflare entrypoint requires configured secrets before polling", async () => {
  const response = await cloudflare.fetch(request("/v1/get-updates", {
    method: "POST", headers: {"content-type": "application/json"}, body: "{}",
  }), {});
  assert.equal(response.status, 503);
});

test("authorized getUpdates is sent directly to Telegram, never Vercel", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push(String(url));
    assert.match(String(url), /^https:\/\/api\.telegram\.org\/bottest-token\/getUpdates\?/);
    assert.equal(options?.method, undefined); // Telegram getUpdates uses GET upstream.
    return new Response(JSON.stringify({ok: true, result: []}), {
      status: 200, headers: {"content-type": "application/json"},
    });
  };
  try {
    const response = await cloudflare.fetch(request("/v1/get-updates", {
      method: "POST",
      headers: {"content-type": "application/json", authorization},
      body: JSON.stringify({timeout: 0, allowed_updates: ["message", "callback_query"]}),
    }), env);
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), {ok: true, result: []});
    assert.equal(calls.length, 1);
  } finally { globalThis.fetch = originalFetch; }
});

test("authorized send uses fixed owner and Telegram directly", async () => {
  const originalFetch = globalThis.fetch;
  let count = 0;
  globalThis.fetch = async (url, options) => {
    count++;
    assert.equal(String(url), "https://api.telegram.org/bottest-token/sendMessage");
    assert.equal(JSON.parse(options.body).chat_id, env.TELEGRAM_CHAT_ID);
    return new Response(JSON.stringify({ok: true, result: {message_id: 12}}), {
      status: 200, headers: {"content-type": "application/json"},
    });
  };
  try {
    const response = await cloudflare.fetch(request("/v1/send", {
      method: "POST",
      headers: {"content-type": "application/json", authorization},
      body: JSON.stringify({event_id: "cf_direct_1234", text: "delivery test"}),
    }), env);
    assert.equal(response.status, 200);
    const result = await response.json();
    assert.equal(result.stage, "accepted_by_telegram_api");
    assert.equal(count, 1);
  } finally { globalThis.fetch = originalFetch; }
});

test("unlisted endpoint remains closed", async () => {
  const response = await cloudflare.fetch(request("/v1/trading", {method: "POST"}), env);
  assert.equal(response.status, 404);
});

import test from "node:test";
import assert from "node:assert/strict";
import worker from "../deploy/telegram_gateway/worker.mjs";

const env = {GATEWAY_SHARED_SECRET:"x".repeat(48),TELEGRAM_BOT_TOKEN:"dummy",TELEGRAM_CHAT_ID:"12345"};
const req = (path, options = {}) =>
  new Request("https://gateway.example" + path, options);

test("health does not claim Telegram delivery", async () => {
  const response = await worker.fetch(req("/health"), {});
  assert.equal(response.status, 200);
  assert.equal((await response.json()).delivery_verified, false);
});

test("send is forbidden without owner authorization", async () => {
  const response = await worker.fetch(req("/v1/send", {
    method:"POST", headers:{"content-type":"application/json"},
    body:JSON.stringify({event_id:"example_12345",text:"hello"})
  }), env);
  assert.equal(response.status, 401);
});

test("send rejects invalid payload before Telegram network", async () => {
  const response = await worker.fetch(req("/v1/send", {
    method:"POST", headers:{
      "content-type":"application/json",
      authorization:"Bearer "+"x".repeat(48)
    }, body:JSON.stringify({event_id:"bad",text:"hello"})
  }), env);
  assert.equal(response.status, 400);
});

test("polling requires authorization", async () => {
  const response = await worker.fetch(req("/v1/get-updates", {
    method:"POST",headers:{"content-type":"application/json"},
    body:"{}"
  }), env);
  assert.equal(response.status, 401);
});

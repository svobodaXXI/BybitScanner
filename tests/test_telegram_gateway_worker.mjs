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

test("photo-card uploads UTF-8 caption and inline keyboard atomically", async () => {
  const originalFetch = globalThis.fetch;
  const outgoing = [];
  globalThis.fetch = async (url, options) => {
    outgoing.push({url, options});
    assert.ok(url.endsWith("/sendPhoto"));
    const sent = options.body;
    assert.equal(sent.get("caption"), "🪞 MIRROR · ALCHUSDT · 5m");
    assert.equal(JSON.parse(sent.get("reply_markup")).inline_keyboard[0][0].text, "К сигналу");
    assert.equal(sent.get("chat_id"), env.TELEGRAM_CHAT_ID);
    assert.ok(sent.get("photo") instanceof Blob);
    return new Response(JSON.stringify({ok:true,result:{message_id:42725}}), {
      status:200,headers:{"content-type":"application/json"}
    });
  };
  try {
    const form = new FormData();
    form.set("caption", "🪞 MIRROR · ALCHUSDT · 5m");
    form.set("reply_markup", JSON.stringify({inline_keyboard:[[{text:"К сигналу",callback_data:"signal:123"}]]}));
    form.set("photo",new Blob([new Uint8Array([137,80,78,71])],{type:"image/png"}),"chart.png");
    const response = await worker.fetch(req("/v1/photo-card", {
      method:"POST",headers:{authorization:"Bearer "+"x".repeat(48)},body:form
    }),env);
    assert.equal(response.status,200);
    assert.equal((await response.json()).result.message_id,42725);
    assert.equal(outgoing.length,1);
  } finally { globalThis.fetch = originalFetch; }
});

test("photo-card file-id repost carries caption and keyboard in one Telegram call", async () => {
  const originalFetch = globalThis.fetch;
  let sends = 0;
  globalThis.fetch = async (url, options) => {
    sends++;
    const payload = JSON.parse(options.body);
    assert.equal(payload.chat_id,"12345");
    assert.equal(payload.photo,"existing-file-id");
    assert.equal(payload.caption,"🔁 ДУБЛИРОВАНИЕ");
    assert.equal(payload.reply_markup.inline_keyboard[0][0].text,"К сигналу");
    return new Response(JSON.stringify({ok:true,result:{message_id:42726}}),{status:200});
  };
  try {
    const response = await worker.fetch(req("/v1/photo-card", {
      method:"POST",headers:{authorization:"Bearer "+"x".repeat(48),"content-type":"application/json"},
      body:JSON.stringify({file_id:"existing-file-id",caption:"🔁 ДУБЛИРОВАНИЕ",
        reply_markup:{inline_keyboard:[[{text:"К сигналу",callback_data:"signal:123"}]]}})
    }),env);
    assert.equal(response.status,200);
    assert.equal(sends,1);
  } finally { globalThis.fetch = originalFetch; }
});

test("photo-card rejects invalid keyboard before network", async () => {
  const response = await worker.fetch(req("/v1/photo-card", {
    method:"POST",headers:{authorization:"Bearer "+"x".repeat(48),"content-type":"application/json"},
    body:JSON.stringify({file_id:"existing-file-id",caption:"🪞 MIRROR",
      reply_markup:{inline_keyboard:[[{text:"unsafe",url:"http://example.com"}]]}})
  }),env);
  assert.equal(response.status,400);
});

test("photo-card denies unauthenticated photo", async () => {
  const response = await worker.fetch(req("/v1/photo-card",{
    method:"POST",headers:{"content-type":"application/json"},
    body:JSON.stringify({file_id:"existing-file-id",caption:"test"})
  }),env);
  assert.equal(response.status,401);
});

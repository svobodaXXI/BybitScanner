// Telegram Gateway send-only transport prototype for issue #684.
// Requires secrets: GATEWAY_SHARED_SECRET, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.
// No incoming bot commands, no trading controls, no durable queue in this slice.
const reply = (status, body) => new Response(JSON.stringify(body), {
  status, headers: {"content-type":"application/json; charset=utf-8","cache-control":"no-store"}
});
function matches(a, b) {
  const enc = new TextEncoder();
  const x = enc.encode(a), y = enc.encode(b);
  let difference = x.length ^ y.length;
  const size = Math.max(x.length, y.length);
  for (let i = 0; i < size; i++) difference |= (x[i] || 0) ^ (y[i] || 0);
  return difference === 0;
}
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health" && request.method === "GET") {
      return reply(200, {component:"bybitscanner-telegram-gateway",status:"up",delivery_verified:false});
    }
    if (url.pathname !== "/v1/send" || request.method !== "POST") {
      return reply(404, {ok:false,error:"not_found"});
    }
    if (!env.GATEWAY_SHARED_SECRET || env.GATEWAY_SHARED_SECRET.length < 32 ||
        !env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID) {
      return reply(503, {ok:false,error:"not_configured"});
    }
    const bearer = request.headers.get("authorization") || "";
    if (!bearer.startsWith("Bearer ") ||
        !matches(bearer.slice(7), env.GATEWAY_SHARED_SECRET)) {
      return reply(401, {ok:false,error:"unauthorized"});
    }
    if (!(request.headers.get("content-type") || "").toLowerCase().startsWith("application/json")) {
      return reply(415, {ok:false,error:"json_required"});
    }
    const length = Number(request.headers.get("content-length") || 0);
    if (length > 8192) return reply(413, {ok:false,error:"too_large"});
    let input;
    try {
      const raw = await request.text();
      if (raw.length > 8192) return reply(413, {ok:false,error:"too_large"});
      input = JSON.parse(raw);
    } catch (_) { return reply(400, {ok:false,error:"invalid_json"}); }
    if (!input || typeof input !== "object" || Array.isArray(input) ||
        !["event_id,text", "event_id,reply_markup,text"].includes(Object.keys(input).sort().join(",")) ||
        typeof input.event_id !== "string" || !/^[A-Za-z0-9_-]{8,128}$/.test(input.event_id) ||
        typeof input.text !== "string" || input.text.length < 1 || input.text.length > 4096) {
      return reply(400, {ok:false,error:"invalid_payload"});
    }
    if (input.reply_markup !== undefined &&
        (!input.reply_markup || typeof input.reply_markup !== "object" ||
         !Array.isArray(input.reply_markup.inline_keyboard) ||
         Object.keys(input.reply_markup).length !== 1 ||
         input.reply_markup.inline_keyboard.length > 20 ||
         !input.reply_markup.inline_keyboard.every(row =>
           Array.isArray(row) && row.length <= 8 && row.every(button =>
             button && typeof button.text === "string" && button.text.length <= 64 &&
             Object.keys(button).length === 2 &&
             (typeof button.callback_data === "string" && button.callback_data.length <= 64 ||
              typeof button.url === "string" && button.url.startsWith("https://") && button.url.length <= 2048 ||
              button.web_app && typeof button.web_app.url === "string" &&
              button.web_app.url.startsWith("https://") && button.web_app.url.length <= 2048))))) {
      return reply(400, {ok:false,error:"invalid_reply_markup"});
    }
    let response;
    try {
      response = await fetch("https://api.telegram.org/bot" +
        env.TELEGRAM_BOT_TOKEN + "/sendMessage", {
        method:"POST",
        headers:{"content-type":"application/json"},
        body:JSON.stringify({chat_id:env.TELEGRAM_CHAT_ID,text:input.text, ...(input.reply_markup === undefined ? {} : {reply_markup:input.reply_markup})}),
        signal:AbortSignal.timeout(10000)
      });
    } catch (_) {
      return reply(503, {ok:false,error:"telegram_transport_unavailable",event_id:input.event_id});
    }
    let result;
    try { result = await response.json(); }
    catch (_) { return reply(502, {ok:false,error:"invalid_telegram_response",event_id:input.event_id}); }
    if (!response.ok || result.ok !== true) {
      return reply(502, {
        ok:false,error:"telegram_rejected",event_id:input.event_id,
        retryable:response.status === 429 || response.status >= 500,
        retry_after_seconds:Number(response.headers.get("retry-after") || 0)
      });
    }
    return reply(200, {ok:true,event_id:input.event_id,
      stage:"accepted_by_telegram_api",telegram_message_id:result.result?.message_id ?? null});
  }
};

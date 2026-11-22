// Telegram Gateway send-only transport prototype for issue #684.
// Requires secrets: GATEWAY_SHARED_SECRET, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.
// No incoming bot commands, no trading controls, no durable queue in this slice.
const reply = (status, body) => new Response(JSON.stringify(body), {
  status, headers: {"content-type":"application/json; charset=utf-8","cache-control":"no-store"}
});
// Preserve only safe Telegram rejection metadata; never forward raw API bodies.
function telegramRejection(upstream, payload, error, extra = {}) {
  const apiCode = Number.isInteger(payload?.error_code) &&
    payload.error_code >= 400 && payload.error_code <= 599 ? payload.error_code : null;
  const statusCode = apiCode ?? upstream.status;
  const status = statusCode >= 400 && statusCode < 500 ? statusCode : 502;
  const retry = payload?.parameters?.retry_after;
  const retryAfter = status === 429 && Number.isSafeInteger(retry) && retry > 0
    ? Math.min(retry, 86400) : null;
  return new Response(JSON.stringify({ok:false,error,...extra,
    upstream_status:upstream.status,upstream_error_code:apiCode,
    ...(retryAfter === null ? {} : {retry_after:retryAfter})}), {
    status,headers:{"content-type":"application/json; charset=utf-8",
      "cache-control":"no-store",
      ...(retryAfter === null ? {} : {"retry-after":String(retryAfter)})}
  });
}
function matches(a, b) {
  const enc = new TextEncoder();
  const x = enc.encode(a), y = enc.encode(b);
  let difference = x.length ^ y.length;
  const size = Math.max(x.length, y.length);
  for (let i = 0; i < size; i++) difference |= (x[i] || 0) ^ (y[i] || 0);
  return difference === 0;
}

const releaseId = /^[0-9a-f]{32}$/;
const releaseSha = /^[0-9a-f]{40}$/;
const releaseKey = /^[0-9a-f]{64}$/;
function releaseText(sha) {
  return "BybitScanner: обновление VPS\nSHA: " + sha +
    "\nШтатный UPDATE. Торговля останется выключенной.";
}
function releaseButtons(rid) {
  return {inline_keyboard:[[{text:"✅ Подтвердить обновление",callback_data:"rel:a:"+rid},
    {text:"❌ Отклонить",callback_data:"rel:r:"+rid}]]};
}
async function attestRelease(update, env) {
  // Only an actual Telegram getUpdates result is an input. Never accept a
  // caller-supplied callback or sign with the ordinary gateway bearer.
  if (!releaseKey.test(env.RELEASE_APPROVAL_KEY || "") ||
      env.RELEASE_APPROVAL_KEY === env.GATEWAY_SHARED_SECRET || !env.TELEGRAM_CHAT_ID || !Number.isSafeInteger(update?.update_id) || update.update_id <= 0) return;
  const q = update.callback_query, m = q?.message;
  if (!q || !m || q.from?.is_bot !== false || m.chat?.type !== "private" ||
      String(q.from?.id) !== String(env.TELEGRAM_CHAT_ID) ||
      String(m.chat?.id) !== String(env.TELEGRAM_CHAT_ID) ||
      !Number.isSafeInteger(m.message_id) || m.message_id <= 0 ||
      m.from?.is_bot !== true || typeof m.text !== "string" || typeof q.data !== "string") return;
  const match = /^rel:([ar]):([0-9a-f]{32})$/.exec(q.data);
  const sha = /^BybitScanner: обновление VPS\nSHA: ([0-9a-f]{40})\n/.exec(m.text)?.[1];
  if (!match || !sha || m.text !== releaseText(sha) ||
      !Array.isArray(m.reply_markup?.inline_keyboard) ||
      m.reply_markup.inline_keyboard.length !== 1 ||
      !Array.isArray(m.reply_markup.inline_keyboard[0]) ||
      m.reply_markup.inline_keyboard[0].length !== 2 ||
      !m.reply_markup.inline_keyboard[0].every((b,i)=>b &&
        Object.keys(b).sort().join(",")==="callback_data,text" &&
        b.text===releaseButtons(match[2]).inline_keyboard[0][i].text &&
        b.callback_data===releaseButtons(match[2]).inline_keyboard[0][i].callback_data)) return;
  const observed = Math.floor(Date.now()/1000);
  if (!Number.isSafeInteger(m.date) || m.date > observed || observed-m.date > 900) return;
  const payload = {decision:match[1]==="a"?"approve":"reject",message_id:m.message_id,
    observed_at:observed,request_id:match[2],target_sha:sha,update_id:update.update_id};
  const raw = Uint8Array.from(env.RELEASE_APPROVAL_KEY.match(/../g), x=>parseInt(x,16));
  const key = await crypto.subtle.importKey("raw",raw,{name:"HMAC",hash:"SHA-256"},false,["sign"]);
  const canonical = JSON.stringify(payload);
  const sig = await crypto.subtle.sign("HMAC",key,new TextEncoder().encode(
    "BybitScanner-Release-Approval-v1\u0000"+canonical));
  update._release_approval = {payload,tag:Array.from(new Uint8Array(sig),x=>x.toString(16).padStart(2,"0")).join("")};
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health" && request.method === "GET") {
      return reply(200, {component:"bybitscanner-telegram-gateway",status:"up",delivery_verified:false});
    }
    // Root-only proposal delivery. Ordinary gateway callers cannot invoke this route.
    if (url.pathname === "/v1/release-proposal" && request.method === "POST") {
      if (!releaseKey.test(env.RELEASE_APPROVAL_KEY || "") || !env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID ||
          env.RELEASE_APPROVAL_KEY === env.GATEWAY_SHARED_SECRET)
        return reply(503,{ok:false,error:"release_not_configured"});
      if (!matches(request.headers.get("authorization")||"", "Bearer "+env.RELEASE_APPROVAL_KEY))
        return reply(401,{ok:false,error:"unauthorized"});
      let input;
      try {
        const raw=await request.text();
        if(raw.length>256) return reply(400,{ok:false,error:"invalid_proposal"});
        input=JSON.parse(raw);
      } catch (_) { return reply(400,{ok:false,error:"invalid_proposal"}); }
      if (!input || Object.keys(input).sort().join(",")!=="request_id,target_sha" ||
          typeof input.request_id!=="string" || !releaseId.test(input.request_id) ||
          typeof input.target_sha!=="string" || !releaseSha.test(input.target_sha))
        return reply(400,{ok:false,error:"invalid_proposal"});
      try {
        const tg=await fetch("https://api.telegram.org/bot"+env.TELEGRAM_BOT_TOKEN+"/sendMessage",{
          method:"POST",headers:{"content-type":"application/json"},
          body:JSON.stringify({chat_id:env.TELEGRAM_CHAT_ID,text:releaseText(input.target_sha),
            reply_markup:releaseButtons(input.request_id)}),signal:AbortSignal.timeout(10000)});
        const p=await tg.json(), m=p.result;
        if (!tg.ok || p.ok!==true || !Number.isSafeInteger(m?.message_id) || m.message_id<=0 ||
            String(m.chat?.id)!==String(env.TELEGRAM_CHAT_ID) || m.chat?.type!=="private" ||
            m.text!==releaseText(input.target_sha))
          return reply(502,{ok:false,error:"release_delivery_unproven"});
        return reply(200,{ok:true,message_id:m.message_id});
      } catch (_) { return reply(503,{ok:false,error:"release_delivery_unproven"}); }
    }
    // Existing VPS monitoring remains the sole getUpdates consumer.
    if (url.pathname === "/v1/get-updates" && request.method === "POST") {
      if (!env.GATEWAY_SHARED_SECRET || env.GATEWAY_SHARED_SECRET.length < 32 || !env.TELEGRAM_BOT_TOKEN)
        return reply(503, {ok:false,error:"not_configured"});
      const auth = request.headers.get("authorization") || "";
      if (!auth.startsWith("Bearer ") || !matches(auth.slice(7), env.GATEWAY_SHARED_SECRET))
        return reply(401, {ok:false,error:"unauthorized"});
      let args;
      try { args = await request.json(); } catch (_) { return reply(400, {ok:false,error:"invalid_json"}); }
      if (!args || typeof args !== "object" || Array.isArray(args) ||
          Object.keys(args).some(k => !["offset","timeout","allowed_updates"].includes(k)) ||
          (args.offset !== undefined && (!Number.isSafeInteger(args.offset) || args.offset < 0)) ||
          (args.timeout !== undefined && (!Number.isInteger(args.timeout) || args.timeout < 0 || args.timeout > 30)) ||
          (args.allowed_updates !== undefined && !Array.isArray(args.allowed_updates)))
        return reply(400, {ok:false,error:"invalid_params"});
      const params = new URLSearchParams();
      if (args.offset !== undefined) params.set("offset", String(args.offset));
      params.set("timeout", String(args.timeout ?? 0));
      params.set("allowed_updates", JSON.stringify(["callback_query","message"]));
      try {
        const remote = await fetch("https://api.telegram.org/bot" + env.TELEGRAM_BOT_TOKEN + "/getUpdates?" + params, {
          signal: AbortSignal.timeout(38000)
        });
        const payload = await remote.json();
        if (remote.ok && payload.ok === true && Array.isArray(payload.result)) {
          for (const update of payload.result) {
            if (!update || typeof update !== "object") continue;
            delete update._release_approval;
            try { await attestRelease(update,env); } catch (_) { /* Approval remains unproven; ordinary polling survives. */ }
          }
        }
        return reply(200, payload);
      } catch (_) { return reply(503, {ok:false,error:"telegram_poll_unavailable"}); }
    }
    if (url.pathname === "/v1/bot-method" && request.method === "POST") {
      if (!env.GATEWAY_SHARED_SECRET || env.GATEWAY_SHARED_SECRET.length < 32 ||
          !env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID)
        return reply(503, {ok:false,error:"not_configured"});
      const header = request.headers.get("authorization") || "";
      if (!header.startsWith("Bearer ") || !matches(header.slice(7), env.GATEWAY_SHARED_SECRET))
        return reply(401, {ok:false,error:"unauthorized"});
      let body;
      try {
        const raw = await request.text();
        if (raw.length > 16384) return reply(413,{ok:false,error:"too_large"});
        body = JSON.parse(raw);
      } catch (_) { return reply(400,{ok:false,error:"invalid_json"}); }
      if (!body || !["answerCallbackQuery","setMyCommands","getChatMenuButton",
                     "setChatMenuButton"].includes(body.method) ||
          !body.params || typeof body.params !== "object" ||
          Array.isArray(body.params)) return reply(400,{ok:false,error:"unsupported_method"});
      const params = body.params;
      if (["getChatMenuButton","setChatMenuButton"].includes(body.method) &&
          String(params.chat_id) !== String(env.TELEGRAM_CHAT_ID))
        return reply(403,{ok:false,error:"owner_chat_required"});
      if (body.method === "setChatMenuButton") {
        let menu;
        try { menu = JSON.parse(params.menu_button); } catch (_) {
          return reply(400,{ok:false,error:"invalid_menu"});
        }
        const commands = menu && menu.type === "commands" && Object.keys(menu).length === 1;
        const webApp = menu && menu.type === "web_app" &&
          Object.keys(menu).sort().join(",") === "text,type,web_app" &&
          typeof menu.text === "string" && menu.text.length <= 64 &&
          menu.web_app && Object.keys(menu.web_app).join(",") === "url" &&
          typeof menu.web_app.url === "string" &&
          menu.web_app.url.startsWith("https://") &&
          menu.web_app.url.length <= 2048;
        if (!commands && !webApp) return reply(400,{ok:false,error:"unsupported_menu"});
      }
      if (body.method === "answerCallbackQuery" &&
          (typeof params.callback_query_id !== "string" ||
           params.callback_query_id.length < 1 || params.callback_query_id.length > 256))
        return reply(400,{ok:false,error:"invalid_callback"});
      const allowed = {
        answerCallbackQuery:["callback_query_id","text"],
        setMyCommands:["commands"],
        getChatMenuButton:["chat_id"],
        setChatMenuButton:["chat_id","menu_button"]
      }[body.method];
      if (Object.keys(params).some(key => !allowed.includes(key)))
        return reply(400,{ok:false,error:"invalid_params"});
      try {
        const tg = await fetch("https://api.telegram.org/bot" + env.TELEGRAM_BOT_TOKEN +
          "/" + body.method, {method:"POST",headers:{"content-type":"application/json"},
          body: JSON.stringify(params),signal:AbortSignal.timeout(10000)});
        const payload = await tg.json();
        return reply(200,payload);
      } catch (_) { return reply(503,{ok:false,error:"telegram_method_unavailable"}); }
    }
    // v2 photo card: one Telegram sendPhoto request owns image, UTF-8 caption
    // and inline keyboard. No separate text message can interleave.
    if (url.pathname === "/v1/photo-card" && request.method === "POST") {
      if (!env.GATEWAY_SHARED_SECRET || env.GATEWAY_SHARED_SECRET.length < 32 ||
          !env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID)
        return reply(503,{ok:false,error:"not_configured"});
      const auth = request.headers.get("authorization") || "";
      if (!auth.startsWith("Bearer ") || !matches(auth.slice(7),env.GATEWAY_SHARED_SECRET))
        return reply(401,{ok:false,error:"unauthorized"});
      const type = (request.headers.get("content-type") || "").toLowerCase();
      const contentLength = Number(request.headers.get("content-length") || 0);
      if (contentLength > 2200000) return reply(413,{ok:false,error:"too_large"});
      let caption, markup, photo, photoType, photoBytes;
      if (type.startsWith("multipart/form-data;")) {
        let form;
        try { form = await request.formData(); }
        catch (_) { return reply(400,{ok:false,error:"invalid_form"}); }
        if (Array.from(form.keys()).some(k => !["photo","caption","reply_markup"].includes(k)))
          return reply(400,{ok:false,error:"invalid_photo_card"});
        caption = form.get("caption") ?? "";
        markup = form.get("reply_markup");
        photo = form.get("photo");
        if (!(photo instanceof Blob) || typeof photo.name !== "string")
          return reply(400,{ok:false,error:"invalid_photo"});
        photoType = photo.type;
        if (!["image/png","image/jpeg"].includes(photoType))
          return reply(415,{ok:false,error:"unsupported_image_type"});
        if (!photo.size || photo.size > 2000000)
          return reply(413,{ok:false,error:"photo_too_large"});
        photoBytes = await photo.arrayBuffer();
      } else if (type.startsWith("application/json")) {
        let body;
        try {
          const raw = await request.text();
          if (raw.length > 8192) return reply(413,{ok:false,error:"too_large"});
          body = JSON.parse(raw);
        } catch (_) { return reply(400,{ok:false,error:"invalid_json"}); }
        if (!body || typeof body !== "object" || Array.isArray(body) ||
            Object.keys(body).some(k => !["file_id","caption","reply_markup"].includes(k)) ||
            typeof body.file_id !== "string" || !body.file_id || body.file_id.length > 1024)
          return reply(400,{ok:false,error:"invalid_photo_card"});
        photo = body.file_id;
        caption = body.caption ?? "";
        markup = body.reply_markup === undefined ? null : JSON.stringify(body.reply_markup);
      } else return reply(415,{ok:false,error:"unsupported_content_type"});
      if (typeof caption !== "string" || caption.length > 1024)
        return reply(400,{ok:false,error:"invalid_caption"});
      let keyboard;
      if (markup !== null) {
        if (typeof markup !== "string" || markup.length > 8192)
          return reply(400,{ok:false,error:"invalid_reply_markup"});
        try { keyboard = JSON.parse(markup); }
        catch (_) { return reply(400,{ok:false,error:"invalid_reply_markup"}); }
        if (!keyboard || typeof keyboard !== "object" || Array.isArray(keyboard) ||
            Object.keys(keyboard).join(",") !== "inline_keyboard" ||
            !Array.isArray(keyboard.inline_keyboard) || keyboard.inline_keyboard.length > 20 ||
            !keyboard.inline_keyboard.every(row =>
              Array.isArray(row) && row.length <= 8 && row.every(button =>
                button && typeof button === "object" && !Array.isArray(button) &&
                typeof button.text === "string" && button.text.length <= 64 &&
                Object.keys(button).length === 2 &&
                ((typeof button.callback_data === "string" && button.callback_data.length <= 64) ||
                 (typeof button.url === "string" && button.url.startsWith("https://") && button.url.length <= 2048) ||
                 (button.web_app && typeof button.web_app.url === "string" &&
                  button.web_app.url.startsWith("https://") && button.web_app.url.length <= 2048)))))
          return reply(400,{ok:false,error:"invalid_reply_markup"});
      }
      let body, headers;
      if (photoBytes) {
        const form = new FormData();
        form.set("chat_id",String(env.TELEGRAM_CHAT_ID));
        form.set("caption",caption);
        form.set("photo",new Blob([photoBytes],{type:photoType}),"chart.png");
        if (keyboard) form.set("reply_markup",JSON.stringify(keyboard));
        body = form;
      } else {
        headers = {"content-type":"application/json"};
        body = JSON.stringify({chat_id:env.TELEGRAM_CHAT_ID,photo,caption,
          ...(keyboard ? {reply_markup:keyboard} : {})});
      }
      try {
        const tg = await fetch("https://api.telegram.org/bot"+env.TELEGRAM_BOT_TOKEN+"/sendPhoto",{
          method:"POST",...(headers ? {headers} : {}),body,signal:AbortSignal.timeout(20000)
        });
        const payload = await tg.json();
        if (!tg.ok || payload.ok !== true)
          return telegramRejection(tg,payload,"telegram_photo_rejected");
        return reply(200,{ok:true,result:payload.result});
      } catch (_) { return reply(503,{ok:false,error:"telegram_photo_unavailable"}); }
    }
    if (url.pathname === "/v1/photo-upload" && request.method === "POST") {
      if (!env.GATEWAY_SHARED_SECRET || env.GATEWAY_SHARED_SECRET.length < 32 ||
          !env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID)
        return reply(503,{ok:false,error:"not_configured"});
      const auth = request.headers.get("authorization") || "";
      if (!auth.startsWith("Bearer ") || !matches(auth.slice(7),env.GATEWAY_SHARED_SECRET))
        return reply(401,{ok:false,error:"unauthorized"});
      const type = request.headers.get("content-type") || "";
      if (!type.startsWith("image/png") && !type.startsWith("image/jpeg"))
        return reply(415,{ok:false,error:"unsupported_image_type"});
      const caption = request.headers.get("x-telegram-caption") || "";
      if (caption.length > 1024) return reply(400,{ok:false,error:"invalid_caption"});
      if (Number(request.headers.get("content-length") || 0) > 2000000)
        return reply(413,{ok:false,error:"photo_too_large"});
      let bytes;
      try { bytes = await request.arrayBuffer(); }
      catch (_) { return reply(400,{ok:false,error:"invalid_photo"}); }
      if (!bytes.byteLength || bytes.byteLength > 2000000)
        return reply(413,{ok:false,error:"photo_too_large"});
      const form = new FormData();
      form.set("chat_id",String(env.TELEGRAM_CHAT_ID));
      form.set("caption",caption);
      form.set("photo",new Blob([bytes],{type:type.split(";")[0]}),"chart.png");
      try {
        const tg = await fetch("https://api.telegram.org/bot"+env.TELEGRAM_BOT_TOKEN+"/sendPhoto",{
          method:"POST",body:form,signal:AbortSignal.timeout(20000)
        });
        const payload=await tg.json();
        return reply(200,payload);
      } catch (_) { return reply(503,{ok:false,error:"telegram_photo_unavailable"}); }
    }
    if (url.pathname === "/v1/photo-file-id" && request.method === "POST") {
      if (!env.GATEWAY_SHARED_SECRET || env.GATEWAY_SHARED_SECRET.length < 32 ||
          !env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID)
        return reply(503,{ok:false,error:"not_configured"});
      const auth = request.headers.get("authorization") || "";
      if (!auth.startsWith("Bearer ") || !matches(auth.slice(7),env.GATEWAY_SHARED_SECRET))
        return reply(401,{ok:false,error:"unauthorized"});
      let body;
      try {
        const raw = await request.text();
        if (raw.length > 8192) return reply(413,{ok:false,error:"too_large"});
        body = JSON.parse(raw);
      } catch (_) { return reply(400,{ok:false,error:"invalid_json"}); }
      if (!body || Object.keys(body).some(k => !["file_id","caption","reply_markup"].includes(k)) ||
          typeof body.file_id !== "string" || !body.file_id || body.file_id.length > 1024 ||
          (body.caption !== undefined && (typeof body.caption !== "string" || body.caption.length > 1024)))
        return reply(400,{ok:false,error:"invalid_photo"});
      if (body.reply_markup !== undefined)
        return reply(400,{ok:false,error:"photo_markup_not_supported"});
      try {
        const tg = await fetch("https://api.telegram.org/bot"+env.TELEGRAM_BOT_TOKEN+"/sendPhoto",{
          method:"POST",headers:{"content-type":"application/json"},
          body:JSON.stringify({chat_id:env.TELEGRAM_CHAT_ID,photo:body.file_id,
                               caption:body.caption ?? ""}),
          signal:AbortSignal.timeout(15000)
        });
        const result=await tg.json();
        return reply(200,result);
      } catch (_) { return reply(503,{ok:false,error:"telegram_photo_unavailable"}); }
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
    try {
      const tg = await fetch("https://api.telegram.org/bot" +
        env.TELEGRAM_BOT_TOKEN + "/sendMessage", {
        method:"POST",headers:{"content-type":"application/json"},
        body:JSON.stringify({chat_id:env.TELEGRAM_CHAT_ID,text:input.text,
          ...(input.reply_markup === undefined ? {} : {reply_markup:input.reply_markup})}),
        signal:AbortSignal.timeout(10000)
      });
      const payload = await tg.json();
      if (!tg.ok || payload.ok !== true)
        return telegramRejection(tg,payload,"telegram_rejected",{event_id:input.event_id});
      return reply(200,{ok:true,event_id:input.event_id,
        stage:"accepted_by_telegram_api",
        telegram_message_id:payload.result?.message_id ?? null});
    } catch (_) {
      return reply(503,{ok:false,error:"telegram_transport_unavailable",
        event_id:input.event_id});
    }
  }
};



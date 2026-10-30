// Cloudflare Worker: allowlisted forwarder to the existing Vercel Telegram Gateway.
// Deployment: Cloudflare dashboard, worker "bybitscanner-gateway".
// No Telegram token, shared secret, Cloudflare Access or trading authority here.
// Historical VPS owner-verified text+PNG route: 2026-10-30.
// Note: source is a reproducible copy; current deployed CF worker is manual.
const ORIGIN = "https://bybitscanner-telegram-gateway.vercel.app";

export default {
  async fetch(request) {
    const path = new URL(request.url).pathname;
    const allowed = {
      "/health": "GET",
      "/v1/send": "POST",
      "/v1/photo-upload": "POST",
      "/v1/photo-file-id": "POST",
      "/v1/get-updates": "POST",
      "/v1/bot-method": "POST"
    };

    if (allowed[path] !== request.method) {
      return new Response("Not found", { status: 404 });
    }

    return fetch(new Request(ORIGIN + path, request), {
      redirect: "manual"
    });
  }
};

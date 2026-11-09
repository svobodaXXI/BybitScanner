// Cloudflare Telegram Gateway: direct, authenticated Telegram transport.
// Reuse the tested API handler; no Vercel origin, second poller, or trading authority.
// Wrangler bundles this local module import into the existing bybitscanner-gateway Worker.
export { default } from "./worker.mjs";

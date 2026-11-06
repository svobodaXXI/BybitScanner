# Cloudflare Workers deployment candidate — Telegram Gateway

The existing `worker.mjs` implements the Cloudflare Workers `export default { fetch(request, env) }` contract. `wrangler.toml` points to it; no Telegram/Scanner trading logic is changed.

**Not deployed / not an accepted transport.** A successful HTTPS request to `https://workers.dev` does **not** prove that a particular `<worker>.<account>.workers.dev` address is reachable from VPS, or that this Worker can reach `https://api.telegram.org`.

Deployment prerequisites (outside GitHub): a user-authorized Cloudflare account, a configured workers.dev account subdomain, and three secrets provisioned without logging values: `GATEWAY_SHARED_SECRET`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Reuse the same validated owner and authorized token; avoid exposing secrets in CLI arguments or GitHub. Deploy from `deploy/telegram_gateway` using Wrangler. No Vercel removal yet.

**Acceptance, in order:** (1) Cloudflare Worker endpoint actually deployed; (2) VPS HTTPS connection to that **exact hostname** works; (3) Worker authenticates and returns `stage=accepted_by_telegram_api` for one safe diagnostic message; (4) owner confirms receipt; (5) callback/getUpdates support and duplicate-send safety verified; (6) only then separately authorize flipping the Gateway URL in protected VPS environment at a safe process boundary. Do not claim 24/7 delivery or restart any running backend merely on `/health` success.

PAPER only. Robot/Scanner/PAPER_AUTO/STOP-TAKE/DB remain untouched. No LIVE.

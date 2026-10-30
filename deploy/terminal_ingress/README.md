# Terminal Telegram Mini App ingress (not deployed)

## Status and boundaries

This is **development-only**. No public URL is assigned, no VPS deployment is authorized, and `BYBITSCANNER_WORKSPACE_URL` must remain unset until security acceptance. The existing internal Terminal (`127.0.0.1:8080`) and PAPER API (`127.0.0.1:8765`) remain loopback-only. No runtime or trading modules are changed.

### Request path

Telegram bot `/terminal` already sends an inline `web_app` button. Once approved, set `BYBITSCANNER_WORKSPACE_URL=https://<approved-host>/login` so Telegram supplies signed Mini App `initData`. The public HTTPS tunnel routes **only** to `127.0.0.1:8081`, the protected Nginx listener (never to legacy `:8080`, PAPER `:8765` or auth sidecar `:8091`).

- `/login` serves a small bootstrap page. It submits signed `Telegram.WebApp.initData` with a same-origin POST.
- `/_telegram_auth` validates Telegram HMAC SHA-256 against bot token, allowed **numeric** owner user ID, `auth_date` within five minutes, no duplicate query keys, then sets a signed 1-hour Secure HttpOnly SameSite=Strict `__Host-terminal` cookie.
- Nginx requires `auth_request /_auth` for every static path and `/api/` path, across all HTTP methods. For unsafe methods/WebSocket upgrades, the sidecar also enforces the expected `Origin`; no token/cookie grants direct ingress access without checks.
- Invalid/expired signatures and sessions fail closed. Sidecar down means auth_request error, never backend access.
- An ingress must additionally use TLS with an authenticated, pinned hostname and transport between cloud edge and VPS. **Do not enable a random unauthenticated tunnel or port-forward**. Keep ports 80/443/8080/8081/8091/8765 blocked externally. Do not expose `/api/` on a second route.
- The Nginx `auth_request` module must be present. Review static frontend relative paths, API verbs, SSE and WebSocket usage before live acceptance.
- All secrets are deployment-only; never commit bot token, session HMAC secret, owner user ID as a secret, or Cloudflare credentials.

### Runtime env for the sidecar (later owner-approved installation)

`BYBITSCANNER_TELEGRAM_BOT_TOKEN` (same bot used for Mini App signing), `BYBITSCANNER_TELEGRAM_OWNER_USER_ID` (numeric account ID; do not substitute chat ID without verifying that they correspond), `BYBITSCANNER_TERMINAL_PUBLIC_ORIGIN` (exact HTTPS origin, no path), `BYBITSCANNER_TERMINAL_SESSION_SECRET` (at least 32 unpredictable bytes). Bind sidecar on `127.0.0.1:8091`. Put `nginx-authenticated.conf` in a separate Nginx site after reviewing existing setup; do not overwrite the existing localhost site.

### Acceptance gate before any VPS mutation

1. Verify owner-only valid `initData` and reject fake user_id, bad HMAC, duplicate fields, expired/future `auth_date`, replay outside 5 min; verify expiry/tampering of signed cookies.
2. Confirm anonymous direct requests to `/`, `/api/` and every API method, including WebSocket upgrade, return denial. Confirm unsafe cross-origin attempts denied even with cookie and sidecar failure fails closed.
3. Confirm valid Telegram Mini App user reaches Terminal and can read expected PAPER views. Confirm no direct network access to internal Nginx, backend or auth sidecar; ingress path remains limited to authenticated Nginx.
4. Only after explicit permission, assign an actual HTTPS hostname and ingress provider, set secrets in protected configuration, install sidecar/nginx, and set workspace URL. Do not restart backend/Robot/Scanner or mutate PAPER DB. LIVE prohibited.

No provider/hostname has been verified yet; **do not infer a publicly accessible Terminal from this PR**.

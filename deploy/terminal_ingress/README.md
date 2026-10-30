# Terminal Telegram Mini App ingress — phone verified

> **CURRENT VERIFIED STATUS — 2026-10-30:** Direct IP HTTPS Terminal was deployed on the VPS and the owner successfully opened Workspace from the Telegram /terminal Mini App on a phone. The first Telegram attempt timed out; a direct phone-browser visit to /login (which correctly requested Telegram) followed by a Telegram retry succeeded. Current deployment details, constraints and recovery are preserved in [DOCUMENTS/TERMINAL_PHONE_WORKING_CONNECTION_20261030.md](../../DOCUMENTS/TERMINAL_PHONE_WORKING_CONNECTION_20261030.md). The historical pre-deployment sections below remain as implementation guidance, **not current status**. Do not deploy Tailscale.

## Historical implementation and deployment gates

This is **development-only**. No public URL is assigned, no VPS deployment is authorized, and `BYBITSCANNER_WORKSPACE_URL` must remain unset until security acceptance. The existing internal Terminal (`127.0.0.1:8080`) and PAPER API (`127.0.0.1:8765`) remain loopback-only. No runtime or trading modules are changed.

### Request path

Telegram bot `/terminal` already sends an inline `web_app` button. Once approved, set `BYBITSCANNER_WORKSPACE_URL=https://<approved-host>/login` so Telegram supplies signed Mini App `initData`. The direct VPS TLS Nginx listener routes **only** to `127.0.0.1:8081`, the protected Nginx listener (never to legacy `:8080`, PAPER `:8765` or auth sidecar `:8091`).

- `/login` serves a small bootstrap page. It submits signed `Telegram.WebApp.initData` with a same-origin POST.
- `/_telegram_auth` validates Telegram HMAC SHA-256 against bot token, allowed **numeric** owner user ID, `auth_date` within five minutes, no duplicate query keys, then sets a signed 1-hour Secure HttpOnly SameSite=Strict `__Host-terminal` cookie.
- Nginx requires `auth_request /_auth` for every static path and `/api/` path, across all HTTP methods. For unsafe methods/WebSocket upgrades, the sidecar also enforces the expected `Origin`; no token/cookie grants direct ingress access without checks.
- Invalid/expired signatures and sessions fail closed. Sidecar down means auth_request error, never backend access.
- Use the direct TLS listener on the known VPS IP with an automatically renewed trusted IP certificate. **Do not enable a random unauthenticated tunnel or port-forward**. Keep ports 80/443/8080/8081/8091/8765 blocked externally. Do not expose `/api/` on a second route.
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


## Direct IP HTTPS — no Tailscale, no domain, no Cloudflare

The approved architectural direction avoids a third-party tunnel. Public HTTPS terminates on the **existing VPS** at `https://83.217.213.181`, directly in Nginx. The gateway for Telegram messages remains a separate existing service. This PR is **code only**, not a deployed/configured endpoint.

1. Only after owner-authorized VPS work, preflight: verify the exact VPS IP, Nginx socket inventory, current upstream config, firewall restrictions, `nginx -V` auth_request, available RAM/disk, and no existing service bound to :80/:443. Never overwrite another owner's Nginx site. Save an isolated rollback copy.
2. Run **127.0.0.1-only** auth sidecar (`:8091`) and protected Nginx listener (`:8081`) from PR #687. Validate no-cookie denial, forged owner, stale/invalid Telegram `initData`, cross-origin unsafe methods, WebSocket upgrades, sidecar outage fail-closed, and no accidental unprotected route. Do not touch `:8080` or `:8765`.
3. Use Certbot **5.4+** (required for IP + webroot) with Let's Encrypt `shortlived` profile. Place ACME webroot in a dedicated path `/var/lib/bybitscanner/acme-challenge`. Open public port 80 only for `/.well-known/acme-challenge/`; all other HTTP paths return 404. Use `--ip-address 83.217.213.181 --preferred-profile shortlived --webroot --webroot-path /var/lib/bybitscanner/acme-challenge` and **first** `--staging` to avoid production rate limits. The first certificate is untrusted; then issue without `--staging` to receive trusted TLS. If issuance fails, do not start public :443.
4. After obtaining the real trusted cert, install isolated `nginx-direct-ip-https.conf`: public :443 forwards **only** to protected `:8081`; legacy terminal and backend ports remain loopback and blocked externally. Validate `nginx -t` then reload Nginx, without restarting trading.
5. Configure verified Certbot auto-renew + deploy-hook `nginx -t && systemctl reload nginx`; test a *dry-run renewal* and alert/monitor failures, because IP certs expire every ~6 days. Never claim persistence from a one-time cert.
6. Set sidecar `BYBITSCANNER_TERMINAL_PUBLIC_ORIGIN=https://83.217.213.181`. Test `https://83.217.213.181/` and `/api/` unauthenticated from outside (denied), forged auth and bad Origin (denied), valid owner Mini App (works) before adding `BYBITSCANNER_WORKSPACE_URL=https://83.217.213.181/login` to the **Telegram** service only. Only its restart is permitted.
7. Rollback only the new :80/:443 Nginx site, sidecar, ACME renewal hook and Telegram workspace URL if ingress fails. Never restart/alter backend, Scanner, Robot, PAPER_AUTO, PAPER DB, Admission or STOP/TAKE. LIVE forbidden. Any IP/firewall opening requires owner-authorized scoped change; do not disable global firewall.

**Corrected trust boundary:** Direct HTTPS removes Tailscale but :443 itself becomes a public listener. Nginx must never serve any Terminal/API content except through guarded :8081. Dependence on the CA for *renewal* remains, but a transient CA outage does not affect the running PAPER robot.

Official references:
- https://letsencrypt.org/2026/03/11/shorter-certs-certbot
- https://core.telegram.org/bots/webapps

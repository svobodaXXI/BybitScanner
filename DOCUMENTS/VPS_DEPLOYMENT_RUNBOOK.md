# BybitScanner VPS Deployment Runbook

## Current authoritative state

Authoritative Git checkpoint:
`8c6a5b6`

Production VPS:
- IP: `91.84.98.100`
- OS: Ubuntu 24.04
- SSH user: `root`
- project root: `/root/BybitScanner`
- Python venv: `/root/BybitScanner/.venv`

## Backend

Systemd unit:
`bybitscanner-terminal.service`

Backend bind:
`127.0.0.1:8765`

The backend must remain loopback-only. It must not be exposed directly to the public network.

Runtime safety requirements:
- LIVE mutation gates remain fail-closed by default.
- Do not enable real-money acceptance or mutation gates as part of ordinary deployment.
- Do not enter API Key / Secret through the public HTTP page.
- Do not perform BUY / SELL / STOP / TAKE / close acceptance tests during deployment.

## Frontend

Frontend source:
`/root/BybitScanner/terminal/frontend`

Production build:
`/root/BybitScanner/terminal/frontend/dist`

Nginx static root:
`/var/www/bybitscanner`

Public frontend:
`http://91.84.98.100/`

After frontend source changes:

1. Build production frontend.
2. Copy `dist` contents to `/var/www/bybitscanner`.
3. Verify the deployed static files match the current build.

Example verification:

    diff -qr /root/BybitScanner/terminal/frontend/dist /var/www/bybitscanner

No output means the directories match.

## Nginx

Authoritative repository configuration:
`deploy/nginx/bybitscanner.conf`

Active VPS site:
`/etc/nginx/sites-available/bybitscanner`

Enabled site:
`/etc/nginx/sites-enabled/bybitscanner`

The active site must match the repository configuration.

Verification:

    diff -u /root/BybitScanner/deploy/nginx/bybitscanner.conf /etc/nginx/sites-available/bybitscanner

No output means they match.

Before nginx reload:

    nginx -t

Expected result:
configuration syntax is ok and test is successful.

Then:

    systemctl reload nginx

## API reverse proxy

All `/api/` traffic is proxied to:

`http://127.0.0.1:8765`

SSE requirements:
- `proxy_buffering off`
- `proxy_cache off`
- long read/send timeouts

## Workspace WebSocket invariant

The current frontend market-data runtime is:
`BackendWorkspaceMarketDataStore`

It uses a same-origin WebSocket:

`/api/workspace/stream?symbol=<SYMBOL>&interval=<INTERVAL>`

Therefore nginx MUST forward WebSocket Upgrade headers:

    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";

Without these headers:
- direct public SSE streams may still work;
- backend market data may still be healthy;
- but Chart, DOM and Smart Tape can remain empty;
- `/api/workspace/stream` returns HTTP 426 `websocket_upgrade_required`.

Successful public WebSocket handshake must return:

`101 Switching Protocols`

## Verified market-data routes

Backend routes include:

- `/api/health`
- `/api/instruments`
- `/api/accounts`
- `/api/workspace/account`
- `/api/workspace/state`
- `/api/workspace/stream`
- `/api/client-market-projection/stream`
- `/api/public-trades/stream`
- `/api/public-orderbook/stream`
- `/api/public-klines/stream`
- `/api/public-trades`
- `/api/paper-state`
- `/api/open-positions`

Direct public SSE transport was verified through nginx for:
- klines
- orderbook
- public trades

The current Workspace UI, however, primarily consumes `/api/workspace/stream` through WebSocket.

## Deployment verification

After deployment verify:

1. Backend:

    systemctl status bybitscanner-terminal.service

2. Nginx:

    nginx -t

3. Public frontend:

    curl -I http://91.84.98.100/

4. PAPER backend:

    curl "http://91.84.98.100/api/paper-state?symbol=ONGUSDT"

5. WebSocket proxy:
   verify `/api/workspace/stream` returns `101 Switching Protocols`.

6. Real-phone visual acceptance:
   - Chart populated
   - DOM populated
   - Smart Tape populated

## Git synchronization

After a completed deployment:

Local:
`main == origin/main`

VPS:
`main == origin/main`

VPS working tree:
clean

Current verified VPS state after checkpoint `8c6a5b6`:
- nginx repository config matches active nginx config;
- public WebSocket handshake PASS;
- Chart PASS;
- DOM PASS;
- Smart Tape PASS;
- LIVE remains fail-closed.

# BybitScanner VPS Deployment Runbook

## VPS 83.217.213.181 — prepare-only, stopped (issue #624, 2026-10-25)

Target: Ubuntu 24.04 VDSina VPS, repository `/opt/BybitScanner`, Terminal static files in
`/var/www/bybitscanner`, Nginx on `127.0.0.1:8080` only (SSH tunnel). The server is prepared and
**stays stopped**: no backend, Scanner, MIRROR, Autopilot, PAPER Robot or Telegram; no LIVE; the main
PC PAPER DB is not transferred.

What the repository provides:
- `tools/vps_check.py` — offline validator (`python -m tools.vps_check`). Reads files, package
  metadata and read-only system state only (`systemctl show`, `nginx -T`, `ss -ltn`); never imports
  the backend/Scanner/Telegram, never connects to Bybit, never opens or creates the PAPER DB, never
  starts, enables or reloads anything. `OK` only after the *installed* units (identical to the
  repository, no drop-ins, static, inactive), their *effective* environment (env file + inline
  `Environment=`, LIVE gates off), the *effective* nginx config (only loopback `listen`, enabled
  site identical to the repository), the actual listening sockets and the write-target ownership
  were all verified; skipped checks give `INCOMPLETE`, never `OK`.
- `deploy/systemd/bybitscanner-paper-backend.service`, `bybitscanner-telegram.service` — existing
  venv `/opt/BybitScanner/venv`, **no `[Install]` section** (cannot be enabled, no start at boot),
  `Restart=no`, PAPER DB in the systemd `StateDirectory` `/var/lib/bybitscanner`. The backend unit's
  `ExecStartPre` runs `tools.vps_check --pre-start`: a start is refused while any LIVE gate or the
  operator token is set, `config.py` is missing, or 8765/8766 is already taken.
- `deploy/systemd/paper.env.example` — template for `/etc/bybitscanner/paper.env` (LIVE gates off,
  fresh PAPER DB under `/var/lib/bybitscanner`, no secrets, standalone MIRROR off, no bytecode writes).
- `deploy/nginx/bybitscanner-loopback.conf` — loopback-only Terminal site.
- On Linux `python -m tools.runtime_intent` never spawns processes: systemd is the only owner of the
  backend and Telegram, so the bootstrap fails closed instead of starting a second owner.

Least privilege: the repository keeps its current owner. The service user `bybitscanner` gets
ownership only of `/var/lib/bybitscanner` and of the gitignored runtime outputs it writes
(`runtime/`, `charts/`, `debug/`, `review_queue/`, `reports/`, `signals_history.json`); no tracked file
changes owner.

Procedure (as root, after the PR is merged; it starts nothing):

    cd /opt/BybitScanner
    test "$(git branch --show-current)" = stable/adfb50b-forward
    git diff --quiet && git diff --cached --quiet
    git fetch origin stable/adfb50b-forward
    git merge --ff-only origin/stable/adfb50b-forward
    id bybitscanner || useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin bybitscanner
    install -d -m 750 -o bybitscanner -g bybitscanner /var/lib/bybitscanner
    for d in runtime charts debug review_queue reports; do install -d -m 750 -o bybitscanner -g bybitscanner "$d"; done
    touch signals_history.json && chown bybitscanner:bybitscanner signals_history.json
    install -d -m 750 -o root -g bybitscanner /etc/bybitscanner
    test -e /etc/bybitscanner/paper.env || install -m 640 -o root -g bybitscanner deploy/systemd/paper.env.example /etc/bybitscanner/paper.env
    install -m 644 deploy/systemd/bybitscanner-paper-backend.service deploy/systemd/bybitscanner-telegram.service /etc/systemd/system/
    systemctl daemon-reload
    diff -u deploy/nginx/bybitscanner-loopback.conf /etc/nginx/sites-enabled/bybitscanner
    /opt/BybitScanner/venv/bin/python -m tools.vps_check

Stop at the first failing line: wrong branch, a dirty tracked tree or a non-fast-forward merge are
reported to the owner, never resolved with `checkout`, `reset`, `stash` or `clean` (untracked files
stay). `install -d` changes the owner of those directories only (not their contents recursively).
If `diff` shows a difference, the installed site is not the repository one and `vps_check` reports
`nginx_site_matches_repo` FAIL: replace it only with owner approval, then `nginx -t`.

Expected: `VPS_PREPARE_CHECK OK`. Known open item until the owner decides: `scanner_config_present`
(machine-local `config.py` with the Telegram identity is not in Git). Do **not** run
`systemctl start` and do not run `python -m terminal.runtime.paper_http_server` as a check: both
start the PAPER runtime.

---

## Previous VPS 91.84.98.100 (historical record; not the #624 target)

### State as recorded for that VPS

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

## Remote Codex phone workflow

Verified on VPS:

- Codex CLI: `0.152.1`
- authenticated with ChatGPT
- model: `gpt-5.6-sol`
- project trust accepted
- system `bubblewrap` installed and active
- Codex starts without the previous missing-bubblewrap warning
- read-only Git validation PASS:
  - branch: `main`
  - working tree: clean
- `tmux 3.4` installed
- persistent tmux session name: `codex`
- session survives SSH client disconnect
- server-side detach command:
  - `tmux detach-client -s codex`
- reattach command:
  - `tmux attach -t codex`
- `/root/.bash_aliases` contains:
  - `alias cx='tmux new-session -A -s codex'`
- `~/.bashrc` automatically sources `~/.bash_aliases`
- mobile SSH client verified from phone
- phone workflow PASS:
  - phone -> SSH -> VPS -> `cx` -> persistent tmux -> Codex
- closing the phone SSH app does not terminate the Codex tmux session
- reconnect restores access to the persistent Codex session
- home PC is not required for remote Codex development control

Safety boundary:

- LIVE remains fail-closed
- LIVE mutation gates remain disabled
- no real-money BUY/SELL/STOP/TAKE/close acceptance was performed
- API Key / Secret must not be entered through the HTTP page

## Future Scanner process supervision

Deferred design note for a later hardening pass. This is **not implemented yet** and is not a current runtime guarantee.

The preferred design is one idempotent `ScannerSupervisor` owned by the existing backend. Telegram's "Запустить сканер" action should mean: **ensure exactly one healthy Scanner instance is running**, not blindly spawn another process.

Required behavior for that future supervisor:

- before every Scanner start, reconcile durable `scanner_runtime_state` with the actual owned Scanner worker/process;
- if the owned worker is already healthy, return `SCANNER_RUNNING` without spawning a duplicate;
- if durable state says running but the owned worker is gone, clear/repair only that stale Scanner process state and start one replacement;
- if an obsolete owned Scanner worker exists, terminate only that worker and then start the authoritative replacement;
- track Scanner ownership with an explicit PID/process-group plus a unique owner/generation token; never use broad process-name killing such as `pkill python`;
- run the same reconciliation when the backend starts, so VPS/backend restarts converge automatically to one unambiguous Scanner process state;
- start must report `SCANNER_RUNNING` only after the replacement worker has actually reached a healthy running state;
- stop/pause/resume must remain idempotent and operate only on the supervisor-owned Scanner instance.

Safety boundary:

- this supervisor may clean up only technical Scanner process/runtime debris that it can prove it owns;
- it must never automatically delete or rewrite Robot candidates, trades, positions, protection obligations, execution history, or other financial state;
- ambiguous Robot/trading ownership continues to use the existing fail-closed reconciliation path;
- LIVE mutation behavior remains outside this design and fail-closed by default.

Implementation preference: reuse the current backend and Scanner control surface; do not add a separate daemon/service unless a concrete runtime limitation later requires it.

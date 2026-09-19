# VPS Runtime Acceptance — 2026-09-16

Status: IN_PROGRESS

This record captures the observed bring-up sequence and current blockers for the VPS runtime.

## Completed

- VPS `main` was synchronized with GitHub `main` at `20c56c4ba64c9222a50d3f7f6d6a5f4cfd2f62f3`.
- The intentional VPS-only `bybit_api.py` network override was preserved and remains uncommitted.
- The PAPER backend service was restarted successfully and returned to active/running state.
- The runtime reported that the local PAPER HTTP server was listening and public market data was active.
- Repository launch scripts were inspected to identify the production process mapping: PAPER backend, `telegram_monitoring.py`, and Scanner entry point `main.py`.
- A temporary standalone `telegram_review` launch was stopped after confirming that it is not the intended production listener for this launch path.
- A shell-output issue was isolated: normal stdout had been redirected to a pipe while stderr remained attached to the terminal. Terminal output was restored. The exact origin of that redirection was not proven.
- `telegram_monitoring.py` passed Python syntax compilation.
- A foreground run exposed the actual startup failure at Telegram command-menu publication.
- A direct Telegram API check confirmed that the currently loaded Telegram credential/configuration is invalid or mis-sourced. The secret value was not printed.

## Not completed / failed

- `telegram_monitoring.py` does not currently stay running; startup fails while publishing the command menu.
- The authoritative source of the incorrect Telegram credential/configuration has not yet been identified.
- The authoritative Robot mode has not yet been re-queried after the backend restart.
- Production Scanner `main.py` has not yet been started in the final combined acceptance run.
- Backend + Telegram monitoring + Scanner simultaneous VPS acceptance is therefore not complete.

## Diagnostic safety decisions

Two Codex proposals were rejected during diagnosis:

- unrelated harness edits were rejected because the task was read-only diagnosis;
- a broad system configuration search was rejected because it could expose a secret value in output.

Future credential-source tracing must remain read-only and must report only source metadata, presence, safe length/hash metadata when needed, and configuration paths — never the secret value itself.

## Scanner performance evidence already available

PR #120's scanner geometry optimization was verified separately before this runtime pass:

- frozen 4STOCK benchmark: 37.003 s before, 6.001 s after;
- normalized semantic oracle matched;
- production-like 50-symbol run: 50/50 OK, 104.127 s total, 2.083 s/symbol average, about 83% CPU, about 113972 KiB max RSS, zero swap activity.

This is useful performance evidence, but it does not replace the pending combined VPS runtime acceptance.

## Next order

1. Finish read-only tracing of the Telegram credential/configuration source without exposing the secret.
2. Restore `telegram_monitoring.py` to a stable running state.
3. Verify that only one Telegram long-polling consumer is active.
4. Re-query authoritative Robot runtime state after the backend restart.
5. Start production Scanner through `main.py`.
6. Observe CPU, memory, load, backend responsiveness, and logs while all required components overlap.
7. Record final PASS/FAIL for the combined runtime acceptance.

LIVE remains outside this acceptance and stays fail-closed.

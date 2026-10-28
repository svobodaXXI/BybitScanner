# BybitScanner VPS Manager — Windows MVP

Standalone Windows utility in `tools/windows_vps_manager.py`, without embedding into the trading Terminal. Deliberately uses Python's standard-library Tkinter to avoid packaging a second React application or server.

## Launch

On Windows with Python 3 + Tkinter and Windows OpenSSH Client installed:

```powershell
py -3 tools\windows_vps_manager.py
```

Enter the VPS hostname/IP and the existing **non-root** SSH account. Before connecting, configure a dedicated Ed25519 SSH key outside the repository and verify the server's SSH host-key fingerprint through a trusted provider channel. Do not disable `StrictHostKeyChecking`. OpenSSH configuration, private keys, and known_hosts are never stored by this application.

The existing SSH configuration can specify the key and port under `%USERPROFILE%\.ssh\config`.

## Scope

Five **read-only** actions: systemd status, existing `tools.vps_check --no-systemd`, Git working-tree/branch/commit inspection, backend's last 35 journal entries, and a combined update preflight (Git status, systemd status, localhost PAPER health). The program intentionally has **no** general-purpose remote command field, trade operations, stop/start, service restart, deploy, database writes or LIVE operations. Remote commands are an allowlist executed with `ssh` and SSH host-key verification.

This MVP reuses the project's existing diagnostics, not the Terminal's UI. An extension for safe PAPER deployment requires explicit owner authorization, identity/preflight verification, backup/rollback design and a tested stop protocol. A direct ChatGPT-to-VPS control channel is **not** provided by this Windows GUI; it is a local operator utility.

## Current limitations

- Not tested on an actual Windows device or on the owner VPS.
- The `bybitscanner` account may need read access to `journalctl`; error output is displayed as-is.
- The VPS host/user are entered per launch. No secrets are requested or stored.
- No SSH credentials or host fingerprints are provisioned by the application.

The update preflight is **informational**, not approval to stop or deploy. It does not establish that the backend is attached to the expected PAPER DB, verify open-position protection, or prove shutdown safety. Any failure must block further owner-side decisions until diagnosed.

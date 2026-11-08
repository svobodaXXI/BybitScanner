# Windows PC → BybitScanner VPS: confirmed recovery and local tool setup (2026-11-08)

Status: **observed operator evidence**, not a runtime/trading readiness receipt. Scope: the **desktop PC** Windows user `svobo`, not the laptop. The owner uses **Codex Desktop GUI already installed/open**, not a CLI-first workflow. Do **not** instruct the owner to launch Codex by typing `codex` in PowerShell. Command-line PowerShell is for bounded SSH access/testing when truly needed; use the already-open Desktop app for Codex tasks. Codex Desktop's direct SSH access is **NOT YET VERIFIED** (see latest failure).

## What changed, and what did not

This is an **additional public IPv4 address, not an API endpoint or API key**:
- VPS: VDSina Ubuntu 24.04, hostname observed via SSH `v3286418.hosted-by-vdsina.ru`.
- Old primary IPv4: `83.217.213.181/24`, primary gateway remains `83.217.213.1`.
- Additional IPv4: `212.193.14.116/24`, VDSina allocation, 6.30 RUB/day, cancellable in provider panel. VDSina panel listed additional subnet gateway `212.193.14.1`, but the **actual default route remains the old gateway**. Never add a second default route as a guess.
- Existing interface: `ens3`. Actual `ip -4 -br addr` after `ip addr add 212.193.14.116/24 dev ens3` showed **both addresses**.
- Primary Netplan: `/etc/netplan/01-netcfg.yaml`, `renderer: networkd`, one `ens3.addresses` list; modified from `[ "83.217.213.181/24" ]` to `[ "83.217.213.181/24", "212.193.14.116/24" ]`. Existing DNS and default route preserved.
- Netplan backup: `/etc/netplan/01-netcfg.yaml.backup-20261108-193614`. `netplan generate` succeeded; **no `netplan apply`, network restart, or VPS reboot performed**. Persistence is configured, **not yet proven by reboot**. Do not reboot just to prove it.
- No PAPER DB / trading service / LIVE / STOP/TAKE / credentials mutation was authorized as part of access recovery.

## Windows PC, confirmed evidence

- Windows profile: `C:\Users\svobo`; desktop path supplied by Windows: `C:\Users\svobo\OneDrive\Рабочий стол`.
- Local `ssh`, `git`, `gh`, `codex`, `py`, `python` were found. `gh auth status` and `codex login status` both succeeded.
- **Codex Desktop** is installed, open, and has the `BybitScanner` project selected in `Этот компьютер` mode. Existing app, not something to reinstall/relaunch from PowerShell; the app and CLI may have different execution environments.
- Working historical private SSH identity (file path only, **do not read, print, commit, or copy its contents**): `C:\Users\svobo\.ssh\bybitscanner_vdsina_gateway_20261030`. The older `bybitscanner_vdsina_2026` key also exists; no new key needed for the successful connection.
- Windows OpenSSH config `C:\Users\svobo\.ssh\config` was **created/appended** with `Host bybitscanner-vps`, `HostName 212.193.14.116`, `User root`, the existing key as `IdentityFile`, `IdentitiesOnly yes`, `BatchMode yes`, `StrictHostKeyChecking yes`, `ConnectTimeout 10`. Do not replace existing config or duplicate aliases without reading it.
- **PowerShell acceptance observed**: `ssh bybitscanner-vps 'whoami; hostname; echo SSH_OK'` returned `root`, `v3286418.hosted-by-vdsina.ru`, `SSH_OK`, exit 0. Host key for additional IP had first been accepted into `known_hosts`. Maintain host-key checks; never use `StrictHostKeyChecking=no`.
- **Codex Desktop acceptance NOT observed**: the initial Desktop agent attempt `ssh bybitscanner-vps ...` returned `ssh: Could not resolve hostname bybitscanner-vps: Этот хост неизвестен.`, exit 1. It did not modify anything. This is consistent with its SSH execution environment **not reading the Windows SSH alias** or using a different SSH binary/config; do not assume it is a broken key or server. Next bounded non-mutating diagnosis: inside Codex Desktop use the explicit Windows OpenSSH executable/config (`C:\Windows\System32\OpenSSH\ssh.exe -F C:\Users\svobo\.ssh\config bybitscanner-vps`) **only if its execution environment can access those Windows paths**, and otherwise stop/report its OS and actual SSH path. Do not change protected environment, keys, or server just to make a test pass.
- **VPS Manager** installed from GitHub Actions run `42374701807`, artifact `BybitScanner-VPS-Manager-Windows`, expected source SHA `844ffc74635c663a9633d1a3b55acd3b8fa7199b`, EXE `C:\Users\svobo\AppData\Local\BybitScanner\VPSManager\release-42374701807\BybitScanner-VPS-Manager.exe`. Shortcut `C:\Users\svobo\OneDrive\Рабочий стол\BybitScanner VPS Manager - новый IP.lnk` supplies `--host 212.193.14.116 --user root --key <existing local key path>`. Owner screenshot confirmed **Состояние → Успешно, Exit code 0** and a read-only service output. This is **not evidence of a safe trading state**.
- VPS Manager screenshot `Состояние` showed three `ActiveState=inactive / SubState=dead` groups; implementation context identifies those status probes as PAPER backend, Telegram, paper-start. Treat this as **status at that observation time**, not global current runtime truth; there was no verification of Scanner/Robot/protection/positions. Do not start/restart anything as a consequence.
- **Машина времени** Windows research-only local simulator installed: `C:\Users\svobo\AppData\Local\BybitScanner\MachineTime\release-42430357426` from GitHub run `42430357426` (artifact `machine-time-windows-h017-real-history`, source SHA `173333546613b6ea0c55eaf1b7529c28c83523b9`). `LOCAL_REPLAY_PACKAGE_OK` and `WINDOWS_LOCAL_REPLAY_SMOKE_OK` observed (loopback, HTML, JS, forbidden routes), Windows shortcut created; launcher request issued. This is local SIMULATION, not PAPER or LIVE.
- Happ 4.5.4 (625) on PC: switching to **TUN** enabled alternate routed access (public egress observed `185.183.32.126` vs direct `88.135.125.163`). Proxy/mixed routes and TLS fragment experiments alone did not resolve the earlier banner timeout. The new IP **after it was assigned to ens3** was proven by SSH exit 0. Happ profile/routing may change: diagnose actual egress and SSH handshake once, rather than asserting VPN is always necessary.

## What happened / lessons

1. Direct home-route IP `88.135.125.163` could trace to the VPS but ports 22/443 were unreachable; VDSina panel displayed `Your IP address is blacklisted!`. Support speculated network restrictions (ТСПУ), **not a verified firewall root cause**.
2. Happ TUN made TCP 22/443 reachable but SSH failed `Connection timed out during banner exchange`. **TCP connect is not SSH authentication.** Existing keys were not at fault, as shown by later successful SSH.
3. VDSina allocated additional public IPv4 `212.193.14.116` for a fee, preserving old IP. Before Ubuntu interface assignment, its TCP ports appeared reachable but SSH banner still timed out; do not interpret that as proof the newly allocated IP is bad.
4. VDSina no longer performs OS-side IP configuration for customers; generic help article contains older CentOS/Ubuntu examples and **networking restart** instructions inappropriate for blindly applying to Ubuntu 24.04. Phone VNC and pasted shell blocks garbled commands; last-resort VNC on PC with one short command at a time gave trustworthy evidence.
5. Via VNC: `systemctl is-active ssh` → `active`; `ss -lntp | grep ':22 '` → `sshd` listening on `0.0.0.0:22` and `[::]:22`; `ssh-keyscan -T 3 127.0.0.1` → SSH banner/host public keys. `ip -4 -br addr` initially showed only `83.217.213.181/24` on `ens3`; default `83.217.213.1`.
6. One live, non-restarting interface address addition `ip addr add 212.193.14.116/24 dev ens3` succeeded. PowerShell SSH using the existing PC key to `root@212.193.14.116` returned exit 0, before Netplan persistence.
7. Netplan file was backed up; one addresses-list addition; `netplan generate` passed. No network restart; follow-up PowerShell via SSH alias returned exit 0. VPS Manager read-only action returned exit 0. Codex Desktop alias lookup remains the only outstanding local tool/access proof.

## Codex Desktop → VPS acceptance (owner report, 2026-11-08)

Following the initial `ssh bybitscanner-vps` failure (unknown hostname) and then `-F C:\\Users\\svobo\\.ssh\\config` denial (`Permission denied`), Codex Desktop re-used the older proven **explicit Windows OpenSSH identity** route, without the alias/config:

- Target: `root@212.193.14.116`.
- Existing PC private-key **path only**: `C:\\Users\\svobo\\.ssh\\bybitscanner_vdsina_gateway_20261030` (use `-i`; do not print, copy or relax ACL on the key).
- SSH options: `IdentitiesOnly=yes`, `BatchMode=yes`, `PasswordAuthentication=no`, `StrictHostKeyChecking=yes`.
- The owner's Codex Desktop execution report: `root`, `v3286418.hosted-by-vdsina.ru`, `SSH_OK`, **exit code 0**. Read-only probe; no server/runtime mutations.
- **Preferred Codex Desktop route**: Windows OpenSSH with explicit `-i` and target IPv4, **not** the host alias and not the Windows user `config` (which the agent environment could not read). Codex Desktop remains a GUI app; **never tell owner to launch it by typing `codex` in PowerShell**.
- This proves an SSH login from Codex Desktop at the time of that probe; it is **not** a trading-runtime readiness certificate or authorization for any mutating command.

## Routing and safety rules for future chats

- **Default PC workflow:** Codex Desktop already open, BybitScanner project selected. Do **not** tell the owner to run `codex` in PowerShell or reinstall Codex. For GitHub tasks use the GitHub connector/PR workflow; for authorized VPS work use verified Codex bridge if proven, or existing PowerShell SSH alias on PC as fallback. No arbitrary VNC/manual juggling unless a specific SSH failure makes it necessary.
- **Preferred VPS address on this PC:** `212.193.14.116`; old `83.217.213.181` is retained for continuity, not erased or assumed universally reachable. SSH configuration path and private-key path are machine-specific, do not confuse with laptop (`bybitscanner_laptop` on `SVOBODA21`).
- Codex Desktop may not inherit host Windows SSH settings. Always verify its execution context and a real SSH exit 0 before claiming Desktop-to-VPS readiness.
- Do not expose private keys, passwords, host credentials, repo tokens. Do not modify `authorized_keys` unnecessarily; do not disable host-key verification.
- No network restart, service changes, `netplan apply`, VPS reboot, PAPER DB access/migration, live trading changes, STOP/TAKE bypass, or deployment under a mere connectivity/documentation task.
- Expensive extra IPv4 continues billing at 6.30 RUB/day until cancelled; deleting it before routing and dependent services are migrated may remove working access. Owner approval required for any cancellation/change.

This record documents observed access recovery. It does not supersede `AGENTS.md`, owning safety specifications, or future actual host evidence.

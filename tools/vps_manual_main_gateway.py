"""Fail-closed MAIN read-only gateway adoption inside the authorized Gitless monolith.

No PAPER/Robot/Scanner/DB actions. Requires the *already installed*, attested
release, a reviewed loopback systemd unit and the existing owner-authenticated
Nginx site. Never invents an unauthenticated route or overwrites an unknown site.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import stat
import subprocess
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from tools.vps_gitless_release_activate import _atomic_file
from tools.vps_release_identity import verify_release
from tools.vps_main_store_key import KEY_NAME, KEY_PATH, verify_main_store_key

UNIT = "bybitscanner-manual-main-read.service"
UNIT_DIR = Path("/etc/systemd/system")
NGINX_DIR = Path("/etc/nginx")
AUTH_LISTENER = "    listen 127.0.0.1:8081;"
BACKEND_BLOCK = (
    "    location /api/ {\n"
    "        auth_request /_auth;\n"
    "        proxy_pass http://127.0.0.1:8765;\n"
)
AUTH_BLOCK = "    location = /_auth {\n        internal;"
BRIDGE_START = "    # Paired Windows Simulator agent only:"
BRIDGE_FACTS_START = "    # Exact owner-queued PAPER facts for the paired device ONLY."
BRIDGE_FACTS_ROUTE = "location = /api/diary/simulator-bridge/facts {"
BRIDGE_CLAIM_PATH = "/api/diary/simulator-bridge/pair-claim"
BRIDGE_CLAIM_BLOCK = (
    "    location = /api/diary/simulator-bridge/pair-claim {\n"
    "        limit_except POST { deny all; }\n"
    "        client_max_body_size 128;\n"
    "        proxy_pass http://127.0.0.1:8765;\n"
    "        proxy_set_header Host $host;\n"
    "        proxy_set_header X-Forwarded-Proto https;\n"
    "        proxy_set_header Cookie \"\";\n"
    "        proxy_set_header Authorization \"\";\n"
    "        proxy_cache off;\n"
    "        proxy_buffering off;\n"
    "        proxy_hide_header Cache-Control;\n"
    "        add_header Cache-Control \"no-store\" always;\n"
    "    }\n"
    "\n"
)
ROUTE_START = "    # MAIN reads are isolated from the PAPER backend."
ROUTE_END = "    # The backend is never publicly exposed"
MARKER = re.compile(r"(?m)^# configuration file ([^:\n]+):\s*$")


class MainGatewayBlocked(ValueError):
    pass


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise MainGatewayBlocked(reason)


def _command(argv: list[str], *, run: Callable) -> str:
    try:
        result = run(argv, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MainGatewayBlocked("gateway_command_unreachable") from exc
    _require(result.returncode == 0, "gateway_command_failed")
    return result.stdout


def _route_from_source(root: Path) -> str:
    path = root / "deploy/terminal_ingress/nginx-authenticated.conf"
    try:
        contents = path.read_text(encoding="utf-8")
        start = contents.index(ROUTE_START)
        end = contents.index(ROUTE_END, start)
        block = contents[start:end]
    except (OSError, UnicodeError, ValueError) as exc:
        raise MainGatewayBlocked("reviewed_main_auth_route_unavailable") from exc
    _require(block.count("location ^~ /api/manual-main/ {") == 1
             and "auth_request /_auth;" in block
             and "proxy_pass http://127.0.0.1:8771;" in block
             and "client_max_body_size 1k;" in block,
             "reviewed_main_auth_route_invalid")
    return block


def _simulator_bridge_from_source(root: Path) -> str:
    """An independently reviewed device-token route, outside the MAIN block.

    Keeping it separate retains byte-for-byte compatibility with the older
    installed Monolith preflight during the protected release transition.
    """
    path = root / "deploy/terminal_ingress/nginx-authenticated.conf"
    try:
        contents = path.read_text(encoding="utf-8")
        start = contents.index(BRIDGE_START)
        end = contents.index(ROUTE_START, start)
        block = contents[start:end]
    except (OSError, UnicodeError, ValueError) as exc:
        raise MainGatewayBlocked("reviewed_simulator_bridge_unavailable") from exc
    successor = block.endswith(BRIDGE_CLAIM_BLOCK)
    reviewed = block.removesuffix(BRIDGE_CLAIM_BLOCK)
    _require(not successor or BRIDGE_FACTS_ROUTE in reviewed,
             "reviewed_simulator_bridge_invalid")
    # Two immutable, precisely constrained source shapes are reviewed:
    # migration release poll+ack (accepted by the installed old monolith),
    # and the successor poll+ack+facts. Nothing in between is admissible.
    with_facts = (BRIDGE_FACTS_ROUTE in reviewed or BRIDGE_FACTS_START in reviewed)
    count = 3 if with_facts else 2
    _require(
        reviewed.count("location = /api/diary/simulator-bridge/poll {") == 1
        and reviewed.count("location = /api/diary/simulator-bridge/ack {") == 1
        and reviewed.count(BRIDGE_FACTS_ROUTE) == int(with_facts)
        and reviewed.count(BRIDGE_FACTS_START) == int(with_facts)
        and len(re.findall(
            r"location\s*=\s*/api/diary/simulator-bridge/[a-z-]+\s*\{", reviewed,
        )) == count
        and reviewed.count("limit_except GET { deny all; }") == 1 + int(with_facts)
        and reviewed.count("limit_except POST { deny all; }") == 1
        and reviewed.count("proxy_pass http://127.0.0.1:8765;") == count
        and reviewed.count('proxy_set_header Cookie "";') == count
        and reviewed.count('proxy_set_header Authorization "";') == count
        and reviewed.count("client_max_body_size 1k;") == count
        and reviewed.count("proxy_set_header X-BybitScanner-Simulator-Device-Token"
                        " $http_x_bybitscanner_simulator_device_token;")
            == int(with_facts)
        and "auth_request" not in reviewed,
        "reviewed_simulator_bridge_invalid",
    )
    return block


def _legacy_simulator_bridge_from_reviewed(bridge: str) -> str:
    """Exact previous poll/ack bytes, not a substring chosen from VPS state."""
    _require(bridge.count(BRIDGE_FACTS_START) == 1,
             "reviewed_simulator_bridge_invalid")
    legacy = bridge.split(BRIDGE_FACTS_START, 1)[0]
    _require(legacy.count("location = /api/diary/simulator-bridge/poll {") == 1
             and legacy.count("location = /api/diary/simulator-bridge/ack {") == 1
             and BRIDGE_FACTS_ROUTE not in legacy,
             "reviewed_simulator_bridge_invalid")
    return legacy


def _trusted_site(path: Path, *, nginx_dir: Path, uid: int) -> Path:
    # sites-enabled often contains an owner-controlled link to sites-available.
    # Follow only one root-owned link into the same protected Nginx tree.
    try:
        root = nginx_dir.resolve(strict=True)
        _require(path.is_relative_to(root), "untrusted_auth_site_path")
        for directory in (root, path.parent):
            info = directory.lstat()
            _require(directory.is_dir() and not directory.is_symlink()
                     and info.st_uid == uid and not info.st_mode & 0o022,
                     "untrusted_auth_site_directory")
        link = path.lstat()
        _require(link.st_uid == uid, "untrusted_auth_site_owner")
        resolved = path.resolve(strict=True)
        _require(resolved.is_relative_to(root), "auth_site_escapes_nginx_tree")
        for directory in (resolved.parent,):
            info = directory.lstat()
            _require(directory.is_dir() and not directory.is_symlink()
                     and info.st_uid == uid and not info.st_mode & 0o022,
                     "untrusted_auth_site_target_directory")
        info = resolved.lstat()
        _require(stat.S_ISREG(info.st_mode) and info.st_uid == uid
                 and not info.st_mode & 0o022,
                 "untrusted_auth_site_file")
    except (OSError, RuntimeError, ValueError) as exc:
        if isinstance(exc, MainGatewayBlocked):
            raise
        raise MainGatewayBlocked("auth_site_unreadable") from exc
    return resolved


def inspect_authenticated_site(
    *, root: Path, run: Callable = subprocess.run,
    nginx_dir: Path = NGINX_DIR, uid: int = 0,
) -> tuple[Path, bytes, bytes]:
    """Read-only attestation. The caller must perform this *before* STOP."""
    # Before any canonical STOP, attest the already-prepared sealed key for
    # releases whose MAIN service requires it. Never create/replace keys here.
    unit_source = root / "deploy/systemd" / UNIT
    marker = f"LoadCredentialEncrypted={KEY_NAME}:{KEY_PATH}".encode()
    if unit_source.is_file() and marker in unit_source.read_bytes():
        try:
            verify_main_store_key()
        except (OSError, ValueError) as exc:
            raise MainGatewayBlocked("main_store_key_preflight_unproven") from exc
    route = _route_from_source(root)
    bridge = _simulator_bridge_from_source(root)
    dump = _command(["nginx", "-T"], run=run)
    blocks = MARKER.split(dump)
    candidates = []
    count_route = dump.count("location ^~ /api/manual-main/ {")
    _require(count_route <= 1, "duplicate_main_gateway_routes")
    bridge_poll = "location = /api/diary/simulator-bridge/poll {"
    bridge_ack = "location = /api/diary/simulator-bridge/ack {"
    bridge_facts = BRIDGE_FACTS_ROUTE
    with_claim = bridge.endswith(BRIDGE_CLAIM_BLOCK)
    bridge_routes = re.findall(
        r"location\s*=\s*(/api/diary/simulator-bridge/[a-z-]+)\s*\{", dump,
    )
    _require(
        all(path in {
            "/api/diary/simulator-bridge/poll",
            "/api/diary/simulator-bridge/ack",
            "/api/diary/simulator-bridge/facts",
            BRIDGE_CLAIM_PATH,
        } for path in bridge_routes)
        and len(bridge_routes) == len(set(bridge_routes))
        and (with_claim or BRIDGE_CLAIM_PATH not in bridge_routes),
        "duplicate_simulator_bridge_routes",
    )
    for idx in range(1, len(blocks), 2):
        filename, body = blocks[idx], blocks[idx + 1]
        if AUTH_LISTENER in body and "location = /_auth {" in body:
            candidates.append(Path(filename))
    _require(len(candidates) == 1, "authenticated_terminal_site_not_unique")
    site = _trusted_site(candidates[0], nginx_dir=nginx_dir, uid=uid)
    try:
        original = site.read_bytes()
        contents = original.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise MainGatewayBlocked("auth_site_content_unreadable") from exc
    _require(contents.count(AUTH_LISTENER) == 1
             and contents.count(BACKEND_BLOCK) == 1
             and contents.count(AUTH_BLOCK) == 1,
             "authenticated_terminal_security_boundary_changed")
    if route in contents:
        updated = original
    else:
        _require("location ^~ /api/manual-main/" not in contents
                 and count_route == 0, "unknown_main_gateway_route")
        contents = contents.replace(BACKEND_BLOCK, route + BACKEND_BLOCK, 1)
        updated = contents.encode("utf-8")
    # Phase A must never inherit an unreviewed facts route. Phase B may
    # upgrade only byte-identical legacy poll/ack routes, never arbitrary site
    # contents. Installed site and other Nginx files remain protected.
    with_facts = BRIDGE_FACTS_ROUTE in bridge
    if not with_facts:
        _require(bridge_facts not in contents and dump.count(bridge_facts) == 0,
                 "unknown_simulator_bridge_route")
    if bridge not in contents:
        if with_claim:
            predecessor = bridge.removesuffix(BRIDGE_CLAIM_BLOCK)
            _require(contents.count(predecessor) == 1
                     and BRIDGE_CLAIM_PATH not in bridge_routes,
                     "unknown_simulator_bridge_route")
            contents = contents.replace(predecessor, bridge, 1)
        elif with_facts:
            legacy = _legacy_simulator_bridge_from_reviewed(bridge)
            if legacy in contents:
                _require(bridge_facts not in contents
                         and dump.count(bridge_facts) == 0
                         and contents.count(legacy) == 1,
                         "unknown_simulator_bridge_route")
                contents = contents.replace(legacy, bridge, 1)
            else:
                _require(bridge_poll not in contents and bridge_ack not in contents
                         and bridge_facts not in contents
                         and dump.count(bridge_poll) == 0
                         and dump.count(bridge_ack) == 0
                         and dump.count(bridge_facts) == 0,
                         "unknown_simulator_bridge_route")
                contents = contents.replace(BACKEND_BLOCK, bridge + BACKEND_BLOCK, 1)
        else:
            _require(bridge_poll not in contents and bridge_ack not in contents
                     and dump.count(bridge_poll) == 0
                     and dump.count(bridge_ack) == 0,
                     "unknown_simulator_bridge_route")
            contents = contents.replace(BACKEND_BLOCK, bridge + BACKEND_BLOCK, 1)
        updated = contents.encode("utf-8")
    _require(updated.decode("utf-8").count(f"location = {BRIDGE_CLAIM_PATH} {{") == int(with_claim),
             "simulator_bridge_route_not_unique")
    _require(updated.decode("utf-8").count("location ^~ /api/manual-main/ {") == 1,
             "main_gateway_route_not_unique")
    _require(updated.decode("utf-8").count(bridge_poll) == 1
             and updated.decode("utf-8").count(bridge_ack) == 1
             and updated.decode("utf-8").count(bridge_facts) == int(with_facts),
             "simulator_bridge_route_not_unique")
    return site, original, updated


def _unit_attested(root: Path, *, unit_dir: Path, uid: int) -> Path:
    source = root / "deploy/systemd" / UNIT
    installed = unit_dir / UNIT
    try:
        info = installed.lstat()
        raw = installed.read_bytes()
        _require(stat.S_ISREG(info.st_mode) and info.st_uid == uid
                 and not info.st_mode & 0o022
                 and raw == source.read_bytes(), "main_gateway_unit_untrusted")
        _require(b"Restart=no" in raw and b"StateDirectoryMode=0700" in raw
                 and b"User=bybitscanner" in raw
                 and b"ExecStart=/opt/BybitScanner/venv/bin/python -m terminal.runtime.manual_main_read_server" in raw
                 and b"[Install]" not in raw, "main_gateway_unit_contract_changed")
    except OSError as exc:
        raise MainGatewayBlocked("main_gateway_unit_not_installed") from exc
    return installed


def _service_state(*, run: Callable, installed: Path) -> str:
    text = _command([
        "systemctl", "show", UNIT,
        "--property=LoadState,ActiveState,MainPID,FragmentPath,DropInPaths",
        "--no-pager",
    ], run=run)
    state = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    _require(state.get("LoadState") == "loaded"
             and state.get("FragmentPath") == str(installed)
             and not state.get("DropInPaths"), "main_gateway_unit_origin_unproven")
    if state.get("ActiveState") == "active":
        _require(state.get("MainPID", "0").isdigit()
                 and int(state["MainPID"]) > 0, "main_gateway_process_unproven")
        return "active"
    _require(state.get("ActiveState") == "inactive" and state.get("MainPID") == "0",
             "main_gateway_not_stopped")
    return "inactive"


def _read_gateway_health(*, open_url: Callable) -> None:
    try:
        with open_url("http://127.0.0.1:8771/api/manual-main/health", timeout=5) as res:
            data = res.read(4096)
            _require(res.status == 200 and b'"manual_main_read"' in data
                     and b'"trading_enabled":false' in data,
                     "main_gateway_health_invalid")
    except (OSError, URLError, ValueError) as exc:
        raise MainGatewayBlocked("main_gateway_health_unavailable") from exc


def _verify_anonymous_denial(*, open_url: Callable) -> None:
    try:
        with open_url("http://127.0.0.1:8081/api/manual-main/health", timeout=5):
            raise MainGatewayBlocked("main_gateway_auth_bypassed")
    except HTTPError as exc:
        _require(exc.code in (401, 403), "main_gateway_auth_denial_unknown")
    except (OSError, URLError, ValueError) as exc:
        if isinstance(exc, MainGatewayBlocked):
            raise
        raise MainGatewayBlocked("main_gateway_auth_probe_unavailable") from exc



def _main_port_listening(port: int = 8771) -> bool:
    """Read-only socket snapshot; unknown state is a blocker, never 'empty'."""
    try:
        for table in ("/proc/net/tcp", "/proc/net/tcp6"):
            for record in Path(table).read_text().splitlines()[1:]:
                fields = record.split()
                if len(fields) < 4:
                    raise MainGatewayBlocked("main_gateway_socket_snapshot_malformed")
                if fields[3] == "0A" and int(fields[1].rsplit(":", 1)[1], 16) == port:
                    return True
    except (OSError, IndexError, ValueError) as exc:
        if isinstance(exc, MainGatewayBlocked):
            raise
        raise MainGatewayBlocked("main_gateway_socket_snapshot_unavailable") from exc
    return False


def quiesce_gateway_after_paper_stop(
    *, root: Path, run: Callable = subprocess.run,
    unit_dir: Path = UNIT_DIR, uid: int = 0,
    port_listening: Callable = _main_port_listening,
) -> str:
    """Only after the caller proved canonical PAPER shutdown success.

    Stop just the independent read-only MAIN worker once. Never stop PAPER,
    write SQL, signal an unknown PID or guess service shutdown on failure.
    """
    installed = unit_dir / UNIT
    if not installed.exists():
        _require(not installed.is_symlink() and not port_listening(),
                 "unowned_main_gateway_port_or_unit")
        return "READY: MAIN gateway not previously installed"
    _unit_attested(root, unit_dir=unit_dir, uid=uid)
    state = _service_state(run=run, installed=installed)
    if state == "active":
        _command(["systemctl", "stop", UNIT], run=run)
        state = _service_state(run=run, installed=installed)
    _require(state == "inactive" and not port_listening(),
             "main_gateway_shutdown_not_proven")
    return "READY: MAIN read-only gateway quiescent; PAPER stop was independently confirmed"


def prepare_gateway(
    target: str, *, root: Path, run: Callable = subprocess.run,
    open_url: Callable = urlopen, nginx_dir: Path = NGINX_DIR,
    unit_dir: Path = UNIT_DIR, uid: int = 0,
    verify: Callable = verify_release,
) -> str:
    """Idempotently adopt existing gateway after EDITOR_ONLY proof.

    No service stop/restart, no PAPER or Robot API, no credential touches.
    Nginx patch is limited to one confirmed owner-authenticated site and can
    be rolled back to *exact* prior bytes if reload fails.
    """
    _require(len(target) == 40 and all(c in "0123456789abcdef" for c in target),
             "main_gateway_target_invalid")
    _require(verify(root) == target, "main_gateway_release_not_installed")
    installed = _unit_attested(root, unit_dir=unit_dir, uid=uid)
    site, before, updated = inspect_authenticated_site(
        root=root, run=run, nginx_dir=nginx_dir, uid=uid,
    )
    state = _service_state(run=run, installed=installed)
    if state == "inactive":
        _command(["systemctl", "start", UNIT], run=run)
        _require(_service_state(run=run, installed=installed) == "active",
                 "main_gateway_start_unproven")
    # A newly started read-only worker can take a moment to bind port 8771.
    # Reobserve health only; never repeat systemctl start or relax the proof.
    deadline = time.monotonic() + 20.0
    while True:
        try:
            _read_gateway_health(open_url=open_url)
            break
        except MainGatewayBlocked as exc:
            if str(exc) != "main_gateway_health_unavailable" or time.monotonic() >= deadline:
                raise
            time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))
    _require(site.read_bytes() == before, "auth_site_changed_after_preflight")
    if before != updated:
        info = site.stat()
        _atomic_file(site, updated, stat.S_IMODE(info.st_mode), group_gid=info.st_gid)
        phase = "nginx_validation"
        try:
            _command(["nginx", "-t"], run=run)
            phase = "nginx_reload"
            _command(["systemctl", "reload", "nginx"], run=run)
        except MainGatewayBlocked as exc:
            # Restore only our own narrowly proven previous site bytes.
            if site.read_bytes() == updated:
                _atomic_file(site, before, stat.S_IMODE(info.st_mode), group_gid=info.st_gid)
                try:
                    _command(["nginx", "-t"], run=run)
                    _command(["systemctl", "reload", "nginx"], run=run)
                except MainGatewayBlocked:
                    raise MainGatewayBlocked("main_gateway_nginx_rollback_unknown")
            raise MainGatewayBlocked("main_gateway_" + phase + "_unproven") from exc
    _verify_anonymous_denial(open_url=open_url)
    return "READY: MAIN read-only service healthy and owner-authenticated Nginx route proven; PAPER unchanged"

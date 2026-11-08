"""Gateway deployment preflight and failure-safety tests (no VPS actions)."""
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
import os

import pytest

from tools import vps_manual_main_gateway as gateway


def _site(tmp_path: Path, *, content: str | None = None):
    ng = tmp_path / "nginx"
    ng.mkdir(mode=0o700)
    site = ng / "terminal-auth"
    baseline = (
        "server {\n"
        "    listen 127.0.0.1:8081;\n"
        "    location = /_auth {\n        internal;\n"
        "        proxy_pass http://127.0.0.1:8091;\n    }\n"
        "    location /api/ {\n"
        "        auth_request /_auth;\n"
        "        proxy_pass http://127.0.0.1:8765;\n"
        "    }\n"
        "}\n"
    )
    site.write_text(content if content is not None else baseline)
    root = tmp_path / "release"
    source = root / "deploy/terminal_ingress/nginx-authenticated.conf"
    source.parent.mkdir(parents=True)
    authoritative = Path("deploy/terminal_ingress/nginx-authenticated.conf").read_text()
    source.write_text(authoritative)
    unit_source = root / "deploy/systemd" / gateway.UNIT
    unit_source.parent.mkdir(parents=True)
    unit_source.write_text(Path("deploy/systemd", gateway.UNIT).read_text())
    return root, ng, site, baseline


def _runner(site: Path, calls: list, *, fail=()):
    def run(args, **kwargs):
        calls.append(tuple(args))
        if tuple(args) in fail:
            return SimpleNamespace(returncode=1, stdout="", stderr="denied")
        if args == ["nginx", "-T"]:
            return SimpleNamespace(returncode=0, stdout=(
                f"# configuration file {site}:\n" + site.read_text() +
                "\n# configuration file /unrelated/nginx.conf:\nserver { listen 443 ssl; }\n"
            ))
        if args[:2] == ["systemctl", "show"]:
            return SimpleNamespace(returncode=0, stdout=(
                "LoadState=loaded\nActiveState=inactive\nMainPID=0\n"
                f"FragmentPath={site.parent / 'units' / gateway.UNIT}\nDropInPaths=\n"
            ))
        return SimpleNamespace(returncode=0, stdout="")
    return run


def test_preflight_patches_only_protected_site_without_mutation(tmp_path):
    root, ng, site, before = _site(tmp_path)
    calls = []
    found, old, new = gateway.inspect_authenticated_site(
        root=root, run=_runner(site, calls), nginx_dir=ng, uid=os.geteuid(),
    )
    assert found == site
    assert old.decode() == before
    assert b"auth_request /_auth;" in new
    assert b"proxy_pass http://127.0.0.1:8771;" in new
    assert new.count(b"location ^~ /api/manual-main/ {") == 1
    assert site.read_text() == before
    assert calls == [("nginx", "-T")]


def test_preflight_rejects_missing_owner_auth_and_preserves_site(tmp_path):
    root, ng, site, before = _site(tmp_path)
    site.write_text(before.replace("auth_request /_auth;", ""))
    with pytest.raises(gateway.MainGatewayBlocked, match="security_boundary_changed"):
        gateway.inspect_authenticated_site(
            root=root, run=_runner(site, []), nginx_dir=ng, uid=os.geteuid(),
        )
    assert "auth_request /_auth;" not in site.read_text()


def test_preflight_rejects_unknown_existing_manual_route(tmp_path):
    root, ng, site, before = _site(tmp_path)
    malicious = before.replace("    location /api/ {",
        "    location ^~ /api/manual-main/ { proxy_pass http://127.0.0.1:8771; }\n"
        "    location /api/ {")
    site.write_text(malicious)
    with pytest.raises(gateway.MainGatewayBlocked, match="unknown_main_gateway_route"):
        gateway.inspect_authenticated_site(
            root=root, run=_runner(site, []), nginx_dir=ng, uid=os.geteuid(),
        )
    assert site.read_text() == malicious


def test_preflight_refuses_site_escaping_trusted_nginx_tree(tmp_path):
    root, ng, site, before = _site(tmp_path)
    outside = tmp_path / "owner"
    outside.write_text(before)
    site.unlink()
    site.symlink_to(outside)
    with pytest.raises(gateway.MainGatewayBlocked, match="auth_site_escapes_nginx_tree"):
        gateway.inspect_authenticated_site(
            root=root, run=_runner(site, []), nginx_dir=ng, uid=os.geteuid(),
        )
    assert outside.read_text() == before


def test_preflight_existing_exact_route_is_idempotent(tmp_path):
    root, ng, site, before = _site(tmp_path)
    run = _runner(site, [])
    _, _, new = gateway.inspect_authenticated_site(
        root=root, run=run, nginx_dir=ng, uid=os.geteuid(),
    )
    site.write_bytes(new)
    _, old, same = gateway.inspect_authenticated_site(
        root=root, run=run, nginx_dir=ng, uid=os.geteuid(),
    )
    assert old == same


def test_protected_gateway_unit_requires_exact_installed_bytes(tmp_path):
    root, ng, site, _ = _site(tmp_path)
    unit_dir = ng / "units"
    unit_dir.mkdir()
    target = unit_dir / gateway.UNIT
    target.write_text("unrelated owner service")
    with pytest.raises(gateway.MainGatewayBlocked, match="main_gateway_unit_untrusted"):
        gateway._unit_attested(root, unit_dir=unit_dir, uid=os.geteuid())
    assert target.read_text() == "unrelated owner service"


def test_anonymous_route_must_fail_with_401_or_403():
    def allow(*args, **kwargs):
        return SimpleNamespace(__enter__=lambda x: x)
    with pytest.raises(gateway.MainGatewayBlocked, match="auth_bypassed"):
        class Open:
            def __enter__(self):
                return self
            def __exit__(self, *_):
                pass
        gateway._verify_anonymous_denial(open_url=lambda *_args, **_kwargs: Open())
    gateway._verify_anonymous_denial(
        open_url=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            HTTPError("http://127.0.0.1", 401, "Unauthorized", {}, None)),
    )

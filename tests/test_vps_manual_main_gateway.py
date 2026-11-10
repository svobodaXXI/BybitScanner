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



def test_quiesce_existing_main_only_after_proven_paper_stop(tmp_path):
    root, ng, _site_path, _old = _site(tmp_path)
    unit_dir = ng / "units"
    unit_dir.mkdir()
    installed = unit_dir / gateway.UNIT
    installed.write_bytes((root / "deploy/systemd" / gateway.UNIT).read_bytes())
    active = [True]
    calls = []

    def run(argv, **_kwargs):
        calls.append(tuple(argv))
        if argv[:2] == ["systemctl", "show"]:
            return SimpleNamespace(returncode=0, stdout=(
                "LoadState=loaded\n"
                f"ActiveState={'active' if active[0] else 'inactive'}\n"
                f"MainPID={'123' if active[0] else '0'}\n"
                f"FragmentPath={installed}\nDropInPaths=\n"
            ))
        if argv == ["systemctl", "stop", gateway.UNIT]:
            active[0] = False
        return SimpleNamespace(returncode=0, stdout="")

    result = gateway.quiesce_gateway_after_paper_stop(
        root=root, unit_dir=unit_dir, run=run, uid=os.geteuid(),
        port_listening=lambda: active[0],
    )
    assert result.startswith("READY:")
    assert calls.count(("systemctl", "stop", gateway.UNIT)) == 1
    assert active == [False]
    gateway.quiesce_gateway_after_paper_stop(
        root=root, unit_dir=unit_dir, run=run, uid=os.geteuid(),
        port_listening=lambda: active[0],
    )
    assert calls.count(("systemctl", "stop", gateway.UNIT)) == 1


def test_unproven_main_gateway_stop_is_not_retried(tmp_path):
    root, ng, _site_path, _old = _site(tmp_path)
    unit_dir = ng / "units"
    unit_dir.mkdir()
    installed = unit_dir / gateway.UNIT
    installed.write_bytes((root / "deploy/systemd" / gateway.UNIT).read_bytes())
    calls = []

    def run(argv, **_kwargs):
        calls.append(tuple(argv))
        if argv[:2] == ["systemctl", "show"]:
            return SimpleNamespace(returncode=0, stdout=(
                "LoadState=loaded\nActiveState=active\nMainPID=123\n"
                f"FragmentPath={installed}\nDropInPaths=\n"
            ))
        return SimpleNamespace(returncode=1, stdout="")

    with pytest.raises(gateway.MainGatewayBlocked, match="gateway_command_failed"):
        gateway.quiesce_gateway_after_paper_stop(
            root=root, unit_dir=unit_dir, run=run, uid=os.geteuid(),
            port_listening=lambda: True,
        )
    assert calls.count(("systemctl", "stop", gateway.UNIT)) == 1



class _GatewayHealth:
    status = 200
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        return False
    def read(self, *_args):
        return b'{"ok":true,"component":"manual_main_read","trading_enabled":false}'


def _gateway_deploy_fixture(tmp_path, *, fail_nginx_test=False):
    root, ng, site, original = _site(tmp_path)
    unit_dir = ng / "units"
    unit_dir.mkdir()
    installed = unit_dir / gateway.UNIT
    installed.write_bytes((root / "deploy/systemd" / gateway.UNIT).read_bytes())
    active = [False]
    calls = []
    validations = [0]

    def runner(argv, **_kwargs):
        calls.append(tuple(argv))
        if argv == ["nginx", "-T"]:
            return SimpleNamespace(returncode=0, stdout=
                f"# configuration file {site}:\n" + site.read_text())
        if argv[:2] == ["systemctl", "show"]:
            return SimpleNamespace(returncode=0, stdout=(
                "LoadState=loaded\n"
                f"ActiveState={'active' if active[0] else 'inactive'}\n"
                f"MainPID={'123' if active[0] else '0'}\n"
                f"FragmentPath={installed}\nDropInPaths=\n"
            ))
        if argv == ["systemctl", "start", gateway.UNIT]:
            active[0] = True
        if argv == ["nginx", "-t"]:
            validations[0] += 1
            if fail_nginx_test and validations[0] == 1:
                return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(returncode=0, stdout="")

    def open_url(url, **_kwargs):
        if url == "http://127.0.0.1:8771/api/manual-main/health":
            return _GatewayHealth()
        if url == "http://127.0.0.1:8081/api/manual-main/health":
            raise HTTPError(url, 401, "Unauthorized", {}, None)
        raise AssertionError("Unexpected URL " + url)

    return dict(root=root, run=runner, open_url=open_url, nginx_dir=ng,
                unit_dir=unit_dir, uid=os.geteuid(),
                verify=lambda _path: "a" * 40), site, original, calls


def test_gateway_install_succeeds_once_and_remains_idempotent(tmp_path):
    params, site, original, calls = _gateway_deploy_fixture(tmp_path)
    assert gateway.prepare_gateway("a" * 40, **params).startswith("READY:")
    assert site.read_text() != original
    assert "auth_request /_auth;" in site.read_text()
    assert calls.count(("systemctl", "start", gateway.UNIT)) == 1
    assert calls.count(("systemctl", "reload", "nginx")) == 1
    assert gateway.prepare_gateway("a" * 40, **params).startswith("READY:")
    assert calls.count(("systemctl", "start", gateway.UNIT)) == 1
    assert calls.count(("systemctl", "reload", "nginx")) == 1
    assert not any("paper-backend" in " ".join(call) for call in calls)


def test_nginx_validation_failure_restores_exact_prior_auth_site(tmp_path):
    params, site, original, calls = _gateway_deploy_fixture(
        tmp_path, fail_nginx_test=True,
    )
    with pytest.raises(gateway.MainGatewayBlocked, match="nginx_validation_unproven"):
        gateway.prepare_gateway("a" * 40, **params)
    assert site.read_text() == original
    assert calls.count(("systemctl", "start", gateway.UNIT)) == 1
    assert calls.count(("nginx", "-t")) == 2
    assert calls.count(("systemctl", "reload", "nginx")) == 1
    assert not any("paper-backend" in " ".join(call) for call in calls)


def test_nginx_reload_failure_preserves_specific_phase_and_restores_site(tmp_path):
    params, site, original, calls = _gateway_deploy_fixture(tmp_path)
    run = params["run"]
    failed_once = [False]

    def failed_reload(argv, **kwargs):
        if argv == ["systemctl", "reload", "nginx"] and not failed_once[0]:
            failed_once[0] = True
            calls.append(tuple(argv))
            return SimpleNamespace(returncode=1, stdout="")
        return run(argv, **kwargs)

    params["run"] = failed_reload
    with pytest.raises(gateway.MainGatewayBlocked, match="nginx_reload_unproven"):
        gateway.prepare_gateway("a" * 40, **params)
    assert site.read_text() == original
    assert calls.count(("systemctl", "reload", "nginx")) == 2
    assert not any("paper-backend" in " ".join(call) for call in calls)


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


def test_main_gateway_warmup_rechecks_health_without_restarting(tmp_path, monkeypatch):
    from urllib.error import URLError
    params, _site_path, _original, calls = _gateway_deploy_fixture(tmp_path)
    real_open = params["open_url"]
    health_checks = [0]

    def warming(url, **kwargs):
        if url == "http://127.0.0.1:8771/api/manual-main/health":
            health_checks[0] += 1
            if health_checks[0] == 1:
                raise URLError("worker still binding")
        return real_open(url, **kwargs)

    monkeypatch.setattr(gateway.time, "sleep", lambda _: None)
    params["open_url"] = warming
    assert gateway.prepare_gateway("a" * 40, **params).startswith("READY:")
    assert health_checks == [2]
    assert calls.count(("systemctl", "start", gateway.UNIT)) == 1
    assert calls.count(("systemctl", "reload", "nginx")) == 1

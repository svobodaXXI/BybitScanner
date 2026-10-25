"""Real-systemd probe of the #627/#628 stop semantics with dummy services (CI runner only, as root).

The dummy units are generated from the repository's own unit files: every stop-related key
(KillSignal, SendSIGKILL, KillMode, Restart, NoNewPrivileges, PrivateTmp) is kept verbatim; only the
programs (ExecStart/ExecStop), the user, environment and state directory are replaced by stand-ins,
and TimeoutStopSec is shortened. No BybitScanner runtime, PAPER DB, network or Telegram is involved.

Scenarios:
  A  backend, ExecStop fails (safe-stop BLOCKED)  -> protected process must survive; unit failed(timeout)
  B  backend, ExecStop succeeds (safe-stop done)  -> process exits; unit inactive, Result=success
  C  Telegram worker exits after launching the real tools.stop_robot_runtime.launch_detached helper
     -> with the repository KillMode=process the helper survives and finishes;
  C' control: same with KillMode=control-group -> the helper is reaped (why #627 sets KillMode=process)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import time

REPO = Path(__file__).resolve().parents[1]
WORK = Path("/run/bbs-probe")
PY = sys.executable
TIMEOUT_STOP = 6
RESULTS: dict[str, object] = {}


def sh(*argv: str, check: bool = True) -> subprocess.CompletedProcess:
    out = subprocess.run(list(argv), capture_output=True, text=True)
    if check and out.returncode != 0:
        raise SystemExit(f"{argv} failed: {out.stdout}{out.stderr}")
    return out


def sections(text: str) -> dict[str, dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = found.setdefault(line[1:-1], {})
        elif current is not None and "=" in line:
            key, value = line.split("=", 1)
            current[key.strip()] = value.strip()
    return found


KEEP = ("Type", "Restart", "KillSignal", "SendSIGKILL", "KillMode", "NoNewPrivileges", "PrivateTmp")


def dummy_unit(repo_unit: str, *, exec_start: str, exec_stop: str | None, kill_mode: str | None = None) -> tuple[str, dict]:
    service = sections((REPO / "deploy/systemd" / repo_unit).read_text(encoding="utf-8"))["Service"]
    kept = {key: service[key] for key in KEEP if key in service}
    if kill_mode is not None:
        kept["KillMode"] = kill_mode
    lines = ["[Unit]", f"Description=probe of {repo_unit}", "", "[Service]"]
    lines += [f"{k}={v}" for k, v in kept.items()]
    lines += [f"ExecStart={exec_start}", f"WorkingDirectory={WORK}", f"TimeoutStopSec={TIMEOUT_STOP}"]
    if exec_stop:
        lines.append(f"ExecStop={exec_stop}")
    return "\n".join(lines) + "\n", kept


def install(name: str, text: str) -> None:
    Path(f"/etc/systemd/system/{name}").write_text(text, encoding="utf-8")
    sh("systemctl", "daemon-reload")


def show(unit: str) -> dict[str, str]:
    out = sh("systemctl", "show", unit, "-p", "ActiveState,SubState,Result,MainPID,ExecMainStatus", check=False).stdout
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def wait_for(predicate, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.2)
    return bool(predicate())


def backend_main() -> Path:
    path = WORK / "backend_main.py"
    path.write_text(textwrap.dedent(f"""
        import os, pathlib, time
        work = pathlib.Path({str(WORK)!r})
        (work / "backend.pid").write_text(str(os.getpid()))
        while not (work / "stop-request").exists():   # SIGCONT does nothing to this loop
            time.sleep(0.2)
    """), encoding="utf-8")
    return path


def scenario_backend(name: str, exec_stop: str) -> dict[str, object]:
    for leftover in ("stop-request", "backend.pid"):
        (WORK / leftover).unlink(missing_ok=True)
    unit = f"bbs-probe-{name}.service"
    text, kept = dummy_unit("bybitscanner-paper-backend.service",
                            exec_start=f"{PY} {backend_main()}", exec_stop=exec_stop)
    install(unit, text)
    sh("systemctl", "start", unit)
    assert wait_for(lambda: (WORK / "backend.pid").exists(), 10), "dummy backend did not start"
    pid = int((WORK / "backend.pid").read_text())
    started = time.monotonic()
    stop = sh("systemctl", "stop", unit, check=False)
    elapsed = round(time.monotonic() - started, 1)
    state = show(unit)
    result = {"kept_stop_keys": kept, "stop_rc": stop.returncode, "stop_seconds": elapsed,
              "unit": state, "protected_process_alive": alive(pid)}
    journal = sh("journalctl", "-u", unit, "--no-pager", "-o", "cat", check=False).stdout.strip().splitlines()
    result["journal_tail"] = journal[-6:]
    if alive(pid):                                    # cleanup of the probe only
        (WORK / "stop-request").touch()
        wait_for(lambda: not alive(pid), 10)
    sh("systemctl", "reset-failed", unit, check=False)
    return result


def fake_root() -> Path:
    root = WORK / "fake_root"
    (root / "tools").mkdir(parents=True, exist_ok=True)
    (root / "tools" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tools" / "stop_robot_runtime.py").write_text(textwrap.dedent(f"""
        import os, pathlib, sys, time
        work = pathlib.Path({str(WORK)!r})
        (work / "helper.started").write_text(f"{{os.getpid()}} sid={{os.getsid(0)}} argv={{sys.argv[1:]}}")
        time.sleep(4)                                  # still running after the worker has exited
        (work / "helper.finished").write_text("done")
    """), encoding="utf-8")
    return root


def scenario_telegram(name: str, kill_mode: str | None) -> dict[str, object]:
    for leftover in ("helper.started", "helper.finished", "worker.pid"):
        (WORK / leftover).unlink(missing_ok=True)
    root = fake_root()
    worker = WORK / "worker_main.py"
    worker.write_text(textwrap.dedent(f"""
        import os, pathlib, sys, time
        sys.path.insert(0, {str(REPO)!r})
        from tools.stop_robot_runtime import launch_detached     # the real #627 implementation
        work = pathlib.Path({str(WORK)!r})
        (work / "worker.pid").write_text(str(os.getpid()))
        launch_detached("all", notify_chat=None, root=pathlib.Path({str(root)!r}))
        time.sleep(1)
        # the worker now exits, as the Telegram worker does after its own canonical shutdown
    """), encoding="utf-8")
    unit = f"bbs-probe-{name}.service"
    text, kept = dummy_unit("bybitscanner-telegram.service", exec_start=f"{PY} {worker}", exec_stop=None,
                            kill_mode=kill_mode)
    install(unit, text)
    sh("systemctl", "start", unit)
    worker_done = wait_for(lambda: show(unit).get("ActiveState") in {"inactive", "failed"}, 15)
    helper_started = wait_for(lambda: (WORK / "helper.started").exists(), 5)
    helper_finished = wait_for(lambda: (WORK / "helper.finished").exists(), 10)
    return {"kept_stop_keys": kept, "worker_exited": worker_done, "unit": show(unit),
            "helper_started": helper_started,
            "helper_info": (WORK / "helper.started").read_text() if helper_started else None,
            "helper_finished_after_worker_exit": helper_finished}


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    RESULTS["A_blocked_safe_stop"] = scenario_backend("blocked", "/bin/sh -c 'echo STOP BLOCKED: probe position open; exit 1'")
    RESULTS["B_successful_safe_stop"] = scenario_backend(
        "graceful", f"/bin/sh -c 'touch {WORK}/stop-request; while kill -0 $MAINPID 2>/dev/null; do sleep 0.2; done; echo Runtime STOPPED.'")
    RESULTS["C_telegram_helper_repo_killmode"] = scenario_telegram("tg-repo", None)
    RESULTS["C_control_killmode_control_group"] = scenario_telegram("tg-cgroup", "control-group")
    print(json.dumps(RESULTS, indent=2))

    a, b = RESULTS["A_blocked_safe_stop"], RESULTS["B_successful_safe_stop"]
    c, cc = RESULTS["C_telegram_helper_repo_killmode"], RESULTS["C_control_killmode_control_group"]
    checks = {
        "A: protected process survives a blocked ExecStop": a["protected_process_alive"] is True,
        "A: unit reports failure (not a clean stop)": a["unit"].get("Result") != "success",
        "A: no SIGKILL/SIGINT used (repo keys kept)": a["kept_stop_keys"].get("KillSignal") == "SIGCONT"
                                                       and a["kept_stop_keys"].get("SendSIGKILL") == "no",
        "B: process gone after successful ExecStop": b["protected_process_alive"] is False,
        "B: unit inactive with Result=success": b["unit"].get("ActiveState") == "inactive"
                                                and b["unit"].get("Result") == "success",
        "C: repo KillMode is process": c["kept_stop_keys"].get("KillMode") == "process",
        "C: detached helper outlives the Telegram worker": c["helper_finished_after_worker_exit"] is True,
        "C': control-group kill reaps the helper (control)": cc["helper_finished_after_worker_exit"] is False,
    }
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

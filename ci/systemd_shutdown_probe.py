"""Real-systemd probe of the #627/#628 stop semantics with dummy services (CI runner only, as root).

The dummy units are generated from the repository's own unit files: every stop-related key
(KillSignal, SendSIGKILL, KillMode, Restart, NoNewPrivileges, PrivateTmp) is kept verbatim; only the
programs (ExecStart/ExecStop), the user, environment and state directory are replaced by stand-ins,
and TimeoutStopSec is shortened. No BybitScanner runtime, PAPER DB, network or Telegram is involved.

Scenarios (backend dummy unit keeps the repository RefuseManualStop/KillSignal/SendSIGKILL):
  A  manual `systemctl stop` / `restart` -> refused; unit stays active, same MainPID, process alive
  B  canonical safe-stop (the tool makes the backend exit by itself) -> unit inactive, Result=success
  D  systemd-initiated stop (Conflicts= job, as at host shutdown) with ExecStop BLOCKED
     -> the protected process is not killed (SIGCONT only, SIGKILL skipped)
  D2 systemd-initiated stop with ExecStop succeeding -> unit inactive, Result=success
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
KEEP_UNIT = ("RefuseManualStop",)


def dummy_unit(repo_unit: str, *, exec_start: str, exec_stop: str | None, kill_mode: str | None = None) -> tuple[str, dict]:
    parsed = sections((REPO / "deploy/systemd" / repo_unit).read_text(encoding="utf-8"))
    service, unit_section = parsed["Service"], parsed.get("Unit", {})
    kept = {key: service[key] for key in KEEP if key in service}
    kept_unit = {key: unit_section[key] for key in KEEP_UNIT if key in unit_section}
    if kill_mode is not None:
        kept["KillMode"] = kill_mode
    lines = ["[Unit]", f"Description=probe of {repo_unit}", *[f"{k}={v}" for k, v in kept_unit.items()],
             "", "[Service]"]
    kept = {**kept_unit, **kept}
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


def start_backend(name: str, exec_stop: str) -> tuple[str, int, dict]:
    for leftover in ("stop-request", "backend.pid"):
        (WORK / leftover).unlink(missing_ok=True)
    unit = f"bbs-probe-{name}.service"
    text, kept = dummy_unit("bybitscanner-paper-backend.service",
                            exec_start=f"{PY} {backend_main()}", exec_stop=exec_stop)
    install(unit, text)
    sh("systemctl", "start", unit)
    assert wait_for(lambda: (WORK / "backend.pid").exists(), 10), "dummy backend did not start"
    return unit, int((WORK / "backend.pid").read_text()), kept


def journal(unit: str) -> list[str]:
    return sh("journalctl", "-u", unit, "--no-pager", "-o", "cat", check=False).stdout.strip().splitlines()[-6:]


def cleanup(unit: str, pid: int) -> None:
    if alive(pid):                                    # probe cleanup only: the dummy exits by itself
        (WORK / "stop-request").touch()
        wait_for(lambda: not alive(pid), 10)
    sh("systemctl", "reset-failed", unit, check=False)


BLOCKED = "/bin/sh -c 'echo STOP BLOCKED: probe position open; exit 1'"
GRACEFUL = ("/bin/sh -c 'touch " + str(WORK) + "/stop-request; "
            "while kill -0 $MAINPID 2>/dev/null; do sleep 0.2; done; echo Runtime STOPPED.'")


def scenario_manual_stop_refused() -> dict[str, object]:
    unit, pid, kept = start_backend("manual", BLOCKED)
    stop = sh("systemctl", "stop", unit, check=False)
    restart = sh("systemctl", "restart", unit, check=False)
    time.sleep(1)
    state = show(unit)
    result = {"kept_stop_keys": kept, "stop_rc": stop.returncode, "stop_err": stop.stderr.strip(),
              "restart_rc": restart.returncode, "unit": state,
              "main_pid_unchanged": state.get("MainPID") == str(pid), "protected_process_alive": alive(pid)}
    cleanup(unit, pid)
    return result


def scenario_canonical_safe_stop() -> dict[str, object]:
    unit, pid, kept = start_backend("canonical", BLOCKED)
    (WORK / "stop-request").touch()                   # what /api/runtime/shutdown does: exit by itself
    gone = wait_for(lambda: not alive(pid), 10)
    wait_for(lambda: show(unit).get("ActiveState") == "inactive", 10)
    result = {"kept_stop_keys": kept, "process_exited": gone, "unit": show(unit), "journal_tail": journal(unit)}
    cleanup(unit, pid)
    return result


def scenario_systemd_initiated(name: str, exec_stop: str) -> dict[str, object]:
    unit, pid, kept = start_backend(name, exec_stop)
    conflict = f"bbs-probe-{name}-conflict.service"
    install(conflict, f"[Unit]\nConflicts={unit}\n\n[Service]\nType=oneshot\nExecStart=/bin/true\n")
    started = time.monotonic()
    sh("systemctl", "start", conflict, check=False)   # enqueues a non-manual stop job for the backend
    wait_for(lambda: show(unit).get("ActiveState") in {"inactive", "failed"}, 3 * TIMEOUT_STOP + 5)
    result = {"kept_stop_keys": kept, "seconds": round(time.monotonic() - started, 1), "unit": show(unit),
              "protected_process_alive": alive(pid), "journal_tail": journal(unit)}
    cleanup(unit, pid)
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
    RESULTS["A_manual_stop_refused"] = scenario_manual_stop_refused()
    RESULTS["B_canonical_safe_stop"] = scenario_canonical_safe_stop()
    RESULTS["D_systemd_stop_blocked"] = scenario_systemd_initiated("sysblocked", BLOCKED)
    RESULTS["D2_systemd_stop_succeeds"] = scenario_systemd_initiated("sysgraceful", GRACEFUL)
    RESULTS["C_telegram_helper_repo_killmode"] = scenario_telegram("tg-repo", None)
    RESULTS["C_control_killmode_control_group"] = scenario_telegram("tg-cgroup", "control-group")
    print(json.dumps(RESULTS, indent=2))

    a, b = RESULTS["A_manual_stop_refused"], RESULTS["B_canonical_safe_stop"]
    d, d2 = RESULTS["D_systemd_stop_blocked"], RESULTS["D2_systemd_stop_succeeds"]
    c, cc = RESULTS["C_telegram_helper_repo_killmode"], RESULTS["C_control_killmode_control_group"]
    checks = {
        "A: repo RefuseManualStop=yes kept": a["kept_stop_keys"].get("RefuseManualStop") == "yes",
        "A: manual systemctl stop is refused": a["stop_rc"] != 0,
        "A: manual systemctl restart is refused": a["restart_rc"] != 0,
        "A: unit stays active with the same MainPID (still managed)": a["unit"].get("ActiveState") == "active"
                                                                       and a["main_pid_unchanged"] is True,
        "A: protected process alive": a["protected_process_alive"] is True,
        "B: canonical safe-stop ends the process": b["process_exited"] is True,
        "B: unit inactive with Result=success": b["unit"].get("ActiveState") == "inactive"
                                                and b["unit"].get("Result") == "success",
        "D: systemd-initiated stop with blocked ExecStop never kills the process": d["protected_process_alive"] is True,
        "D: no SIGKILL/SIGINT used (repo keys kept)": d["kept_stop_keys"].get("KillSignal") == "SIGCONT"
                                                       and d["kept_stop_keys"].get("SendSIGKILL") == "no",
        "D2: systemd-initiated stop with successful ExecStop is clean": d2["protected_process_alive"] is False
                                                                         and d2["unit"].get("Result") == "success",
        "C: repo KillMode is process": c["kept_stop_keys"].get("KillMode") == "process",
        "C: detached helper outlives the Telegram worker": c["helper_finished_after_worker_exit"] is True,
        "C': control-group kill reaps the helper (control)": cc["helper_finished_after_worker_exit"] is False,
    }
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

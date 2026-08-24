"""Run minimal checks for exact task paths and record a PASS receipt."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from .workflow import Git, compact, fingerprints, normalize_task_paths, receipt_path, repository_root, require_ok


def _run_check(root: Path, label: str, command: Sequence[str]) -> tuple[str, bool, str]:
    result = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
    detail = (result.stderr or result.stdout).strip().replace("\n", " ")
    return label, result.returncode == 0, detail


def verify(path_values: Sequence[str], *, git: Git | None = None) -> tuple[bool, str]:
    probe = git or Git(Path.cwd())
    checks: list[dict[str, object]] = []
    try:
        root = repository_root(probe)
        active_git = git or Git(root)
        paths, files = normalize_task_paths(root, path_values)
        branch = require_ok(active_git.run("branch", "--show-current"), "branch discovery")
        head = require_ok(active_git.run("rev-parse", "HEAD"), "HEAD discovery")
        if not branch:
            raise RuntimeError("detached HEAD is not supported")
        python_files = [str(root / p) for p in files if p.endswith(".py")]
        test_files = [p for p in files if p.startswith("tests/") and p.endswith(".py")]
        if python_files:
            label, passed, detail = _run_check(root, "python-compile", (sys.executable, "-m", "py_compile", *python_files))
            checks.append({"name": label, "status": "PASS" if passed else "FAIL", "detail": detail})
        for test_file in test_files:
            label = f"focused-test:{Path(test_file).name}"
            module = test_file[:-3].replace("/", ".")
            name, passed, detail = _run_check(root, label, (sys.executable, "-m", "unittest", module))
            checks.append({"name": name, "status": "PASS" if passed else "FAIL", "detail": detail})
        diff = active_git.run("diff", "--check", "--", *paths)
        checks.append({"name": "diff-check", "status": "PASS" if diff.returncode == 0 else "FAIL", "detail": (diff.stderr or diff.stdout).strip()})
        failed = [str(item["name"]) for item in checks if item["status"] != "PASS"]
        if failed:
            return False, compact("FAIL", paths, [str(x["name"]) for x in checks], failed, ())
        receipt = {
            "schema": 1,
            "status": "PASS",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "branch": branch,
            "head": head,
            "task_paths": paths,
            "files": files,
            "fingerprints": fingerprints(root, files),
            "checks": checks,
        }
        target = receipt_path(root, active_git)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return True, compact("PASS", paths, [str(x["name"]) for x in checks], (), ())
    except (OSError, RuntimeError, ValueError) as exc:
        return False, compact("FAIL", list(path_values), [str(x["name"]) for x in checks], (), (str(exc),))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", action="append", required=True, dest="paths")
    args = parser.parse_args(argv)
    passed, output = verify(args.paths)
    print(output)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

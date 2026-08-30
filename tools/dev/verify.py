"""Run minimal checks for exact task paths and record a PASS receipt."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from .task_transaction import candidate_root, derive_candidate, inspect, load_transaction
from .workflow import (
    Git, compact, fingerprints, index_snapshot, normalize_task_paths, receipt_path,
    repository_root, require_ok,
)


def _run_check(root: Path, label: str, command: Sequence[str]) -> tuple[str, bool, str]:
    result = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
    detail = (result.stderr or result.stdout).strip().replace("\n", " ")
    return label, result.returncode == 0, detail


def verify(
    path_values: Sequence[str], *, git: Git | None = None, transaction_id: str | None = None
) -> tuple[bool, str]:
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
        transaction_receipt = None
        transaction_post_fingerprints = None
        transaction_index = None
        if transaction_id:
            transaction_index = index_snapshot(root, active_git)
            transaction_post_fingerprints = fingerprints(root, files)
            _, metadata = load_transaction(transaction_id, git=active_git)
            if metadata["scope"] != paths:
                raise RuntimeError("transaction scope does not exactly match verification paths")
            state = inspect(transaction_id, git=active_git)
            if state["status"] != "OK":
                raise RuntimeError("transaction is stale: " + ", ".join(state["blockers"]))
            proofs = derive_candidate(transaction_id, git=active_git)
            if set(proofs) != set(files) or any(proof.status != "PASS" for proof in proofs.values()):
                raise RuntimeError("task-delta or inverse proof did not PASS for every transaction file")
            candidates = candidate_root(transaction_id, git=active_git)
            all_candidate_fingerprints = fingerprints(candidates, files)
            if any(value["state"] != "file" for value in all_candidate_fingerprints.values()):
                raise RuntimeError("transaction candidate is incomplete")
            baseline_hashes = {record["path"]: record["head_sha256"] for record in metadata["files"]}
            candidate_files = [
                path for path in files
                if all_candidate_fingerprints[path]["sha256"] != baseline_hashes[path]
            ]
            if not candidate_files:
                raise RuntimeError("transaction has no task-only candidate changes")
            candidate_fingerprints = {
                path: all_candidate_fingerprints[path] for path in candidate_files
            }
            transaction_receipt = {
                "id": transaction_id,
                "branch": metadata["branch"],
                "head": metadata["head"],
                "task_paths": metadata["scope"],
                "candidate_files": candidate_files,
                "candidate_fingerprints": candidate_fingerprints,
                "proofs": {
                    path: {"status": proof.status, "detail": proof.detail}
                    for path, proof in sorted(proofs.items())
                },
            }
            checks.append({"name": "task-delta-proof", "status": "PASS", "detail": ""})
            checks.append({"name": "inverse-proof", "status": "PASS", "detail": ""})
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
        contract_prefixes = (
            "terminal/api/", "terminal/application/pretrade_guard.py",
            "terminal/domain/models.py",
            "terminal/runtime/paper_http_server.py", "terminal/runtime/paper_runtime.py",
            "terminal/frontend/src/contracts/", "terminal/frontend/src/components/ModePanel",
            "tools/dev/contract_consistency.py", "tests/test_contract_consistency.py",
        )
        if any(path.startswith(contract_prefixes) for path in paths):
            label, passed, detail = _run_check(
                root, "trading-contract-consistency",
                (sys.executable, "-m", "tools.dev.contract_consistency"),
            )
            checks.append({"name": label, "status": "PASS" if passed else "FAIL", "detail": detail})
        diff = active_git.run("diff", "--check", "--", *paths)
        checks.append({"name": "diff-check", "status": "PASS" if diff.returncode == 0 else "FAIL", "detail": (diff.stderr or diff.stdout).strip()})
        failed = [str(item["name"]) for item in checks if item["status"] != "PASS"]
        if failed:
            return False, compact("FAIL", paths, [str(x["name"]) for x in checks], failed, ())
        if transaction_receipt:
            state = inspect(transaction_id or "", git=active_git)
            if state["status"] != "OK":
                raise RuntimeError("transaction became stale during verification")
            if fingerprints(root, files) != transaction_post_fingerprints:
                raise RuntimeError("transaction task-file content changed during verification")
            if index_snapshot(root, active_git) != transaction_index:
                raise RuntimeError("real Git index changed during transaction verification")
            checks.append({"name": "real-index-unchanged", "status": "PASS", "detail": ""})
        receipt = {
            "schema": 2 if transaction_receipt else 1,
            "status": "PASS",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "branch": branch,
            "head": head,
            "task_paths": paths,
            "files": files,
            "fingerprints": transaction_post_fingerprints or fingerprints(root, files),
            "checks": checks,
        }
        if transaction_receipt:
            receipt["transaction"] = transaction_receipt
        target = receipt_path(root, active_git)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return True, compact("PASS", paths, [str(x["name"]) for x in checks], (), ())
    except (OSError, RuntimeError, ValueError) as exc:
        return False, compact("FAIL", list(path_values), [str(x["name"]) for x in checks], (), (str(exc),))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", action="append", required=True, dest="paths")
    parser.add_argument("--transaction", dest="transaction_id")
    args = parser.parse_args(argv)
    passed, output = verify(args.paths, transaction_id=args.transaction_id)
    print(output)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

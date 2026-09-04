"""Run minimal checks for exact task paths and record a PASS receipt."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from .task_transaction import (
    candidate_root, candidate_tree, create_isolated_worktree, derive_candidate, inspect,
    load_transaction, remove_isolated_worktree,
)
from .workflow import (
    Git, compact, fingerprints, index_snapshot, normalize_task_paths, receipt_path,
    repository_root, require_ok, resolve_inside,
)


def _run_check(root: Path, label: str, command: Sequence[str]) -> tuple[str, bool, str]:
    result = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
    detail = (result.stderr or result.stdout).strip().replace("\n", " ")
    return label, result.returncode == 0, detail


def _link_frontend_dependencies(root: Path, verification_root: Path) -> bool:
    source = root / "terminal" / "frontend" / "node_modules"
    target = verification_root / "terminal" / "frontend" / "node_modules"
    if not source.is_dir() or target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.symlink_to(source, target_is_directory=True)
    except OSError as exc:
        if os.name != "nt":
            raise RuntimeError(f"frontend dependency link creation failed at {target}: {exc}") from exc
        completed = subprocess.run(
            ("cmd.exe", "/d", "/c", "mklink", "/J", str(target), str(source)),
            text=True, capture_output=True, check=False,
        )
        if completed.returncode:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(
                f"frontend dependency link creation failed at {target}"
                + (f": {detail}" if detail else "")
            ) from exc
    return True


def _unlink_frontend_dependencies(verification_root: Path) -> None:
    target = verification_root / "terminal" / "frontend" / "node_modules"
    if target.is_symlink():
        target.unlink()
    elif os.name == "nt" and target.exists():
        os.rmdir(target)


def verify(
    path_values: Sequence[str], *, git: Git | None = None, transaction_id: str | None = None,
    additional_commands: Sequence[dict[str, object]] = (),
) -> tuple[bool, str]:
    probe = git or Git(Path.cwd())
    checks: list[dict[str, object]] = []
    isolated_path: Path | None = None
    frontend_dependencies_linked = False
    try:
        root = repository_root(probe)
        active_git = git or Git(root)
        target = receipt_path(root, active_git)
        target.unlink(missing_ok=True)
        paths, files = normalize_task_paths(root, path_values)
        branch = require_ok(active_git.run("branch", "--show-current"), "branch discovery")
        head = require_ok(active_git.run("rev-parse", "HEAD"), "HEAD discovery")
        if not branch:
            raise RuntimeError("detached HEAD is not supported")
        transaction_receipt = None
        transaction_post_fingerprints = None
        transaction_index = None
        verification_root = root
        isolated_tree = None
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
            isolated_path, isolated_tree = create_isolated_worktree(transaction_id, git=active_git)
            verification_root = isolated_path
            if fingerprints(verification_root, files) != all_candidate_fingerprints:
                raise RuntimeError("isolated candidate overlay does not match derived candidate")
            checks.append({"name": "isolated-candidate-overlay", "status": "PASS", "detail": ""})
        python_files = [str(verification_root / p) for p in files if p.endswith(".py")]
        test_files = [p for p in files if p.startswith("tests/") and p.endswith(".py")]
        if python_files:
            label, passed, detail = _run_check(verification_root, "python-compile", (sys.executable, "-m", "py_compile", *python_files))
            checks.append({"name": label, "status": "PASS" if passed else "FAIL", "detail": detail})
        for test_file in test_files:
            label = f"focused-test:{Path(test_file).name}"
            module = test_file[:-3].replace("/", ".")
            name, passed, detail = _run_check(verification_root, label, (sys.executable, "-m", "unittest", module))
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
                verification_root, "trading-contract-consistency",
                (sys.executable, "-m", "tools.dev.contract_consistency"),
            )
            checks.append({"name": label, "status": "PASS" if passed else "FAIL", "detail": detail})
        executed_commands: list[dict[str, object]] = []
        command_specs = list(additional_commands)
        if any(path.startswith("terminal/frontend/src/") for path in paths):
            if transaction_id and _link_frontend_dependencies(root, verification_root):
                frontend_dependencies_linked = True
                checks.append({"name": "frontend-dependency-link", "status": "PASS", "detail": ""})
            command_specs.append({
                "label": "frontend-build", "cwd": "terminal/frontend",
                "argv": ["npm.cmd" if os.name == "nt" else "npm", "run", "build"],
            })
        for number, spec in enumerate(command_specs, start=1):
            if not isinstance(spec, dict):
                raise ValueError("additional verification command must be an object")
            argv = spec.get("argv")
            cwd_value = spec.get("cwd", ".")
            label_value = spec.get("label", f"additional-check:{number}")
            if (
                not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv)
                or not isinstance(cwd_value, str) or not isinstance(label_value, str) or not label_value
            ):
                raise ValueError("additional verification command requires label, cwd and non-empty argv")
            command_cwd = resolve_inside(
                verification_root, cwd_value, label="additional verification command cwd"
            )
            if not command_cwd.is_dir():
                raise ValueError(f"additional verification command cwd is missing: {cwd_value}")
            name, passed, detail = _run_check(command_cwd, label_value, tuple(argv))
            checks.append({"name": name, "status": "PASS" if passed else "FAIL", "detail": detail})
            executed_commands.append({"label": label_value, "cwd": cwd_value, "argv": argv})
        if transaction_receipt:
            changed_result = Git(verification_root).run("diff", "--name-only", "-z")
            changed_files = {item for item in require_ok(
                changed_result, "isolated tracked-file inspection"
            ).split("\0") if item}
            expected_changes = set(transaction_receipt["candidate_files"])
            checks.append({
                "name": "isolated-tracked-scope",
                "status": "PASS" if changed_files == expected_changes else "FAIL",
                "detail": "" if changed_files == expected_changes else (
                    "tracked files differ from candidate scope: " + ", ".join(sorted(changed_files))
                ),
            })
        diff = Git(verification_root).run("diff", "--check", "--", *paths)
        checks.append({"name": "diff-check", "status": "PASS" if diff.returncode == 0 else "FAIL", "detail": (diff.stderr or diff.stdout).strip()})
        failed = [str(item["name"]) for item in checks if item["status"] != "PASS"]
        if failed:
            if isolated_path is not None:
                if frontend_dependencies_linked:
                    _unlink_frontend_dependencies(isolated_path)
                    frontend_dependencies_linked = False
                remove_isolated_worktree(isolated_path, git=active_git)
                isolated_path = None
            return False, compact("FAIL", paths, [str(x["name"]) for x in checks], failed, ())
        if transaction_receipt:
            state = inspect(transaction_id or "", git=active_git)
            if state["status"] != "OK":
                raise RuntimeError("transaction became stale during verification")
            if fingerprints(root, files) != transaction_post_fingerprints:
                raise RuntimeError("transaction task-file content changed during verification")
            if index_snapshot(root, active_git) != transaction_index:
                raise RuntimeError("real Git index changed during transaction verification")
            if fingerprints(verification_root, files) != all_candidate_fingerprints:
                raise RuntimeError("isolated candidate changed during verification")
            if candidate_tree(transaction_id or "", git=active_git) != isolated_tree:
                raise RuntimeError("candidate tree changed during isolated verification")
            if frontend_dependencies_linked:
                _unlink_frontend_dependencies(isolated_path or Path())
                frontend_dependencies_linked = False
            remove_isolated_worktree(isolated_path or Path(), git=active_git)
            isolated_path = None
            checks.append({"name": "real-index-unchanged", "status": "PASS", "detail": ""})
            checks.append({"name": "isolated-worktree-cleanup", "status": "PASS", "detail": ""})
            transaction_receipt["candidate_tree"] = isolated_tree
            transaction_receipt["isolated_verification"] = {
                "status": "PASS", "base_head": head, "candidate_tree": isolated_tree,
                "commands": executed_commands, "cleanup": "PASS",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
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
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return True, compact("PASS", paths, [str(x["name"]) for x in checks], (), ())
    except (OSError, RuntimeError, ValueError) as exc:
        blockers = [str(exc)]
        if isolated_path is not None:
            try:
                if frontend_dependencies_linked:
                    _unlink_frontend_dependencies(isolated_path)
                remove_isolated_worktree(isolated_path, git=git or Git(Path.cwd()))
            except (OSError, RuntimeError, ValueError) as cleanup_exc:
                blockers.append(str(cleanup_exc))
        return False, compact("FAIL", list(path_values), [str(x["name"]) for x in checks], (), blockers)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", action="append", required=True, dest="paths")
    parser.add_argument("--transaction", dest="transaction_id")
    parser.add_argument(
        "--check-command", action="append", default=[],
        help='JSON object: {"label":"...","cwd":"...","argv":["command","arg"]}',
    )
    args = parser.parse_args(argv)
    try:
        commands = [json.loads(value) for value in args.check_command]
    except json.JSONDecodeError as exc:
        parser.error(f"invalid --check-command JSON: {exc}")
    passed, output = verify(
        args.paths, transaction_id=args.transaction_id, additional_commands=commands
    )
    print(output)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

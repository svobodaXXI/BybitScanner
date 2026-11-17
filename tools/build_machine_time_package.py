"""Build a bounded, public-source local Machine Time ZIP for desktop releases.

No user files, trading credentials, VPS state, runtime databases, cache,
.git directories, virtualenv or developer workstation artifacts can enter it.
Run after npm build:replay produced the expected dist/replay.html.
"""
from __future__ import annotations

import argparse
import ast
from pathlib import Path
import re
import shutil
import subprocess
import sys
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "research/local_replay_viewer"
ROOT_DIRS = ("research", "geometry", "wedge", "signals", "mirror_levels", "terminal")
ROOT_FILES = ("robot_protection.py", "mirror_scanner.py", "mirror_retest_robot.py")
SHA = re.compile(r"[0-9a-f]{40}\Z")


def package(output: Path, sha: str) -> int:
    if not SHA.fullmatch(sha):
        raise ValueError("invalid_release_sha")
    if not (VIEWER / "dist/replay.html").is_file():
        raise ValueError("standalone_replay_assets_not_built")
    # Only git-tracked source files, no ignored local configuration or secrets.
    listing = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "-z"])
    tracked = [Path(p.decode("utf-8")) for p in listing.split(b"\0") if p]
    entries: dict[str, bytes] = {}
    for rel in tracked:
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("unsafe_tracked_path")
        if ((rel.parts[0] in ROOT_DIRS and rel.suffix == ".py"
                and rel.parts[:2] != ("terminal", "frontend"))
                or rel.as_posix() in ROOT_FILES):
            entries[rel.as_posix()] = (ROOT / rel).read_bytes()
    # Resolve only tracked root-module imports needed by the bundled Python
    # packages. E.g. geometry.touches imports root confirmation.py. Do not
    # include every root script or shadow Python's stdlib (signal.py).
    root_modules = {
        rel.stem: rel for rel in tracked
        if len(rel.parts) == 1 and rel.suffix == ".py"
        and rel.stem not in sys.stdlib_module_names
        and rel.stem not in ROOT_DIRS and not rel.stem.startswith("test_")
        and rel.name != "config.example.py"
    }
    while True:
        required = set()
        for relative, payload in entries.items():
            if not relative.endswith(".py"):
                continue
            try:
                source = ast.parse(payload.decode("utf-8"), filename=relative)
            except (SyntaxError, UnicodeError) as exc:
                raise ValueError("tracked_python_source_invalid") from exc
            for node in ast.walk(source):
                if isinstance(node, ast.Import):
                    required.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    required.add(node.module.split(".")[0])
        missing = sorted(name for name in required
                         if name in root_modules and
                         root_modules[name].as_posix() not in entries)
        if not missing:
            break
        for name in missing:
            rel = root_modules[name]
            entries[rel.as_posix()] = (ROOT / rel).read_bytes()
    for rel in tracked:
        if rel.parts[:2] == ("research", "local_replay_viewer") and rel.name in (
            "START_LOCAL.cmd", "README.txt",
        ):
            entries[rel.name] = (ROOT / rel).read_bytes()
    for name in ("server.py", "public_m5_cache.py", "protocol_launcher.py",
                 "launch_bridge_agent.py", "desktop_update.py",
                 "simulator_self_update.py", "paper_episode_local_store.py"):
        if name.endswith(".py"):
            # Desktop entrypoints must also live at the extracted ZIP root.
            source = VIEWER / name
            if not source.is_file():
                raise ValueError("missing_local_entrypoint_" + name)
            entries[name] = source.read_bytes()
    dist = VIEWER / "dist"
    for file in dist.rglob("*"):
        if file.is_symlink():
            raise ValueError("untrusted_dist_symlink")
        if file.is_file():
            rel = file.relative_to(VIEWER).as_posix()
            entries[rel] = file.read_bytes()
    entries["desktop-build-sha.txt"] = (sha + "\n").encode("ascii")
    if any(p.startswith(("simulator-v2-data/", "paper-episode-facts/",
                         "public-m5-cache/", ".wedge-python/"))
           for p in entries):
        raise ValueError("protected_user_state_in_package")
    if len(entries) > 5000 or sum(len(x) for x in entries.values()) > 220_000_000:
        raise ValueError("package_size_unbounded")
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "x", compression=ZIP_DEFLATED, compresslevel=8) as zipf:
        for rel, data in sorted(entries.items()):
            zipf.writestr("MachineTime/" + rel, data)
    return len(entries)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print("MACHINE_TIME_PACKAGE_FILES=" + str(package(args.output, args.sha)))


if __name__ == "__main__":
    main()

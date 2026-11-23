"""Regression: the desktop ZIP must import scoring without production config."""
from __future__ import annotations

import subprocess
import sys
from zipfile import ZipFile

from tools import build_machine_time_package as builder


def test_desktop_zip_bundles_pure_analyzer_scoring(tmp_path, monkeypatch):
    root = tmp_path / "source"
    viewer = root / "research" / "local_replay_viewer"
    (viewer / "dist").mkdir(parents=True)
    (viewer / "dist" / "replay.html").write_text("<!doctype html>", encoding="utf-8")
    (viewer / "trusted-statistics-origin.txt").write_text(
        "https://example.invalid\n", encoding="utf-8"
    )

    tracked = [
        "analyzer/__init__.py",
        "analyzer/scoring.py",
        "analyzer.py",
        "research/local_replay_viewer/trusted-statistics-origin.txt",
    ]
    # Test the actual reviewed analyzer sources, not a fabricated scoring stub.
    for relative in tracked[:3]:
        dest = root / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((builder.ROOT / relative).read_bytes())

    for name in (
        "server.py",
        "public_m5_cache.py",
        "protocol_launcher.py",
        "launch_bridge_agent.py",
        "desktop_update.py",
        "simulator_self_update.py",
        "paper_episode_local_store.py",
    ):
        (viewer / name).write_text("# entrypoint fixture\n", encoding="utf-8")

    monkeypatch.setattr(builder, "ROOT", root)
    monkeypatch.setattr(builder, "VIEWER", viewer)
    monkeypatch.setattr(
        builder.subprocess, "check_output",
        lambda cmd: b"\0".join(path.encode() for path in tracked) + b"\0",
    )

    archive = tmp_path / "machine-time.zip"
    builder.package(archive, "a" * 40)
    with ZipFile(archive) as zf:
        names = set(zf.namelist())
        assert "MachineTime/analyzer/__init__.py" in names
        assert "MachineTime/analyzer/scoring.py" in names
        assert "MachineTime/analyzer.py" not in names
        assert "MachineTime/config.py" not in names
        zf.extractall(tmp_path / "unpacked")

    extracted = tmp_path / "unpacked" / "MachineTime"
    check = (
        "import sys; sys.path.insert(0, " + repr(str(extracted)) + "); "
        "from analyzer.scoring import calculate_final_score; "
        "assert calculate_final_score({'score': 60}, "
        "{'confirmation_score': 15}) == 75"
    )
    subprocess.run(
        [sys.executable, "-I", "-B", "-c", check],
        check=True, capture_output=True, text=True, timeout=15,
    )

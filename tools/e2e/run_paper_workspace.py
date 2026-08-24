"""Run the isolated real-backend/real-frontend PAPER Workspace E2E suite."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "terminal" / "frontend"


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_ready(url: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"process exited before readiness: {url}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"timed out waiting for {url}")


def _stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    backend_port, frontend_port = _free_port(), _free_port()
    backend_url = f"http://127.0.0.1:{backend_port}"
    frontend_url = f"http://127.0.0.1:{frontend_port}"
    processes: list[subprocess.Popen[bytes]] = []

    with tempfile.TemporaryDirectory(prefix="bybitscanner-paper-e2e-") as runtime_dir:
        env = os.environ.copy()
        env.update(
            {
                "BYBITSCANNER_PAPER_DB": str(Path(runtime_dir) / "paper-e2e.sqlite3"),
                "BYBITSCANNER_PAPER_PORT": str(backend_port),
                "PAPER_BACKEND_URL": backend_url,
                "PAPER_FRONTEND_URL": frontend_url,
                "PLAYWRIGHT_OUTPUT_DIR": str(Path(runtime_dir) / "playwright-results"),
            }
        )
        try:
            backend = subprocess.Popen(
                [sys.executable, "-m", "terminal.runtime.paper_http_server"],
                cwd=ROOT,
                env=env,
            )
            processes.append(backend)
            _wait_ready(f"{backend_url}/api/health", backend)

            vite = subprocess.Popen(
                ["node", "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", str(frontend_port), "--strictPort"],
                cwd=FRONTEND,
                env=env,
            )
            processes.append(vite)
            _wait_ready(frontend_url, vite)

            return subprocess.run(
                ["node", "node_modules/@playwright/test/cli.js", "test"],
                cwd=FRONTEND,
                env=env,
                check=False,
            ).returncode
        finally:
            for process in reversed(processes):
                _stop(process)


if __name__ == "__main__":
    raise SystemExit(main())

"""``python -m tools.SwordCounter`` starts the SwordCounter window (one instance per user session)."""

from __future__ import annotations

import sys
from typing import Callable

from tools.SwordCounter.single_instance import SingleInstance


def main(guard: SingleInstance | None = None, run_app: Callable[[], None] | None = None) -> int:
    guard = guard if guard is not None else SingleInstance()
    if not guard.acquire():
        return 0  # already running: stay quiet, the existing window is the one to use
    try:
        if run_app is None:
            from tools.SwordCounter.app import run as run_app
        run_app()
    finally:
        guard.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())

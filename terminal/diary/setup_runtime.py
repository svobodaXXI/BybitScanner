"""Runtime-safe read boundary for Trading Diary D6.3 setup observations."""

from __future__ import annotations

from pathlib import Path

from .decision_store import DiaryDecisionStore
from .setup_presentation import project_setup_list


def decision_store_path(runtime_database_path: str | Path) -> Path:
    """Keep D2 observational evidence separate from Terminal execution persistence."""
    return Path(runtime_database_path).with_suffix(".trading_diary.sqlite3")


def project_setup_store(path: str | Path) -> dict[str, object]:
    """Read setup observations from the dedicated D2 store.

    Opening the append-only Diary store may initialize its own schema when absent,
    but this function never writes setup/decision/trade evidence and has no access
    to trading command or execution mutation paths.
    """
    with DiaryDecisionStore.open(path) as store:
        return {
            "setups": project_setup_list(store),
            "source": "TRADING_DIARY_D2",
        }

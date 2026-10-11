"""SwordCounter S3: user settings (total swords) persisted outside the Git repository.

The RO cost is not a setting: it is Account Equity / total swords, read live from Bybit.
Only the number of swords is stored, as JSON in ``%APPDATA%\\SwordCounter\\settings.json``.
API keys are never read or written here.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TOTAL_SWORDS = 20
SETTINGS_VERSION = 1
_REPO_ROOT = Path(__file__).resolve().parents[2]
_INTEGER = re.compile(r"^\d+$")


@dataclass(frozen=True)
class AppSettings:
    total_swords: int = DEFAULT_TOTAL_SWORDS   # also the number of equity parts: 1 RO = equity / total

    def __post_init__(self) -> None:
        value = self.total_swords
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("total_swords must be a positive integer")


def parse_total_swords(text: str) -> int:
    """Total swords from user input: a positive whole number."""
    value = str(text).strip()
    if not _INTEGER.match(value) or int(value) <= 0:
        raise ValueError("Всего мечей: целое положительное число")
    return int(value)


def default_settings_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "SwordCounter" / "settings.json"


def load_settings(path: Path | None = None) -> tuple[AppSettings, str | None]:
    """Return (settings, warning). A missing file is the defaults; a bad file is kept and reported."""
    path = Path(path) if path is not None else default_settings_path()
    if not path.exists():
        return AppSettings(), None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != SETTINGS_VERSION:
            raise ValueError("unsupported settings format")
        return AppSettings(total_swords=data.get("total_swords")), None   # an old "ro_usdt" is ignored
    except (OSError, ValueError, TypeError) as error:
        return AppSettings(), f"настройки не прочитаны ({type(error).__name__}), используются значения по умолчанию"


def save_settings(settings: AppSettings, path: Path | None = None) -> Path:
    """Atomically write the settings. Refuses any location inside the Git repository."""
    path = Path(path) if path is not None else default_settings_path()
    resolved = path.resolve()
    if resolved == _REPO_ROOT or _REPO_ROOT in resolved.parents:
        raise ValueError("settings must be stored outside the Git repository")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"version": SETTINGS_VERSION, "total_swords": settings.total_swords}, indent=1)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return path

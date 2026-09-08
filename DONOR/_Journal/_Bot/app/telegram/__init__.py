"""Production Telegram presentation boundary for the Trading Journal."""

from .composition import JournalApplication, create_runtime
from .config import TelegramSettings, load_settings

__all__ = ["JournalApplication", "TelegramSettings", "create_dispatcher", "create_runtime", "load_settings"]


def __getattr__(name):
    """Load the bot module lazily so ``python -m app.telegram.bot`` is clean."""
    if name == "create_dispatcher":
        from .bot import create_dispatcher

        return create_dispatcher
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

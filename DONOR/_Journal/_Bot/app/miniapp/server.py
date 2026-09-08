"""Development ASGI factory for the Telegram Mini App."""

from app.infrastructure.persistence.telegram_access import TelegramAccessStore
from app.telegram.composition import create_runtime
from app.telegram.config import load_settings
from zoneinfo import ZoneInfo

from .api import create_mini_app
from .auth import TelegramWebAppAuthenticator
from .viewer_access import install_viewer_access


def create_app():
    settings = load_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required")
    engine, runtime = create_runtime(
        settings.database_url,
        settings.journal_account_id,
        entry_timezone=ZoneInfo(settings.reminder_settings.timezone_name),
    )

    if settings.telegram_bot_token and settings.allowed_user_id is not None:
        authenticator = TelegramWebAppAuthenticator(
            settings.telegram_bot_token,
            None,
            max_age_seconds=settings.webapp_auth_max_age_seconds,
        )
        app = create_mini_app(runtime, authenticator=authenticator)
        install_viewer_access(
            app,
            access_store=TelegramAccessStore.from_engine(engine),
            owner_telegram_user_id=settings.allowed_user_id,
            authenticator=authenticator,
            default_account_id=settings.journal_account_id,
        )
    else:
        app = create_mini_app(runtime, settings)

    app.state.database_engine = engine

    async def dispose_engine():
        await engine.dispose()

    # FastAPI 0.141 removed the application convenience method; the router
    # lifecycle hook remains the stable ASGI shutdown integration point.
    app.router.on_shutdown.append(dispose_engine)
    return app

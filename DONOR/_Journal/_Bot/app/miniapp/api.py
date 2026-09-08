"""FastAPI HTTP boundary for the Telegram Mini App."""

from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path

from fastapi import Body, Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.application import (
    DynamicFieldCoverageRequest,
    GetTradeDetailsCommand,
    GroupedPerformanceRequest,
    SearchInstrumentsCommand,
    StatisticsFilter,
    StatisticsGroupBy,
)
from app.application.errors import TradeNotFoundError

from .auth import MiniAppAuthError, MiniAppOwnerError, TelegramWebAppAuthenticator, TelegramWebAppUser
from .serializers import (
    serialize_coverage,
    serialize_dynamic_field,
    serialize_attention,
    serialize_grouped,
    serialize_metric_coverage,
    serialize_metric_definition,
    serialize_statistics_layout,
    serialize_statistics_overview,
    serialize_automatic_factor,
    serialize_summary,
    serialize_trade_details,
    serialize_trade_page,
)

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).with_name("static")


def create_mini_app(runtime, settings=None, *, authenticator=None) -> FastAPI:
    """Create a protected Mini App; static shell is public, API is not."""
    if authenticator is None and settings is not None:
        if getattr(settings, "telegram_bot_token", "") and getattr(settings, "allowed_user_id", None) is not None:
            authenticator = TelegramWebAppAuthenticator(
                settings.telegram_bot_token,
                settings.allowed_user_id,
                max_age_seconds=getattr(settings, "webapp_auth_max_age_seconds", 86400),
            )

    app = FastAPI(title="Trading Journal Mini App", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.middleware("http")
    async def basic_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    async def current_user(
        x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
        authorization: str | None = Header(default=None),
    ) -> TelegramWebAppUser:
        init_data = x_telegram_init_data
        if init_data is None and authorization and authorization.startswith("tma "):
            init_data = authorization[4:]
        if authenticator is None:
            raise MiniAppAuthError("Mini App authentication is not configured")
        return authenticator.authenticate(init_data or "")

    @app.exception_handler(MiniAppAuthError)
    async def auth_error_handler(request: Request, exc: MiniAppAuthError):
        status = 403 if isinstance(exc, MiniAppOwnerError) else 401
        return _error(status, "ACCESS_DENIED" if status == 403 else "AUTH_REQUIRED", str(exc))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return _error(422, "INVALID_REQUEST", "Invalid request parameters")

    @app.exception_handler(TradeNotFoundError)
    async def not_found_handler(request: Request, exc: TradeNotFoundError):
        return _error(404, "NOT_FOUND", "Trade not found")

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return _error(422, "INVALID_REQUEST", str(exc))

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        logger.error("MINIAPP_REQUEST_FAILED path=%s error_type=%s", request.url.path, type(exc).__name__)
        return _error(500, "INTERNAL_ERROR", "Request could not be completed")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/miniapp/dashboard")
    async def dashboard(
        user: TelegramWebAppUser = Depends(current_user),
        account_id: str | None = None,
        instrument_id: str | None = None,
        direction: str | None = None,
        from_at: str | None = None,
        to_at: str | None = None,
    ):
        result = await runtime.miniapp_dashboard(_parse_filters(
            account_id, instrument_id, direction, None, from_at, to_at, default_status="CLOSED"
        ))
        return {"summary": serialize_summary(result)}

    @app.get("/api/miniapp/trades")
    async def trades(
        user: TelegramWebAppUser = Depends(current_user),
        account_id: str | None = None,
        instrument_id: str | None = None,
        direction: str | None = None,
        status: str | None = None,
        from_at: str | None = None,
        to_at: str | None = None,
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        result = await runtime.miniapp_list_trades(
            _parse_filters(account_id, instrument_id, direction, status, from_at, to_at, default_status=None),
            limit=limit,
            offset=offset,
        )
        return serialize_trade_page(result)

    @app.get("/api/miniapp/trades/{trade_id}")
    async def trade_details(trade_id: str, user: TelegramWebAppUser = Depends(current_user)):
        return serialize_trade_details(await runtime.miniapp_trade_details(GetTradeDetailsCommand(trade_id)))

    @app.get("/api/miniapp/attention")
    async def attention(
        user: TelegramWebAppUser = Depends(current_user),
        account_id: str | None = None,
        instrument_id: str | None = None,
    ):
        return serialize_attention(await runtime.miniapp_attention(account_id=account_id, instrument_id=instrument_id))

    @app.get("/api/miniapp/attention/summary")
    async def attention_summary(
        user: TelegramWebAppUser = Depends(current_user),
        account_id: str | None = None,
        instrument_id: str | None = None,
    ):
        result = await runtime.miniapp_attention(account_id=account_id, instrument_id=instrument_id)
        return {"summary": serialize_attention(result)["summary"]}

    @app.get("/api/miniapp/statistics/summary")
    async def statistics_summary(
        user: TelegramWebAppUser = Depends(current_user),
        account_id: str | None = None,
        instrument_id: str | None = None,
        direction: str | None = None,
        status: str | None = "CLOSED",
        from_at: str | None = None,
        to_at: str | None = None,
    ):
        result = await runtime.miniapp_dashboard(
            _parse_filters(account_id, instrument_id, direction, status, from_at, to_at, default_status="CLOSED")
        )
        return {"summary": serialize_summary(result)}

    @app.get("/api/miniapp/statistics/groups")
    async def statistics_groups(
        group_by: str = Query(...),
        user: TelegramWebAppUser = Depends(current_user),
        field_id: str | None = None,
        field_code: str | None = None,
        account_id: str | None = None,
        instrument_id: str | None = None,
        direction: str | None = None,
        status: str | None = "CLOSED",
        from_at: str | None = None,
        to_at: str | None = None,
        min_sample_size: int = Query(0, ge=0),
        include_missing: bool = False,
    ):
        request = GroupedPerformanceRequest(
            StatisticsGroupBy(group_by),
            filters=_parse_filters(account_id, instrument_id, direction, status, from_at, to_at, default_status="CLOSED"),
            field_id=field_id,
            field_code=field_code,
            min_sample_size=min_sample_size,
            include_missing=include_missing,
        )
        return serialize_grouped(await runtime.miniapp_statistics_groups(request))

    @app.get("/api/miniapp/statistics/coverage")
    async def statistics_coverage(
        user: TelegramWebAppUser = Depends(current_user),
        field_id: str | None = None,
        field_code: str | None = None,
        account_id: str | None = None,
        instrument_id: str | None = None,
        direction: str | None = None,
        status: str | None = "CLOSED",
        from_at: str | None = None,
        to_at: str | None = None,
    ):
        request = DynamicFieldCoverageRequest(
            filters=_parse_filters(account_id, instrument_id, direction, status, from_at, to_at, default_status="CLOSED"),
            field_id=field_id,
            field_code=field_code,
        )
        return serialize_coverage(await runtime.miniapp_dynamic_field_coverage(request))

    @app.get("/api/miniapp/statistics/metrics/coverage")
    async def metric_coverage(
        metric: str = Query(...),
        user: TelegramWebAppUser = Depends(current_user),
        account_id: str | None = None,
        instrument_id: str | None = None,
        direction: str | None = None,
        status: str | None = "CLOSED",
        from_at: str | None = None,
        to_at: str | None = None,
    ):
        result = await runtime.miniapp_metric_coverage(
            metric,
            _parse_filters(account_id, instrument_id, direction, status, from_at, to_at, default_status="CLOSED"),
        )
        return serialize_metric_coverage(result)

    @app.get("/api/miniapp/statistics/metrics")
    async def statistics_metrics(user: TelegramWebAppUser = Depends(current_user)):
        return {"items": [serialize_metric_definition(item) for item in await runtime.miniapp_statistics_metrics()]}

    @app.get("/api/miniapp/statistics/overview")
    async def statistics_overview(
        user: TelegramWebAppUser = Depends(current_user), account_id: str | None = None,
        instrument_id: str | None = None, direction: str | None = None,
        status: str | None = "CLOSED", from_at: str | None = None, to_at: str | None = None,
    ):
        filters = _parse_filters(account_id, instrument_id, direction, status, from_at, to_at, default_status="CLOSED")
        result = await runtime.miniapp_statistics_overview(filters, account_id)
        return serialize_statistics_overview(result, await runtime.miniapp_statistics_metrics())

    @app.get("/api/miniapp/settings/statistics-layout")
    async def get_statistics_layout(account_id: str | None = None, user: TelegramWebAppUser = Depends(current_user)):
        return serialize_statistics_layout(await runtime.miniapp_statistics_layout(account_id))

    @app.patch("/api/miniapp/settings/statistics-layout")
    @app.put("/api/miniapp/settings/statistics-layout")
    async def update_statistics_layout(payload: dict = Body(...), account_id: str | None = None, user: TelegramWebAppUser = Depends(current_user)):
        layout = await runtime.save_statistics_layout(account_id, payload)
        return serialize_statistics_layout(layout)

    @app.get("/api/miniapp/automatic-factors")
    async def automatic_factors(account_id: str | None = None, user: TelegramWebAppUser = Depends(current_user)):
        return {"items": [serialize_automatic_factor(item, enabled) for item, enabled in await runtime.miniapp_automatic_factors(account_id)]}

    @app.get("/api/miniapp/settings/automatic-factors")
    async def get_automatic_factor_settings(account_id: str | None = None, user: TelegramWebAppUser = Depends(current_user)):
        return {"items": [serialize_automatic_factor(item, enabled) for item, enabled in await runtime.miniapp_automatic_factors(account_id)]}

    @app.patch("/api/miniapp/settings/automatic-factors/{factor_id}")
    async def update_automatic_factor_setting(factor_id: str, payload: dict = Body(...), account_id: str | None = None, user: TelegramWebAppUser = Depends(current_user)):
        if type(payload.get("enabled")) is not bool:
            raise ValueError("boolean enabled is required")
        return await runtime.set_automatic_factor_enabled(account_id, factor_id, payload["enabled"])

    @app.patch("/api/miniapp/settings/automatic-factors")
    async def update_automatic_factor_setting_body(payload: dict = Body(...), account_id: str | None = None, user: TelegramWebAppUser = Depends(current_user)):
        if not isinstance(payload.get("factor_id"), str) or type(payload.get("enabled")) is not bool:
            raise ValueError("factor_id and boolean enabled are required")
        return await runtime.set_automatic_factor_enabled(account_id, payload["factor_id"], payload["enabled"])

    @app.get("/api/miniapp/dynamic-fields")
    async def dynamic_fields(user: TelegramWebAppUser = Depends(current_user)):
        return {"items": [serialize_dynamic_field(item) for item in await runtime.miniapp_dynamic_fields()]}

    @app.patch("/api/miniapp/dynamic-fields/{field_id}")
    async def update_dynamic_field(field_id: str, required_for_statistics: bool = Body(...), user: TelegramWebAppUser = Depends(current_user)):
        field = await runtime.set_custom_field_required_for_statistics(field_id, required_for_statistics)
        return serialize_dynamic_field(field)

    @app.get("/api/miniapp/instruments")
    async def instruments(query: str = Query(..., min_length=1, max_length=100), user: TelegramWebAppUser = Depends(current_user)):
        items = await runtime.search_instruments(SearchInstrumentsCommand(query))
        return {"items": [
            {"id": str(item.instrument_id), "symbol": item.symbol, "name": item.name, "exchange": item.exchange, "market": item.market}
            for item in items
        ]}

    return app


def _parse_filters(account_id, instrument_id, direction, status, from_at, to_at, *, default_status):
    return StatisticsFilter(
        account_id=account_id,
        instrument_id=instrument_id,
        direction=direction,
        status=default_status if status is None else status,
        from_at=_parse_datetime(from_at),
        to_at=_parse_datetime(to_at),
    )


def _parse_datetime(value):
    if value is None or value == "":
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _error(status: int, code: str, message: str):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})

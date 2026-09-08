"""Read-only viewer authorization layered over the existing Mini App API."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.access import AccessRole
from app.infrastructure.persistence.telegram_access import TelegramAccessStore

from .auth import MiniAppAuthError, MiniAppStaleAuthError, TelegramWebAppAuthenticator


_ACCOUNT_SCOPED_PATHS = (
    "/api/miniapp/dashboard",
    "/api/miniapp/trades",
    "/api/miniapp/attention",
    "/api/miniapp/statistics/summary",
    "/api/miniapp/statistics/groups",
    "/api/miniapp/statistics/coverage",
    "/api/miniapp/statistics/metrics/coverage",
    "/api/miniapp/statistics/overview",
    "/api/miniapp/settings/statistics-layout",
    "/api/miniapp/automatic-factors",
    "/api/miniapp/settings/automatic-factors",
)


def install_viewer_access(
    app: FastAPI,
    *,
    access_store: TelegramAccessStore,
    owner_telegram_user_id: int | None,
    authenticator: TelegramWebAppAuthenticator,
    default_account_id=None,
) -> None:
    """Authorize signed Telegram users and make VIEWER HTTP access read-only."""

    @app.middleware("http")
    async def telegram_viewer_authorization(request: Request, call_next):
        if not request.url.path.startswith("/api/miniapp/"):
            return await call_next(request)
        try:
            user = authenticator.authenticate(_init_data(request))
        except MiniAppStaleAuthError as exc:
            return _error(401, "AUTH_REQUIRED", str(exc))
        except MiniAppAuthError as exc:
            return _error(401, "AUTH_REQUIRED", str(exc))

        role = await access_store.resolve_role(user.user_id, owner_telegram_user_id)
        if role is None:
            return _error(403, "ACCESS_DENIED", "Доступ запрещён.")
        request.state.access_role = role
        request.state.telegram_user = user

        if role is AccessRole.VIEWER:
            if request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
                return _error(403, "READ_ONLY", "Редактирование отключено.")
            scoped = await _scope_viewer_request(request, access_store, default_account_id)
            if scoped is not None:
                return scoped
        return await call_next(request)

    @app.get("/api/miniapp/access", include_in_schema=False)
    async def access_info(request: Request):
        role = getattr(request.state, "access_role", None)
        if role is None:
            return _error(403, "ACCESS_DENIED", "Доступ запрещён.")
        return {
            "role": role.value,
            "read_only": role is AccessRole.VIEWER,
            "notice": "Вы просматриваете журнал. Редактирование отключено."
            if role is AccessRole.VIEWER
            else None,
        }


async def _scope_viewer_request(request: Request, access_store: TelegramAccessStore, default_account_id):
    path = request.url.path
    if path.startswith("/api/miniapp/trades/") and path != "/api/miniapp/trades/":
        trade_id = path.rsplit("/", 1)[-1]
        try:
            allowed = bool(trade_id) and await access_store.trade_belongs_to_owner(trade_id)
        except (TypeError, ValueError):
            allowed = False
        if not allowed:
            return _error(403, "ACCESS_DENIED", "Доступ запрещён.")
        return None

    if not any(path == prefix or path.startswith(prefix + "/") for prefix in _ACCOUNT_SCOPED_PATHS):
        return None

    pairs = parse_qsl(request.scope.get("query_string", b"").decode(), keep_blank_values=True)
    values = dict(pairs)
    requested_account = values.get("account_id") or None
    if requested_account is None:
        if default_account_id is None:
            return _error(403, "ACCESS_DENIED", "Журнал не настроен.")
        requested_account = str(default_account_id)
        pairs.append(("account_id", requested_account))
        request.scope["query_string"] = urlencode(pairs).encode()
    try:
        allowed = await access_store.account_belongs_to_owner(requested_account)
    except (TypeError, ValueError):
        allowed = False
    if not allowed:
        return _error(403, "ACCESS_DENIED", "Доступ запрещён.")
    return None


def _init_data(request: Request) -> str:
    value = request.headers.get("X-Telegram-Init-Data")
    if value:
        return value
    authorization = request.headers.get("Authorization", "")
    return authorization[4:] if authorization.startswith("tma ") else ""


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})

import hashlib
import hmac
import json
from datetime import datetime, timezone
from urllib.parse import urlencode

from fastapi.testclient import TestClient

from app.application.statistics import StatisticsLayout
from app.core.access import AccessRole
from app.core.accounts.account_id import AccountId
from app.miniapp.api import create_mini_app
from app.miniapp.auth import TelegramWebAppAuthenticator
from app.miniapp.viewer_access import install_viewer_access


TOKEN = "123456:VIEWER_TEST_TOKEN"
NOW = datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc)
OWNER_ID = 42
VIEWER_ID = 99


def init_data(user_id: int) -> str:
    values = {
        "auth_date": str(int(NOW.timestamp())),
        "query_id": "viewer-test-query",
        "user": json.dumps({"id": user_id, "first_name": "User"}, separators=(",", ":")),
    }
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


class RuntimeFake:
    async def miniapp_statistics_metrics(self):
        return ()

    async def save_statistics_layout(self, account_id, layout):
        return StatisticsLayout()


class AccessStoreFake:
    def __init__(self, roles):
        self.roles = roles
        self.account_allowed = True
        self.trade_allowed = True

    async def resolve_role(self, telegram_user_id, owner_telegram_user_id):
        if telegram_user_id == owner_telegram_user_id:
            return AccessRole.OWNER
        return self.roles.get(telegram_user_id)

    async def account_belongs_to_owner(self, account_id):
        return self.account_allowed

    async def trade_belongs_to_owner(self, trade_id):
        return self.trade_allowed


def make_client(roles=None):
    authenticator = TelegramWebAppAuthenticator(
        TOKEN,
        None,
        max_age_seconds=3600,
        now=lambda: int(NOW.timestamp()),
    )
    store = AccessStoreFake(roles or {})
    app = create_mini_app(RuntimeFake(), authenticator=authenticator)
    install_viewer_access(
        app,
        access_store=store,
        owner_telegram_user_id=OWNER_ID,
        authenticator=authenticator,
        default_account_id=AccountId.generate(),
    )
    return TestClient(app), store


def headers(user_id: int):
    return {"X-Telegram-Init-Data": init_data(user_id)}


def test_viewer_can_read_and_receives_read_only_notice():
    client, _ = make_client({VIEWER_ID: AccessRole.VIEWER})

    access = client.get("/api/miniapp/access", headers=headers(VIEWER_ID))
    metrics = client.get("/api/miniapp/statistics/metrics", headers=headers(VIEWER_ID))

    assert access.status_code == 200
    assert access.json() == {
        "role": "VIEWER",
        "read_only": True,
        "notice": "Вы просматриваете журнал. Редактирование отключено.",
    }
    assert metrics.status_code == 200
    assert metrics.json() == {"items": []}


def test_viewer_write_is_blocked_before_application_runtime():
    client, _ = make_client({VIEWER_ID: AccessRole.VIEWER})

    response = client.patch(
        "/api/miniapp/settings/statistics-layout",
        headers=headers(VIEWER_ID),
        json={"overview_metric_ids": []},
    )

    assert response.status_code == 403
    assert response.json()["error"] == {"code": "READ_ONLY", "message": "Редактирование отключено."}


def test_unknown_signed_telegram_user_is_denied():
    client, _ = make_client()

    response = client.get("/api/miniapp/statistics/metrics", headers=headers(VIEWER_ID))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCESS_DENIED"


def test_owner_keeps_write_access():
    client, _ = make_client({VIEWER_ID: AccessRole.VIEWER})

    response = client.patch(
        "/api/miniapp/settings/statistics-layout",
        headers=headers(OWNER_ID),
        json={"overview_metric_ids": []},
    )

    assert response.status_code == 200


def test_viewer_cannot_expand_scope_with_known_foreign_account_id():
    client, store = make_client({VIEWER_ID: AccessRole.VIEWER})
    store.account_allowed = False

    response = client.get(
        f"/api/miniapp/dashboard?account_id={AccountId.generate()}",
        headers=headers(VIEWER_ID),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCESS_DENIED"

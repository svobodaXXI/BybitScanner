import hashlib
import hmac
import json
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlencode

from fastapi.testclient import TestClient

from app.application import (
    DynamicFieldCoverage,
    DynamicFieldMetadata,
    GetTradeDetailsResult,
    GroupedPerformanceResult,
    InstrumentView,
    MiniAppTradePage,
    MiniAppTradeRow,
    PerformanceSummary,
    StatisticsGroupBy,
    StatisticsTradeRecord,
    TradeView,
)
from app.application.attention import AttentionItem, AttentionResult, AttentionSummary
from app.application.statistics import DynamicFieldCoverageRequest
from app.application.statistics import DEFAULT_STATISTICS_METRIC_REGISTRY, StatisticsLayout
from app.core.accounts.account_id import AccountId
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments.instrument_id import InstrumentId
from app.core.statistics import CustomFieldDefinition, CustomFieldPhase, CustomFieldSource, CustomFieldValueType
from app.core.trades.enums import TradeDirection
from app.core.trades.readiness import TradeReadiness, TradeReadinessStatus
from app.core.trades.trade import Trade
from app.miniapp.api import create_mini_app
from app.miniapp.auth import TelegramWebAppAuthenticator


TOKEN = "123456:TEST_TOKEN"
NOW = datetime(2026, 9, 3, 12, tzinfo=timezone.utc)


def init_data(user_id=42, auth_date=int(NOW.timestamp())):
    values = {
        "auth_date": str(auth_date),
        "query_id": "test-query",
        "user": json.dumps({"id": user_id, "first_name": "Owner"}, separators=(",", ":")),
    }
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


def closed_trade():
    trade = Trade.open(AccountId.generate(), InstrumentId.generate(), TradeDirection.LONG, Price(100), Quantity(1), NOW, "USDT")
    trade.close(Price(110), NOW.replace(hour=13))
    return trade


TRADE = closed_trade()
SUMMARY = PerformanceSummary(
    sample_size=1, trade_count=1, win_count=1, loss_count=0, breakeven_count=0,
    win_rate=Decimal("1"), gross_pnl=Decimal("10"), net_pnl=Decimal("10"), total_fees=Decimal("0"),
    total_expenses=Decimal("0"), average_net_pnl=Decimal("10"), average_win=Decimal("10"), average_loss=None,
    profit_factor=None, expectancy=Decimal("10"), largest_win=Decimal("10"), largest_loss=None,
    median_net_pnl=Decimal("10"), currency="USDT",
)
FIELD = CustomFieldDefinition.create(
    "quality", "Quality", CustomFieldValueType.TEXT, CustomFieldSource.MANUAL,
    CustomFieldPhase.ANY, created_at=NOW,
)


class RuntimeFake:
    def __init__(self):
        self.last_filters = None
        self.last_request = None

    async def miniapp_dashboard(self, filters):
        self.last_filters = filters
        return SUMMARY

    async def miniapp_list_trades(self, filters, *, limit, offset):
        self.last_filters = filters
        return MiniAppTradePage(
            (MiniAppTradeRow(TradeView.from_trade(TRADE), InstrumentView(TRADE.instrument_id, "BTCUSDT", "Bitcoin / Tether", "BYBIT", "LINEAR", True)),),
            limit, offset, False,
        )

    async def miniapp_trade_details(self, command):
        return GetTradeDetailsResult(
            TradeView.from_trade(TRADE), (),
            InstrumentView(TRADE.instrument_id, "BTCUSDT", "Bitcoin / Tether", "BYBIT", "LINEAR", True),
        )

    async def miniapp_statistics_groups(self, request):
        self.last_request = request
        from app.application.statistics import StatisticsGroup, GroupedPerformanceResult
        return GroupedPerformanceResult(StatisticsGroupBy.DIRECTION, (StatisticsGroup("LONG", "LONG", SUMMARY),), 1, 1, 0, Decimal("1"))

    async def miniapp_dynamic_field_coverage(self, request: DynamicFieldCoverageRequest):
        self.last_request = request
        return DynamicFieldCoverage(FIELD.id, str(FIELD.code), 1, 1, 0, Decimal("1"))

    async def miniapp_dynamic_fields(self):
        return (FIELD,)

    async def miniapp_attention(self, **kwargs):
        item = AttentionItem(
            TradeView.from_trade(TRADE),
            TradeReadiness(TradeReadinessStatus.INCOMPLETE, ("EXIT_PRICE",)),
            InstrumentView(TRADE.instrument_id, "BTCUSDT", "Bitcoin / Tether", "BYBIT", "LINEAR", True),
        )
        return AttentionResult(AttentionSummary(1, 0, 1), (item,))

    async def search_instruments(self, command):
        return (InstrumentView(TRADE.instrument_id, "BTCUSDT", "Bitcoin / Tether", "BYBIT", "LINEAR", True),)

    async def miniapp_statistics_metrics(self):
        return DEFAULT_STATISTICS_METRIC_REGISTRY.list()

    async def miniapp_statistics_layout(self, account_id=None):
        return StatisticsLayout()

    async def save_statistics_layout(self, account_id, layout):
        return layout if isinstance(layout, StatisticsLayout) else StatisticsLayout(**layout)

    async def miniapp_statistics_overview(self, filters, account_id=None):
        return {"summary": SUMMARY, "series": (), "layout": StatisticsLayout(), "coverage": {}}

    async def miniapp_automatic_factors(self, account_id=None):
        from app.core.automatic_data import DEFAULT_AUTOMATIC_FACTOR_REGISTRY
        return tuple((item, True) for item in DEFAULT_AUTOMATIC_FACTOR_REGISTRY)

    async def set_automatic_factor_enabled(self, account_id, factor_id, enabled):
        return {"factor_id": factor_id, "enabled": enabled}


def make_client():
    runtime = RuntimeFake()
    app = create_mini_app(runtime, authenticator=TelegramWebAppAuthenticator(
        TOKEN, 42, max_age_seconds=3600, now=lambda: int(NOW.timestamp())
    ))
    return TestClient(app), runtime


def headers():
    return {"X-Telegram-Init-Data": init_data()}


def test_api_requires_auth_and_returns_exact_decimal_summary():
    client, _ = make_client()
    assert client.get("/api/miniapp/dashboard").status_code == 401
    response = client.get("/api/miniapp/dashboard", headers=headers())
    assert response.status_code == 200
    body = response.json()["summary"]
    assert body["net_pnl"] == "10"
    assert body["profit_factor"] is None
    assert "Infinity" not in response.text and "NaN" not in response.text


def test_api_journal_details_statistics_coverage_and_metadata():
    client, runtime = make_client()
    journal = client.get("/api/miniapp/trades?limit=1&offset=2&direction=LONG", headers=headers())
    assert journal.status_code == 200
    assert journal.json()["items"][0]["instrument"]["symbol"] == "BTCUSDT"
    assert journal.json()["offset"] == 2
    assert runtime.last_filters.direction is TradeDirection.LONG

    details = client.get(f"/api/miniapp/trades/{TRADE.trade_id}", headers=headers())
    assert details.status_code == 200
    assert details.json()["trade"]["net_pnl"] == "10"
    assert details.json()["instrument"]["symbol"] == "BTCUSDT"

    groups = client.get("/api/miniapp/statistics/groups?group_by=DIRECTION&min_sample_size=2", headers=headers())
    assert groups.status_code == 200
    assert groups.json()["groups"][0]["sample_size"] == 1
    assert runtime.last_request.filters.status.value == "CLOSED"

    coverage = client.get("/api/miniapp/statistics/coverage?field_id=" + str(FIELD.id), headers=headers())
    assert coverage.status_code == 200
    assert coverage.json()["coverage_rate"] == "1"

    fields = client.get("/api/miniapp/dynamic-fields", headers=headers())
    assert fields.status_code == 200
    assert fields.json()["items"][0]["label"] == "Quality"
    assert "code" not in fields.json()["items"][0]


def test_attention_api_exposes_summary_items_and_readiness_in_details():
    client, _ = make_client()
    attention = client.get("/api/miniapp/attention", headers=headers())
    assert attention.status_code == 200
    assert attention.json()["summary"] == {"total_attention": 1, "open_count": 0, "incomplete_count": 1}
    assert attention.json()["items"][0]["data_status"] == "INCOMPLETE"
    summary = client.get("/api/miniapp/attention/summary", headers=headers())
    assert summary.status_code == 200
    assert summary.json()["summary"]["total_attention"] == 1


def test_metric_layout_and_automatic_data_api_contracts():
    client, _ = make_client()
    metrics = client.get("/api/miniapp/statistics/metrics", headers=headers())
    assert metrics.status_code == 200
    assert "cumulative_pnl" in {item["metric_id"] for item in metrics.json()["items"]}
    layout = client.patch("/api/miniapp/settings/statistics-layout", json={"overview_metric_ids": ["net_pnl"], "home_metric_ids": ["cumulative_pnl"], "home_metric_period": "30d"}, headers=headers())
    assert layout.status_code == 200 and layout.json()["home_metric_period"] == "30d"
    factors = client.get("/api/miniapp/automatic-factors", headers=headers())
    assert factors.status_code == 200
    assert all("source_kind" not in item and "capture_semantics" not in item for item in factors.json()["items"])
    setting = client.patch("/api/miniapp/settings/automatic-factors", json={"factor_id": "entry_hour", "enabled": False}, headers=headers())
    assert setting.status_code == 200 and setting.json()["enabled"] is False


def test_api_invalid_auth_and_invalid_filter_have_consistent_errors():
    client, _ = make_client()
    response = client.get("/api/miniapp/dashboard", headers={"X-Telegram-Init-Data": init_data(user_id=7)})
    assert response.status_code == 403
    assert set(response.json()["error"]) == {"code", "message"}
    response = client.get("/api/miniapp/trades?from_at=2026-09-03T12:00:00", headers=headers())
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_static_frontend_is_served_without_exposing_api_data():
    client, _ = make_client()
    response = client.get("/")
    assert response.status_code == 200
    assert "TRADING JOURNAL" in response.text
    assert "data-page=\"statistics\"" in response.text
    assert response.headers["x-content-type-options"] == "nosniff"


def test_static_frontend_has_phase_16_1_ux_contract_without_frontend_formulas():
    client, _ = make_client()
    index = client.get("/").text
    styles = client.get("/static/styles.css").text
    script = client.get("/static/app.js").text
    assert "aria-label=\"Основная навигация\"" in index
    assert "aria-current=\"page\"" in index
    assert "--tg-theme-bg-color" in styles and "--tg-theme-button-color" in styles
    assert "position: fixed" in styles and "prefers-reduced-motion" in styles
    assert "@media (min-width: 640px)" in styles and "min-width: 320px" in styles
    assert "hero-card" in script and "skeleton-stack" in script
    assert "coverage_rate" in script and "include_missing" in script
    assert "profit_factor =" not in script and "win_rate =" not in script and "net_pnl =" not in script

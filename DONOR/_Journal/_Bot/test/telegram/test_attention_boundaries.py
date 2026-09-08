import asyncio
import os
import subprocess
import sys
from types import SimpleNamespace

from app.application.attention import AttentionItem, AttentionResult, AttentionSummary
from app.application.dtos import ListAllTradesResult
from app.core.accounts.account_id import AccountId
from app.telegram.composition import JournalApplication
from app.telegram.config import TelegramSettings
from app.telegram.handlers import create_router
from app.core.trades.readiness import TradeReadiness, TradeReadinessStatus
from app.core.trades.trade_id import TradeId


class _Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, statement):
        raise AssertionError("the attention use case should be replaced in this boundary test")

    async def flush(self):
        raise AssertionError("the attention use case should be replaced in this boundary test")


class _SessionFactory:
    def __call__(self):
        return _Session()


def test_attention_facade_normalizes_account_id_before_repository_boundary(monkeypatch):
    import app.telegram.composition as composition

    account = AccountId.generate()
    observed = []

    class AttentionFake:
        def __init__(self, *repositories):
            assert len(repositories) == 4

        async def execute(self, *, account_id=None, instrument_id=None):
            observed.append((account_id, instrument_id))
            return AttentionResult(AttentionSummary(0, 0, 0), ())

    monkeypatch.setattr(composition, "GetAttentionCenter", AttentionFake)
    runtime = JournalApplication(_SessionFactory())

    async def exercise():
        await runtime.attention(account_id=account)
        await runtime.attention(account_id=account.value)
        await runtime.attention(account_id=str(account))
        await runtime.attention(account_id=None)

    asyncio.run(exercise())

    assert [item[0] for item in observed] == [account, account, account, None]
    assert all(item is None or isinstance(item, AccountId) for item, _ in observed)


class _Callback:
    def __init__(self, data):
        self.data = data
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class _TelegramRuntime:
    def __init__(self):
        self.attention_account_ids = []

    async def list_all_trades(self, command):
        assert isinstance(command.account_id, AccountId)
        return ListAllTradesResult(())

    async def attention(self, *, account_id=None, instrument_id=None):
        assert isinstance(account_id, AccountId)
        self.attention_account_ids.append(account_id)
        return AttentionResult(AttentionSummary(0, 0, 0), ())


def _handler(router, name):
    return next(item.callback for item in router.callback_query.handlers if item.callback.__name__ == name)


def test_recent_and_attention_telegram_flows_pass_typed_configured_account():
    account = AccountId.generate()
    runtime = _TelegramRuntime()
    router = create_router(runtime, TelegramSettings("token", 1, "db", account))

    async def exercise():
        recent = _Callback("recent_trades")
        await _handler(router, "handle_recent_trades")(recent)
        attention = _Callback("attention")
        await _handler(router, "handle_attention")(attention)
        return recent, attention

    recent, attention = asyncio.run(exercise())

    assert recent.answers
    assert attention.answers
    assert runtime.attention_account_ids == [account, account]


def test_attention_screen_separates_open_lifecycle_from_closed_incomplete():
    account = AccountId.generate()
    open_trade = SimpleNamespace(trade_id=TradeId.generate())
    closed_trade = SimpleNamespace(trade_id=TradeId.generate())
    items = (
        AttentionItem(open_trade, TradeReadiness(TradeReadinessStatus.OPEN), instrument=type("I", (), {"symbol": "BTCUSDT"})()),
        AttentionItem(closed_trade, TradeReadiness(TradeReadinessStatus.INCOMPLETE, ("NET_PNL",)), instrument=type("I", (), {"symbol": "ZECUSDT"})(), missing_labels=("Результат",)),
    )

    class Message:
        def __init__(self):
            self.edited = None

        async def edit_text(self, text, reply_markup=None):
            self.edited = (text, reply_markup)

    class Runtime:
        async def attention(self, *, account_id=None, instrument_id=None):
            return AttentionResult(AttentionSummary(2, 1, 1), items)

    callback = _Callback("attention")
    router = create_router(Runtime(), __import__("app.telegram.config", fromlist=["TelegramSettings"]).TelegramSettings("token", 1, "db", account))
    asyncio.run(_handler(router, "handle_attention")(callback))

    text = callback.answers[1][0][0]
    markup = callback.answers[1][1]["reply_markup"]
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "🟢 Открытые сделки: 1" in text
    assert "⚠ Закрытые, требуют заполнения: 1" in text
    assert "Активная позиция — заполнение не требуется." in text
    assert "Не заполнено:" in text
    assert "attention:open" in callbacks
    assert "attention:closed" in callbacks
    assert callback.answers


def test_python_module_telegram_bot_has_no_eager_import_runpy_warning():
    environment = os.environ.copy()
    environment.update({"TELEGRAM_BOT_TOKEN": "", "DATABASE_URL": "", "JOURNAL_ACCOUNT_ID": ""})
    result = subprocess.run(
        [sys.executable, "-W", "error::RuntimeWarning", "-m", "app.telegram.bot"],
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "RuntimeWarning" not in result.stderr

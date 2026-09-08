from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = PROJECT_ROOT / "app" / "miniapp" / "static"


def test_generic_ui_uses_platform_adapter_instead_of_telegram_runtime_directly():
    app_script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "TradingJournalPlatform" in app_script
    assert "platform.authHeaders()" in app_script
    assert "platform.prepare()" in app_script
    assert "window.Telegram" not in app_script
    assert "X-Telegram-Init-Data" not in app_script
    assert "initData()" not in app_script


def test_telegram_platform_adapter_owns_telegram_webapp_transport():
    adapter = (STATIC_DIR / "telegram-platform.js").read_text(encoding="utf-8")
    index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert "window.Telegram" in adapter
    assert "webApp.ready()" in adapter
    assert "webApp.expand()" in adapter
    assert "X-Telegram-Init-Data" in adapter
    assert "webApp.initData" in adapter

    telegram_sdk = 'src="https://telegram.org/js/telegram-web-app.js"'
    platform_script = 'src="/static/telegram-platform.js"'
    app_script = 'src="/static/app.js"'
    assert telegram_sdk in index
    assert platform_script in index
    assert app_script in index
    assert index.index(telegram_sdk) < index.index(platform_script) < index.index(app_script)


def test_platform_fallback_does_not_create_an_authentication_bypass():
    app_script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert 'provider: "none"' in app_script
    assert "authHeaders() { return {}; }" in app_script
    assert 'authErrorMessage: "Требуется авторизация."' in app_script

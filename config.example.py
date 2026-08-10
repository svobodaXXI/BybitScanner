"""
config.example.py

Безопасный пример конфигурации BybitScanner.

Скопируйте файл как config.py
и заполните локальные секретные значения.

ВАЖНО:
config.py не должен попадать в Git.
"""

# ==================================================
# Bybit API
# ==================================================

BYBIT_CATEGORY = "linear"


# ==================================================
# Market Data
# ==================================================

TIMEFRAME = "5"
CANDLE_LIMIT = 200


# ==================================================
# Pattern Detection
# ==================================================

MIN_TOUCHES = 2
MIN_PIVOT_CHANGE = 0.003
MIN_WEDGE_SCORE = 60


# ==================================================
# Scanner Mode
# ==================================================

MODE = "hunter"
MIN_SCORE = 60
MAX_SYMBOLS = None


# ==================================================
# Confirmation Engine
# ==================================================

VOLUME_PERIOD = 20
VOLUME_Z_WEAK = 1.0
VOLUME_Z_STRONG = 2.0

ATR_PERIOD = 14
MIN_ATR_PERCENT = 0.3

BREAKOUT_LOOKBACK = 3
MAX_BREAKOUT_DISTANCE = 1.5

BREAKOUT_SCORE = 10
VOLUME_SCORE = 10
VOLATILITY_SCORE = 5
FRESHNESS_SCORE = 5
DISTANCE_SCORE = 5

CONFIRMATION_MIN_SCORE = 25


# ==================================================
# Telegram
# ==================================================

TELEGRAM_ENABLED = True

# Никогда не публикуйте реальные значения.
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"

TELEGRAM_TEST_MODE = False

TELEGRAM_DEBUG = True
TELEGRAM_DEBUG_CHARTS = True

DEBUG_MAX_REPORTS = 5
# Trading Workspace - Local / Pinggy / Telegram Runbook

## Назначение

Проверенная процедура запуска development PAPER Trading Workspace после перезагрузки Windows, отключения света или завершения временного Pinggy-туннеля.

Это только DEVELOPMENT / PAPER. Live execution здесь не используется.

## 1. PAPER backend

Открыть отдельное окно PowerShell.

Команды:

    cd C:\BybitScanner
    $env:PYTHONPATH="C:\BybitScanner"
    .\venv\Scripts\python.exe terminal\runtime\paper_http_server.py

Рабочий признак:

    PAPER HTTP runtime listening on http://127.0.0.1:8765

Окно оставить открытым.

Проверка:

    curl.exe http://127.0.0.1:8765/api/health

Ожидается:

    {"ok":true,"mode":"paper"}

## 2. Vite frontend

Открыть второе окно PowerShell.

Команды:

    cd C:\BybitScanner\terminal\frontend
    npm run dev -- --host 127.0.0.1

Рабочий признак:

    Local: http://127.0.0.1:5173/

Окно оставить открытым.

Проверка:

    curl.exe http://127.0.0.1:5173

Должен вернуться HTML Trading Workspace.

## 3. Pinggy tunnel

Открыть третье окно PowerShell.

Основная рабочая команда:

    ssh -p 443 -R0:127.0.0.1:5173 a.pinggy.io

Если Pinggy запросит пароль, пройти запрос и дождаться выдачи временных HTTPS URL.

Обычно выдаются адреса двух типов:

    https://xxxxx.run.pinggy-free.link
    https://xxxxx.free.pinggy.net

Окно Pinggy оставить открытым.

ВАЖНО:
- Pinggy URL временный.
- После закрытия SSH, сообщения Time exceeded, перезагрузки или отключения света старый URL считать недействительным.
- После каждого нового tunnel нужно заново обновлять Telegram Workspace menu button.

## 4. Какой URL использовать

Для Telegram WebView в практической проверке лучше сработал адрес:

    https://xxxxx.free.pinggy.net

Адрес run.pinggy-free.link может показывать промежуточную страницу Enter Site и работать в Telegram нестабильно.

Перед настройкой Telegram проверить URL с компьютера:

    curl.exe -I https://CURRENT-PINGGY-URL

Нужен финальный ответ:

    HTTP/1.1 200 OK

Одна строка:

    HTTP/1.1 200 Connection established

ещё не подтверждает полноценную работу tunnel.

Если появляется:

    Time exceeded

или TLS/SSL handshake error, создать новый Pinggy tunnel.

## 5. Vite allowedHosts

В terminal/frontend/vite.config.ts должны быть разрешены оба suffix:

    .pinggy-free.link
    .free.pinggy.net

Иначе Vite может показать:

    Blocked request. This host is not allowed.

После изменения vite.config.ts Vite должен автоматически вывести:

    [vite] server restarted

## 6. Обновление Telegram Workspace menu button

После получения нового рабочего Pinggy URL:

    cd C:\BybitScanner
    .\venv\Scripts\python.exe -m tools.configure_telegram_workspace "https://CURRENT-PINGGY-URL"

Ожидаемый результат:

    Telegram Workspace menu button configured for the owner chat.

Эту команду повторять после каждого нового Pinggy tunnel.

## 7. Проверка телефона

Последовательность:

1. Проверить новый URL через curl на компьютере.
2. Проверить URL в обычном браузере телефона.
3. Затем открыть Workspace из Telegram.
4. Если браузер телефона работает, а Telegram нет, проблема относится к Telegram WebView, menu URL или allowedHosts.
5. Если Telegram показывает host is not allowed, проверить Vite allowedHosts.
6. Если Telegram открывает старый tunnel, заново выполнить configure_telegram_workspace с текущим URL.

## 8. PAPER execution check

После открытия Workspace найти:

    PAPER Market BUY

Нажать один раз.

Рабочий результат:

    PAPER execution completed

Это подтверждает путь:

    Telegram / browser
    -> Pinggy HTTPS
    -> Vite :5173
    -> /api proxy
    -> PAPER HTTP :8765
    -> TerminalCommandApi
    -> TradingApplication
    -> PaperMarketExecutor
    -> SQLite
    -> COMPLETED
    -> frontend

## Быстрое восстановление после перезапуска

1. Запустить PAPER backend.
2. Запустить Vite.
3. Запустить Pinggy.
4. Проверить новый URL через curl -I.
5. Для Telegram предпочесть .free.pinggy.net.
6. Обновить Telegram Workspace menu button.
7. Проверить браузер телефона.
8. Открыть Workspace в Telegram.
9. Проверить PAPER Market BUY.

## Важные замечания

- Не использовать старый Pinggy URL после завершения tunnel.
- Не закрывать три рабочих окна: PAPER backend, Vite, Pinggy.
- Не добавлять permissive CORS: frontend обращается к /api через Vite same-origin proxy.
- PAPER HTTP server остаётся loopback-only на 127.0.0.1:8765.
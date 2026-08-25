# Trading Workspace — development PAPER launch runbook

## Назначение

Canonical operational runbook для локального development/PAPER запуска Trading Workspace через PAPER backend,
Vite, Pinggy и Telegram Mini App. Live execution в этой схеме не используется.

Для рабочей сессии одновременно должны оставаться открытыми три отдельных окна PowerShell: PAPER backend,
Vite frontend и Pinggy tunnel. Закрытие любого окна ломает соответствующий слой цепочки.

## 1. PAPER backend

Из `C:\BybitScanner`:

```powershell
python -m terminal.runtime.paper_http_server
```

Backend должен слушать `http://127.0.0.1:8765`. В другом окне проверить:

```powershell
curl.exe -i "http://127.0.0.1:8765/api/paper-state?symbol=BTCUSDT"
```

Ожидается `HTTP 200`. Окно backend оставить открытым.

## 2. Vite frontend

Во втором PowerShell:

```powershell
cd C:\BybitScanner\terminal\frontend
npm run dev -- --host 127.0.0.1
```

Frontend должен слушать `http://127.0.0.1:5173`. Проверить frontend и backend через Vite proxy:

```powershell
curl.exe -I "http://127.0.0.1:5173/"
curl.exe -i "http://127.0.0.1:5173/api/paper-state?symbol=BTCUSDT"
```

Оба запроса должны вернуть `HTTP 200`. Окно Vite оставить открытым.

## 3. Pinggy tunnel

В третьем PowerShell использовать именно `127.0.0.1`, не `localhost`:

```powershell
ssh -p 443 -R0:127.0.0.1:5173 a.pinggy.io
```

На Windows `localhost` может разрешиться в IPv6 `::1`; тогда tunnel не попадёт в Vite, слушающий
`127.0.0.1`. Pinggy выдаёт два HTTPS URL. Допустим любой URL, который проходит обе проверки:

```powershell
curl.exe -I "https://PINGGY_URL"
curl.exe -i "https://PINGGY_URL/api/paper-state?symbol=BTCUSDT"
```

Оба запроса должны вернуть `HTTP 200`. Окно Pinggy оставить открытым. После завершения tunnel старый URL
считать недействительным.

## 4. Telegram Workspace menu button

Из `C:\BybitScanner`, подставив проверенный Pinggy URL:

```powershell
.\venv\Scripts\python.exe -m tools.configure_telegram_workspace "https://PINGGY_URL"
```

Ожидаемое сообщение:

```text
Telegram Workspace menu button configured for the owner chat.
```

После получения нового временного Pinggy URL команду нужно выполнить снова.

## 5. Telegram Mini App после смены URL

Telegram Desktop может продолжать использовать старое состояние WebApp/menu button. Если новый URL напрямую
открывается в Chrome, Pinggy root и `/api/paper-state` возвращают `200`, но Mini App не открывается, полностью
закрыть Telegram Desktop и запустить его снова. После полного restart Telegram использует новый Workspace URL.

## Быстрая диагностика

Если Workspace не открывается, проверять строго сверху вниз:

1. PAPER backend на `127.0.0.1:8765`;
2. Vite frontend на `127.0.0.1:5173`;
3. `/api/paper-state` через Vite proxy;
4. Pinggy root URL;
5. `/api/paper-state` через Pinggy;
6. прямое открытие Pinggy URL в Chrome;
7. Telegram Mini App.

Не менять Pinggy URL и не перезапускать случайные компоненты, пока не определён broken layer. Если первые
шесть пунктов работают, проблема относится к Telegram/WebApp state; первое действие — полный restart
Telegram Desktop.

Рабочая цепочка:

```text
Telegram / browser
→ Pinggy HTTPS
→ Vite 127.0.0.1:5173
→ Vite /api proxy
→ PAPER backend 127.0.0.1:8765
```

Checkpoint: `TRADING_WORKSPACE_DEV_LAUNCH_RUNBOOK_RECORDED`.

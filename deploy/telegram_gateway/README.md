# Telegram Gateway — минимальный маршрут (#684)

**Статус на 2026-10-30: Production Gateway развёрнут, двусторонняя связь с VPS подтверждена в PAPER.** PR #685 объединён в `stable/adfb50b-forward` (`f4d5ef34`). Gateway: https://bybitscanner-telegram-gateway.vercel.app. Backend и PAPER DB при подключении Gateway не изменялись; LIVE запрещён.

## Цель
Вместо старого Windows SOCKS/SSH-туннеля использовать один HTTPS Gateway на внешней площадке, которая имеет доступ к Telegram API. Торговая логика остаётся на VPS. Telegram не блокирует открытие/закрытие PAPER-сделок и защиту STOP/TAKE.

## Реализованная схема
- Gateway Worker: аутентифицированная отправка текста с inline-кнопками, фото PNG/JPEG с ограничением размера, повторное использование Telegram photo file_id; relay для getUpdates и разрешённых методов меню/ответа на callback.
- Python: opt-in клиент в существующих telegram_bot.py и telegram_monitoring.py. Один существующий getUpdates consumer на VPS; Worker самостоятельно не опрашивает Telegram.
- Секреты только в защищённой конфигурации: GATEWAY_SHARED_SECRET, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID; на VPS BYBITSCANNER_TELEGRAM_GATEWAY_URL и BYBITSCANNER_TELEGRAM_GATEWAY_SECRET. Секреты не помещать в GitHub или журналы.
- При настройке Gateway попытка отправки текста выполняется ограниченно (не более двух запросов с одним event_id). Возможны дубли при потере подтверждения — это допустимо для обычных уведомлений, **не для торговых команд**.
- Необязательные Durable Objects и отдельная SQLite-outbox исключены из MVP. Нет обязательного ручного разбора UNKNOWN.

## Границы и критерии приёмки
1. Выбран и разрешён реальный хостинг. Проверены VPS → конкретный HTTPS endpoint и Gateway → Telegram API. Общий NETWORK_READY с GitHub/Google не заменяет эту проверку.
2. Подтверждена успешная отправка и фактическое получение сообщения владельцем; кнопки и одна безопасная команда работают через авторизованный канал. Не выдавать /health или Telegram API 200 за прочтение владельцем.
3. При временном сбое Telegram выдаёт отдельное NOT_READY и возобновляет работу без перезапуска торговли; не вызывает дополнительного торгового действия.
4. Проверены ограничения получателя, auth, отсутствие прямого fallback при настроенном Gateway, короткие целевые тесты и логирование без токена.
5. Только после успешной приёмки и разрешения владельца менять работающий Telegram service. Backend, Robot, Scanner и PAPER_AUTO не трогать. LIVE запрещён.

Это транспортное решение без гарантий exactly-once доставки; не добавлять сложную state-machine без доказанной необходимости.

## Фактическая приёмка 2026-10-30
- Production redeploy `READY`; `/health` HTTP 200 `status: up`; неверная авторизация HTTP 401.
- Отправка VPS → Gateway → Telegram API принята; входящая безопасная команда `/terminal` через Gateway обработана Telegram-службой VPS, ответ получен.
- Telegram-служба active, её `/health` HTTP 200; один потребитель `getUpdates`, конфликтов нет.
- Временная недоступность Gateway выявлялась, восстановленная отправка проверена.
- Три развёрнутых Telegram-файла сверены с SHA `b762560d476f6b3a4477efdc13e070af1ae12eb2`. Источник доказательств — отчёт E2E-исполнителя, приведённый владельцем; не путать HTTP 200 Telegram API с доказательством прочтения сообщения человеком.
- `BYBITSCANNER_WORKSPACE_URL` на VPS не настроен: ссылка Терминала по `/terminal` пока ограничена; транспорт Telegram от этого не зависит.
- Для постоянной Telegram-связи Windows, Xray, SOCKS и SSH-туннель не требуются. SSH используется только для администрирования VPS.

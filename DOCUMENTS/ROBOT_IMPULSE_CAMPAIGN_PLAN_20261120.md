# Единая импульсная кампания Робота — проект реализации (20.11.2026)

**Статус:** ACCEPTED DESIGN для границ/единого жизненного цикла; HYPOTHESIS для торговых преимуществ и параметров; **не разрешение на PAPER, merge, release или LIVE**. Владелец направления: ANALYSIS; рабочий Draft: [#1116](https://github.com/svobodaXXI/BybitScanner/pull/1116). Внешний контроль: [планёрка #1077](https://github.com/svobodaXXI/BybitScanner/issues/1077). Уточняет §1.3 \`DOCUMENTS/TRADING_STRATEGY_SPEC.md\`, не заменяет контракт Admission, risk и защиты.

## 1. Цель и единственный владелец исполнения

Не косметический фильтр старого RETEST/закрытой подтверждающей свечи, а **новая приоритетная политика времени входа** для уже существующего паттерна. Паттерн и подтверждённая геометрия указывают направление реализации, границы, инвалидацию, остаточный потенциал и исходный лимит риска. После действительного выхода цены в сторону реализации Робот оценивает **поток реальных агрессивных исполнений и его изменение**, вторично — OI, ADX/DMI, доказанные L2-перестройки, ликвидации и разворотные свечные структуры. Новых IMPULSE_FLOW сигналов, Telegram-карточек, независимых кандидатов или второго торгового движка НЕТ.

Единый маршрут: Scanner pattern → immutable candidate_id/revision/frozen geometry → canonical approval/Admission → policy timing → original protected Robot order owner → actual fill → STOP/TAKE protection → causal manage/partial/fee-aware STOP → optional same-campaign new attempt → Diary/Simulator. Торговые решения и исполнение отделены. Любой новый путь должен доказывать не меньше защитных свойств, чем старый.

## 2. Фазы одной кампании, не набор стратегий

- \`PATTERN_APPROVED\`: существующий кандидат, неизменный snapshot; без entry order.
- \`POST_BREAKOUT_WATCH\`: для каждой семьи используется ЕЁ подтверждённая граница реализации (не общая линия клина). Ранний наблюдатель не тождественен торговому разрешению.
- \`IMPULSE_ELIGIBLE\`: на действительно доступной в тот момент ленте видно направленное усиление агрессоров и подтверждение движения, а источник/временная метка пригодны для решения. Решение может быть раньше старого полного M1-retest, но не обходит Admission, защиту и переделку семейного pre-entry owner в последующих этапах.
- \`ENTRY_PENDING\` → \`OPEN_PROTECTED\`: сначала полноценная защита/владелец ордера, затем фактическое исполнение. Не менять ордера при частичном исполнении или неразрешённом статусе.
- \`MOMENTUM_FADE_WATCH\`: после положительного движения проверяется затухание импульса/потеря ценового воздействия при сохранении риска; фиксированный процент не обязателен.
- \`PARTIAL_INTENT\` → \`PARTIAL_CONFIRMED\` → \`STOP_TIGHTENED\`: лишь проверенная reduce-only частичная продажа/покупка, идентифицированные исполнения и комиссии, затем fee-aware tighten-only STOP остатка. Сначала расчёт фактической/ожидаемой net-прибыли с проскальзыванием, минимальным размером и риском. Повторный вызов по тому же intent не открывает новую сделку.
- \`FLAT_AFTER_EXIT\` → \`REENTRY_WATCH\`: только после доказанной закрытой позиции, отсутствия обязательств/ордеров и установления причины выхода; \`STOP_BE\` не смешивать с обычным защитным STOP. Исходный паттерн остаётся действительным, не исчерпал потенциал (пример 50% — **не нормативный порог**). Нужны ретест/возврат к релевантной паттернной границе или внутрь структуры, причинно подтверждённое затухание противоположного потока и новое направленное усиление. Ликвидации, OI и L2 — дополнительный аргумент при доступности, не выдуманная гарантия «высадки толпы». Новая попытка имеет отдельный idempotent attempt ID и общий campaign/candidate lineage, новый риск/STOP/TAKE и новую полную Admission.
- \`INVALIDATED\` / \`EXPIRED\`: пробита авторитетная инвалидация, срок/потенциал исчерпан, возник конфликт владения или источник ненадёжен. Нет новых входов; ранее открытая защищённая позиция продолжает сопровождаться существующим owner, без отключения защиты.

Никаких автоматических повторных входов после любого STOP. Для Box/Mirror/L-shape/Wedge/будущего Triangle нужны собственные существующие geometry/entry adapters; общие признаки и журнал решений одни.

## 3. Каталог наблюдений (не автоматические голоса «за»)

- \`executed_trade_flow\`: signed notional delta по taker Buy/Sell, ускорение/замедление волны, ценовое воздействие на объём; без synthetic prints.
- \`order_book\`: проверенные snapshot + delta/seq/cts, возраст уровней и реальное исполнение напротив плотности; простой объём стены не означает исполнение или намерение крупного участника.
- \`liquidations\`: точные symbol/side/size/event/receipt от публичного Bybit потока; ликвидация не доказывает направление последующего движения.
- \`oi\`: as-of опубликованные 5m+ данные; изменение OI само по себе не различает новые LONG и SHORT.
- \`ADX/DMI\`: закрытые бары, пересечения +DI/−DI/ADX/20, наклоны и precursor как отдельные причинно известные факты; не брать будущую свечу.
- \`pattern_reversal\`: Double Top/Bottom и прочие фигуры — только вспомогательные аргументы для конкретного host-паттерна.

Каждое наблюдение: \`candidate_id\`, revision, symbol, direction, family, geometry_version, origin, event_ms, receipt_ms, availability_ms, transport_generation, content hash, quality/unknown, correlation_group, pattern-boundary provenance. Независимые группы не удваиваются. Нет «процента уверенности» без калибровки. Потеря ленты/reconnect, незавершённая свеча или snapshot mismatch → UNKNOWN; не конструировать рыночный факт из отсутствия данных. Фиксировать фактическое отсутствие новых сделок при OFF.

## 4. Правила оптимизации (все числовые примеры ненормативны)

Исследовать: (а) ранний вход на растущем направленном потоке, (б) сохранение прежней паттернной логики как контроль, (в) пропуск/поздний вход при противоречии. Старый обязательный «закрытая свеча за границей/ретест» не должен искусственно тормозить эксперимент раннего входа, **но** для торговли потребуется новый доказанный family-specific boundary и защищённый executor до изменения production gate.

Выход: частичная фиксация при **наблюдаемом затухании** и положительной net-экономике, не жёсткие +0.3%, +0.5%, +0.7% или +2R. Долю (включая прежние 25%), число частичных выходов и допустимые задержки тестировать отдельными вариантами с комиссиями, проскальзыванием и остаточным STOP. При отрицательном after-cost результате частичная фиксация безоснóвательна; защитный STOP не расслаблять.

Перезаход: отдельно проверить возврат к паттернной границе и внутри паттерна, угасание противоположной агрессии, подтверждённую поддержку/возобновление исходной волны и неизрасходованный потенциал. Ограничивать число попыток и суммарный campaign risk, не удваивать одновременно открытую позицию и не сбрасывать loss budget после выхода по BE.

## 5. Реализация с минимальной архитектурой

1. **ПЕРВЫЙ CODE SLICE (в этом Draft):** чистая недееспособная policy-функция для исследования \`POST_BREAKOUT_WATCH → IMPULSE_ENTRY_RESEARCH\`, которая принимает исключительно существующий APPROVED host, доказанное время breakout и строго bound source-complete causal flow. Возвращает decision + reason, **trading_authorized=false**; не меняет фазу, БД, сервис, order/admission/STOP. Адресные positive/negative tests для Wedge/L-shape/MIRROR/Box, identity/source/clock/duplicate. Цель — убрать из исследовательского контракта обязательность старого retest для *кандидата на тайминг*, не для реального ордера.
2. **Единый data/evidence adapter:** реальная early publicTrade пригодность и независимая полнота feed или доказанная нижняя граница данных; DMI/OI/L2/liquidation при наличии. Не в owner-thread, без дополнительного WS, не терять защищённые подписки. Отдельные family-specific breakout receipts.
3. **Новый pre-entry protected owner path:** ровно одна попытка для оригинального candidate_id после раннего решения; переподключение к canonical Admission/risk/STOP/TAKE/fees/size, idempotency/restart; старые entry gates убрать только при принятом эквивалентном защищённом пути.
4. **Менеджер затухания:** переиспользовать проверенные owner serialized reduce-only partial/fee-aware STOP из Wedge BE, но НЕ менять неявно существующее Wedge правило +2R. Новый policy-version/allowlist для других паттернов и dynamic exit, отдельная проверка фактических комиссий.
5. **Восстановимый campaign/reentry:** тот же паттерн, новые attempt ID, cumulative risk, no parallel exposure; множество отрицательных restart/partial/late-fill/stop tests.
6. **Одинаковый causal replay:** по exact-ID паттернным сделкам старый baseline vs новый timing-only vs timing+partial vs timing+reentry. Моделировать реальные costs/latency, missed fills и exposure risk; не подменять фактический entry fill касанием OHLC. Out-of-sample holdout без подборки только убыточных сделок; метрики net PnL, drawdown, stop rate, lost winners, risk/exposure, abstain/unknown rate. Исторические пять Wedge STOP имеют M1 и факты PAPER, но **нет полной исходной publicTrade tape, первоначальной геометрии, decision-time receipt и frozen initial STOP**: честный сопоставимый A/B пока невычислим, \`DATA_INSUFFICIENT\`, не ноль и не оценка улучшения.
7. После CI, code review и независимого after-cost доказательства: отдельно разрешённые merge → MONOLITH protected PAPER install → owner-approved PAPER activation и личная приёмка. LIVE запрещён.

## 6. Что заимствуем из зрелых проектов — без копирования архитектуры

- **NautilusTrader:** источник истины — события состояния ордеров/позиций и независимые risk/execution/reconciliation; применить к campaign/attempt idempotency и журналу фактических partial/STOP.
- **Hummingbot Strategy V2:** controller формирует предложение, executor отвечает за позицию, trailing/exit barriers — отдельно; в BybitScanner переиспользовать существующий защищённый Robot owner, не новый executor.
- **Freqtrade:** корректное частичное изменение размера позиции и пересчёт STOP после исполнения, а не по желанию стратегии; переносить экономический принцип без переноса их callback engine.
- **QuantConnect LEAN:** разделение сигналов/portfolio/risk/execution; применять строгую границу чистой policy и авторитетного исполнения.

Источники: https://nautilustrader.io/docs/latest/concepts/events/ ; https://nautilustrader.io/docs/latest/concepts/execution/ ; https://hummingbot.org/strategies/v2-strategies/controllers/ ; https://hummingbot.org/strategies/v2-strategies/executors/positionexecutor/ ; https://www.freqtrade.io/en/stable/strategy-callbacks/ ; https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/overview ; https://bybit-exchange.github.io/docs/v5/websocket/public/trade ; https://bybit-exchange.github.io/docs/v5/websocket/public/orderbook ; https://bybit-exchange.github.io/docs/v5/websocket/public/all-liquidation ; https://bybit-exchange.github.io/docs/v5/market/open-interest

**Критерий принятия:** отдельный реальный PAPER trade по той же паттернной кампании с доказанным качеством источника, protected entry, partial/STOP/reentry (когда применимо), восстановлением, сравнимым after-cost результатом и отдельной приёмкой владельца. Ни PR, ни unit tests, ни искусственная доходность не означают доказанный торговый эффект.

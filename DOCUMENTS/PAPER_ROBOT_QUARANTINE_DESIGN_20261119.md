# PAPER Robot — автономный карантин и локализация отказов (решение владельца 19.11.2026)

Статус: **OWNER DESIGN FROZEN / NOT IMPLEMENTED / NOT DEPLOYED / NOT ACCEPTED**. Владелец поставил P0 выше импульса и геометрии; геометрия отложена до накопления исправленных образцов Редактора.
База: `stable/adfb50b-forward`. Связи: issue #1134, PR #1147/#1148, #682, `DOCUMENTS/PAPER_CONTOUR_INTERNAL_CONSOLIDATION_PLAN_20261027.md`.
Этот контракт не даёт разрешения на merge, изменение VPS, PAPER DB, торговых режимов или LIVE. При конфликте с доказанной safety-границей действует fail-closed.

## 1. Результат и минимальная модель

Ошибка одной независимой цепочки кандидата не превращается в бессрочный account-wide `RECONCILIATION_REQUIRED`. Робот продолжает торговлю по другим доказанно независимым цепочкам, если account-wide exposure, shared risk, integrity и protection достоверны. Каждая изоляция оставляет диагностируемый durable след; карантин сам разбирается с ней в фоне, не вмешиваясь в защиту.

Четыре **логические стадии**, а не четыре новые взаимоисключающие машины статусов:

1. **PRE_INTENT**: кандидат принят/анализируется, но нет durable execution intent, активного ордера, исполнения, позиции, незавершённой команды или защиты. Изоляция допустима лишь после авторитетного proof отсутствия lineage; инвалидировать кандидата, не уничтожая сигнал/history.
2. **ORDER_OR_INTENT**: зафиксировано намерение или виртуальная заявка; fill ещё не подтверждён. Freeze именно этот lineage; reconcile неизменную identity с единым PAPER-исполнителем, не повторять uncertain submit/intent новым ID; проверить fill/partial/cancel прежде чем менять статус.
3. **EXPOSURE**: partial/full fill либо возможно сохраняющаяся экспозиция. STOP/TAKE/закрытие остаются приоритетными; изолируются новые действия этой цепочки, а не её защита. Общие risk/admission gates работают по доказанному aggregate state.
4. **SETTLEMENT**: position/order obligations доказанно завершены; сверить final executions, fees, net PnL, terminal Robot trade и position projection. Не обозначать CLOSED/FLAT лишь по UI/status; расхождение accounting сохраняет локальный или глобальный fence по охвату доказанного риска.

**Quarantine — атрибут/журнал инцидента поверх существующего lifecycle, а не новая исполняющая стратегия.** Статусы журнала: `ISOLATED`, `RECONCILING`, `RESOLVED`, `NEEDS_REVIEW`. Сохранять immutable candidate ID, account/symbol, stage, linkage trade/order/intent/command/protection, error category/fingerprint (санитизированный), observed facts, latest proven state, timestamps, attempts, next_due, outcome, event chronology. Не удалять execution/ledger/fees/fills/trade history. Дедуплицировать по стабильному incident/lineage key; повторная диагностика обновляет ту же запись. Исторические resolved-инциденты доступны для анализа; retention диагностических вложений отдельно от авторитетных торговых фактов.

## 2. Отказоустойчивость и собственность

- **Один PAPER writer:** только существующий сериализованный `PaperRuntime` / store изменяет торговые факты. Карантин и монолитный помощник не создают второго исполнителя, writer, SQLite connection с независимым commit, внешнего бота или брокера. Одна существующая DB и canonical predicates.
- **Bulkhead:** сбор/классификация evidence за пределами protection-owner loop; bounded low-priority work, no blocking waits on trade path, no network/database long transaction while owning protection queue. Перед коротким commit — fresh reread+revision/identity check на авторитетном writer. Непрошедший CAS оставляет quarantined и повторяет read-only diagnosis позже.
- **Protection > admissions > diagnosis:** защитные события и законное уменьшение экспозиции не ждут карантина; diagnosis отступает при ingress backlog/high watermark, unhealthy coverage, busy owner или shared resource pressure. Не повышать capacity ingress и не поглощать overflow под видом исправления.
- **Нет циклических зависимостей:** нормальные заявки не ждут пустой карантинной очереди; quarantine не требует Robot STOP, обновления монолита или завершения всех остальных записей; монолит/maintenance не ждёт исторического разбора инертных объектов. Shutdown/deploy по-прежнему требуют полного доказательства exposure/protection safe-stop.
- **Circuit breaker + retry budget:** bounded concurrent recovery, capped attempts, exponential backoff с jitter, next_due persisted. При неполадке вспомогательного проверяющего он временно отключается/откладывается; объект остаётся в карантине с явной причиной и не создаёт tight loop. На restart продолжить по durable key, без дублирующих actions. Никакого произвольного автоматического patch торгового кода.
- **Scope-aware admission:** quarantine одного pre-intent кандидата не влияет на независимые символы. Order/exposure lineage допускает торговлю другими независимыми символами лишь при доказанной суммарной экспозиции, лимитах, ownership и coverage. Если общий ledger/accounting/position projection/active order set неизвестен — новые входы fail-closed с конкретным blocker и штатной автоматической повторной сверкой. Нельзя снимать fence по TTL.
- **Монолит только вспомогателен:** переиспользовать `RobotRecoveryCoordinator`, существующий PAPER store, `PaperRuntime`, `tools.paper_maintenance` и диагностику; потеря вспомогательного management/control/diagnostics процесса не должна блокировать уже работающую защиту. Сама защита не переносится в помощник.

## 3. Канонический автоматический цикл

`detect -> classify stage -> durable incident -> prove blast radius -> isolate scope -> reconcile under resource budget -> resolve or requeue`.

Каждая итерация использует snapshot revision и immutable execution identities. Кандидат без доказанных обязательств может быть `INVALIDATED` с `paper_quarantine` и продолжением остальной торговли. Для ORDER и EXPOSURE — никаких притворных отмен/fill/FLAT: только существующие authoritative execution/protection/close paths. Settlement завершать только по доказанным ledger facts. Нерешённые случаи возвращать к проверке по next_due, а не к бесконечному синхронному вызову.

Изоляция не удаляет и не подменяет право на STOP/TAKE; read-only мониторинг в Terminal может показывать stage, status, last cause, next attempt и финальный outcome через существующие интерфейсы, без обязательного нового экрана на первой итерации.

## 4. Проверяемая интеграция — не размножать PR и воркеры

1. Сверить открытые #1147 (restart pre-intent) и #1148 (repeated runtime error) на **одной актуальной stable базе**; вынести единый proof `inert candidate`, устранить разницу в predicates и исключить raw exception из durable fingerprint. Приоритет: сначала объединить адресную предисполнительную изоляцию, не затрагивая execution.
2. Доказать на реальных runtime-фактах источник **текущего** durable `RECONCILIATION_REQUIRED` и его lineage. Не сбрасывать существующий fence декларативно. Добавить узкий доказательный reconcile/rehydrate для уже застрявшего pre-intent случая; неоднозначность ордера/позиции вынести в отдельно проверяемую recovery границу.
3. Добавить один bounded recovery tick, использующий существующий owner, только когда нужно; никаких новых внешних scheduler/Temporal/Kubernetes/Redis/Celery/БД. Повторные попытки строго идемпотентны по immutable identity и ограничены ресурсами.
4. Отдельно устранить **фактическую первопричину** `INGRESS_OVERFLOW` пяти аварийных закрытий 17.11; доказана причина CLOSE (overflow), но не upstream bottleneck. Использовать имеющийся `tests/test_robot_protection_overflow_recovery.py` и `terminal/protection_timing.py` на installed/stable lineage; сначала representative offline profile с scratch DB, затем самый узкий fix. Не менять STOP/TAKE/fence или просто увеличивать очередь.
5. Адресные сценарии: inert candidate isolated without global freeze; healthy candidate unaffected; intent/working LIMIT/partial fill cannot be falsely quarantined; unknown ledger/account exposure retains global admission fence; restart resumes same incident and no duplicate command; busy protection makes recovery yield; recovered CLOSED requires fills/fees evidence; helper unavailable does not block protection. Один focused run на изменённое поведение, затем обязательные CI. Owner separately accepts installed VPS PAPER after explicit merge/deploy permissions.

## 5. Подходы зрелых систем: копировать принципы, не инфраструктуру

- **Kubernetes controller/workqueue:** event detection отдельно от reconcile keyed object; rate-limited requeue and `RequeueAfter`; полезен keyed single-flight, no global full DB scan на каждом тике. Источники: https://github.com/kubernetes/client-go/blob/master/ARCHITECTURE.md и https://github.com/kubernetes-sigs/controller-runtime/blob/main/pkg/reconcile/reconcile.go
- **Temporal:** durable retries, bounded timeouts, idempotent activity effects, resume after crash. В нашем случае уже есть durable PAPER storage; не внедрять Temporal server. https://docs.temporal.io/activity-definition и https://docs.temporal.io/encyclopedia/retry-policies
- **Azure bulkhead/circuit breaker:** независимый ресурсный бюджет диагностики, быстрое прекращение неуспешных вспомогательных вызовов, защита от каскадных отказов. Не путать circuit breaker диагностики с запретом STOP/TAKE. https://learn.microsoft.com/azure/architecture/patterns/bulkhead и https://learn.microsoft.com/azure/architecture/patterns/circuit-breaker
- **Explicit non-goals:** второй trading writer, параллельный engine, новый broker, новый сервис, cron-команда, auto-code-fix, очистка исторических операций по TTL, LIVE trading, снятие global safety fence по таймеру.

## 6. Итоговая приёмка

Карантин не парализует независимую PAPER-торговлю; законная защита и risk guard имеют приоритет даже при crash/quarantine backlog; неизвестная shared exposure не маскируется; все переходы durable и воспроизводимы; аварийные CLOSE из `INGRESS_OVERFLOW` устранены лишь после причинного профиля и реальной PAPER-проверки. До доказательства этих условий — `NOT ACCEPTED`.

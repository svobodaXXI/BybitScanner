# Монолит: аварийные состояния, машинный журнал и сквозная автоматизация

**Статус:** DESIGN / NOT IMPLEMENTED. **Дата:** 2026-11-21. **Приоритет:** продолжение ранее разрешённой PAPER-приёмки; дальнейшая автоматизация не должна задерживать восстановление. **Владелец runtime:** существующий `tools.vps_owner_control` → `tools.paper_maintenance`. Второй контроллер, агент торговли и альтернативная БД не создаются.

## 1. Зафиксированный инцидент (только проверенное)

- VPS установил точный Gitless релиз `96d13840550d7892825413a5ef4eeaea89b0a875`; `update-take-closed` owner UUID `610682ab587552ccd5773ef0245de514` завершён `FINISHED_OK`, журнал сообщил `READY: exact installed PAPER release, Telegram and EDITOR_ONLY proven; no Scanner/PAPER_AUTO start`.
- Дополнительный **read-only** `verify_update` остановился на `BLOCKED_DURABLE_OWNERS`. Это **не откат установки** и **не разрешение на START**.
- Штатный PAPER START owner UUID `67ae92671491baac21de6e02d8e855e8` завершён `FAILED`/exit 2: `active_PAPER_Robot_RECONCILIATION_REQUIRED`. START **не повторять**. `Scanner=SCANNER_STOPPED`, `Autopilot=OFF`, `Robot=ROBOT_RUNNING/RECONCILIATION_REQUIRED`; причиной назван один pending entry candidate (точный идентификатор держать в защищённом host journal).
- `_active_required_flat_proof` вернул `None`, `_paper_start_quiescent=False`: это **не указывает**, какой предикат отказал. Предыдущая самостоятельная read-only проверка `SQLiteStore.get_robot_candidate` вернула `SchemaError("persisted Robot candidate JSON is corrupt")`, **но проверяющий скрипт не установил `conn.row_factory = sqlite3.Row`**. `_robot_candidate_from_row` обращается к строке по именам полей; на стандартном tuple возникает `TypeError`, который тот же обработчик ошибочно сообщает как `SchemaError`. Поэтому наблюдение **не подтверждает порчу JSON ни одного поля**. Исправление диагностики — требовать `sqlite3.Row`, как в штатном `prove_take_closed_approved`, и только после этого классифицировать исключение. Фактические владельцы/экспозиция всё ещё не доказаны безопасными.
- Следующий **один read-only этап**: установить `conn.row_factory = sqlite3.Row`, вызвать `SQLiteStore.get_robot_candidate` для **точного** ID и `prove_approved_candidate_never_traded`. Если после корректной конфигурации остаётся `SchemaError`, дополнительно использовать штатный `load_active_robot_candidate_states` (читает состояние без снимка) для разделения ошибок; не делать вывод из некорректно сконфигурированного клиента. Для остальных владельцев потребуется один агрегированный источник категорий, а не серия ручных команд и новых START.
- В ходе релиза также возникали однократный SHA-bound Backend handoff, MAIN quiescence и запрет повтора STOP. PR #1220/#1221 и release receipts описаны в `RUNTIME_KNOWN_FAILURE_FAST_PATH.md`; они **не** доказательство PAPER торговой готовности.

## 2026-11-21 — точный protected legacy Wedge owner кандидат: корректное чтение и защищённый путь

**Host READ-ONLY после исправления row factory:** точный pending candidate `[protected exact candidate ID]` = `protected legacy Wedge owner`, `APPROVED`, `state_revision=1278`, `phase=RETEST_DETECTED`, `robot_state=dict`; `execution` содержит `emergency_close_attempted_at_ms`, `emergency_close_pending=True`, `entry_mode`, `late_market_intent`, `protection_failure`; `prove_approved_candidate_never_traded=False`. Это ожидаемо для **уже исполненного входа** и НЕ даёт права считать кандидата «инертным», а также само по себе не доказывает текущую позицию.

**2026-11-21 runtime proof:** owner supplied a fresh read-only result: `TAKE_CLOSED_PROOF=ONE_APPROVED_PAPER_TAKE_FLAT_IMMUTABLE_V1`, `CURRENT_BACKEND_MATCH=True`, `READ_ONLY_EXIT_CODE=0`. This is exact immutable account-level FLAT + original Market/TAKE proof and current Backend/DB identity; it is **not** proof that canonical reconciliation ran, Robot became PAUSED, or trading started. Keep exact candidate/position IDs only in protected host journal.

**Source-proof, not host-proof:** установленный `terminal.runtime.paper_runtime.PaperRuntime.robot_reconcile` имеет точный `recover_protected_legacy_postfill` для `POST_FILL_NET_RR_BELOW_2 rr=` и `emergency_close_pending`. В `robot_breakout_monitor` есть `_recover_take_closed_legacy_postfill`: проверяет `FLAT`/version 2, ровно original Market fill + internal TAKE fill, отсутствие другого владельца, команд, pending limits, открытых сделок и обязательств, идентичность плана, qty/fees/RR; **только после proof** атомарно добавляет исторический CLOSED trade и очищает pending marker без новой Market-команды. Регрессионный тест `test_take_closed_legacy_orphan_reconciles_atomically_without_new_order` проверяет `REQUIRED → PAUSED`, CLOSED / TAKE, отсутствие дополнительных executions/commands.

**Почему текущий START не решил это:** `tools.paper_maintenance` для уже активного exact-SHA Backend с `ROBOT_RUNNING/RECONCILIATION_REQUIRED` не вызывает `robot_reconcile`; возвращает сохранённый reason, если это не особо разрешённый ingress overflow. Исторический reason кандидата имеет timestamp от 20.11; сообщение в failed START 21.11 — **не новая попытка reconciliation**. Не повторять `start` или `POST /api/robot/reconcile` вслепую.

**Следующий доказательный барьер:** получить **один** защищённый read-only повтор `prove_take_closed_approved` на неизменённой PAPER SQLite с исходным pinned snapshot из protected one-flat journal, либо эквивалентный existing owner proof; отдельно проверить текущую backend/DB identity и защиту. Если result `ONE_APPROVED_PAPER_TAKE_FLAT_IMMUTABLE_V1`, нужен монолитный однократный reconciliation intent, а **не** повтор release/STOP/START. Если proof fails, держать admission CLOSED и сообщить **конкретный отказ** без подмены фактов.

**Для будущей автоматики:** `CANDIDATE_READ_ERROR` сначала проверяет row factory; если кандидат читается и pending emergency=true, event `LEGACY_TAKE_CLOSED_OWNER_PENDING` с красным `ADMISSION_CLOSED`, не `NEVER_TRADED`. Existing protected proof → one-shot canonical reconciliation → verify `PAUSED`, terminal candidate, closed trade/net fees, no pending owners → only then ordinary owner START. GitHub получает redacted state, без exact trade/candidate ID и финансовых сведений. **Runtime-автоматизация пока не реализована**.

## 2. Минимальная целевая схема (одна система)

```text
PAPER Backend / Scanner / Robot / Telegram / systemd
                 |
   canonical read-only state + protected owner receipts
                 |
      tools.vps_owner_control / paper_maintenance
                 |
  append-only host incident journal (root-owned, no secrets in argv)
                 |
  bounded redacted GitHub status publisher (outbound only)
                 |
 GitHub issue/action artifact: public summary, SHA, state, event_seq, UTC
                 |
  assistant reads journal + exact repo/spec + immutable host receipt
                 |
 existing monolith: safe one-shot recheck/repair, or BLOCKED escalation
```

- **Истина:** PAPER SQLite, авторитетный runtime API, systemd и локальные защищённые receipts остаются authority. GitHub — **зеркало обезличенных свидетельств**, а не торговый ledger и не источник разрешений. Отсутствующий/старый GitHub статус трактовать как `UNKNOWN`, не как `FLAT` или `SAFE`.
- **Один producer:** добавить публикацию к существующему owner control/maintenance boundary, без нового фонового watchdog, независимого STOP/START, SQL writer или самодельного trading API. Передавать состояния после commits/receipts и при переходе в известный BLOCKED. По расписанию допускается *только read-only* resync heartbeat с проверкой TTL/последовательности.
- **Один outbound publisher:** минимальный root-owned read-only exporter фиксированной JSON-схемы, очередь с bounded spool/TTL, идемпотентный `event_id`, rate limit/backoff и отсутствие повторов управляющего действия. Если GitHub недоступен — монолит сохраняет безопасный host state; экспорт не делает сервисы и торговлю зависимыми от сети.
- **Безопасность публичного GitHub:** только агрегированные флаги (`PAPER_ONLY`, `ADMISSION_CLOSED`, `REQUIRED`, `OWNER_UNRESOLVED`, `RELEASE_INSTALLED`, `STOP_UNPROVEN`), фиксированные reason codes, полные approved SHA / owner request UUID если нет угрозы эксплуатации, UTC/event_seq/expiry. **Не публиковать** raw candidate/trade IDs, конкретные позиции, символы/объёмы/цены, PnL, payload сделок, SQLite, endpoint tokens, SSH paths/keys, host addresses, полные stack traces и произвольные exception strings. Exact-ID detail остаётся на VPS или в отдельном приватном хранилище с явным доступом; публичный repo **не подходит** для приватного журнала.
- **Целостность:** SHA/instance identity, источник события, seq и время, флаг `source_complete`, category error, SHA-256 sealed host record; отсутствие пропусков sequence, binding к установленному SHA и UUID. Подписанный host manifest/проверяемый digest возможен как расширение; не выдавать digest за доказательство торговой безопасности. Только allowlisted fields; секреты исключать **до** сериализации.
- **Ролевое разделение:** ассистент может без участия владельца читать GitHub, сопоставлять с exact-SHA кодом и предлагать/готовить исправление. GitHub issue, PR, комментарий и успешная CI **не** дают право на runtime mutation. Только штатный уже разрешённый owner action проходит текущие STOP/TAKE/admission/protection/position gates. LIVE запрещён.

## 3. Состояния и автоматические действия

| Событие | Автоматическое действие | Запрет / эскалация |
| --- | --- | --- |
| `RELEASE_REQUEST_ACCEPTED` | сохранить request UUID, poll status; при SSH reconnect — прочитать тот же UUID | не submit нового UUID при таймауте |
| `STOP/START_FAILED` | read-only evidence snapshot + GitHub redacted event; искать точный known-failure fast path | повтор STOP/START и очистка receipt |
| `BACKEND_EXIT_PROVEN` | продолжать установленный одноразовый handoff только по seal/identity | неизвестный SIGINT outcome → BLOCKED |
| REQUIRED + CANDIDATE_READ_ERROR` | оставить admission закрытым; сначала проверить правильные `sqlite3.Row` и exact-ID, затем различие JSON-state/snapshot штатным read-only методом; классифицировать `MALFORMED_JSON` / `INVALID_SHAPE` / `HASH_MISMATCH` / `UNKNOWN`, затем определить earliest durable producer event | не восстанавливать JSON догадками, не менять status, не выполнять reconcile до полной доказанности владельцев |
| `PAPER_LEDGER_OWNER_UNRESOLVED` | read-only diff по всем pending candidates/trades/orders/commands/obligations/checkpoints/position projections через allowlisted project diagnostic; минимальный безопасный summary | нельзя считать `FLAT` по нулевой проекции или одним HTTP 200 |
| `FLAT_AND_RECONCILIATION_PROVEN` | только уже разрешённая существующая canonical recovery в монолите, с одноразовой защищённой квитанцией | не открывать admission по GitHub записи |
| `GITHUB_UNAVAILABLE` / `SEQUENCE_GAP` | bounded spool + degraded observability, host remains authoritative | никаких торговых действий, основанных на неполном зеркале |

**Автодействия по умолчанию — диагностика и публикация**, не принудительное «лечение» неизвестных денег/экспозиции. После доказанного terminal-safe incident можно пользоваться существующим одноразовым штатным recovery; неизвестный источник/неконсистентный JSON/позиция или защита → карантин **только проблемного кандидата/символа**, если существующий Robot owner fence это уже поддерживает и независимый риск-гейт доказан. В противном случае оставить глобальный admission закрытым; не вводить оптимистический per-symbol bypass.

## 4. Схема обезличенного события (контракт, не runtime endpoint)

```json
{
  "schema_version": 1,
  "event_id": "deterministic-hash-of-source-and-sequence",
  "seq": 0,
  "observed_at_utc": "ISO-8601",
  "source": "existing-owner-monolith",
  "installed_sha": "40-hex-sha",
  "owner_request_id": "optional-32-hex",
  "mode": "PAPER",
  "scanner": "STOPPED|RUNNING|UNKNOWN",
  "robot": "READY|PAUSED|RECONCILIATION_REQUIRED|STOPPED|UNKNOWN",
  "autopilot": "OFF|ON|UNKNOWN",
  "admission": "CLOSED|OPEN|UNKNOWN",
  "issue_code": "CANDIDATE_READ_ERROR",
  "scope": "OWNER_UNRESOLVED",
  "host_evidence_digest": "sha256-only",
  "source_complete": false,
  "expires_at_utc": "ISO-8601"
}
```

The example contains symbolic values, **not** the actual current VPS state. No raw IDs/contents. Public issue text generated only by a strict schema validator.

## 5. Этапы внедрения (не новая инфраструктурная эпопея)

1. **Сейчас:** сохранить доказательства данного случая и его один следующий read-only discriminator; устранить блокер текущего PAPER START до автоматизации. Документация не подтверждает восстановление.
2. **Минимальный PR после локализации причины:** встроить единый `snapshot_incident` read-only reporter в существующий monolith action status path, включая source SHA / request ID, reason code и факт невалидного JSON; тесты на отсутствие секретов, stale/unknown, корректность owner reference, no mutation.
3. **GitHub bridge:** append-only redacted status публикация из VPS только outbound, отдельный scoped token с минимальными правами; хранение неизменяемых полных данных только локально. Проверить транспорт, idempotency, interruption/reconnect, no retry/replay; не выдавать issue comment за receipt.
4. **Ограниченная автоматическая реакция:** таблица известных причин → только доказанные read-only checks и существующие идемпотентные безопасные owner transitions; запрещены обходы gate. При `UNKNOWN` автоматом публиковать состояние и прекращать торговые мутации.
5. **Приёмка владельца:** искусственный `REQUIRED`/invalid JSON/restart/reconnect/GitHub outage в изолированном тесте → одна запись host journal и GitHub, ноль raw secrets и повторных команд, ни одного опасного START, проверенная корреляция с protected receipt; только потом наблюдать на реальном PAPER с owner approval.

**Метрика успеха:** число ручных PowerShell-раундов на известный инцидент (цель 0), доля автоматической классификации известных отказов, число повторных опасных owner intents (цель 0), время от события до доступного GitHub redacted evidence и абсолютное отсутствие утечки данных. Не считать PR/CI результатом внедрения.

**Граница:** текущая реализация журнала GitHub/автореакций **отсутствует**; существующие системные журналы, `vps_owner_control`, защищённые receipts и GitHub PR — переиспользуемые компоненты. Этот документ не разрешает автоматическую торговлю или LIVE.

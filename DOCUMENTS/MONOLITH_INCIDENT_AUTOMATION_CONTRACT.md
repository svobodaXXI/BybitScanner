# Монолит: аварийные состояния, машинный журнал и сквозная автоматизация

**Статус:** DESIGN / NOT IMPLEMENTED. **Дата:** 2026-11-21. **Приоритет:** продолжение ранее разрешённой PAPER-приёмки; дальнейшая автоматизация не должна задерживать восстановление. **Владелец runtime:** существующий `tools.vps_owner_control` → `tools.paper_maintenance`. Второй контроллер, агент торговли и альтернативная БД не создаются.

## 1. Зафиксированный инцидент (только проверенное)

- VPS установил точный Gitless релиз `96d13840550d7892825413a5ef4eeaea89b0a875`; `update-take-closed` owner UUID `610682ab587552ccd5773ef0245de514` завершён `FINISHED_OK`, журнал сообщил `READY: exact installed PAPER release, Telegram and EDITOR_ONLY proven; no Scanner/PAPER_AUTO start`.
- Дополнительный **read-only** `verify_update` остановился на `BLOCKED_DURABLE_OWNERS`. Это **не откат установки** и **не разрешение на START**.
- Штатный PAPER START owner UUID `67ae92671491baac21de6e02d8e855e8` завершён `FAILED`/exit 2: `active_PAPER_Robot_RECONCILIATION_REQUIRED`. START **не повторять**. `Scanner=SCANNER_STOPPED`, `Autopilot=OFF`, `Robot=ROBOT_RUNNING/RECONCILIATION_REQUIRED`; причиной назван один pending entry candidate (точный идентификатор держать в защищённом host journal).
- `_active_required_flat_proof` вернул `None`, `_paper_start_quiescent=False`: это **не указывает**, какой предикат отказал. При чтении точного кандидата через `SQLiteStore.get_robot_candidate` получен `SchemaError("persisted Robot candidate JSON is corrupt")`. В `terminal/persistence/sqlite_store.py` это сообщение выдаётся при JSON decode ошибки `signal_snapshot_json` или `robot_state_json`. Повреждение всей SQLite, тип ошибочного поля и наличие реальной экспозиции **ещё не доказаны**.
- Остался следующий **read-only** этап: штатный `load_active_robot_candidate_states` для разграничения повреждённого `robot_state_json` и сигнального снимка. Если падает, нужен один агрегированный источник безопасных категорий, а не серия ручных команд и новых START.
- В ходе релиза также возникали однократный SHA-bound Backend handoff, MAIN quiescence и запрет повтора STOP. PR #1220/#1221 и release receipts описаны в `RUNTIME_KNOWN_FAILURE_FAST_PATH.md`; они **не** доказательство PAPER торговой готовности.

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
| `REQUIRED + CANDIDATE_JSON_DECODE_ERROR` | оставить admission закрытым; проверить различие JSON-state/snapshot штатным read-only методом; классифицировать `MALFORMED_JSON` / `INVALID_SHAPE` / `HASH_MISMATCH` / `UNKNOWN`, затем определить earliest durable producer event | не восстанавливать JSON догадками, не менять status, не выполнять reconcile до полной доказанности владельцев |
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
  "issue_code": "CANDIDATE_JSON_DECODE_ERROR",
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

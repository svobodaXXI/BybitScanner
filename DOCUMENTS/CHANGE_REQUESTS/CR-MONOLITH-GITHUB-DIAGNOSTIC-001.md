# CR-MONOLITH-GITHUB-DIAGNOSTIC-001 — Двусторонний мост

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-MONOLITH-GITHUB-DIAGNOSTIC-001",
  "title": "Двусторонний мост — изолированный протокол диагностики",
  "governance_type": "DESIGN_TO_IMPLEMENTATION_CHANGE_REQUEST",
  "status": "IN_PROGRESS",
  "revision": "1.2",
  "lifecycle_stage": "IMPLEMENT",
  "objective": "Сократить ручные PowerShell-шаги: запрос диагностики через GitHub → фиксированное read-only наблюдение → проверяемый коррелированный ответ.",
  "non_goals": [
    "Прямой SSH, произвольные команды, новый исполнитель релизов, торговые полномочия."
  ],
  "approved_scope": [
    "Офлайн прототип и интегрированный диагностический цикл: строгий протокол, независимые Ed25519 ключи, переиспользование observe(), durable journal, ограниченный GitHub transport и проверка повторной доставки. Подготовка изолированного host wiring и независимого issuer; реальная активация только после защитных ворот."
  ],
  "prohibited_scope": [
    "Любая активация VPS до отдельного разрешения и закрытия защитных ворот; публичный комментарий не является полномочием; LIVE, START, STOP, UPDATE, SQL и торговые мутации."
  ],
  "authoritative_references": [
    "AGENTS.md",
    "DOCUMENTS/WORKSTREAM_COORDINATION.md",
    "GitHub coordination #1077",
    "RISK-MONOLITH-01"
  ],
  "context_scope_paths": [
    "tools/github_status_reporter.py",
    "tools/vps_owner_control.py"
  ],
  "context_test_paths": [
    "tests/test_github_status_reporter.py"
  ],
  "external_reference_inspiration": [],
  "context_findings": [
    "Наблюдатель уже доставил первый отчёт в #1212; обратный маршрут существует; текущий формат не доказывает подлинность и не принимает запросы."
  ],
  "approved_decisions": [
    "Сначала изолированная диагностика, никаких runtime mutations; GitHub только транспорт; раздельный доверенный издатель запросов и подписант ответов; Ed25519 из существующей зависимости."
  ],
  "unresolved_decisions": [
    "Владелец поручил минимальную активацию при выполнении обязательных защитных ворот. Требуются CI, защищённая настройка ключей и issuer environment, доказательство доставки новым токеном, exact-SHA release и коррелированный реальный roundtrip."
  ],
  "acceptance_criteria": [
    "Изолированный signed roundtrip с точным request ID и digest; отклонение подмены, устаревания, неправильного назначения, неразрешённого действия и повтора до чтения API.",
    "После отдельной активации: настоящий запрос и проверяемый ответ без PowerShell владельца; до этого runtime acceptance pending."
  ],
  "verification_requirements": [
    "Existing PAPER maintenance CI includes protocol and observer regressions. No live IO in tests."
  ],
  "risks": [
    "RISK-MONOLITH-01 remains OPEN. Rotation, independent key pinning and replay/durable delivery evidence required before activation."
  ],
  "rollback_boundaries": [
    "Пока только неактивный код; existing observer, service files, owner monolith, trading unchanged."
  ],
  "implementation_phases": [
    {
      "id": "TASK",
      "status": "COMPLETED"
    },
    {
      "id": "SPEC",
      "status": "COMPLETED_HUMAN_APPROVED"
    },
    {
      "id": "CONTEXT",
      "status": "COMPLETED"
    },
    {
      "id": "IMPLEMENT",
      "status": "IN_PROGRESS"
    },
    {
      "id": "VERIFY",
      "status": "NOT_STARTED"
    },
    {
      "id": "RECORD",
      "status": "NOT_STARTED"
    }
  ],
  "current_phase": "IMPLEMENT",
  "current_checkpoint": "ISOLATED_HOST_WIRING_AND_ISSUER_CI_PENDING",
  "implementation_status": "IN_PROGRESS",
  "next_phase": "VERIFY",
  "next_phase_authorization": "OWNER_REQUESTED_MINIMAL_ACTIVATION_SUBJECT_TO_GATES",
  "related_commits": [
    {
      "phase": "BASELINE",
      "commit": "fa5925b6d75c644049e066ceb358373e82fcfc52"
    }
  ],
  "repository_sync": {
    "branch": "stable/adfb50b-forward",
    "baseline_local_head": "fa5925b6d75c644049e066ceb358373e82fcfc52",
    "status": "GITHUB_FIRST"
  },
  "amendment_history": [
    {
      "revision": "1.0",
      "reason": "Owner authorized development of the bidirectional bridge, not activation.",
      "date": "2026-11-22"
    },
    {
      "revision": "1.1",
      "reason": "Consolidate durable journal, bounded transport and authenticated cycle into one development delivery; runtime activation remains prohibited.",
      "date": "2026-11-22"
    }
  ]
}
```
<!-- CHANGE_REQUEST_METADATA_END -->

## Границы первого этапа

Транспорт GitHub не является доверенным. Запрос содержит только version, operation=observe, audience, request_id, issued_at, expires_at. Срок жизни не более 300 секунд; независимый доверенный issuer подписывает канонический формат. На VPS проверяется заранее доверенный публичный ключ; отдельно подписывается ответ, привязанный к полному digest запроса. Только существующий allowlist наблюдателя, не произвольный URL/команда. Не считать этот отчёт торговой authority или атомарным снимком DB.

В офлайн-прототипе доверенные ключи, часы, источник наблюдений и атомарная резервация передаются явно. Нет запускаемого процесса, runtime wiring, чтения токена или автоматического сетевого обращения. Тестовая резервация не доказывает долговечность. Следующий этап — реальный защищённый транспорт с независимым issuer, pinned keys, durable request/response ledger, bounded polling, rate limits, kill switch и отдельным owner opt-in; не подключать до закрытия RISK-MONOLITH-01. Этап релизов вызывает только существующий монолит после отдельной owner authority, не входит в этот PR.

## Единая поставка диагностического контура

Протокол #1230 объединяется с отдельным журналом подписанных запросов и ответов, атомарной записью до observe(), ограниченным опросом #1212 и восстановлением доставки после неопределённого POST. Повтор публикации возможен только теми же подписанными байтами; дедупликация по request ID и digest. При прерывании между резервированием и сохранением ответа повторное наблюдение запрещено; потерянный результат не выдаётся за доказанный. Просроченные ответы проверяются как исторические, не как текущий статус. Неотправленные ответы не удаляются. Тесты не используют реальные ключи, сеть или торговый runtime. Реальная активация, ротация токена, доверенный issuer, защищённый key/release pinning и гарантированный интервал запуска остаются отдельными защитными воротами.

## Минимальная активация (22.11.2026)

Отдельная ветка diagnostic-issuer создаётся **только из проверенного интегрированного релиза**, после review и merge. Запрос инициируется обновлением единственного файла .github/diagnostic-request.json (request_id, issued_at, expires_at). Workflow запускается только push в эту ветку, не issue_comment, не PR. Новый Issues-only токен наблюдателя не должен иметь Contents/Actions/Workflows write. Доверенная Contents-write сторона и защищённый GitHub Actions environment bybitscanner-diagnostic-issuer — независимый issuer; секрет DIAGNOSTIC_ISSUER_SEED только в environment, разрешённая deployment branch только diagnostic-issuer, без доступа из PR/других веток. Любой, кто может изменить код на доверенной ветке, входит в доверенную issuer boundary; не выдавать это за изоляцию от владельца репозитория. Проверить настройки и реальное срабатывание workflow, не считать GitHub-коннектор способным trigger до evidence.

Одноразовая настройка: независимые Ed25519 seed (issuer в environment, responder только VPS), public pins в .github/diagnostic-public.json (audience, issuer_public, responder_public), root-only 0700 каталог /etc/bybitscanner/github-diagnostic и 0600 config.json (enabled, release_sha, audience, issuer_public, responder_seed). Ни private seed, ни PAT не публиковать. Реальный VPS exact-SHA pin и отдельный durable journal: tools.github_diagnostic_runtime --initialize только впервые; отсутствующий/повреждённый прежний journal не восстанавливать автоматически. Включение только через tools.vps_owner_control -> tools.paper_maintenance github-diagnostic-enable. Таймер 30 секунд после завершения, один observe за цикл, GitHub endpoint фиксирован. Kill switch: root-controlled enabled=false, polling не выполняет IO; для отключения таймера root/systemd без затрагивания торговых служб. При смене release SHA наблюдение fail-closed до подтверждённого обновления pin. Автоматизация lifecycle key/release pin отложена. Принимается только настоящий signed roundtrip, в котором ответ проверен по заранее закреплённому public key и digest запроса; unsigned status не заменяет это. Состояние существующего observer не является доказательством закрытия RISK-MONOLITH-01.


## Продолжение существующего диагностического pin при UPDATE

Предлагаемое изменение после доказанного signed roundtrip: при штатной owner-authorized Gitless установке точного stable SHA использовать уже вызываемую из монолита подготовку units для ограниченного локального продолжения существующего opt-in. Не создавать нового исполнителя релизов. В root-only конфигурации атомарно менять исключительно release_sha, только если защищённые old.json/target.json, неизменённый target manifest, canonical STOP confirmation и полный installed-release verification доказывают прямой переход от прежнего pin. Проверить защищённый journal без его изменения, pinned sources и неизменность обоих диагностических unit-файлов в старом/новом manifest и на хосте. Использовать существующий release lock и journal lock. Disabled/unconfigured оставлять без изменений. Не активировать или перезапускать таймер, не менять ключи, token, audience или replay receipts. При неизвестности — pin не продвигать, диагностический контур остаётся fail-closed; ограниченный timeout и отдельный статус не меняют существующие PAPER readiness/STOP/START gates. Исключительные handoff и пропуск промежуточного pin не получают автоматической authority. Требуются CI и отдельное разрешение на merge/deploy; после первого штатного UPDATE — новый подписанный запрос и независимая проверка ответа с новым build SHA, без ручного repin. До этого эксплуатационная приёмка продолжения не доказана.

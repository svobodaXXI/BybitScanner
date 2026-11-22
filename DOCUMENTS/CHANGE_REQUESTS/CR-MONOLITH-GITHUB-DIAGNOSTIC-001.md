# CR-MONOLITH-GITHUB-DIAGNOSTIC-001 — Двусторонний мост

<!-- CHANGE_REQUEST_METADATA_BEGIN -->
```json
{
  "schema_version": "1.0",
  "id": "CR-MONOLITH-GITHUB-DIAGNOSTIC-001",
  "title": "Двусторонний мост — изолированный протокол диагностики",
  "governance_type": "DESIGN_TO_IMPLEMENTATION_CHANGE_REQUEST",
  "status": "IN_PROGRESS",
  "revision": "1.0",
  "lifecycle_stage": "IMPLEMENT",
  "objective": "Сократить ручные PowerShell-шаги: запрос диагностики через GitHub → фиксированное read-only наблюдение → проверяемый коррелированный ответ.",
  "non_goals": [
    "Прямой SSH, произвольные команды, новый исполнитель релизов, торговые полномочия."
  ],
  "approved_scope": [
    "Офлайн прототип по текущей команде владельца: строгий протокол, независимые Ed25519 ключи, переиспользование observe(), проверка корреляции и отклонения повторов."
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
    "Конкретный доверенный issuer и защищённое размещение ключей; доставка, журнал резервации/ответов с сохранением после reboot, лимиты, pinning release, owner enable/disable. Эти компоненты не реализованы и не авторизованы к активации."
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
  "current_checkpoint": "OFFLINE_PROTOCOL_CI_PENDING",
  "implementation_status": "IN_PROGRESS",
  "next_phase": "VERIFY",
  "next_phase_authorization": "AUTHORIZED_OFFLINE_ONLY",
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
    }
  ]
}
```
<!-- CHANGE_REQUEST_METADATA_END -->

## Границы первого этапа

Транспорт GitHub не является доверенным. Запрос содержит только version, operation=observe, audience, request_id, issued_at, expires_at. Срок жизни не более 300 секунд; независимый доверенный issuer подписывает канонический формат. На VPS проверяется заранее доверенный публичный ключ; отдельно подписывается ответ, привязанный к полному digest запроса. Только существующий allowlist наблюдателя, не произвольный URL/команда. Не считать этот отчёт торговой authority или атомарным снимком DB.

В офлайн-прототипе доверенные ключи, часы, источник наблюдений и атомарная резервация передаются явно. Нет запускаемого процесса, runtime wiring, чтения токена или автоматического сетевого обращения. Тестовая резервация не доказывает долговечность. Следующий этап — реальный защищённый транспорт с независимым issuer, pinned keys, durable request/response ledger, bounded polling, rate limits, kill switch и отдельным owner opt-in; не подключать до закрытия RISK-MONOLITH-01. Этап релизов вызывает только существующий монолит после отдельной owner authority, не входит в этот PR.

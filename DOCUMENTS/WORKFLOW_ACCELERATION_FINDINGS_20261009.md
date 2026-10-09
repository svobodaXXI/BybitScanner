> **Current owner Wedge RR decision (2026-10-09):** minimum executable RR for Falling/Rising Wedge is **1.5:1**, not 2:1. See `DOCUMENTS/WEDGE_ROBOT_RR_OWNER_DECISION_20261009.md`. PR #440 was closed unmerged; Box and L-shape remain governed by their own thresholds.

# BybitScanner — доказательный разбор веток и PR (этап 1)
Дата: 2026-10-09. Статус: read-only findings, **без runtime/code-изменений**.
Связан с `DOCUMENTS/WORKFLOW_ACCELERATION_AUDIT_PLAN_20261009.md`.

## Проверено непосредственно в GitHub
- Репозиторий: `svobodaXXI/BybitScanner`. Default branch `main`.
- Compare `main...stable/adfb50b-forward`: `diverged`, 34 ahead stable / 106 behind stable; merge base `adfb50b758181c3ed9bc3670b00fe842ffa8d08a`; base commit main в ответе `ea956e234d5aae3620d3f81d08b6bf4451bd281d`. Это **не** основание для merge/reset/rebase.
- Выборка: 30 последних PR пользователя, от #401 до #437 (в списке есть пропуски номеров). Метаданные предоставили created/merged, но не timestamps CI, ожидания владельца или фактического PAPER acceptance. На этих данных нельзя вычислять end-to-end lead time.
- PR #426 и #427 имеют base `stable/adfb50b-forward`, описаны как точные backport upstream #396/#397. PR #437 также base stable. Следовательно, в рассмотренных PR `main` — upstream отдельных фиксов, `stable` — селективная рабочая линия. Это установленная практика в выборке, но не универсальная гарантия для будущих PR.
- PR #404 (`main`): переинтерпретировал ярлык «Запуск робота» как ROBOT-only; PR #405 (`main`): восстановил owner-approved `ALL` из-за неверного понимания контракта. Прямое свидетельство предотвращаемой переделки. Актуальный handoff подтверждает `start_robot_runtime.bat ALL` на ноутбуке. Не возвращать #404.
- PR #423–#437: серия schema/runtime, сетевой изоляции owner-thread, protection и UI. Не считать эти уже слитые решения невыполненной работой.

## Наблюдение по PR-циклу
В выборке 30 PR с 29 отмеченными merge timestamp (один без). Большинство слиты быстро, но метрика open→merge не равна времени до полезного PAPER результата. Особенный кейс #437: создан 2026-10-08 23:16:06Z, слит 2026-10-09 06:01:54Z; нельзя утверждать, чем объясняется промежуток, без проверки CI/reviews/owner approval. Не делать вывод об эффективности агентов по одиночным интервалам.

## Ранжированные выводы
1. **P0 — guard против неверной интерпретации owner UX.** Перед правкой launch intent или Telegram control сравнить задачу с документированным owner contract и последними корректирующими PR. Измерение пользы: отсутствие возвратных PR по тем же контрактам. Не создавать новый gate, если существующий `AGENTS.md` + `ASSISTANT_PROTOCOL.md` достаточен; сначала установить, почему его не применили.
2. **P0 — осознанный backport workflow.** Для нового PR явно указывать target branch, upstream SHA/patch и зависимости. В PR #426/#427 это уже применялось успешно; рекомендуем использовать имеющийся формат, а не новый pipeline. Stable не сливать с main автоматически.
3. **P1 — единый актуальный указатель следующего шага.** Прежде чем объявлять `QUEST_STATE`/`BACKLOG` устаревшими глобально, проверить все активные разделы и фактическую owner-команду. Затем исправить только найденную навигационную нестыковку в рамках отдельного документационного change, не размножая статусы.
4. **P1 — критический путь PAPER после backport.** Риск owner-thread I/O следует проверять по новой реализации и свежим метрикам, а не считать старое поведение живым дефектом только по incident history. Следующий этап аудита read-only.

## Что пока не доказано
- Реальные bottlenecks CI: нет проверенных длительностей runs/queues.
- Время от задачи до принятой PAPER-сделки: нет связанной выборки acceptance timestamps.
- Изменение runtime latency после #424/#426–#431: нужны реальные метрики, без запуска агентом.
- Полная согласованность всех backlog/quest разделов: пока просмотрены верхние записи.
- Влияние веточного расхождения на конкретную новую задачу: требует task-scoped diff.

## Решение о реализации
**Не менять** `main`, `stable`, runtime или workflow без отдельной доказанной проблемы. Следующий read-only срез: CI/review evidence на representative PR и карта узких мест Paper owner flow. Эксплуатационная очередь прежняя: owner-only первый PAPER-запуск ноутбука → Robot Stability → Geometry Quality.

Источники: https://github.com/svobodaXXI/BybitScanner/compare/main...stable/adfb50b-forward ; https://github.com/svobodaXXI/BybitScanner/pull/404 ; https://github.com/svobodaXXI/BybitScanner/pull/405 ; https://github.com/svobodaXXI/BybitScanner/pull/426 ; https://github.com/svobodaXXI/BybitScanner/pull/427 ; https://github.com/svobodaXXI/BybitScanner/pull/437 .

# BybitScanner — аудит CI / PAPER-проверок, этап 2 (09.10.2026)

Статус: **доказательный read-only срез; не является завершённым профилированием runtime или CI**.
Основа: `DOCUMENTS/WORKFLOW_ACCELERATION_AUDIT_PLAN_20261009.md` и `DOCUMENTS/WORKFLOW_ACCELERATION_FINDINGS_20261009.md`.

## Проверенные GitHub Actions факты

GitHub connector `fetch_commit_workflow_runs` для **head SHA** проверенных PR:
- PR #405, `f0f52231cc02bd30e8a7a4d10e490b1be11a8ceb`: successful `Developer workflow checks` run **37598235745**, successful `Robot PAPER acceptance` run **37598235731**.
- PR #427, `095908f2e8d2e0fd67686e622a255a4454c60159`: successful `Robot PAPER acceptance` run **37755287072**.
- PR #435, `0a444eeaff74ee99db824237afa7cd9606d08e53`: successful `Robot PAPER acceptance` run **37813511593**.
- PR #437, `dd669b97c32608ce7b0cb307028c176cf56eb186`: PR-triggered workflow runs **не возвращены**. Это НЕ доказывает отсутствия всех проверок: endpoint отфильтровывает только PR-triggered workflow и первую страницу.

`fetch_workflow_run_jobs` вернул по каждому из трёх PAPER runs successful job `deterministic-paper-path`. Среди шагов: runtime replay, deterministic PAPER acceptance, Scanner-to-Robot handoff, Autopilot shadow, Scanner control/Telegram menu, scoped LIMIT amend и protection schema migration. Для #405 отдельный job `affected-workflow-tests` также successful.

**Ограничение данных:** на полученных job/step объектах отсутствовали usable `started_at`/`completed_at` timestamp; продолжительность отдельных этапов, queue time, runner overhead и повторные CI attempts по этим данным не установлены. Тесты и workflows повторно НЕ запускались.

## Следствие для плана

1. **Не объявлять CI bottleneck.** Известно, что на выбранных PR PAPER и workflow checks проходили, но нет доказанного узкого места по времени. Сохранять existing mandatory checks.
2. **Первый подтверждённый процессный источник переделки — контракт launch-intent:** PR #404 трактовал `Запуск робота` как ROBOT-only; PR #405 немедленно вернул owner `ALL`. Перед изменением owner control surface сверять текущий owner UX contract и последний исправляющий PR. Делать это в существующем task-scoped preflight, без нового формального approval-gate.
3. **Branch routing уже работает как selective backport:** в PR #426/#427 присутствуют upstream SHA, patch/dependency evidence и stable-target; не заменять это автоматическим merge `main`→`stable`.
4. **Критический путь Robot owner-thread:** серия уже merged #424/#426–#431, #435 направлена на устранение owner-thread REST и protection path gaps; ускорение нельзя измерять по исходному коду или CI PASS. Для дальнейших выводов нужны telemetry уже происходящего owner-controlled PAPER-прогона, не дополнительная тестовая кампания.

## Следующий зависимый этап и решение

В рамках существующего owner-controlled первого PAPER-запуска ноутбука при получении результатов оценить Backend/Telegram/Scanner/Robot, `paper_live_safe`, protection health и, **только если существующие наблюдения доступны**, owner ingress pending/high watermark, latency и incidents. Отсутствующие метрики не являются автоматическим основанием для новых instrumentation PR.

Прежде чем предлагать реализацию, дополнить текущую evidence-table указанием узкого места, потенциально сэкономленных действий/времени, риска, минимального изменения и требуемой проверки. Если реальная задержка не доказана — не создавать оптимизационный PR.

**Не выполнено:** runtime профилирование, оценка end-to-end latency, измерение CI job duration, новая PAPER-приёмка. Это не основание тормозить штатный owner launch.

Источники: https://github.com/svobodaXXI/BybitScanner/pull/405 ; https://github.com/svobodaXXI/BybitScanner/pull/427 ; https://github.com/svobodaXXI/BybitScanner/pull/435 ; https://github.com/svobodaXXI/BybitScanner/actions/runs/37598235731 ; https://github.com/svobodaXXI/BybitScanner/actions/runs/37755287072 ; https://github.com/svobodaXXI/BybitScanner/actions/runs/37813511593 .


## 09.10 — ограниченная оценка стоимости backport

Проверены семь пар исходный PR `main` → backport PR `stable` по метаданным GitHub. Интервал **только от открытия backport PR до merge**, в минутах:
- #392 → #422: 12,9;
- #394 → #424: 1,6;
- #396 → #426: 8,5;
- #397 → #427: 52,1;
- #398 → #428: 3,9;
- #401 → #430: 6,1;
- #402 → #431: 1,9.

Сумма наблюдаемых PR-open→merge интервалов: **около 87 минут**, медиана **6,1 минуты**. Суммирование не учитывает параллельную работу, подготовку до открытия PR, ожидание владельца, CI и окончательную PAPER-приёмку; это **не** измеренные трудозатраты и **не** полная стоимость backport. Само расхождение коммитов не доказывает задержку.

**Решение:** отдельная переделка Git-ветвления не оправдана текущими доказательствами. Существующий селективный backport оставить без новых gates, синхронизации или PR. Вернуться к PAPER-запуску ноутбука и следить только за фактическими повторными переносами/конфликтами, если они появятся в новых задачах.

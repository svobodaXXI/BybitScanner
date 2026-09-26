# BybitScanner — состояние кампании

Статус: ACTIVE  
Обновлено: 2026-09-26  
Назначение: компактная игровая проекция текущего GTD/backlog состояния для автоматического восстановления в новом чате.

> Этот файл не задаёт технический приоритет сам по себе. При конфликте текущая
> команда владельца и `DOCUMENTS/BACKLOG.md` имеют более высокий приоритет.

## Кампания

**«PAPER Robot: Гильдия паттернов»**

## Текущий уровень

- XP: **100**
- Уровень: **2 — Охотник за пивотами**
- Серия: **Комбо переиспользования ×1**

Начальный XP после введения игровой системы начислен только за уже доказанный
сегодня результат: устранение protection-continuity false positive (#237),
которое прошло Robot PAPER acceptance. Планирование, документация и количество
коммитов XP не добавляют.

## Последний reconciliation checkpoint — 2026-09-26

Обязательный долг синхронизации/reconciliation закрыт.

- `C:\BybitScanner-sync-20260926` fast-forward синхронизирован с текущим `main`;
- `C:\BybitScanner-box-robot-run` синхронизирован с текущим `main` и сохраняет
  локальные launcher-файлы;
- уникальные локальные дельты `C:\BybitScanner` для
  `geometry/ikigai_box_chart.py` и `start_scanner.bat` сохранены побайтово
  в `C:\BybitScanner-reconciliation-backup-20260926\main-local`; сам dirty
  checkout не очищался и не перезаписывался;
- PAPER backend поднят на актуальном коде без Scanner и без LIVE;
- protection coverage восстановлено в healthy state;
- explicit operator reconciliation успешно перевёл Robot из
  `ROBOT_RUNNING / RECONCILIATION_REQUIRED` в
  `ROBOT_RUNNING / PAUSED`;
- открытая RDWUSDT PAPER-позиция не закрывалась; вход, durable trade,
  protection и ownership были согласованы; unresolved protection obligations = 0;
- admission остаётся закрытым, Scanner не запускался.

Backup и dirty локальный checkout пока сохраняются; не удалять их только ради
cleanup. Следующий активный этап — реальная PAPER-проверка L-shape рейда.

## 🎯 Активный квест

### Рейд «Один запуск — весь прототип»

**Приоритет:** P0  
**Статус:** АКТИВЕН  
**Цель:** сделать один канонический owner-start путь, после которого PAPER
backend, Robot protection/admission, Telegram callbacks/menu и Scanner имеют
по одному владельцу, одну runtime authority и проверенную readiness-цепочку.

Причина переключения: 2026-09-26 длинный acceptance-run был начат после
неполного preflight. Backend и Robot были READY, но Telegram callback worker
не работал; дополнительно обнаружен split-brain Scanner ownership:
standalone `main.py` и backend `ScannerControlRuntime` являются разными
владельцами и могут породить дубли.

**Этапы рейда:**

- [x] PR #249 merged (`2032188`): one-pass authoritative Scanner runtime с pause/resume/stop;
- [x] PR #251 merged (`b02e330`): canonical launcher больше не запускает standalone `main.py`; Scanner стартует через backend `/api/scanner/start`;
- [ ] сделать Telegram update consumer singleton + observable readiness;
- [ ] заменить fixed sleeps на bounded dependency readiness/fail-closed startup;
- [ ] убрать устаревший 1m Wedge observational-only Robot-button gate;
- [ ] только после этого провести один полный owner-run acceptance.

**Награда:** без XP за документацию/рефакторинг; награда только за доказанный
полный запуск без ручного кризисного восстановления.

Предыдущий рейд «Г-образные врата» не отменён: PR #248 merged, но его
реальная PAPER acceptance временно ждёт завершения этого P0 operational gate.

## 🚧 Временные ворота активного рейда

### «Один запуск — один проход»

Во время реальной проверки обнаружено, что Scanner в RUNNING автоматически
запускает новые полные проходы. Владелец также разделил требуемую семантику:
**Пауза/Продолжить** сохраняют текущий проход, а **Остановить сканер** полностью
завершает его. Исправление находится в draft PR #249. Там же восстанавливается
исчезающая Telegram-кнопка Menu. Последний code-bearing head `d2a6473...` имеет green Robot
PAPER acceptance, включая прямой Scanner-control/Telegram-menu шаг; последующие
коммиты этого checkpoint — только документация; merge и
owner runtime acceptance ещё не выполнены. До них повторный полный Scanner
acceptance не заказывать.

### «Переполненный шлюз»

Robot protection ingress ранее дал `ingress_overflow`, после чего штатный
fail-closed recovery аварийно закрыл owned позиции и оставил Robot в
`ROBOT_RUNNING / RECONCILIATION_REQUIRED`. Аварийное закрытие не считать
дефектом защиты; отдельный незакрытый босс — причина переполнения ingress.
Перед новыми PAPER admission требуется штатная evidence-based сверка.


### «Сломанный телепорт Codex»

Read-only разбор торговли Robot за 25.09.2026 ещё не выполнен. Codex Desktop
повторно отвечает `401 Incorrect API key`, хотя локальная диагностика
подтверждает ChatGPT auth, отсутствие сохранённого API key и доступность
ChatGPT endpoint. Desktop остаётся на 26.917.9434.0 при доступной
26.924.1866.0; встроенное обновление пока не меняет установленную версию.
Сначала восстановить рабочий Codex Desktop, затем сделать только read-only
аудит сделок/PnL. Отдельный `helper_sandbox_lock_failed` не считать дефектом
BybitScanner без доказанной связи.

## Очередь после активного квеста

### 2. 👹 Босс «Кривой первый импульс»

Ikigai Box first-impulse geometry. Конкретный дефект: AIGENSYNUSDT 5m.

Правило владельца:

- отчётливая встречная коррекционная волна завершает первый импульс;
- допускаются только 1–2 небольшие встречные свечи как пауза;
- если они формируют отдельный локальный counter-swing, это уже конец импульса.

Связанный FLOCK baseline рассматривается в том же geometry-slice только если
причина действительно общая.

### 3. 🧰 Побочный квест «Приодеть карточку позиции»

Telegram open-position card:

- больше места справа от последних свечей;
- убрать слово «Вход», оставить уровень/цену;
- «Стоп» / «Тейк» -> `SL` / `TP`;
- уменьшить execution triangles;
- цвет контура по направлению;
- `Размер` = quantity + USDT notional.

Торговую логику не менять.

## Таверна ожидания / отложено

- **Рейд «Много зверей — один тикер»** — multi-pattern Scanner:
  все паттерны 5m -> все паттерны 1m -> следующий тикер.
- **Квест «Ночной дозор»** — FocusedPatternMonitor для новых структур после
  ухода Full Scanner.
- синхронизация/ручной restart PC runtime с сегодняшним новым main — только
  когда владелец решит перезапускать runtime; не прерывать текущую сессию
  автоматически.
- полный real Scanner acceptance — только по существующему owner-run правилу.

## Открытые ачивки

- ✅ **«Повелитель барьера»** — #237: reconnect barrier больше не уничтожает
  валидные pre-disconnect события из-за задержки owner FIFO.
- ✅ **«Феникс»** — reconcile восстановил корректный Robot lifecycle без ручных
  правок БД; затем владелец штатно вернул Robot в READY через Telegram.
- ⬜ **«Новый монстр, старый движок»** — цель текущего L-shape рейда.
- ⬜ **«Один тикер — много зверей»** — будущий multi-pattern Scanner.
- ⬜ **«Оба этажа зачищены»** — будущий полный 5m+1m per-symbol traversal.
- ⬜ **«Ночной дозор»** — будущий FocusedPatternMonitor.
- ⬜ **«Контекст не потерян»** — откроется после первого нового чата, который
  без ручного handoff корректно восстановит активный квест из репозитория.

## Последняя доказанная добыча

- ordered disconnect/reconnect continuity barrier;
- regression/acceptance proof для protection continuity;
- Ikigai Box owner Robot status/control button;
- два утверждённых архитектурных плана:
  multi-pattern Scanner и FocusedPatternMonitor;
- русская GTD Quest System;
- стабильный Custom Instructions bootstrap для автоматического нового-чата и
  быстрого освежения контекста;
- глобальные ChatGPT Custom Instructions установлены владельцем 2026-09-25;
  реальная проверка нового-чата ещё не выполнена, поэтому ачивка
  «Контекст не потерян» остаётся закрытой.

## Правило автоматического восстановления

При первом BybitScanner-сообщении нового ChatGPT-чата:

1. загрузить `AGENTS.md`;
2. восстановить минимальный task-scoped контекст;
3. прочитать этот файл;
4. сверить его с верхним текущим priority index в `DOCUMENTS/BACKLOG.md`;
5. если пользователь в новом чате сразу даёт новый приоритет — он побеждает;
6. продолжить уже в русском игровом режиме;
7. не просить пользователя вручную переносить этот контекст.

Если этот файл устарел относительно BACKLOG, исправить его при ближайшем
документационном checkpoint, а не следовать устаревшему квесту.

В существующем чате короткая команда владельца «освежи контекст» означает
быстро сверить этот save-game с актуальными BACKLOG/owning spec и сообщить
только важное изменение. Команда `э` продолжает активный квест; если state
сомнительно свежий, перед продолжением выполняется такое быстрое освежение.

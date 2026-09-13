# Robot Run Index

Этот файл является указателем на результаты фактических запусков Robot v0.1.
При расследовании истории запусков Robot сначала искать записи здесь.

## 2026-09-12 — Local Paper Run

**Результат:** Robot был `ROBOT_RUNNING + READY`; приняты 2 кандидата, оба `APPROVED`; Robot trades = 0.

**Полный отчёт:**
`DOCUMENTS/ROBOT_V0_1_LOCAL_PAPER_RUN_2026-09-12.md`

**Кандидаты:**
- AAVEUSDT → APPROVED
- BLURUSDT → APPROVED

**Важно:** причина отсутствия `robot_trades` в рамках этого запуска не исследовалась.

---

## 2026-09-12 — Post-closure fix: RobotBreakoutMonitor SQLiteStore thread ownership

**CR-ROBOT-BREAKOUT-MONITOR-001 остаётся `CLOSED`** — эта запись не переоткрывает его, а фиксирует
отдельно найденный и исправленный дефект в уже закрытом коде.

**Найдено:** `RobotBreakoutMonitor` принимал уже открытый `SQLiteStore` из потока-конструктора
(`PaperRuntime.__init__`), но тикал из собственного фонового потока. `SQLiteStore` жёстко привязывается
к потоку, в котором был открыт (`self._owner_thread`), и любой вызов из другого потока проваливается с
`PersistenceError("SQLiteStore must be used by its owning writer thread")`. Это означает, что каждый
реальный тик (после первого реального интервала фонового потока) падал бы с этой ошибкой — молча,
поскольку `_run()` перехватывает и логирует исключения, не давая процессу упасть. Ни один существующий
тест этого не обнаружил, так как все они вызывали `.tick()` синхронно из потока теста; единственный
тест жизненного цикла потока (`test_start_and_close_do_not_tick_within_the_interval`) намеренно
останавливает монитор до истечения интервала, поэтому реальный фоновый поток никогда не успевал
выполнить ни одного настоящего тика ни в одном существующем тесте.

**Исправлено:** `RobotBreakoutMonitor` больше не принимает готовый `SQLiteStore`. Конструктор теперь
принимает `store_factory: Callable[[], SQLiteStore]`; соединение открывается лениво, изнутри вызывающего
потока, и кешируется per-thread (`threading.local()`). Реальный фоновый поток открывает и владеет
собственным соединением; синхронный вызывающий (например, тесты) получает отдельное соединение в своём
потоке. `terminal/runtime/paper_runtime.py` передаёт `store_factory=lambda: SQLiteStore.open(database_path)`
вместо готового `self.store`.

**Регрессионный тест:** добавлен `tests/test_robot_breakout_monitor.py::RobotBreakoutMonitorRealThreadTests`
— запускает настоящий `start()`+ждёт реальный тик на живом фоновом потоке +`close()`, проверяя, что
кандидат реально продвинулся (а не просто не упал молча). Этот тест обнаружил бы регрессию, которую
пропустили все существующие тесты.

**Область:** только `terminal/application/robot_breakout_monitor.py` и
`terminal/runtime/paper_runtime.py` (конструктор `RobotBreakoutMonitor`). Никакая бизнес-логика
breakout/retest/partial-fill/confirmation/protection не менялась.

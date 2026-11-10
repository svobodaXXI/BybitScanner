import { useEffect, useMemo, useRef, useState } from "react";
import {
  ALL_SELECTABLE, MIRROR_OPTIONS, OTHER_OPTIONS, PLANNED_OPTIONS,
  clearAll, isAllSelected, onlyWedges, presetEndInclusive, extendInclusiveWindow,
  selectAll, toggleMirror, toggleStrategy, validateInclusiveWindow,
  makeWedgeRunRequest, parseWedgeResult, parseWedgeStatus, runnableWedgeSelection,
  type PeriodPreset, type PeriodIncrement, type RunSelection, type StrategyId,
  type LocalWedgeResult, type LocalWedgeStatus,
} from "./runSetup";
import "./runSetup.css";

const INITIAL_START = new Date(Date.now() - 3 * 86_400_000).toISOString().slice(0, 16);
const INCREMENTS: Array<{ id: PeriodIncrement; name: string }> = [
  { id: "HOUR", name: "+1 час" },
  { id: "DAY", name: "+1 день" },
  { id: "WEEK", name: "+1 неделя" },
  { id: "MONTH", name: "+1 месяц" },
];

/** Local-only Wedge execution via loopback: never production /api or PAPER. */
export function RunSetupPanel({
  symbol, onArchiveSymbol,
}: {
  symbol: string; onArchiveSymbol: (archiveSymbol: string) => boolean;
}) {
  const [selection, setSelection] = useState<RunSelection>(clearAll);
  const [start, setStart] = useState(INITIAL_START);
  const [end, setEnd] = useState(() => presetEndInclusive(INITIAL_START, "DAY"));
  const [preset, setPreset] = useState<PeriodPreset | null>("DAY");
  const [openMirror, setOpenMirror] = useState(true);
  const [balance, setBalance] = useState("1000");
  const [status, setStatus] = useState<LocalWedgeStatus | null>(null);
  const [statusError, setStatusError] = useState("");
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<LocalWedgeResult | null>(null);
  const [runError, setRunError] = useState("");
  const [periodError, setPeriodError] = useState("");
  const datesEdited = useRef(false);
  const parsed = useMemo(() => {
    try {
      return { window: validateInclusiveWindow(start, end), error: "" };
    } catch (error) {
      return { window: null, error: error instanceof Error ? error.message : "Некорректный период" };
    }
  }, [start, end]);
  const active = ALL_SELECTABLE.filter(id => selection.selected.includes(id));
  const mirrorSelected = MIRROR_OPTIONS.filter(x => selection.selected.includes(x.id)).length;
  const wedgesOnly = runnableWedgeSelection(selection);
  const selectionAllowed = wedgesOnly && !parsed.error;
  const ready = Boolean(status?.can_attempt);

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const response = await fetch("/local-replay/simulation/status", {
          method: "GET", cache: "no-store", signal: controller.signal,
        });
        if (!response.ok) throw new Error("Локальный движок пока недоступен");
        const next = parseWedgeStatus(await response.json() as unknown);
        if (!controller.signal.aborted) {
          setStatus(next);
          // A manifest hint is NOT proof of the cache or instrument terms.
          // Do not overwrite an owner-selected ticker or period.
          if (next.archive_hint && !datesEdited.current &&
              onArchiveSymbol(next.archive_hint.symbol)) {
            setStart(next.archive_hint.start_utc);
            setEnd(next.archive_hint.end_utc_inclusive);
            setPreset("DAY");
          }
        }
      } catch (error) {
        if (!controller.signal.aborted) setStatusError(
          error instanceof Error ? error.message : "Нет подключения к локальному движку",
        );
      }
    })();
    return () => controller.abort();
  }, [onArchiveSymbol]);

  const runWedges = async () => {
    setRunError(""); setReport(null);
    let request;
    try {
      request = makeWedgeRunRequest(selection, symbol, start, end, balance);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "Некорректный выбор");
      return;
    }
    setLoading(true);
    try {
      // The loopback viewer accepts this exact path and a same-origin header.
      // Never call /api; that path may target the PAPER backend.
      const response = await fetch("/local-replay/simulation/wedge", {
        method: "POST", cache: "no-store",
        headers: { "Content-Type": "application/json", "X-Local-Simulation": "wedge" },
        body: JSON.stringify(request),
      });
      const raw: unknown = await response.json();
      if (!response.ok) {
        const x = raw && typeof raw === "object" ? raw as Record<string, unknown> : {};
        throw new Error(typeof x.error === "string" ? x.error : "Локальный прогон заблокирован");
      }
      const result = parseWedgeResult(raw);
      if (result.symbol !== request.symbol || result.requested_minutes !== parsed.window?.minutes) {
        throw new Error("Отчёт не соответствует выбранному тикеру или периоду");
      }
      setReport(result);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "Симуляция недоступна");
    } finally {
      setLoading(false);
    }
  };

  const updateStart = (value: string) => {
    datesEdited.current = true;
    setPeriodError("");
    setStart(value);
    if (preset) {
      try { setEnd(presetEndInclusive(value, preset)); } catch { /* Display validation until input completed. */ }
    }
  };
  const choosePreset = (next: PeriodPreset) => {
    datesEdited.current = true;
    setPeriodError("");
    setPreset(next);
    try { setEnd(presetEndInclusive(start, next)); } catch { /* Invalid start remains visible. */ }
  };
  const addPeriod = (increment: PeriodIncrement) => {
    try {
      const updatedEnd = extendInclusiveWindow(start, end, increment);
      datesEdited.current = true;
      setPreset(null);
      setEnd(updatedEnd);
      setPeriodError("");
    } catch (error) {
      setPeriodError(error instanceof Error ? error.message : "Нельзя продлить период");
    }
  };
  const toggleComponent = (id: StrategyId, enabled: boolean) =>
    setSelection(current => toggleStrategy(current, id, enabled));

  return (
    <section className="replay-run-setup" aria-label="Настройка стратегий и периода">
      <div className="replay-run-heading">
        <strong>Универсальный симулятор · настройка прогона</strong>
        <span>Локальный SIMULATION · один тикер: {symbol.trim().toUpperCase() || "не выбран"}</span>
      </div>
      <div className="replay-run-layout">
        <fieldset className="replay-run-strategies">
          <legend>Стратегии</legend>
          <div className="replay-run-actions">
            <label className="replay-run-check">
              <input type="checkbox" aria-label="Все стратегии"
                checked={isAllSelected(selection)}
                onChange={e => setSelection(e.target.checked ? selectAll() : clearAll())} />
              <strong>Все стратегии</strong>
            </label>
            <button type="button" onClick={() => setSelection(onlyWedges())}>Только клинья</button>
            <button type="button" onClick={() => setSelection(clearAll())}>Снять все</button>
          </div>
          <div className="replay-run-mirror">
            <div className="replay-run-mirror-top">
              <label className="replay-run-check">
                <input type="checkbox" aria-label="Mirror — комплекс"
                  checked={selection.mirror}
                  onChange={e => setSelection(current => toggleMirror(current, e.target.checked))} />
                <strong>Mirror — комплекс</strong>
              </label>
              <button type="button" aria-expanded={openMirror}
                onClick={() => setOpenMirror(value => !value)}>
                {openMirror ? "Свернуть" : "Раскрыть"} · {mirrorSelected}/{MIRROR_OPTIONS.length}
              </button>
            </div>
            {openMirror && <div className="replay-run-components">
              {MIRROR_OPTIONS.map(option => <label className="replay-run-check" key={option.id}>
                <input type="checkbox" aria-label={option.label}
                  checked={selection.selected.includes(option.id)}
                  onChange={e => toggleComponent(option.id, e.target.checked)} />
                <span>{option.label}</span>
              </label>)}
            </div>}
          </div>
          <div className="replay-run-independent">
            <span>Независимые стратегии</span>
            {OTHER_OPTIONS.map(option => <label className="replay-run-check" key={option.id}>
              <input type="checkbox" aria-label={option.label}
                checked={selection.selected.includes(option.id)}
                onChange={e => toggleComponent(option.id, e.target.checked)} />
              {option.label}
            </label>)}
          </div>
          <details className="replay-run-planned">
            <summary>В разработке — не доступны для прогона</summary>
            {PLANNED_OPTIONS.map(name => <label key={name}>
              <input type="checkbox" disabled aria-label={name} /> {name}
            </label>)}
          </details>
        </fieldset>
        <fieldset className="replay-run-dates">
          <legend>Исторический период · UTC</legend>
          <label>Начало · дата и время
            <input aria-label="Начало прогона UTC" type="datetime-local" step={60}
              value={start} onChange={e => updateStart(e.target.value)} />
          </label>
          <div className="replay-run-presets" role="group" aria-label="Продлить период прогона">
            {INCREMENTS.map(option => <button key={option.id} type="button"
              onClick={() => addPeriod(option.id)}>{option.name}</button>)}
            <button type="button" aria-pressed={preset === "THREE_MONTHS"}
              onClick={() => choosePreset("THREE_MONTHS")}>3 месяца · 90 дней</button>
          </div>
          {periodError && <p role="alert" className="replay-run-error">{periodError}</p>}
          <label>Конец · дата и время, включительно
            <input aria-label="Конец прогона UTC" type="datetime-local" step={60}
              value={end} onChange={e => {
                datesEdited.current = true; setPeriodError(""); setPreset(null); setEnd(e.target.value);
              }} />
          </label>
          {parsed.error ? <p role="alert" className="replay-run-error">{parsed.error}</p> :
            <p role="status" className="replay-run-summary">
              {parsed.window?.minutes.toLocaleString("ru-RU")} минут M1 · конечная минута включена
            </p>}
        </fieldset>
      </div>
      <div className="replay-run-account">
        <label>Виртуальный депозит · USDT
          <input aria-label="Виртуальный депозит" type="text" inputMode="decimal"
            value={balance} onChange={e => setBalance(e.target.value)} />
        </label>
        <span>Риск, шаг цены и перевод 1 WV в контракты берутся только из локального профиля SIMULATION.</span>
      </div>
      <div className="replay-run-footer">
        <span data-selected-strategies={active.join(",")}>
          Выбрано компонентов: {active.length}. {selection.mirror ? "Mirror включён." : "Mirror выключен."}
        </span>
        <button type="button" onClick={() => void runWedges()}
          disabled={loading || !selectionAllowed || !ready}
          title={!wedgesOnly ? "В торговом режиме пока доступны только клинья"
            : !ready ? "Требуются локальный движок, проверенный архив и профиль риска"
            : "Локальный виртуальный прогон без PAPER"}>
          {loading ? "Выполняется прогон…" : "Запустить клинья · SIMULATION"}
        </button>
      </div>
      {!wedgesOnly && active.length > 0 &&
        <p className="replay-run-error" role="status">
          Отмеченные стратегии сохранены как выбор, но торговый запуск пока поддерживает только два клина.
        </p>}
      {statusError && <p role="status" className="replay-run-error">{statusError}</p>}
      {status && !status.can_attempt &&
        <p role="status" className="replay-run-error">
          Локальный запуск пока недоступен: {[
            !status.wedge_engine_available && "движок",
            !status.python_dependencies_available && "Python pandas",
            !status.archive_files_present && "проверенный архив M1",
            !status.wedge_risk_profile_present && "профиль риска 1 WV",
          ].filter(Boolean).join(", ")}.
        </p>}
      {runError && <p role="alert" className="replay-run-error">{runError}</p>}
      {report && <section aria-label="Результаты виртуального прогона" className="replay-run-result" role="status">
        <strong>Результат локального SIMULATION · {report.symbol}</strong>
        <span>Реализованный Net PnL: {report.realized_net_pnl} USDT ·
          нереализованный: {report.unrealized_pnl} USDT</span>
        <span>Суммарный PnL: {report.total_net_pnl} USDT ·
          доходность: {report.return_percent}% · просадка: {report.max_drawdown_percent}%</span>
        <span>Обнаружено клиньев: {report.scanner_wedge_observations} ·
          ретестов: {report.robot_retests_in_period} ·
          LIMIT: {report.submitted_protected_limits} ·
          исполнений: {report.virtual_fills} · STOP: {report.stop_exits} · TAKE: {report.take_exits}</span>
        <small>Модель OHLC, не фактические биржевые исполнения. Параметры риска — локальные исследовательские допущения.</small>
      </section>}
      <p className="replay-run-disclaimer">
        Общий мультивыбор сохранён, но пока торгуются только клинья. Прогон строго локальный, по заранее
        проверенным архивам Bybit без доступа к PAPER/VPS. Ниже — прежний независимый просмотр M5.
      </p>
    </section>
  );
}

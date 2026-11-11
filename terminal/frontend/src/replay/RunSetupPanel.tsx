import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type ReplayDocument, type ReplayEvent } from "./replayModel";
import { streamWedge } from "./streamWedge";
import {
  ALL_SELECTABLE, MIRROR_OPTIONS, OTHER_OPTIONS, PLANNED_OPTIONS,
  clearAll, isAllSelected, onlyWedges, onlyBox, presetEndInclusive, adjustInclusiveWindow,
  parseRunCoordinates, formatRunDuration,
  selectAll, toggleMirror, toggleStrategy, validateInclusiveWindow,
  makeWedgeRunRequest, parseWedgeStatus, runnableWedgeSelection,
  type PeriodPreset, type PeriodIncrement, type RunSelection, type StrategyId,
  type LocalWedgeResult, type LocalWedgeStatus,
} from "./runSetup";
import "./runSetup.css";

type WedgeRunRequest = ReturnType<typeof makeWedgeRunRequest>;
const INITIAL_START = new Date(Date.now() - 3 * 86_400_000).toISOString().slice(0, 16);
const STEPS: Array<{ id: PeriodIncrement; name: string }> = [
  { id: "HOUR", name: "1 час" },
  { id: "DAY", name: "1 день" },
  { id: "WEEK", name: "1 неделя" },
];

/** Native Wedge/Box Scanner+Robot via one isolated loopback SIMULATION adapter. */
export function RunSetupPanel({
  symbol, onArchiveSymbol, onPasteSymbol, onSimulationStart, onSimulationReady,
  onSimulationAppend, onSimulationFailed, onSimulationBusy, playRequestId, showReport,
  onPublicHistoryRequest, publicHistoryLoading, onStrategySelectionChange,
}: {
  symbol: string;
  onArchiveSymbol: (archiveSymbol: string) => boolean;
  onPasteSymbol: (symbol: string) => void;
  onSimulationStart: (request: WedgeRunRequest) => void;
  onSimulationBusy: (busy: boolean) => void;
  playRequestId: number;
  showReport: boolean;
  onSimulationReady: (replay: ReplayDocument) => void;
  onSimulationAppend: (runId: string, events: ReplayEvent[]) => void;
  onSimulationFailed: () => void;
  onPublicHistoryRequest: (symbol: string, start: string, endInclusive: string, selected: readonly StrategyId[]) => void;
  publicHistoryLoading: boolean;
  onStrategySelectionChange: (selection: RunSelection) => void;
}) {
  const [selection, setSelection] = useState<RunSelection>(onlyWedges);
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
  const [coordinateText, setCoordinateText] = useState("");
  const [coordinateError, setCoordinateError] = useState("");
  const datesEdited = useRef(false);
  const preparedRun = useRef<WedgeRunRequest | null>(null);
  const generation = useRef(0);
  const running = useRef(false);
  const requestController = useRef<AbortController | null>(null);
  const parsed = useMemo(() => {
    try {
      return { window: validateInclusiveWindow(start, end), error: "" };
    } catch (error) {
      return { window: null, error: error instanceof Error ? error.message : "Некорректный период" };
    }
  }, [start, end]);
  const active = ALL_SELECTABLE.filter(id => selection.selected.includes(id));
  const mirrorSelected = MIRROR_OPTIONS.filter(x => selection.selected.includes(x.id)).length;
  const runnableNative = runnableWedgeSelection(selection);

  // The chart is another VIEW of the same checked selection. Never
  // let public MARKET_ONLY geometry disregard the owner's strategy choices.
  // This is not strategy admission or a trading command.
  useEffect(() => { onStrategySelectionChange(selection); },
    [selection, onStrategySelectionChange]);

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

  const runWedges = useCallback(async (request: WedgeRunRequest, seq: number) => {
    if (running.current) return; // No duplicate Scanner/Robot computation.
    running.current = true;
    const controller = new AbortController();
    requestController.current = controller;
    setRunError(""); setReport(null); setLoading(true);
    onSimulationBusy(true);
    try {
      const result = await streamWedge(
        request, controller.signal,
        replay => {
          if (seq === generation.current && !controller.signal.aborted)
            onSimulationReady(replay); // Show first verified M5 without waiting for the end.
        },
        (runId, events) => {
          if (seq === generation.current && !controller.signal.aborted)
            onSimulationAppend(runId, events);
        },
      );
      if (seq === generation.current && !controller.signal.aborted)
        setReport(result);
    } catch (error) {
      if (seq === generation.current && !controller.signal.aborted) {
        onSimulationFailed();
        setRunError(error instanceof Error ? error.message : "Поток SIMULATION недоступен");
      }
    } finally {
      if (requestController.current === controller) {
        requestController.current = null; running.current = false;
        setLoading(false); onSimulationBusy(false);
      }
    }
  }, [onSimulationReady, onSimulationAppend, onSimulationFailed, onSimulationBusy]);

  useEffect(() => {
    if (playRequestId > 0 && preparedRun.current)
      void runWedges(preparedRun.current, generation.current);
  }, [playRequestId, runWedges]);

  const updateStart = (value: string) => {
    datesEdited.current = true;
    setPeriodError("");
    setCoordinateText("");
    setStart(value);
    if (preset) {
      try { setEnd(presetEndInclusive(value, preset)); } catch { /* Display validation until input completed. */ }
    }
  };
  const choosePreset = (next: PeriodPreset) => {
    datesEdited.current = true;
    setPeriodError("");
    setPreset(next); setCoordinateText("");
    try { setEnd(presetEndInclusive(start, next)); } catch { /* Invalid start remains visible. */ }
  };
  const changePeriod = (increment: PeriodIncrement, direction: 1 | -1) => {
    try {
      const updatedEnd = adjustInclusiveWindow(start, end, increment, direction);
      datesEdited.current = true;
      setPreset(null); setCoordinateText("");
      setEnd(updatedEnd);
      setPeriodError("");
    } catch (error) {
      setPeriodError(error instanceof Error ? error.message : "Нельзя изменить период");
    }
  };
  const applyCoordinates = (value: string) => {
    try {
      const coords = value.trim() ? parseRunCoordinates(value) :
        { symbol, start_utc: start, end_utc_inclusive: end };
      const request = makeWedgeRunRequest(
        selection, coords.symbol, coords.start_utc, coords.end_utc_inclusive, balance,
      );
      requestController.current?.abort();
      requestController.current = null;
      running.current = false;
      onSimulationBusy(false);
      generation.current++;
      preparedRun.current = request;
      datesEdited.current = true;
      onPasteSymbol(request.symbol);
      setStart(request.start_utc); setEnd(request.end_utc_inclusive);
      setPreset(null); setPeriodError(""); setCoordinateError(""); setRunError("");
      setReport(null);
      onSimulationStart(request); // Prepare Source and clear old chart; POST waits for ▶.
    } catch (error) {
      setCoordinateError(error instanceof Error ? error.message : "Неверные координаты прогона");
    }
  };
  const pasteCoordinates = async () => {
    try {
      if (!navigator.clipboard?.readText)
        throw new Error("Буфер недоступен — вставьте строку в поле вручную");
      const value = await navigator.clipboard.readText();
      setCoordinateText(value);
      setCoordinateError("");
    } catch (error) {
      setCoordinateError(error instanceof Error ? error.message : "Вставка недоступна");
    }
  };
  const toggleComponent = (id: StrategyId, enabled: boolean) =>
    setSelection(current => toggleStrategy(current, id, enabled));

  return (
    <section className="replay-run-setup" aria-label="Настройка стратегий и периода">
      <div className="replay-run-heading">
        <strong>Универсальный симулятор · настройка прогона</strong>
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
          <div className="replay-run-coordinates">
            <label>Вставить тикер и даты · UTC
              <input aria-label="Координаты прогона" type="text" value={coordinateText}
                placeholder="XRPUSDT | 2026-09-11T00:00 | 2026-09-11T23:59"
                onChange={e => { setCoordinateText(e.target.value); setCoordinateError(""); }} />
            </label>
            <div className="replay-run-coordinate-actions">
              <button type="button" onClick={() => void pasteCoordinates()}>Вставить из буфера</button>
              <button type="button" onClick={() => applyCoordinates(coordinateText)}>Применить</button>
            </div>
            {coordinateError && <p role="alert" className="replay-run-error">{coordinateError}</p>}
          </div>
          <label>Начало · дата и время
            <input aria-label="Начало прогона UTC" type="datetime-local" step={60}
              value={start} onChange={e => updateStart(e.target.value)} />
          </label>
          <div className="replay-run-presets" role="group" aria-label="Изменить период прогона">
            {STEPS.map(option => <div className="replay-run-step" key={option.id}
              role="group" aria-label={"Период " + option.name}>
              <div className="replay-run-stepper">
                <button type="button" aria-label={"Добавить " + option.name}
                  onClick={() => changePeriod(option.id, 1)}>+</button>
                <button type="button" aria-label={"Убавить " + option.name}
                  onClick={() => changePeriod(option.id, -1)}>−</button>
              </div>
              <span className="replay-run-step-label">{option.name}</span>
            </div>)}
            <button type="button" onClick={() => changePeriod("MONTH", 1)}>+1 месяц</button>
            <button type="button" aria-pressed={preset === "THREE_MONTHS"}
              onClick={() => choosePreset("THREE_MONTHS")}>3 месяца · 90 дней</button>
          </div>
          {parsed.window && <p className="replay-run-duration" role="status"
            aria-label="Продолжительность прогона" aria-live="polite">
            Продолжительность: <strong>{formatRunDuration(parsed.window.minutes)}</strong>
          </p>}
          {periodError && <p role="alert" className="replay-run-error">{periodError}</p>}
          <label>Конец · дата и время, включительно
            <input aria-label="Конец прогона UTC" type="datetime-local" step={60}
              value={end} onChange={e => {
                datesEdited.current = true; setPeriodError(""); setPreset(null);
                setCoordinateText(""); setEnd(e.target.value);
              }} />
          </label>
          {parsed.error ? <p role="alert" className="replay-run-error">{parsed.error}</p> :
            <p role="status" className="replay-run-summary">
              {parsed.window?.minutes.toLocaleString("ru-RU")} минут M1 · конечная минута включена
            </p>}
          <div className="replay-run-public-history">
            <button type="button" disabled={publicHistoryLoading || !parsed.window}
              onClick={() => onPublicHistoryRequest(symbol, start, end, selection.selected)}>
              {publicHistoryLoading ? "Загружаю историю…" : "Загрузить Bybit (без сделок)"}
            </button>
          </div>
        </fieldset>
      </div>
      <div className="replay-run-account">
        <label>Виртуальный депозит · USDT
          <input aria-label="Виртуальный депозит" type="text" inputMode="decimal"
            value={balance} onChange={e => setBalance(e.target.value)} />
        </label>

      </div>
      <div className="replay-run-footer">
        <span data-selected-strategies={active.join(",")} aria-hidden="true" />
        {loading && <span>Проверка M1 и расчёт виртуального прогона…</span>}
      </div>
      {!runnableNative && active.length > 0 &&
        <p className="replay-run-error" role="status">
          Торговый запуск: два клина вместе или Ikigai Box отдельно.
          Остальные выбранные стратегии ещё не подключены к изолированному Robot.
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
      {report && showReport && <section aria-label="Результаты виртуального прогона" className="replay-run-result" role="status">
        <strong>Результат локального SIMULATION · {report.symbol}</strong>
        <span>Реализованный Net PnL: {report.realized_net_pnl} USDT ·
          нереализованный: {report.unrealized_pnl} USDT</span>
        <span>Суммарный PnL: {report.total_net_pnl} USDT ·
          доходность: {report.return_percent}% · просадка: {report.max_drawdown_percent}%</span>
        {report.scenario_type === "ORIGINAL_IKIGAI_BOX_SCANNER_ROBOT_LOCAL_OHLC_SIMULATION"
          ? <span>Ikigai Box: найдено {report.scanner_box_observations} ·
              допущено Robot {report.admitted_box_candidates} ·
              исполнено входов {report.box_entry_fills} ·
              всех исполнений {report.virtual_fills} ·
              STOP: {report.stop_exits} · TAKE: {report.take_exits}</span>
          : <span>Клинья: найдено {report.scanner_wedge_observations} ·
              ретестов {report.robot_retests_in_period} ·
              LIMIT: {report.submitted_protected_limits} ·
              исполнений: {report.virtual_fills} · STOP: {report.stop_exits} ·
              TAKE: {report.take_exits}</span>}
        <small>Модель OHLC, не фактические биржевые исполнения. Параметры риска — локальные исследовательские допущения.</small>
      </section>}
    </section>
  );
}

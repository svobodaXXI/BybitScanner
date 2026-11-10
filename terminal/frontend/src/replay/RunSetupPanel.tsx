import { useEffect, useMemo, useState } from "react";
import {
  ALL_SELECTABLE, MIRROR_OPTIONS, OTHER_OPTIONS, PLANNED_OPTIONS,
  clearAll, isAllSelected, onlyWedges, presetEndInclusive,
  selectAll, toggleMirror, toggleStrategy, validateInclusiveWindow,
  type PeriodPreset, type RunSelection, type StrategyId,
} from "./runSetup";
import "./runSetup.css";

const INITIAL_START = new Date(Date.now() - 3 * 86_400_000).toISOString().slice(0, 16);
const PRESETS: Array<{ id: PeriodPreset; name: string }> = [
  { id: "DAY", name: "День" },
  { id: "WEEK", name: "Неделя" },
  { id: "MONTH", name: "Месяц · 30 дней" },
  { id: "THREE_MONTHS", name: "3 месяца · 90 дней" },
];

type LocalSimulationStatus = {
  can_attempt: boolean;
  wedge_engine_available: boolean;
  python_dependencies_available: boolean;
  archive_files_present: boolean;
  wedge_risk_profile_present: boolean;
};
type LocalSimulationReport = {
  scenario_type: string;
  namespace: string;
  source_id: string;
  minutes: number;
  virtual_fills: number;
  submitted_protected_limits: number;
  stop_exits: number;
  take_exits: number;
  total_net_pnl: string;
  return_percent: string;
  total_fees: string;
  max_drawdown_percent: string;
  pending_order_id: string | null;
  risk_terms_status: string;
};

/** One local viewer and one virtual-only engine.
 * The button never calls the PAPER/LIVE API or an external trading endpoint.
 */
export function RunSetupPanel({ symbol }: { symbol: string }) {
  const [selection, setSelection] = useState<RunSelection>(clearAll);
  const [start, setStart] = useState(INITIAL_START);
  const [end, setEnd] = useState(() => presetEndInclusive(INITIAL_START, "DAY"));
  const [preset, setPreset] = useState<PeriodPreset | null>("DAY");
  const [openMirror, setOpenMirror] = useState(true);
  const [initialBalance, setInitialBalance] = useState("1000");
  const [availability, setAvailability] = useState<LocalSimulationStatus | null>(null);
  const [availabilityError, setAvailabilityError] = useState("");
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState("");
  const [runReport, setRunReport] = useState<LocalSimulationReport | null>(null);
  useEffect(() => {
    let cancelled = false;
    void fetch("/local-replay/simulation/status", { cache: "no-store" })
      .then(async response => {
        if (!response.ok) throw new Error("Локальный сервер симуляции недоступен");
        return response.json() as Promise<LocalSimulationStatus>;
      })
      .then(info => { if (!cancelled) setAvailability(info); })
      .catch(() => { if (!cancelled) setAvailabilityError("Локальный движок не обнаружен"); });
    return () => { cancelled = true; };
  }, []);
  const parsed = useMemo(() => {
    try {
      return { window: validateInclusiveWindow(start, end), error: "" };
    } catch (error) {
      return { window: null, error: error instanceof Error ? error.message : "Некорректный период" };
    }
  }, [start, end]);
  const active = ALL_SELECTABLE.filter(id => selection.selected.includes(id));
  const mirrorSelected = MIRROR_OPTIONS.filter(x => selection.selected.includes(x.id)).length;
  const wedgeOnly = !selection.mirror && active.length > 0 && active.every(
    id => id === "WEDGE_FALLING" || id === "WEDGE_RISING",
  );
  const balanceOk = /^(?:0|[1-9]\d*)(?:\.\d{1,8})?$/.test(initialBalance) &&
    Number(initialBalance) > 0 && Number.isFinite(Number(initialBalance));
  const canRun = availability?.can_attempt === true && wedgeOnly &&
    parsed.window !== null && balanceOk && !running;

  async function runWedges() {
    if (!canRun) return;
    setRunning(true); setRunError(""); setRunReport(null);
    try {
      const response = await fetch("/local-replay/simulation/wedge", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Local-Simulation": "wedge",
        },
        cache: "no-store",
        body: JSON.stringify({
          symbol: symbol.trim().toUpperCase(),
          selected_strategies: active,
          start_utc: start,
          end_utc_inclusive: end,
          initial_balance: initialBalance,
        }),
      });
      const raw: unknown = await response.json();
      if (!response.ok) {
        const error = raw && typeof raw === "object" && "error" in raw &&
          typeof raw.error === "string" ? raw.error : "SIMULATION не смог завершить прогон";
        throw new Error(error);
      }
      if (!raw || typeof raw !== "object" || !("namespace" in raw) ||
          raw.namespace !== "SIMULATION" || !("scenario_type" in raw) ||
          raw.scenario_type !== "ORIGINAL_WEDGE_SCANNER_ROBOT_LOCAL_OHLC_SIMULATION") {
        throw new Error("Ответ не является проверенным локальным отчётом SIMULATION");
      }
      setRunReport(raw as LocalSimulationReport);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "Локальный прогон не завершился");
    } finally { setRunning(false); }
  }

  const updateStart = (value: string) => {
    setStart(value);
    if (preset) {
      try { setEnd(presetEndInclusive(value, preset)); } catch { /* Display validation until input completed. */ }
    }
  };
  const choosePreset = (next: PeriodPreset) => {
    setPreset(next);
    try { setEnd(presetEndInclusive(start, next)); } catch { /* Invalid start remains visible. */ }
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
          <label>Виртуальный начальный баланс · USDT
            <input aria-label="Виртуальный депозит USDT" type="text" inputMode="decimal"
              value={initialBalance} onChange={e => setInitialBalance(e.target.value)} />
          </label>
          <div className="replay-run-presets" role="group" aria-label="Длина прогона">
            {PRESETS.map(option => <button key={option.id} type="button"
              aria-pressed={preset === option.id}
              onClick={() => choosePreset(option.id)}>{option.name}</button>)}
          </div>
          <label>Конец · дата и время, включительно
            <input aria-label="Конец прогона UTC" type="datetime-local" step={60}
              value={end} onChange={e => { setPreset(null); setEnd(e.target.value); }} />
          </label>
          {parsed.error ? <p role="alert" className="replay-run-error">{parsed.error}</p> :
            <p role="status" className="replay-run-summary">
              {parsed.window?.minutes.toLocaleString("ru-RU")} минут M1 · конечная минута включена
            </p>}
        </fieldset>
      </div>
      <div className="replay-run-footer">
        <span data-selected-strategies={active.join(",")}>
          Выбрано компонентов: {active.length}. {selection.mirror ? "Mirror включён." : "Mirror выключен."}
        </span>
        <button type="button" disabled={!canRun} onClick={() => void runWedges()}
          title={!wedgeOnly ? "Для торговли доступны только клинья без комплекса Mirror" :
            availability?.can_attempt ? "Только локальная виртуальная торговля" :
            "Требуются движок, проверенный архив и явный профиль виртуального риска"}>
          {running ? "Считаю виртуальный прогон…" : "Запустить клинья · SIMULATION"}
        </button>
      </div>
      <p className="replay-run-disclaimer" role="status">
        {!wedgeOnly && active.length > 0 ?
          "Выбраны пока не подключённые стратегии: торговый запуск заблокирован. Режим «Только клинья» поддерживается." :
          availabilityError || (!availability ? "Проверяю локальный движок…" :
            availability.can_attempt ? "Движок и локальные файлы обнаружены. Контрольные суммы архива проверяются при запуске." :
            "Запуск недоступен: нужен полный локальный движок, pandas, проверенный архив Bybit и отдельный профиль риска 1 WV.")}
        {" "}Прежний просмотр M5 остаётся отдельным режимом без сделок.
      </p>
      {!balanceOk && <p role="alert" className="replay-run-error">Укажите положительный виртуальный депозит USDT</p>}
      {runError && <p role="alert" className="replay-run-error">{runError}</p>}
      {runReport && <section className="replay-run-result" aria-label="Результат виртуального прогона">
        <strong>Результат · только SIMULATION</strong>
        <div>Net PnL: {runReport.total_net_pnl} USDT · доходность {runReport.return_percent}%</div>
        <div>Виртуальных исполнений: {runReport.virtual_fills}, входных LIMIT: {runReport.submitted_protected_limits},
          STOP: {runReport.stop_exits}, TAKE: {runReport.take_exits}</div>
        <div>Комиссии: {runReport.total_fees} USDT · максимальная просадка {runReport.max_drawdown_percent}%</div>
        <div>Минут M1: {runReport.minutes} · заявка в ожидании: {runReport.pending_order_id ?? "нет"}</div>
        <small>Это модель OHLC, не реальные исполнения Bybit. Размер 1 WV задаётся исследовательским профилем, не подтверждает биржевую пригодность.</small>
      </section>}

    </section>
  );
}

import { useMemo, useState } from "react";
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

/** Configuration-only surface for the future original Scanner/Robot integration.
 * No requests, import of trading modules, order submission or PAPER IO.
 */
export function RunSetupPanel({ symbol }: { symbol: string }) {
  const [selection, setSelection] = useState<RunSelection>(clearAll);
  const [start, setStart] = useState(INITIAL_START);
  const [end, setEnd] = useState(() => presetEndInclusive(INITIAL_START, "DAY"));
  const [preset, setPreset] = useState<PeriodPreset | null>("DAY");
  const [openMirror, setOpenMirror] = useState(true);
  const parsed = useMemo(() => {
    try {
      return { window: validateInclusiveWindow(start, end), error: "" };
    } catch (error) {
      return { window: null, error: error instanceof Error ? error.message : "Некорректный период" };
    }
  }, [start, end]);
  const active = ALL_SELECTABLE.filter(id => selection.selected.includes(id));
  const mirrorSelected = MIRROR_OPTIONS.filter(x => selection.selected.includes(x.id)).length;

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
        <button type="button" disabled title="Фактический Scanner/Robot ещё не подключён к изолированному SIMULATION">
          Торговый прогон — ожидает подключения Robot
        </button>
      </div>
      <p className="replay-run-disclaimer">
        Пока это только настройка. Торговля и общий PnL не выполняются.
        Ниже доступен прежний просмотр публичных M5 (до 7 суток); он не использует эти новые настройки.
        Для теста доходности клиньев требуется подключить оригинальный Scanner/Robot к виртуальному исполнителю.
      </p>
    </section>
  );
}

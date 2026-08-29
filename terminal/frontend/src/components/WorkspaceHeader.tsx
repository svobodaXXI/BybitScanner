import { useEffect, useRef, useState } from "react";
import {
  CHART_TIMEFRAMES,
  type ChartTimeframe,
} from "../marketData/timeframes";
import { baseAssetFromSymbol } from "../marketData/symbol";

interface WorkspaceHeaderProps {
  instruments: readonly string[];
  onSymbolSelect: (symbol: string) => void;
  onTimeframeChange: (timeframe: ChartTimeframe) => void;
  symbol: string;
  timeframe: ChartTimeframe;
}

export function WorkspaceHeader({
  instruments,
  onSymbolSelect,
  onTimeframeChange,
  symbol,
  timeframe,
}: WorkspaceHeaderProps) {
  const [timeframeOpen, setTimeframeOpen] = useState(false);
  const [symbolOpen, setSymbolOpen] = useState(false);
  const [symbolQuery, setSymbolQuery] = useState("");
  const symbolRef = useRef<HTMLDivElement>(null);
  const timeframeRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!timeframeOpen) return;
    const dismissOutside = (event: PointerEvent) => {
      if (!timeframeRef.current?.contains(event.target as Node)) {
        setTimeframeOpen(false);
      }
    };
    const dismissEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setTimeframeOpen(false);
    };
    document.addEventListener("pointerdown", dismissOutside);
    document.addEventListener("keydown", dismissEscape);
    return () => {
      document.removeEventListener("pointerdown", dismissOutside);
      document.removeEventListener("keydown", dismissEscape);
    };
  }, [timeframeOpen]);
  useEffect(() => {
    if (!symbolOpen) return;
    const dismissOutside = (event: PointerEvent) => {
      if (!symbolRef.current?.contains(event.target as Node)) setSymbolOpen(false);
    };
    const dismissEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSymbolOpen(false);
    };
    document.addEventListener("pointerdown", dismissOutside);
    document.addEventListener("keydown", dismissEscape);
    return () => {
      document.removeEventListener("pointerdown", dismissOutside);
      document.removeEventListener("keydown", dismissEscape);
    };
  }, [symbolOpen]);
  const normalizedQuery = symbolQuery.trim().toUpperCase();
  const matches = normalizedQuery
    ? instruments.filter((instrument) => instrument.includes(normalizedQuery))
    : instruments;
  return (
    <div className="chart-workspace-controls" data-chart-control>
      <div className="instrument-block" ref={symbolRef}>
        <button
          className="symbol-selector-trigger"
          type="button"
          aria-label={`Select symbol ${symbol}`}
          onClick={() => {
            setSymbolQuery("");
            setSymbolOpen(true);
          }}
        >
          {baseAssetFromSymbol(symbol)}
        </button>
        {symbolOpen ? (
          <div className="symbol-selector-popover" role="dialog" aria-label="Выбор инструмента">
            <input
              autoFocus
              aria-label="Поиск инструмента"
              onChange={(event) => setSymbolQuery(event.target.value)}
              placeholder="BTC, ON..."
              value={symbolQuery}
            />
            <div className="symbol-selector-results" role="listbox">
              {matches.map((instrument) => (
                <button
                  key={instrument}
                  onClick={() => {
                    onSymbolSelect(instrument);
                    setSymbolOpen(false);
                  }}
                  role="option"
                  type="button"
                >{instrument}</button>
              ))}
              {matches.length === 0 ? <span>Инструменты не найдены</span> : null}
            </div>
            <button onClick={() => setSymbolOpen(false)} type="button">Отмена</button>
          </div>
        ) : null}
        <div className="timeframe-selector" ref={timeframeRef}>
          <button
            aria-expanded={timeframeOpen}
            aria-label="Select chart timeframe"
            className="timeframe-display"
            onClick={() => setTimeframeOpen((open) => !open)}
            type="button"
          >
            {timeframe}
          </button>
          {timeframeOpen ? (
            <div className="timeframe-menu" role="menu">
              {CHART_TIMEFRAMES.map((option) => (
                <button
                  aria-current={option === timeframe ? "true" : undefined}
                  key={option}
                  onClick={() => {
                    onTimeframeChange(option);
                    setTimeframeOpen(false);
                  }}
                  role="menuitem"
                  type="button"
                >
                  {option}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

import { useEffect, useRef, useState } from "react";
import {
  CHART_TIMEFRAMES,
  type ChartTimeframe,
} from "../marketData/timeframes";

interface WorkspaceHeaderProps {
  accountOpen: boolean;
  onAccountToggle: () => void;
  onSymbolClick: () => void;
  onTimeframeChange: (timeframe: ChartTimeframe) => void;
  symbol: string;
  timeframe: ChartTimeframe;
}

export function WorkspaceHeader({
  accountOpen,
  onAccountToggle,
  onSymbolClick,
  onTimeframeChange,
  symbol,
  timeframe,
}: WorkspaceHeaderProps) {
  const [timeframeOpen, setTimeframeOpen] = useState(false);
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
  return (
    <header className="workspace-header">
      <div className="instrument-block">
        <button
          className="symbol-selector-trigger"
          type="button"
          aria-label={`Select symbol ${symbol}`}
          onClick={onSymbolClick}
        >
          {symbol}
        </button>
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
      <div className="header-actions">
        <button
          aria-expanded={accountOpen}
          aria-label="Open account selection"
          className="account-switch-button"
          onClick={onAccountToggle}
          type="button"
        >
          <span className="account-switch-key" aria-hidden="true">
            <span className="account-key-head" />
            <span className="account-key-shaft" />
          </span>
          <span className="account-switch-label">
            <strong>PAPER</strong>
            <small>NON-LIVE</small>
          </span>
        </button>
      </div>
    </header>
  );
}

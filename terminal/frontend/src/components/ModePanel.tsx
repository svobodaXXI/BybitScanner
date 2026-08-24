import { useCallback, useEffect, useRef, useState } from "react";

export type WorkspaceMode = "TERMINAL" | "AUTOPILOT" | "EDITOR";
type MarketSide = "Buy" | "Sell";

const descriptions: Record<WorkspaceMode, string> = {
  TERMINAL: "Manual PAPER execution is available for the development instrument.",
  AUTOPILOT: "Robot observation and control are intentionally not implemented.",
  EDITOR: "Editor tools are reserved for a later authorized slice.",
};

export function ModePanel({
  mode,
  onModeChange,
}: {
  mode: WorkspaceMode;
  onModeChange: (mode: WorkspaceMode) => void;
}) {
  const [executionStatus, setExecutionStatus] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [engagedWorkingVolume, setEngagedWorkingVolume] = useState<string | null>(
    null,
  );
  const submissionInFlight = useRef(false);

  const refreshPaperState = useCallback(async () => {
    try {
      const response = await fetch("/api/paper-state?symbol=BTCUSDT");
      if (!response.ok) {
        setEngagedWorkingVolume(null);
        return;
      }

      const state = (await response.json()) as {
        ok: boolean;
        engaged_wv: string;
      };

      const engagedWv = Number(state.engaged_wv);
      setEngagedWorkingVolume(
        state.ok && Number.isFinite(engagedWv) ? engagedWv.toFixed(1) : null,
      );
    } catch {
      setEngagedWorkingVolume(null);
    }
  }, []);

  useEffect(() => {
    if (mode === "TERMINAL") {
      void refreshPaperState();
    }
  }, [mode, refreshPaperState]);

  const alternatives = (["TERMINAL", "AUTOPILOT", "EDITOR"] as const).filter(
    (candidate) => candidate !== mode,
  );

  const submitPaperMarket = async (side: MarketSide) => {
    if (submissionInFlight.current) return;

    submissionInFlight.current = true;
    setIsSubmitting(true);

    try {
      const result = await fetch("/api/market", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_action_id: `paper-market-${side.toLowerCase()}-${Date.now()}`,
          symbol: "BTCUSDT",
          side,
          volume: { unit: "working_volume", amount: "1" },
          sizing_reference_price: "64250",
          slippage_type: "Percent",
          slippage_value: "0.5",
        }),
      });

      const commandResult = (await result.json()) as { status: string };

      setExecutionStatus(
        commandResult.status === "completed"
          ? `PAPER ${side.toUpperCase()} completed`
          : `PAPER ${side.toUpperCase()} not completed`,
      );

      if (commandResult.status === "completed") {
        await refreshPaperState();
      }
    } catch {
      setExecutionStatus("PAPER execution unavailable");
    } finally {
      submissionInFlight.current = false;
      setIsSubmitting(false);
    }
  };

  return (
    <section className="mode-panel" aria-label={`${mode} controls`}>
      <div>
        <p className="eyebrow">Active mode</p>
        <h2>{mode}</h2>
        <p>{descriptions[mode]}</p>
      </div>

      <nav className="mode-switcher" aria-label="Workspace modes">
        {alternatives.map((candidate) => (
          <button
            key={candidate}
            onClick={() => onModeChange(candidate)}
            type="button"
          >
            {candidate}
          </button>
        ))}
      </nav>

      {mode === "TERMINAL" ? (
        <div className="paper-market-actions">
          <div className="paper-wv-indicator" aria-label="Engaged working volume">
            {"\u2694\uFE0F"} {engagedWorkingVolume ?? "\u2014"}
          </div>
          <button
            onClick={() => submitPaperMarket("Buy")}
            className="paper-market-buy"
            disabled={isSubmitting}
            type="button"
          >
            {isSubmitting ? "..." : "BUY"}
          </button>

          <button
            onClick={() => submitPaperMarket("Sell")}
            className="paper-market-sell"
            disabled={isSubmitting}
            type="button"
          >
            {isSubmitting ? "..." : "SELL"}
          </button>

          <p className="paper-execution-status" aria-live="polite">
            {executionStatus}
          </p>
        </div>
      ) : null}
    </section>
  );
}

import { useEffect, useMemo, useState } from "react";
import type { Candle } from "../contracts/marketData";
import type { DrawingObject } from "../chart/drawingModel";
import type { RobotTradeMarker } from "../chart/robotTradeMarkers";
import type { TimestampDrawing } from "../geometryFeedback/geometryReviewDraft";
import { projectSignalGeometry } from "../geometryFeedback/signalChartBridge";
import type { RobotPositionOrigin } from "./robotPositionOrigin";
import { parseProvenRobotSignalGeometry, robotSignalTimeframeMatchesChart } from "./robotSignalGeometry";

type RobotMarkerSnapshot = {
  symbol: string; tradeId: string; markers: RobotTradeMarker[];
  origin: RobotPositionOrigin | null;
};

export function useRobotSignalGeometry(args: {
  observing: boolean;
  tradeId: string | null;
  symbol: string;
  markers: RobotMarkerSnapshot | null;
  timeframe: string;
  candles: readonly Candle[];
}): { drawings: DrawingObject[] | null; status: "loading" | "ready" | "unavailable"; origin: RobotPositionOrigin | null } {
  const { observing, tradeId, symbol, markers, timeframe, candles } = args;
  const origin = observing && tradeId && markers?.tradeId === tradeId &&
    markers.symbol === symbol ? markers.origin : null;
  const candidateId = origin?.candidate_id ?? null;
  const signalMinutes = origin?.signal_timeframe_minutes ?? null;
  const [source, setSource] = useState<{
    tradeId: string; candidateId: string; symbol: string; boundaries: TimestampDrawing[];
  } | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "unavailable">("unavailable");

  useEffect(() => {
    setSource(null);
    setStatus("unavailable");
    if (!observing || !tradeId || !candidateId || !origin || signalMinutes === null) return;
    const controller = new AbortController();
    const capturedOrigin = origin;
    setStatus("loading");
    void (async () => {
      try {
        const response = await fetch(
          `/api/workspace/signal-geometry?signal_id=${encodeURIComponent(candidateId)}`,
          { signal: controller.signal, credentials: "same-origin" },
        );
        if (!response.ok) throw new Error("Original geometry unavailable");
        const boundaries = parseProvenRobotSignalGeometry(await response.json(), {
          candidateId, symbol, origin: capturedOrigin,
        });
        if (!boundaries) throw new Error("Original signal identity unproven");
        if (!controller.signal.aborted) {
          setSource({ tradeId, candidateId, symbol, boundaries });
          setStatus("ready");
        }
      } catch {
        // Do not reconstruct signals from current OHLC, symbol, or pattern.
        if (!controller.signal.aborted) setStatus("unavailable");
      }
    })();
    return () => controller.abort();
  }, [observing, tradeId, symbol, candidateId, signalMinutes]);

  const drawings = useMemo(() => {
    if (!observing || !tradeId || !origin || !source ||
        source.tradeId !== tradeId || source.symbol !== symbol ||
        source.candidateId !== candidateId ||
        !robotSignalTimeframeMatchesChart(origin, timeframe)) return null;
    try {
      return projectSignalGeometry(source.boundaries, candles).referenceDrawings;
    } catch {
      // Exact frozen source pivots may be outside the current live window.
      return null;
    }
  }, [observing, tradeId, origin, source, symbol, candidateId, timeframe, candles]);

  return { drawings, status, origin };
}

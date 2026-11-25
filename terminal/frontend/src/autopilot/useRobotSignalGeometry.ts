import { useEffect, useMemo, useState } from "react";
import type { Candle } from "../contracts/marketData";
import type { DrawingObject } from "../chart/drawingModel";
import type { RobotTradeMarker } from "../chart/robotTradeMarkers";
import type { TimestampDrawing } from "../geometryFeedback/geometryReviewDraft";
import { parseGeometryRevisions, type GeometryRevisionObservation } from "../replay/paperEpisodeFacts";
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
}): { drawings: DrawingObject[] | null; status: "loading" | "ready" | "unavailable"; origin: RobotPositionOrigin | null; revisions: GeometryRevisionObservation[] } {
  const { observing, tradeId, symbol, markers, timeframe, candles } = args;
  const origin = observing && tradeId && markers?.tradeId === tradeId &&
    markers.symbol === symbol ? markers.origin : null;
  const candidateId = origin?.candidate_id ?? null;
  const signalMinutes = origin?.signal_timeframe_minutes ?? null;
  const [source, setSource] = useState<{
    tradeId: string; candidateId: string; symbol: string; boundaries: TimestampDrawing[]; revisions: GeometryRevisionObservation[];
  } | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "unavailable">("unavailable");

  useEffect(() => {
    setSource(null);
    setStatus("unavailable");
    if (!observing || !tradeId || !candidateId || !origin || signalMinutes === null) return;
    const controller = new AbortController();
    const capturedOrigin = origin;
    setStatus("loading");
    let timer: ReturnType<typeof setTimeout> | undefined;
    const isWedge = capturedOrigin.pattern === "Falling Wedge" || capturedOrigin.pattern === "Rising Wedge";
    const refresh = async () => {
      try {
        const response = await fetch(
          `/api/workspace/signal-geometry?signal_id=${encodeURIComponent(candidateId)}`,
          { signal: controller.signal, credentials: "same-origin" },
        );
        if (!response.ok) throw new Error("Original geometry unavailable");
        const body = await response.json();
        const boundaries = parseProvenRobotSignalGeometry(body, {
          candidateId, symbol, origin: capturedOrigin,
        });
        if (!boundaries) throw new Error("Original signal identity unproven");
        let revisions: GeometryRevisionObservation[] = [];
        if (isWedge && body.geometry_revisions && typeof body.snapshot_revision === "string") {
          try {
            revisions = parseGeometryRevisions(body.geometry_revisions, {
              signal_id: candidateId, sha256: body.snapshot_revision,
              sent_at_ms: 0,
              boundaries: boundaries.map(b => ({ boundary_id: b.id,
                kind: b.type as "ray" | "segment" | "horizontal" | "horizontal-ray",
                anchors: b.anchors })),
            }, capturedOrigin.pattern === "Falling Wedge" ? "LONG" : "SHORT", Date.now());
          } catch { /* Original stays available if revision evidence is invalid. */ }
        }
        if (!controller.signal.aborted) {
          setSource({ tradeId, candidateId, symbol, boundaries, revisions });
          setStatus("ready");
        }
      } catch {
        // Do not reconstruct signals from current OHLC, symbol, or pattern.
        if (!controller.signal.aborted) setStatus("unavailable");
      } finally {
        if (isWedge && !controller.signal.aborted) timer = setTimeout(() => void refresh(), 5000);
      }
    };
    void refresh();
    return () => { controller.abort(); if (timer !== undefined) clearTimeout(timer); };
  }, [observing, tradeId, symbol, candidateId, signalMinutes]);

  const drawings = useMemo(() => {
    if (!observing || !tradeId || !origin || !source ||
        source.tradeId !== tradeId || source.symbol !== symbol ||
        source.candidateId !== candidateId ||
        !robotSignalTimeframeMatchesChart(origin, timeframe)) return null;
    try {
      const latest = source.revisions[source.revisions.length - 1];
      if (!latest) return projectSignalGeometry(source.boundaries, candles).referenceDrawings;
      const current = latest.current_boundary, previous = latest.previous_boundary;
      const drawings = source.boundaries.map(b => b.id === current.boundary_id
        ? { ...b, anchors: current.anchors } : b);
      drawings.push({ id: "previous:" + previous.boundary_id, type: "ray", anchors: previous.anchors });
      return drawings.flatMap(b => {
        try {
          // Native time projection only; never refit a ray to live OHLC.
          let anchors = b.anchors;
          if (b.type === "ray" && !anchors.every(a => candles.some(c => Date.parse(c.time) === a.bar_open_time_ms))) {
            const [a, z] = anchors;
            const times = candles.map(c => Date.parse(c.time)).filter(time => time >= z.bar_open_time_ms);
            if (times.length < 2) return [];
            anchors = times.slice(0,2).map(time => ({bar_open_time_ms: time,
              price: a.price + (z.price-a.price)*(time-a.bar_open_time_ms)/(z.bar_open_time_ms-a.bar_open_time_ms)}));
          }
          return projectSignalGeometry([{...b, anchors}], candles).referenceDrawings.map(d => ({
            ...d, referenceStroke: d.id === current.boundary_id ? "solid" as const : "dashed" as const,
          }));
        } catch { return []; }
      });
    } catch {
      // Exact frozen source pivots may be outside the current live window.
      return null;
    }
  }, [observing, tradeId, origin, source, symbol, candidateId, timeframe, candles]);

  const revisions = observing && tradeId && source?.tradeId === tradeId &&
    source.symbol === symbol && source.candidateId === candidateId ? source.revisions : [];
  return { drawings, status, origin, revisions };
}

import { useCallback, useEffect, useRef } from "react";
import type { Candle } from "../contracts/marketData";
import {
  nearestOhlcAnchor,
  type Point,
  pointDistance,
  rayEndPoint,
  segmentDistance,
} from "./drawingGeometry";
import {
  type DrawingAnchor,
  type DrawingObject,
  type DrawingTool,
  fibonacciPrices,
  rulerMeasurement,
} from "./drawingModel";

export interface DrawingCoordinates {
  logicalToX(value: number): number | null;
  xToLogical(value: number): number | null;
  priceToY(value: number): number | null;
  yToPrice(value: number): number | null;
}
const HIT_RADIUS = 12;
const fmtDuration = (seconds: number) =>
  seconds >= 3600
    ? `${Math.floor(seconds / 3600)}h${Math.floor((seconds % 3600) / 60)}m`
    : `${Math.floor(seconds / 60)}m`;

export function DrawingOverlay({
  drawings,
  selectedId,
  tool,
  magnet,
  candles,
  coordinates,
  onCommit,
  onSelect,
  onDrawingGesture,
  onDrawingComplete,
}: {
  drawings: DrawingObject[];
  selectedId: string | null;
  tool: DrawingTool;
  magnet: boolean;
  candles: readonly Candle[];
  coordinates: DrawingCoordinates;
  onCommit: (drawings: DrawingObject[]) => void;
  onSelect: (id: string | null) => void;
  onDrawingGesture: () => void;
  onDrawingComplete: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const draftRef = useRef<DrawingObject | null>(null);
  const dragRef = useRef<{
    id: string;
    anchor: number | null;
    start: DrawingAnchor;
    original: DrawingObject;
  } | null>(null);
  const pointOf = useCallback(
    (a: DrawingAnchor): Point | null => {
      const x = coordinates.logicalToX(a.logical),
        y = coordinates.priceToY(a.price);
      return x === null || y === null ? null : { x, y };
    },
    [coordinates],
  );
  const anchorOf = useCallback(
    (event: React.PointerEvent): DrawingAnchor | null => {
      const rect = event.currentTarget.getBoundingClientRect();
      const logical = coordinates.xToLogical(event.clientX - rect.left),
        price = coordinates.yToPrice(event.clientY - rect.top);
      if (logical === null || price === null) return null;
      const a = { logical, price };
      return magnet
        ? nearestOhlcAnchor(
            a,
            candles,
            coordinates.logicalToX,
            coordinates.priceToY,
          )
        : a;
    },
    [candles, coordinates, magnet],
  );
  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect(),
      ratio = devicePixelRatio || 1;
    if (
      canvas.width !== rect.width * ratio ||
      canvas.height !== rect.height * ratio
    ) {
      canvas.width = rect.width * ratio;
      canvas.height = rect.height * ratio;
    }
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, rect.width, rect.height);
    for (const drawing of [
      ...drawings,
      ...(draftRef.current && !drawings.some((item) => item.id === draftRef.current?.id)
        ? [draftRef.current]
        : []),
    ]) {
      if (drawing.hidden) continue;
      const points = drawing.anchors
        .map(pointOf)
        .filter((p): p is Point => p !== null);
      if (!points.length) continue;
      ctx.strokeStyle = drawing.style.color;
      ctx.fillStyle = drawing.style.color;
      ctx.lineWidth = drawing.style.lineWidth;
      ctx.beginPath();
      const [a, b = a] = points;
      if (drawing.type === "horizontal") {
        ctx.moveTo(0, a.y);
        ctx.lineTo(rect.width, a.y);
      } else if (drawing.type === "horizontal-ray") {
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(rect.width, a.y);
      } else if (drawing.type === "vertical") {
        ctx.moveTo(a.x, 0);
        ctx.lineTo(a.x, rect.height);
      } else if (drawing.type === "ray") {
        const end = rayEndPoint(a, b, rect);
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(end.x, end.y);
      } else if (drawing.type === "rectangle") {
        ctx.rect(a.x, a.y, b.x - a.x, b.y - a.y);
      } else if (drawing.type === "fibonacci") {
        for (const item of fibonacciPrices(
          drawing.anchors[0].price,
          drawing.anchors[1]?.price ?? drawing.anchors[0].price,
        )) {
          const y = coordinates.priceToY(item.price);
          if (y === null) continue;
          ctx.moveTo(Math.min(a.x, b.x), y);
          ctx.lineTo(Math.max(a.x, b.x), y);
          ctx.fillText(
            `${item.level}  ${item.price.toFixed(4)}`,
            Math.min(a.x, b.x) + 4,
            y - 3,
          );
        }
      } else {
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
      }
      ctx.stroke();
      if (drawing.type === "ruler" && drawing.anchors[1]) {
        const m = rulerMeasurement(drawing.anchors[0], drawing.anchors[1]);
        const sign = m.priceDelta >= 0 ? "+" : "";
        ctx.fillText(
          `${sign}${m.percentDelta.toFixed(2)}% · ${sign}${m.priceDelta.toFixed(4)} · ${m.bars} bars · ${fmtDuration(m.elapsedSeconds)}`,
          b.x + 6,
          b.y - 8,
        );
      }
      if (drawing.id === selectedId) {
        for (const p of points) {
          ctx.beginPath();
          ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
          ctx.fill();
          ctx.strokeStyle = "#10151b";
          ctx.stroke();
        }
      }
    }
  }, [drawings, pointOf, selectedId, coordinates]);
  useEffect(() => {
    redraw();
    const id = requestAnimationFrame(redraw);
    return () => cancelAnimationFrame(id);
  }, [redraw]);
  useEffect(() => {
    if (draftRef.current && selectedId !== draftRef.current.id) {
      draftRef.current = null;
      redraw();
    }
  }, [redraw, selectedId]);
  const hit = (point: Point, bounds: { width: number; height: number }) => {
    for (let i = drawings.length - 1; i >= 0; i--) {
      const d = drawings[i];
      if (d.hidden) continue;
      const pts = d.anchors.map(pointOf).filter((p): p is Point => p !== null);
      for (let a = 0; a < pts.length; a++)
        if (pointDistance(point, pts[a]) <= HIT_RADIUS)
          return { id: d.id, anchor: a };
      if (pts.length === 1) {
        if (
          (d.type === "horizontal" &&
            Math.abs(point.y - pts[0].y) < HIT_RADIUS) ||
          (d.type === "vertical" && Math.abs(point.x - pts[0].x) < HIT_RADIUS)
        )
          return { id: d.id, anchor: null };
      } else if (
        segmentDistance(
          point,
          pts[0],
          d.type === "ray" ? rayEndPoint(pts[0], pts[1], bounds) : pts[1],
        ) < HIT_RADIUS
      )
        return { id: d.id, anchor: null };
    }
    return null;
  };
  const withDrawing = (drawing: DrawingObject) =>
    drawings.some((item) => item.id === drawing.id)
      ? drawings.map((item) => item.id === drawing.id ? drawing : item)
      : [...drawings, drawing];
  const onPointerDown = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (event.pointerType === "touch" && event.isPrimary === false) return;
    const anchor = anchorOf(event);
    if (!anchor) return;
    const rect = event.currentTarget.getBoundingClientRect();
    if (draftRef.current) {
      draftRef.current = {
        ...draftRef.current,
        anchors: [draftRef.current.anchors[0], anchor],
      };
      onCommit(withDrawing(draftRef.current));
      onSelect(draftRef.current.id);
      draftRef.current = null;
      onDrawingComplete();
      redraw();
      return;
    }
    if (tool === "select") {
      const found = hit(
        { x: event.clientX - rect.left, y: event.clientY - rect.top },
        rect,
      );
      onSelect(found?.id ?? null);
      if (found) {
        onDrawingGesture();
        const original = drawings.find((d) => d.id === found.id);
        if (original && !original.locked) {
          dragRef.current = {
            id: found.id,
            anchor: found.anchor,
            start: anchor,
            original,
          };
          event.currentTarget.setPointerCapture(event.pointerId);
        }
      }
      return;
    }
    if (tool === "crosshair") return;
    const type = tool;
    const single = ["horizontal", "horizontal-ray", "vertical"].includes(type);
    const draft = {
      id: `drawing-${Date.now()}`,
      type,
      anchors: [anchor],
      style: { color: "#e0b45b", lineWidth: 1.5 },
      locked: false,
      hidden: false,
    } as DrawingObject;
    if (single) {
      onCommit([...drawings, draft]);
      onSelect(draft.id);
      onDrawingComplete();
    } else {
      draft.anchors.push(anchor);
      draftRef.current = draft;
      onCommit(withDrawing(draft));
      onSelect(draft.id);
      onDrawingGesture();
      event.currentTarget.setPointerCapture(event.pointerId);
      redraw();
    }
  };
  const onPointerMove = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const anchor = anchorOf(event);
    if (!anchor) return;
    if (draftRef.current) {
      draftRef.current = {
        ...draftRef.current,
        anchors: [draftRef.current.anchors[0], anchor],
      };
      onCommit(withDrawing(draftRef.current));
      redraw();
      return;
    }
    const drag = dragRef.current;
    if (!drag) return;
    const next = drawings.map((d) => {
      if (d.id !== drag.id) return d;
      if (drag.anchor !== null)
        return {
          ...drag.original,
          anchors: drag.original.anchors.map((a, i) =>
            i === drag.anchor ? anchor : a,
          ),
        };
      return {
        ...drag.original,
        anchors: drag.original.anchors.map((a) => ({
          logical: a.logical + anchor.logical - drag.start.logical,
          price: a.price + anchor.price - drag.start.price,
        })),
      };
    });
    onCommit(next);
  };
  const finish = () => {
    dragRef.current = null;
    redraw();
  };
  return (
    <canvas
      ref={canvasRef}
      className={`drawing-overlay tool-${tool}`}
      aria-label="Drawing layer"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={finish}
      onPointerCancel={finish}
    />
  );
}

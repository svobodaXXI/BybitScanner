import type { DrawingTool } from "./drawingModel";
import { useState } from "react";

const tools: Array<[DrawingTool, string, string]> = [
  ["select", "\u2316", "Crosshair / chart interaction"],
  ["trend", "\u2571", "Straight line"],
  ["horizontal", "\u2014", "Horizontal line"],
  ["ray", "\u2197", "Ray"],
  ["horizontal-ray", "\u2192", "Horizontal ray"],
  ["ruler", "\u0394", "Ruler"],
  ["fibonacci", "Fib", "Fibonacci grid"],
];

export function DrawingToolbar({
  activeTool,
  magnet,
  selected,
  onTool,
  onMagnet,
  onUndo,
  onDelete,
  onClear,
}: {
  activeTool: DrawingTool;
  magnet: boolean;
  selected: boolean;
  onTool: (tool: DrawingTool) => void;
  onMagnet: () => void;
  onUndo: () => void;
  onDelete: () => void;
  onClear: () => void;
}) {
  const [open, setOpen] = useState(true);

  return (
    <aside className={`drawing-tools-panel${open ? "" : " is-collapsed"}`}>
      <button
        type="button"
        className="drawing-tools-toggle"
        title={`${open ? "Hide" : "Show"} drawing tools`}
        aria-label={`${open ? "Hide" : "Show"} drawing tools`}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? "\u02C4" : "\u02C5"}
      </button>
      {open ? <nav className="drawing-toolbar" aria-label="Drawing tools">
      {tools.map(([tool, icon, label]) => (
        <button
          key={tool}
          type="button"
          title={label}
          aria-label={label}
          aria-pressed={activeTool === tool}
          className={activeTool === tool ? "active" : ""}
          onClick={() => onTool(tool)}
        >
          {icon}
        </button>
      ))}
      <span className="drawing-toolbar-divider" />
      <button
        type="button"
        title="Magnet"
        aria-label="Magnet"
        aria-pressed={magnet}
        className={magnet ? "active" : ""}
        onClick={onMagnet}
      >
        {"\u{1F9F2}"}
      </button>
      <button
        type="button"
        title="Undo"
        aria-label="Undo drawing"
        onClick={onUndo}
      >
        {"\u21B6"}
      </button>
      {selected ? (
        <button
          type="button"
          title="Delete selected"
          aria-label="Delete selected drawing"
          onClick={onDelete}
        >
          {"\u232B"}
        </button>
      ) : null}
      <button
        type="button"
        title="Clear drawings"
        aria-label="Clear drawings"
        onClick={onClear}
      >
        {"\u00D7"}
      </button>
      </nav> : null}
    </aside>
  );
}

import type { DrawingTool } from "./drawingModel";

const tools: Array<[DrawingTool, string, string]> = [
  ["select", "⌖", "Crosshair / chart interaction"],
  ["trend", "╱", "Straight line"],
  ["horizontal", "—", "Horizontal line"],
  ["ray", "↗", "Ray"],
  ["horizontal-ray", "→", "Horizontal ray"],
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
  return (
    <nav className="drawing-toolbar" aria-label="Drawing tools">
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
        🧲
      </button>
      <button
        type="button"
        title="Undo"
        aria-label="Undo drawing"
        onClick={onUndo}
      >
        ↶
      </button>
      {selected ? (
        <button
          type="button"
          title="Delete selected"
          aria-label="Delete selected drawing"
          onClick={onDelete}
        >
          ⌫
        </button>
      ) : null}
      <button
        type="button"
        title="Clear drawings"
        aria-label="Clear drawings"
        onClick={onClear}
      >
        ×
      </button>
    </nav>
  );
}

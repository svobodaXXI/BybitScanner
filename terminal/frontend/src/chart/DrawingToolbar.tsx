import type { DrawingTool } from "./drawingModel";

const tools: Array<[DrawingTool, string, string]> = [
  ["select", "↖", "Select / cursor"],
  ["crosshair", "⌖", "Crosshair"],
  ["trend", "╱", "Trend line"],
  ["horizontal", "—", "Horizontal line"],
  ["ray", "↗", "Ray"],
  ["horizontal-ray", "→", "Horizontal ray"],
  ["vertical", "│", "Vertical line"],
  ["fibonacci", "Fib", "Fibonacci retracement"],
  ["ruler", "⌁", "Ruler"],
  ["rectangle", "□", "Rectangle"],
];

export function DrawingToolbar({
  activeTool,
  magnet,
  selected,
  onTool,
  onMagnet,
  onDelete,
  onUndo,
  onRedo,
  onClear,
  onLock,
}: {
  activeTool: DrawingTool;
  magnet: boolean;
  selected: boolean;
  onTool: (tool: DrawingTool) => void;
  onMagnet: () => void;
  onDelete: () => void;
  onUndo: () => void;
  onRedo: () => void;
  onClear: () => void;
  onLock: () => void;
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
      <button
        type="button"
        title="Redo"
        aria-label="Redo drawing"
        onClick={onRedo}
      >
        ↷
      </button>
      <button
        type="button"
        title="Lock selected"
        aria-label="Lock selected drawing"
        disabled={!selected}
        onClick={onLock}
      >
        🔒
      </button>
      <button
        type="button"
        title="Delete selected"
        aria-label="Delete selected drawing"
        disabled={!selected}
        onClick={onDelete}
      >
        ⌫
      </button>
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

export type WorkspaceMode = "TERMINAL" | "AUTOPILOT" | "EDITOR";
const descriptions: Record<WorkspaceMode, string> = {
  TERMINAL: "Manual controls remain disabled in this safe prototype.",
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
  const alternatives = (["TERMINAL", "AUTOPILOT", "EDITOR"] as const).filter(
    (candidate) => candidate !== mode,
  );
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
    </section>
  );
}

import type { PropsWithChildren } from "react";

interface WorkspacePanelProps extends PropsWithChildren {
  className?: string;
  title: string;
}

export function WorkspacePanel({
  children,
  className = "",
  title,
}: WorkspacePanelProps) {
  return (
    <section className={`workspace-panel ${className}`.trim()}>
      <h2>{title}</h2>
      <div className="panel-placeholder">{children}</div>
    </section>
  );
}

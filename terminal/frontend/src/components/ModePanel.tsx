import type { ComponentProps } from "react";
import {
  ModePanel as LegacyModePanel,
  type WorkspaceMode as LegacyWorkspaceMode,
} from "./ModePanelLegacy";
import { AutopilotDiaryControls } from "./AutopilotDiaryControls";

export type WorkspaceMode = LegacyWorkspaceMode;

type ModePanelProps = ComponentProps<typeof LegacyModePanel> & {
  autopilotTradeEpisodeId?: string | null;
};

export function ModePanel({
  autopilotTradeEpisodeId = null,
  ...props
}: ModePanelProps) {
  const accountKey = `${props.accountWorkspaceProjection?.account_id ?? "unknown"}:${props.accountWorkspaceProjection?.session_generation ?? 0}`;

  return (
    <>
      <LegacyModePanel {...props} />
      {props.mode === "AUTOPILOT" ? (
        <AutopilotDiaryControls
          accountKey={accountKey}
          tradeEpisodeId={autopilotTradeEpisodeId}
        />
      ) : null}
    </>
  );
}

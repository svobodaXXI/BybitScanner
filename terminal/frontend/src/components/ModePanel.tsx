import { useState, type ComponentProps } from "react";
import {
  ModePanel as LegacyModePanel,
  type WorkspaceMode as LegacyWorkspaceMode,
} from "./ModePanelLegacy";
import { AutopilotDiaryControls } from "./AutopilotDiaryControls";
import { AutopilotFirstScreen } from "./AutopilotFirstScreen";

export type WorkspaceMode = LegacyWorkspaceMode;

type ModePanelProps = ComponentProps<typeof LegacyModePanel> & {
  autopilotTradeEpisodeId?: string | null;
};

export function ModePanel({
  autopilotTradeEpisodeId = null,
  ...props
}: ModePanelProps) {
  const [openPositionsRequest, setOpenPositionsRequest] = useState(0);
  const accountKey = `${props.accountWorkspaceProjection?.account_id ?? "unknown"}:${props.accountWorkspaceProjection?.session_generation ?? 0}`;

  return (
    <>
      <LegacyModePanel {...props} openPositionsRequest={openPositionsRequest} />
      {props.mode === "AUTOPILOT" ? (
        <>
          <AutopilotFirstScreen onOpenPositions={() => setOpenPositionsRequest((value) => value + 1)} />
          <AutopilotDiaryControls
            accountKey={accountKey}
            tradeEpisodeId={autopilotTradeEpisodeId}
          />
        </>
      ) : null}
    </>
  );
}

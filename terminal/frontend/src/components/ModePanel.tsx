import { useState, type ComponentProps } from "react";
import {
  ModePanel as LegacyModePanel,
  type WorkspaceMode as LegacyWorkspaceMode,
} from "./ModePanelLegacy";
import { AutopilotDiaryControls } from "./AutopilotDiaryControls";
import { AutopilotFirstScreen } from "./AutopilotFirstScreen";
import { AccountMenu } from "./AccountMenu";
import { RobotManagerPanel } from "./RobotManagerPanel";

export type WorkspaceMode = LegacyWorkspaceMode;

type ModePanelProps = ComponentProps<typeof LegacyModePanel> & {
  autopilotTradeEpisodeId?: string | null;
};

export function ModePanel({
  autopilotTradeEpisodeId = null,
  ...props
}: ModePanelProps) {
  const [openPositionsRequest, setOpenPositionsRequest] = useState(0);
  const [requestedTradeEpisodeId, setRequestedTradeEpisodeId] = useState<string | null>(null);
  const [statisticsRequest, setStatisticsRequest] = useState(0);
  const [robotManagerOpen, setRobotManagerOpen] = useState(false);
  const accountKey = `${props.accountWorkspaceProjection?.account_id ?? "unknown"}:${props.accountWorkspaceProjection?.session_generation ?? 0}`;

  return (
    <>
      <LegacyModePanel {...props} openPositionsRequest={openPositionsRequest} />
      {props.mode === "AUTOPILOT" ? (
        <>
          {robotManagerOpen ? (
            <RobotManagerPanel onClose={() => setRobotManagerOpen(false)} />
          ) : (
            <>
              <AutopilotFirstScreen
                accountKey={accountKey}
                onOpenPositions={() => setOpenPositionsRequest((value) => value + 1)}
                onTradeDetails={setRequestedTradeEpisodeId}
                onStatistics={() => setStatisticsRequest((value) => value + 1)}
                onTerminal={() => props.onModeChange("TERMINAL")}
                onRobotControls={() => setRobotManagerOpen(true)}
                accountControl={<AccountMenu open={props.accountOpen ?? false} onToggle={props.onAccountToggle ?? (() => {})} workspaceProjection={props.accountWorkspaceProjection ?? null} />}
              />
              <AutopilotDiaryControls
            accountKey={accountKey}
            tradeEpisodeId={autopilotTradeEpisodeId}
            requestedTradeEpisodeId={requestedTradeEpisodeId}
            requestedStatisticsCount={statisticsRequest}
            hideActions
                onRequestConsumed={() => setRequestedTradeEpisodeId(null)}
              />
            </>
          )}
        </>
      ) : null}
    </>
  );
}

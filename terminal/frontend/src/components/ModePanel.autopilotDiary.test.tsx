import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EMPTY_LIMIT_DRAFT_STATE } from "../orders/limitDraft";
import { ModePanel } from "./ModePanel";

function renderAutopilot(tradeEpisodeId?: string | null) {
  return render(
    <ModePanel
      mode="AUTOPILOT"
      onModeChange={vi.fn()}
      symbol="BTCUSDT"
      paperState={null}
      activeLimitOrders={[]}
      refreshPaperState={vi.fn()}
      sizingReferencePrice="64000"
      authoritativeTickSize="0.5"
      limitDraftState={EMPTY_LIMIT_DRAFT_STATE}
      dispatchLimitDraft={vi.fn()}
      onLimitDraftConfirm={vi.fn()}
      onPositionSideChange={vi.fn()}
      mutationsAllowed={false}
      autopilotTradeEpisodeId={tradeEpisodeId}
    />,
  );
}

describe("ModePanel D6.5 AUTOPILOT Diary integration", () => {
  it("shows Diary navigation without exposing manual trading controls", () => {
    renderAutopilot();

    expect(screen.getByRole("button", { name: "Статистика" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Подробности сделки" })).toBeDisabled();
    expect(screen.queryByRole("group", { name: "Manual trading controls" })).not.toBeInTheDocument();
  });

  it("enables trade details only when the caller supplies an explicit episode link", () => {
    renderAutopilot("trade-robot-1");

    expect(screen.getByRole("button", { name: "Подробности сделки" })).toBeEnabled();
  });
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { AccountWorkspaceProjection } from "../accountWorkspace/accountWorkspaceStore";
import { EMPTY_LIMIT_DRAFT_STATE } from "../orders/limitDraft";
import { ModePanel } from "./ModePanel";

const fullCloseMocks = vi.hoisted(() => ({
  submit: vi.fn(),
  clear: vi.fn(),
}));

vi.mock("../orders/liveFullCloseSubmission", () => ({
  LiveFullCloseSubmissionController: class {
    submit(...args: unknown[]) {
      return fullCloseMocks.submit(...args);
    }
    clear() {
      fullCloseMocks.clear();
    }
  },
}));

const projection = (fullClose = true): AccountWorkspaceProjection => ({
  ok: true,
  account_id: "bybit-main",
  provider: "BYBIT",
  environment: "MAINNET",
  status: "READY",
  session_generation: 7,
  projection_generation: 12,
  read_only: false,
  capabilities: {
    market: true,
    limit: true,
    stop: true,
    take: true,
    full_close: fullClose,
  },
  wallet_balance_usdt: "1000",
  total_equity_usdt: "1000",
  available_balance_usdt: "900",
  one_wv_usdt: "50",
  positions: [{
    symbol: "BTCUSDT",
    side: "Long",
    size: "0.01",
    average_entry: "64000",
    mark_price: "64500",
  }],
  orders: [],
  paper_state: null,
});

const renderLive = (liveMarketAllowed = true, fullClose = true) => render(
  <ModePanel
    mode="TERMINAL"
    onModeChange={vi.fn()}
    symbol="BTCUSDT"
    paperState={null}
    activeLimitOrders={[]}
    refreshPaperState={async () => {}}
    sizingReferencePrice="64500"
    authoritativeTickSize="0.5"
    limitDraftState={EMPTY_LIMIT_DRAFT_STATE}
    dispatchLimitDraft={vi.fn()}
    onLimitDraftConfirm={vi.fn()}
    onPositionSideChange={vi.fn()}
    accountWorkspaceProjection={projection(fullClose)}
    mutationsAllowed={false}
    liveMarketAllowed={liveMarketAllowed}
    liveLimitAllowed={liveMarketAllowed}
    liveProtectionAllowed={liveMarketAllowed}
  />,
);

it("projects the LIVE position and routes confirmed Full Close through the shared LIVE controller", async () => {
  fullCloseMocks.submit.mockResolvedValue({
    status: "completed",
    reason_code: "completed",
    command_id: "cmd-close",
    reconciliation_required: false,
  });

  renderLive();

  const closeButton = screen.getByRole("button", { name: "Закрыть позицию" });
  expect(closeButton).toBeEnabled();
  expect(document.querySelector(".paper-wv-amount")).toHaveTextContent("645");

  fireEvent.click(closeButton);
  const dialog = screen.getByRole("dialog", { name: "Закрыть позицию?" });
  fireEvent.click(dialog.querySelector(".paper-close-confirm-accept")!);

  await waitFor(() => expect(fullCloseMocks.submit).toHaveBeenCalledOnce());
  expect(fullCloseMocks.submit.mock.calls[0][0]).toEqual({ symbol: "BTCUSDT" });
  expect(await screen.findByText("LIVE position closed")).toBeInTheDocument();
});

it("keeps LIVE Full Close fail-closed when the common LIVE mutation authority envelope is unavailable", () => {
  renderLive(false, true);
  expect(screen.getByRole("button", { name: "Закрыть позицию" })).toBeDisabled();
  expect(fullCloseMocks.submit).not.toHaveBeenCalled();
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PaperOpenPosition, PaperState } from "../contracts/trading";
import { OpenPositionsOverlay } from "./OpenPositionsOverlay";

const position: PaperOpenPosition = {
  symbol: "BTCUSDT",
  position_side: "Long",
  position_quantity: "0.01",
  average_entry: "64000",
  engaged_notional_usdt: "640",
  engaged_wv: "1.0",
  current_price: "64100",
  unrealized_pnl: "1",
  tick_size: "0.10",
};

const paperState = { position_side: "Flat" } as PaperState;

const inventory = (positions: PaperOpenPosition[]) => ({
  ok: true,
  json: vi.fn().mockResolvedValue({
    ok: true,
    account_id: "paper-main",
    positions,
  }),
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("OpenPositionsOverlay PAPER Full Close lifecycle boundary", () => {
  it("routes single Full Close through the shared submission mutation boundary", async () => {
    const runPaperMutation = vi.fn(
      async <T,>(_key: string, operation: () => Promise<T>): Promise<T> => operation(),
    );
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(inventory([position]))
      .mockResolvedValueOnce({
        ok: true,
        json: vi.fn().mockResolvedValue({
          client_action_id: "paper-full-close-1",
          status: "completed",
          reason_code: "closed",
          reconciliation_required: false,
          paper_state: paperState,
        }),
      })
      .mockResolvedValueOnce(inventory([]));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <OpenPositionsOverlay
        activeSymbol="BTCUSDT"
        onClose={vi.fn()}
        onNavigate={vi.fn()}
        runPaperMutation={runPaperMutation}
        applyPaperState={vi.fn(() => true)}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Закрыть позицию BTCUSDT" }));
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));

    await waitFor(() => expect(runPaperMutation).toHaveBeenCalled());
    expect(runPaperMutation.mock.calls[0][0]).toBe("FULL_CLOSE");
    expect(fetchMock.mock.calls.filter(([url]) => url === "/api/full-close")).toHaveLength(1);
  });
});

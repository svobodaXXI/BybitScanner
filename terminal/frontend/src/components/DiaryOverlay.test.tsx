import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  afterEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import { DiaryOverlay } from "./DiaryOverlay";

const response = {
  ok: true,
  active_account_id: "paper",
  session_generation: 1,
  environment: "PAPER" as const,
  trades: [
    {
      trade_episode_id: "closed-1",
      symbol: "BTCUSDT",
      side: "LONG" as const,
      environment: "PAPER" as const,
      controller_origin: null,
      opened_at_ms: 1_700_000_000_000,
      closed_at_ms: 1_700_003_600_000,
      opening_price: "100",
      average_entry: "101",
      exit_price: null,
      open_quantity: "0",
      pnl: null,
      holding_duration_ms: 3_600_000,
      readiness: "CLOSED_INCOMPLETE" as const,
      needs_attention: true,
      missing_reasons: ["MISSING_FUNDING"],
    },
    {
      trade_episode_id: "open-1",
      symbol: "ETHUSDT",
      side: "SHORT" as const,
      environment: "PAPER" as const,
      controller_origin: null,
      opened_at_ms: 1_700_010_000_000,
      closed_at_ms: null,
      opening_price: "200",
      average_entry: "200",
      exit_price: null,
      open_quantity: "2",
      pnl: null,
      holding_duration_ms: 120_000,
      readiness: "OPEN" as const,
      needs_attention: false,
      missing_reasons: ["TRADE_OPEN"],
    },
  ],
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DiaryOverlay", () => {
  it(
    "keeps unavailable values missing and filters attention",
    async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({
          ok: true,
          json: async () => response,
        }),
      );

      render(
        <DiaryOverlay
          accountKey="paper:1"
          onClose={() => {}}
        />,
      );

      expect(
        await screen.findByText("BTCUSDT"),
      ).toBeTruthy();

      expect(screen.getByText("ETHUSDT")).toBeTruthy();
      expect(screen.getAllByText("PnL ?").length).toBe(2);

      fireEvent.click(
        screen.getByRole("button", {
          name: "??????? ????????",
        }),
      );

      await waitFor(() => {
        expect(screen.getByText("BTCUSDT")).toBeTruthy();
        expect(
          screen.queryByText("ETHUSDT"),
        ).toBeNull();
      });
    },
  );

  it(
    "refetches after active account authority changes",
    async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => response,
      });
      vi.stubGlobal("fetch", fetchMock);

      const rendered = render(
        <DiaryOverlay
          accountKey="paper:1"
          onClose={() => {}}
        />,
      );

      await screen.findByText("BTCUSDT");
      expect(fetchMock).toHaveBeenCalledTimes(1);

      rendered.rerender(
        <DiaryOverlay
          accountKey="bybit-1:2"
          onClose={() => {}}
        />,
      );

      await waitFor(() =>
        expect(fetchMock).toHaveBeenCalledTimes(2),
      );
    },
  );
});

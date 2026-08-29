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

const paperState = {
  position_side: "Flat",
} as PaperState;

function inventory(positions: PaperOpenPosition[]) {
  return {
    ok: true,
    json: vi.fn().mockResolvedValue({
      ok: true,
      account_id: "paper-main",
      positions,
    }),
  };
}

function renderOverlay(onNavigate = vi.fn()) {
  render(
    <OpenPositionsOverlay
      onClose={vi.fn()}
      onNavigate={onNavigate}
      runPaperMutation={(_key, operation) => operation()}
      applyPaperState={vi.fn(() => true)}
    />,
  );
}

async function confirmFullClose() {
  fireEvent.click(await screen.findByRole("button", { name: "Закрыть позицию BTCUSDT" }));
  fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("account-wide PAPER Full Close reconciliation", () => {
  it("requires navigation confirmation and keeps close action isolated from card navigation", async () => {
    const onNavigate = vi.fn();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(inventory([position])));
    renderOverlay(onNavigate);

    const close = await screen.findByRole("button", { name: "Закрыть позицию BTCUSDT" });
    fireEvent.click(close);
    expect(screen.getByRole("dialog", { name: "Закрыть всю позицию BTCUSDT по рынку?" })).toBeInTheDocument();
    expect(onNavigate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Отмена" }));

    fireEvent.click(screen.getByRole("button", { name: "Открыть позицию BTCUSDT в терминале" }));
    expect(screen.getByRole("dialog", { name: "Перейти в терминал BTCUSDT?" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Отмена" }));
    expect(onNavigate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Открыть позицию BTCUSDT в терминале" }));
    fireEvent.click(screen.getByRole("button", { name: "Перейти" }));
    expect(onNavigate).toHaveBeenCalledOnce();
    expect(onNavigate).toHaveBeenCalledWith("BTCUSDT");
  });
  it("formats symbol tick precision and renders backend-owned PnL", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(inventory([position])));
    renderOverlay();

    expect(await screen.findByText("Ср. цена: 64000.00")).toBeInTheDocument();
    expect(screen.getByText("Объем: 640.00 USDT")).toBeInTheDocument();
    expect(screen.getByText("PnL +1.00 USDT (+0.16%)")).toBeInTheDocument();
  });

  it("fails closed when authoritative PnL is unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(inventory([
      { ...position, symbol: "ETHUSDT", current_price: null, unrealized_pnl: null, tick_size: "0.01" },
    ])));
    renderOverlay();

    expect(await screen.findByText("PnL —")).toBeInTheDocument();
  });

  it("opens and cancels Close All confirmation without a mutation", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(inventory([position]));
    vi.stubGlobal("fetch", fetchMock);
    renderOverlay();

    fireEvent.click(await screen.findByRole("button", { name: "Закрыть все" }));
    expect(screen.getByRole("dialog", { name: "Закрыть все открытые позиции по рынку?" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Отмена" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("keeps only an unresolved Close All row visible and locked", async () => {
    const eth = { ...position, symbol: "ETHUSDT", tick_size: "0.01" };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(inventory([position, eth]))
      .mockResolvedValueOnce({
        ok: true,
        json: vi.fn().mockResolvedValue({
          ok: true,
          client_action_id: "bulk-1",
          results: [{ client_action_id: "child", status: "unknown", reconciliation_required: true }],
          positions: [eth],
        }),
      });
    vi.stubGlobal("fetch", fetchMock);
    renderOverlay();

    fireEvent.click(await screen.findByRole("button", { name: "Закрыть все" }));
    fireEvent.click(screen.getByRole("button", { name: "Закрыть все позиции" }));

    expect(await screen.findByText("ETHUSDT")).toBeInTheDocument();
    expect(screen.queryByText("BTCUSDT")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Закрыть позицию ETHUSDT" })).toBeDisabled();
    expect(fetchMock.mock.calls.filter(([url]) => url === "/api/close-all")).toHaveLength(1);
  });

  it("keeps a completed close locked while authoritative inventory still contains the position", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(inventory([position]))
      .mockResolvedValueOnce({
        ok: true,
        json: vi.fn().mockResolvedValue({ status: "completed", paper_state: paperState }),
      })
      .mockResolvedValueOnce(inventory([position]));
    vi.stubGlobal("fetch", fetchMock);
    renderOverlay();

    await confirmFullClose();

    expect(await screen.findByText("Позиция ещё открыта")).toBeInTheDocument();
    const closeButton = screen.getByRole("button", { name: "Закрыть позицию BTCUSDT" });
    expect(closeButton).toBeDisabled();
    fireEvent.click(closeButton);
    expect(fetchMock.mock.calls.filter(([url]) => url === "/api/full-close")).toHaveLength(1);
  });

  it("settles an ambiguous close when authoritative inventory confirms FLAT", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(inventory([position]))
      .mockResolvedValueOnce({
        ok: true,
        json: vi.fn().mockResolvedValue({
          status: "unknown",
          reconciliation_required: true,
        }),
      })
      .mockResolvedValueOnce(inventory([]));
    vi.stubGlobal("fetch", fetchMock);
    renderOverlay();

    await confirmFullClose();

    expect(await screen.findByText("Нет открытых позиций")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Закрыть список позиций" })).toBeEnabled();
    });
    expect(fetchMock.mock.calls.filter(([url]) => url === "/api/full-close")).toHaveLength(1);
    expect(screen.queryByText(/повтор заблокирован/)).not.toBeInTheDocument();
  });
});

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

function renderOverlay(onNavigate = vi.fn(), activeSymbol = "BTCUSDT", robotOnly = false) {
  render(
    <OpenPositionsOverlay
      activeSymbol={activeSymbol}
      robotOnly={robotOnly}
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

describe("Autopilot Robot positions use the existing inventory view safely", () => {
  it("shows only proven Robot-linked PAPER positions and never exposes close actions", async () => {
    const robot = { ...position, robot_trade_id: "robot-trade-btc" };
    const manual = { ...position, symbol: "ETHUSDT", robot_trade_id: null };
    const fetchMock = vi.fn().mockResolvedValueOnce(inventory([manual, robot]));
    vi.stubGlobal("fetch", fetchMock);
    const onNavigate = vi.fn();
    renderOverlay(onNavigate, "BTCUSDT", true);

    expect(await screen.findByRole("region", { name: "Открытые позиции робота" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Показать позицию BTCUSDT на графике" })).toBeInTheDocument();
    expect(screen.queryByText("ETHUSDT")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Закрыть все" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Закрыть позицию/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Показать позицию BTCUSDT на графике" }));
    expect(screen.getByRole("dialog", { name: "Показать позицию BTCUSDT на графике?" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Показать" }));
    expect(onNavigate).toHaveBeenCalledWith("BTCUSDT");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls.every(([url, options]) => url === "/api/open-positions" && !options)).toBe(true);
  });

  it("keeps multiple Robot positions available and synchronizes their current inventory before chart navigation", async () => {
    const btc = { ...position, robot_trade_id: "robot-btc" };
    const eth = { ...position, symbol: "ETHUSDT", robot_trade_id: "robot-eth" };
    const onInventoryLoaded = vi.fn();
    const onNavigate = vi.fn();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(inventory([btc, eth])));
    render(<OpenPositionsOverlay
      activeSymbol="BTCUSDT"
      robotOnly
      onClose={vi.fn()}
      onNavigate={onNavigate}
      onInventoryLoaded={onInventoryLoaded}
      runPaperMutation={(_key, operation) => operation()}
      applyPaperState={vi.fn(() => true)}
    />);
    const ethRow = await screen.findByRole("button", { name: "Показать позицию ETHUSDT на графике" });
    expect(screen.getByRole("button", { name: "Показать позицию BTCUSDT на графике" })).toBeInTheDocument();
    await waitFor(() => expect(onInventoryLoaded).toHaveBeenCalledWith([btc, eth]));
    fireEvent.click(ethRow);
    fireEvent.click(screen.getByRole("button", { name: "Показать" }));
    expect(onNavigate).toHaveBeenCalledWith("ETHUSDT");
  });

  it("shows live Robot inventory from the first screen without additional polling", async () => {
    const first = [{ ...position, robot_trade_id: "robot-btc" }];
    const second = [{ ...position, symbol: "ETHUSDT", robot_trade_id: "robot-eth" }];
    const fetchMock = vi.fn().mockResolvedValue(inventory(first));
    vi.stubGlobal("fetch", fetchMock);
    const baseProps = {
      activeSymbol: "BTCUSDT", robotOnly: true, onClose: vi.fn(), onNavigate: vi.fn(),
      runPaperMutation: (_key: string, operation: () => Promise<unknown>) => operation(),
      applyPaperState: vi.fn(() => true),
    };
    const view = render(<OpenPositionsOverlay {...baseProps} liveRobotPositions={first} />);
    expect(await screen.findByRole("button", { name: "Показать позицию BTCUSDT на графике" }))
      .toBeInTheDocument();
    view.rerender(<OpenPositionsOverlay {...baseProps} liveRobotPositions={second} />);
    expect(screen.queryByRole("button", { name: "Показать позицию BTCUSDT на графике" }))
      .not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Показать позицию ETHUSDT на графике" }))
      .toBeInTheDocument();
    view.rerender(<OpenPositionsOverlay {...baseProps} liveRobotPositions={null} />);
    expect(screen.getByText("Принадлежность позиций роботу не подтверждена")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Показать позицию/ })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not misclassify an old backend inventory as a Robot inventory", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(inventory([position])));
    renderOverlay(vi.fn(), "BTCUSDT", true);
    expect(await screen.findByText("Принадлежность позиций роботу не подтверждена")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Показать позицию/ })).not.toBeInTheDocument();
  });
});

describe("account-wide PAPER Full Close reconciliation", () => {
  it("renders the active symbol first and highlighted without reordering other positions", async () => {
    const eth = { ...position, symbol: "ETHUSDT", tick_size: "0.01" };
    const sol = { ...position, symbol: "SOLUSDT", tick_size: "0.001" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(inventory([position, eth, sol])));
    renderOverlay(vi.fn(), "ETHUSDT");

    const rows = await screen.findAllByRole("button", { name: /Открыть позицию .* в терминале/ });
    expect(rows.map((row) => row.getAttribute("aria-label"))).toEqual([
      "Открыть позицию ETHUSDT в терминале",
      "Открыть позицию BTCUSDT в терминале",
      "Открыть позицию SOLUSDT в терминале",
    ]);
    expect(rows[0]).toHaveClass("active-symbol");
    expect(rows[1]).not.toHaveClass("active-symbol");
    expect(rows[2]).not.toHaveClass("active-symbol");
  });

  it("places the red Close All control beside the heading", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(inventory([position])));
    renderOverlay();

    const closeAll = await screen.findByRole("button", { name: "Закрыть все" });
    expect(closeAll.parentElement).toHaveClass("paper-open-positions-title");
    expect(closeAll).toHaveClass("paper-open-positions-close-all");
  });

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

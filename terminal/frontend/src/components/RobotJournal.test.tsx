import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RobotJournal } from "./RobotJournal";

afterEach(() => vi.unstubAllGlobals());
describe("PAPER Robot journal", () => {
  const valid = {
    ok: true, source: "robot_trades", account_id: "paper", symbol: "BTCUSDT",
    events: [
      { trade_id: "robot-a", time_ms: 1790000000000, kind: "SIGNAL_RECORDED", pattern: "Falling Wedge" },
      { trade_id: "robot-a", time_ms: 1790000005000, kind: "POSITION_OPENED",
        direction: "LONG", quantity: "2", price: "101" },
      { trade_id: "robot-a", time_ms: 1790000015000, kind: "POSITION_CLOSED", reason: "TAKE", price: "105" },
    ],
  };

  it("displays only the three confirmed trade-ledger lifecycle facts and refreshes by GET", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => valid });
    vi.stubGlobal("fetch", fetchMock);
    render(<RobotJournal symbol="BTCUSDT" />);
    expect(await screen.findByText(/Позиция открыта: LONG/)).toHaveTextContent("101");
    expect(screen.getByText(/Сигнал зарегистрирован: Falling Wedge/)).toBeInTheDocument();
    expect(screen.getByText(/Позиция закрыта · цена 105/)).toHaveTextContent("TAKE");
    expect(screen.queryByText(/ожидаю ретест/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Обновить" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls.every(([url, options]) =>
      url === "/api/robot/journal?symbol=BTCUSDT" && !options?.method)).toBe(true);
  });

  it("rejects an untrusted symbol or absent source rather than inventing events", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({
      ...valid, symbol: "ETHUSDT",
    }) }));
    render(<RobotJournal symbol="BTCUSDT" />);
    expect(await screen.findByText("События недоступны")).toBeInTheDocument();
    expect(screen.queryByText(/Позиция открыта/)).not.toBeInTheDocument();
  });

  it("reports an empty confirmed ledger honestly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({
      ...valid, events: [],
    }) }));
    render(<RobotJournal symbol="BTCUSDT" />);
    expect(await screen.findByText("Нет подтверждённых событий за 7 дней")).toBeInTheDocument();
  });
});

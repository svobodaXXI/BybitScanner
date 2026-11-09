import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RobotExecutionJournal } from "./RobotExecutionJournal";

describe("read-only execution facts under the Robot chart", () => {
  it("shows only real fill/limit markers in Moscow time, with no invented decisions", () => {
    const initial = Date.UTC(2026, 10, 9, 12);
    const { container } = render(<RobotExecutionJournal selectedTradeId="robot-btc" markers={[
      { time_ms: initial + 60_000, price: "100.5", side: "Sell", filled: false },
      { time_ms: initial, price: "100", side: "Buy", filled: true },
    ]} />);
    expect(screen.getByRole("region", { name: "Журнал подтверждённых событий робота" }))
      .toBeInTheDocument();
    expect(screen.getByText(/Buy исполнено · 100 USDT/)).toBeInTheDocument();
    expect(screen.getByText(/Лимитная заявка Sell ожидает исполнения · 100.5 USDT/))
      .toBeInTheDocument();
    expect(container.querySelectorAll("time")[0]).toHaveTextContent("15:00:00");
    expect(screen.queryByText(/ретест|вход выполнен|сделка открыта/i)).toBeNull();
    expect(container.querySelectorAll("button")).toHaveLength(0);
  });

  it("does not represent missing evidence as flat or as an executed event", () => {
    const { rerender } = render(<RobotExecutionJournal selectedTradeId="robot-btc" markers={null} />);
    expect(screen.getByText("Данные исполнений недоступны.")).toBeInTheDocument();
    rerender(<RobotExecutionJournal selectedTradeId="robot-btc" markers={[]} />);
    expect(screen.getByText("Подтверждённых исполнений пока нет.")).toBeInTheDocument();
    rerender(<RobotExecutionJournal selectedTradeId={null} markers={null} />);
    expect(screen.getByText("Выберите открытую позицию робота.")).toBeInTheDocument();
  });
  it("rejects malformed execution timestamps and prices without creating journal events", () => {
    const at = Date.UTC(2026, 10, 9, 12);
    const { container } = render(<RobotExecutionJournal selectedTradeId="robot-btc" markers={[
      { time_ms: Number.NaN, price: "100", side: "Buy", filled: true },
      { time_ms: at, price: "Infinity", side: "Sell", filled: true },
      { time_ms: at + 1000, price: "-5", side: "Buy", filled: false },
      { time_ms: at + 2000, price: "101", side: "Sell", filled: true },
    ]} />);
    expect(container.querySelectorAll("time")).toHaveLength(1);
    expect(screen.getByText("Sell исполнено · 101 USDT")).toBeInTheDocument();
    expect(screen.queryByText(/Infinity|-5 USDT/)).toBeNull();
  });


});

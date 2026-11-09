import type { RobotTradeMarker } from "../chart/robotTradeMarkers";
import "./RobotExecutionJournal.css";

export type RobotExecutionJournalProps = {
  selectedTradeId: string | null;
  markers: readonly RobotTradeMarker[] | null;
};

const moscowTime = (millis: number) => new Date(millis).toLocaleString("ru-RU", {
  timeZone: "Europe/Moscow", day: "2-digit", month: "2-digit",
  hour: "2-digit", minute: "2-digit", second: "2-digit",
});

export function RobotExecutionJournal({ selectedTradeId, markers }: RobotExecutionJournalProps) {
  const verified = markers?.filter((marker) =>
    Number.isSafeInteger(marker.time_ms) && marker.time_ms > 0 &&
    ["Buy", "Sell"].includes(marker.side) &&
    typeof marker.filled === "boolean" &&
    typeof marker.price === "string" &&
    Number.isFinite(Number(marker.price)) && Number(marker.price) > 0,
  ).slice().sort((a, b) => a.time_ms - b.time_ms) ?? [];

  return (
    <section className="robot-execution-journal" aria-label="Журнал подтверждённых событий робота">
      <strong>События сделки <small>МСК · подтверждённые исполнения и заявки</small></strong>
      {!selectedTradeId ? <p>Выберите открытую позицию робота.</p>
        : markers === null ? <p>Данные исполнений недоступны.</p>
          : verified.length === 0 ? <p>Подтверждённых исполнений пока нет.</p>
            : <ol>
                {verified.slice(-16).map((marker, index) => (
                  <li key={`${marker.time_ms}:${marker.side}:${marker.price}:${marker.filled}:${index}`}>
                    <time dateTime={new Date(marker.time_ms).toISOString()}>{moscowTime(marker.time_ms)}</time>
                    <span>
                      {marker.filled ? `${marker.side} исполнено`
                        : `Лимитная заявка ${marker.side} ожидает исполнения`}
                      {` · ${marker.price} USDT`}
                    </span>
                  </li>
                ))}
              </ol>}
    </section>
  );
}

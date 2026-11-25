import type { RobotTradeMarker } from "../chart/robotTradeMarkers";
import type { GeometryRevisionObservation } from "../replay/paperEpisodeFacts";
import "./RobotExecutionJournal.css";

export type RobotExecutionJournalProps = {
  selectedTradeId: string | null;
  markers: readonly RobotTradeMarker[] | null;
  revisions?: readonly GeometryRevisionObservation[];
};

const moscowTime = (millis: number) => new Date(millis).toLocaleString("ru-RU", {
  timeZone: "Europe/Moscow", day: "2-digit", month: "2-digit",
  hour: "2-digit", minute: "2-digit", second: "2-digit",
});

export function RobotExecutionJournal({ selectedTradeId, markers, revisions = [] }: RobotExecutionJournalProps) {
  const verified = markers?.filter((marker) =>
    Number.isSafeInteger(marker.time_ms) && marker.time_ms > 0 &&
    ["Buy", "Sell"].includes(marker.side) &&
    typeof marker.filled === "boolean" &&
    typeof marker.price === "string" &&
    Number.isFinite(Number(marker.price)) && Number(marker.price) > 0,
  ).slice().sort((a, b) => a.time_ms - b.time_ms) ?? [];

  const events = [
    ...verified.map((marker,index) => ({
      key: `fill:${marker.time_ms}:${index}`, at: marker.time_ms,
      text: (marker.filled ? `${marker.side} исполнено`
        : `Лимитная заявка ${marker.side} ожидает исполнения`) + ` · ${marker.price} USDT`,
    })),
    ...revisions.map(r => ({ key: "geometry:"+r.revision+":"+r.source_trade_id,
      at:r.event_time_ms, text:"Паттерн перестроен · ревизия "+r.revision+
        " · "+r.previous_extreme+" → "+r.trigger_price })),
  ].sort((a,b) => a.at-b.at || a.key.localeCompare(b.key));
  return (
    <section className="robot-execution-journal" aria-label="Журнал подтверждённых событий робота">
      <strong>События на графике <small>МСК · исполнения, заявки и наблюдения геометрии Robot</small></strong>
      {!selectedTradeId ? <p>Выберите открытую позицию робота.</p>
        : markers === null && !events.length ? <p>Данные исполнений недоступны.</p>
          : events.length === 0 ? <p>Подтверждённых событий пока нет.</p>
            : <ol>
                {events.slice(-16).map(event => (
                  <li key={event.key}>
                    <time dateTime={new Date(event.at).toISOString()}>{moscowTime(event.at)}.{String(event.at%1000).padStart(3,"0")}</time>
                    <span>{event.text}</span>
                  </li>
                ))}
              </ol>}
    </section>
  );
}

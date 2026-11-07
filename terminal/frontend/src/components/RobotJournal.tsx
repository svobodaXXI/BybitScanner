import { useEffect, useState } from "react";
import { marketApiRoutes } from "../marketData/apiRoutes";

type Event = {
  trade_id: string; time_ms: number;
  kind: "SIGNAL_RECORDED" | "POSITION_OPENED" | "POSITION_CLOSED";
  pattern?: string; price?: string; quantity?: string;
  direction?: string; reason?: string | null;
};
function valid(value: unknown): value is Event {
  if (!value || typeof value !== "object") return false;
  const e = value as Partial<Event>;
  return typeof e.trade_id === "string" && e.trade_id.length > 0 &&
    Number.isSafeInteger(e.time_ms) && (e.time_ms ?? 0) > 0 &&
    ["SIGNAL_RECORDED", "POSITION_OPENED", "POSITION_CLOSED"].includes(e.kind ?? "");
}
function describe(e: Event): string {
  if (e.kind === "SIGNAL_RECORDED") return `Сигнал зарегистрирован${e.pattern ? `: ${e.pattern}` : ""}`;
  if (e.kind === "POSITION_OPENED")
    return `Позиция открыта: ${e.direction ?? "—"} · ${e.quantity ?? "—"} · средняя цена ${e.price ?? "—"}`;
  return `Позиция закрыта · цена ${e.price ?? "—"}${e.reason ? ` · причина ${e.reason}` : ""}`;
}

/** Only durable PAPER Robot facts. No speculative WAIT/RETEST or fictitious fills. */
export function RobotJournal({ symbol }: { symbol: string }) {
  const [events, setEvents] = useState<Event[] | null>(null);
  const [error, setError] = useState(false);
  const [refreshCount, setRefreshCount] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setEvents(null);
    setError(false);
    void (async () => {
      try {
        const response = await fetch(marketApiRoutes.robotJournal(symbol), { signal: controller.signal });
        if (!response.ok) throw new Error("Unavailable");
        const body = await response.json() as {
          ok?: boolean; account_id?: string; source?: string; symbol?: string; events?: unknown;
        };
        if (body.ok !== true || body.account_id !== "paper" ||
            body.source !== "robot_trades" || body.symbol !== symbol ||
            !Array.isArray(body.events) || !body.events.every(valid))
          throw new Error("Untrusted robot journal");
        if (!controller.signal.aborted) setEvents(body.events);
      } catch {
        if (!controller.signal.aborted) setError(true);
      }
    })();
    return () => controller.abort();
  }, [symbol, refreshCount]);
  return (
    <section className="autopilot-robot-journal" aria-label={`Журнал робота ${symbol}`}>
      <header>
        <strong>Журнал робота · {symbol}</strong>
        <button type="button" onClick={() => setRefreshCount((n) => n + 1)}>Обновить</button>
      </header>
      {error ? <p role="status">События недоступны</p> :
        events === null ? <p role="status">Загрузка журнала…</p> :
        events.length === 0 ? <p>Нет подтверждённых событий за 7 дней</p> : (
          <ol aria-label="Подтверждённые события робота">
            {events.map((e, i) => <li key={`${e.trade_id}:${e.kind}:${e.time_ms}:${i}`}>
              <time dateTime={new Date(e.time_ms).toISOString()}>
                {new Date(e.time_ms).toLocaleString("ru-RU", {
                  timeZone: "Europe/Moscow", day: "2-digit", month: "2-digit",
                  hour: "2-digit", minute: "2-digit", second: "2-digit",
                })}
              </time>
              <span>{describe(e)}</span>
            </li>)}
          </ol>
        )}
    </section>
  );
}

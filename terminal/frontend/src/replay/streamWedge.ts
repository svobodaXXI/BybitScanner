/** Bounded same-origin incremental transport for ONE original Wedge SIMULATION.
 * Every displayed closed M5 and virtual order is validated with replayModel.
 * No early PnL, no synthetic fallback, no producer-side browser calculations.
 */
import { parseReplayDocument, type ReplayDocument, type ReplayEvent } from "./replayModel";
import { parseWedgeResult, validateInclusiveWindow, type LocalWedgeResult, makeWedgeRunRequest } from "./runSetup";

type WedgeRequest = ReturnType<typeof makeWedgeRunRequest>;
type RecordValue = Record<string, unknown>;
const SOURCE = "BYBIT_OFFICIAL_PUBLIC_TRADES_DERIVED_5M";
function object(value: unknown): RecordValue {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("Повреждён поток SIMULATION");
  return value as RecordValue;
}
export async function streamWedge(
  request: WedgeRequest, signal: AbortSignal,
  onFirst: (document: ReplayDocument) => void,
  onAppend: (runId: string, events: ReplayEvent[]) => void,
): Promise<LocalWedgeResult> {
  const window = validateInclusiveWindow(request.start_utc, request.end_utc_inclusive);
  const response = await fetch("/local-replay/simulation/wedge-stream", {
    method: "POST", cache: "no-store", signal,
    headers: { "Content-Type": "application/json", "X-Local-Simulation": "wedge" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    let message = "Локальный прогон заблокирован";
    try {
      const result = object(await response.json() as unknown);
      if (typeof result.error === "string") message = result.error;
    } catch { /* Preserve the HTTP failure. */ }
    throw new Error(message);
  }
  if (!response.headers.get("Content-Type")?.startsWith("application/x-ndjson") ||
      !response.body)
    throw new Error("Локальный сервер не поддерживает потоковый прогон");

  const decoder = new TextDecoder();
  const reader = response.body.getReader();
  let pending = "";
  let identity: ReplayDocument | null = null;
  let count = 0;
  let lastTime = -1;
  let lastCandleEnd = -1;
  let firstCandle = false;
  let fillCount = 0;
  let finalReport: LocalWedgeResult | null = null;
  try {
    const handle = (value: unknown) => {
      const frame = object(value);
      if (frame.type === "error") {
        throw new Error(typeof frame.error === "string" ? frame.error : "Локальная SIMULATION прервана");
      }
      if (frame.type === "start") {
        if (identity || count || frame.symbol !== request.symbol ||
            frame.start_utc !== request.start_utc ||
            frame.end_utc_inclusive !== request.end_utc_inclusive ||
            typeof frame.simulation_run_id !== "string" ||
            !/^[a-zA-Z0-9_-]{1,100}$/.test(frame.simulation_run_id))
          throw new Error("SIMULATION изменила выбранные координаты");
        identity = {
          source: "SIMULATION", simulation_run_id: frame.simulation_run_id,
          symbol: request.symbol, timeframe: "5m", demo: false, mode: "STRATEGY",
          market_data_source: SOURCE, events: [],
        };
        return;
      }
      if (frame.type === "events") {
        if (!identity || finalReport || !Array.isArray(frame.events) ||
            frame.events.length < 1 || frame.events.length > 1000 ||
            count + frame.events.length > 100_000)
          throw new Error("Неверный пакет потоковых свечей");
        const input = frame.events as unknown[];
        const verified = input.map((item, i) => {
          const event = object(item);
          if (event.sequence !== count + i + 1)
            throw new Error("Неверная последовательность SIMULATION");
          return { ...event, sequence: i + 1 };
        });
        // Reuse the authoritative read-only validation, with local sequence
        // numbering for each bounded packet; restore global numbers afterward.
        const parsed = parseReplayDocument({ ...identity, events: verified });
        const chunk = parsed.events.map((event, i) => ({
          ...event, sequence: count + i + 1,
        }));
        for (const event of chunk) {
          if (event.time_ms < lastTime)
            throw new Error("Потоковые события идут назад во времени");
          if (event.kind === "CANDLE_CLOSED" && event.candle) {
            if (event.candle.start_ms < lastCandleEnd ||
                event.candle.start_ms < window.startMs ||
                event.candle.end_ms > window.endExclusiveMs)
              throw new Error("Чужая или незавершённая свеча в потоке");
            firstCandle = true;
            lastCandleEnd = event.candle.end_ms;
          } else if (event.kind === "ENTRY_FILLED" || event.kind === "EXIT_FILLED") {
            fillCount++;
          }
          lastTime = event.time_ms;
        }
        count += chunk.length;
        if (count === chunk.length) {
          if (!firstCandle) throw new Error("Нет первой закрытой M5");
          onFirst({ ...identity, events: chunk });
        } else {
          onAppend(identity.simulation_run_id, chunk);
        }
        return;
      }
      if (frame.type === "complete") {
        if (!identity || !firstCandle || finalReport ||
            frame.event_count !== count || !frame.report)
          throw new Error("Нет полного подтверждённого журнала SIMULATION");
        const raw = object(frame.report);
        const report = parseWedgeResult(raw);
        if (raw.simulation_run_id !== identity.simulation_run_id ||
            frame.source_id !== raw.source_id ||
            report.symbol !== request.symbol ||
            report.requested_minutes !== window.minutes ||
            report.virtual_fills !== fillCount)
          throw new Error("PnL не совпадает с подтверждёнными событиями");
        finalReport = report;
        return;
      }
      throw new Error("Неизвестный тип потокового события");
    };
    while (true) {
      const { value, done } = await reader.read();
      if (signal.aborted) throw new Error("Прогон отменён");
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      if (pending.length > 512_000) throw new Error("Превышен размер потокового пакета");
      let cut = pending.indexOf("\n");
      while (cut >= 0) {
        const line = pending.slice(0, cut);
        pending = pending.slice(cut + 1);
        if (line.trim()) handle(JSON.parse(line) as unknown);
        cut = pending.indexOf("\n");
      }
    }
    if (pending.trim() || !finalReport)
      throw new Error("Поток SIMULATION оборвался до завершения");
    return finalReport;
  } finally {
    if (!finalReport) await reader.cancel().catch(() => undefined);
  }
}

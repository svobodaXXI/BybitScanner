/** Streaming read-only public M5, using the SAME original native Scanner.
 * A snapshot is a causally completed prefix; incomplete/failed streams never
 * become a verified finished market/strategy history. No Robot or PAPER path.
 */
import { parseReplayDocument, type ReplayDocument, type ReplayEvent } from "./replayModel";

type Fields = Record<string, unknown>;
function object(value: unknown): Fields {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("Повреждён поток публичных M5");
  return value as Fields;
}
export async function streamPublicM5(
  query: URLSearchParams, signal: AbortSignal,
  onReady: (document: ReplayDocument) => void,
): Promise<void> {
  const expectedSymbol = query.get("symbol");
  const response = await fetch("/local-replay/history-stream?" + query.toString(), {
    method: "GET", cache: "no-store", signal,
  });
  if (!response.ok) throw new Error("История M5 недоступна: HTTP " + response.status);
  if (!response.headers.get("Content-Type")?.startsWith("application/x-ndjson") ||
      !response.body) throw new Error("Локальный сервер не поддерживает потоковый M5");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  let started = false;
  let completed = false;
  let ready = 0;
  let identity: string | null = null;
  let prior: ReplayEvent[] = [];
  const handle = (raw: unknown) => {
    const frame = object(raw);
    if (frame.type === "start") {
      if (started || frame.symbol !== expectedSymbol ||
          frame.start !== query.get("start") || frame.end !== query.get("end"))
        throw new Error("Поток M5 изменил выбранные координаты");
      started = true;
      return;
    }
    if (frame.type === "error")
      throw new Error(typeof frame.error === "string"
        ? frame.error : "Исследование M5 прервано до завершения");
    if (frame.type === "snapshot") {
      if (!started || completed) throw new Error("Преждевременная история Scanner");
      const next = parseReplayDocument(frame.document);
      if (next.mode !== "MARKET_ONLY" || next.demo ||
          next.market_data_source !== "BYBIT_PUBLIC_KLINE" ||
          next.symbol !== expectedSymbol ||
          !next.scanner_research ||
          frame.ready_count !== next.events.length ||
          next.events.length <= ready ||
          (identity !== null && next.simulation_run_id !== identity) ||
          prior.some((event, i) => JSON.stringify(event) !== JSON.stringify(next.events[i])))
        throw new Error("Поток Scanner M5 нарушил подтверждённый фронтир");
      ready = next.events.length;
      identity = next.simulation_run_id;
      prior = next.events;
      onReady(next);
      return;
    }
    if (frame.type === "complete") {
      if (!started || completed || ready < 1 ||
          frame.ready_count !== ready || frame.simulation_run_id !== identity)
        throw new Error("Неполная история M5 объявлена завершённой");
      completed = true;
      return;
    }
    throw new Error("Неизвестный пакет публичных M5");
  };
  let reachedEof = false;
  try {
    // The validated 'complete' frame is the protocol's terminal marker.
    // It may arrive before HTTP EOF; do not keep the Apply button waiting
    // for a socket the transport has not yet closed.
    while (!completed) {
      const { done, value } = await reader.read();
      if (signal.aborted) throw new Error("Загрузка M5 отменена");
      if (done) { reachedEof = true; break; }
      pending += decoder.decode(value, { stream: true });
      if (pending.length > 2_000_000) throw new Error("Превышен размер пакета M5");
      let cut = pending.indexOf("\n");
      while (cut >= 0) {
        const line = pending.slice(0, cut);
        pending = pending.slice(cut + 1);
        if (line.trim()) handle(JSON.parse(line) as unknown);
        cut = pending.indexOf("\n");
      }
    }
    if (pending.trim() || !completed)
      throw new Error("Публичный поток M5 оборвался до подтверждения результата");
  } finally {
    // Explicitly release the open reader when the protocol completes before EOF.
    if (!reachedEof) await reader.cancel().catch(() => undefined);
  }
}

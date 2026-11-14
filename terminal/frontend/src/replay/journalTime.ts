/** Wall-clock presentation only. Keep original event time_ms untouched.
 * D2 and PAPER timestamps are epoch milliseconds; public trade/L2 clocks
 * must carry their separate provenance when later correlated by the viewer.
 */
export type JournalZone = "MSK" | "UTC";

export function journalTimeParts(
  timestampMs: number, zone: JournalZone,
): { date: string; seconds: string; milliseconds: string } {
  if (!Number.isSafeInteger(timestampMs) || timestampMs < 0 ||
      !Number.isFinite(new Date(timestampMs).getTime()))
    throw new Error("Недостоверная временная метка события");
  const timeZone = zone === "MSK" ? "Europe/Moscow" : "UTC";
  const date = new Date(timestampMs);
  return {
    date: new Intl.DateTimeFormat("ru-RU", {
      timeZone, day: "2-digit", month: "2-digit", year: "numeric",
    }).format(date),
    seconds: new Intl.DateTimeFormat("ru-RU", {
      timeZone, hour: "2-digit", minute: "2-digit", second: "2-digit",
      hourCycle: "h23",
    }).format(date),
    milliseconds: String(timestampMs % 1000).padStart(3, "0"),
  };
}

import { TickMarkType, type Time } from "lightweight-charts";

// Display-only conversion: never shift canonical UTC candle timestamps or geometry anchors.
const TIME_ZONE = "Europe/Moscow";
const formatter = (options: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat("ru-RU", { timeZone: TIME_ZONE, ...options });

const year = formatter({ year: "numeric" });
const month = formatter({ month: "short" });
const day = formatter({ day: "2-digit" });
const clock = formatter({ hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const clockWithSeconds = formatter({
  hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
});
const fullTime = formatter({
  day: "2-digit", month: "2-digit", year: "numeric",
  hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});

function utcInstant(time: Time): Date | null {
  // ChartPanel supplies UTCTimestamps (Unix seconds), not BusinessDay data.
  if (typeof time !== "number" || !Number.isFinite(time)) return null;
  const date = new Date(time * 1000);
  return Number.isFinite(date.getTime()) ? date : null;
}

export function editorMoscowTickMark(time: Time, kind: TickMarkType): string | null {
  const date = utcInstant(time);
  if (!date) return null;
  switch (kind) {
    case TickMarkType.Year: return year.format(date);
    case TickMarkType.Month: return month.format(date);
    case TickMarkType.DayOfMonth: return day.format(date);
    case TickMarkType.Time: return clock.format(date);
    case TickMarkType.TimeWithSeconds: return clockWithSeconds.format(date);
    default: return null;
  }
}

export function editorMoscowCrosshairTime(time: Time): string {
  const date = utcInstant(time);
  return date ? `${fullTime.format(date)} МСК` : "";
}

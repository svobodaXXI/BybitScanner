import { describe, expect, it } from "vitest";
import { parseSignalWorkspaceLink } from "./signalDeepLink";

describe("GFL editor and terminal deep link", () => {
  it("parses a symbol, timeframe, editor mode, and opaque signal ID", () => {
    expect(parseSignalWorkspaceLink("?mode=EDITOR&symbol=BTCUSDT&timeframe=5m&signal_id=sg-25")).toEqual({
      mode: "EDITOR", symbol: "BTCUSDT", timeframe: "5m", signalId: "sg-25",
    });
    expect(parseSignalWorkspaceLink("?mode=TERMINAL&symbol=SOLUSDT&timeframe=1m")).toEqual({
      mode: "TERMINAL", symbol: "SOLUSDT", timeframe: "1m", signalId: null,
    });
  });
  it("rejects unknown modes, malformed symbols and unsupported timeframes", () => {
    for (const query of ["?mode=AUTOPILOT&symbol=BTCUSDT&timeframe=5m",
      "?mode=EDITOR&symbol=BTCUSDT&timeframe=bad",
      "?mode=EDITOR&symbol=../BTCUSDT&timeframe=5m",
      "?mode=EDITOR&symbol=BTCUSDT&timeframe=5m&signal_id=a%2Fb",
      "?symbol=BTCUSDT&timeframe=5m"]) expect(parseSignalWorkspaceLink(query)).toBeNull();
  });
});

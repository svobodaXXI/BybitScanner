import { describe, expect, it } from "vitest";
import { editorSignalWorkspaceHref, parseSignalWorkspaceLink } from "./signalDeepLink";

describe("GFL editor and terminal deep link", () => {
  it("parses a symbol, timeframe, editor mode, and opaque signal ID", () => {
    expect(parseSignalWorkspaceLink("?mode=EDITOR&symbol=BTCUSDT&timeframe=5m&signal_id=sg-25")).toEqual({
      mode: "EDITOR", symbol: "BTCUSDT", timeframe: "5m", signalId: "sg-25",
    });
    expect(parseSignalWorkspaceLink("?mode=TERMINAL&symbol=SOLUSDT&timeframe=1m")).toEqual({
      mode: "TERMINAL", symbol: "SOLUSDT", timeframe: "1m", signalId: null,
    });
  });
  it("uses the validated Editor source link, never a symbol-only or malformed identity", () => {
    const href = editorSignalWorkspaceHref("BTCUSDT", "5m", "candidate-42");
    expect(href).toBe("?mode=EDITOR&symbol=BTCUSDT&timeframe=5m&signal_id=candidate-42");
    expect(parseSignalWorkspaceLink(href!)).toEqual({
      mode: "EDITOR", symbol: "BTCUSDT", timeframe: "5m", signalId: "candidate-42",
    });
    expect(editorSignalWorkspaceHref("BTCUSDT", "5m", "../unsafe")).toBeNull();
    expect(editorSignalWorkspaceHref("BTC", "5m", "candidate-42")).toBeNull();
  });
  it("opens the owner Autopilot tab directly without inventing signal identity", () => {
    expect(parseSignalWorkspaceLink("?mode=AUTOPILOT&symbol=BTCUSDT&timeframe=5m")).toEqual({
      mode: "AUTOPILOT", symbol: "BTCUSDT", timeframe: "5m", signalId: null,
    });
  });
  it("rejects unknown modes, malformed symbols and unsupported timeframes", () => {
    for (const query of ["?mode=SCANNER&symbol=BTCUSDT&timeframe=5m",
      "?mode=EDITOR&symbol=BTCUSDT&timeframe=bad",
      "?mode=EDITOR&symbol=../BTCUSDT&timeframe=5m",
      "?mode=EDITOR&symbol=BTCUSDT&timeframe=5m&signal_id=a%2Fb",
      "?symbol=BTCUSDT&timeframe=5m"]) expect(parseSignalWorkspaceLink(query)).toBeNull();
  });
});

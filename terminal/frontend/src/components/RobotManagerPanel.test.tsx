import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RobotManagerPanel } from "./RobotManagerPanel";

function mockRobotApi(stopResponse: { ok: boolean; error?: string }, afterStop = "ROBOT_STOPPED", failedGet: string | null = null) {
  let robot = "ROBOT_RUNNING";
  let recovery = "READY";
  const replies: Record<string, Record<string, unknown>> = {
    "/api/scanner/status": { ok: true, mode: "SCANNER_RUNNING" },
    "/api/robot/autopilot": { ok: true, mode: "PAPER_AUTO" },
    "/api/robot/protection-health": { ok: true, healthy: true, unhealthy_symbols: {} },
    "/api/health": { ok: true, robot_admission_ready: true },
  };
  const request = vi.fn((url: string, options?: RequestInit) => {
    if (options?.method === "POST") {
      if (url !== "/api/robot/stop") throw new Error("unexpected Robot mutation");
      if (stopResponse.ok) {
        robot = afterStop;
        recovery = afterStop === "ROBOT_STOPPED" ? "ROBOT_STOPPED" : recovery;
      }
      return Promise.resolve(new Response(JSON.stringify(stopResponse), {
        status: stopResponse.ok ? 200 : 409,
        headers: { "Content-Type": "application/json" },
      }));
    }
    if (url === failedGet) return Promise.resolve(new Response(JSON.stringify({ ok: false }), { status: 503 }));
    const body = url === "/api/robot/state"
      ? { ok: true, mode: robot, recovery_status: recovery }
      : replies[url];
    if (!body) throw new Error("unexpected read " + url);
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
  });
  vi.stubGlobal("fetch", request);
  return request;
}

afterEach(() => vi.unstubAllGlobals());

describe("RobotManagerPanel", () => {
  it("runs one-tap stop only through the canonical Robot endpoint and verifies its result", async () => {
    const request = mockRobotApi({ ok: true, robot: "ROBOT_STOPPED" } as { ok: boolean });
    render(<RobotManagerPanel onClose={() => {}} />);
    await screen.findByText("ROBOT_RUNNING / READY");
    fireEvent.click(screen.getByRole("button", { name: "Остановить Robot" }));
    expect(await screen.findByText("Robot STOPPED подтверждён. Backend не останавливался.")).toBeInTheDocument();
    await screen.findByText("ROBOT_STOPPED / ROBOT_STOPPED");
    const postCalls = request.mock.calls.filter((call) => call[1]?.method === "POST");
    expect(postCalls).toHaveLength(1);
    expect(postCalls[0][0]).toBe("/api/robot/stop");
    expect(postCalls[0][1]?.body).toBe("{}");
  });

  it("does not force-close open Robot trades after a canonical stop refusal", async () => {
    const request = mockRobotApi({ ok: false, error: "stop_robot is rejected while OPEN Robot trades remain" });
    render(<RobotManagerPanel onClose={() => {}} />);
    await screen.findByText("ROBOT_RUNNING / READY");
    fireEvent.click(screen.getByRole("button", { name: "Остановить Robot" }));
    expect(await screen.findByText(/BLOCKED: stop_robot is rejected while OPEN Robot trades remain/)).toBeInTheDocument();
    expect(request.mock.calls.filter((call) => call[1]?.method === "POST").map((call) => call[0])).toEqual(["/api/robot/stop"]);
    expect(screen.getByText("ROBOT_RUNNING / READY")).toBeInTheDocument();
  });

  it("preserves available Robot diagnosis when Scanner fails and disables every mutation", async () => {
    const request = mockRobotApi({ ok: true }, "ROBOT_STOPPED", "/api/scanner/status");
    render(<RobotManagerPanel onClose={() => {}} />);
    expect(await screen.findByText("ROBOT_RUNNING / READY")).toBeInTheDocument();
    expect(screen.getByText("Недоступны источники: Scanner")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Диагностика неполная");
    for (const name of ["Запустить Robot", "Отключить автовходы", "Остановить Robot"]) {
      expect(screen.getByRole("button", { name })).toBeDisabled();
    }
    expect(request.mock.calls.filter((call) => call[1]?.method === "POST")).toHaveLength(0);
  });

  it("does not offer stop when Robot state is unknown", async () => {
    const request = mockRobotApi({ ok: true }, "ROBOT_STOPPED");
    render(<RobotManagerPanel onClose={() => {}} />);
    await screen.findByText("ROBOT_RUNNING / READY");
    expect(screen.getByRole("button", { name: "Остановить Robot" })).toBeEnabled();
    expect(request.mock.calls.filter((call) => call[1]?.method === "POST")).toHaveLength(0);
  });
});

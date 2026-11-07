import { useCallback, useEffect, useState } from "react";
import { marketApiRoutes } from "../marketData/apiRoutes";
import "./RobotManagerPanel.css";

type Snapshot = {
  robot: string;
  recovery: string;
  reason: string | null;
  scanner: string;
  autopilot: string;
  healthy: boolean | null;
  admission: boolean | null;
  blockers: string[];
};

async function readJson(url: string): Promise<Record<string, unknown>> {
  const response = await fetch(url);
  const data: unknown = await response.json();
  if (!response.ok || !data || typeof data !== "object" || (data as Record<string, unknown>).ok !== true) {
    throw new Error("Диагностика недоступна");
  }
  return data as Record<string, unknown>;
}

/** Uses canonical backend observations, not the Windows-only VPS Manager SSH transport. */
export function RobotManagerPanel({ onClose }: { onClose: () => void }) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");
  const [result, setResult] = useState("");
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<"start" | "freeze" | "stop" | null>(null);

  const refresh = useCallback(async () => {
    try {
    const [robot, scanner, autopilot, protection, health] = await Promise.all([
      readJson(marketApiRoutes.robotState),
      readJson(marketApiRoutes.scannerStatus),
      readJson(marketApiRoutes.robotAutopilot),
      readJson(marketApiRoutes.robotProtectionHealth),
      readJson(marketApiRoutes.health),
    ]);
    const mode = typeof robot.mode === "string" ? robot.mode : "UNKNOWN";
    const recovery = typeof robot.recovery_status === "string" ? robot.recovery_status : "UNKNOWN";
    const reason = typeof robot.reason === "string" && robot.reason.trim() ? robot.reason.trim().slice(0, 200) : null;
    const scannerMode = typeof scanner.mode === "string" ? scanner.mode : "UNKNOWN";
    const autoMode = typeof autopilot.mode === "string" ? autopilot.mode : "UNKNOWN";
    const healthy = typeof protection.healthy === "boolean" ? protection.healthy : null;
    const admission = typeof health.robot_admission_ready === "boolean" ? health.robot_admission_ready : null;
    const blockers: string[] = [];
    if (mode === "ROBOT_RUNNING" && !["READY", "PAUSED"].includes(recovery)) blockers.push("Robot: " + recovery);
    if (reason) blockers.push("Причина Robot: " + reason);
    if (healthy !== true) blockers.push("Защита: " + (healthy === false ? "UNHEALTHY" : "UNKNOWN"));
    if (mode === "ROBOT_RUNNING" && recovery === "READY" && admission !== true) blockers.push("Допуск: " + (admission === false ? "закрыт" : "неизвестен"));
    if (protection.unhealthy_symbols && typeof protection.unhealthy_symbols === "object") {
      const symbols = Object.keys(protection.unhealthy_symbols);
      if (symbols.length) blockers.push("Проблемные символы: " + symbols.join(", "));
    }
    setSnapshot({ robot: mode, recovery, reason, scanner: scannerMode, autopilot: autoMode, healthy, admission, blockers });
    setError("");
    } catch (error) {
      setSnapshot(null); // A stale READY is never authority for a new control action.
      setError("Диагностика недоступна. Состояние неизвестно.");
      throw error;
    }
  }, []);

  useEffect(() => {
    let active = true;
    void refresh().catch(() => { if (active) setError("Диагностика недоступна. Состояние неизвестно."); });
    return () => { active = false; };
  }, [refresh]);

  const execute = async (action: "start" | "freeze" | "stop") => {
    setPending(null);
    if (busy) return;
    setBusy(true);
    setResult("");
    try {
      // Reuse the existing canonical Robot reconciler and Autopilot admission fence.
      // Neither endpoint bypasses admission, STOP/TAKE, owner guards or LIVE restrictions.
      const path = action === "start" ? marketApiRoutes.runtimeIntent
        : action === "stop" ? marketApiRoutes.robotStop
        : marketApiRoutes.robotAutopilot;
      const body = action === "start" ? { intent: "ROBOT" }
        : action === "stop" ? {}
        : { mode: "OFF" };
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const result = await response.json() as { ok?: boolean; blocked_by?: string[]; error?: string };
      if (!response.ok || result.ok !== true) {
        setResult("BLOCKED: " + (result.blocked_by?.join(", ") || result.error || "неизвестная причина"));
      } else {
        setResult(action === "start" ? "Robot запущен через штатный reconciler."
          : action === "stop" ? "Robot STOPPED подтверждён. Backend не останавливался."
          : "Автоматические новые входы отключены. Robot и STOP/TAKE продолжают работать.");
      }
    } catch {
      setResult("Результат операции неизвестен; повтор не выполнялся.");
    } finally {
      try { await refresh(); } catch { setError("Не удалось подтвердить новое состояние."); }
      setBusy(false);
    }
  };

  return (
    <div className="robot-manager-backdrop" role="presentation">
      <section className="robot-manager-panel" role="region" aria-label="Управление роботом">
        <header><strong>Управление роботом</strong><button type="button" onClick={onClose} aria-label="К Автопилоту" title="К Автопилоту">←</button></header>
        <p className="robot-manager-note">Только PAPER Robot — независимо от выбранного счёта Terminal. Диагностика из действующего backend; VPS Manager используется как образец.</p>
        {snapshot ? <dl className="robot-manager-status">
          <dt>Robot</dt><dd>{snapshot.robot} / {snapshot.recovery}</dd>
          <dt>Scanner</dt><dd>{snapshot.scanner}</dd>
          <dt>Автопилот</dt><dd>{snapshot.autopilot}</dd>
          <dt>Защита</dt><dd>{snapshot.healthy === true ? "HEALTHY" : snapshot.healthy === false ? "UNHEALTHY" : "UNKNOWN"}</dd>
          <dt>Допуск</dt><dd>{snapshot.admission === true ? "Открыт" : snapshot.admission === false ? "Закрыт" : "Неизвестен"}</dd>
        </dl> : <p>Состояние неизвестно</p>}
        <h4>Блокеры и ограничения</h4>
        {snapshot?.blockers.length ? <ul>{snapshot.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul> : <p>{snapshot ? "Явных блокеров в этих источниках нет; полный preflight не выполнен." : "Данные недоступны"}</p>}
        {error ? <p role="alert">{error}</p> : null}
        {result ? <p role="status">{result}</p> : null}
        <div className="robot-manager-actions">
          <button type="button" disabled={busy} onClick={() => void refresh().catch(() => setError("Диагностика недоступна."))}>Обновить</button>
          <button type="button" disabled={busy || !snapshot} onClick={() => setPending("start")}>Запустить Robot</button>
          <button type="button" disabled={busy || !snapshot || snapshot.autopilot === "OFF"} onClick={() => setPending("freeze")}>Отключить автовходы</button>
          <button type="button" disabled={busy || !snapshot || snapshot.robot !== "ROBOT_RUNNING" || !["READY", "PAUSED"].includes(snapshot.recovery)} onClick={() => setPending("stop")}>Остановить Robot</button>
        </div>
        {pending ? <div className="robot-manager-confirm" role="group" aria-label="Подтверждение действия">
          <p>{pending === "start" ? "Запустить Robot через штатный reconciler? PAPER_AUTO отдельно не включается."
            : pending === "stop" ? "Остановить Robot штатной командой? При открытых Robot-сделках команда будет отклонена; защита позиций и Backend сохраняются."
            : "Отключить новые автоматические входы? Robot и защита открытых позиций останутся активными."}</p>
          <button type="button" disabled={busy} onClick={() => void execute(pending)}>Подтвердить</button>
          <button type="button" onClick={() => setPending(null)}>Отмена</button>
        </div> : null}
      </section>
    </div>
  );
}

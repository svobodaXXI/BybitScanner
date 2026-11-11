import { useEffect, useState } from "react";
import "./appVersionControl.css";

type InstalledVersion = {
  installed_sha: string | null;
  build_status: "MANIFEST_HASH_MATCH" | "UNVERIFIED";
};
type UpdateResult = {
  status: "CURRENT" | "NO_COMPATIBLE_RELEASE" | "PUBLISHED_CANDIDATE" | "CHECK_UNAVAILABLE";
  available_sha?: string;
  message?: string;
};

function updateMessage(update: UpdateResult): string {
  if (update.status === "CURRENT") return "Установленная версия совпадает с опубликованной.";
  if (update.status === "NO_COMPATIBLE_RELEASE") return "Совместимых опубликованных обновлений пока нет.";
  if (update.status === "PUBLISHED_CANDIDATE")
    return `Обнаружен выпуск ${update.available_sha?.slice(0, 12) ?? ""}. Автоустановка ещё не подключена.`;
  return "Не удалось проверить GitHub. Локальная работа доступна без интернета.";
}

/** Deliberately no polling: a weak laptop performs one local read per launch
 * and GitHub is queried only by an explicit click.
 */
export function AppVersionControl() {
  const [installed, setInstalled] = useState<InstalledVersion | null>(null);
  const [checking, setChecking] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    void fetch("/local-replay/app-version", {
      method: "GET", cache: "no-store", signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) throw new Error("unavailable");
      const value: unknown = await response.json();
      if (value && typeof value === "object") {
        const data = value as Record<string, unknown>;
        if ((data.installed_sha === null ||
             (typeof data.installed_sha === "string" && /^[0-9a-f]{40}$/.test(data.installed_sha))) &&
            (data.build_status === "MANIFEST_HASH_MATCH" || data.build_status === "UNVERIFIED")) {
          setInstalled(data as InstalledVersion);
        }
      }
    }).catch(() => { /* Source or old package without version endpoint. */ });
    return () => controller.abort();
  }, []);

  async function check() {
    if (checking) return;
    setChecking(true);
    setMessage("");
    try {
      const response = await fetch("/local-replay/update/check", {
        method: "POST",
        cache: "no-store",
        headers: { "X-Local-Update-Check": "1" },
      });
      if (!response.ok) throw new Error("check_http_" + response.status);
      const raw: unknown = await response.json();
      if (!raw || typeof raw !== "object" || !("status" in raw) ||
          !["CURRENT", "NO_COMPATIBLE_RELEASE", "PUBLISHED_CANDIDATE", "CHECK_UNAVAILABLE"]
            .includes((raw as Record<string, unknown>).status as string))
        throw new Error("check_result_invalid");
      setMessage(updateMessage(raw as UpdateResult));
    } catch {
      setMessage("Не удалось проверить GitHub. Симулятор продолжает работать автономно.");
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="replay-app-version" aria-label="Версия Машины времени">
      <span title={installed?.installed_sha ?? "Версия этой сборки не подтверждена"}>
        Версия: {installed?.build_status === "MANIFEST_HASH_MATCH"
          ? installed.installed_sha?.slice(0, 12) : "не определена"}
      </span>
      <button type="button" disabled={checking} onClick={() => void check()}>
        {checking ? "Проверка…" : "Проверить обновления"}
      </button>
      {message ? <small role="status">{message}</small> : null}
    </div>
  );
}

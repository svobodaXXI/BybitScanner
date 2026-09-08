(function () {
  "use strict";

  window.addEventListener("DOMContentLoaded", async function () {
    const platform = window.TradingJournalPlatform;
    if (!platform || typeof platform.authHeaders !== "function") return;
    try {
      const response = await fetch("/api/miniapp/access", { headers: platform.authHeaders() });
      if (!response.ok) return;
      const access = await response.json();
      if (!access.read_only) return;
      const shell = document.querySelector(".app-shell");
      const header = document.querySelector(".app-header");
      if (!shell || !header || document.getElementById("viewer-notice")) return;
      const notice = document.createElement("div");
      notice.id = "viewer-notice";
      notice.className = "state-card";
      notice.textContent = access.notice || "Вы просматриваете журнал. Редактирование отключено.";
      header.insertAdjacentElement("afterend", notice);
    } catch (_) {
      // The main application renders authentication/network errors itself.
    }
  });
})();

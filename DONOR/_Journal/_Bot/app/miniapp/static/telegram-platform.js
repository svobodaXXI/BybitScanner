(function () {
  "use strict";

  const webApp = window.Telegram && window.Telegram.WebApp;

  window.TradingJournalPlatform = {
    provider: "telegram",

    prepare() {
      if (!webApp) return;
      webApp.ready();
      webApp.expand();
    },

    authHeaders() {
      if (!webApp || !webApp.initData) return {};
      return { "X-Telegram-Init-Data": webApp.initData };
    },

    authErrorMessage: "Доступ к Mini App не подтверждён Telegram.",
  };
})();

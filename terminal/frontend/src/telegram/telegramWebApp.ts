export interface TelegramSafeArea {
  top: number;
  right: number;
  bottom: number;
  left: number;
}
export interface TelegramWebApp {
  contentSafeAreaInset?: TelegramSafeArea;
  expand(): void;
  ready(): void;
  setBackgroundColor?(color: string): void;
  setHeaderColor?(color: string): void;
  onEvent?(event: "contentSafeAreaChanged", listener: () => void): void;
  offEvent?(event: "contentSafeAreaChanged", listener: () => void): void;
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

function applySafeArea(webApp: TelegramWebApp, root: HTMLElement) {
  const inset = webApp.contentSafeAreaInset ?? {
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
  };
  root.style.setProperty("--tg-content-safe-area-inset-top", `${inset.top}px`);
  root.style.setProperty(
    "--tg-content-safe-area-inset-right",
    `${inset.right}px`,
  );
  root.style.setProperty(
    "--tg-content-safe-area-inset-bottom",
    `${inset.bottom}px`,
  );
  root.style.setProperty(
    "--tg-content-safe-area-inset-left",
    `${inset.left}px`,
  );
}

export function initializeTelegramMiniApp(
  root: HTMLElement = document.documentElement,
) {
  const webApp = window.Telegram?.WebApp;
  if (!webApp) return { embedded: false, dispose: () => undefined };
  const updateSafeArea = () => applySafeArea(webApp, root);
  updateSafeArea();
  webApp.setHeaderColor?.("#11161c");
  webApp.setBackgroundColor?.("#090c10");
  webApp.expand();
  webApp.ready();
  webApp.onEvent?.("contentSafeAreaChanged", updateSafeArea);
  return {
    embedded: true,
    dispose: () => webApp.offEvent?.("contentSafeAreaChanged", updateSafeArea),
  };
}

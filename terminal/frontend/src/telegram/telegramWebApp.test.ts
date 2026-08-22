import { afterEach, describe, expect, it, vi } from "vitest";
import {
  initializeTelegramMiniApp,
  type TelegramWebApp,
} from "./telegramWebApp";

afterEach(() => {
  delete window.Telegram;
});

describe("Telegram Mini App adapter", () => {
  it("keeps ordinary browser launch available", () => {
    expect(initializeTelegramMiniApp().embedded).toBe(false);
  });
  it("initializes Telegram and applies content safe-area values", () => {
    const webApp: TelegramWebApp = {
      contentSafeAreaInset: { top: 12, right: 3, bottom: 18, left: 4 },
      expand: vi.fn(),
      ready: vi.fn(),
      setBackgroundColor: vi.fn(),
      setHeaderColor: vi.fn(),
    };
    window.Telegram = { WebApp: webApp };
    const root = document.createElement("div");
    expect(initializeTelegramMiniApp(root).embedded).toBe(true);
    expect(webApp.expand).toHaveBeenCalledOnce();
    expect(webApp.ready).toHaveBeenCalledOnce();
    expect(
      root.style.getPropertyValue("--tg-content-safe-area-inset-bottom"),
    ).toBe("18px");
  });
});

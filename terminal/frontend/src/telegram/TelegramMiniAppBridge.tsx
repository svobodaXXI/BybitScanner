import { useEffect } from "react";
import { initializeTelegramMiniApp } from "./telegramWebApp";
export function TelegramMiniAppBridge() {
  useEffect(() => initializeTelegramMiniApp().dispose, []);
  return null;
}

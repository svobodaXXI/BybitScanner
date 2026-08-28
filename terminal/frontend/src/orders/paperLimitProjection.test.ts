import { describe, expect, it } from "vitest";
import type { PaperLimitOrder } from "../contracts/trading";
import { projectPaperLimitOrders } from "./paperLimitProjection";

describe("projectPaperLimitOrders", () => {
  it("preserves each order identity and notional at a shared price", () => {
    const orders: PaperLimitOrder[] = [
      { order_id: "buy-1", order_link_id: "a", symbol: "ONGUSDT", side: "Buy", price: "2", quantity: "3", time_in_force: "GTC" },
      { order_id: "buy-2", order_link_id: "b", symbol: "ONGUSDT", side: "Buy", price: "2", quantity: "4", time_in_force: "GTC" },
      { order_id: "sell-1", order_link_id: "c", symbol: "ONGUSDT", side: "Sell", price: "2.5", quantity: "2", time_in_force: "GTC" },
    ];

    expect(projectPaperLimitOrders(orders)).toEqual([
      { id: "buy-1", price: 2, notionalUsdt: 6, side: "BUY" },
      { id: "buy-2", price: 2, notionalUsdt: 8, side: "BUY" },
      { id: "sell-1", price: 2.5, notionalUsdt: 5, side: "SELL" },
    ]);
  });
});

import type { OwnOrder } from "../contracts/marketData";
import type { PaperLimitOrder } from "../contracts/trading";

export function projectPaperLimitOrders(
  orders: readonly PaperLimitOrder[],
): OwnOrder[] {
  return orders.flatMap((order) => {
    const price = Number(order.price);
    const quantity = Number(order.quantity);
    if (!Number.isFinite(price) || !Number.isFinite(quantity)) return [];
    return [{
      id: order.order_id,
      price,
      notionalUsdt: price * quantity,
      side: order.side === "Buy" ? "BUY" as const : "SELL" as const,
    }];
  });
}

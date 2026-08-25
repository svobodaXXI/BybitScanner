import { useCallback, useEffect, useRef, useState } from "react";
import {
  type CommandResult,
  type FullCloseCommandRequest,
  HANDLED_REASON_CODES,
  type LimitCommandRequest,
  type MarketCommandRequest,
  type MarketSide,
  type PaperState,
  type PaperLimitCancelRequest,
  type PaperLimitAmendRequest,
  type PaperLimitMutationResult,
  type PaperLimitOrder,
} from "../contracts/trading";

export type WorkspaceMode = "TERMINAL" | "AUTOPILOT" | "EDITOR";

const descriptions: Record<WorkspaceMode, string> = {
  TERMINAL: "Manual PAPER execution is available for the development instrument.",
  AUTOPILOT: "Robot observation and control are intentionally not implemented.",
  EDITOR: "Editor tools are reserved for a later authorized slice.",
};

export function ModePanel({
  mode,
  onModeChange,
}: {
  mode: WorkspaceMode;
  onModeChange: (mode: WorkspaceMode) => void;
}) {
  const [executionStatus, setExecutionStatus] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [engagedWorkingVolume, setEngagedWorkingVolume] = useState<string | null>(
    null,
  );
  const [engagedNotionalUsdt, setEngagedNotionalUsdt] = useState("0");
  const [buyAmount, setBuyAmount] = useState("");
  const [sellAmount, setSellAmount] = useState("");
  const [limitSide, setLimitSide] = useState<MarketSide>("Buy");
  const [limitPrice, setLimitPrice] = useState("64200");
  const [limitAmount, setLimitAmount] = useState("250");
  const [activeLimits, setActiveLimits] = useState<PaperLimitOrder[]>([]);
  const [amendPrices, setAmendPrices] = useState<Record<string, string>>({});
  const buyAmountEdited = useRef(false);
  const sellAmountEdited = useRef(false);
  const submissionInFlight = useRef(false);

  const refreshPaperState = useCallback(async () => {
    try {
      const response = await fetch("/api/paper-state?symbol=BTCUSDT");
      if (!response.ok) {
        setEngagedWorkingVolume(null);
        return;
      }

      const state = (await response.json()) as PaperState;

      const engagedWv = Number(state.engaged_wv);
      const engagedNotional = Number(state.engaged_notional_usdt);
      setEngagedWorkingVolume(
        state.ok && Number.isFinite(engagedWv) ? engagedWv.toFixed(1) : null,
      );
      setEngagedNotionalUsdt(
        state.ok && Number.isFinite(engagedNotional)
          ? String(Math.round(Math.max(0, engagedNotional)))
          : "0",
      );
      const limits = state.ok ? state.active_limit_orders : [];
      setActiveLimits(limits);
      setAmendPrices((current) => Object.fromEntries(
        limits.map((order) => [order.order_id, current[order.order_id] ?? order.price]),
      ));
      if (state.ok && !buyAmountEdited.current) {
        setBuyAmount(state.one_wv_usdt);
      }
      if (state.ok && !sellAmountEdited.current) {
        setSellAmount(state.one_wv_usdt);
      }
    } catch {
      setEngagedWorkingVolume(null);
      setEngagedNotionalUsdt("0");
    }
  }, []);

  useEffect(() => {
    if (mode === "TERMINAL") {
      buyAmountEdited.current = false;
      sellAmountEdited.current = false;
      void refreshPaperState();
    }
  }, [mode, refreshPaperState]);

  const alternatives = (["TERMINAL", "AUTOPILOT", "EDITOR"] as const).filter(
    (candidate) => candidate !== mode,
  );

  const submitPaperMarket = async (side: MarketSide, amount: string) => {
    if (submissionInFlight.current) return;
    const numericAmount = Number(amount);
    if (!amount.trim() || !Number.isFinite(numericAmount) || numericAmount <= 0) {
      return;
    }

    submissionInFlight.current = true;
    setIsSubmitting(true);

    try {
      const request: MarketCommandRequest = {
        client_action_id: `paper-market-${side.toLowerCase()}-${Date.now()}`,
        symbol: "BTCUSDT",
        side,
        volume: { unit: "usdt", amount },
        sizing_reference_price: "64250",
        slippage_type: "Percent",
        slippage_value: "0.5",
      };
      const result = await fetch("/api/market", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });

      const commandResult = (await result.json()) as CommandResult;

      setExecutionStatus(
        commandResult.status === "completed"
          ? `PAPER ${side.toUpperCase()} completed`
          : commandResult.reason_code === HANDLED_REASON_CODES[0]
            ? "Сумма слишком мала для шага объёма"
            : `${side.toUpperCase()} отменено`,
      );

      if (commandResult.status === "completed") {
        await refreshPaperState();
      }
    } catch {
      setExecutionStatus(`${side.toUpperCase()} отменено`);
    } finally {
      submissionInFlight.current = false;
      setIsSubmitting(false);
    }
  };

  const submitFullClose = async () => {
    if (submissionInFlight.current) return;
    submissionInFlight.current = true;
    setIsSubmitting(true);
    try {
      const request: FullCloseCommandRequest = {
        client_action_id: `paper-full-close-${Date.now()}`,
        symbol: "BTCUSDT",
      };
      const response = await fetch("/api/full-close", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      const result = (await response.json()) as CommandResult;
      setExecutionStatus(
        result.status === "completed" ? "PAPER позиция закрыта" : "Закрытие отменено",
      );
      if (result.status === "completed") await refreshPaperState();
    } catch {
      setExecutionStatus("Закрытие отменено");
    } finally {
      submissionInFlight.current = false;
      setIsSubmitting(false);
    }
  };

  const submitLimit = async () => {
    if (submissionInFlight.current) return;
    if (!(Number(limitPrice) > 0) || !(Number(limitAmount) > 0)) return;
    submissionInFlight.current = true;
    setIsSubmitting(true);
    try {
      const request: LimitCommandRequest = {
        client_action_id: `paper-limit-create-${Date.now()}`,
        symbol: "BTCUSDT", side: limitSide,
        volume: { unit: "usdt", amount: limitAmount },
        sizing_reference_price: limitPrice,
        limit_price: limitPrice, time_in_force: "GTC",
      };
      const response = await fetch("/api/limit", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      const result = (await response.json()) as PaperLimitMutationResult;
      setExecutionStatus(result.status === "completed" ? "PAPER LIMIT создан" : "LIMIT отменён");
      if (result.status === "completed") await refreshPaperState();
    } catch { setExecutionStatus("LIMIT отменён"); }
    finally { submissionInFlight.current = false; setIsSubmitting(false); }
  };

  const cancelLimit = async (orderId: string) => {
    if (submissionInFlight.current) return;
    submissionInFlight.current = true;
    setIsSubmitting(true);
    try {
      const request: PaperLimitCancelRequest = {
        client_action_id: `paper-limit-cancel-${Date.now()}`,
        symbol: "BTCUSDT", order_id: orderId,
      };
      const response = await fetch("/api/limit/cancel", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      const result = (await response.json()) as PaperLimitMutationResult;
      setExecutionStatus(result.status === "completed" ? "PAPER LIMIT отменён" : "Отмена LIMIT не выполнена");
      if (result.status === "completed") await refreshPaperState();
    } catch { setExecutionStatus("Отмена LIMIT не выполнена"); }
    finally { submissionInFlight.current = false; setIsSubmitting(false); }
  };

  const amendLimit = async (orderId: string) => {
    if (submissionInFlight.current) return;
    const price = amendPrices[orderId];
    if (!(Number(price) > 0)) return;
    submissionInFlight.current = true;
    setIsSubmitting(true);
    try {
      const request: PaperLimitAmendRequest = {
        client_action_id: `paper-limit-amend-${Date.now()}`,
        symbol: "BTCUSDT", order_id: orderId, limit_price: price,
      };
      const response = await fetch("/api/limit/amend", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      const result = (await response.json()) as PaperLimitMutationResult;
      setExecutionStatus(result.status === "completed" ? "PAPER LIMIT изменён" : "Изменение LIMIT не выполнено");
      if (result.status === "completed") await refreshPaperState();
    } catch { setExecutionStatus("Изменение LIMIT не выполнено"); }
    finally { submissionInFlight.current = false; setIsSubmitting(false); }
  };

  return (
    <section className="mode-panel" aria-label={`${mode} controls`}>
      <div>
        <p className="eyebrow">Active mode</p>
        <h2>{mode}</h2>
        <p>{descriptions[mode]}</p>
      </div>

      <nav className="mode-switcher" aria-label="Workspace modes">
        {alternatives.map((candidate) => (
          <button
            key={candidate}
            onClick={() => onModeChange(candidate)}
            type="button"
          >
            {candidate}
          </button>
        ))}
      </nav>

      {mode === "TERMINAL" ? (
        <div className="paper-market-actions">
          <div className="paper-wv-indicator" aria-label="Engaged working volume">
            <span>{"\u2694\uFE0F"} {engagedWorkingVolume ?? "\u2014"}</span>
            <span>{engagedNotionalUsdt} USDT</span>
          </div>
          <div className="paper-market-side">
            <button
              onClick={() => submitPaperMarket("Buy", buyAmount)}
              className="paper-market-buy"
              disabled={isSubmitting}
              type="button"
            >
              {isSubmitting ? "..." : "BUY"}
            </button>
            <input
              aria-label="BUY amount"
              inputMode="decimal"
              min="0"
              onChange={(event) => {
                buyAmountEdited.current = true;
                setBuyAmount(event.target.value);
              }}
              type="number"
              value={buyAmount}
            />
          </div>

          <section aria-label="PAPER Limit controls">
            <select aria-label="LIMIT side" value={limitSide} onChange={(event) => setLimitSide(event.target.value as MarketSide)}>
              <option value="Buy">BUY</option><option value="Sell">SELL</option>
            </select>
            <input aria-label="LIMIT price" type="number" min="0" value={limitPrice} onChange={(event) => setLimitPrice(event.target.value)} />
            <input aria-label="LIMIT amount" type="number" min="0" value={limitAmount} onChange={(event) => setLimitAmount(event.target.value)} />
            <button type="button" disabled={isSubmitting} onClick={submitLimit}>Создать LIMIT</button>
            <ul aria-label="Active PAPER limits">
              {activeLimits.map((order) => (
                <li key={order.order_id}>
                  <span>{order.side} {order.quantity} @ {order.price} {order.time_in_force}</span>
                  <input
                    aria-label={`Новая цена ${order.order_id}`}
                    min="0"
                    onChange={(event) => setAmendPrices((current) => ({
                      ...current, [order.order_id]: event.target.value,
                    }))}
                    type="number"
                    value={amendPrices[order.order_id] ?? order.price}
                  />
                  <button type="button" disabled={isSubmitting} onClick={() => amendLimit(order.order_id)}>Изменить {order.order_id}</button>
                  <button type="button" disabled={isSubmitting} onClick={() => cancelLimit(order.order_id)}>Отменить {order.order_id}</button>
                </li>
              ))}
            </ul>
          </section>

          <button disabled={isSubmitting} onClick={submitFullClose} type="button">
            Закрыть позицию
          </button>

          <div className="paper-market-side">
            <button
              onClick={() => submitPaperMarket("Sell", sellAmount)}
              className="paper-market-sell"
              disabled={isSubmitting}
              type="button"
            >
              {isSubmitting ? "..." : "SELL"}
            </button>
            <input
              aria-label="SELL amount"
              inputMode="decimal"
              min="0"
              onChange={(event) => {
                sellAmountEdited.current = true;
                setSellAmount(event.target.value);
              }}
              type="number"
              value={sellAmount}
            />
          </div>

          <p className="paper-execution-status" aria-live="polite">
            {executionStatus}
          </p>
        </div>
      ) : null}
    </section>
  );
}

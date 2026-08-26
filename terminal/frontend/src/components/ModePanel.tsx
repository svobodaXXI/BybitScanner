import { useCallback, useEffect, useRef, useState } from "react";
import {
  type CommandResult,
  type FullCloseCommandRequest,
  HANDLED_REASON_CODES,
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
  sizingReferencePrice,
  onPositionSideChange,
}: {
  mode: WorkspaceMode;
  onModeChange: (mode: WorkspaceMode) => void;
  sizingReferencePrice: string;
  onPositionSideChange: (side: PaperState["position_side"]) => void;
}) {
  const [executionStatus, setExecutionStatus] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [closeConfirmOpen, setCloseConfirmOpen] = useState(false);
  const [engagedWorkingVolume, setEngagedWorkingVolume] = useState<string | null>(
    null,
  );
  const [engagedNotionalUsdt, setEngagedNotionalUsdt] = useState("0");
  const [oneWvUsdt, setOneWvUsdt] = useState("0");
  const [positionQuantity, setPositionQuantity] = useState("0");
  const [positionSide, setPositionSide] = useState<PaperState["position_side"]>("Flat");
  const [holdTooltip, setHoldTooltip] = useState<string | null>(null);
  const holdTooltipTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [buyAmount, setBuyAmount] = useState("");
  const [sellAmount, setSellAmount] = useState("");
  const [activeLimits, setActiveLimits] = useState<PaperLimitOrder[]>([]);
  const [amendPrices, setAmendPrices] = useState<Record<string, string>>({});
  const buyAmountEdited = useRef(false);
  const sellAmountEdited = useRef(false);
  const submissionInFlight = useRef(false);

  const refreshPaperState = useCallback(async () => {
    try {
      const response = await fetch("/api/paper-state?symbol=ONGUSDT");
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
      setPositionSide(state.ok ? state.position_side : "Flat");
      onPositionSideChange(state.ok ? state.position_side : "Flat");
      setOneWvUsdt(state.ok ? state.one_wv_usdt : "0");
      setPositionQuantity(state.ok ? state.position_quantity : "0");
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

  const alternatives = (["TERMINAL", "AUTOPILOT"] as const).filter(
    (candidate) => candidate !== mode,
  );

  const startHoldTooltip = (message: string) => {
    if (holdTooltipTimer.current) {
      clearTimeout(holdTooltipTimer.current);
    }

    holdTooltipTimer.current = setTimeout(() => {
      setHoldTooltip(message);
      holdTooltipTimer.current = null;
    }, 500);
  };

  const stopHoldTooltip = () => {
    if (holdTooltipTimer.current) {
      clearTimeout(holdTooltipTimer.current);
      holdTooltipTimer.current = null;
    }
    setHoldTooltip(null);
  };

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
        symbol: "ONGUSDT",
        side,
        volume: { unit: "usdt", amount },
        sizing_reference_price: sizingReferencePrice,
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
        symbol: "ONGUSDT",
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

  const cancelLimit = async (orderId: string) => {
    if (submissionInFlight.current) return;
    submissionInFlight.current = true;
    setIsSubmitting(true);
    try {
      const request: PaperLimitCancelRequest = {
        client_action_id: `paper-limit-cancel-${Date.now()}`,
        symbol: "ONGUSDT", order_id: orderId,
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
        symbol: "ONGUSDT", order_id: orderId, limit_price: price,
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
            <span
              className="paper-wv-value paper-hold-target"
              onPointerDown={() =>
                startHoldTooltip(`1 \u0420\u041E = ${oneWvUsdt} USDT`)
              }
              onPointerUp={stopHoldTooltip}
              onPointerCancel={stopHoldTooltip}
              onPointerLeave={stopHoldTooltip}
              onTouchStart={() =>
                startHoldTooltip(`1 \u0420\u041E = ${oneWvUsdt} USDT`)
              }
              onTouchEnd={stopHoldTooltip}
              onTouchCancel={stopHoldTooltip}
              onContextMenu={(event) => event.preventDefault()}
            >
              {"\u2694\uFE0F"} {engagedWorkingVolume ?? "\u2014"}
            </span>

            <div
              className={`paper-wv-position ${
                positionSide === "Long"
                  ? "long"
                  : positionSide === "Short"
                    ? "short"
                    : "flat"
              }`}
            >
              <span
                className={`paper-wv-direction ${
                  positionSide === "Long"
                    ? "long"
                    : positionSide === "Short"
                      ? "short"
                      : "flat"
                }`}
                aria-hidden="true"
              />

              <span
                className="paper-position-notional-hold paper-hold-target"
                onPointerDown={() =>
                  startHoldTooltip(`${positionQuantity} BTC`)
                }
                onPointerUp={stopHoldTooltip}
                onPointerCancel={stopHoldTooltip}
                onPointerLeave={stopHoldTooltip}
                onTouchStart={() =>
                  startHoldTooltip(`${positionQuantity} BTC`)
                }
                onTouchEnd={stopHoldTooltip}
                onTouchCancel={stopHoldTooltip}
                onContextMenu={(event) => event.preventDefault()}
              >
                <span className="paper-wv-amount">{engagedNotionalUsdt}</span>
                <span className="paper-wv-currency">USDT</span>
              </span>

              <button
                className="paper-wv-close"
                disabled={isSubmitting || positionSide === "Flat"}
                onClick={() => setCloseConfirmOpen(true)}
                type="button"
                aria-label="??????? ??????? ???????"
                title="??????? ??????? ???????"
              >
                <svg
                  className="paper-close-icon"
                  viewBox="0 0 16 16"
                  aria-hidden="true"
                >
                  <line x1="4" y1="4" x2="12" y2="12" />
                  <line x1="12" y1="4" x2="4" y2="12" />
                </svg>              </button>
            </div>
          </div>

          <div className="paper-market-side paper-market-buy-side">
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

          <div className="paper-market-side paper-market-sell-side">
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

          <div className="paper-utility-stack">
            <button
              className="paper-position-list-button"
              type="button"
              aria-label="?????? ???????? ???????"
              title="?????? ???????? ???????"
              onClick={() => setExecutionStatus("?????? ???????: ????????? ????")}
            >
              <span />
              <span />
              <span />
            </button>

            <button
              className="paper-autopilot-button"
              type="button"
              aria-label="?????????"
              title="?????????"
              onClick={() => onModeChange("AUTOPILOT")}
            >
              <svg
                className="paper-autopilot-wheel-icon"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="9" />
                <circle cx="12" cy="12" r="2.2" />

                <line x1="4.5" y1="9.5" x2="10.2" y2="11.3" />
                <line x1="19.5" y1="9.5" x2="13.8" y2="11.3" />

                <line x1="12" y1="14.2" x2="12" y2="20.5" />

                <path d="M4.8 9.8 Q12 6.5 19.2 9.8" />
              </svg>            </button>
          </div>

          <div className="paper-protection-stack">
            <button
              className="paper-stop-button"
              type="button"
              onClick={() => setExecutionStatus("STOP: ??????? ??????????")}
            >
              STOP
            </button>
            <button
              className="paper-take-button"
              type="button"
              onClick={() => setExecutionStatus("TAKE: ??????? ??????????")}
            >
              TAKE
            </button>
          </div>

          <section className="paper-limit-list" aria-label="Active PAPER limits">
            <div className="paper-limit-list-header">
              <span>LIMITS</span>
              <strong>{activeLimits.length}</strong>
            </div>

            <ul>
              {activeLimits.map((order) => (
                <li key={order.order_id}>
                  <span className={`paper-limit-summary ${order.side.toLowerCase()}`}>
                    {order.side} {order.quantity} @ {order.price}
                  </span>
                  <input
                    aria-label={`????? ???? ${order.order_id}`}
                    min="0"
                    onChange={(event) => setAmendPrices((current) => ({
                      ...current,
                      [order.order_id]: event.target.value,
                    }))}
                    type="number"
                    value={amendPrices[order.order_id] ?? order.price}
                  />
                  <button
                    type="button"
                    disabled={isSubmitting}
                    onClick={() => amendLimit(order.order_id)}
                    aria-label="??????????? ????? ????"
                  >
                    ?
                  </button>
                  <button
                    type="button"
                    disabled={isSubmitting}
                    onClick={() => cancelLimit(order.order_id)}
                    aria-label="???????? ???????? ?????"
                  >
                    ?
                  </button>
                </li>
              ))}
            </ul>
          </section>

          <p className="paper-execution-status" aria-live="polite">
            {executionStatus}
          </p>

          {holdTooltip ? (
            <div className="paper-hold-tooltip" role="tooltip">
              {holdTooltip}
            </div>
          ) : null}

          {closeConfirmOpen ? (
            <div
              className="paper-close-confirm-backdrop"
              role="presentation"
              onPointerDown={(event) => {
                if (event.target === event.currentTarget) {
                  setCloseConfirmOpen(false);
                }
              }}
            >
              <section
                className="paper-close-confirm"
                role="dialog"
                aria-modal="true"
                aria-label={"\u0417\u0430\u043a\u0440\u044b\u0442\u044c \u043f\u043e\u0437\u0438\u0446\u0438\u044e?"}
              >
                <strong>{"\u0417\u0430\u043a\u0440\u044b\u0442\u044c \u043f\u043e\u0437\u0438\u0446\u0438\u044e?"}</strong>

                <span>
                  {positionSide === "Long"
                    ? "LONG"
                    : positionSide === "Short"
                      ? "SHORT"
                      : "FLAT"}{" "}
                  {"\u00b7"} {engagedNotionalUsdt} USDT
                </span>

                <div className="paper-close-confirm-actions">
                  <button
                    type="button"
                    className="paper-close-confirm-accept"
                    disabled={isSubmitting}
                    onClick={async () => {
                      await submitFullClose();
                      setCloseConfirmOpen(false);
                    }}
                  >
                    {"\u0417\u0410\u041a\u0420\u042b\u0422\u042c \u041f\u041e\u0417\u0418\u0426\u0418\u042e"}
                  </button>

                  <button
                    type="button"
                    className="paper-close-confirm-cancel"
                    disabled={isSubmitting}
                    onClick={() => setCloseConfirmOpen(false)}
                  >
                    {"\u041d\u0415 \u0417\u0410\u041a\u0420\u042b\u0412\u0410\u0422\u042c"}
                  </button>
                </div>
              </section>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

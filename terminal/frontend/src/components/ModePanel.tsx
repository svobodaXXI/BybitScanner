import { useEffect, useRef, useState, type Dispatch } from "react";
import {
  type CommandResult,
  type FullCloseCommandRequest,
  HANDLED_REASON_CODES,
  type MarketCommandRequest,
  type MarketSide,
  type PaperLimitAmendRequest,
  type PaperLimitCancelRequest,
  type PaperLimitMutationResult,
  type PaperLimitOrder,
  type PaperState,
} from "../contracts/trading";
import {
  formatPositionAverageEntry,
  formatPositionPnlPercent,
  positionPnlPercent,
} from "../marketData/positionPnl";
import { baseAssetFromSymbol } from "../marketData/symbol";
import {
  createLimitDraft,
  type LimitDraftAction,
  type LimitDraftState,
  normalizeLimitDraftPrice,
} from "../orders/limitDraft";

export type WorkspaceMode = "TERMINAL" | "AUTOPILOT" | "EDITOR";

const descriptions: Record<WorkspaceMode, string> = {
  TERMINAL: "Manual PAPER execution is available for the development instrument.",
  AUTOPILOT: "Robot observation and control are intentionally not implemented.",
  EDITOR: "Editor tools are reserved for a later authorized slice.",
};

export function ModePanel({
  mode,
  onModeChange,
  symbol,
  paperState,
  activeLimitOrders,
  refreshPaperState,
  sizingReferencePrice,
  authoritativeTickSize,
  limitDraftState,
  dispatchLimitDraft,
  onLimitDraftConfirm,
  onFastLimitHoldChange = () => {},
  onPositionSideChange,
  onPositionAverageEntryChange,
}: {
  mode: WorkspaceMode;
  onModeChange: (mode: WorkspaceMode) => void;
  symbol: string;
  paperState: PaperState | null;
  activeLimitOrders: PaperLimitOrder[];
  refreshPaperState: () => Promise<void>;
  sizingReferencePrice: string;
  authoritativeTickSize: string | null;
  limitDraftState: LimitDraftState;
  dispatchLimitDraft: Dispatch<LimitDraftAction>;
  onLimitDraftConfirm: () => void;
  onFastLimitHoldChange?: (
    intent: { side: MarketSide; volumeUsdt: string } | null,
  ) => void;
  onPositionSideChange: (side: PaperState["position_side"]) => void;
  onPositionAverageEntryChange?: (averageEntry: number | null) => void;
}) {
  const [executionStatus, setExecutionStatus] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [closeConfirmOpen, setCloseConfirmOpen] = useState(false);
  const [limitPresentationOpen, setLimitPresentationOpen] = useState(false);
  const [limitsOverlayOpen, setLimitsOverlayOpen] = useState(false);
  const [limitsShortExpanded, setLimitsShortExpanded] = useState(false);
  const [limitsLongExpanded, setLimitsLongExpanded] = useState(false);
  const limitsHoldTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const limitsLongPressTriggered = useRef(false);
  const [cancelAllLimitsConfirmOpen, setCancelAllLimitsConfirmOpen] =
    useState(false);
  const [cancelLimitSideConfirm, setCancelLimitSideConfirm] =
    useState<"Buy" | "Sell" | null>(null);
  const [engagedWorkingVolume, setEngagedWorkingVolume] = useState<string | null>(
    null,
  );
  const [engagedNotionalUsdt, setEngagedNotionalUsdt] = useState("0");
  const [oneWvUsdt, setOneWvUsdt] = useState("0");
  const [positionQuantity, setPositionQuantity] = useState("0");
  const [positionSide, setPositionSide] = useState<PaperState["position_side"]>("Flat");
  const [positionSymbol, setPositionSymbol] = useState("");
  const [positionAverageEntry, setPositionAverageEntry] = useState<number | null>(null);
  const [holdTooltip, setHoldTooltip] = useState<string | null>(null);
  const holdTooltipTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [buyAmount, setBuyAmount] = useState("");
  const [sellAmount, setSellAmount] = useState("");
  const [amendPrices, setAmendPrices] = useState<Record<string, string>>({});
  const buyAmountEdited = useRef(false);
  const sellAmountEdited = useRef(false);
  const submissionInFlight = useRef(false);
  const fastLimitHoldTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fastLimitHoldTriggered = useRef(false);
  const previousLimitDraft = useRef(limitDraftState.draft);

  useEffect(() => {
      const engagedWv = Number(paperState?.engaged_wv);
      const engagedNotional = Number(paperState?.engaged_notional_usdt);
      setEngagedWorkingVolume(
        paperState?.ok && Number.isFinite(engagedWv) ? engagedWv.toFixed(1) : null,
      );
      setEngagedNotionalUsdt(
        paperState?.ok && Number.isFinite(engagedNotional)
          ? String(Math.round(Math.max(0, engagedNotional)))
          : "0",
      );
      const normalizedPositionSide =
        paperState?.ok && (paperState.position_side === "Long" || paperState.position_side === "Short")
          ? paperState.position_side
          : "Flat";
      setPositionSide(normalizedPositionSide);
      setPositionSymbol(paperState?.ok ? paperState.symbol : "");
      onPositionSideChange(normalizedPositionSide);
      const averageEntry = Number(paperState?.average_entry);
      const normalizedAverageEntry =
        paperState?.ok && paperState.average_entry !== null && Number.isFinite(averageEntry)
          && averageEntry > 0
          ? averageEntry
          : null;
      setPositionAverageEntry(normalizedAverageEntry);
      onPositionAverageEntryChange?.(normalizedAverageEntry);
      setOneWvUsdt(paperState?.ok ? paperState.one_wv_usdt : "0");
      setPositionQuantity(paperState?.ok ? paperState.position_quantity : "0");
      setAmendPrices((current) => Object.fromEntries(
        activeLimitOrders.map((order) => [order.order_id, current[order.order_id] ?? order.price]),
      ));
      if (paperState?.ok && !buyAmountEdited.current) {
        setBuyAmount(paperState.one_wv_usdt);
      }
      if (paperState?.ok && !sellAmountEdited.current) {
        setSellAmount(paperState.one_wv_usdt);
      }
  }, [activeLimitOrders, onPositionAverageEntryChange, onPositionSideChange, paperState]);

  useEffect(() => {
    if (mode === "TERMINAL") {
      buyAmountEdited.current = false;
      sellAmountEdited.current = false;
    }
  }, [mode]);

  useEffect(() => {
    if (previousLimitDraft.current !== null && limitDraftState.draft === null) {
      setLimitPresentationOpen(false);
    }
    previousLimitDraft.current = limitDraftState.draft;
  }, [limitDraftState.draft]);

  const alternatives = (["TERMINAL", "AUTOPILOT"] as const).filter(
    (candidate) => candidate !== mode,
  );
  const pnlPercent = positionPnlPercent(
    positionSide,
    positionAverageEntry,
    Number(sizingReferencePrice),
  );
  const pnlTone = pnlPercent === null || pnlPercent === 0
    ? "neutral"
    : pnlPercent > 0 ? "positive" : "negative";
  const positionBaseAsset = baseAssetFromSymbol(positionSymbol);
  const currentPrice = Number(sizingReferencePrice);
  const longDefaultPrice = Number.isFinite(currentPrice) && currentPrice > 0
    ? normalizeLimitDraftPrice(
        String(currentPrice * 0.98),
        authoritativeTickSize,
        "Buy",
      )
    : null;
  const shortDefaultPrice = Number.isFinite(currentPrice) && currentPrice > 0
    ? normalizeLimitDraftPrice(
        String(currentPrice * 1.02),
        authoritativeTickSize,
        "Sell",
      )
    : null;

  const selectLimitDraft = (side: MarketSide, price: string | null) => {
    if (price === null) return;
    dispatchLimitDraft({
      type: "begin",
      draft: createLimitDraft({
        draftId: `limit-draft-${symbol}-${side.toLowerCase()}-${Date.now()}`,
        symbol,
        side,
        origin: "limits-popup",
        volume: { unit: "working_volume", amount: "1" },
        sizingReferencePrice,
        price,
        authoritativeTickSize,
      }),
    });
  };

  const dismissLimitPresentation = () => {
    setLimitPresentationOpen(false);
    dispatchLimitDraft({ type: "dismiss" });
  };

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
        symbol,
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
        symbol,
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
        symbol, order_id: orderId,
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

  const cancelLimits = async (orders: PaperLimitOrder[]) => {
    if (submissionInFlight.current || orders.length === 0) return;

    submissionInFlight.current = true;
    setIsSubmitting(true);

    try {
      const batchId = Date.now();

      const results = await Promise.all(
        orders.map(async (order, index) => {
          const request: PaperLimitCancelRequest = {
            client_action_id: `paper-limit-cancel-batch-${batchId}-${index}`,
            symbol,
            order_id: order.order_id,
          };

          const response = await fetch("/api/limit/cancel", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(request),
          });

          return (await response.json()) as PaperLimitMutationResult;
        }),
      );

      const completed = results.filter((result) => result.status === "completed").length;
      setExecutionStatus(`PAPER LIMITS ????????: ${completed}/${orders.length}`);
      await refreshPaperState();
    } catch {
      setExecutionStatus("???????? ?????? LIMIT ?? ?????????");
      await refreshPaperState();
    } finally {
      submissionInFlight.current = false;
      setIsSubmitting(false);
    }
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
        symbol, order_id: orderId, limit_price: price,
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

  const startFastLimitHold = (side: MarketSide, volumeUsdt: string) => {
    fastLimitHoldTriggered.current = false;

    if (fastLimitHoldTimer.current) {
      clearTimeout(fastLimitHoldTimer.current);
    }

    fastLimitHoldTimer.current = setTimeout(() => {
      fastLimitHoldTriggered.current = true;
      onFastLimitHoldChange({ side, volumeUsdt });
      fastLimitHoldTimer.current = null;
    }, 500);
  };

  const finishFastLimitHold = (side: MarketSide, volumeUsdt: string) => {
    if (fastLimitHoldTimer.current) {
      clearTimeout(fastLimitHoldTimer.current);
      fastLimitHoldTimer.current = null;
    }

    if (fastLimitHoldTriggered.current) {
      onFastLimitHoldChange(null);
      fastLimitHoldTriggered.current = false;
      return;
    }

    submitPaperMarket(side, volumeUsdt);
  };

  const cancelFastLimitHold = () => {
    if (fastLimitHoldTimer.current) {
      clearTimeout(fastLimitHoldTimer.current);
      fastLimitHoldTimer.current = null;
    }

    if (fastLimitHoldTriggered.current) {
      onFastLimitHoldChange(null);
    }

    fastLimitHoldTriggered.current = false;
  };

  const shortLimitOrders = activeLimitOrders.filter((order) => order.side === "Sell");
  const longLimitOrders = activeLimitOrders.filter((order) => order.side === "Buy");

  const limitNotionalUsdt = (order: PaperLimitOrder) => {
    const price = Number(order.price);
    const quantity = Number(order.quantity);
    return Number.isFinite(price) && Number.isFinite(quantity)
      ? price * quantity
      : 0;
  };

  const shortLimitsTotalUsdt = shortLimitOrders.reduce(
    (total, order) => total + limitNotionalUsdt(order),
    0,
  );

  const longLimitsTotalUsdt = longLimitOrders.reduce(
    (total, order) => total + limitNotionalUsdt(order),
    0,
  );

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
          <div className="paper-trade-side-group" aria-label="PAPER trade sides">
            <div className="paper-market-side paper-market-buy-side">
              <button
                onPointerDown={() => startFastLimitHold("Buy", buyAmount)}
                onPointerUp={() => finishFastLimitHold("Buy", buyAmount)}
                onPointerCancel={cancelFastLimitHold}
                onPointerLeave={cancelFastLimitHold}
                onContextMenu={(event) => event.preventDefault()}
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
                onPointerDown={() => startFastLimitHold("Sell", sellAmount)}
                onPointerUp={() => finishFastLimitHold("Sell", sellAmount)}
                onPointerCancel={cancelFastLimitHold}
                onPointerLeave={cancelFastLimitHold}
                onContextMenu={(event) => event.preventDefault()}
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
          </div>

          <div className="paper-position-controls" aria-label="PAPER position controls">
            <div className="paper-wv-indicator" aria-label="Engaged working volume">
              <div className="paper-wv-primary">
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

                {positionSide !== "Flat" ? (
                  <button
                    className={`paper-wv-close ${positionSide.toLowerCase()}`}
                    disabled={isSubmitting}
                    onClick={() => setCloseConfirmOpen(true)}
                    type="button"
                    aria-label="Закрыть позицию"
                    title="Закрыть позицию"
                  >
                    <svg
                      className="paper-close-icon"
                      viewBox="0 0 16 16"
                      aria-hidden="true"
                    >
                      <line x1="4" y1="4" x2="12" y2="12" />
                      <line x1="12" y1="4" x2="4" y2="12" />
                    </svg>
                  </button>
                ) : null}
              </div>

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
                  startHoldTooltip(`${positionQuantity} ${positionBaseAsset}`)
                }
                onPointerUp={stopHoldTooltip}
                onPointerCancel={stopHoldTooltip}
                onPointerLeave={stopHoldTooltip}
                onTouchStart={() =>
                  startHoldTooltip(`${positionQuantity} ${positionBaseAsset}`)
                }
                onTouchEnd={stopHoldTooltip}
                onTouchCancel={stopHoldTooltip}
                onContextMenu={(event) => event.preventDefault()}
              >
                <span className="paper-wv-amount">{engagedNotionalUsdt}</span>
                <span className="paper-wv-currency">USDT</span>
              </span>

            </div>
            </div>

            {positionSide !== "Flat" ? (
              <div className="paper-position-info" aria-label="Current PAPER position">
                <span className="paper-position-symbol">{positionSymbol}</span>
                {positionAverageEntry !== null ? (
                  <span className="paper-position-average">
                    {formatPositionAverageEntry(positionAverageEntry)}
                  </span>
                ) : null}
                {pnlPercent !== null ? (
                  <span className={`paper-position-pnl ${pnlTone}`}>
                    {formatPositionPnlPercent(pnlPercent)}
                  </span>
                ) : null}
              </div>
            ) : null}
          </div>

          <div className="paper-utility-stack" aria-label="PAPER utility controls">
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

          <div className="paper-limits-shell">
            <button
              type="button"
              className="paper-limits-button"
              aria-expanded={limitPresentationOpen || limitsOverlayOpen}
              onPointerDown={() => {
                limitsLongPressTriggered.current = false;
                limitsHoldTimer.current = setTimeout(() => {
                  limitsLongPressTriggered.current = true;
                  setLimitPresentationOpen(false);
                  setLimitsShortExpanded(false);
                  setLimitsLongExpanded(false);
                  setLimitsOverlayOpen(true);
                }, 500);
              }}
              onPointerUp={() => {
                if (limitsHoldTimer.current) {
                  clearTimeout(limitsHoldTimer.current);
                  limitsHoldTimer.current = null;
                }
                if (!limitsLongPressTriggered.current) {
                  setLimitPresentationOpen(true);
                }
              }}
              onPointerCancel={() => {
                if (limitsHoldTimer.current) {
                  clearTimeout(limitsHoldTimer.current);
                  limitsHoldTimer.current = null;
                }
              }}
              onPointerLeave={() => {
                if (limitsHoldTimer.current) {
                  clearTimeout(limitsHoldTimer.current);
                  limitsHoldTimer.current = null;
                }
              }}
            >
              LIMITS {activeLimitOrders.length}
            </button>
            <button
              type="button"
              className="paper-limits-cancel-all"
              aria-label={`Cancel all Limit orders for ${symbol}`}
              onClick={() => setCancelAllLimitsConfirmOpen(true)}
            >
              ×
            </button>
          </div>

          <p className="paper-execution-status" aria-live="polite">
            {executionStatus}
          </p>

          {holdTooltip ? (
            <div className="paper-hold-tooltip" role="tooltip">
              {holdTooltip}
            </div>
          ) : null}

          {limitPresentationOpen ? (
            <div
              className="paper-limit-popup-backdrop"
              role="presentation"
              onPointerDown={(event) => {
                if (event.target === event.currentTarget) {
                  dismissLimitPresentation();
                }
              }}
            >
              <section
                className="paper-limit-popup"
                role="dialog"
                aria-modal="true"
                aria-label="New Limit"
              >
                {([
                  { label: "LONG / L", side: "Buy", price: longDefaultPrice },
                  { label: "SHORT / S", side: "Sell", price: shortDefaultPrice },
                ] as const).map((row) => {
                  const selected = limitDraftState.draft?.side === row.side;
                  const displayedPrice = selected
                    ? limitDraftState.draft?.price
                    : row.price;
                  return (
                    <div
                      key={row.side}
                      className={`paper-limit-popup-row ${row.side.toLowerCase()}${selected ? " selected" : ""}`}
                      role="button"
                      tabIndex={0}
                      onClick={() => selectLimitDraft(row.side, row.price)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          selectLimitDraft(row.side, row.price);
                        }
                      }}
                    >
                      <strong>{row.label}</strong>
                      <span>{oneWvUsdt} USDT</span>
                      <span>{displayedPrice ?? "—"}</span>
                      <button
                        type="button"
                        aria-label={`Confirm ${row.label} Limit`}
                        disabled={!selected || limitDraftState.draft?.status === "submitting" || limitDraftState.draft?.status === "ambiguous"}
                        onClick={(event) => {
                          event.stopPropagation();
                          onLimitDraftConfirm();
                        }}
                      >
                        ✓
                      </button>
                    </div>
                  );
                })}
              </section>
            </div>
          ) : null}

          {limitsOverlayOpen ? (
            <div
              className="paper-limits-overlay-backdrop"
              role="presentation"
              onPointerDown={(event) => {
                if (event.target === event.currentTarget) {
                  setLimitsOverlayOpen(false);
                }
              }}
            >
              <section
                className="paper-limits-overlay"
                role="dialog"
                aria-modal="true"
                aria-label={`Active Limit orders for ${symbol}`}
              >
                <div className="paper-limits-overlay-title">
                  <strong>{symbol}</strong>
                  <button
                    type="button"
                    aria-label="Close Limit orders"
                    onClick={() => setLimitsOverlayOpen(false)}
                  >
                    {"\u00d7"}
                  </button>
                </div>

                <div className="paper-limits-side sell">
                  <div className="paper-limits-side-header">
                    <button
                      type="button"
                      className="paper-limits-side-toggle"
                      onClick={() => setLimitsShortExpanded((value) => !value)}
                    >
                      <strong>SHORT</strong>
                      <span>{shortLimitOrders.length} orders</span>
                      <span>{shortLimitsTotalUsdt.toFixed(2)} USDT</span>
                    </button>
                    <button
                      type="button"
                      className="paper-limits-side-cancel"
                      aria-label={`Cancel all SHORT Limit orders for ${symbol}`}
                      disabled={isSubmitting || shortLimitOrders.length === 0}
                      onClick={() => setCancelLimitSideConfirm("Sell")}
                    >
                      {"\u00d7"}
                    </button>
                  </div>

                  {limitsShortExpanded ? (
                    <div className="paper-limits-order-list">
                      {shortLimitOrders.map((order) => (
                        <div className="paper-limits-order-row" key={order.order_id}>
                          <span>{order.price}</span>
                          <span>{limitNotionalUsdt(order).toFixed(2)} USDT</span>
                          <button
                            type="button"
                            aria-label={`Cancel Limit ${order.order_id}`}
                            onClick={() => cancelLimit(order.order_id)}
                          >
                            {"\u00d7"}
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>

                <div className="paper-limits-side buy">
                  <div className="paper-limits-side-header">
                    <button
                      type="button"
                      className="paper-limits-side-toggle"
                      onClick={() => setLimitsLongExpanded((value) => !value)}
                    >
                      <strong>LONG</strong>
                      <span>{longLimitOrders.length} orders</span>
                      <span>{longLimitsTotalUsdt.toFixed(2)} USDT</span>
                    </button>
                    <button
                      type="button"
                      className="paper-limits-side-cancel"
                      aria-label={`Cancel all LONG Limit orders for ${symbol}`}
                      disabled={isSubmitting || longLimitOrders.length === 0}
                      onClick={() => setCancelLimitSideConfirm("Buy")}
                    >
                      {"\u00d7"}
                    </button>
                  </div>

                  {limitsLongExpanded ? (
                    <div className="paper-limits-order-list">
                      {longLimitOrders.map((order) => (
                        <div className="paper-limits-order-row" key={order.order_id}>
                          <span>{order.price}</span>
                          <span>{limitNotionalUsdt(order).toFixed(2)} USDT</span>
                          <button
                            type="button"
                            aria-label={`Cancel Limit ${order.order_id}`}
                            onClick={() => cancelLimit(order.order_id)}
                          >
                            {"\u00d7"}
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              </section>
            </div>
          ) : null}

          {cancelLimitSideConfirm ? (
            <div
              className="paper-close-confirm-backdrop"
              role="presentation"
              onPointerDown={(event) => {
                if (event.target === event.currentTarget) {
                  setCancelLimitSideConfirm(null);
                }
              }}
            >
              <section
                className="paper-close-confirm"
                role="dialog"
                aria-modal="true"
                aria-label={`Cancel all ${cancelLimitSideConfirm === "Sell" ? "SHORT" : "LONG"} Limit orders for ${symbol}?`}
              >
                <strong>
                  Cancel all {cancelLimitSideConfirm === "Sell" ? "SHORT" : "LONG"} Limit orders for {symbol}?
                </strong>
                <div className="paper-close-confirm-actions">
                  <button
                    type="button"
                    className="paper-close-confirm-accept"
                    disabled={isSubmitting}
                    onClick={async () => {
                      const orders =
                        cancelLimitSideConfirm === "Sell"
                          ? shortLimitOrders
                          : longLimitOrders;
                      await cancelLimits(orders);
                      setCancelLimitSideConfirm(null);
                    }}
                  >
                    CANCEL
                  </button>
                  <button
                    type="button"
                    className="paper-close-confirm-cancel"
                    onClick={() => setCancelLimitSideConfirm(null)}
                  >
                    KEEP
                  </button>
                </div>
              </section>
            </div>
          ) : null}

          {cancelAllLimitsConfirmOpen ? (
            <div
              className="paper-close-confirm-backdrop"
              role="presentation"
              onPointerDown={(event) => {
                if (event.target === event.currentTarget) {
                  setCancelAllLimitsConfirmOpen(false);
                }
              }}
            >
              <section
                className="paper-close-confirm"
                role="dialog"
                aria-modal="true"
                aria-label={`Cancel all Limit orders for ${symbol}?`}
              >
                <strong>Cancel all Limit orders for {symbol}?</strong>
                <span>Batch cancellation is not enabled yet.</span>
                <div className="paper-close-confirm-actions">
                  <button
                    type="button"
                    className="paper-close-confirm-accept"
                    disabled={isSubmitting || activeLimitOrders.length === 0}
                    onClick={async () => {
                      await cancelLimits(activeLimitOrders);
                      setCancelAllLimitsConfirmOpen(false);
                    }}
                  >
                    CANCEL ALL LIMITS
                  </button>
                  <button
                    type="button"
                    className="paper-close-confirm-cancel"
                    onClick={() => setCancelAllLimitsConfirmOpen(false)}
                  >
                    KEEP LIMITS
                  </button>
                </div>
              </section>
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

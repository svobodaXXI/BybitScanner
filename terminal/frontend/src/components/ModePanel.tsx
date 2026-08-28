import { useEffect, useRef, useState, type Dispatch } from "react";
import {
  type CommandMutationResponse,
  type FullCloseCommandRequest,
  HANDLED_REASON_CODES,
  type MarketCommandRequest,
  type MarketSide,
  type PaperLimitAmendRequest,
  type PaperLimitMutationResponse,
  type PaperLimitOrder,
  type PaperState,
} from "../contracts/trading";
import {
  formatPositionAverageEntry,
  formatPositionPnlPercent,
  positionPnlPercent,
} from "../marketData/positionPnl";
import { baseAssetFromSymbol } from "../marketData/symbol";
import { TradingControlButton } from "../interactions/useTradingControlActivation";
import { useTradingNumericInputFocusPolicy } from "../interactions/tradingNumericInput";
import {
  dismissPopupFromBackdrop,
  shieldPopupClickInteraction,
  shieldPopupPointerInteraction,
} from "../interactions/popupInteractionBoundary";
import {
  createLimitDraft,
  type LimitDraftAction,
  type LimitDraftState,
  normalizeLimitDraftPrice,
} from "../orders/limitDraft";
import { isValidSelectedVolume, type SelectedSideVolumes } from "../orders/selectedVolume";

export type WorkspaceMode = "TERMINAL" | "AUTOPILOT" | "EDITOR";
type PaperMutationRunner = <T>(key: string, operation: () => Promise<T>) => Promise<T>;
const EMPTY_PENDING_ACTIONS: ReadonlySet<string> = new Set();
const runMutationDirectly: PaperMutationRunner = (_key, operation) => operation();

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
  applyPaperState = () => false,
  pendingActions = EMPTY_PENDING_ACTIONS,
  runPaperMutation = runMutationDirectly,
  sizingReferencePrice,
  authoritativeTickSize,
  limitDraftState,
  dispatchLimitDraft,
  onLimitDraftConfirm,
  onFastLimitHoldChange = () => {},
  selectedVolumes = { Buy: "", Sell: "" },
  onSelectedVolumeChange = () => {},
  onLimitCancel,
  onPositionSideChange,
  onPositionAverageEntryChange,
}: {
  mode: WorkspaceMode;
  onModeChange: (mode: WorkspaceMode) => void;
  symbol: string;
  paperState: PaperState | null;
  activeLimitOrders: PaperLimitOrder[];
  refreshPaperState: () => Promise<void>;
  applyPaperState?: (state: PaperState) => boolean;
  pendingActions?: ReadonlySet<string>;
  runPaperMutation?: PaperMutationRunner;
  sizingReferencePrice: string;
  authoritativeTickSize: string | null;
  limitDraftState: LimitDraftState;
  dispatchLimitDraft: Dispatch<LimitDraftAction>;
  onLimitDraftConfirm: () => void;
  onFastLimitHoldChange?: (
    intent: { side: MarketSide } | null,
  ) => void;
  selectedVolumes?: SelectedSideVolumes;
  onSelectedVolumeChange?: (side: MarketSide, value: string) => void;
  onLimitCancel?: (orderId: string) => Promise<PaperLimitMutationResponse>;
  onPositionSideChange: (side: PaperState["position_side"]) => void;
  onPositionAverageEntryChange?: (averageEntry: number | null) => void;
}) {
  const tradingInputFocus = useTradingNumericInputFocusPolicy();
  const [executionStatus, setExecutionStatus] = useState("");
  const [closeConfirmOpen, setCloseConfirmOpen] = useState(false);
  const [limitPresentationSide, setLimitPresentationSide] =
    useState<MarketSide | null>(null);
  const [limitsInventorySide, setLimitsInventorySide] =
    useState<MarketSide | null>(null);
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
  const [amendPrices, setAmendPrices] = useState<Record<string, string>>({});
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
  }, [activeLimitOrders, onPositionAverageEntryChange, onPositionSideChange, paperState]);

  useEffect(() => {
    if (previousLimitDraft.current !== null && limitDraftState.draft === null) {
      setLimitPresentationSide(null);
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

  const dismissLimitPresentation = () => {
    setLimitPresentationSide(null);
    dispatchLimitDraft({ type: "dismiss" });
  };

  const dismissSideCancelConfirmation = () => {
    setCancelLimitSideConfirm(null);
  };

  const openLimitPresentation = (side: MarketSide) => {
    setCancelLimitSideConfirm(null);
    setLimitsInventorySide(null);
    setLimitPresentationSide(side);
    const price = side === "Buy" ? longDefaultPrice : shortDefaultPrice;
    if (price === null) {
      dispatchLimitDraft({ type: "dismiss" });
      return;
    }
    dispatchLimitDraft({
      type: "begin",
      draft: createLimitDraft({
        draftId: `limit-draft-${symbol}-${side.toLowerCase()}-${Date.now()}`,
        symbol,
        side,
        origin: "limits-popup",
        volume: { unit: "usdt", amount: selectedVolumes[side] },
        sizingReferencePrice,
        price,
        authoritativeTickSize,
      }),
    });
  };

  const openLimitsInventory = (side: MarketSide) => {
    setCancelLimitSideConfirm(null);
    setLimitPresentationSide(null);
    setLimitsInventorySide(side);
  };

  const openSideCancelConfirmation = (side: MarketSide) => {
    const orders = side === "Buy" ? longLimitOrders : shortLimitOrders;
    if (orders.length === 0) return;
    setLimitPresentationSide(null);
    setLimitsInventorySide(null);
    setCancelLimitSideConfirm(side);
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
    const numericAmount = Number(amount);
    if (!amount.trim() || !Number.isFinite(numericAmount) || numericAmount <= 0) {
      return;
    }

    const actionKey = `MARKET:${side}`;
    await runPaperMutation(actionKey, async () => {
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

      const commandResult = (await result.json()) as CommandMutationResponse;

      setExecutionStatus(
        commandResult.status === "completed"
          ? `PAPER ${side.toUpperCase()} completed`
          : commandResult.reason_code === HANDLED_REASON_CODES[0]
            ? "Сумма слишком мала для шага объёма"
            : `${side.toUpperCase()} отменено`,
      );

      if (commandResult.status === "completed") {
        applyPaperState(commandResult.paper_state);
      }
      } catch {
        setExecutionStatus(`${side.toUpperCase()} отменено`);
        await refreshPaperState();
      }
    });
  };

  const submitFullClose = async () => {
    await runPaperMutation("FULL_CLOSE", async () => {
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
      const result = (await response.json()) as CommandMutationResponse;
      setExecutionStatus(
        result.status === "completed" ? "PAPER позиция закрыта" : "Закрытие отменено",
      );
      if (result.status === "completed") applyPaperState(result.paper_state);
      } catch {
        setExecutionStatus("Закрытие отменено");
        await refreshPaperState();
      }
    });
  };

  const cancelLimit = async (orderId: string) => {
    if (!onLimitCancel) return;
    try {
      const result = await onLimitCancel(orderId);
      setExecutionStatus(result.status === "completed" ? "PAPER LIMIT отменён" : "Отмена LIMIT не выполнена");
    } catch {
      setExecutionStatus("Отмена LIMIT не выполнена");
    }
  };

  const cancelLimits = async (orders: PaperLimitOrder[]) => {
    if (orders.length === 0 || !onLimitCancel) return;

    const side = orders[0].side;
    await runPaperMutation(`CANCEL_SIDE:${side}`, async () => {
      try {
      let completed = 0;

      for (const order of orders) {
        const result = await onLimitCancel(order.order_id);
        if (result.status === "completed") {
          completed += 1;
        }
      }

      setExecutionStatus(`PAPER LIMITS cancelled: ${completed}/${orders.length}`);
      } catch {
        setExecutionStatus("PAPER LIMIT cancellation failed");
        await refreshPaperState();
      }
    });
  };

  const amendLimit = async (orderId: string) => {
    const price = amendPrices[orderId];
    if (!(Number(price) > 0)) return;
    await runPaperMutation(`AMEND_LIMIT:${orderId}`, async () => {
      try {
      const request: PaperLimitAmendRequest = {
        client_action_id: `paper-limit-amend-${Date.now()}`,
        symbol, order_id: orderId, limit_price: price,
      };
      const response = await fetch("/api/limit/amend", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      const result = (await response.json()) as PaperLimitMutationResponse;
      setExecutionStatus(result.status === "completed" ? "PAPER LIMIT изменён" : "Изменение LIMIT не выполнено");
      if (result.status === "completed") applyPaperState(result.paper_state);
      } catch {
        setExecutionStatus("Изменение LIMIT не выполнено");
        await refreshPaperState();
      }
    });
  };

  const shortLimitOrders = activeLimitOrders.filter((order) => order.side === "Sell");
  const longLimitOrders = activeLimitOrders.filter((order) => order.side === "Buy");
  const sortLimitsByCurrentPrice = (orders: PaperLimitOrder[]) =>
    [...orders].sort((left, right) => {
      const distance = Math.abs(Number(left.price) - currentPrice) -
        Math.abs(Number(right.price) - currentPrice);
      return distance || left.order_id.localeCompare(right.order_id);
    });
  const inventoryOrders = limitsInventorySide === "Buy"
    ? sortLimitsByCurrentPrice(longLimitOrders)
    : limitsInventorySide === "Sell"
      ? sortLimitsByCurrentPrice(shortLimitOrders)
      : [];

  const limitNotionalUsdt = (order: PaperLimitOrder) => {
    const price = Number(order.price);
    const quantity = Number(order.quantity);
    return Number.isFinite(price) && Number.isFinite(quantity)
      ? price * quantity
      : 0;
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
        <div className="paper-market-actions" {...tradingInputFocus.boundaryProps}>
          <div className="paper-trade-side-group" aria-label="PAPER trade sides">
            <div className="paper-market-side paper-market-buy-side">
              <TradingControlButton
                onTap={() => void submitPaperMarket("Buy", selectedVolumes.Buy)}
                onHoldStart={() => {
                  navigator.vibrate?.(20);
                  onFastLimitHoldChange({ side: "Buy" });
                }}
                onHoldEnd={() => onFastLimitHoldChange(null)}
                onCancel={() => onFastLimitHoldChange(null)}
                holdMs={200}
                className="paper-market-buy"
                disabled={pendingActions.has("MARKET:Buy")}
                type="button"
              >
                {pendingActions.has("MARKET:Buy") ? "..." : "BUY"}
              </TradingControlButton>
              <input
                {...tradingInputFocus.inputProps}
                aria-label="BUY amount"
                inputMode="decimal"
                min="0"
                placeholder={oneWvUsdt}
                onChange={(event) => {
                  onSelectedVolumeChange("Buy", event.target.value);
                }}
                type="number"
                value={selectedVolumes.Buy}
              />
            </div>

            <div className="paper-market-side paper-market-sell-side">
              <TradingControlButton
                onTap={() => void submitPaperMarket("Sell", selectedVolumes.Sell)}
                onHoldStart={() => {
                  navigator.vibrate?.(20);
                  onFastLimitHoldChange({ side: "Sell" });
                }}
                onHoldEnd={() => onFastLimitHoldChange(null)}
                onCancel={() => onFastLimitHoldChange(null)}
                holdMs={200}
                className="paper-market-sell"
                disabled={pendingActions.has("MARKET:Sell")}
                type="button"
              >
                {pendingActions.has("MARKET:Sell") ? "..." : "SELL"}
              </TradingControlButton>
              <input
                {...tradingInputFocus.inputProps}
                aria-label="SELL amount"
                inputMode="decimal"
                min="0"
                placeholder={oneWvUsdt}
                onChange={(event) => {
                  onSelectedVolumeChange("Sell", event.target.value);
                }}
                type="number"
                value={selectedVolumes.Sell}
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
                  <TradingControlButton
                    className={`paper-wv-close ${positionSide.toLowerCase()}`}

                    onTap={() => setCloseConfirmOpen(true)}
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
                  </TradingControlButton>
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
            {(["Buy", "Sell"] as const).map((side) => {
              const orders = side === "Buy" ? longLimitOrders : shortLimitOrders;
              return (
                <div className="paper-limits-side-control" key={side}>
                  <TradingControlButton
                    type="button"
                    className={`paper-limits-button ${side.toLowerCase()}`}
                    aria-expanded={
                      limitPresentationSide === side || limitsInventorySide === side
                    }
                    onTap={() => openLimitPresentation(side)}
                    onHoldStart={() => openLimitsInventory(side)}
                    holdMs={500}
                  >
                    {side.toUpperCase()} LIMITS <small>{orders.length}</small>
                  </TradingControlButton>
                  <TradingControlButton
                    type="button"
                    className={`paper-limits-cancel-all ${side.toLowerCase()}`}
                    aria-label={`Cancel all ${side} Limit orders for ${symbol}`}
                    disabled={
                      orders.length === 0 || pendingActions.has(`CANCEL_SIDE:${side}`)
                    }
                    onTap={() => openSideCancelConfirmation(side)}
                  >
                    ×
                  </TradingControlButton>
                </div>
              );
            })}

            {limitsInventorySide ? (
              <section
                className={`paper-limits-side-inventory ${limitsInventorySide.toLowerCase()}`}
                aria-label={`Active ${limitsInventorySide} Limit orders for ${symbol}`}
              >
                <header>
                  <strong>{limitsInventorySide.toUpperCase()} LIMITS</strong>
                  <TradingControlButton
                    type="button"
                    aria-label={`Cancel all ${limitsInventorySide} Limit orders for ${symbol}`}
                    disabled={
                      pendingActions.has(`CANCEL_SIDE:${limitsInventorySide}`)
                      || inventoryOrders.length === 0
                    }
                    onTap={() => openSideCancelConfirmation(limitsInventorySide)}
                  >
                    ×
                  </TradingControlButton>
                </header>
                <div className="paper-limits-order-list">
                  {inventoryOrders.map((order) => (
                    <div className="paper-limits-order-row" key={order.order_id}>
                      <span>{order.price}</span>
                      <span>{limitNotionalUsdt(order).toFixed(2)} USDT</span>
                      <TradingControlButton
                        type="button"
                        aria-label={`Cancel Limit ${order.order_id}`}
                        disabled={
                          pendingActions.has(`CANCEL_LIMIT:${order.order_id}`)
                          || pendingActions.has(`CANCEL_SIDE:${order.side}`)
                        }
                        onTap={() => void cancelLimit(order.order_id)}
                      >
                        ×
                      </TradingControlButton>
                    </div>
                  ))}
                </div>
              </section>
            ) : null}
          </div>

          <p className="paper-execution-status" aria-live="polite">
            {executionStatus}
          </p>

          {holdTooltip ? (
            <div className="paper-hold-tooltip" role="tooltip">
              {holdTooltip}
            </div>
          ) : null}

          {limitPresentationSide ? (
            <div
              className="paper-limit-popup-backdrop"
              role="presentation"
              onPointerDown={(event) =>
                dismissPopupFromBackdrop(event, dismissLimitPresentation)
              }
            >
              <section
                className="paper-limit-popup"
                role="dialog"
                aria-modal="true"
                aria-label={`New ${limitPresentationSide} Limit`}
                onPointerDown={shieldPopupPointerInteraction}
                onClick={shieldPopupClickInteraction}
              >
                {(() => {
                  const side = limitPresentationSide;
                  const label = side === "Buy" ? "LONG" : "SHORT";
                  const selected = limitDraftState.draft?.side === side;
                  const draft = selected ? limitDraftState.draft : null;
                  const selectedVolume = selectedVolumes[side];
                  const canSubmit = draft !== null
                    && isValidSelectedVolume(selectedVolume)
                    && normalizeLimitDraftPrice(
                      draft.price,
                      draft.authoritativeTickSize,
                      draft.side,
                    ) !== null
                    && draft.status !== "submitting"
                    && draft.status !== "ambiguous";
                  return (
                    <div
                      className={`paper-limit-popup-row ${side.toLowerCase()}${selected ? " selected" : ""}`}
                    >
                      <strong>{label}</strong>
                      <input
                        {...tradingInputFocus.inputProps}
                        aria-label={`${label} Limit volume`}
                        className="paper-limit-popup-volume"
                        disabled={draft?.status === "submitting" || draft?.status === "ambiguous"}
                        inputMode="decimal"
                        min="0"
                        onChange={(event) => onSelectedVolumeChange(side, event.target.value)}
                        type="number"
                        value={selectedVolume}
                      />
                      <input
                        {...tradingInputFocus.inputProps}
                        aria-label={`${label} Limit price`}
                        className="paper-limit-popup-price"
                        disabled={draft?.status === "submitting" || draft?.status === "ambiguous"}
                        inputMode="decimal"
                        onChange={(event) => {
                          if (!draft) return;
                          dispatchLimitDraft({
                            type: "update-price",
                            draftId: draft.draftId,
                            price: event.target.value,
                          });
                        }}
                        type="text"
                        value={draft?.price ?? ""}
                      />
                      <TradingControlButton
                        type="button"
                        aria-label={`Confirm ${label} Limit`}
                        disabled={!canSubmit}
                        onTap={onLimitDraftConfirm}
                      >
                        ✓
                      </TradingControlButton>
                    </div>
                  );
                })()}
              </section>
            </div>
          ) : null}

          {cancelLimitSideConfirm ? (
            <div
              className="paper-close-confirm-backdrop"
              role="presentation"
              onPointerDown={(event) =>
                dismissPopupFromBackdrop(event, dismissSideCancelConfirmation)
              }
            >
              <section
                className="paper-close-confirm"
                role="dialog"
                aria-modal="true"
                aria-label={`Cancel all ${cancelLimitSideConfirm === "Sell" ? "SHORT" : "LONG"} Limit orders for ${symbol}?`}
                onPointerDown={shieldPopupPointerInteraction}
                onClick={shieldPopupClickInteraction}
              >
                <strong>
                  Cancel all {cancelLimitSideConfirm === "Sell" ? "SHORT" : "LONG"} Limit orders for {symbol}?
                </strong>
                <div className="paper-close-confirm-actions">
                  <TradingControlButton
                    type="button"
                    className="paper-close-confirm-accept"
                    onTap={() => {
                      const orders =
                        cancelLimitSideConfirm === "Sell"
                          ? shortLimitOrders
                          : longLimitOrders;
                      dismissSideCancelConfirmation();
                      void cancelLimits(orders);
                    }}
                  >
                    CANCEL
                  </TradingControlButton>
                  <TradingControlButton
                    type="button"
                    className="paper-close-confirm-cancel"
                    onTap={dismissSideCancelConfirmation}
                  >
                    KEEP
                  </TradingControlButton>
                </div>
              </section>
            </div>
          ) : null}

          {closeConfirmOpen ? (
            <div
              className="paper-close-confirm-backdrop"
              role="presentation"
              onPointerDown={(event) =>
                dismissPopupFromBackdrop(event, () => setCloseConfirmOpen(false))
              }
            >
              <section
                className="paper-close-confirm"
                role="dialog"
                aria-modal="true"
                aria-label={"\u0417\u0430\u043a\u0440\u044b\u0442\u044c \u043f\u043e\u0437\u0438\u0446\u0438\u044e?"}
                onPointerDown={shieldPopupPointerInteraction}
                onClick={shieldPopupClickInteraction}
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
                  <TradingControlButton
                    type="button"
                    className="paper-close-confirm-accept"
                    disabled={pendingActions.has("FULL_CLOSE")}
                    onTap={async () => {
                      await submitFullClose();
                      setCloseConfirmOpen(false);
                    }}
                  >
                    {"\u0417\u0410\u041a\u0420\u042b\u0422\u042c \u041f\u041e\u0417\u0418\u0426\u0418\u042e"}
                  </TradingControlButton>

                  <TradingControlButton
                    type="button"
                    className="paper-close-confirm-cancel"
                    disabled={pendingActions.has("FULL_CLOSE")}
                    onTap={() => setCloseConfirmOpen(false)}
                  >
                    {"\u041d\u0415 \u0417\u0410\u041a\u0420\u042b\u0412\u0410\u0422\u042c"}
                  </TradingControlButton>
                </div>
              </section>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

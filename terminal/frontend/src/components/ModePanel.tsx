import { useEffect, useRef, useState, type Dispatch } from "react";
import {
  type CommandMutationResponse,
  type FullCloseCommandRequest,
  HANDLED_REASON_CODES,
  type MarketCommandRequest,
  type LiveMarketCommandRequest,
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
import { executePaperMarketCommand } from "../orders/paperMarketCommand";
import { createLiveMarketAction, executeLiveMarketCommand } from "../orders/liveMarketCommand";
import { OpenPositionsOverlay } from "./OpenPositionsOverlay";
import { AccountMenu } from "./AccountMenu";
import { LiveAccountInventory } from "./LiveAccountInventory";
import type { AccountWorkspaceProjection } from "../accountWorkspace/accountWorkspaceStore";
import { StopSettings } from "./StopSettings";

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
  onStopTap = () => {},
  onStopHold = () => {},
  stopActive = false,
  stopSettingsOpen = false,
  stopPresetPercent = "2",
  stopReferencePrice = "0",
  onStopSettingsApply = () => {},
  onStopPresetChange = () => {},
  onStopSettingsClose = () => {},
  onTakeTap = () => {},
  onTakeHold = () => {},
  takeActive = false,
  takeSettingsOpen = false,
  takePresetPercent = "3",
  takeReferencePrice = "0",
  onTakeSettingsApply = () => {},
  onTakePresetChange = () => {},
  onTakeSettingsClose = () => {},
  onWorkspaceSymbolSelect,
  accountOpen = false,
  onAccountToggle = () => {},
  accountWorkspaceProjection = null,
  mutationsAllowed = true,
  liveMarketAllowed = false,
  liveLimitAllowed = false,
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
    intent: { side: MarketSide; volumeUsdt: string } | null,
  ) => void;
  selectedVolumes?: SelectedSideVolumes;
  onSelectedVolumeChange?: (side: MarketSide, value: string) => void;
  onLimitCancel?: (orderId: string) => Promise<{ status: string } | null>;
  onPositionSideChange: (side: PaperState["position_side"]) => void;
  onPositionAverageEntryChange?: (averageEntry: number | null) => void;
  onStopTap?: () => "drafted" | "not-improved" | undefined | void;
  onStopHold?: () => void;
  stopActive?: boolean;
  stopSettingsOpen?: boolean;
  stopPresetPercent?: string;
  stopReferencePrice?: string;
  onStopSettingsApply?: (price: string, percent: string) => void;
  onStopPresetChange?: (percent: string) => void;
  onStopSettingsClose?: () => void;
  onTakeTap?: () => void;
  onTakeHold?: () => void;
  takeActive?: boolean;
  takeSettingsOpen?: boolean;
  takePresetPercent?: string;
  takeReferencePrice?: string;
  onTakeSettingsApply?: (price: string, percent: string) => void;
  onTakePresetChange?: (percent: string) => void;
  onTakeSettingsClose?: () => void;
  onWorkspaceSymbolSelect?: (symbol: string) => void;
  accountOpen?: boolean;
  onAccountToggle?: () => void;
  accountWorkspaceProjection?: AccountWorkspaceProjection | null;
  mutationsAllowed?: boolean;
  liveMarketAllowed?: boolean;
  liveLimitAllowed?: boolean;
}) {
  const tradingInputFocus = useTradingNumericInputFocusPolicy();
  const [executionStatus, setExecutionStatus] = useState("");
  const [closeConfirmOpen, setCloseConfirmOpen] = useState(false);
  const [openPositionsVisible, setOpenPositionsVisible] = useState(false);
  const [activeAccountLabel, setActiveAccountLabel] = useState<{ id: string; name: string } | null>(null);
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
  const [liveConfirmation, setLiveConfirmation] = useState<LiveMarketCommandRequest | null>(null);
  const [liveConfirmationSubmitting, setLiveConfirmationSubmitting] = useState(false);
  const liveDispatchActionIdRef = useRef<string | null>(null);

  useEffect(() => {
    setLiveConfirmation(null);
  }, [accountWorkspaceProjection?.account_id, accountWorkspaceProjection?.session_generation]);

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
      const commandResult = await executePaperMarketCommand(request, {
        applyPaperState,
      });

      setExecutionStatus(
        commandResult.status === "completed"
          ? `PAPER ${side.toUpperCase()} completed`
          : commandResult.reason_code === HANDLED_REASON_CODES[0]
            ? "РЎСѓРјРјР° СЃР»РёС€РєРѕРј РјР°Р»Р° РґР»СЏ С€Р°РіР° РѕР±СЉС‘РјР°"
            : `${side.toUpperCase()} РѕС‚РјРµРЅРµРЅРѕ`,
      );

      } catch {
        setExecutionStatus(`${side.toUpperCase()} РѕС‚РјРµРЅРµРЅРѕ`);
        await refreshPaperState();
      }
    });
  };

  const beginMarket = (side: MarketSide, amount: string) => {
    if (mutationsAllowed) {
      void submitPaperMarket(side, amount);
      return;
    }
    const numericAmount = Number(amount);
    if (!liveMarketAllowed || !accountWorkspaceProjection || !amount.trim()
      || !Number.isFinite(numericAmount) || numericAmount <= 0) return;
    const action = createLiveMarketAction({
      accountId: accountWorkspaceProjection.account_id,
      sessionGeneration: accountWorkspaceProjection.session_generation,
      symbol, side, amount, sizingReferencePrice,
    });
    liveDispatchActionIdRef.current = null;
    setLiveConfirmationSubmitting(false);
    setLiveConfirmation(action);
  };

  const confirmLiveMarket = async () => {
    const action = liveConfirmation;
    if (!action || liveDispatchActionIdRef.current === action.client_action_id) return;
    liveDispatchActionIdRef.current = action.client_action_id;
    setLiveConfirmationSubmitting(true);
    const result = await executeLiveMarketCommand(action, {
      currentAuthority: () => accountWorkspaceProjection ? {
        accountId: accountWorkspaceProjection.account_id,
        sessionGeneration: accountWorkspaceProjection.session_generation,
      } : null,
    });
    if (!result) return;
    setLiveConfirmation(null);
    setExecutionStatus(result.status === "unknown"
      ? "LIVE result ambiguous вЂ” reconciling; do not retry"
      : result.status === "accepted_pending" ? "LIVE accepted вЂ” awaiting REST evidence"
      : `LIVE ${result.status}: ${result.reason_code}`);
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
        result.status === "completed" ? "PAPER РїРѕР·РёС†РёСЏ Р·Р°РєСЂС‹С‚Р°" : "Р—Р°РєСЂС‹С‚РёРµ РѕС‚РјРµРЅРµРЅРѕ",
      );
      if (result.status === "completed") applyPaperState(result.paper_state);
      } catch {
        setExecutionStatus("Р—Р°РєСЂС‹С‚РёРµ РѕС‚РјРµРЅРµРЅРѕ");
        await refreshPaperState();
      }
    });
  };

  const cancelLimit = async (orderId: string) => {
    if (!onLimitCancel) return;
    try {
      const result = await onLimitCancel(orderId);
      setExecutionStatus(result?.status === "completed" || result?.status === "accepted_pending"
        ? `${mutationsAllowed ? "PAPER" : "LIVE"} LIMIT cancellation submitted`
        : "LIMIT cancellation failed or requires reconciliation");
    } catch {
      setExecutionStatus("РћС‚РјРµРЅР° LIMIT РЅРµ РІС‹РїРѕР»РЅРµРЅР°");
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
        if (result?.status === "completed" || result?.status === "accepted_pending") {
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
      setExecutionStatus(result.status === "completed" ? "PAPER LIMIT РёР·РјРµРЅС‘РЅ" : "РР·РјРµРЅРµРЅРёРµ LIMIT РЅРµ РІС‹РїРѕР»РЅРµРЅРѕ");
      if (result.status === "completed") applyPaperState(result.paper_state);
      } catch {
        setExecutionStatus("РР·РјРµРЅРµРЅРёРµ LIMIT РЅРµ РІС‹РїРѕР»РЅРµРЅРѕ");
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
        <>
        <div className="paper-market-actions-shell" {...tradingInputFocus.boundaryProps}>
        <div
          aria-label="Manual trading controls"
          className={`paper-market-actions${mutationsAllowed || liveMarketAllowed || liveLimitAllowed ? "" : " is-read-only"}`}
        >
          <fieldset className="paper-mutation-boundary" disabled={!mutationsAllowed && !liveMarketAllowed && !liveLimitAllowed}>
          <div className="paper-trade-side-group" aria-label="PAPER trade sides">
            <div className="paper-market-side paper-market-buy-side">
              <TradingControlButton
                onTap={() => beginMarket("Buy", selectedVolumes.Buy)}
                onHoldStart={() => {
                  if (mutationsAllowed) {
                    navigator.vibrate?.(20);
                    onFastLimitHoldChange({ side: "Buy", volumeUsdt: selectedVolumes.Buy || oneWvUsdt });
                  }
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
                onTap={() => beginMarket("Sell", selectedVolumes.Sell)}
                onHoldStart={() => {
                  if (mutationsAllowed) {
                    navigator.vibrate?.(20);
                    onFastLimitHoldChange({ side: "Sell", volumeUsdt: selectedVolumes.Sell || oneWvUsdt });
                  }
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
                    aria-label="Р—Р°РєСЂС‹С‚СЊ РїРѕР·РёС†РёСЋ"
                    title="Р—Р°РєСЂС‹С‚СЊ РїРѕР·РёС†РёСЋ"
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

          </fieldset>
          <div className="paper-utility-stack" aria-label="PAPER utility controls">
            <button
              className="paper-position-list-button"
              type="button"
              aria-label="Открытые позиции"
              title="Открытые позиции"
              onClick={() => setOpenPositionsVisible(true)}
            >
              <span /><span /><span />
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

          <fieldset className="paper-mutation-boundary" disabled={!mutationsAllowed && !liveMarketAllowed}>
          <div className="paper-protection-stack">
            <TradingControlButton
              className="paper-stop-button"
              disabled={!mutationsAllowed}
              type="button"
              aria-pressed={stopActive}
              onTap={() => {
                const result = onStopTap();
                if (result === "not-improved") setExecutionStatus("STOP unchanged: protection would not improve");
              }}
              onHoldStart={onStopHold}
              holdMs={500}
            >
              {stopActive ? <span className="paper-stop-active-dot" aria-hidden="true" /> : null}
              STOP
            </TradingControlButton>
            {stopSettingsOpen && paperState?.ok && paperState.position_side !== "Flat" ? (
              <StopSettings
                side={paperState.position_side}
                referencePrice={stopReferencePrice}
                tickSize={authoritativeTickSize}
                presetPercent={stopPresetPercent}
                onPresetChange={onStopPresetChange}
                onApply={onStopSettingsApply}
                onClose={onStopSettingsClose}
              />
            ) : null}
            <TradingControlButton
              className="paper-take-button"
              disabled={!mutationsAllowed}
              type="button"
              aria-pressed={takeActive}
              onTap={onTakeTap}
              onHoldStart={onTakeHold}
              holdMs={500}
            >
              {takeActive ? <span className="paper-take-active-dot" aria-hidden="true" /> : null}
              TAKE
            </TradingControlButton>
            {takeSettingsOpen && paperState?.ok && paperState.position_side !== "Flat" ? (
              <StopSettings
                leg="TAKE"
                side={paperState.position_side}
                referencePrice={takeReferencePrice}
                tickSize={authoritativeTickSize}
                presetPercent={takePresetPercent}
                onPresetChange={onTakePresetChange}
                onApply={onTakeSettingsApply}
                onClose={onTakeSettingsClose}
              />
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
                        вњ“
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

          {openPositionsVisible && accountWorkspaceProjection?.provider === "PAPER" ? (
            <OpenPositionsOverlay
              activeSymbol={symbol}
              onClose={() => setOpenPositionsVisible(false)}
              onNavigate={(nextSymbol) => {
                setOpenPositionsVisible(false);
                onWorkspaceSymbolSelect?.(nextSymbol);
              }}
              runPaperMutation={runPaperMutation}
              applyPaperState={applyPaperState}
            />
          ) : null}
          {openPositionsVisible && accountWorkspaceProjection?.provider !== "PAPER" ? (
            <LiveAccountInventory
              activeAccountName={activeAccountLabel && activeAccountLabel.id === accountWorkspaceProjection?.account_id
                ? activeAccountLabel.name : ""}
              activeSymbol={symbol}
              onClose={() => setOpenPositionsVisible(false)}
              onNavigate={(nextSymbol) => {
                setOpenPositionsVisible(false);
                onWorkspaceSymbolSelect?.(nextSymbol);
              }}
              projection={accountWorkspaceProjection}
            />
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
          </fieldset>
        </div>
          <div className="paper-lower-actions-row">
            <fieldset className="paper-limits-shell" disabled={!mutationsAllowed && !liveLimitAllowed}>
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
                      Г—
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
                      Г—
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
                          Г—
                        </TradingControlButton>
                      </div>
                    ))}
                  </div>
                </section>
              ) : null}
            </fieldset>
            <div className="workspace-display-navigation" aria-label="Workspace account">
              <div className="mode-panel-account-control">
                <AccountMenu
                  open={accountOpen}
                  onToggle={onAccountToggle}
                  workspaceProjection={accountWorkspaceProjection}
                  onActiveAccountChange={setActiveAccountLabel}
                />
              </div>
            </div>
          </div>

          {liveConfirmation ? (
            <div className="paper-limit-popup-backdrop" role="presentation">
              <div className="paper-limit-popup" role="dialog" aria-label="Confirm LIVE Market order">
                <strong>Main Bybit / LIVE</strong>
                <p>{liveConfirmation.side.toUpperCase()} MARKET {liveConfirmation.symbol}</p>
                <p>{liveConfirmation.volume.amount} USDT В· slippage {liveConfirmation.slippage_value}%</p>
                <button type="button" disabled={liveConfirmationSubmitting} onClick={() => void confirmLiveMarket()}>
                  {liveConfirmationSubmitting ? "LIVE MARKET SUBMITTING" : "CONFIRM LIVE MARKET"}
                </button>
                <button type="button" onClick={() => setLiveConfirmation(null)}>CANCEL</button>
              </div>
            </div>
          ) : null}
        </div>
        </>
      ) : null}
    </section>
  );
}

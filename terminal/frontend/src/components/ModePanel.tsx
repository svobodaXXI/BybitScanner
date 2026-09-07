import { useEffect, useRef, useState, type Dispatch } from "react";
import {
  HANDLED_REASON_CODES,
  type MarketCommandRequest,
  type LiveMarketCommandRequest,
  type MarketSide,
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
import { PaperFullCloseSubmissionController } from "../orders/paperFullCloseSubmission";
import { LiveFullCloseSubmissionController } from "../orders/liveFullCloseSubmission";
import { OpenPositionsOverlay } from "./OpenPositionsOverlay";
import { AccountMenu } from "./AccountMenu";
import { LiveAccountInventory } from "./LiveAccountInventory";
import {
  accountWorkspaceStore,
  type AccountWorkspaceProjection,
} from "../accountWorkspace/accountWorkspaceStore";
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
  protectionPositionSide = "Flat",
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
  liveProtectionAllowed = false,
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
  onLimitDraftConfirm: (draftId?: string) => void | Promise<void>;
  onFastLimitHoldChange?: (
    intent: { side: MarketSide; volumeUsdt: string } | null,
  ) => void;
  selectedVolumes?: SelectedSideVolumes;
  onSelectedVolumeChange?: (side: MarketSide, value: string) => void;
  onLimitCancel?: (orderId: string) => Promise<{ status: string } | null>;
  onPositionSideChange: (side: PaperState["position_side"]) => void;
  onPositionAverageEntryChange?: (averageEntry: number | null) => void;
  protectionPositionSide?: PaperState["position_side"];
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
  liveProtectionAllowed?: boolean;
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
  const liveCancelPending = useRef<{ authorityKey: string; token: symbol } | null>(null);
  const cancelAuthority = useRef({ projection: accountWorkspaceProjection, allowed: liveLimitAllowed });
  cancelAuthority.current = { projection: accountWorkspaceProjection, allowed: liveLimitAllowed };
  const marketAuthority = useRef({ projection: accountWorkspaceProjection, allowed: liveMarketAllowed });
  marketAuthority.current = { projection: accountWorkspaceProjection, allowed: liveMarketAllowed };
  const liveMutationEnvelopeAllowed = liveMarketAllowed || liveLimitAllowed || liveProtectionAllowed;
  const liveFullCloseAllowed = liveMutationEnvelopeAllowed
    && accountWorkspaceProjection?.provider === "BYBIT"
    && accountWorkspaceProjection.environment === "MAINNET"
    && accountWorkspaceProjection.status === "READY"
    && accountWorkspaceProjection.read_only === false
    && accountWorkspaceProjection.capabilities?.full_close === true;
  const fullCloseAuthority = useRef({ projection: accountWorkspaceProjection, allowed: liveFullCloseAllowed });
  fullCloseAuthority.current = { projection: accountWorkspaceProjection, allowed: liveFullCloseAllowed };
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
  const limitDrafts =
    limitDraftState.drafts ??
    (limitDraftState.draft ? [limitDraftState.draft] : []);
  const popupLimitDrafts = limitDrafts.filter(
    (draft) => draft.origin === "limits-popup",
  );
  const previousPopupLimitDraftCount = useRef(popupLimitDrafts.length);
  const [liveConfirmation, setLiveConfirmation] = useState<LiveMarketCommandRequest | null>(null);
  const [liveConfirmationSubmitting, setLiveConfirmationSubmitting] = useState(false);
  const liveDispatchActionIdRef = useRef<string | null>(null);
  const paperFullCloseSubmissionController = useRef(new PaperFullCloseSubmissionController());
  const liveFullCloseSubmissionController = useRef(new LiveFullCloseSubmissionController());

  useEffect(() => {
    setLiveConfirmation(null);
    setLiveConfirmationSubmitting(false);
    liveDispatchActionIdRef.current = null;
  }, [
    accountWorkspaceProjection?.account_id,
    accountWorkspaceProjection?.session_generation,
    liveMarketAllowed,
  ]);

  useEffect(() => {
    paperFullCloseSubmissionController.current.clear();
    liveFullCloseSubmissionController.current.clear();
    setCloseConfirmOpen(false);
  }, [
    accountWorkspaceProjection?.account_id,
    accountWorkspaceProjection?.provider,
    accountWorkspaceProjection?.session_generation,
    liveFullCloseAllowed,
    mutationsAllowed,
  ]);

  useEffect(() => {
      if (paperState?.ok) {
        const engagedWv = Number(paperState.engaged_wv);
        const engagedNotional = Number(paperState.engaged_notional_usdt);
        setEngagedWorkingVolume(Number.isFinite(engagedWv) ? engagedWv.toFixed(1) : null);
        setEngagedNotionalUsdt(
          Number.isFinite(engagedNotional)
            ? String(Math.round(Math.max(0, engagedNotional)))
            : "0",
        );
        const normalizedPositionSide =
          paperState.position_side === "Long" || paperState.position_side === "Short"
            ? paperState.position_side
            : "Flat";
        setPositionSide(normalizedPositionSide);
        setPositionSymbol(paperState.symbol);
        onPositionSideChange(normalizedPositionSide);
        const averageEntry = Number(paperState.average_entry);
        const normalizedAverageEntry =
          paperState.average_entry !== null && Number.isFinite(averageEntry) && averageEntry > 0
            ? averageEntry
            : null;
        setPositionAverageEntry(normalizedAverageEntry);
        onPositionAverageEntryChange?.(normalizedAverageEntry);
        setOneWvUsdt(paperState.one_wv_usdt);
        setPositionQuantity(paperState.position_quantity);
      } else {
        const livePosition = accountWorkspaceProjection?.provider === "BYBIT"
          ? accountWorkspaceProjection.positions.find((candidate) =>
              candidate.symbol === symbol
              && (candidate.side === "Long" || candidate.side === "Short")
              && Number(candidate.size) > 0,
            ) ?? null
          : null;
        const liveSide = livePosition?.side === "Long" || livePosition?.side === "Short"
          ? livePosition.side
          : "Flat";
        const liveQuantity = livePosition && Number(livePosition.size) > 0
          ? String(livePosition.size)
          : "0";
        const liveAverage = Number(livePosition?.average_entry);
        const normalizedAverage = Number.isFinite(liveAverage) && liveAverage > 0 ? liveAverage : null;
        const mark = Number(livePosition?.mark_price);
        const quantity = Number(liveQuantity);
        const reference = Number.isFinite(mark) && mark > 0 ? mark : normalizedAverage ?? 0;
        const notional = Number.isFinite(quantity) && quantity > 0 && reference > 0
          ? quantity * reference
          : 0;
        const liveOneWv = accountWorkspaceProjection?.one_wv_usdt ?? "0";
        const liveOneWvNumber = Number(liveOneWv);
        setPositionSide(liveSide);
        setPositionSymbol(livePosition ? symbol : "");
        onPositionSideChange(liveSide);
        setPositionAverageEntry(normalizedAverage);
        onPositionAverageEntryChange?.(normalizedAverage);
        setPositionQuantity(liveQuantity);
        setEngagedNotionalUsdt(String(Math.round(notional)));
        setOneWvUsdt(liveOneWv);
        setEngagedWorkingVolume(
          liveSide !== "Flat" && Number.isFinite(liveOneWvNumber) && liveOneWvNumber > 0
            ? (notional / liveOneWvNumber).toFixed(1)
            : null,
        );
      }
  }, [
    accountWorkspaceProjection,
    onPositionAverageEntryChange,
    onPositionSideChange,
    paperState,
    symbol,
  ]);

  useEffect(() => {
    if (
      limitPresentationSide !== null &&
      previousPopupLimitDraftCount.current > 0 &&
      popupLimitDrafts.length === 0
    ) {
      setLimitPresentationSide(null);
    }
    previousPopupLimitDraftCount.current = popupLimitDrafts.length;
  }, [limitPresentationSide, popupLimitDrafts.length]);

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
    if (
      popupLimitDrafts.some(
        (draft) =>
          draft.status === "submitting" || draft.status === "ambiguous",
      )
    ) {
      return;
    }

    setLimitPresentationSide(null);
    for (const draft of popupLimitDrafts) {
      dispatchLimitDraft({ type: "dismiss", draftId: draft.draftId });
    }
  };

  useEffect(() => {
    if (limitPresentationSide === null) return;

    const dismissFromOutside = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      if (target.closest(".paper-limit-popup")) return;
      if (target.closest('[data-popup-limit-draft="true"]')) return;
      dismissLimitPresentation();
    };

    document.addEventListener("pointerdown", dismissFromOutside, true);
    return () => {
      document.removeEventListener("pointerdown", dismissFromOutside, true);
    };
  }, [limitPresentationSide, popupLimitDrafts]);

  useEffect(() => {
    if (limitsInventorySide === null) return;

    const dismissInventoryFromOutside = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      if (target.closest(".paper-limits-side-inventory")) return;
      setLimitsInventorySide(null);
    };

    document.addEventListener("pointerdown", dismissInventoryFromOutside, true);
    return () => {
      document.removeEventListener("pointerdown", dismissInventoryFromOutside, true);
    };
  }, [limitsInventorySide]);

  const dismissSideCancelConfirmation = () => {
    setCancelLimitSideConfirm(null);
  };

  const openLimitPresentation = (side: MarketSide) => {
    setCancelLimitSideConfirm(null);
    setLimitsInventorySide(null);

    const lockedPopupDraft = popupLimitDrafts.find(
      (draft) =>
        draft.status === "submitting" || draft.status === "ambiguous",
    );
    if (lockedPopupDraft) {
      setLimitPresentationSide(lockedPopupDraft.side);
      dispatchLimitDraft({
        type: "select",
        draftId: lockedPopupDraft.draftId,
      });
      return;
    }

    for (const draft of popupLimitDrafts) {
      dispatchLimitDraft({ type: "dismiss", draftId: draft.draftId });
    }

    setLimitPresentationSide(side);
    const price = side === "Buy" ? longDefaultPrice : shortDefaultPrice;
    if (price === null) {
      setLimitPresentationSide(null);
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
            ? "Сумма слишком мала для шага объёма"
            : `${side.toUpperCase()} отменено`,
      );

      } catch {
        setExecutionStatus(`${side.toUpperCase()} отменено`);
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
    const current = marketAuthority.current;
    const projection = current.projection;
    if (
      !current.allowed
      || projection?.provider !== "BYBIT"
      || projection.account_id !== action.account_id
      || projection.session_generation !== action.session_generation
    ) {
      setLiveConfirmation(null);
      setLiveConfirmationSubmitting(false);
      setExecutionStatus("LIVE Market unavailable: account authority changed");
      return;
    }
    liveDispatchActionIdRef.current = action.client_action_id;
    setLiveConfirmationSubmitting(true);
    const result = await executeLiveMarketCommand(action, {
      currentAuthority: () => {
        const latest = marketAuthority.current;
        const currentProjection = latest.projection;
        return latest.allowed && currentProjection?.provider === "BYBIT"
          ? {
              accountId: currentProjection.account_id,
              sessionGeneration: currentProjection.session_generation,
            }
          : null;
      },
    });
    if (!result) {
      setLiveConfirmation(null);
      setLiveConfirmationSubmitting(false);
      setExecutionStatus("LIVE Market authority changed — do not retry");
      return;
    }
    setLiveConfirmation(null);
    setLiveConfirmationSubmitting(false);
    setExecutionStatus(result.status === "unknown"
      ? "LIVE result ambiguous — reconciling; do not retry"
      : result.status === "accepted_pending" ? "LIVE accepted — awaiting REST evidence"
      : `LIVE ${result.status}: ${result.reason_code}`);
  };

  const submitFullClose = async () => {
    if (liveFullCloseAllowed) {
      try {
        const result = await liveFullCloseSubmissionController.current.submit(
          { symbol },
          {
            currentAuthority: () => {
              const current = fullCloseAuthority.current;
              const projection = current.projection;
              return current.allowed && projection?.provider === "BYBIT"
                ? {
                    accountId: projection.account_id,
                    sessionGeneration: projection.session_generation,
                  }
                : null;
            },
            createClientActionId: () =>
              globalThis.crypto?.randomUUID?.() ?? `live-full-close-${Date.now()}`,
            refreshActiveLive: accountWorkspaceStore.refreshActiveLive,
          },
        );
        setExecutionStatus(
          !result || result.status === "unknown" || result.reconciliation_required
            ? "LIVE Full Close ambiguous — reconciling; do not retry"
            : result.status === "accepted_pending"
              ? "LIVE Full Close accepted — awaiting REST evidence"
              : result.status === "completed"
                ? "LIVE position closed"
                : `LIVE Full Close ${result.status}: ${result.reason_code}`,
        );
      } catch {
        setExecutionStatus("LIVE Full Close transport uncertain — reconciling; do not retry");
        await accountWorkspaceStore.refreshActiveLive();
      }
      return;
    }
    if (!mutationsAllowed) {
      setExecutionStatus("Full Close unavailable: account authority changed");
      return;
    }
    try {
      const result = await paperFullCloseSubmissionController.current.submit(
        { symbol },
        {
          applyPaperState,
          runMutation: runPaperMutation,
        },
      );
      setExecutionStatus(
        result.status === "completed"
          ? "PAPER позиция закрыта"
          : "Закрытие отменено",
      );
    } catch {
      setExecutionStatus("Закрытие отменено");
      await refreshPaperState();
    }
  };

  const cancelLimit = async (orderId: string) => {
    if (!onLimitCancel) return;
    try {
      const result = await onLimitCancel(orderId);
      setExecutionStatus(result?.status === "completed" || result?.status === "accepted_pending"
        ? `${mutationsAllowed ? "PAPER" : "LIVE"} LIMIT cancellation submitted`
        : "LIMIT cancellation failed or requires reconciliation");
    } catch {
      setExecutionStatus("Отмена LIMIT не выполнена");
    }
  };

  const cancelLimits = async (orders: PaperLimitOrder[]) => {
    if (orders.length === 0 || !onLimitCancel) return;

    if (accountWorkspaceProjection?.provider === "BYBIT" || liveLimitAllowed || !mutationsAllowed) {
      const captured = accountWorkspaceProjection;
      const authorityKey = captured?.provider === "BYBIT"
        ? `${captured.account_id}:${captured.session_generation}`
        : null;
      const authorityMatches = () => {
        const current = cancelAuthority.current;
        return captured?.provider === "BYBIT" && current.allowed
          && current.projection?.account_id === captured.account_id
          && current.projection?.session_generation === captured.session_generation;
      };
      const pending = liveCancelPending.current;
      if (!authorityMatches() || !authorityKey || pending?.authorityKey === authorityKey) return;
      const token = Symbol("live-bulk-cancel");
      liveCancelPending.current = { authorityKey, token };
      try {
        let submitted = 0;
        for (const order of orders) {
          if (!authorityMatches()) return;
          const result = await onLimitCancel(order.order_id);
          if (!authorityMatches()) return;
          if (result?.status !== "completed" && result?.status !== "accepted_pending") {
            setExecutionStatus("LIVE LIMIT cancellation failed or requires reconciliation");
            return;
          }
          submitted += 1;
        }
        setExecutionStatus(`LIVE LIMIT cancellations submitted: ${submitted}/${orders.length}`);
      } catch {
        if (authorityMatches()) setExecutionStatus("LIVE LIMIT cancellation failed or requires reconciliation");
      } finally {
        if (liveCancelPending.current?.token === token) {
          liveCancelPending.current = null;
        }
      }
      return;
    }

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
          className={`paper-market-actions${mutationsAllowed || liveMarketAllowed || liveLimitAllowed || liveProtectionAllowed || liveFullCloseAllowed ? "" : " is-read-only"}`}
        >
          <fieldset className="paper-mutation-boundary">
          <div className="paper-trade-side-group" aria-label="PAPER trade sides">
            <div className="paper-market-side paper-market-buy-side">
              <TradingControlButton
                onTap={() => beginMarket("Buy", selectedVolumes.Buy)}
                onHoldStart={() => {
                  if (mutationsAllowed || liveLimitAllowed) {
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
                  if (mutationsAllowed || liveLimitAllowed) {
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
                    startHoldTooltip(`1 РО = ${oneWvUsdt} USDT`)
                  }
                  onPointerUp={stopHoldTooltip}
                  onPointerCancel={stopHoldTooltip}
                  onPointerLeave={stopHoldTooltip}
                  onTouchStart={() =>
                    startHoldTooltip(`1 РО = ${oneWvUsdt} USDT`)
                  }
                  onTouchEnd={stopHoldTooltip}
                  onTouchCancel={stopHoldTooltip}
                  onContextMenu={(event) => event.preventDefault()}
                >
                  {"⚔️"} {engagedWorkingVolume ?? "—"}
                </span>

                {positionSide !== "Flat" ? (
                  <TradingControlButton
                    className={`paper-wv-close ${positionSide.toLowerCase()}`}
                    disabled={!mutationsAllowed && !liveFullCloseAllowed}
                    onTap={() => setCloseConfirmOpen(true)}
                    type="button"
                    aria-label={"Закрыть позицию"}
                    title={"Закрыть позицию"}
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

          <fieldset className="paper-mutation-boundary">
          <div className="paper-protection-stack">
            <TradingControlButton
              className="paper-stop-button"
              disabled={!mutationsAllowed && !liveProtectionAllowed}
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
            {stopSettingsOpen && protectionPositionSide !== "Flat" ? (
              <StopSettings
                side={protectionPositionSide}
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
              disabled={!mutationsAllowed && !liveProtectionAllowed}
              type="button"
              aria-pressed={takeActive}
              onTap={onTakeTap}
              onHoldStart={onTakeHold}
              holdMs={500}
            >
              {takeActive ? <span className="paper-take-active-dot" aria-hidden="true" /> : null}
              TAKE
            </TradingControlButton>
            {takeSettingsOpen && protectionPositionSide !== "Flat" ? (
              <StopSettings
                leg="TAKE"
                side={protectionPositionSide}
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
            >
              <section
                className="paper-limit-popup"
                role="dialog"
                aria-label={`New ${limitPresentationSide} Limit`}
                onPointerDown={shieldPopupPointerInteraction}
                onClick={shieldPopupClickInteraction}
              >
                {(() => {
                  const side = limitPresentationSide;
                  const label = side === "Buy" ? "LONG" : "SHORT";
                  const draft =
                    popupLimitDrafts.find(
                      (candidate) => candidate.side === side,
                    ) ?? null;
                  const selected = draft !== null;
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
                        onTap={() => {
                          if (draft) {
                            void onLimitDraftConfirm(draft.draftId);
                          }
                        }}
                      >
                        {draft?.status === "submitting"
                          ? "..."
                          : "✓"}
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
                aria-label={"Закрыть позицию?"}
                onPointerDown={shieldPopupPointerInteraction}
                onClick={shieldPopupClickInteraction}
              >
                <strong>{"Закрыть позицию?"}</strong>

                <span>
                  {positionSide === "Long"
                    ? "LONG"
                    : positionSide === "Short"
                      ? "SHORT"
                      : "FLAT"}{" "}
                  {"·"} {engagedNotionalUsdt} USDT
                </span>

                <div className="paper-close-confirm-actions">
                  <TradingControlButton
                    type="button"
                    className="paper-close-confirm-accept"
                    disabled={
                      (!mutationsAllowed && !liveFullCloseAllowed)
                      || pendingActions.has("FULL_CLOSE")
                    }
                    onTap={async () => {
                      await submitFullClose();
                      setCloseConfirmOpen(false);
                    }}
                  >
                    {"ЗАКРЫТЬ ПОЗИЦИЮ"}
                  </TradingControlButton>

                  <TradingControlButton
                    type="button"
                    className="paper-close-confirm-cancel"
                    disabled={pendingActions.has("FULL_CLOSE")}
                    onTap={() => setCloseConfirmOpen(false)}
                  >
                    {"НЕ ЗАКРЫВАТЬ"}
                  </TradingControlButton>
                </div>
              </section>
            </div>
          ) : null}
          </fieldset>
        </div>
          <div className="paper-lower-actions-row">
            <fieldset className="paper-limits-shell">
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
                      {"×"}
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
                      aria-label={`Close ${limitsInventorySide} Limit orders for ${symbol}`}
                      onTap={() => setLimitsInventorySide(null)}
                    >
                      {"×"}
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
                          {"×"}
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
                <p>{liveConfirmation.volume.amount} USDT · slippage {liveConfirmation.slippage_value}%</p>
                <button type="button" disabled={liveConfirmationSubmitting || !liveMarketAllowed} onClick={() => void confirmLiveMarket()}>
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

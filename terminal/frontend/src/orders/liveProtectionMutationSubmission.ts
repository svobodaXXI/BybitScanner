import type { LiveAuthority } from "./liveLimitCommand";
import {
  executeLiveProtection,
  type LiveProtectionLeg,
  type LiveProtectionOperation,
  type LiveProtectionResponse,
} from "./liveProtectionCommand";
import { ProtectionCommandLifecycleController } from "./protectionCommandLifecycle";

export type LiveProtectionMutationIntent = {
  leg: LiveProtectionLeg;
  operation: LiveProtectionOperation;
  symbol: string;
  triggerPrice?: string;
  currentStopLoss: string | null;
  currentTakeProfit: string | null;
};

export type LiveProtectionMutationDependencies = {
  currentAuthority: () => LiveAuthority | null;
  createClientActionId: () => string;
  refreshActiveLive: () => Promise<unknown>;
  fetcher?: typeof fetch;
};

const attemptKey = (intent: LiveProtectionMutationIntent) => intent.operation === "DELETE"
  ? `${intent.leg}:${intent.operation}:${intent.symbol}`
  : `${intent.leg}:${intent.operation}:${intent.symbol}:${intent.triggerPrice ?? ""}`;

const disposition = (
  result: LiveProtectionResponse | null,
): "release" | "retain" => {
  if (result === null) return "retain";
  if (result.status === "unknown" || result.reconciliation_required) return "retain";
  return "release";
};

function targetProtection(intent: LiveProtectionMutationIntent) {
  if (intent.operation !== "DELETE" && !intent.triggerPrice) {
    throw new Error("protection_trigger_price_required");
  }

  let stopLoss = intent.currentStopLoss;
  let takeProfit = intent.currentTakeProfit;
  const nextPrice = intent.operation === "DELETE" ? null : intent.triggerPrice!;

  if (intent.leg === "STOP") stopLoss = nextPrice;
  else takeProfit = nextPrice;

  return { stopLoss, takeProfit };
}

/** LIVE adapter over the provider-neutral STOP/TAKE ownership lifecycle. */
export class LiveProtectionMutationController {
  private readonly lifecycle =
    new ProtectionCommandLifecycleController<LiveProtectionResponse | null>();

  submit(
    intent: LiveProtectionMutationIntent,
    dependencies: LiveProtectionMutationDependencies,
  ): Promise<LiveProtectionResponse | null> {
    return this.lifecycle.submit(attemptKey(intent), {
      startAttempt: () => {
        const authority = dependencies.currentAuthority();
        if (!authority) throw new Error("stale_live_authority");
        const clientActionId = dependencies.createClientActionId();
        const target = targetProtection(intent);
        return executeLiveProtection(
          intent.leg,
          intent.operation,
          {
            client_action_id: clientActionId,
            account_id: authority.accountId,
            session_generation: authority.sessionGeneration,
            symbol: intent.symbol,
            take_profit: target.takeProfit,
            stop_loss: target.stopLoss,
            tp_trigger_by: "MarkPrice",
            sl_trigger_by: "MarkPrice",
          },
          dependencies.currentAuthority,
          dependencies.fetcher,
        ).then(async (result) => {
          if (result?.status === "accepted_pending" || result?.status === "completed") {
            await dependencies.refreshActiveLive();
          }
          return result;
        });
      },
      classifyResult: disposition,
      // A rejected LIVE transport/refresh promise is ambiguous. Retain the
      // owned attempt until reconciliation or an authority change clears it.
      releaseOnError: false,
    });
  }

  clear(): void {
    this.lifecycle.clear();
  }
}

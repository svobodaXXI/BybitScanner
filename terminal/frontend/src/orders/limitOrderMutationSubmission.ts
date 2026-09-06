import type {
  PaperLimitAmendRequest,
  PaperLimitCancelRequest,
  PaperLimitMutationResponse,
  PaperState,
} from "../contracts/trading";
import {
  executeLiveLimitAmend,
  executeLiveLimitCancel,
  type LiveAuthority,
  type LiveLimitResponse,
} from "./liveLimitCommand";
import {
  executePaperLimitAmend,
  executePaperLimitCancel,
} from "./paperLimitCommand";
import {
  LimitOrderMutationController,
  type LimitOrderMutationAttempt,
} from "./limitOrderMutation";

export type PaperLimitOrderMutationDependencies = {
  createClientActionId: () => string;
  applyPaperState: (state: PaperState) => boolean;
  runMutation: <T>(key: string, operation: () => Promise<T>) => Promise<T>;
  refreshPaper: () => Promise<unknown>;
  fetcher?: typeof fetch;
};

export type LiveLimitOrderMutationDependencies = {
  currentAuthority: () => LiveAuthority | null;
  createClientActionId: () => string;
  refreshActiveLive: () => Promise<unknown>;
  fetcher?: typeof fetch;
};

export type ExistingLimitAmendIntent = {
  symbol: string;
  orderId: string;
  price: string;
};

export type ExistingLimitCancelIntent = {
  symbol: string;
  orderId: string;
};

/** PAPER adapter for the shared existing-Limit mutation ownership lifecycle. */
export class PaperLimitOrderMutationController {
  private readonly common = new LimitOrderMutationController<PaperLimitMutationResponse>();

  amend(
    intent: ExistingLimitAmendIntent,
    dependencies: PaperLimitOrderMutationDependencies,
  ): LimitOrderMutationAttempt<PaperLimitMutationResponse> {
    return this.common.submit("AMEND_LIMIT", intent.orderId, {
      startAttempt: () => {
        const clientActionId = dependencies.createClientActionId();
        const request: PaperLimitAmendRequest = {
          client_action_id: clientActionId,
          symbol: intent.symbol,
          order_id: intent.orderId,
          limit_price: intent.price,
        };
        const promise = dependencies.runMutation(
          `AMEND_LIMIT:${intent.orderId}`,
          async () => {
            try {
              const result = await executePaperLimitAmend(request, {
                applyPaperState: dependencies.applyPaperState,
                fetcher: dependencies.fetcher,
              });
              if (result.status !== "completed") throw new Error(result.reason_code);
              return result;
            } catch (error) {
              await dependencies.refreshPaper();
              throw error;
            }
          },
        );
        return { clientActionId, promise };
      },
      classifyResult: () => "release",
      // PAPER reconciles immediately after transport/application failure, so
      // preserve its existing release-after-refresh behavior.
      classifyError: () => "release",
    });
  }

  cancel(
    intent: ExistingLimitCancelIntent,
    dependencies: PaperLimitOrderMutationDependencies,
  ): LimitOrderMutationAttempt<PaperLimitMutationResponse> {
    return this.common.submit("CANCEL_LIMIT", intent.orderId, {
      startAttempt: () => {
        const clientActionId = dependencies.createClientActionId();
        const request: PaperLimitCancelRequest = {
          client_action_id: clientActionId,
          symbol: intent.symbol,
          order_id: intent.orderId,
        };
        const promise = dependencies.runMutation(
          `CANCEL_LIMIT:${intent.orderId}`,
          async () => {
            try {
              return await executePaperLimitCancel(request, {
                applyPaperState: dependencies.applyPaperState,
                fetcher: dependencies.fetcher,
              });
            } catch (error) {
              await dependencies.refreshPaper();
              throw error;
            }
          },
        );
        return { clientActionId, promise };
      },
      classifyResult: () => "release",
      classifyError: () => "release",
    });
  }

  clear() {
    this.common.clear();
  }
}

function liveResultDisposition(
  result: LiveLimitResponse | null,
): "release" | "retain" {
  if (result === null) return "retain";
  if (result.status === "unknown" || result.reconciliation_required) return "retain";
  return "release";
}

/** LIVE adapter retaining authority, reconciliation and no-blind-retry rules. */
export class LiveLimitOrderMutationController {
  private readonly common = new LimitOrderMutationController<LiveLimitResponse | null>();

  amend(
    intent: ExistingLimitAmendIntent,
    dependencies: LiveLimitOrderMutationDependencies,
  ): LimitOrderMutationAttempt<LiveLimitResponse | null> {
    return this.submitLive("AMEND_LIMIT", intent.orderId, dependencies, (authority, clientActionId) =>
      executeLiveLimitAmend({
        client_action_id: clientActionId,
        account_id: authority.accountId,
        session_generation: authority.sessionGeneration,
        symbol: intent.symbol,
        order_id: intent.orderId,
        limit_price: intent.price,
      }, dependencies.currentAuthority, dependencies.fetcher),
    );
  }

  cancel(
    intent: ExistingLimitCancelIntent,
    dependencies: LiveLimitOrderMutationDependencies,
  ): LimitOrderMutationAttempt<LiveLimitResponse | null> {
    return this.submitLive("CANCEL_LIMIT", intent.orderId, dependencies, (authority, clientActionId) =>
      executeLiveLimitCancel({
        client_action_id: clientActionId,
        account_id: authority.accountId,
        session_generation: authority.sessionGeneration,
        symbol: intent.symbol,
        order_id: intent.orderId,
      }, dependencies.currentAuthority, dependencies.fetcher),
    );
  }

  clear() {
    this.common.clear();
  }

  private submitLive(
    kind: "AMEND_LIMIT" | "CANCEL_LIMIT",
    orderId: string,
    dependencies: LiveLimitOrderMutationDependencies,
    execute: (
      authority: LiveAuthority,
      clientActionId: string,
    ) => Promise<LiveLimitResponse | null>,
  ) {
    return this.common.submit(kind, orderId, {
      startAttempt: () => {
        const authority = dependencies.currentAuthority();
        if (!authority) throw new Error("stale_live_authority");
        const clientActionId = dependencies.createClientActionId();
        const promise = execute(authority, clientActionId).then(async (result) => {
          if (result?.status === "accepted_pending" || result?.status === "completed") {
            await dependencies.refreshActiveLive();
          }
          return result;
        });
        return { clientActionId, promise };
      },
      classifyResult: liveResultDisposition,
      // A rejected LIVE transport/refresh promise is ambiguous from the UI's
      // perspective. Keep ownership latched until authoritative reconciliation
      // or an account/session invalidation clears it.
      classifyError: () => "retain",
    });
  }
}

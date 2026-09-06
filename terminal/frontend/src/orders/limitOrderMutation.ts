export type LimitOrderMutationKind = "AMEND_LIMIT" | "CANCEL_LIMIT";

export type LimitOrderMutationAttempt<T> = {
  clientActionId: string;
  promise: Promise<T>;
};

export type LimitOrderMutationDisposition = "release" | "retain";

export type LimitOrderMutationDependencies<T> = {
  startAttempt: () => LimitOrderMutationAttempt<T>;
  classifyResult: (result: T) => LimitOrderMutationDisposition;
  classifyError: (error: unknown) => LimitOrderMutationDisposition;
};

/**
 * Provider-neutral ownership for mutations against an existing Limit order.
 *
 * The controller owns one attempt per operation/order pair and only the
 * release-vs-retain lifecycle. Provider adapters own transport, authority,
 * command identity, reconciliation and authoritative projection refresh.
 *
 * Retained attempts are intentionally latched after ambiguous outcomes so the
 * same UI action cannot blindly redispatch a mutation whose exchange outcome
 * is unknown.
 */
export class LimitOrderMutationController<T> {
  private readonly attempts = new Map<string, LimitOrderMutationAttempt<T>>();

  submit(
    kind: LimitOrderMutationKind,
    orderId: string,
    dependencies: LimitOrderMutationDependencies<T>,
  ): LimitOrderMutationAttempt<T> {
    const attemptKey = `${kind}:${orderId}`;
    const existing = this.attempts.get(attemptKey);
    if (existing) return existing;

    // Provider preflight may fail synchronously. Do not record an attempt until
    // the adapter has captured valid authority/identity and actually owns a
    // transport promise.
    const attempt = dependencies.startAttempt();
    this.attempts.set(attemptKey, attempt);

    const execution = attempt.promise;
    attempt.promise = execution.then(
      (result) => {
        if (dependencies.classifyResult(result) === "release") {
          this.attempts.delete(attemptKey);
        }
        return result;
      },
      (error: unknown) => {
        if (dependencies.classifyError(error) === "release") {
          this.attempts.delete(attemptKey);
        }
        throw error;
      },
    );

    return attempt;
  }

  clear() {
    this.attempts.clear();
  }
}

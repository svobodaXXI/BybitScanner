export type MarketCommandAttemptDisposition = "release" | "retain";

export type MarketCommandLifecycleDependencies<T> = {
  startAttempt: () => Promise<T>;
  classifyResult: (result: T) => MarketCommandAttemptDisposition;
  releaseOnError: boolean;
};

/**
 * Provider-neutral ownership for one MARKET command attempt.
 *
 * The controller deliberately knows nothing about PAPER/LIVE transport,
 * account authority, reconciliation, state projection, or response shapes.
 * It only guarantees one in-flight/retained attempt per durable
 * client_action_id and race-safe release semantics.
 */
export class MarketCommandLifecycleController<T> {
  private readonly attempts = new Map<string, Promise<T>>();

  submit(
    clientActionId: string,
    dependencies: MarketCommandLifecycleDependencies<T>,
  ): Promise<T> {
    const existing = this.attempts.get(clientActionId);
    if (existing) return existing;

    const started = dependencies.startAttempt();
    let owned: Promise<T>;

    owned = started.then(
      (result) => {
        if (
          dependencies.classifyResult(result) === "release"
          && this.attempts.get(clientActionId) === owned
        ) {
          this.attempts.delete(clientActionId);
        }
        return result;
      },
      (error: unknown) => {
        if (
          dependencies.releaseOnError
          && this.attempts.get(clientActionId) === owned
        ) {
          this.attempts.delete(clientActionId);
        }
        throw error;
      },
    );

    this.attempts.set(clientActionId, owned);
    return owned;
  }

  clear(): void {
    this.attempts.clear();
  }
}

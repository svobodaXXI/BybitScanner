export type ProtectionAttemptDisposition = "release" | "retain";

export type ProtectionAttemptDependencies<T> = {
  startAttempt: () => Promise<T>;
  classifyResult: (result: T) => ProtectionAttemptDisposition;
  releaseOnError: boolean;
};

/**
 * Provider-neutral ownership for one STOP/TAKE mutation attempt.
 *
 * attemptKey is semantic rather than transport-specific so repeated UI gestures
 * for the same leg/operation/symbol/price reuse one in-flight attempt even if a
 * caller has already allocated another client_action_id. The first dispatched
 * request therefore remains the durable identity for that attempt.
 */
export class ProtectionCommandLifecycleController<T> {
  private readonly attempts = new Map<string, Promise<T>>();

  submit(
    attemptKey: string,
    dependencies: ProtectionAttemptDependencies<T>,
  ): Promise<T> {
    const existing = this.attempts.get(attemptKey);
    if (existing) return existing;

    const started = dependencies.startAttempt();
    let owned: Promise<T>;

    owned = started.then(
      (result) => {
        if (
          dependencies.classifyResult(result) === "release"
          && this.attempts.get(attemptKey) === owned
        ) {
          this.attempts.delete(attemptKey);
        }
        return result;
      },
      (error: unknown) => {
        if (
          dependencies.releaseOnError
          && this.attempts.get(attemptKey) === owned
        ) {
          this.attempts.delete(attemptKey);
        }
        throw error;
      },
    );

    this.attempts.set(attemptKey, owned);
    return owned;
  }

  clear(): void {
    this.attempts.clear();
  }
}

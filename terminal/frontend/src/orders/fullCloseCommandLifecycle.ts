export type FullCloseAttemptDisposition = "release" | "retain";

export type FullCloseLifecycleDependencies<T> = {
  startAttempt: () => Promise<T>;
  classifyResult: (result: T) => FullCloseAttemptDisposition;
  releaseOnError: boolean;
};

/**
 * Provider-neutral ownership for one FULL_CLOSE attempt.
 *
 * The semantic attempt key is independent of transport identity so repeated UI
 * gestures for the same close action reuse the first owned request and its
 * durable client_action_id. clear() is race-safe because late completion only
 * releases the Promise that still owns the key.
 */
export class FullCloseCommandLifecycleController<T> {
  private readonly attempts = new Map<string, Promise<T>>();

  submit(
    attemptKey: string,
    dependencies: FullCloseLifecycleDependencies<T>,
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

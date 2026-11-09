/*
 * Connection state the shell reads. It holds the time of the last answer, whether calls are
 * failing and how many failed in a row. A tiny external store, read through useSyncExternalStore.
 */
export interface ConnectionState {
  /** Epoch milliseconds of the last answer from the server, null before the first one. */
  lastAnswerAt: number | null;
  /** True while calls fail. */
  retrying: boolean;
  /** Calls in a row that got no answer. */
  failures: number;
}

export interface Connection {
  getState: () => ConnectionState;
  subscribe: (listener: () => void) => () => void;
  recordAnswer: (at: number) => void;
  recordFailure: () => number;
  reset: () => void;
}

const INITIAL: ConnectionState = { lastAnswerAt: null, retrying: false, failures: 0 };

export function createConnection(): Connection {
  let state = INITIAL;
  const listeners = new Set<() => void>();

  function set(next: ConnectionState): void {
    state = next;
    for (const listener of listeners) listener();
  }

  return {
    getState: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    recordAnswer(at) {
      set({ lastAnswerAt: at, retrying: false, failures: 0 });
    },
    recordFailure() {
      const failures = state.failures + 1;
      set({ ...state, retrying: true, failures });
      return failures;
    },
    reset() {
      set(INITIAL);
    },
  };
}

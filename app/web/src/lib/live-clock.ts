/*
 * The page clock for Live. The server's clock may be fixed, replayed or real, so the page keeps an
 * offset to the `server_time` of each answer and moves "Now" once a second between answers. A new
 * answer may land behind the shown time, and Now never steps back more than 2 seconds when it does
 * (the old page used the same rule). While Pause is on the clock holds still.
 *
 * It is a small external store, read with useSyncExternalStore, so a tick is not a state update in
 * an effect. The interval runs only while something is subscribed and the clock is not paused.
 */
import { useEffect, useState, useSyncExternalStore } from "react";

export const TICK_MS = 1_000;
export const STEP_BACK_MS = 2_000;

export interface PageClock {
  /** A new answer: the server's time and the local time it arrived at. Ignored while paused. */
  observe: (serverMs: number, localMs: number) => void;
  /** Holds the shown time still, or lets it run again. */
  setPaused: (paused: boolean) => void;
  /** Now in epoch milliseconds, or null before the first answer. */
  getSnapshot: () => number | null;
  subscribe: (listener: () => void) => () => void;
}

/** Never steps back more than STEP_BACK_MS from what is shown. */
export function stepClock(shown: number | null, raw: number): number {
  if (shown === null || raw >= shown) return raw;
  return Math.max(raw, shown - STEP_BACK_MS);
}

export function createPageClock(now: () => number = () => Date.now()): PageClock {
  let offset: number | null = null;
  let shown: number | null = null;
  let paused = false;
  let timer: ReturnType<typeof setInterval> | null = null;
  const listeners = new Set<() => void>();

  function emit(): void {
    for (const listener of listeners) listener();
  }

  function advance(): void {
    if (offset === null || paused) return;
    const next = stepClock(shown, now() + offset);
    if (next !== shown) {
      shown = next;
      emit();
    }
  }

  function sync(): void {
    const wanted = listeners.size > 0 && !paused && offset !== null;
    if (wanted && timer === null) {
      timer = setInterval(advance, TICK_MS);
    } else if (!wanted && timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  }

  return {
    observe(serverMs, localMs) {
      if (paused) return;
      offset = serverMs - localMs;
      shown = stepClock(shown, serverMs + (now() - localMs));
      sync();
      emit();
    },
    setPaused(next) {
      if (next === paused) return;
      paused = next;
      sync();
    },
    getSnapshot: () => shown,
    subscribe(listener) {
      listeners.add(listener);
      sync();
      return () => {
        listeners.delete(listener);
        sync();
      };
    },
  };
}

/**
 * The page clock for one Live feed. `answer` is the server time and arrival time of the latest
 * answer, changed once per poll. The result is Now in epoch milliseconds, null before an answer.
 */
export function usePageClock(
  answer: { serverMs: number; receivedAt: number } | null,
  paused: boolean,
): number | null {
  const [clock] = useState(createPageClock);
  const serverMs = answer?.serverMs;
  const receivedAt = answer?.receivedAt;
  useEffect(() => {
    if (serverMs !== undefined && receivedAt !== undefined) clock.observe(serverMs, receivedAt);
  }, [clock, serverMs, receivedAt]);
  useEffect(() => {
    clock.setPaused(paused);
  }, [clock, paused]);
  return useSyncExternalStore(clock.subscribe, clock.getSnapshot);
}

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createPageClock, stepClock, STEP_BACK_MS, usePageClock } from "@/lib/live-clock";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-09T10:00:00Z"));
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const base = Date.parse("2026-10-30T22:40:00Z");

describe("stepClock", () => {
  it("moves forward freely", () => {
    expect(stepClock(1000, 5000)).toBe(5000);
    expect(stepClock(null, 7)).toBe(7);
  });

  it("steps back no more than 2 seconds", () => {
    expect(stepClock(10_000, 9_000)).toBe(9_000);
    expect(stepClock(10_000, 1_000)).toBe(10_000 - STEP_BACK_MS);
  });
});

describe("createPageClock", () => {
  it("is null before the first answer", () => {
    expect(createPageClock().getSnapshot()).toBeNull();
  });

  it("takes the server time at an answer and advances once a second between answers", () => {
    const clock = createPageClock();
    const seen = vi.fn();
    const stop = clock.subscribe(seen);
    clock.observe(base, Date.now());
    expect(clock.getSnapshot()).toBe(base);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(clock.getSnapshot()).toBe(base + 1000);
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(clock.getSnapshot()).toBe(base + 3000);
    stop();
  });

  it("offsets to a new answer, and never steps back more than 2 seconds", () => {
    const clock = createPageClock();
    const stop = clock.subscribe(() => undefined);
    clock.observe(base, Date.now());
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(clock.getSnapshot()).toBe(base + 5000);
    // the server says it is only base + 1 s now
    clock.observe(base + 1000, Date.now());
    expect(clock.getSnapshot()).toBe(base + 5000 - STEP_BACK_MS);
    stop();
  });

  it("freezes while paused, ignores answers, and runs again on resume", () => {
    const clock = createPageClock();
    const stop = clock.subscribe(() => undefined);
    clock.observe(base, Date.now());
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    clock.setPaused(true);
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(clock.getSnapshot()).toBe(base + 1000);
    clock.observe(base + 60_000, Date.now());
    expect(clock.getSnapshot()).toBe(base + 1000);
    clock.setPaused(false);
    clock.observe(base + 12_000, Date.now());
    expect(clock.getSnapshot()).toBe(base + 12_000);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(clock.getSnapshot()).toBe(base + 13_000);
    stop();
  });

  it("holds no timer without a subscriber", () => {
    const clock = createPageClock();
    clock.observe(base, Date.now());
    expect(vi.getTimerCount()).toBe(0);
    const stop = clock.subscribe(() => undefined);
    expect(vi.getTimerCount()).toBe(1);
    stop();
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("usePageClock", () => {
  it("follows the answer and ticks", () => {
    interface Props {
      answer: { serverMs: number; receivedAt: number } | null;
      paused: boolean;
    }
    const initialProps: Props = { answer: null, paused: false };
    const { result, rerender } = renderHook(
      ({ answer, paused }: Props) => usePageClock(answer, paused),
      { initialProps },
    );
    expect(result.current).toBeNull();
    rerender({ answer: { serverMs: base, receivedAt: Date.now() }, paused: false });
    expect(result.current).toBe(base);
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(result.current).toBe(base + 2000);
    rerender({ answer: { serverMs: base, receivedAt: Date.now() - 2000 }, paused: true });
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(result.current).toBe(base + 2000);
  });
});

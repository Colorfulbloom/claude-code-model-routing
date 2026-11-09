import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Timeline } from "@/api/types";
import { MOVED_MS } from "@/lib/live-lanes";
import { useMovedRuns } from "@/lib/use-moved";
import { run, timeline } from "@/test/timelines";

const unlinked = (): Timeline =>
  timeline({
    runs: [
      run("main"),
      run("w", { dispatch_order: 1, parent_known: false, parent_state: "waiting" }),
    ],
  });
const linked = (): Timeline =>
  timeline({ runs: [run("main"), run("w", { dispatch_order: 1, parent_known: true })] });

interface Props {
  answer: Timeline | undefined;
  nowMs: number;
}

describe("useMovedRuns", () => {
  it("rings a run when its starter becomes known, then lets go after 2 seconds", () => {
    const first = unlinked();
    const { result, rerender } = renderHook(
      ({ answer, nowMs }: Props) => useMovedRuns(answer, nowMs),
      {
        initialProps: { answer: first, nowMs: 1000 },
      },
    );
    expect([...result.current]).toEqual([]);
    rerender({ answer: linked(), nowMs: 2000 });
    expect([...result.current]).toEqual(["w"]);
    rerender({ answer: linked(), nowMs: 2000 + MOVED_MS - 1 });
    expect([...result.current]).toEqual(["w"]);
    rerender({ answer: linked(), nowMs: 2000 + MOVED_MS });
    expect([...result.current]).toEqual([]);
  });

  it("does not ring a run that was linked from the first answer", () => {
    const { result } = renderHook(({ answer, nowMs }: Props) => useMovedRuns(answer, nowMs), {
      initialProps: { answer: linked(), nowMs: 1000 },
    });
    expect(result.current.size).toBe(0);
  });

  it("has nothing before the first answer", () => {
    const { result } = renderHook(({ answer, nowMs }: Props) => useMovedRuns(answer, nowMs), {
      initialProps: { answer: undefined, nowMs: 0 },
    });
    expect(result.current.size).toBe(0);
  });
});

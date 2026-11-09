/*
 * Which runs found their starter a moment ago. A foreground run has no link until it finishes
 * (fact V-7b16), so its row sits under the main session with a dashed line and then moves under its
 * real parent. The lane rings that row for about 2 seconds. The clock is the page clock, so the
 * ring clears on the tick after 2 seconds and never in a paused page.
 */
import { useState } from "react";
import type { Timeline } from "@/api/types";
import { MOVED_MS } from "@/lib/live-lanes";

interface Tracked {
  answer: Timeline | null;
  /** Run id to the page time its parent became known. */
  movedAt: ReadonlyMap<string, number>;
}

export function useMovedRuns(answer: Timeline | undefined, nowMs: number): ReadonlySet<string> {
  const [tracked, setTracked] = useState<Tracked>({ answer: null, movedAt: new Map() });
  if (answer !== undefined && answer !== tracked.answer) {
    const before = new Map(tracked.answer?.runs.map((run) => [run.run_id, run]) ?? []);
    const movedAt = new Map(tracked.movedAt);
    if (tracked.answer !== null) {
      for (const run of answer.runs) {
        const was = before.get(run.run_id);
        if (was !== undefined && !was.parent_known && run.parent_known)
          movedAt.set(run.run_id, nowMs);
      }
    }
    setTracked({ answer, movedAt });
  }
  const moved = new Set<string>();
  for (const [id, at] of tracked.movedAt) if (nowMs - at < MOVED_MS) moved.add(id);
  return moved;
}

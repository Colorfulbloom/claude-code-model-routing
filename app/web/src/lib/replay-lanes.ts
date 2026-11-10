/*
 * The lane rows of "Who worked when" at the replay line, from one timeline answer. It follows
 * live-lanes.ts, with three differences. Every value comes from timeline-at.ts at the line, so a run
 * that has not started reads "Not started yet" with no numbers, a run's starter is the one known at
 * the line (a run whose link has not arrived hangs under main with the unlinked badge), and a
 * parent with more than four children folds the runs that start later into one "starts later" row.
 * Finished runs fold as on Live, judged at the line.
 *
 * Tokens and cost on a row are the run's cumulative values at the last bucket that counts. Run
 * states, parents and rounds are exact at every minute. The component draws what it gets.
 */
import type { Timeline, TimelineRun } from "@/api/types";
import type {
  LaneFold,
  LaneRun,
  LaneSegment,
  TimelineLaneProps,
} from "@/components/TimelineLane/TimelineLane";
import { clockShort } from "@/lib/clock";
import { formatTokens } from "@/lib/format";
import { frac } from "@/lib/live-chart";
import type { AxisView } from "@/lib/live-chart";
import { laneCost, sumCosts } from "@/lib/live-cost";
import {
  DEPTH_CAP_DESKTOP,
  DEPTH_CAP_PHONE,
  FOLD_ABOVE,
  FOLD_QUIET_MS,
  rowId,
} from "@/lib/live-lanes";
import { modelFamily, modelLabel } from "@/lib/models";
import type { Replay } from "@/lib/replay";
import { effectiveStates } from "@/lib/replay-view";
import { runLabel } from "@/lib/run-label";
import { ACTIVE_MS, type RunAt, type RunStateAt } from "@/lib/timeline-at";
import { t, tn } from "@/strings/t";

const ms = (text: string): number => Date.parse(text);

export const foldId = (runId: string): string => `lane-fold-${runId}`;
export const laterId = (runId: string): string => `lane-later-${runId}`;

interface Node {
  run: TimelineRun;
  depth: number;
  children: Node[];
}

/**
 * Runs as a tree under main at the line. A started run hangs under the starter known at the line
 * (main when the link has not arrived). A run that has not started hangs under its real starter,
 * so a "starts later" row sits where the run will appear.
 */
function buildTreeAt(
  runs: readonly TimelineRun[],
  at: ReadonlyMap<string, RunAt>,
  states: ReadonlyMap<string, RunStateAt>,
): Node[] {
  const sorted = [...runs].sort((a, b) => a.dispatch_order - b.dispatch_order);
  const nodes = new Map<string, Node>(
    sorted.map((run) => [run.run_id, { run, depth: 0, children: [] }]),
  );
  const root = sorted.find((run) => run.parent === null && run.agent === null) ?? null;
  const rootId = root?.run_id ?? "";
  const top: Node[] = [];
  for (const run of sorted) {
    const node = nodes.get(run.run_id);
    if (node === undefined) continue;
    const started = states.get(run.run_id) !== "not_started";
    const starter = started ? (at.get(run.run_id)?.parent ?? run.parent) : run.parent;
    const parent =
      run.parent === null || starter === null
        ? undefined
        : nodes.get(starter === "main" ? rootId : starter);
    if (parent === undefined || parent === node) top.push(node);
    else parent.children.push(node);
  }
  const setDepth = (node: Node, depth: number, seen: Set<Node>): void => {
    if (seen.has(node)) return;
    seen.add(node);
    node.depth = depth;
    for (const child of node.children) setDepth(child, depth + 1, seen);
  };
  const seen = new Set<Node>();
  for (const node of top) setDepth(node, 0, seen);
  return top;
}

function* subtree(node: Node): Generator<Node> {
  yield node;
  for (const child of node.children) yield* subtree(child);
}

export interface ReplayLaneContext {
  axis: AxisView;
  /** True at 721px and up, where the indent cap is 3. */
  desktop: boolean;
  /** Fold ids (foldId and laterId) that are open. */
  expanded: ReadonlySet<string>;
  onToggle: (id: string) => void;
}

function segmentsOf(run: TimelineRun, axis: AxisView): LaneSegment[] {
  return run.segments.map((segment) => ({
    start: frac(axis, ms(segment.start)),
    end: frac(axis, ms(segment.end)),
  }));
}

function stateWord(state: RunStateAt): string {
  switch (state) {
    case "working":
      return t("rs_working");
    case "idle":
      return t("rs_idle");
    case "finished":
      return t("rs_finished");
    case "not_started":
      return t("c_not_started");
  }
}

/** When the run's last finished state began at or before T. It falls back to its last request. */
function finishedAtOrBefore(run: TimelineRun, at: number): number {
  const entry = [...run.states]
    .reverse()
    .find((state) => state.state === "finished" && ms(state.at) <= at);
  return Math.min(at, entry === undefined ? ms(run.last_request) : ms(entry.at));
}

/**
 * "Last request 3 min ago" at the line. The state history marks idle 60 seconds after the last
 * request, so that request sits one active window before the last idle mark at or before the
 * line. A round clamped to the line cannot say it, because a round runs on through its pauses.
 */
function idleLine(run: TimelineRun, at: RunAt, atMs: number): string {
  const idle = [...run.states].reverse().find((s) => s.state === "idle" && ms(s.at) <= atMs);
  const first = ms(run.first_request);
  const last =
    idle === undefined
      ? (at.rounds.at(-1)?.lastRequest ?? atMs)
      : Math.max(first, ms(idle.at) - ACTIVE_MS);
  const seconds = Math.max(0, Math.round((atMs - last) / 1000));
  return seconds < 60
    ? t("tl_last", { n: seconds })
    : t("tl_last_min", { n: Math.floor(seconds / 60) });
}

export type ReplayLane = Pick<TimelineLaneProps, "axis" | "items" | "note" | "label"> & {
  /** The line as a fraction of the axis, 0 to 1. */
  cut: number;
};

export function buildReplayLane(
  timeline: Timeline,
  replay: Replay,
  context: ReplayLaneContext,
): ReplayLane {
  const states = effectiveStates(timeline, replay);
  const at = new Map(replay.values.runs.map((entry) => [entry.runId, entry]));
  const atMs = replay.at;
  const sessionOver = replay.values.session === "ended";
  const cap = context.desktop ? DEPTH_CAP_DESKTOP : DEPTH_CAP_PHONE;
  const stateOf = (run: TimelineRun): RunStateAt => states.get(run.run_id) ?? "not_started";
  const tokensOf = (run: TimelineRun): number => {
    const cum = at.get(run.run_id)?.cum;
    return cum === undefined ? 0 : cum.tokens + cum.cache_read;
  };
  const costOf = (
    run: TimelineRun,
  ): { cost: number | null; unpriced: TimelineRun["unpriced"] } => ({
    cost: at.get(run.run_id)?.cum.cost ?? null,
    unpriced: run.unpriced,
  });
  const costPair = (run: TimelineRun): [number | null, TimelineRun["unpriced"]] => {
    const { cost, unpriced } = costOf(run);
    return [cost, unpriced];
  };

  function laneRun(node: Node, parent: Node | null): LaneRun {
    const { run } = node;
    const state = stateOf(run);
    const here = at.get(run.run_id);
    const notStarted = state === "not_started";
    const rounds = run.rounds
      .filter((round) => round.n > 1)
      .map((round) => ({
        at: frac(context.axis, ms(round.at)),
        label: t("tl_round", { n: round.n }),
      }));
    // On an ended session no starter can still arrive, so a waiting run reads as never found.
    const parentState =
      here?.parentState === "waiting" && sessionOver ? "unknown" : here?.parentState;
    const unlinked =
      notStarted || here === undefined
        ? null
        : parentState === "waiting"
          ? { kind: "may" as const, label: t("tl_unl_may") }
          : parentState === "unknown"
            ? { kind: "never" as const, label: t("tl_unl_never") }
            : null;
    let ageLine = "";
    if (state === "working") ageLine = t("sr_since", { time: clockShort(ms(run.first_request)) });
    else if (state === "idle" && here !== undefined) ageLine = idleLine(run, here, atMs);
    else if (state === "finished") {
      const lastRequest = here?.rounds.at(-1)?.lastRequest ?? ms(run.last_request);
      const minutes = Math.max(1, Math.round((lastRequest - ms(run.first_request)) / 60_000));
      ageLine = t("sr_ran", { n: minutes });
    }
    const base: LaneRun = {
      kind: "run",
      id: rowId(run.run_id),
      name: runLabel(run),
      depth: Math.min(node.depth, cap),
      model: modelFamily(run.model),
      modelLabel: run.model === null ? "" : modelLabel(run.model),
      effortLabel: run.effort,
      state,
      stateWord: stateWord(state),
      ageLine,
      tokens: notStarted ? "–" : formatTokens(tokensOf(run)),
      cost: notStarted ? { kind: "cost", text: "–" } : laneCost(...costPair(run)),
      segments: segmentsOf(run, context.axis),
      rounds: notStarted ? [] : rounds,
      unlinked,
      moved: false,
      reachesNow: false,
    };
    return node.depth > cap && parent !== null
      ? { ...base, startedBy: t("tl_by", { name: runLabel(parent.run) }) }
      : base;
  }

  const items: (LaneRun | LaneFold)[] = [];
  function walk(node: Node, parent: Node | null): void {
    items.push(laneRun(node, parent));
    const many = node.children.length > FOLD_ABOVE;
    const finished = many
      ? node.children.filter((child) =>
          [...subtree(child)].every(
            ({ run }) =>
              stateOf(run) === "finished" && atMs - finishedAtOrBefore(run, atMs) > FOLD_QUIET_MS,
          ),
        )
      : [];
    const later = many
      ? node.children.filter((child) =>
          [...subtree(child)].every(({ run }) => stateOf(run) === "not_started"),
        )
      : [];

    if (finished.length > 0) {
      const id = foldId(node.run.run_id);
      const open = context.expanded.has(id);
      const runs = finished.flatMap((child) => [...subtree(child)].map((entry) => entry.run));
      const total = sumCosts(runs.map(costOf));
      items.push({
        kind: "fold",
        id,
        depth: Math.min(node.depth + 1, cap),
        label: t("tl_fold", { n: runs.length }),
        expanded: open,
        toggleLabel: open ? t("tl_fold_hide") : t("tl_fold_show"),
        onToggle: () => {
          context.onToggle(id);
        },
        controls: finished.map((child) => rowId(child.run.run_id)).join(" "),
        segments: runs.flatMap((run) => segmentsOf(run, context.axis)),
        tokens: formatTokens(runs.reduce((sum, run) => sum + tokensOf(run), 0)),
        cost: laneCost(total.cost, total.unpriced),
        stateWord: t("rs_finished"),
      });
      if (open) for (const child of finished) walk(child, node);
    }
    for (const child of node.children) {
      if (!finished.includes(child) && !later.includes(child)) walk(child, node);
    }
    if (later.length > 0) {
      const id = laterId(node.run.run_id);
      const open = context.expanded.has(id);
      const runs = later.flatMap((child) => [...subtree(child)].map((entry) => entry.run));
      const parentName = runLabel(node.run);
      items.push({
        kind: "fold",
        id,
        depth: Math.min(node.depth + 1, cap),
        label: tn("sr_later", runs.length),
        expanded: open,
        toggleLabel: open ? t("sr_later_hide") : t("sr_later_show"),
        toggleAria: open
          ? tn("sr_later_hide_aria", runs.length, { name: parentName })
          : tn("sr_later_show_aria", runs.length, { name: parentName }),
        onToggle: () => {
          context.onToggle(id);
        },
        controls: later.map((child) => rowId(child.run.run_id)).join(" "),
        segments: runs.flatMap((run) => segmentsOf(run, context.axis)),
        tokens: "–",
        cost: { kind: "cost", text: "–" },
        stateWord: t("c_not_started"),
        later: true,
      });
      if (open) for (const child of later) walk(child, node);
    }
  }
  for (const node of buildTreeAt(timeline.runs, at, states)) walk(node, null);

  return {
    axis: {
      ticks: timeline.axis.ticks.map((tick) => ({ frac: frac(context.axis, ms(tick)), label: "" })),
      nowFrac: null,
    },
    items,
    cut: replay.atEnd ? 1 : frac(context.axis, atMs),
    note: t("sr_note"),
    label: t("sr_tl_h"),
  };
}

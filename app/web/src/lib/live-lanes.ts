/*
 * The lane rows for "Who is working", from one timeline answer. It nests the runs under their
 * starters in dispatch order, folds old finished subtrees under a parent with more than four
 * children, caps the indent (3 at 1440, 2 at 375) and turns every time into a fraction of the axis.
 * The component draws what it gets, so every word, fraction and cap is settled here.
 */
import type { Timeline, TimelineRun } from "@/api/types";
import type {
  LaneFold,
  LaneRun,
  LaneSegment,
  TimelineLaneProps,
} from "@/components/TimelineLane/TimelineLane";
import { formatTokens } from "@/lib/format";
import { frac } from "@/lib/live-chart";
import type { AxisView } from "@/lib/live-chart";
import { laneCost, sumCosts } from "@/lib/live-cost";
import { modelFamily, modelLabel } from "@/lib/models";
import { runLabel } from "@/lib/run-label";
import { t } from "@/strings/t";

/** A parent with more than this many children may fold its old finished ones. */
export const FOLD_ABOVE = 4;
/** A run that finished more recently than this never folds. */
export const FOLD_QUIET_MS = 2 * 60_000;
export const DEPTH_CAP_DESKTOP = 3;
export const DEPTH_CAP_PHONE = 2;
/** How long a row that found its starter keeps the ring. */
export const MOVED_MS = 2_000;

const ms = (text: string): number => Date.parse(text);

interface Node {
  run: TimelineRun;
  depth: number;
  children: Node[];
}

/** Runs as a tree under main. A run whose starter is not in the answer hangs under main. */
export function buildTree(runs: readonly TimelineRun[]): Node[] {
  const sorted = [...runs].sort((a, b) => a.dispatch_order - b.dispatch_order);
  const nodes = new Map<string, Node>(
    sorted.map((run) => [run.run_id, { run, depth: 0, children: [] }]),
  );
  const root = sorted.find((run) => run.parent === null && run.agent === null) ?? null;
  const rootId = root?.run_id ?? null;
  const top: Node[] = [];
  for (const run of sorted) {
    const node = nodes.get(run.run_id);
    if (node === undefined) continue;
    const parent =
      run.parent === null
        ? undefined
        : nodes.get(run.parent === "main" ? (rootId ?? "") : run.parent);
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

/** When a run's finished state began. It falls back to its last request. */
function finishedAt(run: TimelineRun): number {
  const entry = [...run.states].reverse().find((state) => state.state === "finished");
  return entry === undefined ? ms(run.last_request) : ms(entry.at);
}

function foldable(node: Node, nowMs: number): boolean {
  return [...subtree(node)].every(
    ({ run }) => run.state === "finished" && nowMs - finishedAt(run) > FOLD_QUIET_MS,
  );
}

function segmentsOf(run: TimelineRun, axis: AxisView): LaneSegment[] {
  return run.segments.map((segment) => ({
    start: frac(axis, ms(segment.start)),
    end: frac(axis, ms(segment.end)),
  }));
}

function stateWord(state: TimelineRun["state"]): string {
  switch (state) {
    case "working":
      return t("rs_working");
    case "idle":
      return t("rs_idle");
    case "finished":
      return t("rs_finished");
  }
}

/**
 * What a row shows. Once the session has ended every run reads Finished with its run time, as the
 * board draws it. The server keeps main idle (it is never done on its own), but nothing is left
 * running, so the page does not show "Idle" for a session that is over.
 */
function shownState(run: TimelineRun, sessionRunning: boolean): TimelineRun["state"] {
  return sessionRunning ? run.state : "finished";
}

function ageLine(run: TimelineRun, nowMs: number, shown: TimelineRun["state"]): string {
  if (shown === "finished") {
    const minutes = Math.max(
      1,
      Math.round((ms(run.last_request) - ms(run.first_request)) / 60_000),
    );
    return t("tl_ran", { n: minutes });
  }
  const seconds = Math.max(0, Math.round((nowMs - ms(run.last_request)) / 1000));
  // Under a minute it reads in seconds, from a minute up in whole minutes.
  return seconds < 60
    ? t("tl_last", { n: seconds })
    : t("tl_last_min", { n: Math.floor(seconds / 60) });
}

export interface LaneContext {
  nowMs: number;
  axis: AxisView;
  /** True at 721px and up, where the indent cap is 3. */
  desktop: boolean;
  /** Run ids of the parents whose fold is open. */
  expanded: ReadonlySet<string>;
  /** Run ids that found their starter a moment ago. */
  moved: ReadonlySet<string>;
  onToggle: (parentRunId: string) => void;
}

export const rowId = (runId: string): string => `lane-run-${runId}`;
export const foldId = (runId: string): string => `lane-fold-${runId}`;

function laneRun(node: Node, parent: Node | null, context: LaneContext, cap: number): LaneRun {
  const { run } = node;
  const family = modelFamily(run.model);
  const rounds = run.rounds
    .filter((round) => round.n > 1)
    .map((round) => ({
      at: frac(context.axis, ms(round.at)),
      label: t("tl_round", { n: round.n }),
    }));
  const unlinked =
    run.parent_state === "waiting"
      ? { kind: "may" as const, label: t("tl_unl_may") }
      : run.parent_state === "unknown"
        ? { kind: "never" as const, label: t("tl_unl_never") }
        : null;
  const shown = shownState(run, context.axis.running);
  const base: LaneRun = {
    kind: "run",
    id: rowId(run.run_id),
    name: runLabel(run),
    depth: Math.min(node.depth, cap),
    model: family,
    modelLabel: run.model === null ? "" : modelLabel(run.model),
    effortLabel: run.effort,
    state: shown,
    stateWord: stateWord(shown),
    ageLine: ageLine(run, context.nowMs, shown),
    tokens: formatTokens(run.tokens + (run.cum.at(-1)?.cache_read ?? 0)),
    cost: laneCost(run.cost, run.unpriced),
    segments: segmentsOf(run, context.axis),
    rounds,
    unlinked,
    moved: context.moved.has(run.run_id),
    reachesNow: run.state === "working" && context.axis.running,
  };
  return node.depth > cap && parent !== null
    ? { ...base, startedBy: t("tl_by", { name: runLabel(parent.run) }) }
    : base;
}

/** The rows in display order, the folds included. */
export function buildLaneItems(timeline: Timeline, context: LaneContext): (LaneRun | LaneFold)[] {
  const cap = context.desktop ? DEPTH_CAP_DESKTOP : DEPTH_CAP_PHONE;
  const items: (LaneRun | LaneFold)[] = [];
  const walk = (node: Node, parent: Node | null): void => {
    items.push(laneRun(node, parent, context, cap));
    const folded =
      node.children.length > FOLD_ABOVE
        ? node.children.filter((child) => foldable(child, context.nowMs))
        : [];
    if (folded.length > 0) {
      const open = context.expanded.has(node.run.run_id);
      const runs = folded.flatMap((child) => [...subtree(child)].map((entry) => entry.run));
      const total = sumCosts(runs);
      const cacheRead = runs.reduce((sum, run) => sum + (run.cum.at(-1)?.cache_read ?? 0), 0);
      items.push({
        kind: "fold",
        id: foldId(node.run.run_id),
        depth: Math.min(node.depth + 1, cap),
        label: t("tl_fold", { n: runs.length }),
        expanded: open,
        toggleLabel: open ? t("tl_fold_hide") : t("tl_fold_show"),
        onToggle: () => {
          context.onToggle(node.run.run_id);
        },
        controls: folded.map((child) => rowId(child.run.run_id)).join(" "),
        segments: runs.flatMap((run) => segmentsOf(run, context.axis)),
        tokens: formatTokens(runs.reduce((sum, run) => sum + run.tokens, 0) + cacheRead),
        cost: laneCost(total.cost, total.unpriced),
        stateWord: t("rs_finished"),
      });
      if (open) for (const child of folded) walk(child, node);
    }
    for (const child of node.children) if (!folded.includes(child)) walk(child, node);
  };
  for (const node of buildTree(timeline.runs)) walk(node, null);
  return items;
}

export function buildLane(
  timeline: Timeline,
  context: LaneContext,
): Pick<TimelineLaneProps, "axis" | "items" | "note" | "label"> {
  const ticks = timeline.axis.ticks.map((tick) => ({
    frac: frac(context.axis, ms(tick)),
    label: "",
  }));
  return {
    axis: { ticks, nowFrac: context.axis.running ? 1 : null },
    items: buildLaneItems(timeline, context),
    note: t("tl_note"),
    label: t("tl_h"),
  };
}

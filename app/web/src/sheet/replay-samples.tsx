/*
 * Sample data for the replay line and the replay lane on the component sheet (task 9b). Every word
 * comes from words.ts (sheet-only words) or the string deck, and every number is made up for the
 * sheet. Nothing here is real data.
 */
import { useState } from "react";
import type { Model } from "@/components/ModelSwatch/ModelSwatch";
import { ReplayLine } from "@/components/ReplayLine/ReplayLine";
import {
  TimelineLane,
  type LaneCost,
  type LaneFold,
  type LaneRun,
  type LaneSegment,
} from "@/components/TimelineLane/TimelineLane";
import { t } from "@/strings/t";
import { W } from "./words";

/* ---------- Replay line ---------- */

export type ReplayLineState =
  "default" | "hover" | "focus" | "dragging" | "at-start" | "at-end" | "long";

interface ReplaySpec {
  max: number;
  value: number;
  /** Minutes after midnight at the axis start. */
  base: number;
  pageStep: number;
}

const replaySpecs: Record<ReplayLineState, ReplaySpec> = {
  default: { max: 60, value: 25, base: 14 * 60, pageStep: 5 },
  hover: { max: 60, value: 25, base: 14 * 60, pageStep: 5 },
  focus: { max: 60, value: 25, base: 14 * 60, pageStep: 5 },
  dragging: { max: 60, value: 25, base: 14 * 60, pageStep: 5 },
  "at-start": { max: 60, value: 0, base: 14 * 60, pageStep: 5 },
  "at-end": { max: 60, value: 60, base: 14 * 60, pageStep: 5 },
  // Nine to five and then some: 484 minutes, so bucket_seconds is 600 and the page step is 10.
  long: { max: 484, value: 163, base: 9 * 60, pageStep: 10 },
};

const forced: Partial<Record<ReplayLineState, string>> = {
  hover: "is-hover",
  focus: "is-focus",
  dragging: "is-drag",
};

/** "2:25 PM" for a minute count from the axis start. */
export function clock(base: number, minute: number): string {
  const total = base + minute;
  const h = Math.floor(total / 60) % 24;
  const m = total % 60;
  return `${String(h % 12 || 12)}:${String(m).padStart(2, "0")} ${h >= 12 ? "PM" : "AM"}`;
}

/** A replay line with its own value, so keys and drags work on the sheet. */
export function ReplayLineDemo({ state }: { state: ReplayLineState }) {
  const spec = replaySpecs[state];
  const [value, setValue] = useState(spec.value);
  const time = clock(spec.base, value);
  const long = state === "long";
  const extra = forced[state];
  return (
    <ReplayLine
      label={W.sheet_replay_label}
      max={spec.max}
      value={value}
      valueText={time}
      pageStep={spec.pageStep}
      onChange={setValue}
      showing={
        <>
          <span className="replay-word">{W.sheet_replay_showing}</span>{" "}
          <b className="num">{time}</b>
        </>
      }
      {...(long ? { precision: W.sheet_replay_prec } : {})}
      hint={long ? W.sheet_replay_keys_long : W.sheet_replay_keys}
      {...(extra !== undefined ? { className: extra } : {})}
    />
  );
}

/* ---------- Replay lane ---------- */

export type ReplayLaneState = "hollow" | "not-yet" | "later-folded" | "later-open";

const TICKS = [0, 1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6, 1].map((frac) => ({
  frac,
  label: String(frac),
}));

const CUT = 0.42;

const cost = (text: string): LaneCost => ({ kind: "cost", text });
const span = (start: number, end: number): LaneSegment => ({ start, end });

function laneRun(input: Partial<LaneRun> & Pick<LaneRun, "id" | "name" | "segments">): LaneRun {
  const model: Model = input.model ?? "sonnet";
  return {
    kind: "run",
    depth: 1,
    model,
    modelLabel: model === "opus" ? W.m_opus : W.m_sonnet,
    effortLabel: model === "opus" ? "high" : "medium",
    state: "working",
    stateWord: t("rs_working"),
    ageLine: W.sheet_replay_since,
    tokens: "35K",
    cost: cost("$0.04"),
    rounds: [],
    unlinked: null,
    moved: false,
    reachesNow: false,
    ...input,
  };
}

const notStarted = (input: Partial<LaneRun> & Pick<LaneRun, "id" | "name" | "segments">) =>
  laneRun({
    state: "not_started",
    stateWord: t("rs_not_started"),
    ageLine: "",
    tokens: "–",
    cost: cost("–"),
    ...input,
  });

const mainRun = laneRun({
  id: "p-main",
  name: t("tl_main"),
  depth: 0,
  model: "opus",
  segments: [span(0, 1)],
  tokens: "1.0M",
  cost: cost("$1.72"),
});

const designerRun = laneRun({
  id: "p-designer",
  name: "designer",
  model: "opus",
  segments: [span(0.04, 1)],
  tokens: "752K",
  cost: cost("$1.24"),
});

const workerRun = laneRun({
  id: "p-fw5",
  name: "fast-worker 5",
  depth: 2,
  segments: [span(0.38, 0.5)],
});

const doneRun = laneRun({
  id: "p-fw3",
  name: "fast-worker 3",
  depth: 2,
  segments: [span(0.3, 0.4)],
  state: "finished",
  stateWord: t("rs_finished"),
  ageLine: t("tl_ran", { n: 4 }),
  tokens: "84K",
  cost: cost("$0.08"),
});

const laterRuns = [
  notStarted({ id: "p-fw8", name: "fast-worker 8", depth: 2, segments: [span(0.7, 0.8)] }),
  notStarted({ id: "p-fw9", name: "fast-worker 9", depth: 2, segments: [span(0.84, 0.94)] }),
];

function laterFold(expanded: boolean, onToggle: () => void): LaneFold {
  return {
    kind: "fold",
    id: "p-later",
    depth: 1,
    label: W.sheet_replay_later_two,
    expanded,
    toggleLabel: expanded ? t("tl_fold_hide") : t("tl_fold_show"),
    onToggle,
    controls: laterRuns.map((item) => item.id).join(" "),
    segments: [span(0.7, 0.8), span(0.84, 0.94)],
    tokens: "–",
    cost: cost("–"),
    stateWord: t("rs_not_started"),
    later: true,
  };
}

function replayItems(
  state: ReplayLaneState,
  expanded: boolean,
  onToggle: () => void,
): (LaneRun | LaneFold)[] {
  switch (state) {
    case "hollow":
      return [mainRun, designerRun, workerRun, doneRun];
    case "not-yet":
      return [
        mainRun,
        notStarted({
          id: "p-verifier",
          name: "verifier",
          model: "opus",
          segments: [span(0.8, 0.96)],
        }),
      ];
    case "later-folded":
    case "later-open":
      return [
        mainRun,
        designerRun,
        workerRun,
        laterFold(expanded, onToggle),
        ...(expanded ? laterRuns : []),
      ];
  }
}

/** A replay lane with its own fold state, so Show and Hide work on the sheet. */
export function ReplayLaneDemo({ state }: { state: ReplayLaneState }) {
  const [expanded, setExpanded] = useState(state === "later-open");
  const items = replayItems(state, expanded, () => {
    setExpanded((value) => !value);
  });
  return (
    <TimelineLane
      axis={{ ticks: TICKS, nowFrac: null }}
      cut={CUT}
      items={items}
      note={W.sheet_replay_note}
      label={W.sheet_replay_h}
      tokensWord="tokens"
    />
  );
}

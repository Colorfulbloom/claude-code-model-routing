/*
 * Sample data for the stacked bars and the timeline lane on the component sheet. The numbers follow
 * the designer's boards (a-live and the M2 many and long boards, 30 minutes from 6:10) and every word
 * comes from the string deck, so the sheet shows what the page will. Nothing here is real data.
 */
import { useState } from "react";
import type { Model } from "@/components/ModelSwatch/ModelSwatch";
import type { StackedBar, StackedBarsProps } from "@/components/StackedBars/StackedBars";
import {
  TimelineLane,
  type LaneCost,
  type LaneFold,
  type LaneRun,
  type LaneSegment,
} from "@/components/TimelineLane/TimelineLane";
import { useIsDesktop } from "@/lib/media";
import { t } from "@/strings/t";
import { W } from "./words";

const OPUS = W.m_opus;
const SONNET = W.m_sonnet;
const HAIKU = W.m_haiku;

/* ---------- Stacked bars ---------- */

const barModels: Model[] = ["opus", "sonnet", "haiku"];

function sampleBars(count: number, openFrac: number | null): StackedBar[] {
  return Array.from({ length: count }, (_, i) => {
    const wave = 0.75 + 0.5 * Math.abs(Math.sin(i * 1.7));
    const open = openFrac !== null && i === count - 1;
    return {
      key: `b${String(i)}`,
      byModel: {
        opus: Math.round(26000 * wave),
        ...(i % 3 === 1 ? { sonnet: Math.round(14000 * wave) } : {}),
        ...(i % 7 === 2 ? { haiku: Math.round(6000 * wave) } : {}),
      },
      ...(open ? { open: true, openFrac } : {}),
    };
  });
}

const shortLabels = [
  { frac: 0, label: "6:10" },
  { frac: 1 / 6, label: "6:15" },
  { frac: 2 / 6, label: "6:20" },
  { frac: 3 / 6, label: "6:25" },
  { frac: 4 / 6, label: "6:30" },
  { frac: 5 / 6, label: "6:35" },
  { frac: 1, label: t("tl_now") },
];

const longLabels = [
  { frac: 0, label: "9 AM" },
  { frac: 0.124, label: "10" },
  { frac: 0.248, label: "11" },
  { frac: 0.372, label: "12 PM" },
  { frac: 0.496, label: "1" },
  { frac: 0.62, label: "2" },
  { frac: 0.744, label: "3" },
  { frac: 0.868, label: "4" },
  { frac: 1, label: t("tl_now") },
];

const legendFor = (totals: [string, string, string]): StackedBarsProps["legend"] => [
  { model: "opus", label: OPUS, total: totals[0] },
  { model: "sonnet", label: SONNET, total: totals[1] },
  { model: "haiku", label: HAIKU, total: totals[2] },
];

const tickSet = [
  { value: 50000, label: "50K" },
  { value: 100000, label: "100K" },
];

export type BarsState = "normal" | "open-bucket" | "averaged" | "empty";

export function barsSample(state: BarsState): StackedBarsProps {
  switch (state) {
    case "normal":
      return {
        bars: sampleBars(30, null),
        models: barModels,
        yTicks: tickSet,
        xLabels: shortLabels,
        legend: legendFor(["1.0M", "215K", "29K"]),
        axisLabel: t("tl_axis_lab"),
        summary: "New tokens per minute over the last 30 minutes, mostly Opus 5.5.",
      };
    case "open-bucket":
      return {
        bars: sampleBars(30, 0.4),
        models: barModels,
        yTicks: tickSet,
        xLabels: shortLabels,
        legend: legendFor(["1.0M", "215K", "29K"]),
        axisLabel: t("tl_axis_lab"),
        summary: "New tokens per minute over the last 30 minutes. The last bar is still filling.",
      };
    case "averaged":
      return {
        bars: sampleBars(49, 0.4),
        models: barModels,
        yTicks: [
          { value: 100000, label: "100K" },
          { value: 200000, label: "200K" },
        ],
        xLabels: longLabels,
        legend: legendFor(["3.3M", "349K", "78K"]),
        axisLabel: t("tl_axis_avg", { n: 10 }),
        summary: "New tokens per minute, averaged over 10 minutes, across 8 hours.",
      };
    case "empty":
      return {
        bars: [],
        models: barModels,
        yTicks: [],
        xLabels: [],
        legend: [],
        axisLabel: t("tl_axis_lab"),
        summary: "No tokens used yet.",
      };
  }
}

/* ---------- Timeline lane ---------- */

const SHORT_TICKS = [0, 1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6, 1].map((frac) => ({
  frac,
  label: String(frac),
}));

const cost = (text: string): LaneCost => ({ kind: "cost", text });
const span = (start: number, end: number): LaneSegment => ({ start, end });

type RunInput = Partial<LaneRun> & Pick<LaneRun, "id" | "name" | "segments" | "tokens" | "cost">;

function run(input: RunInput, model: Model | null, effort: string | null): LaneRun {
  const working = input.state === "working";
  const modelLabel = model === "opus" ? OPUS : model === "sonnet" ? SONNET : HAIKU;
  return {
    kind: "run",
    depth: 0,
    model,
    modelLabel,
    effortLabel: effort,
    state: "finished",
    stateWord: t("rs_finished"),
    ageLine: t("tl_ran", { n: 3 }),
    rounds: [],
    unlinked: null,
    moved: false,
    reachesNow: working,
    ...input,
  };
}

const working = (n: number) => ({
  state: "working" as const,
  stateWord: t("rs_working"),
  ageLine: t("tl_last", { n }),
});

const mainRun = run(
  {
    id: "r-main",
    name: t("tl_main"),
    segments: [span(0, 1)],
    tokens: "1.9M",
    cost: cost("$3.10"),
    ...working(2),
  },
  "opus",
  "high",
);

const deepRun = run(
  {
    id: "r-dr",
    name: "deep-reasoner",
    depth: 1,
    segments: [span(0.066, 1)],
    tokens: "1.8M",
    cost: cost("$3.22"),
    ...working(32),
  },
  "opus",
  "high",
);

const scoutRun = run(
  {
    id: "r-scout",
    name: "scout",
    depth: 2,
    segments: [span(0.134, 0.222)],
    tokens: "42K",
    cost: cost("<$0.01"),
  },
  "haiku",
  "medium",
);

const scoutTwo = run(
  {
    id: "r-scout2",
    name: "scout 2",
    depth: 2,
    segments: [span(0.134, 0.245)],
    tokens: "59K",
    cost: cost("<$0.01"),
  },
  "haiku",
  "medium",
);

const workerRun = run(
  {
    id: "r-fw",
    name: "fast-worker",
    depth: 2,
    segments: [span(0.4, 0.6)],
    tokens: "248K",
    cost: cost("$0.25"),
    ageLine: t("tl_ran", { n: 6 }),
  },
  "sonnet",
  "medium",
);

const workerTwo = run(
  {
    id: "r-fw2",
    name: "fast-worker 2",
    depth: 2,
    segments: [span(0.4, 0.58)],
    tokens: "230K",
    cost: cost("$0.23"),
    ageLine: t("tl_ran", { n: 5 }),
  },
  "sonnet",
  "medium",
);

const judgeRun = run(
  {
    id: "r-judge",
    name: "judge",
    depth: 2,
    segments: [span(0.67, 1)],
    tokens: "681K",
    cost: cost("$1.21"),
    ...working(10),
  },
  "opus",
  "medium",
);

const writerRun = run(
  {
    id: "r-tw",
    name: "tech-writer",
    depth: 1,
    segments: [span(0.335, 0.48), span(0.975, 1)],
    rounds: [{ at: 0.975, label: t("tl_round", { n: 2 }) }],
    tokens: "288K",
    cost: cost("$0.26"),
    ...working(4),
  },
  "sonnet",
  "high",
);

const busyItems: LaneRun[] = [
  mainRun,
  deepRun,
  scoutRun,
  scoutTwo,
  workerRun,
  workerTwo,
  judgeRun,
  writerRun,
];

const scoutThree = run(
  {
    id: "r-scout3",
    name: "scout 3",
    depth: 1,
    segments: [span(0.93, 1)],
    tokens: "38K",
    cost: cost("<$0.01"),
    unlinked: { kind: "may", label: t("tl_unl_may") },
    ...working(3),
  },
  "haiku",
  "medium",
);

const exploreRun = run(
  {
    id: "r-explore",
    name: "Explore",
    depth: 1,
    segments: [span(0.4, 0.48)],
    tokens: "21K",
    cost: cost("<$0.01"),
    ageLine: t("tl_ran", { n: 2 }),
    unlinked: { kind: "never", label: t("tl_unl_never") },
  },
  "haiku",
  "low",
);

export type LaneState =
  | "busy"
  | "idle"
  | "not-started"
  | "unlinked-may"
  | "unlinked-never"
  | "unpriced-least"
  | "unpriced-none"
  | "folded"
  | "open"
  | "depth-cap"
  | "moved";

const axis = { ticks: SHORT_TICKS, nowFrac: 1 as number | null };

/** The "many" scenario's start: two runs and a fold of finished workers that Show reveals. */
function foldItems(expanded: boolean, onToggle: () => void): (LaneRun | LaneFold)[] {
  const hidden = [scoutRun, workerRun, workerTwo].map((item) => ({ ...item, depth: 2 }));
  const fold: LaneFold = {
    kind: "fold",
    id: "f-earlier",
    depth: 1,
    label: t("tl_fold", { n: 10 }),
    expanded,
    toggleLabel: expanded ? t("tl_fold_hide") : t("tl_fold_show"),
    onToggle,
    controls: hidden.map((item) => item.id).join(" "),
    segments: [
      span(0.08, 0.2),
      span(0.24, 0.3),
      span(0.36, 0.45),
      span(0.52, 0.53),
      span(0.57, 0.65),
    ],
    tokens: "685K",
    cost: cost("$0.67"),
    stateWord: t("rs_finished"),
  };
  const lead = [mainRun, { ...deepRun, ...working(18) }];
  const tail = [
    run(
      {
        id: "r-fw13",
        name: "fast-worker 13",
        depth: 2,
        segments: [span(0.93, 1)],
        tokens: "105K",
        cost: cost("$0.10"),
        ...working(15),
      },
      "sonnet",
      "medium",
    ),
  ];
  return [...lead, fold, ...(expanded ? hidden : []), ...tail];
}

function laneItems(
  state: LaneState,
  cap: number,
  expanded: boolean,
  onToggle: () => void,
): (LaneRun | LaneFold)[] {
  switch (state) {
    case "busy":
      return busyItems;
    case "idle":
      return [
        {
          ...mainRun,
          state: "idle",
          stateWord: t("rs_idle"),
          ageLine: "Last request 95 s ago",
          reachesNow: false,
          segments: [span(0, 0.92)],
        },
      ];
    case "not-started":
      return [
        { ...mainRun, ...working(2) },
        run(
          {
            id: "r-future",
            name: "verifier",
            depth: 1,
            segments: [],
            tokens: "0",
            cost: cost("$0.00"),
            state: "not_started",
            stateWord: t("rs_not_started"),
            ageLine: "",
          },
          "opus",
          "high",
        ),
      ];
    case "unlinked-may":
      return [mainRun, scoutThree];
    case "unlinked-never":
      return [mainRun, exploreRun];
    case "unpriced-least":
      return [
        mainRun,
        {
          ...judgeRun,
          depth: 1,
          cost: { kind: "least", text: t("c_least", { cost: "$0.97" }) },
        },
      ];
    case "unpriced-none":
      return [
        mainRun,
        {
          ...writerRun,
          modelLabel: W.m_fable,
          model: "fable",
          cost: { kind: "none", text: t("c_none", { model: W.m_fable }) },
        },
      ];
    case "folded":
    case "open":
      return foldItems(expanded, onToggle);
    case "depth-cap": {
      // The page caps the indent and adds "Started by". Real nesting here is 0, 1, 2 and 4.
      const chain = [
        { run: mainRun, real: 0 },
        { run: { ...deepRun, id: "c-dr", name: "designer 2" }, real: 1 },
        { run: { ...judgeRun, id: "c-judge", ...working(4) }, real: 2 },
        { run: { ...scoutThree, id: "c-scout", name: "scout 11", unlinked: null }, real: 4 },
      ];
      return chain.map(({ run: item, real }) => ({
        ...item,
        depth: Math.min(real, cap),
        ...(real > cap ? { startedBy: t("tl_by", { name: "judge" }) } : {}),
      }));
    }
    case "moved":
      return [
        mainRun,
        { ...deepRun, ...working(32) },
        {
          ...scoutThree,
          id: "m-scout3",
          depth: 2,
          unlinked: null,
          moved: true,
          state: "finished",
          stateWord: t("rs_finished"),
          ageLine: t("tl_ran", { n: 2 }),
          reachesNow: false,
          segments: [span(0.93, 0.995)],
        },
        exploreRun,
      ];
  }
}

/**
 * One lane sample. It holds the fold's expanded state, so Show and Hide work on the sheet, and it
 * caps the indent the way the page will (3 at 1440, 2 at 375). A moved row keeps its ring on the
 * sheet, where the real one fades after 2 seconds.
 */
export function LaneDemo({ state }: { state: LaneState }) {
  const [expanded, setExpanded] = useState(state === "open");
  const desktop = useIsDesktop();
  const items = laneItems(state, desktop ? 3 : 2, expanded, () => {
    setExpanded((value) => !value);
  });
  return (
    <div className={state === "moved" ? "sheet-hold" : undefined}>
      <TimelineLane
        axis={axis}
        items={items}
        note={t("tl_note")}
        label={t("tl_h")}
        tokensWord="tokens"
      />
    </div>
  );
}

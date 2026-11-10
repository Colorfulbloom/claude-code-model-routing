/*
 * Sample data for the Review components on the component sheet (wave 3): the cost chart with kind
 * patterns and the scope bar's stateful controls. Every word comes from words.ts (sheet-only words)
 * and every number is made up for the sheet. Nothing here is real data.
 */
import { useState } from "react";
import type { Model } from "@/components/ModelSwatch/ModelSwatch";
import { ScopeBar, type ScopeBarProps } from "@/components/ScopeBar/ScopeBar";
import { Segmented, type SegmentedItem } from "@/components/Segmented/Segmented";
import { Select, type SelectOption } from "@/components/Select/Select";
import type { BarKind, StackedBar, StackedBarsProps } from "@/components/StackedBars/StackedBars";
import { W } from "./words";

/* ---------- Cost chart ---------- */

export type CostBarsState =
  "cost-kinds" | "cost-open" | "cost-partial" | "cost-unpriced" | "cost-no-records";

const costModels: Model[] = ["opus", "sonnet", "haiku"];

/** Splits a cost into the four kinds, with a little drift per bar. */
function kindSplit(total: number, i: number): Record<BarKind, number> {
  const drift = (i % 5) / 100;
  return {
    input: total * (0.14 + drift),
    output: total * (0.26 - drift),
    cache_read: total * 0.48,
    cache_write: total * 0.12,
  };
}

function costBar(i: number, extra: Partial<StackedBar> = {}): StackedBar {
  const wave = 0.7 + 0.6 * Math.abs(Math.sin(i * 1.3));
  const opus = 1.6 * wave;
  const sonnet = i % 3 === 1 ? 0.7 * wave : 0;
  const haiku = i % 7 === 2 ? 0.2 * wave : 0;
  return {
    key: `d${String(i)}`,
    byModel: { opus, ...(sonnet > 0 ? { sonnet } : {}), ...(haiku > 0 ? { haiku } : {}) },
    kinds: {
      opus: kindSplit(opus, i),
      ...(sonnet > 0 ? { sonnet: kindSplit(sonnet, i) } : {}),
      ...(haiku > 0 ? { haiku: kindSplit(haiku, i) } : {}),
    },
    ...extra,
  };
}

const costLabels = [
  { frac: 0, label: "Oct 10" },
  { frac: 0.33, label: "Oct 20" },
  { frac: 0.66, label: "Oct 30" },
  { frac: 1, label: "Nov 8" },
];

const costTicks = [
  { value: 1, label: "$1" },
  { value: 2, label: "$2" },
];

const kindsLine: NonNullable<StackedBarsProps["kindsLine"]> = [
  { kind: "input", label: W.sheet_kind_input, total: "$6.10" },
  { kind: "output", label: W.sheet_kind_output, total: "$10.20" },
  { kind: "cache_read", label: W.sheet_kind_cache_read, total: "$20.40" },
  { kind: "cache_write", label: W.sheet_kind_cache_write, total: "$5.10" },
];

export function costBarsSample(state: CostBarsState): StackedBarsProps {
  const count = 30;
  const base = Array.from({ length: count }, (_, i) => costBar(i));
  const common = {
    models: costModels,
    yTicks: costTicks,
    xLabels: costLabels,
    kindsLine,
    kindsLabel: W.sheet_kinds_label,
    axisLabel: W.sheet_cost_axis,
  };
  const legend = (fable: boolean): StackedBarsProps["legend"] => [
    { model: "opus", label: W.m_opus, total: W.sheet_share_a },
    { model: "sonnet", label: W.m_sonnet, total: W.sheet_share_b },
    { model: "haiku", label: W.m_haiku, total: W.sheet_share_c },
    ...(fable ? [{ model: "fable" as const, label: W.m_fable, total: W.sheet_no_price }] : []),
  ];
  switch (state) {
    case "cost-kinds":
      return { ...common, bars: base, legend: legend(false), summary: W.sheet_cost_summary };
    case "cost-open":
      return {
        ...common,
        bars: base.map((bar, i) =>
          i === count - 1 ? costBar(i, { open: true, openFrac: 0.4 }) : bar,
        ),
        legend: legend(false),
        summary: W.sheet_cost_summary,
      };
    case "cost-partial":
      return {
        ...common,
        bars: base.map((bar, i) =>
          i === 0 || i === count - 1 ? costBar(i, { partial: true }) : bar,
        ),
        legend: legend(false),
        summary: W.sheet_cost_partial,
      };
    case "cost-unpriced":
      return {
        ...common,
        models: [...costModels, "fable"],
        bars: base.map((bar, i) =>
          i % 4 === 3 ? { ...bar, byModel: { ...bar.byModel, fable: null } } : bar,
        ),
        legend: legend(true),
        summary: W.sheet_cost_unpriced,
      };
    case "cost-no-records":
      return {
        ...common,
        bars: base.map((bar, i) =>
          i < 8 ? { key: bar.key, byModel: {}, noRecords: W.sheet_no_records } : bar,
        ),
        legend: legend(false),
        summary: W.sheet_cost_none,
      };
  }
}

/* ---------- Scope bar ---------- */

export const rangeOptions: SelectOption[] = [
  { id: "today", label: W.sheet_range_today },
  { id: "7d", label: W.sheet_range_7 },
  { id: "30d", label: W.rv_range },
  { id: "90d", label: W.sheet_range_90 },
  { id: "12m", label: W.sheet_range_12m },
  { id: "all", label: W.sheet_range_all },
];

const sessionOptions: SelectOption[] = [
  { id: "a", label: W.sheet_session_a },
  { id: "b", label: W.sheet_session_b },
];

export const pageItems = (current: string): SegmentedItem[] =>
  [
    { id: "summary", href: "#summary", label: W.nav_summary },
    { id: "sessions", href: "#sessions", label: W.nav_sessions },
    { id: "agents", href: "#agents", label: W.nav_agents },
    { id: "models", href: "#models", label: W.nav_models },
  ].map((item) => ({ ...item, ...(item.id === current ? { current: true } : {}) }));

export interface ScopeBarDemoProps {
  form: "range" | "session";
  force?: "hover" | "focus";
  openLive?: boolean;
  pages?: boolean;
}

/** A scope bar with its own state, for the sheet. */
export function ScopeBarDemo({ form, force, openLive = true, pages = false }: ScopeBarDemoProps) {
  const [range, setRange] = useState<string | null>("30d");
  const [session, setSession] = useState<string | null>("a");
  const forced = force === "hover" ? "is-hover" : force === "focus" ? "is-focus" : undefined;
  const extra = forced !== undefined ? { className: forced } : {};
  const shared = {
    ...(pages
      ? { pages: <Segmented label={W.sheet_pages_label} items={pageItems("summary")} /> }
      : {}),
  };
  const props: ScopeBarProps =
    form === "range"
      ? {
          form: "range",
          title: W.nav_summary,
          sub: W.sheet_scope_sub,
          range: {
            label: W.rv_range_lab,
            options: rangeOptions,
            value: range,
            onChange: setRange,
            ...extra,
          },
          ...shared,
        }
      : {
          form: "session",
          title: W.sheet_session_title,
          sub: W.sheet_session_sub,
          back: { label: W.sheet_back, href: "#sessions", ...extra },
          sessionSelect: (
            <Select
              label={W.sheet_session_lab}
              items={sessionOptions}
              value={session}
              onChange={setSession}
              {...extra}
            />
          ),
          ...(openLive ? { openLive: { label: W.sheet_open_live, href: "#live", ...extra } } : {}),
          ...shared,
        };
  return <ScopeBar {...props} />;
}

import { useId } from "react";
import { useElementWidth } from "@/lib/use-width";
import { cx } from "../cx";
import { ModelSwatch, type Model } from "../ModelSwatch/ModelSwatch";
import "./StackedBars.css";

export const states = ["normal", "open-bucket", "averaged", "empty"] as const;

export interface StackedBar {
  key: string;
  /** Tokens (or any one unit) per model for this bucket. A missing model draws nothing. */
  byModel: Partial<Record<Model, number>>;
  /** The bucket that is still filling. It draws hatched and outlined. */
  open?: boolean;
  /** How much of a full bucket has passed, 0 to 1. An open bar with none counts as 1. */
  openFrac?: number;
}

export interface StackedBarsProps {
  bars: StackedBar[];
  /** Stack order, bottom first. */
  models: Model[];
  yTicks: { value: number; label: string }[];
  /** Where each label sits along the plot, as a fraction from 0 to 1. */
  xLabels: { frac: number; label: string }[];
  /** One line per model with its total. This is the text alternative to the picture. */
  legend: { model: Model; label: string; total: string }[];
  /** "New tokens per minute", or the same with "averaged over {n} minutes". */
  axisLabel: string;
  /** The SVG's accessible name. */
  summary: string;
  className?: string;
}

/** Plot height in px. The bars draw in px, so the CSS reads the same number from the SVG. */
const PLOT_HEIGHT = 72;
const BAR_GAP = 2;
const STACK_GAP = 1;
const OPEN_MIN = 5;
/** Headroom above the tallest bar or tick, as the board draws it. */
const HEADROOM = 1.12;
/** A clock label closer than this to the last label (Now) is dropped, so the two never touch. */
const LABEL_CLEARANCE = 44;
/** Width used before the plot is measured and where nothing can measure it (jsdom). */
const FALLBACK_WIDTH = 600;

interface XLabel {
  frac: number;
  label: string;
  /** Every other label. A phone hides these. */
  minor: boolean;
}

/** Marks every other label as minor, then drops any clock label too close to the last one. */
function fitLabels(labels: StackedBarsProps["xLabels"], width: number): XLabel[] {
  const marked = labels.map((entry, index) => ({
    ...entry,
    minor: index % 2 === 1 && index !== labels.length - 1,
  }));
  const last = marked.at(-1);
  if (last === undefined) return marked;
  return marked.filter(
    (entry, index) =>
      index === marked.length - 1 || (last.frac - entry.frac) * width >= LABEL_CLEARANCE,
  );
}

interface Slot {
  x: number;
  width: number;
}

function openWeight(bar: StackedBar): number {
  if (bar.open !== true) return 1;
  const frac = bar.openFrac ?? 1;
  return Math.min(1, Math.max(0.01, Number.isFinite(frac) ? frac : 1));
}

/** Bars share the width by weight (an open bar weighs its fraction) and an open bar is at least 5 px. */
function layoutBars(bars: StackedBar[], width: number): Slot[] {
  const gaps = BAR_GAP * Math.max(0, bars.length - 1);
  const weights = bars.map(openWeight);
  const total = weights.reduce((sum, w) => sum + w, 0) || 1;
  const first = Math.max(0, width - gaps) / total;
  // An open bar under the floor keeps 5 px, and the other bars share what is left.
  const floored = bars.map((bar, i) => bar.open === true && (weights[i] ?? 1) * first < OPEN_MIN);
  const fixed = floored.filter(Boolean).length * OPEN_MIN;
  const pool = weights.reduce((sum, w, i) => (floored[i] === true ? sum : sum + w), 0);
  const slot = pool > 0 ? Math.max(0, width - gaps - fixed) / pool : 0;
  const widths = weights.map((w, i) => (floored[i] === true ? OPEN_MIN : w * slot));
  return widths.map((w, i) => ({
    x: widths.slice(0, i).reduce((sum, prev) => sum + prev + BAR_GAP, 0),
    width: w,
  }));
}

interface Part {
  model: Model;
  y: number;
  height: number;
}

/** The stacked parts of one bar, bottom first, with a 1 px gap between them. */
function stackBar(bar: StackedBar, models: Model[], top: number): Part[] {
  const heights = models
    .map((model) => ({ model, value: bar.byModel[model] ?? 0 }))
    .filter((part) => part.value > 0)
    .map((part) => ({
      model: part.model,
      height: Math.max(0.5, (part.value / top) * PLOT_HEIGHT),
    }));
  return heights.map((part, i) => {
    const below = heights.slice(0, i).reduce((sum, p) => sum + p.height + STACK_GAP, 0);
    return { model: part.model, height: part.height, y: PLOT_HEIGHT - below - part.height };
  });
}

/**
 * Tokens per minute stacked by model (components.md entry 20, by model only; kind patterns come
 * later). It draws what it is given: the page turns the timeline into buckets, ticks and labels.
 * The picture is an SVG image with a summary for its name. Every label is HTML, and the legend
 * with totals is the text alternative, so the tick and x labels are hidden from assistive tech.
 * It heads the lane list on the card, never inside a well (tokens.css, axis rule).
 */
export function StackedBars({
  bars,
  models,
  yTicks,
  xLabels,
  legend,
  axisLabel,
  summary,
  className,
}: StackedBarsProps) {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");
  const { ref, width } = useElementWidth<HTMLDivElement>(FALLBACK_WIDTH);
  const sums = bars.map((bar) =>
    models.reduce((sum, model) => sum + Math.max(0, bar.byModel[model] ?? 0), 0),
  );
  const top = Math.max(1, ...yTicks.map((tick) => tick.value), ...sums) * HEADROOM;
  const slots = layoutBars(bars, width);
  const usedModels = models.filter((model) => bars.some((bar) => (bar.byModel[model] ?? 0) > 0));
  const labels = fitLabels(xLabels, width);
  const hasOpen = bars.some((bar) => bar.open === true);

  return (
    <div className={cx("bars", className)}>
      <div className="bars-side">
        <p className="bars-axis-label">{axisLabel}</p>
        {legend.length > 0 && (
          <ul className="bars-legend">
            {legend.map((entry) => (
              <li key={entry.model}>
                <ModelSwatch model={entry.model} />
                {entry.label} <b className="num">{entry.total}</b>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="bars-chart">
        <div className="bars-plot" ref={ref}>
          <svg
            className="bars-svg"
            role="img"
            aria-label={summary}
            width="100%"
            height={PLOT_HEIGHT}
            viewBox={`0 0 ${String(width)} ${String(PLOT_HEIGHT)}`}
            preserveAspectRatio="none"
          >
            {hasOpen && (
              <defs>
                {usedModels.map((model) => (
                  <pattern
                    key={model}
                    id={`${uid}-${model}`}
                    patternUnits="userSpaceOnUse"
                    width="5"
                    height="5"
                    patternTransform="rotate(45)"
                  >
                    <rect width="2" height="5" className={`bars-fill-${model}`} />
                  </pattern>
                ))}
              </defs>
            )}
            {yTicks.map((tick) => {
              const y = PLOT_HEIGHT - (tick.value / top) * PLOT_HEIGHT;
              return (
                <line key={tick.value} className="bars-grid" x1="0" x2={width} y1={y} y2={y} />
              );
            })}
            {bars.map((bar, index) => {
              const slot = slots[index];
              if (slot === undefined) return null;
              const open = bar.open === true;
              return (
                <g key={bar.key} data-bar={bar.key} data-open={open ? "true" : undefined}>
                  {stackBar(bar, models, top).map((part) =>
                    open && part.height > 2 && slot.width > 2 ? (
                      <rect
                        key={part.model}
                        className={`bars-seg bars-seg-open bars-stroke-${part.model}`}
                        fill={`url(#${uid}-${part.model})`}
                        x={slot.x + 0.75}
                        y={part.y + 0.75}
                        width={slot.width - 1.5}
                        height={part.height - 1.5}
                      />
                    ) : (
                      <rect
                        key={part.model}
                        className={`bars-seg bars-seg-${part.model}`}
                        x={slot.x}
                        y={part.y}
                        width={slot.width}
                        height={part.height}
                        rx="1"
                      />
                    ),
                  )}
                </g>
              );
            })}
          </svg>
          {yTicks.map((tick) => (
            <span
              key={tick.value}
              className="bars-tick"
              aria-hidden="true"
              style={{ bottom: `calc(${String((tick.value / top) * 100)}% + 1px)` }}
            >
              {tick.label}
            </span>
          ))}
        </div>
        <div className="bars-x" aria-hidden="true">
          {labels.map((entry) => (
            <span
              key={`${String(entry.frac)}-${entry.label}`}
              className={entry.minor ? "bars-x-minor" : undefined}
              style={{ left: `${String(entry.frac * 100)}%` }}
            >
              {entry.label}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

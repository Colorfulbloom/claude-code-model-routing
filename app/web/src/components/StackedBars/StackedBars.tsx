import { useId } from "react";
import { useElementWidth } from "@/lib/use-width";
import { cx } from "../cx";
import { ModelSwatch, type Model } from "../ModelSwatch/ModelSwatch";
import "./StackedBars.css";

export const states = [
  "normal",
  "open-bucket",
  "averaged",
  "empty",
  "cost-kinds",
  "cost-open",
  "cost-partial",
  "cost-unpriced",
  "cost-no-records",
] as const;

/** The four token kinds a model segment can split into, bottom first. */
export const BAR_KINDS = ["input", "output", "cache_read", "cache_write"] as const;
export type BarKind = (typeof BAR_KINDS)[number];

/** Each kind has one pattern, kp1 to kp4, so a kind never relies on colour (entry 20). */
const KIND_PATTERN: Record<BarKind, string> = {
  input: "kp1",
  output: "kp2",
  cache_read: "kp3",
  cache_write: "kp4",
};

export interface StackedBar {
  key: string;
  /**
   * Tokens or cost (one unit) per model for this bucket. A missing model draws nothing. `null` is a
   * part with no price: it draws as the dashed stub the Live sparks use, never as zero.
   */
  byModel: Partial<Record<Model, number | null>>;
  /**
   * Splits a model's segment into kinds, drawn as the kind patterns in the model colour. The split
   * is scaled to the model's value. A model without a split stays solid.
   */
  kinds?: Partial<Record<Model, Partial<Record<BarKind, number>>>>;
  /** The bucket that holds now, still filling. It draws outlined (hatched when it has no kinds). */
  open?: boolean;
  /** How much of a full bucket has passed, 0 to 1. An open bar with none counts as 1. */
  openFrac?: number;
  /** The bucket is cut short by the window or by the start of the records. It draws a dashed outline. */
  partial?: boolean;
  /**
   * The bucket ends before the records start. It draws no bar, never a zero-height one, and this
   * label says so in HTML. Neighbouring buckets with the same label share one.
   */
  noRecords?: string;
  /** A slot for a bucket that has not begun, such as the hours of today after now. It draws nothing. */
  future?: boolean;
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
  /** One line per kind with its total, drawn with the kind patterns. It sits under the chart. */
  kindsLine?: { kind: BarKind; label: string; total: string }[];
  /** Names the kinds line for assistive tech, such as "Cost by kind". */
  kindsLabel?: string;
  /** "New tokens per minute", or the same with "averaged over {n} minutes". */
  axisLabel: string;
  /** The SVG's accessible name. The caller writes it, because only the caller knows the unit. */
  summary: string;
  /**
   * Gives the y labels their own column to the left of the plot, so they never sit on the first
   * bars. The labels centre on their grid lines. Without it the labels sit inside the plot.
   */
  guttered?: boolean;
  /**
   * A marker for the open bucket, such as "Now". It stands where the open bucket has got to. The
   * bucket keeps a whole slot when slots follow it, so the empty slots after it have room.
   */
  nowLabel?: string;
  className?: string;
}

/** Plot height in px. The bars draw in px, so the CSS reads the same number from the SVG. */
const PLOT_HEIGHT = 72;
const BAR_GAP = 2;
const STACK_GAP = 1;
const OPEN_MIN = 5;
/** The dashed stub of a part with no price, in px. */
const STUB_HEIGHT = 10;
/** Pattern tile size in px. */
const TILE = 6;
/** Headroom above the tallest bar or tick, as the board draws it. */
const HEADROOM = 1.12;
/** A clock label closer than this to the last label (Now) is dropped, so the two never touch. */
const LABEL_CLEARANCE = 44;
/** Width used before the plot is measured and where nothing can measure it (jsdom). */
const FALLBACK_WIDTH = 600;
/** A no-records run at least this wide wraps its label inside the run. A narrower one hangs it at the edge. */
const NONE_WIDE = 88;

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

/**
 * Bars share the width by weight, and an open bar is at least 5 px. An open bar that nothing
 * follows weighs its fraction, so it grows as it fills. An open bar with slots after it keeps a
 * whole slot, and the Now marker shows how far it has got.
 */
function layoutBars(bars: StackedBar[], width: number): Slot[] {
  const gaps = BAR_GAP * Math.max(0, bars.length - 1);
  const weights = bars.map((bar, i) => (i === bars.length - 1 ? openWeight(bar) : 1));
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
  /** A part with no price: a dashed stub, not a filled segment. */
  unpriced: boolean;
}

function valueOf(bar: StackedBar, model: Model): number {
  return Math.max(0, bar.byModel[model] ?? 0);
}

/**
 * The stacked parts of one bar, bottom first, with a 1 px gap between them. Priced parts keep the
 * model order and unpriced stubs sit on top. `plotHeight` is the height the values scale to.
 */
function stackBar(bar: StackedBar, models: Model[], top: number, plotHeight: number): Part[] {
  const priced = models
    .filter((model) => valueOf(bar, model) > 0)
    .map((model) => ({
      model,
      unpriced: false,
      height: Math.max(0.5, (valueOf(bar, model) / top) * plotHeight),
    }));
  const stubs = models
    .filter((model) => bar.byModel[model] === null)
    .map((model) => ({ model, unpriced: true, height: STUB_HEIGHT }));
  const heights = [...priced, ...stubs];
  return heights.map((part, i) => {
    const below = heights.slice(0, i).reduce((sum, p) => sum + p.height + STACK_GAP, 0);
    return { ...part, y: PLOT_HEIGHT - below - part.height };
  });
}

interface KindSlice {
  kind: BarKind;
  y: number;
  height: number;
}

/** A segment split by kind, bottom first, scaled to fill the segment. No split means no slices. */
function splitKinds(bar: StackedBar, model: Model, y: number, height: number): KindSlice[] {
  const split = bar.kinds?.[model];
  if (split === undefined) return [];
  const present = BAR_KINDS.filter((kind) => (split[kind] ?? 0) > 0);
  const sum = present.reduce((total, kind) => total + (split[kind] ?? 0), 0);
  if (sum <= 0) return [];
  let used = 0;
  return present.map((kind) => {
    const sliceHeight = ((split[kind] ?? 0) / sum) * height;
    const slice = { kind, y: y + height - used - sliceHeight, height: sliceHeight };
    used += sliceHeight;
    return slice;
  });
}

/** One kind's pattern tile, filled with currentColor. The tile's own class sets `color`. */
function KindPattern({ id, kind, className }: { id: string; kind: BarKind; className: string }) {
  const ink = "currentColor";
  return (
    <pattern
      id={id}
      className={className}
      patternUnits="userSpaceOnUse"
      width={TILE}
      height={TILE}
      data-pattern={KIND_PATTERN[kind]}
    >
      {kind === "input" && <rect width={TILE} height={TILE} fill={ink} />}
      {kind === "output" && (
        <>
          <rect width={TILE} height={TILE} fill={ink} fillOpacity="0.18" />
          <path d="M-1 1 L1 -1 M0 6 L6 0 M5 7 L7 5" stroke={ink} strokeWidth="1.6" fill="none" />
        </>
      )}
      {kind === "cache_read" && (
        <>
          <rect width={TILE} height={TILE} fill={ink} fillOpacity="0.18" />
          <circle cx="3" cy="3" r="1.4" fill={ink} />
        </>
      )}
      {kind === "cache_write" && (
        <>
          <rect width={TILE} height={TILE} fill={ink} fillOpacity="0.18" />
          <rect y="1" width={TILE} height="1.6" fill={ink} />
          <rect y="4" width={TILE} height="1.6" fill={ink} />
        </>
      )}
    </pattern>
  );
}

interface NoRecordsRun {
  label: string;
  x: number;
  width: number;
}

/** Neighbouring no-records buckets with the same label become one run, so the label shows once. */
function noRecordsRuns(bars: StackedBar[], slots: Slot[]): NoRecordsRun[] {
  const runs: NoRecordsRun[] = [];
  let current: { label: string; first: number; last: number } | null = null;
  const close = () => {
    if (current === null) return;
    const first = slots[current.first];
    const last = slots[current.last];
    if (first !== undefined && last !== undefined) {
      runs.push({ label: current.label, x: first.x, width: last.x + last.width - first.x });
    }
    current = null;
  };
  bars.forEach((bar, index) => {
    if (bar.noRecords === undefined) {
      close();
    } else if (current?.label === bar.noRecords) {
      current.last = index;
    } else {
      close();
      current = { label: bar.noRecords, first: index, last: index };
    }
  });
  close();
  return runs;
}

/**
 * Cost or tokens over time, stacked by model (components.md entry 20). It draws what it is given:
 * the page turns its answer into buckets, ticks and labels. A model segment can split into the
 * four kinds, drawn with patterns kp1 to kp4 filled with currentColor in the model colour, so a
 * kind is a pattern plus legend text and never a colour. The picture is an SVG image named by the
 * caller's summary. Every label is HTML, and the legend with totals (and the kinds line) is the
 * text alternative, so the tick and x labels are hidden from assistive tech.
 *
 * A bucket can be open (holds now), partial, or have no records. No records draws no bar and shows
 * the caller's label, never a zero bar. A part with no price draws as a dashed stub. Cost charts
 * never use the --rk ramp. Kinds are told apart by pattern, as the accessibility floor requires.
 * It heads the lane list on the card, never inside a well (tokens.css, axis rule).
 */
export function StackedBars({
  bars,
  models,
  yTicks,
  xLabels,
  legend,
  kindsLine,
  kindsLabel,
  axisLabel,
  summary,
  guttered = false,
  nowLabel,
  className,
}: StackedBarsProps) {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");
  const { ref, width } = useElementWidth<HTMLDivElement>(FALLBACK_WIDTH);
  const shown = bars.filter((bar) => bar.noRecords === undefined);
  const sums = shown.map((bar) => models.reduce((sum, model) => sum + valueOf(bar, model), 0));
  const hasStub = shown.some((bar) => models.some((model) => bar.byModel[model] === null));
  // Room for the stub on the tallest bar, so it never leaves the plot.
  const plotHeight = hasStub ? PLOT_HEIGHT - STUB_HEIGHT - STACK_GAP : PLOT_HEIGHT;
  // The scale follows the data and the ticks. A floor of 1 would squash a chart of cents into its
  // bottom sixth and pile the tick labels up, so only a chart with nothing to show falls back to 1.
  const peak = Math.max(...yTicks.map((tick) => tick.value), ...sums);
  const top = (peak > 0 ? peak : 1) * HEADROOM;
  const slots = layoutBars(bars, width);
  const usedModels = models.filter((model) => shown.some((bar) => valueOf(bar, model) > 0));
  const kindModels = models.filter((model) =>
    shown.some((bar) => splitKinds(bar, model, 0, 1).length > 0),
  );
  const labels = fitLabels(xLabels, width);
  const hasHatch = shown.some((bar) => bar.open === true);
  const runs = noRecordsRuns(bars, slots);
  const openIndex = nowLabel === undefined ? -1 : bars.findIndex((bar) => bar.open === true);
  const openSlot = openIndex < 0 ? undefined : slots[openIndex];
  const nowX =
    openSlot === undefined
      ? null
      : openSlot.x +
        openSlot.width * (openIndex === bars.length - 1 ? 1 : (bars[openIndex]?.openFrac ?? 1));

  return (
    <div className={cx("bars", guttered && "bars-guttered", className)}>
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
            {(hasHatch || kindModels.length > 0) && (
              <defs>
                {hasHatch &&
                  usedModels.map((model) => (
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
                {kindModels.flatMap((model) =>
                  BAR_KINDS.map((kind) => (
                    <KindPattern
                      key={`${model}-${kind}`}
                      id={`${uid}-${KIND_PATTERN[kind]}-${model}`}
                      kind={kind}
                      className={`bars-ink-${model}`}
                    />
                  )),
                )}
              </defs>
            )}
            {yTicks.map((tick) => {
              const y = PLOT_HEIGHT - (tick.value / top) * plotHeight;
              return (
                <line key={tick.value} className="bars-grid" x1="0" x2={width} y1={y} y2={y} />
              );
            })}
            {runs.map((run) => (
              <line
                key={`none-${String(run.x)}`}
                className="bars-none-line"
                x1={run.x + run.width + BAR_GAP / 2}
                x2={run.x + run.width + BAR_GAP / 2}
                y1="0"
                y2={PLOT_HEIGHT}
              />
            ))}
            {bars.map((bar, index) => {
              const slot = slots[index];
              if (slot === undefined || bar.noRecords !== undefined || bar.future === true) {
                return null;
              }
              const open = bar.open === true;
              const parts = stackBar(bar, models, top, plotHeight);
              const stackTop = Math.min(PLOT_HEIGHT, ...parts.map((part) => part.y));
              return (
                <g
                  key={bar.key}
                  data-bar={bar.key}
                  data-open={open ? "true" : undefined}
                  data-partial={bar.partial === true ? "true" : undefined}
                >
                  {parts.map((part) => {
                    if (part.unpriced) {
                      return (
                        <rect
                          key={`${part.model}-stub`}
                          className="bars-stub"
                          data-unpriced={part.model}
                          x={slot.x + 0.5}
                          y={part.y + 0.5}
                          width={Math.max(0, slot.width - 1)}
                          height={part.height - 1}
                        />
                      );
                    }
                    const slices = splitKinds(bar, part.model, part.y, part.height);
                    if (slices.length > 0) {
                      return (
                        <g key={part.model} data-model={part.model}>
                          {slices.map((slice) => (
                            <rect
                              key={slice.kind}
                              className="bars-kind"
                              data-kind={slice.kind}
                              fill={`url(#${uid}-${KIND_PATTERN[slice.kind]}-${part.model})`}
                              x={slot.x}
                              y={slice.y}
                              width={slot.width}
                              height={slice.height}
                            />
                          ))}
                          {open && (
                            <rect
                              className={`bars-outline bars-stroke-${part.model}`}
                              x={slot.x + 0.75}
                              y={part.y + 0.75}
                              width={Math.max(0, slot.width - 1.5)}
                              height={Math.max(0, part.height - 1.5)}
                            />
                          )}
                        </g>
                      );
                    }
                    return open && part.height > 2 && slot.width > 2 ? (
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
                    );
                  })}
                  {bar.partial === true && parts.length > 0 && (
                    <rect
                      className="bars-partial"
                      x={slot.x + 0.5}
                      y={stackTop + 0.5}
                      width={Math.max(0, slot.width - 1)}
                      height={Math.max(0, PLOT_HEIGHT - stackTop - 1)}
                    />
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
              style={{
                bottom: guttered
                  ? `${String((tick.value / top) * (plotHeight / PLOT_HEIGHT) * 100)}%`
                  : `calc(${String((tick.value / top) * (plotHeight / PLOT_HEIGHT) * 100)}% + 1px)`,
              }}
            >
              {tick.label}
            </span>
          ))}
          {runs.map((run) => {
            if (run.width >= NONE_WIDE) {
              return (
                <span
                  key={`label-${String(run.x)}`}
                  className="bars-none-label bars-none-wide"
                  style={{ left: `${String(run.x)}px`, width: `${String(run.width)}px` }}
                >
                  <span>{run.label}</span>
                </span>
              );
            }
            // A run too narrow for its words hangs them on one line past the divider, at the top
            // of the plot, where the headroom over the tallest bar keeps them clear.
            return (
              <span
                key={`label-${String(run.x)}`}
                className="bars-none-label bars-none-edge"
                style={{ left: `${String(run.x + run.width + 2 * BAR_GAP)}px` }}
              >
                <span>{run.label}</span>
              </span>
            );
          })}
          {nowX !== null && nowLabel !== undefined && (
            <span className="bars-now" aria-hidden="true" style={{ left: `${String(nowX)}px` }}>
              <span>{nowLabel}</span>
            </span>
          )}
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
      {kindsLine !== undefined && kindsLine.length > 0 && (
        <ul
          className="bars-kinds"
          {...(kindsLabel !== undefined ? { "aria-label": kindsLabel } : {})}
        >
          {kindsLine.map((entry) => {
            const swatchId = `${uid}-lk-${KIND_PATTERN[entry.kind]}`;
            return (
              <li key={entry.kind} data-kind={entry.kind}>
                <svg
                  className="bars-kind-swatch"
                  width="16"
                  height="12"
                  aria-hidden="true"
                  focusable="false"
                >
                  <defs>
                    <KindPattern id={swatchId} kind={entry.kind} className="bars-ink-neutral" />
                  </defs>
                  <rect width="16" height="12" fill={`url(#${swatchId})`} />
                </svg>
                {entry.label} <b className="num">{entry.total}</b>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

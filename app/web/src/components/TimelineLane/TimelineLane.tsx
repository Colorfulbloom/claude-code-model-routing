import { useId } from "react";
import { useReducedMotion } from "@/lib/reduced-motion";
import { cx } from "../cx";
import { Badge } from "../Badge/Badge";
import { ModelSwatch, type Model } from "../ModelSwatch/ModelSwatch";
import { RunStateGlyph } from "../RunStateGlyph/RunStateGlyph";
import "./TimelineLane.css";

export const states = [
  "busy",
  "idle",
  "not-started",
  "unlinked-may",
  "unlinked-never",
  "unpriced-least",
  "unpriced-none",
  "folded",
  "open",
  "depth-cap",
  "moved",
  // Replay (Session review)
  "hollow",
  "not-yet",
  "later-folded",
  "later-open",
] as const;

/** A stretch of the axis, as fractions from 0 (start) to 1 (end). */
export interface LaneSegment {
  start: number;
  end: number;
}

export type LaneCost =
  | { kind: "cost"; text: string }
  /** Some requests have no price, so the cost is a lower bound. `text` is the whole phrase, such as "at least $1.20". */
  | { kind: "least"; text: string }
  /**
   * No request has a price. `text` is what the cell shows, "No price". `full` is the whole phrase,
   * such as "No price for Fable 5.1", kept for screen readers and the tooltip.
   */
  | { kind: "none"; text: string; full?: string };

export interface LaneRun {
  kind: "run";
  /** The row's DOM id. A fold's `controls` names these ids. */
  id: string;
  name: string;
  /** Indent levels, already capped by the page (3 at 1440, 2 at 375). */
  depth: number;
  /** The whole phrase, such as "Started by judge". Set when the cap hides the real nesting. */
  startedBy?: string;
  /** No swatch when the model is unknown. */
  model: Model | null;
  modelLabel: string;
  effortLabel: string | null;
  state: "working" | "idle" | "finished" | "not_started";
  stateWord: string;
  /** "Last request 2 s ago" or "Ran 3 min". The row's own words carry the times. */
  ageLine: string;
  tokens: string;
  cost: LaneCost;
  segments: LaneSegment[];
  /** Round marks from round 2 on. `at` is a fraction of the axis. */
  rounds: { at: number; label: string }[];
  /** "Finding starter" while a link may still arrive, "No starter found" once it cannot. */
  unlinked: null | { kind: "may" | "never"; label: string };
  /** Moved under its starter a moment ago. Rings the row for about 2 seconds. */
  moved: boolean;
  /** The last segment is still open and runs to Now. */
  reachesNow: boolean;
}

export interface LaneFold {
  kind: "fold";
  id: string;
  depth: number;
  /** "{n} finished earlier". */
  label: string;
  expanded: boolean;
  /** "Show" or "Hide". */
  toggleLabel: string;
  /**
   * The button's full accessible name, such as "Show 4 runs that start later under deep-reasoner".
   * It starts with the visible label. Without it the button reads its label and the group's name
   * describes it.
   */
  toggleAria?: string;
  onToggle: () => void;
  /** Space-separated ids of the rows the button shows or hides (the `id` of each LaneRun). */
  controls: string;
  /** The folded runs' bars, drawn in muted grey. */
  segments?: LaneSegment[];
  tokens?: string;
  cost?: LaneCost;
  /** The state word for the group, such as "Finished". */
  stateWord?: string;
  /**
   * A "starts later" group in replay: every run in it has not started at the cut. It reads as not
   * started (muted name, "Not started yet" glyph) where an earlier fold reads as finished.
   */
  later?: boolean;
}

export interface TimelineLaneProps {
  /** Grid lines at each tick strictly inside the axis. `nowFrac` is where Now sits, or null once the session ended. */
  axis: { ticks: { frac: number; label: string }[]; nowFrac: number | null };
  /** In display order. Nesting comes from `depth`. */
  items: (LaneRun | LaneFold)[];
  /**
   * Replay only. Where the cut line sits, as a fraction of the axis (0 to 1), for Session review's
   * "Who worked when". The page works out the fraction from T and the axis. With a cut, each bar
   * splits there. The part before it draws solid and the part after draws hollow. Round marks
   * after it are left out, and a bar that reaches Now is not drawn open. Rows not started at T,
   * and every per-row value at T, come from the caller. Without `cut` the lane is Live's.
   */
  cut?: number;
  /** The explanatory line under the list. */
  note: string;
  /** The list's accessible name, such as "Who is working". */
  label: string;
  /** Said after each row's token count, such as "tokens". Without it a screen reader hears only "1.9M". */
  tokensWord?: string;
  className?: string;
}

const INDENT = 16;

const pct = (frac: number): string => `${String(Math.min(1, Math.max(0, frac)) * 100)}%`;

function modelClass(model: Model | null): string {
  return model === null ? "lane-seg-plain" : `lane-seg-${model}`;
}

function CostCell({ cost }: { cost: LaneCost }) {
  if (cost.kind === "none") {
    if (cost.full === undefined) return <span className="lane-cost-none">{cost.text}</span>;
    return (
      <span className="lane-cost-none" title={cost.full}>
        <span aria-hidden="true">{cost.text}</span>
        <span className="sr-only">{cost.full}</span>
      </span>
    );
  }
  if (cost.kind === "least") {
    // The amount is the last word, drawn at full size. The words before it stay small and muted.
    const split = /^(.*\s)(\S+)$/.exec(cost.text);
    if (split?.[1] !== undefined && split[2] !== undefined) {
      return (
        <span className="lane-cost-least">
          {split[1]}
          <b>{split[2]}</b>
        </span>
      );
    }
    return <span className="lane-cost-least">{cost.text}</span>;
  }
  return <>{cost.text}</>;
}

function Guides({ depth, dashed }: { depth: number; dashed: boolean }) {
  return Array.from({ length: Math.max(0, depth) }, (_, i) => {
    const last = i === depth - 1;
    return (
      <span
        key={i}
        className={cx(
          "lane-guide",
          last && "lane-guide-elbow",
          last && dashed && "lane-guide-dashed",
        )}
        aria-hidden="true"
        style={{ left: `${String(i * INDENT + 7)}px` }}
      />
    );
  });
}

interface DrawnSegment extends LaneSegment {
  /** After the cut: drawn hollow. */
  after: boolean;
  /** Before the cut, and the bar goes on past it: the end at the cut is square. */
  atCut: boolean;
}

/** Splits each segment at the cut. A bar that crosses it becomes a solid part and a hollow part. */
function splitAtCut(segments: LaneSegment[], cut: number | undefined): DrawnSegment[] {
  if (cut === undefined) return segments.map((s) => ({ ...s, after: false, atCut: false }));
  return segments.flatMap((segment) => {
    const out: DrawnSegment[] = [];
    if (segment.start < cut) {
      out.push({
        start: segment.start,
        end: Math.min(segment.end, cut),
        after: false,
        atCut: segment.end > cut,
      });
    }
    if (segment.end > cut) {
      out.push({
        start: Math.max(segment.start, cut),
        end: segment.end,
        after: true,
        atCut: false,
      });
    }
    return out;
  });
}

function Track({
  segments,
  rounds,
  ticks,
  model,
  fold,
  openEnd,
  nowFrac,
  cut,
}: {
  segments: LaneSegment[];
  rounds: { at: number; label: string }[];
  ticks: number[];
  model: Model | null;
  fold: boolean;
  openEnd: boolean;
  nowFrac: number | null;
  cut: number | undefined;
}) {
  const drawn = splitAtCut(segments, cut);
  // In replay no bar is open: the line at the cut stands where Now stands on Live.
  const open = cut === undefined && openEnd;
  const shownRounds = cut === undefined ? rounds : rounds.filter((round) => round.at <= cut);
  return (
    <div className="lane-track" aria-hidden="true">
      {ticks.map((frac) => (
        <b key={frac} className="lane-gridline" style={{ left: pct(frac) }} />
      ))}
      {drawn.map((segment, i) => {
        const isOpen = open && i === drawn.length - 1;
        // A segment that reaches Now ends exactly on the Now line.
        const end = isOpen && nowFrac !== null ? Math.max(segment.end, nowFrac) : segment.end;
        return (
          <span
            key={`${String(segment.start)}-${String(segment.end)}-${String(segment.after)}`}
            className={cx(
              "lane-seg",
              fold ? "lane-seg-fold" : modelClass(model),
              isOpen && "lane-seg-open",
              segment.after && "lane-seg-after",
              segment.atCut && "lane-seg-cut",
            )}
            style={{ left: pct(segment.start), width: `max(4px, ${pct(end - segment.start)})` }}
          />
        );
      })}
      {cut !== undefined && <i className="lane-cut" style={{ left: pct(cut) }} />}
      {shownRounds.map((round) => (
        <span
          key={`${String(round.at)}-${round.label}`}
          className={cx("lane-round", round.at > 0.85 && "lane-round-end")}
          style={round.at > 0.85 ? { right: pct(1 - round.at) } : { left: pct(round.at) }}
        >
          {round.label}
        </span>
      ))}
    </div>
  );
}

function RunRow({
  run,
  ticks,
  nowFrac,
  reducedMotion,
  tokensWord,
  cut,
}: {
  run: LaneRun;
  ticks: number[];
  nowFrac: number | null;
  reducedMotion: boolean;
  tokensWord: string | undefined;
  cut: number | undefined;
}) {
  const ringed = run.moved && !reducedMotion;
  return (
    <li
      id={run.id}
      className={cx(
        "lane-row",
        run.state === "not_started" && "lane-row-future",
        run.unlinked !== null && "lane-row-unlinked",
        ringed && "lane-row-moved",
      )}
      aria-level={run.depth + 1}
      data-moved={run.moved ? "true" : undefined}
      style={{ "--lane-ind": `${String(run.depth * INDENT)}px` } as React.CSSProperties}
    >
      <div className="lane-grid">
        <Guides depth={run.depth} dashed={run.unlinked !== null} />
        <div className="lane-lab">
          <span className="lane-name-line">
            <span className="lane-name">{run.name}</span>
            {run.unlinked !== null && <Badge className="lane-unlinked">{run.unlinked.label}</Badge>}
          </span>
          <span className="lane-model">
            {run.model !== null && <ModelSwatch model={run.model} />}
            {run.modelLabel}
            {run.effortLabel !== null && ` · ${run.effortLabel}`}
          </span>
          {run.startedBy !== undefined && <span className="lane-by">{run.startedBy}</span>}
        </div>
        <Track
          segments={run.segments}
          rounds={run.rounds}
          ticks={ticks}
          model={run.model}
          fold={false}
          openEnd={run.reachesNow}
          nowFrac={nowFrac}
          cut={cut}
        />
        <div className="lane-state">
          <RunStateGlyph state={run.state}>{run.stateWord}</RunStateGlyph>
          <small>{run.ageLine}</small>
        </div>
        <span className="lane-tokens num">
          {run.tokens}
          {tokensWord !== undefined && <span className="sr-only"> {tokensWord}</span>}
        </span>
        <span className="lane-cost num">
          <CostCell cost={run.cost} />
        </span>
      </div>
    </li>
  );
}

function FoldRow({
  fold,
  ticks,
  tokensWord,
  cut,
}: {
  fold: LaneFold;
  ticks: number[];
  tokensWord: string | undefined;
  cut: number | undefined;
}) {
  const nameId = useId();
  return (
    <li
      id={fold.id}
      className={cx("lane-row", "lane-row-fold", fold.later === true && "lane-row-future")}
      aria-level={fold.depth + 1}
      style={{ "--lane-ind": `${String(fold.depth * INDENT)}px` } as React.CSSProperties}
    >
      <div className="lane-grid">
        <Guides depth={fold.depth} dashed={false} />
        <div className="lane-lab lane-lab-fold">
          <span id={nameId} className="lane-name lane-fold-name">
            {fold.label}
          </span>
          <button
            type="button"
            className="lane-fold-button"
            aria-expanded={fold.expanded}
            aria-controls={fold.controls}
            aria-label={fold.toggleAria}
            aria-describedby={nameId}
            onClick={fold.onToggle}
          >
            {fold.toggleLabel}
          </button>
        </div>
        <Track
          segments={fold.segments ?? []}
          rounds={[]}
          ticks={ticks}
          model={null}
          fold
          openEnd={false}
          nowFrac={null}
          cut={cut}
        />
        <div className="lane-state">
          {fold.stateWord !== undefined && (
            <RunStateGlyph state={fold.later === true ? "not_started" : "finished"}>
              {fold.stateWord}
            </RunStateGlyph>
          )}
        </div>
        <span className="lane-tokens num">
          {fold.tokens}
          {fold.tokens !== undefined && tokensWord !== undefined && (
            <span className="sr-only"> {tokensWord}</span>
          )}
        </span>
        <span className="lane-cost num">
          {fold.cost !== undefined && <CostCell cost={fold.cost} />}
        </span>
      </div>
    </li>
  );
}

/**
 * One row per run, in display order, on a shared time axis (components.md entry 22). The page
 * works out every fraction, label and cap, so nothing here does time math.
 *
 * The list is flat. Rows come in display order with their (capped) `depth`, and each carries
 * `aria-level`. A nested list per level would need the component to rebuild a tree from depths,
 * and a fold's revealed rows are siblings that follow it, not children it owns. The visible tree
 * (indent and guide lines) comes from `depth`, and "Started by" says who a deep row belongs to.
 *
 * Session review draws the same lane with a `cut` (replay). Segments after the cut draw hollow,
 * and the page passes the values at T, so the component still does no time math. A "starts later"
 * group is a fold with `later` set.
 *
 * Rows are not links in M2. The tracks are hidden from assistive tech, because each row's own
 * words (state, age, tokens, cost) carry the times and totals.
 */
export function TimelineLane({
  axis,
  items,
  cut,
  note,
  label,
  tokensWord,
  className,
}: TimelineLaneProps) {
  const reducedMotion = useReducedMotion();
  const ticks = axis.ticks.map((tick) => tick.frac).filter((frac) => frac > 0 && frac < 1);
  return (
    <div className={cx("lane", className)}>
      {/* eslint-disable-next-line jsx-a11y/no-redundant-roles -- Safari drops list semantics once list-style is none */}
      <ul className="lane-list" role="list" aria-label={label}>
        {items.map((item) =>
          item.kind === "fold" ? (
            <FoldRow key={item.id} fold={item} ticks={ticks} tokensWord={tokensWord} cut={cut} />
          ) : (
            <RunRow
              key={item.id}
              run={item}
              ticks={ticks}
              nowFrac={axis.nowFrac}
              reducedMotion={reducedMotion}
              tokensWord={tokensWord}
              cut={cut}
            />
          ),
        )}
      </ul>
      <p className="lane-note">{note}</p>
    </div>
  );
}

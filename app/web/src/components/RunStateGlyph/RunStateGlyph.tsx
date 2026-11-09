import { cx } from "../cx";
import "./RunStateGlyph.css";

export const states = ["working", "done", "idle", "failed"] as const;

export type RunState = (typeof states)[number];

export interface RunStateGlyphProps {
  state: RunState;
  /** The word that goes with the glyph. A run state is never a glyph alone. */
  children: React.ReactNode;
  className?: string;
}

/**
 * Plain glyph plus word for a run state (components.md entry 11). It has no pill, so it never reads
 * as a setting status. Idle and Not started yet share the dotted ring.
 */
export function RunStateGlyph({ state, children, className }: RunStateGlyphProps) {
  return <span className={cx("run-state", `run-state-${state}`, className)}>{children}</span>;
}

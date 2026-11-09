import { t } from "@/strings/t";
import { cx } from "../cx";
import "./RunDots.css";

export const states = ["mixed", "working", "capped"] as const;

/** At most this many dots show. The rest read "+{n}". */
export const DOT_CAP = 8;

export interface RunDotsProps {
  /** Runs still working. Each is a filled dot, drawn first. */
  working: number;
  /** Runs that finished. Each is a ringed check. */
  finished: number;
  className?: string;
}

/** One dot per run state for the agents tile (components.md entry 18), hidden from assistive tech. */
export function RunDots({ working, finished, className }: RunDotsProps) {
  const on = Math.min(Math.max(0, working), DOT_CAP);
  const ok = Math.min(Math.max(0, finished), DOT_CAP - on);
  const more = Math.max(0, working) + Math.max(0, finished) - on - ok;
  return (
    <div className={cx("run-dots", className)} aria-hidden="true">
      {Array.from({ length: on }, (_, index) => (
        <i key={`on${String(index)}`} className="run-dot run-dot-working" />
      ))}
      {Array.from({ length: ok }, (_, index) => (
        <i key={`ok${String(index)}`} className="run-dot run-dot-finished" />
      ))}
      {more > 0 && <span className="run-dots-more">{t("t_agents_more", { n: more })}</span>}
    </div>
  );
}

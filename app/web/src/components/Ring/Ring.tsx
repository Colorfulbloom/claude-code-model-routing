import { cx } from "../cx";
import "./Ring.css";

export const states = ["partial", "empty", "full"] as const;

export interface RingProps {
  /** 0 to 100. Values outside the range are clamped. */
  percent: number;
  className?: string;
}

/**
 * A percentage ring proof for a tile (components.md entry 18). It is hidden from assistive tech,
 * because the tile's text carries the number.
 */
export function Ring({ percent, className }: RingProps) {
  const shown = Math.min(100, Math.max(0, Number.isFinite(percent) ? percent : 0));
  return (
    <svg className={cx("ring", className)} viewBox="0 0 44 44" aria-hidden="true" focusable="false">
      <circle className="ring-track" cx="22" cy="22" r="18.5" />
      {shown > 0 && (
        <circle
          className="ring-fill"
          cx="22"
          cy="22"
          r="18.5"
          pathLength="100"
          strokeDasharray={`${String(shown)} 100`}
          transform="rotate(-90 22 22)"
        />
      )}
    </svg>
  );
}

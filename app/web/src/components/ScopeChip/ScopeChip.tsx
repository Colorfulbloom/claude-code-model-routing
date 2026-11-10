import { cx } from "../cx";
import "./ScopeChip.css";

export const states = ["default", "wrap", "truncated"] as const;

export interface ScopeChipProps {
  /** The scope, such as "Project local". It is in medium weight. */
  scope: string;
  /** The value that scope holds, such as "high". It wraps onto a second line and never clips. */
  value: string;
  /**
   * Cuts the value short with an ellipsis, for a name that can be long, such as a plugin's. The
   * full text stays in the DOM, so the accessible name keeps all of it, and the chip's title shows
   * it on hover.
   */
  truncate?: boolean;
  className?: string;
}

/**
 * Scope plus value under a setup-map row at 375 (components.md entry 12): the badge's pill with
 * the scope in medium weight, then the value. It is plain text in one box, so a screen reader
 * reads "Project local high" whether the value sits on the first line or the second.
 */
export function ScopeChip({ scope, value, truncate = false, className }: ScopeChipProps) {
  return (
    <span
      className={cx("scope-chip", truncate && "scope-chip-truncate", className)}
      {...(truncate ? { title: `${scope} ${value}` } : {})}
    >
      <span className="scope-chip-scope">{scope}</span>{" "}
      <span className="scope-chip-value">{value}</span>
    </span>
  );
}

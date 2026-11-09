import { cx } from "../cx";
import "./Badge.css";

export const states = ["default"] as const;

export interface BadgeProps {
  children: React.ReactNode;
  className?: string;
}

/**
 * A neutral fact about an item (components.md entry 12): an outlined pill with muted text. The
 * unlinked "Finding starter" and "No starter found" badges look the same (m2.css draws the dashed
 * line on the tree, not on the badge).
 */
export function Badge({ children, className }: BadgeProps) {
  return <span className={cx("badge", className)}>{children}</span>;
}

import { cx } from "../cx";
import "./Well.css";

export const states = ["default", "list", "flush"] as const;

export interface WellProps extends React.ComponentPropsWithoutRef<"div"> {
  /** List wells set horizontal padding only. Flush wells (diffs, editors) set none. */
  variant?: "default" | "list" | "flush";
}

/** Holds data inside a card: plots, tables, row lists, diffs (components.md entry 6). */
export function Well({ variant = "default", className, children, ...rest }: WellProps) {
  return (
    <div className={cx("well", variant !== "default" && `well-${variant}`, className)} {...rest}>
      {children}
    </div>
  );
}

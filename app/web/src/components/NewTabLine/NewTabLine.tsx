import { cx } from "../cx";
import "./NewTabLine.css";

export const states = ["default"] as const;

export interface NewTabLineProps {
  /** "Your other tab is open again on Agents, builder." */
  children: React.ReactNode;
  className?: string;
}

/** A polite notice above the h1 on the page a new link opens, when the other tab is back. */
export function NewTabLine({ children, className }: NewTabLineProps) {
  return (
    <p className={cx("new-tab-line", className)} role="status">
      <span className="new-tab-line-mark" aria-hidden="true">
        {"✓"}
      </span>
      <span>{children}</span>
    </p>
  );
}

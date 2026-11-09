import { cx } from "../cx";
import { Button } from "../Button/Button";
import "../Card/Card.css";
import "./EmptyState.css";

export const states = ["page", "page-neutral", "inline"] as const;

export interface EmptyStateProps {
  /** Page-level is a card with a check mark. Inline is a sentence and a button, for lists and tables. */
  variant?: "page" | "inline";
  /** The page-level mark. "done" is the check, "neutral" is an ellipsis with no status colour. */
  mark?: "done" | "neutral";
  /** Heading for the page-level variant. */
  title?: string;
  /** Says what will appear. */
  children: React.ReactNode;
  action?: { label: string; href?: string; onPress?: () => void };
  className?: string;
}

/** Says what will appear and offers the action that fills it (components.md entry 33). */
export function EmptyState({
  variant = "inline",
  mark = "done",
  title,
  children,
  action,
  className,
}: EmptyStateProps) {
  const button =
    action !== undefined ? (
      <Button
        {...(action.href !== undefined ? { href: action.href } : {})}
        {...(action.onPress !== undefined ? { onPress: action.onPress } : {})}
      >
        {action.label}
      </Button>
    ) : null;

  if (variant === "page") {
    return (
      <section className={cx("card", "empty-page", className)}>
        <span className={cx("empty-page-mark", `is-${mark}`)} aria-hidden="true" />
        {title !== undefined && <h2 className="empty-page-title">{title}</h2>}
        <p className="muted">{children}</p>
        {button}
      </section>
    );
  }
  return (
    <div className={cx("empty-inline", className)}>
      <p>{children}</p>
      {button}
    </div>
  );
}

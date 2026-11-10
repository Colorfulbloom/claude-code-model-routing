import { useId } from "react";
import { Link } from "react-aria-components";
import { cx } from "../cx";
import "./Button.css";

export const states = ["default", "hover", "focus", "pressed", "disabled", "busy"] as const;

export type ButtonVariant = "primary" | "secondary" | "quiet" | "danger" | "icon";

export interface ButtonProps {
  variant?: ButtonVariant;
  children: React.ReactNode;
  /** Makes the button a link that looks like a button. */
  href?: string;
  onPress?: () => void;
  /** Disabled stays focusable (aria-disabled). A disabled button needs a visible reason. */
  disabled?: boolean;
  disabledReason?: string;
  /** Busy swaps the label to busyLabel and sets aria-busy. */
  busy?: boolean;
  busyLabel?: string;
  /** Required for the icon variant. */
  ariaLabel?: string;
  /** Id of a visible line that explains the button, such as the Pager's why-line. Joins the reason id. */
  describedBy?: string;
  /** Extra classes. The component sheet uses is-hover, is-focus and is-pressed to force a state. */
  className?: string;
}

/**
 * Starts an action. One variant per intent, see components.md entry 9.
 * It renders a native button, not the React Aria Button, because the disabled and busy states
 * must stay focusable with aria-disabled and aria-busy, and React Aria's Button drops both
 * attributes. A link-style button uses the React Aria Link so it follows the router.
 */
export function Button({
  variant = "secondary",
  children,
  href,
  onPress,
  disabled = false,
  disabledReason,
  busy = false,
  busyLabel,
  ariaLabel,
  describedBy,
  className,
}: ButtonProps) {
  const reasonId = useId();
  const blocked = disabled || busy;
  const hasReason = disabled && disabledReason !== undefined;
  const classes = cx("button", `button-${variant}`, className);
  const describedIds = [hasReason ? reasonId : undefined, describedBy].filter(
    (id): id is string => id !== undefined,
  );
  const label = busy && busyLabel !== undefined ? busyLabel : children;

  const control =
    href !== undefined && !blocked ? (
      <Link
        className={classes}
        href={href}
        {...(ariaLabel !== undefined ? { "aria-label": ariaLabel } : {})}
      >
        {label}
      </Link>
    ) : (
      <button
        type="button"
        className={classes}
        aria-label={ariaLabel}
        aria-disabled={blocked ? "true" : undefined}
        aria-busy={busy ? "true" : undefined}
        aria-describedby={describedIds.length > 0 ? describedIds.join(" ") : undefined}
        onClick={() => {
          if (!blocked) onPress?.();
        }}
      >
        {label}
      </button>
    );

  if (!hasReason) return control;
  return (
    <span className="button-group">
      {control}
      <span id={reasonId} className="button-reason">
        {disabledReason}
      </span>
    </span>
  );
}

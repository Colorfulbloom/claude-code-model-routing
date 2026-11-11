import { cx } from "../cx";
import "./PhoneActionBar.css";

export const states = ["default", "with-link", "button-only"] as const;

export interface PhoneActionBarProps {
  /** The file and the change, such as "settings.local.json, xhigh → medium". It sits above the button. */
  summary?: React.ReactNode;
  /** A link beside the summary, such as one that shows the whole file. */
  aside?: React.ReactNode;
  /** The primary action. The bar stretches it to the full width. */
  children: React.ReactNode;
  className?: string;
}

/**
 * The bar that keeps the primary action in reach at 720px and under (components.md entry 49): a
 * sticky foot with a one-line note on what the save does to which file, and the primary button at
 * full width. The foot of the edit sheet uses it for Save, and the agent form (M6b) uses it with a
 * link that shows the file. It clears the home indicator through the safe-area inset.
 */
export function PhoneActionBar({ summary, aside, children, className }: PhoneActionBarProps) {
  return (
    <div className={cx("phone-action-bar", className)}>
      {(summary !== undefined || aside !== undefined) && (
        <p className="phone-action-bar-note">
          {summary !== undefined && <span className="phone-action-bar-summary">{summary}</span>}
          {aside !== undefined && <span className="phone-action-bar-aside">{aside}</span>}
        </p>
      )}
      <div className="phone-action-bar-action">{children}</div>
    </div>
  );
}

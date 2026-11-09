import { Button } from "../Button/Button";
import { cx } from "../cx";
import "./RetryRow.css";

export const states = ["default", "loading"] as const;

export interface RetryRowProps {
  /** "Checking again every 10 seconds". */
  retryText: string;
  /** "Last answer at 3:42 PM", or the no-answer line. */
  lastText: string;
  tryLabel: string;
  /** The label while a request runs. */
  busyLabel: string;
  busy?: boolean;
  onTryNow: () => void;
  className?: string;
}

/** The server stopped page's retry row: a polite status and a Try now button (components.md, Gate page). */
export function RetryRow({
  retryText,
  lastText,
  tryLabel,
  busyLabel,
  busy = false,
  onTryNow,
  className,
}: RetryRowProps) {
  return (
    <div className={cx("retry-row", className)}>
      <p className="retry-row-text" role="status">
        <span className="retry-row-now">
          <span aria-hidden="true">{"↻"}</span> {retryText}
        </span>
        <span className="muted">{lastText}</span>
      </p>
      <Button busy={busy} busyLabel={busyLabel} onPress={onTryNow}>
        {tryLabel}
      </Button>
    </div>
  );
}

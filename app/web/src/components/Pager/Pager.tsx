import { useId } from "react";
import { Button } from "../Button/Button";
import { cx } from "../cx";
import "./Pager.css";

export const states = [
  "default",
  "hover",
  "focus",
  "earlier-disabled",
  "later-disabled",
  "both-disabled",
] as const;

export interface PagerProps {
  /** Names the group, such as "Cost chart window". */
  label: string;
  earlierLabel: string;
  laterLabel: string;
  /** The buttons' accessible names while they can move, such as "Show earlier costs, October 17 to October 23". */
  earlierAria?: string;
  laterAria?: string;
  /** The window as words, such as "September 1 to September 30". It sits in a polite live region. */
  windowLabel: string;
  onEarlier?: () => void;
  onLater?: () => void;
  /** At the oldest end. The button stays focusable (`aria-disabled`) and `earlierReason` says why. */
  earlierDisabled?: boolean;
  earlierReason?: string;
  /** At the newest end. */
  laterDisabled?: boolean;
  laterReason?: string;
  /** What the pager moves, such as "Moves this chart only. The tiles keep their range." */
  scopeNote?: string;
  /** Extra classes on both buttons. The component sheet uses is-hover and is-focus. */
  buttonClassName?: string;
  className?: string;
}

/**
 * Moves a chart's window to earlier or later data (components.md entry 21). It is chart-local, so
 * the tiles keep their own range. An end that can't move keeps its button focusable with
 * `aria-disabled` and a dashed `--border-strong` border, and a visible why-line is tied to it with
 * `aria-describedby`. The window label is a polite live region. Every word comes in through props.
 */
export function Pager({
  label,
  earlierLabel,
  laterLabel,
  earlierAria,
  laterAria,
  windowLabel,
  onEarlier,
  onLater,
  earlierDisabled = false,
  earlierReason,
  laterDisabled = false,
  laterReason,
  scopeNote,
  buttonClassName,
  className,
}: PagerProps) {
  const earlierId = useId();
  const laterId = useId();
  const earlierWhy = earlierDisabled && earlierReason !== undefined;
  const laterWhy = laterDisabled && laterReason !== undefined;
  return (
    <div className={cx("pager", className)} role="group" aria-label={label}>
      <div className="pager-row">
        <Button
          disabled={earlierDisabled}
          {...(onEarlier !== undefined ? { onPress: onEarlier } : {})}
          {...(earlierWhy ? { describedBy: earlierId } : {})}
          {...(earlierAria !== undefined && !earlierDisabled ? { ariaLabel: earlierAria } : {})}
          {...(buttonClassName !== undefined ? { className: buttonClassName } : {})}
        >
          <span aria-hidden="true">←</span>
          {earlierLabel}
        </Button>
        <span className="pager-window" role="status" aria-live="polite" aria-atomic="true">
          {windowLabel}
        </span>
        <Button
          disabled={laterDisabled}
          {...(onLater !== undefined ? { onPress: onLater } : {})}
          {...(laterWhy ? { describedBy: laterId } : {})}
          {...(laterAria !== undefined && !laterDisabled ? { ariaLabel: laterAria } : {})}
          {...(buttonClassName !== undefined ? { className: buttonClassName } : {})}
        >
          {laterLabel}
          <span aria-hidden="true">→</span>
        </Button>
      </div>
      {earlierWhy && (
        <p id={earlierId} className="pager-why">
          {earlierReason}
        </p>
      )}
      {laterWhy && (
        <p id={laterId} className="pager-why">
          {laterReason}
        </p>
      )}
      {scopeNote !== undefined && <p className="pager-note">{scopeNote}</p>}
    </div>
  );
}

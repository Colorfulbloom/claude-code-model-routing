import { cx } from "../cx";
import "./WaitHold.css";

export const states = ["default"] as const;

export interface WaitHoldProps {
  brand: string;
  /** The polite status, such as "Checking for another dashboard tab". Leave it out for a plain load. */
  status?: string;
  className?: string;
}

/**
 * The brand-only hold shown while a new tab asks the others for a key (components.md, Gate page).
 * The wordmark alone, centred, with no motion.
 */
export function WaitHold({ brand, status, className }: WaitHoldProps) {
  return (
    <div className={cx("wait-hold", className)}>
      <p className="wait-hold-brand">{brand}</p>
      {status !== undefined && (
        <p className="sr-only" role="status">
          {status}
        </p>
      )}
    </div>
  );
}

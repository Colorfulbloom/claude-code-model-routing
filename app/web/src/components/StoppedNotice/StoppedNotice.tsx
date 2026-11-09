import { cx } from "../cx";
import "./StoppedNotice.css";

export const states = ["default"] as const;

export interface StoppedNoticeProps {
  /** The one sentence. A path in it is wrapped in a code element by the caller. */
  children: React.ReactNode;
  /** "status" only when the notice appears after load. */
  role?: "status";
  className?: string;
}

/**
 * The updates-stopped strip (components.md entry 8, revised). A start edge and a ▲ in the
 * overridden colour, then one sentence. It takes role="status" only when it appears after load,
 * so it is announced once.
 */
export function StoppedNotice({ children, role, className }: StoppedNoticeProps) {
  return (
    <p className={cx("stopped-notice", className)} role={role}>
      <span className="stopped-notice-mark glyph" data-glyph="overridden" aria-hidden="true" />
      <span className="stopped-notice-text">{children}</span>
    </p>
  );
}

import { Link } from "react-aria-components";
import { cx } from "../cx";
import { StatusChip, type SettingStatus } from "../StatusChip/StatusChip";
import "./NoticeLine.css";

export const states = ["default", "with-link"] as const;

export type NoticeStatus =
  "in-effect" | "overridden" | "ignored" | "invalid" | "lowered" | "default" | "unknown";

export interface NoticeLineProps {
  status?: NoticeStatus;
  /** The word that goes with the mark, such as "Unknown". */
  statusWord: string;
  children: React.ReactNode;
  link?: { label: string; href: string };
  /** Use "status" only when the notice appears after load. */
  role?: "status";
  className?: string;
}

/** One fact that affects trust in the page, above the cards (components.md entry 8). */
export function NoticeLine({
  status = "unknown",
  statusWord,
  children,
  link,
  role,
  className,
}: NoticeLineProps) {
  return (
    <p className={cx("notice-line", className)} role={role}>
      <StatusChip className="notice-line-status" status={status.replace("-", "_") as SettingStatus}>
        {statusWord}
      </StatusChip>
      <span className="notice-line-text">{children}</span>
      {link !== undefined && (
        <Link className="notice-line-link" href={link.href}>
          {link.label}
        </Link>
      )}
    </p>
  );
}

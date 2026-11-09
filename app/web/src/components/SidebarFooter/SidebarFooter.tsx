import { cx } from "../cx";
import "./SidebarFooter.css";

export const states = ["default", "problem"] as const;

export interface SidebarFooterLine {
  id: string;
  text: string;
  /** A ▲ line in the overridden colour. */
  warn?: boolean;
}

export interface SidebarFooterProps {
  lines: SidebarFooterLine[];
  className?: string;
}

/**
 * The sidebar footer (components.md entry 53). Muted 12px lines, each on one line with an
 * ellipsis. They are plain text, never links and never live regions. The notice line announces.
 */
export function SidebarFooter({ lines, className }: SidebarFooterProps) {
  return (
    <div className={cx("sidebar-footer", className)}>
      {lines.map((line) => (
        <p key={line.id} className={cx("sidebar-footer-line", line.warn === true && "is-warn")}>
          {line.warn === true && (
            <span
              className="sidebar-footer-mark glyph"
              data-glyph="overridden"
              aria-hidden="true"
            />
          )}
          {line.text}
        </p>
      ))}
    </div>
  );
}

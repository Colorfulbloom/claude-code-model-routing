import { cx } from "../cx";
import { HelpTerm } from "../HelpTerm/HelpTerm";
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

/** The prices, backup and editing lines open their help entry, so their text is a help term. */
function LineText({ line }: { line: SidebarFooterLine }) {
  if (line.id === "prices") return <HelpTerm help="shell.prices">{line.text}</HelpTerm>;
  if (line.id === "backup") return <HelpTerm help="shell.backup">{line.text}</HelpTerm>;
  if (line.id === "editing") return <HelpTerm help="shell.editing">{line.text}</HelpTerm>;
  return line.text;
}

/**
 * The sidebar footer (components.md entry 53). Muted 12px lines, each on one row while it fits. A
 * line with a date wraps onto a second row, so a time is never cut off. They are plain text,
 * never links and never live regions. The notice line announces. The prices, backup and editing
 * lines are help terms, so they keep their words and add a dotted underline.
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
          <LineText line={line} />
        </p>
      ))}
    </div>
  );
}

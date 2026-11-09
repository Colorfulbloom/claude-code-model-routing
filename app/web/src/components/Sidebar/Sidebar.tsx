import { Link } from "react-aria-components";
import { Badge } from "../Badge/Badge";
import { cx } from "../cx";
import type { IconName } from "../icons";
import "./Sidebar.css";

export const states = ["default", "hover", "focus", "selected", "end-slot"] as const;

export interface SidebarItem {
  id: string;
  href: string;
  label: string;
  icon: IconName;
  current?: boolean;
  /** Working mark or count. The slot reserves its width even when this is empty. */
  end?: React.ReactNode;
  /** Full accessible name when the end slot holds a count, such as "To fix, 4 items". */
  name?: string;
  /** Extra classes. The component sheet uses is-hover and is-focus to force a state. */
  className?: string;
}

export interface SidebarGroup {
  id: string;
  heading?: string;
  items: SidebarItem[];
}

export interface SidebarProps {
  /** Accessible name of the nav landmark. */
  label: string;
  brand: string;
  /** A quiet mark after the brand, such as "Demo data". Left out on real data. */
  badge?: string;
  /** The project Select goes here. */
  projectSlot?: React.ReactNode;
  groups: SidebarGroup[];
  /** The footer block, such as SidebarFooter. */
  footer?: React.ReactNode;
  className?: string;
}

/** Main navigation at 721px and up (components.md entry 1). Group headings are text, not buttons. */
export function Sidebar({
  label,
  brand,
  badge,
  projectSlot,
  groups,
  footer,
  className,
}: SidebarProps) {
  return (
    <nav className={cx("sidebar", className)} aria-label={label}>
      <div className="brand">
        {brand}
        {badge !== undefined && <Badge className="brand-badge">{badge}</Badge>}
      </div>
      {projectSlot !== undefined && <div className="sidebar-slot">{projectSlot}</div>}
      {groups.map((group) => {
        const headingId = `sidebar-group-${group.id}`;
        return (
          <div className="sidebar-group" key={group.id}>
            {group.heading !== undefined && (
              <p className="sidebar-heading" id={headingId}>
                {group.heading}
              </p>
            )}
            <ul
              className="sidebar-list"
              aria-labelledby={group.heading !== undefined ? headingId : undefined}
            >
              {group.items.map((item) => (
                <li key={item.id}>
                  <Link
                    className={cx("sidebar-link", item.className)}
                    href={item.href}
                    {...(item.current === true ? { "aria-current": "page" as const } : {})}
                    {...(item.name !== undefined ? { "aria-label": item.name } : {})}
                  >
                    <span className="sidebar-icon" data-icon={item.icon} aria-hidden="true" />
                    <span className="sidebar-label">{item.label}</span>
                    {item.end !== undefined && <span className="sidebar-end">{item.end}</span>}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
      {footer}
    </nav>
  );
}

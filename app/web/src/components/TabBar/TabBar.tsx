import { Link } from "react-aria-components";
import { cx } from "../cx";
import type { IconName } from "../icons";
import "./TabBar.css";

export const states = ["default", "hover", "focus", "selected", "count"] as const;

export interface TabBarItem {
  id: string;
  href: string;
  label: string;
  icon: IconName;
  current?: boolean;
  /** Visible count badge. Pass `name` too, so the count is part of the accessible name. */
  count?: string;
  /** Full accessible name, such as "To fix, 4". Needed when there is a count. */
  name?: string;
  className?: string;
}

export interface TabBarProps {
  label: string;
  items: TabBarItem[];
  className?: string;
}

/** Phone navigation, five items, last in the DOM (components.md entry 2). */
export function TabBar({ label, items, className }: TabBarProps) {
  return (
    <nav className={cx("tab-bar", className)} aria-label={label}>
      {items.map((item) => (
        <Link
          key={item.id}
          className={cx("tab-bar-link", item.className)}
          href={item.href}
          {...(item.current === true ? { "aria-current": "page" as const } : {})}
          {...(item.name !== undefined ? { "aria-label": item.name } : {})}
        >
          <span className="tab-bar-icon" data-icon={item.icon} aria-hidden="true">
            {item.count !== undefined && <span className="tab-bar-count">{item.count}</span>}
          </span>
          <span
            className="tab-bar-label"
            aria-hidden={item.name !== undefined ? "true" : undefined}
          >
            {item.label}
          </span>
        </Link>
      ))}
    </nav>
  );
}

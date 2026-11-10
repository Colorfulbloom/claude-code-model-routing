import { Breadcrumb as RacBreadcrumb, Breadcrumbs, Link } from "react-aria-components";
import { cx } from "../cx";
import "./Breadcrumb.css";

export const states = ["default", "hover", "focus", "long", "hidden"] as const;

export interface BreadcrumbItem {
  /** Names the crumb in the route, so it must be unique in one trail. */
  id?: string;
  label: string;
  href: string;
  /** Extra classes. The component sheet uses is-hover and is-focus to force a state. */
  className?: string;
}

export interface BreadcrumbProps {
  /** Names the nav landmark, such as "Breadcrumb". */
  label: string;
  /** The trail, parent first. The last item is the current page. */
  items: BreadcrumbItem[];
  /** Hides the trail while a phone sheet is open, because the sheet header takes over. */
  hidden?: boolean;
  className?: string;
}

/**
 * The trail above a level-3 page's title (components.md entry 3). It is a `nav` with an
 * `aria-label` around React Aria's Breadcrumbs, which puts `aria-current="page"` on the last
 * item. The links get 26 px of height through their padding box. The caller sets `hidden` while a
 * phone sheet is open.
 */
export function Breadcrumb({ label, items, hidden = false, className }: BreadcrumbProps) {
  return (
    <nav aria-label={label} className={cx("breadcrumb", className)} hidden={hidden}>
      <Breadcrumbs className="breadcrumb-list">
        {items.map((item) => (
          <RacBreadcrumb
            key={item.id ?? item.href}
            id={item.id ?? item.href}
            className="breadcrumb-item"
          >
            <Link href={item.href} className={cx("breadcrumb-link", item.className)}>
              {item.label}
            </Link>
          </RacBreadcrumb>
        ))}
      </Breadcrumbs>
    </nav>
  );
}

import { Breadcrumb, Breadcrumbs, Link } from "react-aria-components";
import { cx } from "../cx";
import "./PageHeader.css";

export const states = ["default", "with-controls", "with-breadcrumb"] as const;

export interface PageHeaderCrumb {
  label: string;
  /** The last crumb is the current page and takes no link. */
  href: string;
}

export interface PageHeaderProps {
  title: string;
  sub?: string;
  /** Level-3 pages only. `label` names the nav landmark. */
  breadcrumb?: { label: string; items: PageHeaderCrumb[] };
  /** Right-hand controls. They wrap under the title at narrow widths. */
  controls?: React.ReactNode;
  className?: string;
}

/** Names the page and its scope (components.md entry 3). */
export function PageHeader({ title, sub, breadcrumb, controls, className }: PageHeaderProps) {
  return (
    <header className={cx("page-header", className)}>
      <div className="page-header-text">
        {breadcrumb !== undefined && (
          <nav aria-label={breadcrumb.label}>
            <Breadcrumbs className="page-header-crumbs">
              {breadcrumb.items.map((item) => (
                <Breadcrumb key={item.href} id={item.href} className="page-header-crumb">
                  <Link href={item.href} className="page-header-crumb-link">
                    {item.label}
                  </Link>
                </Breadcrumb>
              ))}
            </Breadcrumbs>
          </nav>
        )}
        <h1 className="page-header-title">{title}</h1>
        {sub !== undefined && <p className="page-header-sub">{sub}</p>}
      </div>
      {controls !== undefined && <div className="page-header-controls">{controls}</div>}
    </header>
  );
}

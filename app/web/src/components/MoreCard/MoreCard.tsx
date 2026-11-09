import { Link } from "react-aria-components";
import { cx } from "../cx";
import type { IconName } from "../icons";
import "../Card/Card.css";
import "./MoreCard.css";

export const states = ["default", "focus"] as const;

export interface MoreRow {
  id: string;
  href: string;
  label: string;
  icon: IconName;
  /** Forces the focus ring, for the component sheet. */
  className?: string;
}

export interface MoreCardProps {
  title: string;
  rows: MoreRow[];
  className?: string;
}

/** A card of link rows for the phone More page, 48px tall each (components.md entry 52). */
export function MoreCard({ title, rows, className }: MoreCardProps) {
  return (
    <section className={cx("card", "more-card", className)} aria-labelledby="more-card-title">
      <h2 className="more-card-title" id="more-card-title">
        {title}
      </h2>
      <ul className="more-card-list">
        {rows.map((row) => (
          <li key={row.id}>
            <Link className={cx("more-card-row", row.className)} href={row.href}>
              <span className="more-card-icon" data-icon={row.icon} aria-hidden="true" />
              <span>{row.label}</span>
              <span className="more-card-chevron" aria-hidden="true">
                {"›"}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

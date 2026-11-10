import { useId } from "react";
import { cx } from "../cx";
import "../Card/Card.css";
import "./ToFixGroup.css";

export const states = ["couldnt-read", "wont-load", "not-as-set", "cant-tell", "notices"] as const;

export type ToFixKind = "couldnt_read" | "wont_load" | "not_as_set" | "cant_tell" | "notices";

/** Can't tell and Notices are not counted, so they never show a count. */
const UNCOUNTED: ReadonlySet<ToFixKind> = new Set(["cant_tell", "notices"]);

export interface ToFixGroupProps {
  kind: ToFixKind;
  /** The h2, such as "Couldn't read". */
  title: string;
  /** The count slot beside the title, such as "2". Ignored for Can't tell and Notices. */
  count?: string;
  /** The h2's accessible name with the count, such as "Couldn't read, 2". Counted groups only. */
  ariaLabel?: string;
  /** The question slot after the count, such as "Not counted. The dashboard can't tell which value wins." */
  note?: string;
  /** `li` elements, usually ToFixRow. */
  children: React.ReactNode;
  className?: string;
}

/**
 * A group card in To fix, one per kind (components.md entry 32). The h2 carries the status glyph
 * for its kind, then the count in its own slot, then the question slot. Couldn't read and Won't
 * load lead with ✕, Not as set with ▼, and Can't tell with a dashed ?. Can't tell and Notices
 * are visually uncounted and have no count. The rows are a list under the h2.
 */
export function ToFixGroup({
  kind,
  title,
  count,
  ariaLabel,
  note,
  children,
  className,
}: ToFixGroupProps) {
  const headingId = useId();
  const counted = !UNCOUNTED.has(kind);
  return (
    <section
      className={cx("card", "tofix-group", `tofix-group-${kind.replaceAll("_", "-")}`, className)}
      aria-labelledby={headingId}
    >
      <header className="card-header">
        <h2
          className="card-title tofix-group-title"
          id={headingId}
          {...(counted && ariaLabel !== undefined ? { "aria-label": ariaLabel } : {})}
        >
          {kind !== "notices" && <span className="tofix-mark" aria-hidden="true" />}
          {title}
        </h2>
        {counted && count !== undefined && <span className="card-count num">{count}</span>}
        {note !== undefined && <span className="card-question">{note}</span>}
      </header>
      <ul className="tofix-rows">{children}</ul>
    </section>
  );
}

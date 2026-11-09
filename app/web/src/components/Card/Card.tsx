import { useId } from "react";
import { cx } from "../cx";
import "./Card.css";

export const states = ["default", "header-extras", "foot"] as const;

export interface CardProps {
  title: string;
  /** A count next to the title, tabular and muted. */
  count?: string;
  /** The question the card answers, in muted text. */
  question?: string;
  /** Right-hand slot in the header. */
  right?: React.ReactNode;
  foot?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
}

/** The unit of a page. One question, one answer (components.md entry 5). */
export function Card({ title, count, question, right, foot, children, className }: CardProps) {
  const headingId = useId();
  return (
    <section className={cx("card", className)} aria-labelledby={headingId}>
      <header className="card-header">
        <h2 className="card-title" id={headingId}>
          {title}
        </h2>
        {count !== undefined && <span className="card-count num">{count}</span>}
        {question !== undefined && <span className="card-question">{question}</span>}
        {right !== undefined && <div className="card-right">{right}</div>}
      </header>
      <div className="card-body">{children}</div>
      {foot !== undefined && <p className="card-foot">{foot}</p>}
    </section>
  );
}

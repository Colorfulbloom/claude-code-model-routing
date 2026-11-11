import { cx } from "../cx";
import { RaisedFinding } from "../RaisedFinding/RaisedFinding";
import "../Card/Card.css";
import "./HistoryCard.css";

export const states = ["default", "problem"] as const;

export interface HistoryRow {
  id: string;
  /** The row's name. A row with a help entry passes a help term. */
  label: React.ReactNode;
  value: string;
  /** A ▲ value in the overridden colour. */
  warn?: boolean;
}

export interface HistoryFinding {
  id: string;
  title: string;
  body: string;
}

export interface HistoryCardProps {
  title: string;
  /** One finding per problem, above the rows, each with its reason. */
  findings?: HistoryFinding[];
  rows: HistoryRow[];
  className?: string;
}

/** The "Your history" card on the phone More page (components.md, More page revised). */
export function HistoryCard({ title, findings = [], rows, className }: HistoryCardProps) {
  return (
    <section className={cx("card", "history-card", className)} aria-labelledby="history-card-title">
      <h2 className="history-card-title" id="history-card-title">
        {title}
      </h2>
      {findings.map((finding) => (
        <RaisedFinding key={finding.id} variant="warning" title={finding.title}>
          <p className="history-card-reason">{finding.body}</p>
        </RaisedFinding>
      ))}
      <dl className="history-card-rows">
        {rows.map((row) => (
          <div key={row.id} className="history-card-row">
            <dt>{row.label}</dt>
            <dd className={cx(row.warn === true && "is-warn")}>
              {row.warn === true && (
                <span
                  className="history-card-mark glyph"
                  data-glyph="overridden"
                  aria-hidden="true"
                />
              )}
              {row.value}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

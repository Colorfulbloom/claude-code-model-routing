import { cx } from "../cx";
import "./RaisedFinding.css";

export const states = ["plain", "check", "warning", "overwritten", "saved", "error"] as const;

export type RaisedFindingVariant = (typeof states)[number];

export interface RaisedFindingProps {
  variant?: RaisedFindingVariant;
  /** Heading for the finding, an h3. */
  title?: string;
  children?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}

const roles: Partial<Record<RaisedFindingVariant, "status" | "alert">> = {
  saved: "status",
  overwritten: "status",
  error: "alert",
};

/**
 * A judged result inside a card (components.md entry 7). A start edge marks a finding that stands
 * alone, and the edge colour always repeats a glyph and words inside the box. Saved and Overwritten
 * are polite status, and a failed preview is an alert because it blocks Save.
 */
export function RaisedFinding({
  variant = "plain",
  title,
  children,
  actions,
  className,
}: RaisedFindingProps) {
  return (
    <div
      className={cx(
        "raised-finding",
        `raised-finding-${variant}`,
        variant !== "plain" && "raised-finding-marked",
        className,
      )}
      role={roles[variant]}
    >
      {variant !== "plain" && <span className="raised-finding-mark" aria-hidden="true" />}
      <div className="raised-finding-body">
        {title !== undefined && <h3 className="raised-finding-title">{title}</h3>}
        {children}
        {actions !== undefined && <div className="raised-finding-actions">{actions}</div>}
      </div>
    </div>
  );
}

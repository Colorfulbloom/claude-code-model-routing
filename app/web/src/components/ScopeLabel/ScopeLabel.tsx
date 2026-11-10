import { cx } from "../cx";
import "./ScopeLabel.css";

export const states = ["default", "long"] as const;

export interface ScopeLabelProps {
  /** The scope name, such as "Project local". */
  name: string;
  /** What the scope means in plain words, such as "Just you, this project". */
  meaning: string;
  className?: string;
}

/**
 * A scope name over its plain meaning, two lines (components.md entry 12). It heads a table column
 * and starts a where-set row. The name is in medium weight and the meaning is muted, and both are
 * plain text, so the label reads as "Project local, Just you, this project".
 */
export function ScopeLabel({ name, meaning, className }: ScopeLabelProps) {
  return (
    <span className={cx("scope-label", className)}>
      <span className="scope-label-name">{name}</span>{" "}
      <span className="scope-label-meaning">{meaning}</span>
    </span>
  );
}

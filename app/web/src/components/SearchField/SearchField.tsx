import { useEffect, useRef, useState } from "react";
import {
  Button as AriaButton,
  Input,
  Label,
  SearchField as AriaSearchField,
} from "react-aria-components";
import { cx } from "../cx";
import "./SearchField.css";

export { highlight, matches } from "./match";

export const states = ["empty", "typed", "no-results"] as const;

export interface SearchFieldProps {
  /** The visible label above the field, such as "Search rules". It is the field's name. */
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** The accessible name of the clear button, such as "Clear search". */
  clearLabel: string;
  /** A hint for the empty field, such as "A setting, a rule id or any word". It never replaces the label. */
  placeholder?: string;
  /** Visible text beside the field, such as "12 of 84 rules". Plain text, not a live region. */
  count?: string;
  /** What a screen reader hears, such as "12 of 84 rules" or "No rules match cache". */
  announce?: string;
  /** Milliseconds to wait after the last change before announcing. */
  delay?: number;
  className?: string;
}

/**
 * A search field that filters a list in place (components.md entry 15). A visible Label, the Input
 * and a clear button. Esc clears the field and focus stays in it, and Enter does nothing, as React
 * Aria does it. The visible count is plain text. One separate visually hidden status region
 * (polite) says `announce` once typing pauses for `delay` ms, only when the text differs from the
 * last announcement, and never on first render or a route change.
 */
export function SearchField({
  label,
  value,
  onChange,
  clearLabel,
  placeholder,
  count,
  announce,
  delay = 600,
  className,
}: SearchFieldProps) {
  const [spoken, setSpoken] = useState("");
  // The last text announced, or the first text the field was given, which is never announced. A page
  // that loads its data first gives none until the data arrives, and that first text is the same
  // baseline as on first render.
  const last = useRef(announce);
  useEffect(() => {
    if (announce === undefined) return undefined;
    if (last.current === undefined) {
      last.current = announce;
      return undefined;
    }
    if (announce === last.current) return undefined;
    const timer = setTimeout(() => {
      last.current = announce;
      setSpoken(announce);
    }, delay);
    return () => {
      clearTimeout(timer);
    };
  }, [announce, delay]);
  return (
    <div className={cx("search", className)}>
      <AriaSearchField className="search-field" value={value} onChange={onChange}>
        <Label className="search-label">{label}</Label>
        <div className="search-box">
          <Input className="search-input" {...(placeholder === undefined ? {} : { placeholder })} />
          <AriaButton className="search-clear" aria-label={clearLabel}>
            <span aria-hidden="true">{"✕"}</span>
          </AriaButton>
        </div>
      </AriaSearchField>
      {count !== undefined && <p className="search-count num">{count}</p>}
      <div className="sr-only" role="status">
        {spoken}
      </div>
    </div>
  );
}

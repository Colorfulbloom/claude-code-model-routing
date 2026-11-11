import { Label, Link, Radio, RadioGroup, Text } from "react-aria-components";
import { t } from "@/strings/t";
import { cx } from "../cx";
import "./Segmented.css";

export const states = [
  "default",
  "hover",
  "focus",
  "selected",
  "overflow",
  "choice",
  "choice-now",
  "choice-hover",
  "choice-focus",
  "choice-disabled",
  "choice-phone",
] as const;

export interface SegmentedItem {
  id: string;
  href: string;
  label: string;
  /** The page the person is on. It gets `aria-current="page"` and the chosen look. */
  current?: boolean;
  /** Extra classes. The component sheet uses is-hover and is-focus to force a state. */
  className?: string;
}

export interface SegmentedProps {
  /** Names the nav landmark, such as "Review pages". */
  label: string;
  items: SegmentedItem[];
  className?: string;
}

/**
 * The pages variant of the segmented control (components.md entry 13): in-page navigation, such as
 * the Review views at 375. It is a `nav` of links, and the current one carries `aria-current="page"`.
 * The chosen look is the canonical one, a --select-bg fill with a 2px --accent edge and semibold
 * text, with no check because it is navigation. Segments never wrap, so a row that doesn't fit
 * scrolls sideways. The choice variant is SegmentedChoice, below.
 */
export function Segmented({ label, items, className }: SegmentedProps) {
  return (
    <nav className={cx("segmented", className)} aria-label={label}>
      <ul className="segmented-track">
        {items.map((item) => (
          <li key={item.id} className="segmented-item">
            <Link
              className={cx("segmented-link", item.className)}
              href={item.href}
              {...(item.current === true ? { "aria-current": "page" as const } : {})}
            >
              {item.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export interface SegmentedChoiceOption {
  id: string;
  label: string;
  /** Marks the option that is set now, with "set now" on a second line under the label. */
  now?: boolean;
  /**
   * What this option would run at when that differs from its own value, such as "runs at high"
   * with its status glyph and word. It sits under "set now". Leave it out for an option that runs
   * as it reads.
   */
  runs?: React.ReactNode;
  /** Extra classes. The component sheet uses is-hover and is-focus to force a state. */
  className?: string;
}

export interface SegmentedChoiceProps {
  /** The visible label above the track, such as "Effort". It is also the group's name. */
  label: string;
  options: SegmentedChoiceOption[];
  value: string;
  onChange: (id: string) => void;
  /** A line under the track, tied to the group as its description. */
  hint?: React.ReactNode;
  /** Disabled shows a dashed track with muted text, and `disabledReason` says why in visible text. */
  disabled?: boolean;
  disabledReason?: string;
  className?: string;
}

/**
 * The choice variant of the segmented control (components.md entry 13): a value picked from two to
 * five short options that fit one row, such as the effort level in the edit rail. It is a React
 * Aria RadioGroup, so Tab enters the group, the arrows move and select, and Tab leaves. The chosen
 * option uses the canonical chosen look (a --select-bg fill, a 2px --accent edge, semibold text)
 * with a check before its label, so the choice is never hue alone. An option can carry "set now" on
 * a second line to show the value that is in the file now.
 */
export function SegmentedChoice({
  label,
  options,
  value,
  onChange,
  hint,
  disabled = false,
  disabledReason,
  className,
}: SegmentedChoiceProps) {
  const hasNote = hint !== undefined || (disabled && disabledReason !== undefined);
  return (
    <RadioGroup
      className={cx("segmented-choice", className)}
      value={value}
      onChange={onChange}
      isDisabled={disabled}
    >
      <Label className="segmented-choice-label">{label}</Label>
      <div className="segmented-choice-track">
        {options.map((option) => (
          <Radio
            key={option.id}
            value={option.id}
            className={({ isSelected }) =>
              cx("segmented-choice-option", isSelected && "chosen", option.className)
            }
          >
            {({ isSelected }) => (
              <>
                <span className={cx("segmented-choice-name", isSelected && "chosen-mark")}>
                  {option.label}
                </span>
                {option.now === true && (
                  <small className="segmented-choice-now">{t("ed_now")}</small>
                )}
                {option.runs !== undefined && (
                  <span className="segmented-choice-runs">{option.runs}</span>
                )}
              </>
            )}
          </Radio>
        ))}
      </div>
      {hasNote && (
        <Text slot="description" className="segmented-choice-hint">
          {hint}
          {disabled && disabledReason !== undefined && (
            <span className="segmented-choice-reason">{disabledReason}</span>
          )}
        </Text>
      )}
    </RadioGroup>
  );
}

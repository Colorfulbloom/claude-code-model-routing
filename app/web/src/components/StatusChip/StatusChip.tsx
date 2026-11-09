import { cx } from "../cx";
import "./StatusChip.css";

export const states = [
  "in_effect",
  "overridden",
  "ignored",
  "lowered",
  "invalid",
  "default",
  "unknown",
] as const;

export type SettingStatus = (typeof states)[number];

export interface StatusChipProps {
  status: SettingStatus;
  /** The status word, such as "In effect". The glyph never stands alone. */
  children: React.ReactNode;
  className?: string;
}

/**
 * The verdict on a setting value (components.md entry 10): a pill with the status glyph and word.
 * Use it for setting status only, never for runs or errors. The glyph comes from CSS with empty alt
 * text, so a screen reader says the word only.
 */
export function StatusChip({ status, children, className }: StatusChipProps) {
  const kebab = status.replace("_", "-");
  return (
    <span
      className={cx("status-chip", `status-chip-${kebab}`, "glyph", className)}
      data-glyph={kebab}
    >
      {children}
    </span>
  );
}

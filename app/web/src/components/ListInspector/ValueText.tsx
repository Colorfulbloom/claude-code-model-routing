import { Badge } from "../Badge/Badge";
import type { ValueText as ValueTextData } from "./types";

export interface ValueTextProps {
  value: ValueTextData;
  /** The word on the masked mark, such as "Masked". It is visible, so it is in the accessible name. */
  maskedLabel: string;
}

/**
 * A value as text, with a small masked mark after it when the server hid part of it. The mark is
 * a glyph and a word, so it never stands on hue or on a glyph alone.
 */
export function ValueText({ value, maskedLabel }: ValueTextProps) {
  return (
    <>
      <span className="value-text">{value.text}</span>
      {value.masked === true && (
        <>
          {" "}
          <Badge className="value-masked">{maskedLabel}</Badge>
        </>
      )}
    </>
  );
}

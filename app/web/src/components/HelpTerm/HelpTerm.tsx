import { Button as AriaButton, DialogTrigger } from "react-aria-components";
import { HelpPanel, type HelpPanelProps } from "@/components/HelpPanel/HelpPanel";
import { useHelpOpen } from "@/components/HelpPanel/useHelpOpen";
import type { ChartUnit, HelpId } from "@/strings/help";
import { cx } from "../cx";
import "./HelpTerm.css";

export const states = ["closed", "open", "in-header"] as const;

export interface HelpTermProps {
  help: HelpId;
  /** The header or label text. It is the button's whole content, so it is the name too. */
  children: React.ReactNode;
  /** What the spot shows now, by the names the entry's lines use as `ref`. */
  values?: Readonly<Record<string, string>>;
  /** The label of the line to mark "This column". A column header passes its own. */
  line?: string;
  /** The id of a status in the entry's list, marked "Shown here". */
  word?: string;
  unit?: ChartUnit;
  /** The id of a note that describes the spot, such as a screen reader line beside a pill. */
  describedBy?: string;
  /** The component sheet only. Draws the panel open in place, so it covers no other cell. */
  sheetOpen?: Pick<HelpPanelProps, "source" | "termExists"> & { tray?: boolean };
  className?: string;
}

/**
 * The light help trigger (components.md entry 55): the header or label text itself, with a dotted
 * underline, opening the same panel as HelpButton. In a `th` it is the header's only content, so
 * the column's name stays its label. The text is the button's name, with no "About" prefix,
 * because a header that read "About Check" would stop matching the column it names. The box is
 * 32px tall (a negative margin keeps the line height), so it meets the button target size.
 */
export function HelpTerm({
  help,
  children,
  values,
  line,
  word,
  unit,
  describedBy,
  sheetOpen,
  className,
}: HelpTermProps) {
  const [open, triggerRef] = useHelpOpen();
  const panel: HelpPanelProps = {
    help,
    ...(values === undefined ? {} : { values }),
    ...(line === undefined ? {} : { line }),
    ...(word === undefined ? {} : { word }),
    ...(unit === undefined ? {} : { unit }),
  };
  if (sheetOpen !== undefined) {
    return (
      <span className="hp-sheet-open">
        <AriaButton
          className={cx("help-term", "is-open", className)}
          aria-haspopup="dialog"
          aria-expanded="true"
          data-help-id={help}
        >
          {children}
        </AriaButton>
        <HelpPanel {...panel} {...sheetOpen} inline />
      </span>
    );
  }
  return (
    <DialogTrigger isOpen={open.isOpen} onOpenChange={open.onOpenChange}>
      <AriaButton
        ref={triggerRef}
        className={cx("help-term", className)}
        aria-haspopup="dialog"
        {...(describedBy === undefined ? {} : { "aria-describedby": describedBy })}
        data-help-id={help}
      >
        {children}
      </AriaButton>
      <HelpPanel {...panel} tray={open.tray} />
    </DialogTrigger>
  );
}

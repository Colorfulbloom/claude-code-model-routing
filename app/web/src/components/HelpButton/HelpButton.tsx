import { Button as AriaButton, DialogTrigger } from "react-aria-components";
import { HelpPanel, type HelpPanelProps } from "@/components/HelpPanel/HelpPanel";
import { helpTitle } from "@/components/HelpPanel/help-title";
import { useHelpOpen } from "@/components/HelpPanel/useHelpOpen";
import { helpEntry, type ChartUnit, type HelpId } from "@/strings/help";
import { t } from "@/strings/t";
import { cx } from "../cx";
import "./HelpButton.css";

export const states = [
  "closed",
  "open-popover",
  "open-with-values",
  "line-marked",
  "word-marked",
] as const;

export interface HelpButtonProps {
  help: HelpId;
  /** What the spot shows now, by the names the entry's lines use as `ref`. Each draws beside its line. */
  values?: Readonly<Record<string, string>>;
  /** The label of the line to mark "This column". */
  line?: string;
  /** The id of a status in the entry's list, marked "Shown here". */
  word?: string;
  /** Picks the title from the entry's per-unit titles, so it matches the card's title. */
  unit?: ChartUnit;
  /** The component sheet only. Draws the panel open in place, so it covers no other cell. */
  sheetOpen?: Pick<HelpPanelProps, "source" | "termExists"> & { tray?: boolean };
  className?: string;
}

/**
 * The "?" that opens a help entry (components.md entry 54). A 24 px circle inside a 32 px target.
 * The name is "About {title}". It is a button with a dialog behind it, so it carries
 * aria-haspopup="dialog" and aria-expanded. Use it on tiles, cards and charts, and once beside a
 * status pill that appears once. Column headers and field labels use HelpTerm instead.
 */
export function HelpButton({
  help,
  values,
  line,
  word,
  unit,
  sheetOpen,
  className,
}: HelpButtonProps) {
  const [open, triggerRef] = useHelpOpen();
  const title = helpTitle(sheetOpen?.source ?? helpEntry(help), unit);
  const name = t("hp_trigger", { title });
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
          className={cx("help-button", "is-open", className)}
          aria-label={name}
          aria-haspopup="dialog"
          aria-expanded="true"
          data-help-id={help}
        >
          <span className="help-button-mark" aria-hidden="true">
            ?
          </span>
        </AriaButton>
        <HelpPanel {...panel} {...sheetOpen} inline />
      </span>
    );
  }
  return (
    <DialogTrigger isOpen={open.isOpen} onOpenChange={open.onOpenChange}>
      <AriaButton
        ref={triggerRef}
        className={cx("help-button", className)}
        aria-label={name}
        aria-haspopup="dialog"
        data-help-id={help}
      >
        <span className="help-button-mark" aria-hidden="true">
          ?
        </span>
      </AriaButton>
      <HelpPanel {...panel} tray={open.tray} />
    </DialogTrigger>
  );
}

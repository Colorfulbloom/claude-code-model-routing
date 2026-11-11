import { useId } from "react";
import {
  Button as AriaButton,
  Dialog,
  Heading,
  Modal,
  ModalOverlay,
  OverlayArrow,
  Popover,
} from "react-aria-components";
import { HelpEntry, type HelpEntryProps } from "@/components/HelpEntry/HelpEntry";
import { helpEntry, type ChartUnit, type HelpId } from "@/strings/help";
import { t } from "@/strings/t";
import { cx } from "../cx";
import { helpTitle } from "./help-title";
import "./HelpPanel.css";

export const states = ["popover", "tray"] as const;

export interface HelpPanelProps {
  help: HelpId;
  values?: Readonly<Record<string, string>>;
  /** The label of the line to mark "This column". */
  line?: string;
  /** The id of the list item to mark "Shown here". */
  word?: string;
  /** Picks the title from the entry's `titleByUnit`. */
  unit?: ChartUnit;
  /** Draws the bottom tray (720 px and under) in place of the popover. */
  tray?: boolean;
  /** The component sheet only. Draws the panel in place, open, with no overlay and no focus move. */
  inline?: boolean;
  /** The component sheet and tests only. See HelpEntry. */
  source?: HelpEntryProps["source"];
  termExists?: HelpEntryProps["termExists"];
  className?: string;
}

const ARROW = (
  <svg width="16" height="8" viewBox="0 0 16 8" aria-hidden="true">
    <path d="M0 8 L8 0 L16 8" />
  </svg>
);

interface BodyProps extends HelpPanelProps {
  titleId?: string;
  onClose?: () => void;
}

/** The heading, the tray's Close button and the entry. Shared by the overlay and the inline sheet form. */
function HelpBody({
  help,
  values,
  line,
  word,
  unit,
  tray = false,
  inline = false,
  source,
  termExists,
  titleId,
  onClose,
}: BodyProps) {
  const title = helpTitle(source ?? helpEntry(help), unit);
  return (
    <>
      {tray && <div className="hp-grip" aria-hidden="true" />}
      <div className="hp-head">
        {inline ? (
          <h2 className="hp-title" {...(titleId === undefined ? {} : { id: titleId })}>
            {title}
          </h2>
        ) : (
          <Heading slot="title" level={2} className="hp-title">
            {title}
          </Heading>
        )}
        {tray && (
          <AriaButton
            className="hp-close"
            aria-label={t("hp_close")}
            {...(inline ? {} : { slot: "close" })}
          >
            <span aria-hidden="true">{"✕"}</span>
          </AriaButton>
        )}
      </div>
      <HelpEntry
        help={help}
        {...(values === undefined ? {} : { values })}
        {...(line === undefined ? {} : { line })}
        {...(word === undefined ? {} : { word })}
        {...(onClose === undefined ? {} : { onNavigate: onClose })}
        {...(source === undefined ? {} : { source })}
        {...(termExists === undefined ? {} : { termExists })}
      />
    </>
  );
}

/**
 * The panel a help trigger opens (components.md entry 56). It sits inside a React Aria
 * DialogTrigger, beside the trigger. Above 720 px it is a Popover under the trigger (bottom, flips
 * when there is no room, 8 px off, 360 px wide) holding a Dialog. At 720 px and under it is a
 * bottom tray in a modal with a grip and a Close button. The heading is the entry title as an h2.
 * Focus moves into the dialog on open and back to the trigger on close, and Esc or a click outside
 * closes it. The caller picks the layout with `tray`, read when the panel opens (useHelpOpen).
 */
export function HelpPanel(props: HelpPanelProps) {
  const { tray = false, inline = false, className } = props;
  const titleId = useId();
  if (inline) {
    return (
      <div className={cx(tray ? "hp-tray hp-inline" : "hp-pop hp-inline", className)}>
        {!tray && <span className="hp-arrow hp-arrow-inline">{ARROW}</span>}
        <section className="hp-dialog" role="dialog" aria-labelledby={titleId}>
          <HelpBody {...props} titleId={titleId} />
        </section>
      </div>
    );
  }
  if (tray) {
    return (
      <ModalOverlay className="hp-scrim" isDismissable>
        <Modal className={cx("hp-tray", className)}>
          <Dialog className="hp-dialog">
            {({ close }) => <HelpBody {...props} onClose={close} />}
          </Dialog>
        </Modal>
      </ModalOverlay>
    );
  }
  return (
    <Popover
      className={cx("hp-pop", className)}
      placement="bottom"
      offset={8}
      containerPadding={12}
    >
      <OverlayArrow className="hp-arrow">{ARROW}</OverlayArrow>
      <Dialog className="hp-dialog">
        {({ close }) => <HelpBody {...props} onClose={close} />}
      </Dialog>
    </Popover>
  );
}

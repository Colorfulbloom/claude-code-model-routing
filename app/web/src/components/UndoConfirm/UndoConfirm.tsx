import { useId } from "react";
import type { Ref } from "react";
import type { DiffLine } from "@/api/edit";
import { t } from "@/strings/t";
import { Button } from "../Button/Button";
import { cx } from "../cx";
import { Diff } from "../Diff/Diff";
import { PathText } from "../Diff/PathText";
import { PhoneActionBar } from "../PhoneActionBar/PhoneActionBar";
import { Mark, MessageFrame } from "../RefusedMessage/MessageFrame";
import "./UndoConfirm.css";

export const states = ["default", "busy", "sheet"] as const;

export interface UndoConfirmProps {
  /** The file's name as the warning says it, such as settings.local.json. */
  file: string;
  /** The display path the diff changes. */
  path: string;
  /** The real file, when the path is a link. */
  linksTo?: string;
  /**
   * What Undo would change: the file as it is now against the old file it puts back. Leave it out
   * where the page has no diff to show, and the confirm shows the warning and the buttons alone.
   */
  lines?: DiffLine[];
  /** The warning's words, when it isn't "{file} changed after your save" (an undo that deletes the file). */
  warning?: string;
  /**
   * Puts "Undo anyway" before "Keep the file as it is" in the panel layout, as the phone sheet
   * does. The panel under a Changes row uses it on a phone.
   */
  anywayFirst?: boolean;
  /** Leaves the file as it is. Cancel and Close do the same. */
  onKeep: () => void;
  /** Puts the old file back, though it also removes the other change. */
  onAnyway: () => void;
  /** The undo is in flight. Both buttons hold, and "Undo anyway" is aria-busy. */
  busy?: boolean;
  /** `sheet` is the phone layout: an icon Close beside the title and the buttons in a sticky foot. */
  layout?: "panel" | "sheet";
  headingRef?: Ref<HTMLHeadingElement>;
  className?: string;
}

/**
 * The confirm for undoing a save when the file changed since (plan 5.3, designer item 22). It
 * warns that Undo puts the whole old file back and so removes the other change too, shows the lines
 * Undo changes, and offers "Keep the file as it is" and "Undo anyway". Undo anyway is the danger
 * button and leads in the phone sheet, where the pair stacks. The warning keeps its glyph and words.
 */
export function UndoConfirm({
  file,
  path,
  linksTo,
  lines,
  warning,
  anywayFirst = false,
  onKeep,
  onAnyway,
  busy = false,
  layout = "panel",
  headingRef,
  className,
}: UndoConfirmProps) {
  const headingId = useId();
  const sheet = layout === "sheet";
  const keep = (
    <Button onPress={onKeep} disabled={busy}>
      {t("ed_undo_keep")}
    </Button>
  );
  const anyway = (
    <Button variant="danger" onPress={onAnyway} busy={busy}>
      {t("ed_undo_anyway")}
    </Button>
  );
  return (
    <section
      className={cx("undo-confirm", sheet && "undo-confirm-sheet", className)}
      aria-labelledby={headingId}
    >
      <header className="undo-confirm-head">
        {sheet && (
          <Button variant="icon" ariaLabel={t("hp_close")} onPress={onKeep}>
            {"✕"}
          </Button>
        )}
        <h2 id={headingId} ref={headingRef} tabIndex={-1} className="undo-confirm-title">
          {t("ed_undo_h")}
        </h2>
        {!sheet && (
          <Button variant="quiet" onPress={onKeep}>
            {t("ed_cancel")}
          </Button>
        )}
      </header>
      <div className="undo-confirm-body">
        <MessageFrame tone="warning">
          <p>
            <Mark tone="warning" />
            {warning ?? t("ed_undo_changed", { file })}
          </p>
        </MessageFrame>
        {lines !== undefined && (
          <>
            <h3 className="undo-confirm-diff-h">{t("ed_undo_diff_h")}</h3>
            <Diff
              lines={lines}
              label={t("ed_undo_diff_h")}
              path={path}
              {...(linksTo === undefined ? {} : { linksTo })}
            />
          </>
        )}
        {lines === undefined && (
          <p className="undo-confirm-path">
            <PathText path={path} />
            {linksTo !== undefined && (
              <small className="undo-confirm-link">
                <span aria-hidden="true">{"↪"}</span> {t("ed_links_to")}{" "}
                <span className="undo-confirm-real">{linksTo}</span>
              </small>
            )}
          </p>
        )}
        {!sheet && (
          <div className="undo-confirm-actions">
            {anywayFirst ? anyway : keep}
            {anywayFirst ? keep : anyway}
          </div>
        )}
      </div>
      {sheet && (
        <PhoneActionBar>
          {anyway}
          {keep}
        </PhoneActionBar>
      )}
    </section>
  );
}

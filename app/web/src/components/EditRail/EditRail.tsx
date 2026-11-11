import { useId } from "react";
import type { Ref } from "react";
import { Dialog, Heading, Modal, ModalOverlay } from "react-aria-components";
import type { EditReason } from "@/api/edit";
import { useIsDesktop } from "@/lib/media";
import { t } from "@/strings/t";
import { Button } from "../Button/Button";
import { cx } from "../cx";
import { PhoneActionBar } from "../PhoneActionBar/PhoneActionBar";
import { refusalSentence } from "../RefusedMessage/RefusedMessage";
import "./EditRail.css";

export const states = [
  "default",
  "message",
  "updating",
  "saving",
  "refusal",
  "sheet",
  "sheet-saving",
] as const;

export interface EditRailProps {
  /** The field's name as a word, such as "effort". The heading reads "Edit effort". */
  field: string;
  /** The scope the save goes to, as the person reads it, such as "Project local". Names the button. */
  scopeName: string;
  /** The value control with its label and hint, such as the effort choice. */
  control: React.ReactNode;
  /** The Save to list. */
  saveTo: React.ReactNode;
  /** The This save card. */
  thisSave: React.ReactNode;
  /** A refusal or restart box above the control. The page moves focus to it. */
  message?: React.ReactNode;
  /** The phone foot's one line, such as "settings.local.json, xhigh → medium". */
  summary: React.ReactNode;
  /** The picked scope refuses a save before it is sent. The reason shows beside Save, and Save holds. */
  refusal?: { code: EditReason; file: string };
  /**
   * Save has nothing to do and says why on the page, not as an error: the picked value and file are
   * what is set now (the neutral line in This save), or the page holds a stale key (the restart
   * box). Save is dashed and aria-disabled, stays focusable, and `describedBy` names that line.
   */
  hold?: { describedBy: string };
  /** A save is in flight, or held for the preview. The label swaps to "Saving" and the width stays. */
  saving?: boolean;
  onSave: () => void;
  onCancel: () => void;
  /**
   * `auto` reads the window: a labelled region at 721px and up, a full-height sheet at 720px and
   * under. The component sheet forces one.
   */
  layout?: "auto" | "rail" | "sheet";
  /** The component sheet only. Draws the phone sheet in place, with no overlay. */
  inline?: boolean;
  /** Where the page puts focus when the rail opens, and the heading's own focus target. */
  headingRef?: Ref<HTMLHeadingElement>;
  className?: string;
}

/**
 * The edit rail of direction B (components.md entries 27 and 28). At 721px and up it is a labelled
 * region beside the item list, with the heading "Edit {field}" and Cancel. Below that it is a
 * modal sheet over the page: a Close button, a scrolling body and a sticky foot with the phone action
 * bar. Both hold the same parts in one order: the message, the value control, the Save to list, the
 * This save card, and Save, which names its scope and keeps its width while it reads "Saving".
 * The parts come in as slots, so the page owns the data and this file owns the layout.
 */
export function EditRail(props: EditRailProps) {
  const desktop = useIsDesktop();
  const { layout = "auto", inline = false, className } = props;
  const sheet = layout === "sheet" || (layout === "auto" && !desktop);
  const headingId = useId();
  if (!sheet) {
    return (
      <section className={cx("edit-rail", className)} aria-labelledby={headingId}>
        <Rail {...props} sheet={false} headingId={headingId} />
      </section>
    );
  }
  if (inline) {
    return (
      <section
        className={cx("edit-rail", "edit-rail-sheet", className)}
        role="dialog"
        aria-labelledby={headingId}
      >
        <Rail {...props} sheet headingId={headingId} />
      </section>
    );
  }
  return (
    <ModalOverlay
      className="edit-rail-scrim"
      isOpen
      isDismissable={props.saving !== true}
      isKeyboardDismissDisabled={props.saving === true}
      onOpenChange={(open) => {
        if (!open) props.onCancel();
      }}
    >
      <Modal className="edit-rail-modal">
        <Dialog className={cx("edit-rail", "edit-rail-sheet", className)}>
          <Rail {...props} sheet racHeading headingId={headingId} />
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}

interface RailProps extends EditRailProps {
  sheet: boolean;
  racHeading?: boolean;
  headingId: string;
}

function Rail({
  field,
  scopeName,
  control,
  saveTo,
  thisSave,
  message,
  summary,
  refusal,
  hold,
  saving = false,
  onSave,
  onCancel,
  headingRef,
  sheet,
  racHeading = false,
  headingId,
}: RailProps) {
  const refusalId = useId();
  const title = t("ed_h", { field });
  const describedBy = refusal !== undefined ? refusalId : hold?.describedBy;
  const save = (
    <Button
      variant="primary"
      className="edit-save"
      busy={saving}
      disabled={refusal !== undefined || hold !== undefined}
      {...(describedBy === undefined ? {} : { describedBy })}
      onPress={onSave}
    >
      <span className="edit-save-label">
        <span
          className={cx("edit-save-idle", saving && "edit-save-hidden")}
          {...(saving ? { "aria-hidden": "true" } : {})}
        >
          {t("ed_save", { scope: scopeName })}
        </span>
        <span
          className={cx("edit-save-busy", !saving && "edit-save-hidden")}
          {...(saving ? {} : { "aria-hidden": "true" })}
        >
          {t("ed_saving")}
        </span>
      </span>
    </Button>
  );
  const heading = racHeading ? (
    <Heading slot="title" level={2} ref={headingRef} tabIndex={-1} className="edit-rail-title">
      {title}
    </Heading>
  ) : (
    <h2 id={headingId} ref={headingRef} tabIndex={-1} className="edit-rail-title">
      {title}
    </h2>
  );
  return (
    <>
      <header className="edit-rail-head">
        {sheet && (
          <Button variant="icon" ariaLabel={t("hp_close")} onPress={onCancel}>
            {"✕"}
          </Button>
        )}
        {heading}
        {!sheet && (
          <Button variant="quiet" onPress={onCancel}>
            {t("ed_cancel")}
          </Button>
        )}
      </header>
      <div className="edit-rail-body">
        {message}
        <div className="edit-rail-control">{control}</div>
        {saveTo}
        {thisSave}
      </div>
      {refusal !== undefined && (
        <p id={refusalId} className="edit-rail-refusal">
          <span className="edit-rail-refusal-mark" aria-hidden="true" />
          {refusalSentence(refusal.code, refusal.file)}
        </p>
      )}
      {sheet ? (
        <PhoneActionBar summary={summary}>{save}</PhoneActionBar>
      ) : (
        <div className="edit-rail-foot">
          <p className="edit-rail-note">{t("ed_backup_note")}</p>
          {save}
        </div>
      )}
    </>
  );
}

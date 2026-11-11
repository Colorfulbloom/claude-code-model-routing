import type { Ref } from "react";
import type { EditReason } from "@/api/edit";
import { t } from "@/strings/t";
import { cx } from "../cx";
import { Mark, MessageFrame } from "./MessageFrame";
import "./RefusedMessage.css";

export const states = [
  "changed",
  "changed-ours",
  "changed-no-keys",
  "link-outside",
  "preview-mismatch",
  "not-undone",
] as const;

export interface RefusedMessageProps {
  /**
   * The code the server refused with, or one of the page's own (`network`, `server`, `locked`,
   * `refused`). Its sentence follows the lead.
   */
  code: EditReason;
  /** The display path of the file, such as settings.local.json. Fills {file} in the sentence. */
  file: string;
  /** "Not undone." leads an undo that was refused. A save leads with "Not saved." */
  undo?: boolean;
  /** The keys another program changed, for `changed`. */
  changedKeys?: readonly string[];
  /** True when one of those keys is the setting being edited. */
  editedKeyChanged?: boolean;
  /** Where focus goes when the save is refused. The box has tabindex -1 and no role="alert". */
  messageRef?: Ref<HTMLDivElement>;
  id?: string;
  className?: string;
}

/**
 * The sentence for a code. One literal t() call per branch, so the static key test sees each key.
 * The page's own reasons come after the server's.
 */
export function refusalSentence(code: EditReason, file: string): string {
  switch (code) {
    case "changed":
      return t("er_changed", { file });
    case "preview_mismatch":
      return t("er_preview_mismatch");
    case "bad_version":
      return t("er_bad_version");
    case "changed_since_save":
      return t("er_changed_since_save", { file });
    case "raced":
      return t("er_raced", { file });
    case "link_outside":
      return t("er_link_outside", { file });
    case "link_dangling":
      return t("er_link_dangling", { file });
    case "not_regular":
      return t("er_not_regular", { file });
    case "hard_link":
      return t("er_hard_link", { file });
    case "not_owner":
      return t("er_not_owner", { file });
    case "too_large":
      return t("er_too_large", { file });
    case "managed":
      return t("er_managed", { file });
    case "forbidden_path":
      return t("er_forbidden_path", { file });
    case "folder_not_found":
      return t("er_folder_not_found");
    case "unknown_project":
      return t("er_unknown_project");
    case "not_editable":
      return t("er_not_editable");
    case "bad_value":
      return t("er_bad_value");
    case "no_change":
      return t("er_no_change");
    case "unparsed":
      return t("er_unparsed", { file });
    case "key_missing":
      return t("er_key_missing", { file });
    case "key_present":
      return t("er_key_present", { file });
    case "parent_not_object":
      return t("er_parent_not_object", { file });
    case "repeated_key":
      return t("er_repeated_key", { file });
    case "oracle_failed":
      return t("er_oracle_failed");
    case "lock_busy":
      return t("er_lock_busy", { file });
    case "write_failed":
      return t("er_write_failed", { file });
    case "ledger_damaged":
      return t("er_ledger_damaged", { file });
    case "backup_damaged":
      return t("er_backup_damaged", { file });
    case "not_undoable":
      return t("er_not_undoable");
    case "unknown_edit":
      return t("er_unknown_edit");
    case "forged_row":
      return t("er_forged_row");
    case "request_reused":
      return t("er_request_reused");
    case "cant_rebuild":
      return t("er_cant_rebuild");
    case "edits_off":
      return t("er_edits_off");
    case "edit_key_unknown":
      return t("er_edit_key_unknown");
    case "network":
      return t("er_network");
    case "server":
      return t("er_server");
    case "locked":
      return t("er_locked");
    case "refused":
      return t("er_refused");
  }
}

/**
 * The lead before the sentence. A network failure or a 5xx may come after the write, so it reads
 * "Not confirmed." (or "Undo not confirmed."), because the page can't say nothing was written. Every
 * other reason says nothing was written, so it reads "Not saved." (or "Not undone.").
 */
export function refusalLead(code: EditReason, undo: boolean): string {
  if (code === "network" || code === "server") {
    return undo ? t("er_lead_unknown_undo") : t("er_lead_unknown");
  }
  return undo ? t("er_lead_undo") : t("er_lead");
}

/**
 * A refusal, in words (plan 5.3). It leads with "Not saved." or "Not undone." (or "Not confirmed."
 * when the answer was lost) and then the code's sentence. For `changed` a second line names the keys another program changed, and says so when
 * one of them is the setting being edited. The box takes focus from code (tabindex -1) and has no
 * role="alert", so a screen reader reads it once. The page keeps the preview below it fresh.
 */
export function RefusedMessage({
  code,
  file,
  undo = false,
  changedKeys = [],
  editedKeyChanged = false,
  messageRef,
  id,
  className,
}: RefusedMessageProps) {
  const lead = refusalLead(code, undo);
  const keysLine =
    code === "changed"
      ? changedKeys.length > 0
        ? t("er_changed_keys", { keys: changedKeys.join(", ") })
        : t("er_changed_nokeys")
      : null;
  return (
    <MessageFrame
      tone="error"
      focusable
      {...(messageRef === undefined ? {} : { frameRef: messageRef })}
      {...(id === undefined ? {} : { id })}
      className={cx("refused", className)}
    >
      <p>
        <Mark tone="error" />
        <b className="refused-lead">{lead}</b> {refusalSentence(code, file)}
      </p>
      {keysLine !== null && (
        <p className="refused-keys">
          {keysLine}
          {editedKeyChanged && ` ${t("er_changed_ours")}`}
        </p>
      )}
    </MessageFrame>
  );
}

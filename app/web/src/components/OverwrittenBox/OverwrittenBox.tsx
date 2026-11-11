import { useEffect, useId, useRef } from "react";
import type { DiffLine, EditReason } from "@/api/edit";
import { t } from "@/strings/t";
import { Button } from "../Button/Button";
import { cx } from "../cx";
import { Diff } from "../Diff/Diff";
import { Mark, MessageFrame } from "../RefusedMessage/MessageFrame";
import { refusalSentence } from "../RefusedMessage/RefusedMessage";
import "./OverwrittenBox.css";

export const states = [
  "kept",
  "lost",
  "drift-open",
  "drift-loading",
  "drift-refused",
  "many-keys",
] as const;

/** What "Review changes" shows. `lines` is the drift diff, `refused` carries the code that blocked it. */
export type DriftView =
  | { state: "loading" }
  | { state: "lines"; lines: DiffLine[]; path?: string; linksTo?: string }
  | { state: "refused"; code: EditReason; file: string };

export interface OverwrittenBoxProps {
  /** The keys that changed after the save, such as permissions.allow. */
  keys: readonly string[];
  /** Whether the saved value is still in the file. Null says nothing, because the recheck couldn't tell. */
  ours: boolean | null;
  /** The setting that was saved, as a word, such as "effort". Fills the kept and lost lines. */
  field: string;
  /** The drift is open under the warning. */
  open: boolean;
  onToggle: () => void;
  drift?: DriftView;
  onUndo: () => void;
  undoBusy?: boolean;
  /** The page holds a stale key (the restart box shows), so Undo is aria-disabled until a reload. */
  undoDisabled?: boolean;
  className?: string;
}

/**
 * The warning that stays after a save when another program changed the file right after (plan 5.3
 * and designer items 17 and 18). It lists the keys that changed, says whether the saved value
 * survived, and offers Review changes and Undo. Review changes opens the drift diff inline under the
 * warning and moves focus to it. The warning is a polite status, and it keeps its glyph and words.
 */
export function OverwrittenBox({
  keys,
  ours,
  field,
  open,
  onToggle,
  drift,
  onUndo,
  undoBusy = false,
  undoDisabled = false,
  className,
}: OverwrittenBoxProps) {
  const driftId = useId();
  const headingId = useId();
  const driftRef = useRef<HTMLElement | null>(null);
  const wasOpen = useRef(open);
  useEffect(() => {
    if (open && !wasOpen.current) driftRef.current?.focus();
    wasOpen.current = open;
  }, [open]);
  return (
    <div className={cx("overwritten-box", className)}>
      <MessageFrame tone="warning" role="status">
        <p>
          <Mark tone="warning" />
          {t("ed_over")}
        </p>
        {keys.length > 0 && (
          <>
            <p className="overwritten-box-keys-h">{t("ed_over_keys")}</p>
            <p className="overwritten-box-keys">
              {keys.map((key, index) => (
                <span key={key}>
                  <code className="overwritten-box-key">{key}</code>
                  {index < keys.length - 1 && ", "}
                </span>
              ))}
            </p>
          </>
        )}
        {ours === true && (
          <p className="overwritten-box-ours">{t("rc_overwritten_kept", { field })}</p>
        )}
        {ours === false && (
          <p className="overwritten-box-ours">{t("rc_overwritten_lost", { field })}</p>
        )}
        <div className="overwritten-box-actions">
          <button
            type="button"
            className="button button-primary"
            aria-expanded={open}
            aria-controls={open ? driftId : undefined}
            onClick={onToggle}
          >
            {t("ed_review_changes")}
          </button>
          <Button onPress={onUndo} busy={undoBusy} disabled={undoDisabled}>
            {t("ed_undo")}
          </Button>
        </div>
      </MessageFrame>
      {open && (
        <section
          ref={driftRef}
          id={driftId}
          className="overwritten-box-drift"
          aria-labelledby={headingId}
          aria-busy={drift?.state === "loading" ? "true" : undefined}
          tabIndex={-1}
        >
          <h3 id={headingId} className="overwritten-box-drift-h">
            {t("ed_drift_h")}
          </h3>
          {drift?.state === "lines" && (
            <Diff
              lines={drift.lines}
              label={t("ed_drift_h")}
              {...(drift.path === undefined ? {} : { path: drift.path })}
              {...(drift.linksTo === undefined ? {} : { linksTo: drift.linksTo })}
            />
          )}
          {drift?.state === "refused" && (
            <p className="overwritten-box-refused">{refusalSentence(drift.code, drift.file)}</p>
          )}
          {drift?.state === "loading" && <p className="overwritten-box-wait">{t("rc_checking")}</p>}
        </section>
      )}
    </div>
  );
}

import { Link } from "react-aria-components";
import { clockShort } from "@/lib/clock";
import { t } from "@/strings/t";
import { Button } from "../Button/Button";
import { cx } from "../cx";
import { Mark, MessageFrame } from "../RefusedMessage/MessageFrame";
import "./SavedBox.css";

export const states = ["checking", "confirmed", "undo-busy", "phone"] as const;

/** What the second read of the file found. An overwritten file gets the OverwrittenBox instead. */
export type SavedRecheck = { state: "checking" } | { state: "confirmed"; value: string };

export interface SavedBoxProps {
  /** When the save finished, as the server sent it. The box shows the clock time. */
  savedAt: string;
  recheck: SavedRecheck;
  onUndo: () => void;
  /** An undo is in flight. The button stays in place with aria-busy. */
  undoBusy?: boolean;
  /** The page holds a stale key (the restart box shows), so Undo is aria-disabled until a reload. */
  undoDisabled?: boolean;
  /** Where "All changes" goes, the Changes page. */
  changesHref: string;
  className?: string;
}

/**
 * What the inspector shows right after a save (plan 5.3): "Saved." with the time and what Undo
 * does, an Undo button, the recheck line and a link to all changes. The recheck line is its own
 * polite region and stays busy while Bar Tab reads the file again, so a screen reader hears it
 * once, when it settles (designer item 20). Each state shows a glyph and words.
 */
export function SavedBox({
  savedAt,
  recheck,
  onUndo,
  undoBusy = false,
  undoDisabled = false,
  changesHref,
  className,
}: SavedBoxProps) {
  const checking = recheck.state === "checking";
  return (
    <MessageFrame tone="ok" className={cx("saved-box", className)}>
      <div className="saved-box-top">
        <p className="saved-box-line" role="status">
          <Mark tone="ok" />
          <b className="saved-box-lead">{t("ed_saved")}</b>{" "}
          <span className="saved-box-meta">
            {t("ed_saved_meta", { time: clockShort(savedAt) })}
          </span>
        </p>
        <Button onPress={onUndo} busy={undoBusy} disabled={undoDisabled}>
          {t("ed_undo")}
        </Button>
      </div>
      <p className="saved-box-recheck" role="status" aria-busy={checking ? "true" : undefined}>
        {recheck.state === "checking" ? (
          <>
            <span className="saved-box-ring ring-mark" aria-hidden="true" />
            {t("rc_checking")}
          </>
        ) : (
          <>
            <span className="saved-box-ok" aria-hidden="true">
              {"✓"}
            </span>
            {t("rc_confirmed", { value: recheck.value })}
          </>
        )}
      </p>
      <Link className="saved-box-link" href={changesHref}>
        {t("ed_all_changes")}
      </Link>
    </MessageFrame>
  );
}

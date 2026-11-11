import { useId } from "react";
import type { EditPreview, EditWarning, RunsAt } from "@/api/edit";
import { Badge } from "@/components/Badge/Badge";
import { HelpButton } from "@/components/HelpButton/HelpButton";
import { asScope, scopeName, splitOnMark, CODE_MARK, statusWord } from "@/lib/edit-words";
import { clockMedium } from "@/lib/clock";
import { modelLabel } from "@/lib/models";
import { t, tn } from "@/strings/t";
import { cx } from "../cx";
import { Diff } from "../Diff/Diff";
import { PathText } from "../Diff/PathText";
import { StatusChip } from "../StatusChip/StatusChip";
import "./ThisSave.css";

export const states = [
  "default",
  "user-link",
  "model",
  "updating",
  "warnings",
  "new-value",
  "phone",
] as const;

export interface ThisSaveProps {
  /** The server preview for the current choice. Everything the card shows comes from it. */
  preview: EditPreview;
  /** True for the model field, where the line reads "Runs on" and the values are model names. */
  runsOn?: boolean;
  /** A preview for the latest choice is still on its way. The card marks itself busy. */
  updating?: boolean;
  /** When the change applies, already worded, such as "Applies to new sessions". */
  applies?: string;
  /**
   * The picked value and file are what is set now, so there is nothing to show. The card keeps its
   * File row, drops the Set to and Runs rows and the diff, and says one neutral line with this id,
   * which Save names in aria-describedby.
   */
  neutralId?: string;
  className?: string;
}

/** The sentence for a warning code. One literal t() call per branch (fact K-819f). */
export function warningSentence(warning: EditWarning): string {
  switch (warning.code) {
    case "wont_win": {
      const named = asScope(warning.params.scope);
      return t("ew_wont_win", {
        scope: named === null ? (warning.params.scope ?? "") : scopeName(named),
      });
    }
    case "config_change_hook":
      return t("ew_config_change_hook");
    case "shared_repo":
      return t("ew_shared_repo", { file: warning.params.file ?? "" });
  }
}

function RunsValue({ at, model }: { at: RunsAt; model: boolean }) {
  return (
    <>
      {at.value !== null && <b>{model ? modelLabel(at.value) : at.value}</b>}
      <StatusChip status={at.status}>{statusWord(at.status)}</StatusChip>
    </>
  );
}

/** A value in the Set to line. Nothing yet reads as "Nothing set here". */
function SetValue({ value }: { value: string | number | null }) {
  if (value === null) return <span className="this-save-none">{t("sc_none")}</span>;
  return <b className="this-save-mono">{String(value)}</b>;
}

function Arrow() {
  return (
    <>
      <span className="this-save-arrow" aria-hidden="true">
        {"→"}
      </span>
      <span className="sr-only">{t("ed_to")}</span>
    </>
  );
}

/**
 * The card that shows what one save does (plan 5.3), read from the server preview: the file with
 * its scope, a "New file" badge when the save creates it, and the link note, Set to with the old and new value, Runs at (or Runs on, for the
 * model) with a status glyph and word before and after, when it applies, the line diff at its real
 * line numbers, and when Bar Tab read the file. Warnings and the other projects a user save
 * reaches follow the lines. While a newer preview is pending the card marks itself updating and
 * sets aria-busy, and the page holds Save until it settles (designer item 9).
 */
export function ThisSave({
  preview,
  runsOn = false,
  updating = false,
  applies,
  neutralId,
  className,
}: ThisSaveProps) {
  const headingId = useId();
  const { target, effect } = preview;
  const [linkBefore, linkAfter] = splitOnMark(t("ed_link", { real: CODE_MARK }));
  return (
    <section
      className={cx("this-save", updating && "this-save-updating", className)}
      aria-labelledby={headingId}
      aria-busy={updating ? "true" : undefined}
    >
      <header className="this-save-head">
        <h3 id={headingId} className="this-save-title">
          {t("ed_this_save_h")}
        </h3>
        {updating && (
          <span className="this-save-busy">
            <span aria-hidden="true">{"↻"}</span> {t("ed_updating")}
          </span>
        )}
        <HelpButton help="edit.save" />
      </header>
      <dl className="this-save-dl">
        <div>
          <dt>{t("ed_l_file")}</dt>
          <dd>
            <span className="this-save-chip">{scopeName(target.scope)}</span>
            {target.new_file && <Badge className="this-save-new">{t("ed_new_file")}</Badge>}
            <PathText path={target.display_path} />
            {target.link && (
              <small className="this-save-link">
                <span aria-hidden="true">{"↪"}</span> {linkBefore}
                <span className="this-save-real">{target.real_path}</span>
                {linkAfter}
              </small>
            )}
          </dd>
        </div>
        {neutralId === undefined && (
          <>
            <div>
              <dt>{t("ed_l_set")}</dt>
              <dd>
                <SetValue value={effect.set.from} />
                <Arrow />
                <SetValue value={effect.set.to} />
              </dd>
            </div>
            <div>
              <dt>{runsOn ? t("ed_l_runs_model") : t("ed_l_runs")}</dt>
              <dd>
                <RunsValue at={effect.runs.now} model={runsOn} />
                <Arrow />
                <RunsValue at={effect.runs.after} model={runsOn} />
                {applies !== undefined && (
                  <small className="this-save-applies">
                    <span aria-hidden="true">{"↻"}</span> {applies}
                  </small>
                )}
              </dd>
            </div>
          </>
        )}
      </dl>
      {neutralId !== undefined && (
        <p id={neutralId} className="this-save-neutral">
          {t("ed_pick_other")}
        </p>
      )}
      {(preview.warnings.length > 0 || preview.reaches.length > 0) && (
        <ul className="this-save-notes">
          {preview.warnings.map((warning) => (
            <li key={warning.code}>
              <span className="glyph" data-glyph="overridden" aria-hidden="true" />{" "}
              {warningSentence(warning)}
            </li>
          ))}
          {preview.reaches.length > 0 && <li>{tn("ed_reaches", preview.reaches.length)}</li>}
        </ul>
      )}
      {neutralId === undefined && <Diff lines={preview.diff.lines} label={t("ed_this_save_h")} />}
      <p className="this-save-read">{t("ed_read_at", { time: clockMedium(preview.read_at) })}</p>
    </section>
  );
}

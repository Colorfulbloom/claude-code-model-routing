import { Radio, RadioGroup } from "react-aria-components";
import type { EditReadOnlyCode, EditScope, EditScopeRow } from "@/api/edit";
import { HelpTerm } from "@/components/HelpTerm/HelpTerm";
import { outcomeView, scopeMeaning, scopeName } from "@/lib/edit-words";
import { t } from "@/strings/t";
import { cx } from "../cx";
import { PathText } from "../Diff/PathText";
import { Mark, MessageFrame } from "../RefusedMessage/MessageFrame";
import { StatusChip } from "../StatusChip/StatusChip";
import "./SaveToList.css";

export const states = [
  "default",
  "hover",
  "focus",
  "user-link",
  "not-writable",
  "disabled",
  "phone",
] as const;

export interface SaveToListProps {
  /** One row per scope the field can be saved to, with the outcome of saving there. */
  scopes: EditScopeRow[];
  picked: EditScope;
  onPick: (scope: EditScope) => void;
  /** Names the project and field for the user-scope warning, such as "Tidewater reporting" and "effort". */
  warning?: { project: string; field: string };
  /** Holds the choice while a save is in flight. */
  disabled?: boolean;
  /** Extra classes per scope. The component sheet uses is-hover and is-focus to force a state. */
  rowClass?: Partial<Record<EditScope, string>>;
  className?: string;
}

function LockMark() {
  return (
    <svg
      className="save-to-lock"
      viewBox="0 0 12 14"
      width="11"
      height="13"
      aria-hidden="true"
      focusable="false"
    >
      <rect x="1.5" y="6" width="9" height="7" rx="1.5" fill="currentColor" />
      <path
        d="M3.5 6V4.2a2.5 2.5 0 0 1 5 0V6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
      />
    </svg>
  );
}

/** The line a row that can't be saved to gives, by the code the server sent. */
function readOnlyLine(code: EditReadOnlyCode | null): string | null {
  switch (code) {
    case "managed":
      return t("ro_managed");
    case "field_until_m7":
      return t("ro_field_until_m7");
    // A link the writer won't follow gets its own line under the row, beside the link target.
    case "link_outside":
    case "link_dangling":
    case "risky_until_m8":
    case "plugin":
    case "not_writable":
    case null:
      return null;
  }
}

/** The plain line under a row whose link the writer won't follow, or null for any other row. */
function linkRowLine(code: EditReadOnlyCode | null): string | null {
  if (code === "link_outside") return t("ed_link_outside_row");
  if (code === "link_dangling") return t("ed_link_dangling_row");
  return null;
}

/** The order the inspector lists the scopes in, top wins: Project local, Shared project, User. */
const SCOPE_ORDER: Record<EditScope, number> = { local: 0, project: 1, user: 2 };

/** The rows in the inspector's order, whatever order the server sent them in. */
export function inInspectorOrder(rows: readonly EditScopeRow[]): EditScopeRow[] {
  return [...rows].sort((a, b) => SCOPE_ORDER[a.scope] - SCOPE_ORDER[b.scope]);
}

/**
 * The "Save to" list (plan 5.3): one radio row per scope, with the real path always visible, the
 * link target under a linked file, and what saving there would do. Each outcome shows its mark
 * glyph and its word ("Takes effect", "Overridden by Project local"), never a hue alone. The
 * chosen row has the --select-bg fill, the 3px start bar and the word "Selected". A row that
 * can't be saved to says so before it is picked. Picking User, when a higher scope wins in this
 * project, raises the warning that the save changes nothing here. The list is a React Aria
 * RadioGroup, so arrows move and select.
 */
export function SaveToList({
  scopes,
  picked,
  onPick,
  warning,
  disabled = false,
  rowClass,
  className,
}: SaveToListProps) {
  const pickedRow = scopes.find((row) => row.scope === picked);
  const beatenBy =
    picked === "user" && pickedRow?.outcome.status === "overridden"
      ? pickedRow.outcome.beaten_by
      : null;
  return (
    <div className={cx("save-to", className)}>
      <div className="save-to-legend">
        <HelpTerm help="edit.scopes">{t("ed_saveto")}</HelpTerm>
      </div>
      <RadioGroup
        className="save-to-rows"
        aria-label={t("ed_saveto")}
        value={picked}
        isDisabled={disabled}
        onChange={(value) => {
          onPick(value as EditScope);
        }}
      >
        {inInspectorOrder(scopes).map((row) => {
          const outcome = outcomeView(row.outcome);
          const reason = row.writable ? null : readOnlyLine(row.read_only_reason);
          // A link the writer won't follow (the server's `link_outside` or `link_dangling` code):
          // the row keeps its lock, says why in one line and names the target. The line is the
          // row's description.
          const linkLine = row.writable ? null : linkRowLine(row.read_only_reason);
          const outside = linkLine !== null;
          const outsideId = `save-to-outside-${row.scope}`;
          return (
            <Radio
              key={row.scope}
              value={row.scope}
              isDisabled={!row.writable}
              {...(outside ? { "aria-describedby": outsideId } : {})}
              className={({ isSelected }) =>
                cx("save-to-row", isSelected && "chosen-row", rowClass?.[row.scope])
              }
            >
              {({ isSelected }) => (
                <>
                  <span className="save-to-scope">
                    <span className="save-to-scope-name">{scopeName(row.scope)}</span>
                    <span className="save-to-scope-meaning">{scopeMeaning(row.scope)}</span>
                  </span>
                  <span className="save-to-path">
                    <PathText path={row.display_path} />
                    {row.link && (
                      <small className="save-to-link">
                        <span aria-hidden="true">{"↪"}</span> {t("ed_links_to")}{" "}
                        <span className="save-to-real">{row.real_path}</span>
                      </small>
                    )}
                  </span>
                  <span className="save-to-outcome">
                    {row.writable ? (
                      <StatusChip status={outcome.status}>{outcome.word}</StatusChip>
                    ) : (
                      <span className="save-to-blocked">
                        <LockMark /> {t("ro_h")}
                      </span>
                    )}
                    {isSelected && <span className="chosen-word">{`✓ ${t("ed_selected")}`}</span>}
                  </span>
                  {reason !== null && <span className="save-to-reason">{reason}</span>}
                  {outside && (
                    <span id={outsideId} className="save-to-reason">
                      {linkLine}
                    </span>
                  )}
                </>
              )}
            </Radio>
          );
        })}
      </RadioGroup>
      {warning !== undefined && beatenBy !== null && (
        <MessageFrame tone="warning" className="save-to-warning">
          <p>
            <Mark tone="warning" />
            {t("ed_user_warn", {
              project: warning.project,
              scope: scopeName(beatenBy),
              field: warning.field,
            })}
          </p>
        </MessageFrame>
      )}
    </div>
  );
}

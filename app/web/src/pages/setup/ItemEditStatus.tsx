/*
 * What an item's inspector says about a save (plan 5.3): the Saved box with its recheck line, the
 * Overwritten box with Review changes, and the line after an Undo. It reads two things. A save made
 * on this page (`saved`), which it rechecks at about 2 s and 10 s. Or, on a later visit, the newest
 * overwritten row nobody has seen for this item (`/api/edit/open`), so the warning comes back until
 * it is marked seen. Opening Review changes marks it seen, and the box stays for this visit.
 */
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useApi } from "@/api/client";
import { EditRequestError, useDrift, useMarkSeen, useOpenWarning, useRecheck } from "@/api/edit";
import type { EditScope, HistoryRow, SettingsEditField, UndoHandle } from "@/api/edit";
import type { SetupItem } from "@/api/types";
import { OverwrittenBox } from "@/components/OverwrittenBox/OverwrittenBox";
import type { DriftView } from "@/components/OverwrittenBox/OverwrittenBox";
import { RefusedMessage } from "@/components/RefusedMessage/RefusedMessage";
import { RestartBox } from "@/components/RestartBox/RestartBox";
import { SavedBox } from "@/components/SavedBox/SavedBox";
import { clockShort } from "@/lib/clock";
import { fieldWord } from "@/lib/edit-page";
import { t } from "@/strings/t";
import { editCommand, fileNameOf } from "./edit-mode";
import type { SavedInfo } from "./SettingsEditor";
import type { UndoTarget } from "./UndoPanel";

export interface ItemEditStatusProps {
  project: string;
  item: SetupItem;
  field: SettingsEditField;
  saved: SavedInfo | null;
  undo: UndoHandle;
  onUndo: (target: UndoTarget) => void;
  changesHref: string;
}

/** The rows an undo or a drift read can name: the saved one, or the one the open warning found. */
interface Subject {
  rowId: string;
  scope: EditScope;
  displayPath: string;
  realPath: string | null;
}

function subjectOfRow(row: HistoryRow): Subject {
  return {
    rowId: row.id,
    scope: row.scope,
    displayPath: row.display_path,
    realPath: row.real_path !== row.display_path ? row.real_path : null,
  };
}

export function ItemEditStatus({
  project,
  item,
  field,
  saved,
  undo,
  onUndo,
  changesHref,
}: ItemEditStatusProps) {
  const mine = saved !== null && saved.itemId === item.id ? saved : null;
  const recheck = useRecheck(
    project,
    mine === null ? null : { rowId: mine.rowId, scope: mine.scope },
  );
  const warn = useOpenWarning(project, mine === null ? item.id : null);
  const markSeen = useMarkSeen(project);
  const { connection } = useApi();
  const conn = useSyncExternalStore(connection.subscribe, connection.getState);

  // The warning a later visit finds is held, so marking it seen doesn't take it off the screen.
  const [held, setHeld] = useState<HistoryRow | null>(null);
  const live = warn.data?.row ?? null;
  if (mine === null && live !== null && held === null) setHeld(live);
  const warning = mine === null ? held : null;

  const [open, setOpen] = useState(false);
  const subject: Subject | null =
    mine !== null
      ? {
          rowId: mine.rowId,
          scope: mine.scope,
          displayPath: mine.displayPath,
          realPath: mine.realPath,
        }
      : warning !== null
        ? subjectOfRow(warning)
        : null;
  const drift = useDrift(project, open && subject !== null ? subject.rowId : null);
  const errorRef = useRef<HTMLDivElement>(null);
  // A refused or lost undo takes focus, as a refused save does.
  const undoKind = undo.state.kind;
  useEffect(() => {
    if (undoKind === "refused" || undoKind === "failed" || undoKind === "restart") {
      errorRef.current?.focus();
    }
  }, [undoKind]);

  if (subject === null) return null;

  const sending = undo.state.kind === "sending" && undo.state.rowId === subject.rowId;
  const undone = undo.state.kind === "done" && undo.state.rowId === subject.rowId;
  const failed =
    (undo.state.kind === "refused" || undo.state.kind === "failed") &&
    undo.state.rowId === subject.rowId
      ? undo.state
      : null;
  const doUndo = (): void => {
    onUndo({
      rowId: subject.rowId,
      scope: subject.scope,
      displayPath: subject.displayPath,
      realPath: subject.realPath,
    });
  };

  if (undone) {
    return (
      <p className="setup-undone" role="status">
        <span aria-hidden="true">{"↺ "}</span>
        {t("cg_undone_at", { time: clockShort(conn.lastAnswerAt ?? 0) })}
      </p>
    );
  }

  const state = mine !== null ? (recheck.answer?.state ?? "checking") : "overwritten";
  const keys =
    mine !== null ? (recheck.answer?.changed_keys ?? []) : (warning?.recheck?.changed_keys ?? []);
  const ours =
    mine !== null
      ? (recheck.answer?.ours_survived ?? null)
      : (warning?.recheck?.ours_survived ?? null);

  const driftView: DriftView | undefined = !open
    ? undefined
    : drift.isPending
      ? { state: "loading" }
      : drift.data?.lines != null
        ? {
            state: "lines",
            lines: drift.data.lines,
            path: subject.displayPath,
            ...(subject.realPath !== null ? { linksTo: subject.realPath } : {}),
          }
        : {
            state: "refused",
            code:
              drift.error instanceof EditRequestError
                ? drift.error.reason
                : (drift.data?.code ?? "cant_rebuild"),
            file: fileNameOf(subject.displayPath),
          };

  const problem =
    undo.restart !== null ? (
      <RestartBox
        restart={undo.restart}
        command={editCommand()}
        onReload={() => {
          window.location.reload();
        }}
        messageRef={errorRef}
      />
    ) : failed !== null ? (
      <RefusedMessage
        undo
        code={failed.kind === "refused" ? failed.code : failed.reason}
        file={fileNameOf(subject.displayPath)}
        messageRef={errorRef}
      />
    ) : null;

  return (
    <>
      {problem}
      {state === "overwritten" ? (
        <OverwrittenBox
          keys={keys}
          ours={ours}
          field={fieldWord(field)}
          open={open}
          onToggle={() => {
            if (!open) markSeen.mutate(subject.rowId);
            setOpen(!open);
          }}
          {...(driftView !== undefined ? { drift: driftView } : {})}
          onUndo={doUndo}
          undoBusy={sending}
          undoDisabled={undo.restart !== null}
        />
      ) : (
        <SavedBox
          savedAt={mine?.savedAt ?? ""}
          recheck={
            state === "confirmed"
              ? { state: "confirmed", value: mine?.value ?? "" }
              : { state: "checking" }
          }
          onUndo={doUndo}
          undoBusy={sending}
          undoDisabled={undo.restart !== null}
          changesHref={changesHref}
        />
      )}
    </>
  );
}

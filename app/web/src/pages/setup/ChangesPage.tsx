/*
 * The Changes page, #/p/<project>/setup/changes (plan 5.4, board x-history). Every save Bar Tab made
 * for the project, newest first and grouped by day, with the columns When, Change, File and Undo.
 * Undo shows the button and the row's undo state, and under it the recheck outcome. Undo of a file
 * that changed since opens the undo confirm inline under its row, with focus on it. Older saves wait
 * in a disclosure, and the line under it names the real backup folder with Copy path.
 *
 * History is read-only, so the page works with edits off. Then one note at the top says Undo needs
 * edits on, and each Undo is aria-disabled with no reason of its own. At 720px and under each row
 * stacks, and its four column words stay as visually hidden labels. An empty history says what will appear and links
 * to Your setup.
 */
import { useState } from "react";
import { Button as AriaButton, Disclosure, DisclosurePanel } from "react-aria-components";
import { useParams } from "react-router";
import { useProjects } from "@/api/client";
import { useHistory, useUndo } from "@/api/edit";
import type { EditHistory, HistoryRow, UndoHandle } from "@/api/edit";
import { postStatus } from "@/app/harness";
import { Button } from "@/components/Button/Button";
import { Card } from "@/components/Card/Card";
import { CopyPath } from "@/components/CopyPath/CopyPath";
import { PathText } from "@/components/Diff/PathText";
import { EditsOffNote } from "@/components/EditsOffNote/EditsOffNote";
import { EmptyState } from "@/components/EmptyState/EmptyState";
import { HelpButton } from "@/components/HelpButton/HelpButton";
import { PageHeader } from "@/components/PageHeader/PageHeader";
import { RefusedMessage } from "@/components/RefusedMessage/RefusedMessage";
import { RestartBox } from "@/components/RestartBox/RestartBox";
import { clockShort } from "@/lib/clock";
import {
  changeText,
  groupByDay,
  hasUndo,
  RECHECK_GLYPH,
  recheckWord,
  rowFieldLabel,
  undoStateText,
} from "@/lib/changes";
import { CODE_MARK, fullPathOf, scopeName, splitOnMark } from "@/lib/edit-words";
import { changesPath, setupPath } from "@/lib/setup-routes";
import { t, tn } from "@/strings/t";
import { editCommand, fileNameOf, useEditAvailability } from "./edit-mode";
import { SetupBones, SetupError } from "./SetupStates";
import { DeleteUndoPanel, UndoPanel, useUndoConfirm } from "./UndoPanel";
import type { UndoTarget } from "./UndoPanel";
import "./ChangesPage.css";

export function ChangesPage() {
  const { project } = useParams();
  if (project === undefined) return null;
  return <ChangesView key={project} project={project} />;
}

/** Where a row's undo went wrong, under the row. A restart shows once, at the top of the page. */
function RowProblem({ row, undo }: { row: HistoryRow; undo: UndoHandle }) {
  const { state } = undo;
  if ((state.kind === "refused" || state.kind === "failed") && state.rowId === row.id) {
    return (
      <RefusedMessage
        undo
        code={state.kind === "refused" ? state.code : state.reason}
        file={fileNameOf(row.display_path)}
        className="changes-problem"
      />
    );
  }
  return null;
}

interface RowsProps {
  rows: HistoryRow[];
  undo: UndoHandle;
  /** Edits are on, so Undo works. Otherwise it is aria-disabled. */
  canUndo: boolean;
  onUndo: (row: HistoryRow) => void;
  /** The undo confirm of a row, or null. It sits inline under the row. */
  confirmFor: (row: HistoryRow) => React.ReactNode;
  /** The project's own path as the project list shows it, for the full path of a file it holds. */
  projectPath: string | undefined;
}

function Row({
  row,
  undo,
  canUndo,
  onUndo,
  projectPath,
  confirm,
}: Omit<RowsProps, "rows" | "confirmFor"> & { row: HistoryRow; confirm: React.ReactNode }) {
  const changeId = `change-${row.id}`;
  const sending = undo.state.kind === "sending" && undo.state.rowId === row.id;
  const link = row.real_path !== row.display_path;
  // A row whose undo deletes the file names the whole path of what goes, "~" for home.
  const deletes = row.undo_state === "deletes_file";
  const shownPath = deletes ? fullPathOf(row.display_path, projectPath) : row.display_path;
  const shownReal = deletes ? fullPathOf(row.real_path, projectPath) : row.real_path;
  const recheck = row.recheck;
  const field = rowFieldLabel(row.field).toLowerCase();
  // An undo is a row of its own and has nothing to undo or recheck, so its Undo cell stays empty.
  const isUndo = row.op === "undo";
  const stateText = undoStateText(row);
  const note =
    recheck?.state !== "overwritten"
      ? null
      : recheck.ours_survived === true
        ? t("rc_overwritten_kept", { field })
        : recheck.ours_survived === false
          ? t("rc_overwritten_lost", { field })
          : null;
  return (
    <li className="changes-row">
      <span className="changes-cell changes-when">
        <span className="sr-only">{t("cg_col_when")}</span>
        {clockShort(row.time)}
      </span>
      <span className="changes-cell changes-what" id={changeId}>
        <span className="sr-only">{t("cg_col_change")}</span>
        {changeText(row)}
      </span>
      <span className="changes-cell changes-file">
        <span className="sr-only">{t("cg_col_file")}</span>
        <span className="changes-chip">{scopeName(row.scope)}</span>
        <PathText path={shownPath} />
        {link && (
          <small className="changes-link">
            <span aria-hidden="true">{"↪"}</span> {t("ed_links_to")}{" "}
            <span className="changes-real">{shownReal}</span>
          </small>
        )}
      </span>
      <span className="changes-cell changes-undo">
        <span className="sr-only">{t("cg_col_undo")}</span>
        {!isUndo && hasUndo(row.undo_state) && (
          <Button
            disabled={!canUndo}
            busy={sending}
            describedBy={changeId}
            onPress={() => {
              onUndo(row);
            }}
          >
            {t("ed_undo")}
          </Button>
        )}
        {!isUndo && stateText !== null && (
          <small className="changes-state muted">
            {row.undo_state === "undone" && <span aria-hidden="true">{"↺ "}</span>}
            {stateText}
          </small>
        )}
        {!isUndo && recheck !== null && (
          <small className="changes-recheck">
            <span className="changes-recheck-word">
              {recheck.state === "checking" ? (
                <span className="ring-mark" aria-hidden="true" />
              ) : (
                <span aria-hidden="true">{RECHECK_GLYPH[recheck.state]}</span>
              )}{" "}
              {recheckWord(recheck.state)}
            </span>
            {note !== null && <span className="changes-recheck-note muted">{note}</span>}
          </small>
        )}
      </span>
      <RowProblem row={row} undo={undo} />
      {confirm}
    </li>
  );
}

function Rows({ rows, confirmFor, ...rest }: RowsProps) {
  return (
    <ol className="changes-list">
      {rows.map((item) => (
        <Row key={item.id} row={item} confirm={confirmFor(item)} {...rest} />
      ))}
    </ol>
  );
}

function BackupLine({ folder }: { folder: EditHistory["backup_folder"] }) {
  const [before, after] = splitOnMark(t("cg_backup_folder", { path: CODE_MARK }));
  return (
    <p className="changes-backup">
      <span>
        {before}
        <code className="changes-folder">{folder.display}</code>
        {after}
      </span>
      <CopyPath
        value={folder.real}
        label={t("in_copy")}
        copiedLabel={t("an_copied")}
        onStatus={postStatus}
      />
    </p>
  );
}

function ChangesView({ project }: { project: string }) {
  const history = useHistory(project);
  const projects = useProjects();
  const availability = useEditAvailability(project);
  const undo = useUndo(project);
  const confirm = useUndoConfirm(undo);
  const [target, setTarget] = useState<UndoTarget | null>(null);
  // The row whose undo deletes the file asks first, in a panel under it, before any request.
  const [deleting, setDeleting] = useState<UndoTarget | null>(null);
  const entry = projects.data?.projects.find((p) => p.key === project);
  const projectName = entry?.name ?? project;
  const projectPath = entry?.display_path;
  const title = t("cg_h1");
  // A page that holds a stale key offers no write, so Undo holds until the page reloads.
  const canUndo = availability.kind === "on" && undo.state.kind !== "restart";

  const targetOf = (row: HistoryRow): UndoTarget => ({
    rowId: row.id,
    scope: row.scope,
    displayPath: row.display_path,
    realPath: row.real_path !== row.display_path ? row.real_path : null,
    fullPath: fullPathOf(row.real_path, projectPath),
  });
  const startUndo = (row: HistoryRow): void => {
    if (row.undo_state === "deletes_file") {
      setDeleting(targetOf(row));
      return;
    }
    setTarget(targetOf(row));
    undo.undo(row.id, row.scope);
  };
  const undoKind = undo.state.kind;
  const sendingId = undo.state.kind === "sending" ? undo.state.rowId : null;
  const confirmFor = (row: HistoryRow): React.ReactNode => {
    if (confirm !== null && target !== null && confirm.rowId === row.id) {
      return (
        <div className="changes-confirm">
          <UndoPanel view={confirm} undo={undo} target={target} inline />
        </div>
      );
    }
    // The delete panel stays up while its undo is sent, and goes when the answer comes back.
    if (
      deleting !== null &&
      deleting.rowId === row.id &&
      (undoKind === "idle" || sendingId === row.id)
    ) {
      return (
        <div className="changes-confirm">
          <DeleteUndoPanel
            target={deleting}
            busy={sendingId === row.id}
            onKeep={() => {
              setDeleting(null);
            }}
            onAnyway={() => {
              undo.undo(deleting.rowId, deleting.scope);
            }}
          />
        </div>
      );
    }
    return null;
  };

  const header = (
    <PageHeader
      title={title}
      sub={t("cg_sub", { project: projectName })}
      breadcrumb={{
        label: t("bc_label"),
        items: [
          { label: t("nav_setup"), href: `#${setupPath(project)}` },
          { label: title, href: `#${changesPath(project)}` },
        ],
      }}
    />
  );

  const data = history.data;
  let body: React.ReactNode;
  if (data === undefined) {
    body = (
      <Card title={title} className="changes-card">
        {history.isError ? (
          <SetupError
            card={title.toLowerCase()}
            onRetry={() => {
              void history.refetch();
            }}
          />
        ) : (
          <SetupBones line={t("ld_line", { card: title.toLowerCase() })} rows={4} />
        )}
      </Card>
    );
  } else if (data.rows.length === 0 && data.older.count === 0) {
    body = (
      <EmptyState
        variant="page"
        title={t("cg_empty_h")}
        action={{ label: t("cg_empty_link"), href: `#${setupPath(project)}` }}
      >
        {t("cg_empty_b")}
      </EmptyState>
    );
  } else {
    const groups = groupByDay(data.rows, data.server_time);
    const shared = { undo, canUndo, onUndo: startUndo, confirmFor, projectPath };
    const older = (
      <>
        {data.older.count > 0 && (
          <Disclosure className="changes-older">
            <AriaButton slot="trigger" className="changes-older-trigger">
              <span className="changes-chevron" aria-hidden="true" />
              <span className="changes-older-h">{t("cg_older_h")}</span>
              <small className="muted">{tn("cg_older", data.older.count)}</small>
            </AriaButton>
            <DisclosurePanel className="changes-older-panel">
              <Rows rows={data.older.rows} {...shared} />
            </DisclosurePanel>
          </Disclosure>
        )}
        <BackupLine folder={data.backup_folder} />
      </>
    );
    body =
      groups.length === 0 ? (
        <Card title={t("cg_older_h")} className="changes-card">
          {older}
        </Card>
      ) : (
        groups.map((group, index) => (
          <Card
            key={group.key}
            title={group.label}
            count={String(group.rows.length)}
            className="changes-card"
            {...(index === 0 ? { right: <HelpButton help="edit.history" /> } : {})}
          >
            <div className="changes-head" aria-hidden="true">
              <span>{t("cg_col_when")}</span>
              <span>{t("cg_col_change")}</span>
              <span>{t("cg_col_file")}</span>
              <span>{t("cg_col_undo")}</span>
            </div>
            <Rows rows={group.rows} {...shared} />
            {index === groups.length - 1 && older}
          </Card>
        ))
      );
  }

  return (
    <div className="setup-page changes-page">
      {header}
      {data !== undefined && !canUndo && availability.kind !== "loading" && (
        <div className="changes-note">
          {availability.kind === "off" ? (
            <EditsOffNote kind="history" command={availability.command} />
          ) : availability.kind === "folder" ? (
            <EditsOffNote kind="folder" path={availability.path} />
          ) : (
            <EditsOffNote kind="demo" />
          )}
        </div>
      )}
      {undo.state.kind === "restart" && (
        <RestartBox
          restart={undo.restart ?? { mode: null }}
          command={editCommand()}
          onReload={() => {
            window.location.reload();
          }}
          className="changes-problem"
        />
      )}
      {body}
    </div>
  );
}

/*
 * Sample data for the edit components on the component sheet (M6a): the Diff, the Save to list, the
 * This save card, the edit rail and its phone sheet, the saved, refused, overwritten, undo and
 * restart boxes, the edits-off notes and the phone action bar. Every word comes from the string deck
 * or words.ts (sheet-only words), and every path, value and time is made up for the sheet, from the
 * same data as the designer's boards (tidewater-reporting, effort xhigh to medium). Nothing here is
 * real data. The effort choice is a stand-in for the page's value control, which is not a
 * component yet.
 */
import { useState } from "react";
import type {
  DiffLine,
  EditPreview,
  EditScope,
  EditScopeRow,
  EditWarning,
  RunsAt,
} from "@/api/edit";
import { Button } from "@/components/Button/Button";
import { Diff } from "@/components/Diff/Diff";
import { EditRail } from "@/components/EditRail/EditRail";
import { EditsOffNote } from "@/components/EditsOffNote/EditsOffNote";
import { OverwrittenBox, type DriftView } from "@/components/OverwrittenBox/OverwrittenBox";
import { PhoneActionBar } from "@/components/PhoneActionBar/PhoneActionBar";
import { RefusedMessage } from "@/components/RefusedMessage/RefusedMessage";
import { RestartBox } from "@/components/RestartBox/RestartBox";
import { SavedBox } from "@/components/SavedBox/SavedBox";
import { SaveToList } from "@/components/SaveToList/SaveToList";
import { ThisSave } from "@/components/ThisSave/ThisSave";
import { UndoConfirm } from "@/components/UndoConfirm/UndoConfirm";
import { SegmentedChoice } from "@/components/Segmented/Segmented";
import { scopeName } from "@/lib/edit-words";
import { t } from "@/strings/t";
import { W } from "./words";

const COMMAND = "/bartab-preview --allow-edits";
const HOME = "~/work/tidewater-reporting";
const PATH: Record<EditScope, string> = {
  local: `${HOME}/.claude/settings.local.json`,
  project: `${HOME}/.claude/settings.json`,
  user: "~/.claude/settings.json",
};
const USER_REAL = "~/dotfiles/claude/settings.json";

/** A clock time that reads the same in every time zone. */
const at = (h: number, m: number, s: number): string =>
  new Date(2026, 10, 11, h, m, s).toISOString();

const runs = (value: string | null, status: RunsAt["status"]): RunsAt => ({ value, status });

function row(scope: EditScope, over: Partial<EditScopeRow> = {}): EditScopeRow {
  const win = scope === "local";
  return {
    scope,
    display_path: PATH[scope],
    real_path: scope === "user" ? USER_REAL : PATH[scope],
    link: scope === "user",
    git_tracked: scope === "project",
    writable: true,
    read_only_reason: null,
    current_value: scope === "local" ? "xhigh" : scope === "project" ? "medium" : "xhigh",
    outcome: win
      ? { status: "in_effect", beaten_by: null }
      : { status: "overridden", beaten_by: "local" },
    ...over,
  };
}

export function scopeRows(
  over: Partial<Record<EditScope, Partial<EditScopeRow>>> = {},
): EditScopeRow[] {
  return (["local", "project", "user"] as const).map((scope) => row(scope, over[scope]));
}

const LOCAL_DIFF: DiffLine[] = [
  { kind: "ctx", old_n: 2, new_n: 2, text: '  "env": {' },
  { kind: "del", old_n: 3, new_n: null, text: '    "CLAUDE_CODE_EFFORT_LEVEL": "xhigh"' },
  { kind: "add", old_n: null, new_n: 3, text: '    "CLAUDE_CODE_EFFORT_LEVEL": "medium"' },
  { kind: "ctx", old_n: 4, new_n: 4, text: "  }," },
];

const USER_DIFF: DiffLine[] = [
  { kind: "ctx", old_n: 2, new_n: 2, text: '  "model": "opus",' },
  { kind: "del", old_n: 3, new_n: null, text: '  "effortLevel": "xhigh",' },
  { kind: "add", old_n: null, new_n: 3, text: '  "effortLevel": "medium",' },
  { kind: "ctx", old_n: 4, new_n: 4, text: '  "theme": "dark"' },
];

const NEW_FILE_DIFF: DiffLine[] = [
  { kind: "add", old_n: null, new_n: 1, text: "{" },
  { kind: "add", old_n: null, new_n: 2, text: '  "effortLevel": "medium"' },
  { kind: "add", old_n: null, new_n: 3, text: "}" },
];

const UNDO_DIFF: DiffLine[] = [
  { kind: "ctx", old_n: 2, new_n: 2, text: '  "permissions": {' },
  { kind: "del", old_n: 3, new_n: null, text: '    "allow": ["Bash(make test)"]' },
  { kind: "ctx", old_n: 4, new_n: 4, text: "  }," },
  { kind: "ctx", old_n: 5, new_n: 5, text: '  "env": {' },
  { kind: "del", old_n: 6, new_n: null, text: '    "CLAUDE_CODE_EFFORT_LEVEL": "medium"' },
  { kind: "add", old_n: null, new_n: 6, text: '    "CLAUDE_CODE_EFFORT_LEVEL": "xhigh"' },
  { kind: "ctx", old_n: 7, new_n: 7, text: "  }," },
];

const DRIFT_DIFF: DiffLine[] = [
  { kind: "ctx", old_n: 2, new_n: 2, text: '  "permissions": {' },
  { kind: "add", old_n: null, new_n: 3, text: '    "allow": ["Bash(make test)"]' },
  { kind: "ctx", old_n: 4, new_n: 4, text: "  }," },
];

const LONG_DIFF: DiffLine[] = [
  {
    kind: "del",
    old_n: 12,
    new_n: null,
    text: '    "ANTHROPIC_DEFAULT_OPUS_MODEL_DESCRIPTION_OVERRIDE_FOR_TIDEWATER_REPORTING": "xhigh"',
  },
  {
    kind: "add",
    old_n: null,
    new_n: 12,
    text: '    "ANTHROPIC_DEFAULT_OPUS_MODEL_DESCRIPTION_OVERRIDE_FOR_TIDEWATER_REPORTING": "medium"',
  },
];

export interface PreviewOptions {
  scope?: EditScope;
  model?: boolean;
  readAt?: string;
  warnings?: EditWarning[];
  reaches?: number;
  fresh?: boolean;
  newValue?: boolean;
}

/** A preview of an effort save, or a model save, as the board draws it. */
export function samplePreview(options: PreviewOptions = {}): EditPreview {
  const { scope = "local", model = false, warnings = [], reaches = 0, newValue = false } = options;
  const link = scope === "user";
  const diff = newValue
    ? NEW_FILE_DIFF
    : scope === "user"
      ? USER_DIFF
      : options.fresh === true
        ? LOCAL_DIFF.map((line) => ({
            ...line,
            old_n: line.old_n === null ? null : line.old_n + 6,
            new_n: line.new_n === null ? null : line.new_n + 6,
          }))
        : LOCAL_DIFF;
  const now = model ? runs("opus", "in_effect") : runs("high", "lowered");
  const after = model
    ? runs("sonnet", "in_effect")
    : scope === "user"
      ? runs("high", "lowered")
      : runs("medium", "in_effect");
  return {
    server_time: at(18, 41, 12),
    seq: 1,
    choice_key: `${scope}-medium`,
    target: {
      scope,
      display_path: PATH[scope],
      real_path: link ? USER_REAL : PATH[scope],
      link,
      exists: !newValue,
      git_tracked: scope === "project",
      new_file: newValue,
    },
    effect: {
      set: {
        from: newValue ? null : model ? "opus" : "xhigh",
        to: model ? "sonnet" : "medium",
      },
      runs: { now, after },
      applies: "new_session",
    },
    options: [],
    scopes: scopeRows(),
    reaches: Array.from({ length: reaches }, (_, i) => ({
      project: `p${String(i)}`,
      name: `Project ${String(i + 1)}`,
      outcome: { status: "in_effect" as const, beaten_by: null },
    })),
    warnings,
    diff: { lines: diff, new_file: newValue },
    summary: {
      verb: newValue ? "creates" : "changes",
      lines_changed: 1,
      display_path: PATH[scope],
    },
    read_at: options.readAt ?? at(18, 41, 12),
    version: "v1",
    refusal: null,
  };
}

/* ---------- The effort choice (Segmented, choice variant) ---------- */

const LEVELS = ["low", "medium", "high", "xhigh", "max"] as const;

function EffortChoice({
  picked,
  onPick,
  now,
  disabled = false,
  forced,
}: {
  picked: string;
  onPick: (level: string) => void;
  now: string | null;
  disabled?: boolean;
  forced?: { level: string; className: string };
}) {
  return (
    <SegmentedChoice
      label={t("sl_effortLevel")}
      hint={W.sheet_edit_hint}
      value={picked}
      onChange={onPick}
      disabled={disabled}
      {...(disabled ? { disabledReason: W.sheet_edit_off_reason } : {})}
      options={LEVELS.map((level) => ({
        id: level,
        label: level,
        ...(level === now ? { now: true } : {}),
        ...(forced?.level === level ? { className: forced.className } : {}),
      }))}
    />
  );
}

export type SegmentedChoiceState =
  "choice" | "choice-now" | "choice-hover" | "choice-focus" | "choice-disabled" | "choice-phone";

/** The choice variant of the segmented control, as the edit rail draws it. */
export function SegmentedChoiceDemo({ state }: { state: SegmentedChoiceState }) {
  const [picked, setPicked] = useState("medium");
  const control = (
    <EffortChoice
      picked={picked}
      onPick={setPicked}
      now={state === "choice" ? null : "xhigh"}
      disabled={state === "choice-disabled"}
      {...(state === "choice-hover"
        ? { forced: { level: "high", className: "is-hover" } }
        : state === "choice-focus"
          ? { forced: { level: "high", className: "is-focus" } }
          : {})}
    />
  );
  return state === "choice-phone" ? (
    <div className="sheet-phone sheet-pad">{control}</div>
  ) : (
    control
  );
}

/* ---------- Diff ---------- */

export type DiffState = "default" | "link" | "new-file" | "no-path" | "wrap";

export function DiffDemo({ state }: { state: DiffState }) {
  switch (state) {
    case "default":
      return <Diff lines={LOCAL_DIFF} label={t("ed_this_save_h")} path={PATH.local} />;
    case "link":
      return (
        <Diff lines={USER_DIFF} label={t("ed_this_save_h")} path={PATH.user} linksTo={USER_REAL} />
      );
    case "new-file":
      return <Diff lines={NEW_FILE_DIFF} label={t("ed_this_save_h")} path={PATH.local} />;
    case "no-path":
      return <Diff lines={LOCAL_DIFF} label={t("ed_this_save_h")} />;
    case "wrap":
      return (
        <div className="sheet-phone">
          <Diff lines={LONG_DIFF} label={t("ed_this_save_h")} path={PATH.local} />
        </div>
      );
  }
}

/* ---------- SaveToList ---------- */

export type SaveToState =
  "default" | "hover" | "focus" | "user-link" | "not-writable" | "disabled" | "phone";

export function SaveToListDemo({ state }: { state: SaveToState }) {
  const [picked, setPicked] = useState<EditScope>(state === "user-link" ? "user" : "local");
  const rows =
    state === "not-writable"
      ? scopeRows({
          project: { writable: false, read_only_reason: "managed" },
          user: { writable: false, read_only_reason: "not_writable" },
        })
      : scopeRows();
  const list = (
    <SaveToList
      scopes={rows}
      picked={picked}
      onPick={setPicked}
      warning={{ project: W.sheet_project, field: W.sheet_edit_field }}
      disabled={state === "disabled"}
      {...(state === "hover"
        ? { rowClass: { project: "is-hover" } }
        : state === "focus"
          ? { rowClass: { project: "is-focus" } }
          : {})}
    />
  );
  return state === "phone" ? <div className="sheet-phone sheet-pad">{list}</div> : list;
}

/* ---------- ThisSave ---------- */

export type ThisSaveState =
  "default" | "user-link" | "model" | "updating" | "warnings" | "new-value" | "phone";

export function ThisSaveDemo({ state }: { state: ThisSaveState }) {
  const applies = t("ap_new_session");
  switch (state) {
    case "default":
      return <ThisSave preview={samplePreview()} applies={applies} />;
    case "user-link":
      return <ThisSave preview={samplePreview({ scope: "user", reaches: 2 })} applies={applies} />;
    case "model":
      return <ThisSave preview={samplePreview({ model: true })} runsOn applies={applies} />;
    case "updating":
      return <ThisSave preview={samplePreview()} applies={applies} updating />;
    case "warnings":
      return (
        <ThisSave
          preview={samplePreview({
            warnings: [
              { code: "wont_win", params: { scope: "local" } },
              { code: "config_change_hook", params: {} },
              { code: "shared_repo", params: { file: "settings.json" } },
            ],
          })}
          applies={applies}
        />
      );
    case "new-value":
      return <ThisSave preview={samplePreview({ newValue: true })} applies={applies} />;
    case "phone":
      return (
        <div className="sheet-phone sheet-pad">
          <ThisSave preview={samplePreview({ readAt: at(18, 42, 31) })} applies={applies} />
        </div>
      );
  }
}

/* ---------- EditRail ---------- */

export type EditRailState =
  "default" | "message" | "updating" | "saving" | "refusal" | "sheet" | "sheet-saving";

/** The rail with its parts, so a pick moves the preview as it does on the page. */
export function EditRailDemo({ state }: { state: EditRailState }) {
  const [scope, setScope] = useState<EditScope>("local");
  const [level, setLevel] = useState("medium");
  const sheet = state === "sheet" || state === "sheet-saving";
  const preview = samplePreview({
    scope,
    readAt: state === "message" ? at(18, 42, 31) : at(18, 41, 12),
    fresh: state === "message",
  });
  const message =
    state === "message" ? (
      <RefusedMessage
        code="changed"
        file="settings.local.json"
        changedKeys={["permissions.allow"]}
      />
    ) : null;
  const rail = (
    <EditRail
      field={W.sheet_edit_field}
      scopeName={scopeName(scope)}
      layout={sheet ? "sheet" : "rail"}
      inline
      saving={state === "saving" || state === "sheet-saving"}
      summary={W.sheet_edit_summary}
      {...(state === "refusal"
        ? { refusal: { code: "link_outside" as const, file: "settings.json" } }
        : {})}
      onSave={() => undefined}
      onCancel={() => undefined}
      message={message}
      control={<EffortChoice picked={level} onPick={setLevel} now={row(scope).current_value} />}
      saveTo={
        <SaveToList
          scopes={scopeRows()}
          picked={scope}
          onPick={setScope}
          warning={{ project: W.sheet_project, field: W.sheet_edit_field }}
        />
      }
      thisSave={
        <ThisSave preview={preview} applies={t("ap_new_session")} updating={state === "updating"} />
      }
    />
  );
  return sheet ? <div className="sheet-phone">{rail}</div> : rail;
}

/* ---------- SavedBox ---------- */

export type SavedBoxState = "checking" | "confirmed" | "undo-busy" | "phone";

export function SavedBoxDemo({ state }: { state: SavedBoxState }) {
  const box = (
    <SavedBox
      savedAt={at(18, 41, 0)}
      recheck={
        state === "checking" ? { state: "checking" } : { state: "confirmed", value: "medium" }
      }
      onUndo={() => undefined}
      undoBusy={state === "undo-busy"}
      changesHref="#changes"
    />
  );
  return state === "phone" ? <div className="sheet-phone sheet-pad">{box}</div> : box;
}

/* ---------- RefusedMessage ---------- */

export type RefusedState =
  | "changed"
  | "changed-ours"
  | "changed-no-keys"
  | "link-outside"
  | "preview-mismatch"
  | "not-undone";

export function RefusedMessageDemo({ state }: { state: RefusedState }) {
  switch (state) {
    case "changed":
      return (
        <RefusedMessage
          code="changed"
          file="settings.local.json"
          changedKeys={["permissions.allow"]}
        />
      );
    case "changed-ours":
      return (
        <RefusedMessage
          code="changed"
          file="settings.local.json"
          changedKeys={["permissions.allow", "env.CLAUDE_CODE_EFFORT_LEVEL"]}
          editedKeyChanged
        />
      );
    case "changed-no-keys":
      return <RefusedMessage code="changed" file="settings.local.json" />;
    case "link-outside":
      return <RefusedMessage code="link_outside" file="settings.json" />;
    case "preview-mismatch":
      return <RefusedMessage code="preview_mismatch" file="settings.local.json" />;
    case "not-undone":
      return <RefusedMessage code="not_undoable" file="settings.local.json" undo />;
  }
}

/* ---------- OverwrittenBox ---------- */

export type OverwrittenState =
  "kept" | "lost" | "drift-open" | "drift-loading" | "drift-refused" | "many-keys";

export function OverwrittenBoxDemo({ state }: { state: OverwrittenState }) {
  const [open, setOpen] = useState(
    state === "drift-open" || state === "drift-loading" || state === "drift-refused",
  );
  const drift: DriftView =
    state === "drift-loading"
      ? { state: "loading" }
      : state === "drift-refused"
        ? { state: "refused", code: "cant_rebuild", file: "settings.local.json" }
        : { state: "lines", lines: DRIFT_DIFF, path: PATH.local };
  return (
    <OverwrittenBox
      keys={
        state === "many-keys"
          ? ["permissions.allow", "permissions.deny", "env.ANTHROPIC_LOG"]
          : ["permissions.allow"]
      }
      ours={state === "lost" ? false : true}
      field={W.sheet_edit_field}
      open={open}
      onToggle={() => {
        setOpen((value) => !value);
      }}
      drift={drift}
      onUndo={() => undefined}
    />
  );
}

/* ---------- UndoConfirm ---------- */

export type UndoConfirmState = "default" | "busy" | "sheet";

export function UndoConfirmDemo({ state }: { state: UndoConfirmState }) {
  const confirm = (
    <UndoConfirm
      file="settings.local.json"
      path={PATH.local}
      lines={UNDO_DIFF}
      busy={state === "busy"}
      layout={state === "sheet" ? "sheet" : "panel"}
      onKeep={() => undefined}
      onAnyway={() => undefined}
    />
  );
  return state === "sheet" ? <div className="sheet-phone">{confirm}</div> : confirm;
}

/* ---------- EditsOffNote ---------- */

export type EditsOffState =
  "reason" | "reason-demo" | "reason-folder" | "history" | "route" | "route-focus" | "route-agent";

/** The disabled Edit button with its reason, as the inspector foot draws them. */
function DisabledEdit({ children, id }: { children: React.ReactNode; id: string }) {
  return (
    <div className="sheet-edit-foot">
      <div className="sheet-wrap">
        <Button variant="primary" disabled describedBy={id}>
          {W.in_edit}
        </Button>
        <Button>{W.in_copy}</Button>
      </div>
      {children}
    </div>
  );
}

export function EditsOffNoteDemo({ state }: { state: EditsOffState }) {
  switch (state) {
    case "reason":
      return (
        <DisabledEdit id="sheet-eo-reason">
          <EditsOffNote id="sheet-eo-reason" kind="reason" command={COMMAND} />
        </DisabledEdit>
      );
    case "reason-demo":
      return <EditsOffNote kind="demo" />;
    case "reason-folder":
      return <EditsOffNote kind="folder" path="~/work/tidewater-reporting" />;
    case "history":
      return <EditsOffNote kind="history" command={COMMAND} />;
    case "route":
      return <EditsOffNote kind="route" command={COMMAND} item={t("sl_effortLevel")} />;
    case "route-focus":
      return (
        <EditsOffNote
          kind="route"
          command={COMMAND}
          item={t("sl_effortLevel")}
          className="is-focus"
        />
      );
    case "route-agent":
      return <EditsOffNote kind="agent" name="builder" />;
  }
}

/* ---------- RestartBox ---------- */

export type RestartState = "off" | "on" | "unknown" | "phone";

export function RestartBoxDemo({ state }: { state: RestartState }) {
  const box = (
    <RestartBox
      restart={{
        mode: state === "off" || state === "phone" ? "off" : state === "on" ? "on" : null,
      }}
      command={COMMAND}
      onReload={() => undefined}
    />
  );
  return state === "phone" ? <div className="sheet-phone sheet-pad">{box}</div> : box;
}

/* ---------- PhoneActionBar ---------- */

export type PhoneBarState = "default" | "with-link" | "button-only";

export function PhoneActionBarDemo({ state }: { state: PhoneBarState }) {
  const save = <Button variant="primary">{t("ed_save", { scope: scopeName("local") })}</Button>;
  return (
    <div className="sheet-phone">
      {state === "default" && (
        <PhoneActionBar summary={W.sheet_edit_summary}>{save}</PhoneActionBar>
      )}
      {state === "with-link" && (
        <PhoneActionBar
          summary={W.sheet_edit_summary}
          aside={<a href="#file">{W.sheet_edit_show_file}</a>}
        >
          {save}
        </PhoneActionBar>
      )}
      {state === "button-only" && <PhoneActionBar>{save}</PhoneActionBar>}
    </div>
  );
}

/*
 * The editor of one Settings item (direction B, plan 5.3). It sits beside the list at 721px and up
 * and is a full-height sheet at 720px and under, both through the EditRail. The rail holds the
 * field's control, the Save to list, This save and Save. Everything it shows about a save comes from
 * the server preview, and Save sends only the preview the page has drawn (usePreview and useSave).
 *
 * State. The control's text and the picked scope are the choice. The choice stays null while the
 * text isn't a value yet, and then no preview is asked for and the rail says so beside Save. A new
 * choice clears an old refusal. A refusal takes focus (tabindex -1, no role="alert"), and presses on
 * Save are ignored until the fresh preview has rendered. A restart (edits switched off, or the server
 * started again) shows the restart box and makes the whole rail inert: the control and the Save to
 * rows lock, and Save is aria-disabled and described by the box. A pick that is what is set now is
 * not an error. This save says so in one neutral line, and Save holds, described by that line.
 */
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Input, Label, TextField } from "react-aria-components";
import { useEditRestart, usePreview, useSave } from "@/api/edit";
import type {
  EditPreview,
  EditReason,
  EditScope,
  OptionRunsAt,
  SettingsChoice,
  SettingsEditField,
} from "@/api/edit";
import { usePrices } from "@/api/client";
import type { SetupItem } from "@/api/types";
import { EditRail } from "@/components/EditRail/EditRail";
import { RefusedMessage } from "@/components/RefusedMessage/RefusedMessage";
import { RestartBox } from "@/components/RestartBox/RestartBox";
import { SaveToList } from "@/components/SaveToList/SaveToList";
import { Select } from "@/components/Select/Select";
import type { SelectOption } from "@/components/Select/Select";
import { SegmentedChoice } from "@/components/Segmented/Segmented";
import { StatusChip } from "@/components/StatusChip/StatusChip";
import { ThisSave } from "@/components/ThisSave/ThisSave";
import {
  appliesWord,
  EFFORT_CAP_LEVELS,
  EFFORT_LEVELS,
  fieldLabel,
  fieldWord,
  requestValue,
  startChoice,
} from "@/lib/edit-page";
import { scopeName, statusWord } from "@/lib/edit-words";
import { modelLabel } from "@/lib/models";
import { t } from "@/strings/t";
import { editCommand, fileNameOf } from "./edit-mode";
import "./SettingsEditor.css";

/** What the inspector needs to show the Saved box once the rail closes. */
export interface SavedInfo {
  itemId: string;
  field: SettingsEditField;
  rowId: string;
  scope: EditScope;
  savedAt: string;
  /** The value that was saved, as the recheck line says it. */
  value: string;
  /** The file's display path, and its real path when it is a link. */
  displayPath: string;
  realPath: string | null;
}

export interface SettingsEditorProps {
  project: string;
  projectName: string;
  item: SetupItem;
  field: SettingsEditField;
  /** Cancel, Close and Escape. */
  onCancel: () => void;
  /** Called once, when the save went through. The page then closes the rail. */
  onSaved: (saved: SavedInfo) => void;
  headingRef: React.RefObject<HTMLHeadingElement | null>;
}

/** The levels the control offers, from the preview's options once it has them. */
function levelsOf(
  field: SettingsEditField,
  options: readonly OptionRunsAt[] | undefined,
): readonly string[] {
  if (options !== undefined && options.length > 0) return options.map((option) => option.value);
  return field === "maxEffortLevel" ? EFFORT_CAP_LEVELS : EFFORT_LEVELS;
}

/**
 * The run line inside one effort option: where it would run and its status, glyph and word, shown
 * before it is picked (designer item 11). An option that runs as it reads needs no line, so only a
 * level that lands somewhere else says "runs at high", with its status.
 */
function optionRuns(option: OptionRunsAt | undefined): React.ReactNode {
  if (option === undefined) return undefined;
  const at = option.runs_at;
  if (at.value === null || at.value === option.value) return undefined;
  return (
    <>
      <span>{t("ed_opt_runs", { value: at.value })}</span>
      <StatusChip status={at.status}>{statusWord(at.status)}</StatusChip>
    </>
  );
}

function WindowField({
  label,
  text,
  onChange,
  invalid,
  disabled,
}: {
  label: string;
  text: string;
  onChange: (text: string) => void;
  invalid: boolean;
  disabled: boolean;
}) {
  return (
    <TextField
      className="setup-window"
      value={text}
      onChange={onChange}
      inputMode="numeric"
      isInvalid={invalid}
      isDisabled={disabled}
    >
      <Label className="setup-window-label">{label}</Label>
      <Input className="setup-window-input" />
    </TextField>
  );
}

/** Model options: every priced model, and the value in the file now when it is another name. */
function modelItems(ids: readonly string[], current: string): SelectOption[] {
  const all = current === "" || ids.includes(current) ? [...ids] : [current, ...ids];
  return all.map((id) => ({ id, label: modelLabel(id) }));
}

export function SettingsEditor({
  project,
  projectName,
  item,
  field,
  onCancel,
  onSaved,
  headingRef,
}: SettingsEditorProps) {
  const start = useMemo(() => startChoice(item, field), [item, field]);
  const [scope, setScope] = useState<EditScope>(start.scope);
  const [text, setText] = useState(start.text);
  const value = requestValue(field, text);
  const choice: SettingsChoice | null = value === null ? null : { op: "set", scope, field, value };
  const handle = usePreview(project, choice);
  const save = useSave(project, handle);
  const restart = useEditRestart();
  const prices = usePrices();
  const { preview, pending } = handle;
  const label = fieldLabel(field);

  // A new choice clears the message of the last try. Saving again after a lost answer does not.
  const choiceKey = `${scope}|${text}`;
  const lastKey = useRef(choiceKey);
  useEffect(() => {
    if (lastKey.current === choiceKey) return;
    lastKey.current = choiceKey;
    save.reset();
  }, [choiceKey, save]);

  const messageRef = useRef<HTMLDivElement>(null);
  const restartId = useId();
  const neutralId = useId();
  const kind = save.state.kind;
  // A stale key makes the whole rail inert. Reload is the only way on.
  const inert = restart !== null || kind === "restart";
  const message: { code: EditReason | "restart"; key: string } | null = (() => {
    if (restart !== null || kind === "restart") return { code: "restart", key: "restart" };
    if (save.state.kind === "conflict")
      return { code: save.state.code, key: `c-${save.state.code}` };
    if (save.state.kind === "refused")
      return { code: save.state.code, key: `r-${save.state.code}` };
    if (save.state.kind === "failed")
      return { code: save.state.reason, key: `f-${save.state.reason}` };
    if (handle.reason !== null && preview === null) return { code: handle.reason, key: "p" };
    return null;
  })();
  const messageKey = message?.key ?? null;
  useEffect(() => {
    if (messageKey !== null) messageRef.current?.focus();
  }, [messageKey]);

  // The rail opens on its heading, so a screen reader reads "Edit effort" first.
  useEffect(() => {
    headingRef.current?.focus();
  }, [headingRef]);

  const savedOnce = useRef(false);
  useEffect(() => {
    if (save.state.kind !== "saved" || savedOnce.current) return;
    savedOnce.current = true;
    onSaved({
      itemId: item.id,
      field,
      rowId: save.state.saved.row_id,
      scope: save.state.scope,
      savedAt: save.state.saved.saved_at,
      value: text.trim(),
      displayPath: preview?.target.display_path ?? "",
      realPath: preview?.target.link === true ? preview.target.real_path : null,
    });
  }, [save.state, item.id, field, text, preview, onSaved]);

  const file = fileNameOf(preview?.target.display_path ?? "");
  const messageNode =
    message === null ? undefined : message.code === "restart" ? (
      <RestartBox
        restart={restart ?? { mode: null }}
        command={editCommand()}
        onReload={() => {
          window.location.reload();
        }}
        messageRef={messageRef}
        id={restartId}
      />
    ) : save.state.kind === "conflict" ? (
      <RefusedMessage
        code={save.state.code}
        file={file}
        changedKeys={save.state.changedKeys}
        editedKeyChanged={save.state.editedKeyChanged}
        messageRef={messageRef}
      />
    ) : (
      <RefusedMessage
        code={message.code}
        file={save.state.kind === "refused" ? (save.state.params.file ?? file) : file}
        messageRef={messageRef}
      />
    );

  // The picked value and file are what is set now. That is not an error, so the card says so in
  // one neutral line and Save holds without a reason line of its own (designer, round a15).
  const noChange = value !== null && preview?.refusal?.code === "no_change";
  const untouched = noChange && !pending;

  // The refusal beside Save: the preview's own, or a value the control can't turn into one.
  const refusal =
    value === null
      ? { code: "bad_value" as const, file }
      : preview?.refusal != null && preview.refusal.code !== "no_change" && !pending
        ? { code: preview.refusal.code, file: preview.refusal.params.file ?? file }
        : undefined;
  const hold = inert
    ? { describedBy: restartId }
    : untouched
      ? { describedBy: neutralId }
      : undefined;

  // After a refusal, Save waits for the fresh preview. After a restart it waits for a reload.
  const ignoring = ((kind === "conflict" || kind === "refused") && pending) || inert;
  const onSave = (): void => {
    if (ignoring || untouched || value === null) return;
    save.save();
  };

  const row = preview?.scopes.find((s) => s.scope === scope);
  const now = row?.current_value ?? null;

  let control: React.ReactNode;
  if (field === "effortLevel" || field === "maxEffortLevel") {
    const levels = levelsOf(field, preview?.options);
    control = (
      <SegmentedChoice
        label={label}
        value={text}
        onChange={(id) => {
          setText(id);
        }}
        disabled={inert}
        options={levels.map((level) => {
          const runs = optionRuns(preview?.options.find((option) => option.value === level));
          return {
            id: level,
            label: level,
            ...(level === now ? { now: true } : {}),
            ...(runs !== undefined ? { runs } : {}),
          };
        })}
      />
    );
  } else if (field === "model") {
    const ids = (prices.data?.models ?? []).map((m) => m.model);
    control = (
      <Select
        stacked
        label={label}
        items={modelItems(ids, start.text)}
        value={text === "" ? null : text}
        onChange={setText}
        isDisabled={inert}
      />
    );
  } else {
    control = (
      <WindowField
        label={label}
        text={text}
        onChange={setText}
        invalid={value === null}
        disabled={inert}
      />
    );
  }

  const saveTo =
    preview === null ? undefined : (
      <SaveToList
        scopes={preview.scopes}
        picked={scope}
        onPick={setScope}
        warning={{ project: projectName, field: fieldWord(field) }}
        disabled={kind === "saving" || inert}
      />
    );
  const thisSave =
    preview === null ? (
      <p className="setup-edit-wait muted" role="status">
        {t("ed_updating")}
      </p>
    ) : (
      <ThisSave
        preview={preview}
        runsOn={field === "model"}
        updating={pending}
        applies={appliesWord(preview.effect.applies)}
        {...(noChange ? { neutralId } : {})}
      />
    );

  return (
    <EditRail
      field={fieldWord(field)}
      scopeName={scopeName(scope)}
      control={control}
      saveTo={saveTo ?? null}
      thisSave={thisSave}
      {...(messageNode !== undefined ? { message: messageNode } : {})}
      summary={summaryOf(preview, file, noChange)}
      {...(refusal !== undefined ? { refusal } : {})}
      {...(hold !== undefined ? { hold } : {})}
      saving={kind === "saving" || kind === "held"}
      onSave={onSave}
      onCancel={onCancel}
      headingRef={headingRef}
    />
  );
}

/**
 * The phone foot: the file and the change, such as "settings.local.json, xhigh → medium", and under
 * it the link's real target when the file is a link. Nothing changes when the pick is what is set
 * now, so the foot names the file alone.
 */
function summaryOf(preview: EditPreview | null, file: string, noChange: boolean): React.ReactNode {
  if (preview === null) return "";
  const { from, to } = preview.effect.set;
  const line = noChange
    ? file
    : `${file}, ${from === null ? t("sc_none") : String(from)} → ${String(to)}`;
  const { link, real_path: real } = preview.target;
  return (
    <>
      {line}
      {link && (
        <span className="edit-foot-link">
          <span aria-hidden="true">{"↪"}</span> {t("ed_links_to")} {real}
        </span>
      )}
    </>
  );
}

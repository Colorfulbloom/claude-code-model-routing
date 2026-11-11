/*
 * The pure parts of the settings edit flow (M6a task a11): which Settings items have an editor, the
 * value a new edit starts from, the field's name as a word, the words for when a change applies, and
 * the edit routes. The page owns the state, and this file owns the rules, so the rules test alone.
 *
 * Four Settings items have an editor. Four more wait for M7 and say so (`field_until_m7`). The
 * server's item answer says neither, so the page reads the item's key, as the field registry does
 * (app/server/edit_fields.py).
 */
import type { EditApplies, EditScope, SettingsEditField } from "@/api/edit";
import type { SetupItem } from "@/api/types";
import { t } from "@/strings/t";

/** The fields an edit can change, in the order the Settings list shows them. */
export const EDIT_FIELDS: readonly SettingsEditField[] = [
  "model",
  "effortLevel",
  "maxEffortLevel",
  "autoCompactWindow",
];

/** The Settings items that wait for M7. Their inspector says so and offers no Edit. */
const UNTIL_M7: ReadonlySet<string> = new Set([
  "alwaysThinkingEnabled",
  "promptCacheTtl",
  "availableModels",
  "fallbackModel",
]);

/** What a settings file may hold for effortLevel (the server's EFFORT_FILE_LEVELS). */
export const EFFORT_LEVELS = ["low", "medium", "high", "xhigh"] as const;
/** What maxEffortLevel may hold, lowest first (EFFORT_CAP_LEVELS). */
export const EFFORT_CAP_LEVELS = ["low", "medium", "high", "xhigh", "max"] as const;
/** The compact window's range in tokens (WINDOW_MIN and WINDOW_MAX). */
export const WINDOW_MIN = 100_000;
export const WINDOW_MAX = 1_000_000;

type ItemLike = Pick<SetupItem, "part" | "key" | "read_only_reason">;

/** The field an item edits, or null for an item with no editor. */
export function fieldOfItem(item: ItemLike): SettingsEditField | null {
  if (item.part !== "settings" || item.read_only_reason !== null) return null;
  return EDIT_FIELDS.find((field) => field === item.key) ?? null;
}

/** True for a Settings item that waits for M7 and has no other read-only reason. */
export function isUntilM7(item: ItemLike): boolean {
  return item.part === "settings" && item.read_only_reason === null && UNTIL_M7.has(item.key);
}

/** The field's name as the list shows it, such as "Effort cap". One literal t() per branch. */
export function fieldLabel(field: SettingsEditField): string {
  switch (field) {
    case "model":
      return t("sl_model");
    case "effortLevel":
      return t("sl_effortLevel");
    case "maxEffortLevel":
      return t("sl_maxEffortLevel");
    case "autoCompactWindow":
      return t("sl_autoCompactWindow");
  }
}

/** The field's name inside a sentence, such as "effort cap". */
export function fieldWord(field: SettingsEditField): string {
  return fieldLabel(field).toLowerCase();
}

/** A settings field name from a history row, or null for a name the page has no label for. */
export function asField(value: string): SettingsEditField | null {
  return EDIT_FIELDS.find((field) => field === value) ?? null;
}

/** When a save takes effect, already worded. A running session picks up nothing by itself. */
export function appliesWord(applies: EditApplies): string {
  switch (applies) {
    case "new_session":
      return t("ap_new_session");
    case "new_run":
    case "picked_up":
      return t("ap_now");
  }
}

type SourceScope = SetupItem["sources"][number]["scope"];

/** The edit scope of a source's scope, or null for a source Bar Tab can't write (shell, flag). */
export function editScopeOf(scope: SourceScope): EditScope | null {
  switch (scope) {
    case "project_local":
      return "local";
    case "project":
      return "project";
    case "user":
      return "user";
    case "managed":
    case "command_line":
    case "plugin":
    case "shell":
      return null;
  }
}

/** What an edit starts from: a scope and a value, as the request sends them. */
export interface StartChoice {
  scope: EditScope;
  /** The value as the control holds it. A window is the number's digits. */
  text: string;
}

/**
 * The value and file a new edit starts from. The winning source's own file and value come first,
 * because that is what the person sees under "Set to". An item set in a file Bar Tab can't write
 * (managed, flag, shell) starts from the value that runs, in Project local. A model id or an effort
 * the item shows as its effective value has no other source here, so it is the fallback.
 */
export function startChoice(item: SetupItem, field: SettingsEditField): StartChoice {
  const win = item.winner === null ? null : (item.sources[item.winner] ?? null);
  const scope = win === null ? null : editScopeOf(win.scope);
  const fromSource = win?.value != null && !win.value.masked ? win.value.text : null;
  const effective = item.effective?.value;
  const fromEffective = effective != null && !effective.masked ? effective.text : null;
  const text = fromSource ?? fromEffective ?? defaultText(field);
  return { scope: scope ?? "local", text: normalise(field, text) };
}

function defaultText(field: SettingsEditField): string {
  switch (field) {
    case "model":
      return "";
    case "effortLevel":
      return "medium";
    case "maxEffortLevel":
      return "max";
    case "autoCompactWindow":
      return String(WINDOW_MAX);
  }
}

/** A window value read from text such as "1000000" or "1M tokens". Other text keeps its digits. */
function normalise(field: SettingsEditField, text: string): string {
  if (field !== "autoCompactWindow") return text.trim();
  const digits = text.replace(/[^0-9]/g, "");
  return digits === "" ? String(WINDOW_MAX) : digits;
}

/** The window in the request, a whole number of tokens, or null while the text isn't one. */
export function parseWindow(text: string): number | null {
  if (!/^[0-9]+$/.test(text.trim())) return null;
  const value = Number(text.trim());
  return value >= WINDOW_MIN && value <= WINDOW_MAX ? value : null;
}

/** The value a request carries for a control's text, or null while the text isn't one yet. */
export function requestValue(field: SettingsEditField, text: string): string | number | null {
  if (field === "autoCompactWindow") return parseWindow(text);
  const trimmed = text.trim();
  return trimmed === "" ? null : trimmed;
}

/** The edit route of an item, `#/p/<project>/setup/<part>/<key>/edit`, with the Switch kept. */
export function editPathOf(itemPath: string): string {
  const [path = "", query] = itemPath.split("?", 2);
  return `${path}/edit${query === undefined ? "" : `?${query}`}`;
}

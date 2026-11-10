/*
 * The list side of a surface page. A SetupItem becomes one list row (name, the line under it, the
 * status, the lock and not-read marks), and a long list is cut to its first rows per group with
 * Show n more (owner decision 5). Jump to chips appear only for a long list with more than one
 * group, because a short list needs no help to find a group.
 *
 * The server's order is kept as it comes: items by `order`, groups in the order the answer lists
 * them. A refetch never reorders rows.
 */
import type { SetupItem, SetupPart } from "@/api/types";
import type { InspectorItem, ValueText } from "@/components/ListInspector/types";
import { modelLabel } from "@/lib/models";
import { setupItemPath, itemKey } from "@/lib/setup-routes";
import { SETTING_LABELS, hookTitle, scopeName, settingLabel, statusWord } from "@/lib/setup-words";
import { t } from "@/strings/t";

/** A list longer than this is cut to GROUP_SHOWN rows per group. */
export const LONG_LIST = 30;
/** Rows a group of a long list shows before Show n more. */
export const GROUP_SHOWN = 6;
/** The longest value the list shows in its second line. The inspector shows the rest. */
const LIST_VALUE_MAX = 60;

/** The plugin an item comes from, or null. */
export function pluginOf(item: SetupItem): string | null {
  const winner = item.winner === null ? undefined : item.sources[item.winner];
  return (
    item.facts.agent?.plugin ??
    winner?.plugin ??
    item.read_only_reason?.params.plugin ??
    item.sources.find((s) => s.plugin !== null)?.plugin ??
    null
  );
}

/** The name an item has in the list and as the inspector's heading. */
export function itemName(item: SetupItem): string {
  if (item.part === "settings") return settingLabel(item.key);
  const hook = item.part === "hooks" ? item.facts.hook : null;
  if (hook !== null && hook !== undefined) return hookTitle(hook.event, hook.matcher);
  return item.name;
}

/** Per-model settings fields that name a setting the deck has a label for. */
const MODEL_FIELDS: Readonly<Record<string, string>> = { effort: "effortLevel" };

function fieldText(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}

/**
 * Per-model settings as words, "Fable 5.1 (Effort cap medium), Haiku 4.5 (Effort low)". The server
 * sends the object as JSON text. Null when the text isn't an object of objects, so the page can
 * show it as written.
 */
export function modelSettingsText(text: string): string | null {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    return null;
  }
  if (typeof data !== "object" || data === null || Array.isArray(data)) return null;
  const entries = Object.entries(data as Record<string, unknown>);
  if (entries.length === 0) return null;
  const parts: string[] = [];
  for (const [model, fields] of entries) {
    if (typeof fields !== "object" || fields === null || Array.isArray(fields)) return null;
    const lines = Object.entries(fields as Record<string, unknown>).map(([name, value]) =>
      t("sl_ms_field", {
        label: settingLabel(
          Object.hasOwn(MODEL_FIELDS, name) ? (MODEL_FIELDS[name] ?? name) : name,
        ),
        value: fieldText(value),
      }),
    );
    parts.push(
      lines.length === 0
        ? modelLabel(model)
        : t("sl_ms_entry", { model: modelLabel(model), fields: lines.join(", ") }),
    );
  }
  return parts.join(", ");
}

/** A setting's value as words: a model id as its name, per-model settings as a summary. */
export function settingValueText(key: string, text: string): string {
  if (key === "model") return modelLabel(text);
  if (key === "modelSettings") return modelSettingsText(text) ?? text;
  return text;
}

function clip(text: string): string {
  return text.length > LIST_VALUE_MAX ? `${text.slice(0, LIST_VALUE_MAX - 1)}…` : text;
}

/** The scope line an item shows when it has no value of its own. */
export function itemScope(item: SetupItem): string | null {
  if (item.facts.output_style?.builtin === true) return t("st_builtin");
  if (item.location === "parent") return t("ins_parent");
  if (item.scope === null) return null;
  return scopeName(item.scope, pluginOf(item));
}

/** The second line of a list row. */
export function itemValue(item: SetupItem): ValueText | undefined {
  if (item.part === "settings") {
    const value = item.effective?.value;
    if (value === null || value === undefined) return undefined;
    return { text: clip(settingValueText(item.key, value.text)), masked: value.masked };
  }
  const scope = itemScope(item);
  return scope === null ? undefined : { text: scope };
}

/** Parts whose names are code or file names, so the list sets them in the code font. */
const MONO_PARTS: ReadonlySet<SetupPart> = new Set<SetupPart>([
  "instructions",
  "rules",
  "permissions",
]);

export function isMono(item: SetupItem): boolean {
  return MONO_PARTS.has(item.part) || (item.part === "settings" && !item.label_known);
}

/** One list row. `scopes` keeps the Switch state in the link. */
export function listRow(project: string, item: SetupItem, scopes: boolean): InspectorItem {
  const key = itemKey(item.part, item.id) ?? item.key;
  const value = itemValue(item);
  return {
    id: item.id,
    name: itemName(item),
    href: `#${setupItemPath(project, item.part, key, scopes)}`,
    ...(value !== undefined ? { value } : {}),
    // An item the server did not read has status unknown, so its row shows the dashed Unknown
    // pill like any other row (a-m4-p11-plugins).
    status: { status: item.status, label: statusWord(item.status) },
    ...(item.read_only_reason !== null ? { locked: true } : {}),
    ...(item.group !== null ? { group: item.group } : {}),
    ...(isMono(item) ? { className: "setup-mono" } : {}),
  };
}

/** A group of the list the page draws. `bare` leaves its heading out. */
export interface ShapedGroup {
  key: string;
  count: number;
  bare: boolean;
}

/** The group a setting sits in on the page, as the board has it. */
export function settingGroup(item: SetupItem): "model" | "other" {
  return Object.hasOwn(SETTING_LABELS, item.key) ? "model" : "other";
}

/**
 * The groups the page draws for a part, from the server's answer. Settings split into Model and
 * effort (the settings Bar Tab has a label for) and Other settings. Hooks are one flat list,
 * because the board has no event headings and the title already says the event. Agents keep their
 * Ran and No runs headings only when both show, since one heading over the whole list adds
 * nothing. The server's groups stand for every other part.
 */
export function shapeGroups(
  part: SetupPart,
  items: readonly SetupItem[],
  groups: readonly { key: string; count: number }[],
): { items: SetupItem[]; groups: ShapedGroup[] } {
  switch (part) {
    case "settings": {
      const shaped = items.map((item) => ({ ...item, group: settingGroup(item) }));
      return {
        items: shaped,
        groups: (["model", "other"] as const)
          .map((key) => ({
            key,
            count: shaped.filter((item) => item.group === key).length,
            bare: false,
          }))
          .filter((g) => g.count > 0),
      };
    }
    case "hooks":
      return { items: [...items], groups: [] };
    default: {
      const bare = part === "agents" && groups.length === 1;
      return {
        items: [...items],
        groups: groups.map((g) => ({ key: g.key, count: g.count, bare })),
      };
    }
  }
}

export interface ListPlan {
  /** The items to draw, in the answer's order. */
  shown: SetupItem[];
  /** How many items each group leaves out, by group key. Only groups with some left out. */
  hidden: ReadonlyMap<string, number>;
  /** The first item each group leaves out, so focus can land on it after Show n more. */
  firstHidden: ReadonlyMap<string, string>;
  /** The list is long enough to cut. */
  long: boolean;
}

/**
 * Cuts a long, grouped list to its first rows per group. The picked item always shows, and a group
 * in `expanded` shows every row. A list with no groups, or a short one, is never cut.
 */
export function planList(
  items: readonly SetupItem[],
  groupKeys: readonly string[],
  expanded: ReadonlySet<string>,
  selectedId: string | undefined,
): ListPlan {
  const long = items.length > LONG_LIST;
  const grouped = groupKeys.length > 0;
  if (!long || !grouped) {
    return { shown: [...items], hidden: new Map(), firstHidden: new Map(), long };
  }
  const seen = new Map<string, number>();
  const hidden = new Map<string, number>();
  const firstHidden = new Map<string, string>();
  const shown: SetupItem[] = [];
  for (const item of items) {
    const key = item.group ?? "";
    const n = seen.get(key) ?? 0;
    seen.set(key, n + 1);
    if (n < GROUP_SHOWN || expanded.has(key) || item.id === selectedId || key === "") {
      shown.push(item);
    } else {
      hidden.set(key, (hidden.get(key) ?? 0) + 1);
      if (!firstHidden.has(key)) firstHidden.set(key, item.id);
    }
  }
  return { shown, hidden, firstHidden, long };
}

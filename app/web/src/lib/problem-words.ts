/*
 * The words of one To fix row, from a problem row of /api/problems. The server sends a code, the
 * display name of the thing, a file and line, and a few params. The page owns every word. Keys that
 * end in a server code (pc_<code>_t, _c and _q, cr_r_<reason>, fx_cant_<reason>) are looked up by
 * that code, so the lookup goes through one loose caller, and a code with no string reads as the
 * raw code rather than failing the page. The closed-enum test in strings/setup-codes.test.ts fails
 * when a code has no string.
 */
import type { ProblemRow } from "@/api/types";
import { modelLabel } from "@/lib/models";
import { setupItemPathFromId } from "@/lib/setup-routes";
import { en } from "@/strings/en";
import { t } from "@/strings/t";

type Params = Record<string, string | number>;

/** `t` with a key known only at run time. The key is checked against the deck first. */
const lookup = t as unknown as (key: string, params?: Params) => string;
const plurals = new Intl.PluralRules("en");

function has(key: string): boolean {
  return Object.hasOwn(en, key);
}

/** A string by key, with unfilled placeholders dropped. Null when the deck has no such key. */
export function word(key: string, params: Params = {}): string | null {
  if (!has(key)) return null;
  return lookup(key, params)
    .replace(/\{\w+\}/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** A plural string by base key, with the count in {n}. Null when the deck has no such pair. */
export function countWord(base: string, n: number, params: Params = {}): string | null {
  const form = plurals.select(n) === "one" ? "one" : "other";
  return word(`${base}_${form}`, { ...params, n });
}

/** "file line 8", "file", or "" for a row with no file. */
function whereOf(row: ProblemRow): string {
  if (row.file === null) return "";
  return row.line === null
    ? t("loc_file", { file: row.file })
    : t("loc_line", { file: row.file, line: row.line });
}

/** The values every string can use. Params from the server win over the row's own fields. */
function paramsOf(row: ProblemRow): Params {
  const out: Params = {
    thing: row.thing,
    file: row.file ?? "",
    where: whereOf(row),
    ...row.params,
  };
  // The server joins variable names with a comma.
  if (typeof out.vars === "string") out.vars = out.vars.replaceAll(",", ", ");
  return out;
}

export interface ProblemWords {
  title: string;
  cause: string;
  consequence: string;
}

/** The title, cause and consequence of a row, by its code. */
export function problemWords(row: ProblemRow): ProblemWords {
  const p = paramsOf(row);
  const code = row.code;
  // An agent a cap lowers: the values read as names (a model by its name), and the cap by its label.
  if (code === "agent_lowered") {
    const shown = (value: string | number | undefined): string =>
      row.params.setting === "model" ? modelLabel(String(value ?? "")) : String(value ?? "");
    const cap = row.params.cap ?? "";
    p.value = shown(p.value);
    p.runs = shown(p.runs);
    p.cap = word(`sl_${cap}`) ?? cap;
  }
  const pick = (...keys: string[]): string => {
    for (const key of keys) {
      const found = word(key, p);
      if (found !== null) return found;
    }
    return code;
  };

  // A counted sentence with no title of its own.
  if (code === "rows_no_usage") {
    const n = Number(row.params.count ?? "0");
    const sentence = countWord("pc_rows_no_usage", n, p) ?? code;
    return { title: sentence, cause: sentence, consequence: "" };
  }

  // A file Bar Tab could not read. The cause comes from the reason, the consequence is shared.
  if (row.group === "couldnt_read" && code !== "transcript_unreadable") {
    return {
      title: pick(`pc_${code}_t`),
      cause: pick(`cr_r_${code}`),
      consequence: pick(
        code === "folder_unlistable"
          ? "pc_folder_unlistable_q"
          : code === "vanished"
            ? "pc_vanished_q"
            : "pc_read_q",
      ),
    };
  }

  const why = row.params.why ?? "";
  switch (code) {
    case "hook_bad_handler":
      return {
        title: pick(
          row.params.event !== undefined
            ? "pc_hook_bad_handler_t"
            : "pc_hook_bad_handler_t_noevent",
        ),
        cause: pick(`pc_hook_why_${why}`),
        consequence: pick("pc_hook_bad_handler_q"),
      };
    case "mcp_bad_entry":
      return {
        title: pick("pc_mcp_bad_entry_t"),
        cause: pick(`pc_mcp_why_${why}`),
        consequence: pick("pc_mcp_bad_entry_q"),
      };
    case "hooks_disabled": {
      const managed = row.params.flag === "allowManagedHooksOnly";
      const n = Number(row.params.count ?? "0");
      return {
        title: pick("pc_hooks_disabled_t"),
        cause: pick("pc_hooks_disabled_c"),
        consequence:
          countWord(managed ? "pc_hooks_disabled_q_managed" : "pc_hooks_disabled_q_all", n, p) ??
          code,
      };
    }
    case "not_object":
      return {
        title: pick("pc_not_object_t"),
        cause: pick(row.params.key !== undefined ? "pc_not_object_c_key" : "pc_not_object_c"),
        consequence: pick("pc_not_object_q"),
      };
    case "same_name_in_folder":
      return {
        title: pick("pc_same_name_in_folder_t"),
        cause: pick(
          row.params.other_file !== undefined
            ? "pc_same_name_in_folder_c"
            : "pc_same_name_in_folder_c_nofile",
        ),
        consequence: pick("pc_same_name_in_folder_q"),
      };
    case "unknown":
      return {
        title: pick("pc_unknown_t"),
        cause: pick(row.file !== null ? "pc_unknown_c" : "pc_unknown_c_nofile"),
        consequence: pick("pc_unknown_q"),
      };
    case "ignored": {
      const paths = row.params.key === "paths";
      return {
        title: pick("pc_ignored_t"),
        cause: pick(paths ? "pc_ignored_c_paths" : "pc_ignored_c"),
        consequence: pick(paths ? "pc_ignored_q_paths" : "pc_ignored_q"),
      };
    }
    default:
      return {
        title: pick(`pc_${code}_t`),
        cause: pick(`pc_${code}_c`),
        consequence: pick(`pc_${code}_q`),
      };
  }
}

/** What a row's one action is, before the page words it. */
export type FixPlan =
  | { kind: "open_item"; label: string; href: string }
  | { kind: "copy_path"; path: string; label: string; ariaLabel: string }
  | { kind: "copy_command"; command: string; ariaLabel: string; note: string }
  | { kind: "cant_fix_here"; reason: string };

/**
 * The label of an item in "Open {item}". A known settings key reads by its name, else the thing.
 * A row whose fix opens a settings item (the cap that lowers an agent) names that setting.
 */
function itemLabel(row: ProblemRow): string {
  const target = row.fix.target;
  if (row.part === "agents" && target?.startsWith("settings:") === true) {
    const key = target.slice("settings:".length);
    return word(`sl_${key}`) ?? key;
  }
  if (row.part === "settings") return word(`sl_${row.thing}`) ?? row.thing;
  return row.thing;
}

/**
 * The one action of a row. An open_item fix with no usable item id has nothing to open, so it says
 * the row has nothing to fix here instead of a dead link.
 */
export function fixPlan(row: ProblemRow, project: string): FixPlan {
  const fix = row.fix;
  const target = fix.target;
  const cant = (reason: string): FixPlan => ({
    kind: "cant_fix_here",
    reason: word(`fx_cant_${reason}`) ?? t("fx_cant_not_fixable"),
  });
  switch (fix.kind) {
    case "open_item": {
      const path = target === null ? null : setupItemPathFromId(project, target);
      if (path === null) return cant("not_fixable");
      return { kind: "open_item", label: t("fx_open", { item: itemLabel(row) }), href: `#${path}` };
    }
    case "copy_path":
      if (target === null) return cant("not_visible");
      return {
        kind: "copy_path",
        path: target,
        label: t("in_copy"),
        ariaLabel: t("fx_copy_path_aria", { file: row.file ?? row.thing }),
      };
    case "copy_command":
      if (target === null) return cant("not_fixable");
      return {
        kind: "copy_command",
        command: target,
        ariaLabel: t("fx_copy_cmd_aria", { thing: row.thing }),
        note: t("fx_cmd_note"),
      };
    case "cant_fix_here":
      return cant(fix.reason ?? "not_fixable");
  }
}

/*
 * The words of the setup pages that come from a server code or an id: part names, scope names, the
 * status words, setting labels, group labels and the lookups for keys that end in a code. The page
 * owns every word, so the server sends codes and ids only.
 *
 * Keys that end in a server code (sl_<key>, hk_ev_<event>, rs_<code>, cr_r_<reason>, lo_<kind>,
 * ins_imp_<state>, mc_t_<transport>, hk_ty_<type>) go through one loose lookup, `word`, which
 * returns null for a key the deck does not have. A code with no string reads as the raw code rather
 * than failing the page. The closed-enum test in strings/setup-codes.test.ts fails when a code has
 * no string. Every other word is a literal t() call.
 */
import type { SetupItem, SetupPart } from "@/api/types";
import { STATUS_WORDS } from "@/lib/model-check";
import { en } from "@/strings/en";
import { t } from "@/strings/t";

export type Scope = SetupItem["sources"][number]["scope"];
export type Status = SetupItem["status"];

type Params = Record<string, string | number>;

/** `t` with a key known only at run time. The key is checked against the deck first. */
const lookup = t as unknown as (key: string, params?: Params) => string;

/** A string by key, with unfilled placeholders dropped. Null when the deck has no such key. */
export function word(key: string, params: Params = {}): string | null {
  if (!Object.hasOwn(en, key)) return null;
  return lookup(key, params)
    .replace(/\{\w+\}/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** The word of a code, or the code itself when the deck has none. */
export function codeWord(prefix: string, code: string, params: Params = {}): string {
  return word(`${prefix}${code}`, params) ?? code;
}

export const PART_NAMES: Readonly<Record<SetupPart, () => string>> = {
  settings: () => t("sf_settings"),
  agents: () => t("sf_agents"),
  instructions: () => t("sf_instructions"),
  rules: () => t("sf_rules"),
  skills: () => t("sf_skills"),
  hooks: () => t("sf_hooks"),
  permissions: () => t("sf_permissions"),
  mcp: () => t("sf_mcp"),
  plugins: () => t("sf_plugins"),
  output_style: () => t("sf_output_style"),
};

export const PART_SUBS: Readonly<Record<SetupPart, (project: string) => string>> = {
  settings: (project) => t("sp_sub_settings", { project }),
  agents: (project) => t("sp_sub_agents", { project }),
  instructions: () => t("sp_sub_instructions"),
  rules: () => t("sp_sub_rules"),
  skills: (project) => t("sp_sub_skills", { project }),
  hooks: () => t("sp_sub_hooks"),
  permissions: () => t("sp_sub_permissions"),
  mcp: () => t("sp_sub_mcp"),
  plugins: (project) => t("sp_sub_plugins", { project }),
  output_style: () => t("sp_sub_output_style"),
};

/** The line an empty part says on the map. */
export const PART_NONE: Readonly<Record<SetupPart, () => string>> = {
  settings: () => t("su_none_settings"),
  agents: () => t("su_none_agents"),
  instructions: () => t("su_none_instructions"),
  rules: () => t("su_none_rules"),
  skills: () => t("su_none_skills"),
  hooks: () => t("su_none_hooks"),
  permissions: () => t("su_none_permissions"),
  mcp: () => t("su_none_mcp"),
  plugins: () => t("su_none_plugins"),
  output_style: () => t("su_r_output_style_default"),
};

/** The empty-list sentence of a surface page. */
export const PART_EMPTY: Readonly<Record<SetupPart, () => string>> = {
  settings: () => t("em_settings"),
  agents: () => t("em_agents"),
  instructions: () => t("em_instructions"),
  rules: () => t("em_rules"),
  skills: () => t("em_skills"),
  hooks: () => t("em_hooks"),
  permissions: () => t("em_permissions"),
  mcp: () => t("em_mcp"),
  plugins: () => t("em_plugins"),
  // An empty output style list means the default applies.
  output_style: () => t("st_set"),
};

export function statusWord(status: Status): string {
  return STATUS_WORDS[status];
}

export const SCOPE_NAMES: Readonly<Record<Scope, () => string>> = {
  managed: () => t("sc_managed"),
  command_line: () => t("sc_command_line"),
  project_local: () => t("sc_project_local"),
  project: () => t("sc_project"),
  user: () => t("sc_user"),
  plugin: () => t("sc_plugin"),
  shell: () => t("sc_shell"),
};

export const SCOPE_MEANINGS: Readonly<Record<Exclude<Scope, "shell">, () => string>> = {
  managed: () => t("sc_managed_2"),
  command_line: () => t("sc_command_line_2"),
  project_local: () => t("sc_project_local_2"),
  project: () => t("sc_project_2"),
  user: () => t("sc_user_2"),
  plugin: () => t("sc_plugin_2"),
};

/** The scope name, with the plugin's name when the scope is a plugin and the name is known. */
export function scopeName(scope: Scope, plugin: string | null = null): string {
  if (scope === "plugin" && plugin !== null) return t("sc_plugin_named", { plugin });
  return SCOPE_NAMES[scope]();
}

/**
 * The scope's plain meaning. The shell's carries the time Bar Tab started, as a clock string, and
 * reads empty until that time is known.
 */
export function scopeMeaning(scope: Scope, startedAt: string | null): string {
  if (scope !== "shell") return SCOPE_MEANINGS[scope]();
  return startedAt === null ? "" : t("sc_shell_2", { time: startedAt });
}

/** The label of a settings key Bar Tab knows. */
export const SETTING_LABELS: Readonly<Record<string, () => string>> = {
  model: () => t("sl_model"),
  effortLevel: () => t("sl_effortLevel"),
  maxEffortLevel: () => t("sl_maxEffortLevel"),
  autoCompactWindow: () => t("sl_autoCompactWindow"),
  promptCacheTtl: () => t("sl_promptCacheTtl"),
  alwaysThinkingEnabled: () => t("sl_alwaysThinkingEnabled"),
  fallbackModel: () => t("sl_fallbackModel"),
  availableModels: () => t("sl_availableModels"),
  modelSettings: () => t("sl_modelSettings"),
  modelPricing: () => t("sl_modelPricing"),
};

/** The label of a setting key, or the key as written when Bar Tab has no name for it. */
export function settingLabel(key: string): string {
  const known = Object.hasOwn(SETTING_LABELS, key) ? SETTING_LABELS[key] : undefined;
  return known === undefined ? key : known();
}

/** The label of an item id, for lines that name another item ("settings:maxEffortLevel"). */
export function itemLabel(id: string): string {
  const colon = id.indexOf(":");
  const part = colon < 0 ? "" : id.slice(0, colon);
  const rest = colon < 0 ? id : id.slice(colon + 1);
  return part === "settings" ? settingLabel(rest) : rest;
}

/** The heading of a group of a part's list. */
export function groupLabel(part: SetupPart, key: string): string {
  switch (part) {
    case "permissions":
      switch (key) {
        case "deny":
          return t("sp_g_deny");
        case "ask":
          return t("sp_g_ask");
        case "allow":
          return t("sp_g_allow");
        case "default_mode":
          return t("sp_g_default_mode");
        case "directory":
          return t("sp_g_directory");
        default:
          return key;
      }
    case "agents":
      if (key === "ran") return t("ag_g_ran");
      if (key === "no_runs") return t("ag_g_no_runs");
      return key;
    case "hooks":
      return codeWord("hk_ev_", key);
    case "settings":
      if (key === "model") return t("sp_g_model");
      if (key === "other") return t("sp_g_other");
      return key;
    default:
      return key;
  }
}

/** Hook events whose matcher names tools, so a title can say "Before Edit". */
const TOOL_EVENTS: ReadonlySet<string> = new Set([
  "PreToolUse",
  "PostToolUse",
  "PostToolUseFailure",
]);

/** A matcher that is only tool names ("Edit", "Edit|Write"), as a list of names. Null for the rest. */
function toolNames(matcher: string | null): string[] | null {
  if (matcher === null || !/^\w+(\|\w+)*$/.test(matcher)) return null;
  return matcher.split("|");
}

/** "Edit", "Edit or Write", "Edit, Write or Read". */
function orList(names: readonly string[]): string {
  const last = names[names.length - 1] ?? "";
  if (names.length < 2) return last;
  return t("hk_or", { list: names.slice(0, -1).join(", "), last });
}

/**
 * A hook as a person says it: "Before Edit", "After Bash succeeds". A tool event with a matcher of
 * tool names says the tools. Every other hook says its event in words, and the matcher stays in the
 * inspector's Matches line, so a regex never breaks across the list.
 */
export function hookTitle(event: string, matcher: string | null): string {
  const tools = TOOL_EVENTS.has(event) ? toolNames(matcher) : null;
  const named = tools === null ? null : word(`hk_nm_${event}`, { tool: orList(tools) });
  return named ?? codeWord("hk_ev_", event);
}

/** The inspector's headline for a hook: "Runs a command after each Bash call that succeeds". */
export function hookRuns(event: string, matcher: string | null, handlerType: string): string {
  const tools = TOOL_EVENTS.has(event) ? toolNames(matcher) : null;
  const when =
    (tools === null ? null : word(`hk_wh_${event}`, { tool: orList(tools) })) ??
    lowerFirst(codeWord("hk_ev_", event));
  return t("hk_runs", { does: codeWord("hk_ty_", handlerType), when });
}

function lowerFirst(text: string): string {
  return text.slice(0, 1).toLowerCase() + text.slice(1);
}

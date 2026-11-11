/*
 * Shared lists, held once. The status words, the scopes, the confidence words and the project
 * states are each defined here as keys into en.ts, so the chips, the help popovers, the Glossary
 * and How Claude Code decides all read one string per word and one per meaning (m5-build.md
 * section 4). Never type one of these words or meanings anywhere else.
 */
import type { StringKey } from "@/strings/en";

export interface ListItem {
  /** Stable id, the same as the server's code where one exists. */
  readonly id: string;
  /** The word on screen. */
  readonly word: StringKey;
  /** What it means, in one sentence. */
  readonly means: StringKey;
}

/** The seven status words, in the order the help and the Glossary list them. */
export const STATUS_WORDS = [
  { id: "in_effect", word: "status_in_effect", means: "rs_in_effect" },
  { id: "overridden", word: "status_overridden", means: "rs_overridden" },
  { id: "ignored", word: "status_ignored", means: "rs_ignored" },
  { id: "lowered", word: "status_lowered", means: "rs_lowered" },
  { id: "invalid", word: "status_invalid", means: "rs_invalid" },
  { id: "default", word: "status_default", means: "rs_default" },
  { id: "unknown", word: "status_unknown", means: "rs_unknown" },
] as const satisfies readonly ListItem[];

/** The scopes, highest first, then Plugin and Your shell, which are not levels. */
export const SCOPES = [
  { id: "managed", word: "sc_managed", means: "sc_managed_2" },
  { id: "command_line", word: "sc_command_line", means: "sc_command_line_2" },
  { id: "project_local", word: "sc_project_local", means: "sc_project_local_2" },
  { id: "project", word: "sc_project", means: "sc_project_2" },
  { id: "user", word: "sc_user", means: "sc_user_2" },
  { id: "plugin", word: "sc_plugin", means: "sc_plugin_2" },
  { id: "shell", word: "sc_shell", means: "sc_shell_def" },
] as const satisfies readonly ListItem[];

/** The three confidence words a rule carries. */
export const CONFIDENCE_WORDS = [
  { id: "tested", word: "in_tested", means: "cf_tested" },
  { id: "documented", word: "in_documented", means: "cf_documented" },
  { id: "assumed", word: "in_assumed", means: "cf_assumed" },
] as const satisfies readonly ListItem[];

/** The states a listed project can be in, as the project picker shows them. */
export const PROJECT_STATES = [
  { id: "ok", word: "pk_state_ok", means: "pk_state_ok_d" },
  { id: "no_claude_folder", word: "pk_state_no_claude_folder", means: "pk_st_noclaude_d" },
  { id: "folder_not_found", word: "pk_state_folder_not_found", means: "pk_st_notfound_d" },
] as const satisfies readonly ListItem[];

/**
 * The order of the groups on How Claude Code decides, as rules.json keys. Each group's name is
 * en.ts rg_<key> with a dot turned into an underscore. A key missing here sorts last.
 */
export const RULE_GROUP_ORDER = [
  "effortLevel",
  "model",
  "effort",
  "modelSettings",
  "maxEffortLevel",
  "modelSettings.maxEffortLevel",
  "autoCompactWindow",
  "modelSettings.autoCompactWindow",
  "promptCacheTtl",
  "subagentPromptCacheTtl",
  "alwaysThinkingEnabled",
  "fallbackModel",
  "availableModels",
  "agentFile",
  "settingsFile",
  "env",
  "rulesFile",
] as const;

export type ListId = "status" | "scopes" | "confidence" | "project_state";

export const LISTS: Readonly<Record<ListId, readonly ListItem[]>> = {
  status: STATUS_WORDS,
  scopes: SCOPES,
  confidence: CONFIDENCE_WORDS,
  project_state: PROJECT_STATES,
};

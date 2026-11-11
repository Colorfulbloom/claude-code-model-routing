/*
 * The pure parts of How Claude Code decides: which words a rule and a setting carry, how the rules
 * group, which layers the order ladder shows, how a search matches, and how the version gap reads.
 * The page only draws what this returns.
 */
import type { RuleConfidence, RuleRow, RulesAnswer } from "@/api/types";
import { matchFields } from "@/components/SearchField/match";
import { word } from "@/lib/setup-words";
import { en } from "@/strings/en";
import { CONFIDENCE_WORDS, RULE_GROUP_ORDER, STATUS_WORDS } from "@/strings/lists";
import { t } from "@/strings/t";

export type RuleStatus = RuleRow["outcomes"][number];
export type ConfidenceFilter = "all" | RuleConfidence;

/** The statuses a rule group can sit under, as Your setup orders them, with Invalid first. */
export const STATUS_ORDER: readonly RuleStatus[] = [
  "invalid",
  "lowered",
  "ignored",
  "overridden",
  "unknown",
  "in_effect",
  "default",
];

/** The one sentence a rule says on screen, typed in en.ts as rl_<rule_id>. The id itself when missing. */
export function ruleSentence(rule: RuleRow): string {
  return word(`rl_${rule.rule_id}`) ?? rule.rule_id;
}

/** The group name of a setting key, typed in en.ts as rg_<key with dots as underscores>. */
export function settingName(key: string): string {
  return word(`rg_${key.split(".").join("_")}`) ?? key;
}

export function confidenceWord(confidence: RuleConfidence): string {
  const item = CONFIDENCE_WORDS.find((entry) => entry.id === confidence);
  return item === undefined ? confidence : en[item.word];
}

export function confidenceMeaning(confidence: RuleConfidence): string {
  const item = CONFIDENCE_WORDS.find((entry) => entry.id === confidence);
  return item === undefined ? "" : en[item.means];
}

export function statusWord(status: RuleStatus): string {
  const item = STATUS_WORDS.find((entry) => entry.id === status);
  return item === undefined ? status : en[item.word];
}

/** The question a status group answers, such as "When a cap lowers it". */
export function statusQuestion(status: RuleStatus): string {
  switch (status) {
    case "invalid":
      return t("dc_q_invalid");
    case "lowered":
      return t("dc_q_lowered");
    case "ignored":
      return t("dc_q_ignored");
    case "overridden":
      return t("dc_q_overridden");
    case "unknown":
      return t("dc_q_unknown");
    case "in_effect":
      return t("dc_q_in_effect");
    case "default":
      return t("dc_q_default");
  }
}

/** The setting keys the rules cover, in RULE_GROUP_ORDER, with any other key after them. */
export function settingKeys(rules: readonly RuleRow[]): string[] {
  const order: readonly string[] = RULE_GROUP_ORDER;
  const seen = [...new Set(rules.map((rule) => rule.key))];
  const rank = (key: string): number => {
    const at = order.indexOf(key);
    return at === -1 ? order.length : at;
  };
  return seen.sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

/** Every status a rule can lead to, in the order the rule lists them. In effect when it lists none. */
export function outcomesOf(rule: RuleRow): readonly RuleStatus[] {
  return rule.outcomes.length > 0 ? rule.outcomes : ["in_effect"];
}

/**
 * The rules grouped under each status they lead to, in STATUS_ORDER. A rule that can lead to more
 * than one status shows in each group, so a group counts its own rows. A status with no rule is
 * left out.
 */
export function groupByOutcome(rules: readonly RuleRow[]): [RuleStatus, RuleRow[]][] {
  return STATUS_ORDER.map(
    (status) =>
      [status, rules.filter((rule) => outcomesOf(rule).includes(status))] as [
        RuleStatus,
        RuleRow[],
      ],
  ).filter(([, inGroup]) => inGroup.length > 0);
}

export interface RuleRowSlot {
  rule: RuleRow;
  /** The first place the rule shows on the page. Only this row carries the rule's id and the route's mark. */
  first: boolean;
}

/**
 * The groups with each row marked first or repeat, in the order the page draws them. `repeats` is
 * how many rows repeat a rule shown above, so it is more than 0 only when some rule shows twice.
 */
export function slotGroups(rules: readonly RuleRow[]): {
  groups: [RuleStatus, RuleRowSlot[]][];
  repeats: number;
} {
  const seen = new Set<string>();
  let repeats = 0;
  const groups = groupByOutcome(rules).map(([status, inGroup]): [RuleStatus, RuleRowSlot[]] => [
    status,
    inGroup.map((rule) => {
      const first = !seen.has(rule.rule_id);
      seen.add(rule.rule_id);
      if (!first) repeats += 1;
      return { rule, first };
    }),
  ]);
  return { groups, repeats };
}

/** The scope words a setting page joins, in the order main, agent, model. */
export function scopeWords(rules: readonly RuleRow[]): string[] {
  const scopes = new Set(rules.map((rule) => rule.scope));
  const words: string[] = [];
  if (scopes.has("main")) words.push(t("dc_scope_main"));
  if (scopes.has("agent")) words.push(t("dc_scope_agent"));
  if (scopes.has("model")) words.push(t("dc_scope_model"));
  return words;
}

/** "a", "a and b", "a, b and c". */
export function joinAnd(words: readonly string[]): string {
  const last = words.at(-1);
  if (last === undefined) return "";
  if (words.length === 1) return last;
  return t("list_and", { list: words.slice(0, -1).join(", "), last });
}

/** The name of one ladder layer. The default layer reads differently for an agent's model. */
export function layerName(layer: string, rule: RuleRow): string {
  switch (layer) {
    case "managed":
      return t("sc_managed");
    case "local":
      return t("sc_project_local");
    case "project":
      return t("sc_project");
    case "user":
      return t("sc_user");
    case "plugin":
      return t("sc_plugin");
    case "env":
      return t("ly_env");
    case "flag":
      return t("ly_flag");
    case "cli":
      return t("ly_cli");
    case "agent":
      return t("ly_agent");
    case "default":
      return rule.scope === "agent" && rule.key === "model"
        ? t("ly_default_agent")
        : t("ly_default");
    default:
      return layer;
  }
}

/**
 * The rule whose order a setting page draws. A rule named for its order comes first, then the rule
 * with the longest order, so a setting reads the full chain Claude Code checks.
 */
export function orderRule(rules: readonly RuleRow[]): RuleRow | null {
  const named = rules.find((rule) => rule.rule_id.endsWith("-order"));
  if (named !== undefined) return named;
  let best: RuleRow | null = null;
  for (const rule of rules) {
    if (best === null || rule.layer_order.length > best.layer_order.length) best = rule;
  }
  return best;
}

export function ladderLayers(rules: readonly RuleRow[]): { id: string; label: string }[] {
  const rule = orderRule(rules);
  if (rule === null) return [];
  return rule.layer_order.map((layer) => ({ id: layer, label: layerName(layer, rule) }));
}

/** The fields a search looks in, by name. The `quotes` field is the docs line. */
export function ruleFields(rule: RuleRow): Record<string, string> {
  return {
    id: rule.rule_id,
    key: rule.key,
    group: settingName(rule.key),
    sentence: ruleSentence(rule),
    confidence: confidenceWord(rule.confidence),
    version: rule.verified_on.claude_version,
    quotes: rule.quotes.map((quote) => quote.quote).join(" "),
  };
}

export interface Filters {
  q: string;
  confidence: ConfidenceFilter;
  due: boolean;
}

export interface Matched {
  rule: RuleRow;
  /** True when the query was found only in the rule's docs line. */
  docsOnly: boolean;
}

/** The fields a query matched in, or null for no match. An empty query matches with no fields. */
export function matchRule(rule: RuleRow, q: string): ReadonlySet<string> | null {
  return matchFields(q, ruleFields(rule));
}

/** Every rule that passes the query, the Confidence filter and the due view, in file order. */
export function filterRules(rules: readonly RuleRow[], filters: Filters): Matched[] {
  const out: Matched[] = [];
  for (const rule of rules) {
    if (filters.confidence !== "all" && rule.confidence !== filters.confidence) continue;
    if (filters.due && !rule.due) continue;
    const found = matchRule(rule, filters.q);
    if (found === null) continue;
    out.push({ rule, docsOnly: found.size === 1 && found.has("quotes") });
  }
  return out;
}

/** How many rules carry each Confidence word, and how many in all. */
export function confidenceCounts(rules: readonly RuleRow[]): Record<ConfidenceFilter, number> {
  const counts: Record<ConfidenceFilter, number> = {
    all: rules.length,
    tested: 0,
    documented: 0,
    assumed: 0,
  };
  for (const rule of rules) counts[rule.confidence] += 1;
  return counts;
}

export interface RuleTarget {
  id: string;
  /** The setting key the rule sits under, for its route. */
  key: string;
  /** The rule was checked on a version older than the one the owner runs. */
  due: boolean;
  installed: string | null;
}

/**
 * What an inspector's Why line needs of a rule: its setting key for the link, and whether it is
 * due. Null for no rule id, or while the rules are not loaded, or for an id the rules lack.
 */
export function ruleTarget(
  ruleId: string | null | undefined,
  answer: Pick<RulesAnswer, "rules" | "installed"> | undefined,
): RuleTarget | null {
  if (ruleId === null || ruleId === undefined || answer === undefined) return null;
  const found = answer.rules.find((rule) => rule.rule_id === ruleId);
  if (found === undefined) return null;
  return { id: found.rule_id, key: found.key, due: found.due, installed: answer.installed };
}

export interface Gap {
  /** The rules checked on a version older than the one the owner runs. */
  due: number;
  total: number;
  installed: string;
  checkedOn: string;
  /**
   * Every rule is due and every due rule was checked on `checked_on`, so the notice can say "all
   * rules were checked on {version}". Otherwise it says how many were checked on an older version.
   */
  all: boolean;
  /** The per-row due mark shows only when some rules are due, never when all are. */
  marks: boolean;
}

/** The version gap, or null when nothing is due or the installed version is not known. */
export function gapOf(answer: Pick<RulesAnswer, "rules" | "installed" | "checked_on">): Gap | null {
  if (answer.installed === null) return null;
  const due = answer.rules.filter((rule) => rule.due);
  if (due.length === 0) return null;
  const everyOne = due.length === answer.rules.length;
  return {
    due: due.length,
    total: answer.rules.length,
    installed: answer.installed,
    checkedOn: answer.checked_on,
    all: everyOne && due.every((rule) => rule.verified_on.claude_version === answer.checked_on),
    marks: !everyOne,
  };
}

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
] as const;

/** An ISO date as month and day, "October 29". The text as it came when it is not a date. */
export function monthDay(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (match === null) return iso;
  const month = MONTHS[Number(match[2]) - 1];
  return month === undefined ? iso : `${month} ${String(Number(match[3]))}`;
}

/*
 * Keeps the rule words in step with the rules file (m5-build.md section 4). The server's
 * rules.json (app/server/data/rules.json) is read from disk as text. Every rule_id needs an
 * en.ts sentence rl_<rule_id>, and every setting key needs a group name rg_<key> with dots turned
 * into underscores. The deck may hold no rl_ or rg_ key the file no longer has. Every group in
 * lists.ts RULE_GROUP_ORDER must be a key in the file.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { en } from "@/strings/en";
import { RULE_GROUP_ORDER } from "@/strings/lists";

const RULES = resolve(import.meta.dirname, "..", "..", "..", "server", "data", "rules.json");

interface RuleFields {
  readonly rule_id: string;
  readonly key: string;
}

type Deck = Readonly<Record<string, string>>;

/**
 * The Review range selector already owns some rg_ keys (rg_h, rg_today, rg_7d, rg_30d, rg_90d,
 * rg_12m, rg_all, and the rg_w_, rg_p_ and rg_n_ phrases). They are not rule groups, so the stale
 * check skips them. A setting key never takes one of these names.
 */
const RANGE_KEY = /^rg_(?:h|today|\d+[dm]|all|[wpn]_\w+)$/;

/** The deck key for a rule's sentence. */
export function ruleKey(ruleId: string): string {
  return `rl_${ruleId}`;
}

/** The deck key for a setting key's group name. */
export function groupKey(key: string): string {
  return `rg_${key.split(".").join("_")}`;
}

/** Every way the deck and the order list disagree with the rules file. */
export function ruleWordProblems(
  rules: readonly RuleFields[],
  order: readonly string[],
  deck: Deck,
): string[] {
  const problems: string[] = [];
  const sentences = new Set(rules.map((rule) => ruleKey(rule.rule_id)));
  const groups = new Set(rules.map((rule) => groupKey(rule.key)));
  for (const rule of rules) {
    if (!Object.hasOwn(deck, ruleKey(rule.rule_id))) {
      problems.push(`rule ${rule.rule_id} has no ${ruleKey(rule.rule_id)}`);
    }
  }
  for (const key of new Set(rules.map((rule) => rule.key))) {
    if (!Object.hasOwn(deck, groupKey(key))) problems.push(`key ${key} has no ${groupKey(key)}`);
  }
  for (const key of Object.keys(deck)) {
    if (key.startsWith("rl_") && !sentences.has(key)) {
      problems.push(`${key} names a rule the file no longer has`);
    }
    if (key.startsWith("rg_") && !RANGE_KEY.test(key) && !groups.has(key)) {
      problems.push(`${key} names a key the file no longer has`);
    }
  }
  const known = new Set(rules.map((rule) => rule.key));
  for (const key of order) {
    if (!known.has(key)) problems.push(`RULE_GROUP_ORDER has ${key}, which rules.json lacks`);
  }
  return problems;
}

function loadRules(): RuleFields[] {
  const parsed: unknown = JSON.parse(readFileSync(RULES, "utf8"));
  const list = (parsed as { rules?: unknown }).rules;
  if (!Array.isArray(list)) throw new Error("rules.json has no rules list");
  return list as RuleFields[];
}

const rules = loadRules();

describe("rule words", () => {
  it("reads the rules file", () => {
    expect(rules.length).toBeGreaterThan(10);
    expect(rules.every((rule) => rule.rule_id !== "" && rule.key !== "")).toBe(true);
  });

  it("has a sentence for every rule and a group name for every key, and no stale ones", () => {
    expect(ruleWordProblems(rules, RULE_GROUP_ORDER, en)).toEqual([]);
  });

  it("orders only keys the file has", () => {
    const known = new Set(rules.map((rule) => rule.key));
    expect(RULE_GROUP_ORDER.filter((key) => !known.has(key))).toEqual([]);
  });
});

describe("rule word guard catches a planted fault", () => {
  const sample: RuleFields[] = [
    { rule_id: "a-rule", key: "effortLevel" },
    { rule_id: "b-rule", key: "modelSettings.maxEffortLevel" },
  ];
  const good: Deck = {
    "rl_a-rule": "x",
    "rl_b-rule": "y",
    rg_effortLevel: "Effort level",
    rg_modelSettings_maxEffortLevel: "Max effort",
    rg_today: "Today",
  };

  const without = (deck: Deck, key: string): Deck =>
    Object.fromEntries(Object.entries(deck).filter(([name]) => name !== key));

  it("passes a complete deck, and skips the Review range keys", () => {
    expect(ruleWordProblems(sample, ["effortLevel"], good)).toEqual([]);
  });

  it("fails on a missing rl_ key", () => {
    const planted = without(good, "rl_b-rule");
    expect(ruleWordProblems(sample, [], planted)).toEqual(["rule b-rule has no rl_b-rule"]);
  });

  it("fails on a missing rg_ key, with dots turned into underscores", () => {
    const planted = without(good, "rg_modelSettings_maxEffortLevel");
    expect(ruleWordProblems(sample, [], planted)).toEqual([
      "key modelSettings.maxEffortLevel has no rg_modelSettings_maxEffortLevel",
    ]);
  });

  it("fails on a stale rl_ or rg_ key", () => {
    expect(ruleWordProblems(sample, [], { ...good, "rl_old-rule": "z" })).toEqual([
      "rl_old-rule names a rule the file no longer has",
    ]);
    expect(ruleWordProblems(sample, [], { ...good, rg_oldKey: "z" })).toEqual([
      "rg_oldKey names a key the file no longer has",
    ]);
  });

  it("fails on an order entry the file lacks", () => {
    expect(ruleWordProblems(sample, ["effortLevel", "nope"], good)).toEqual([
      "RULE_GROUP_ORDER has nope, which rules.json lacks",
    ]);
  });
});

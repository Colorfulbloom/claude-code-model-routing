/*
 * Fails on an en.ts key that no code names. A key counts as used when a non-test source file
 * calls t("key") or tn("base"), with single or double quotes, or names it as a string literal in
 * lists.ts or help.ts. Keys reached through a template or a map are exempt by prefix, each with
 * its reason below. Calls must use literal keys (fact K-819f): a key passed through a helper such
 * as pathLine("key", ...) reads as unused unless its family is listed here.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { en } from "@/strings/en";
import { sourceFiles, type SourceFile } from "@/test/source-files";

// Keys a later M5 task wires up. The lead empties this set before the exit runs.
const PENDING = new Set<string>([]);

/** Families the code reaches by building the key at run time, each with its reason. */
const EXEMPT_PREFIXES: readonly (readonly [string, string])[] = [
  ["rs_", "Why lines, picked by the server's reason code (setup-codes.test.ts guards the set)"],
  ["pc_", "problem titles and causes, picked by the problem code (setup-codes.test.ts)"],
  ["ro_", "reason-for-other lines, picked by a registry code (setup-codes.test.ts)"],
  ["sl_", "setting and capability labels, picked by the setting name (setup-codes.test.ts)"],
  ["hk_ev_", "hook event names, picked by the event (setup-codes.test.ts)"],
  ["cr_r_", "could-not-read reasons, picked by the reason code (setup-codes.test.ts)"],
  ["fx_cant_", "fix refusal reasons, picked by the reason code (setup-codes.test.ts)"],
  ["hk_nm_", "hook lines naming tools, built as word(`hk_nm_${event}`) in lib/setup-words.ts"],
  [
    "hk_wh_",
    "hook lines with a when clause, built as word(`hk_wh_${event}`) in lib/setup-words.ts",
  ],
  ["hk_ty_", 'hook handler types, read through codeWord("hk_ty_", type) in lib/setup-words.ts'],
  ["mc_t_", 'MCP transports, read through codeWord("mc_t_", transport) in InspectorFacts.tsx'],
  [
    "ins_imp_",
    'import states, read through codeWord("ins_imp_", state), guarded by setup-codes.test.ts',
  ],
  ["hp_list_", "help list labels, picked by list id through LIST_LABEL in HelpEntry.tsx"],
];

const RULES = resolve(import.meta.dirname, "..", "..", "..", "server", "data", "rules.json");

/**
 * The exact keys the rules page builds from rules.json: rl_<rule_id> for each rule and
 * rg_<key, dots as underscores> for each setting key. Only these are exempt, so the Review range
 * keys (rg_today, rg_7d, rg_w_*, rg_p_*, rg_n_*) go through the normal check. rules-words.test.ts
 * holds the same two rules and checks the file against the deck.
 */
export function ruleKeys(rules: readonly { rule_id: string; key: string }[]): Set<string> {
  const keys = new Set<string>();
  for (const rule of rules) {
    keys.add(`rl_${rule.rule_id}`);
    keys.add(`rg_${rule.key.split(".").join("_")}`);
  }
  return keys;
}

function loadRuleKeys(): Set<string> {
  const parsed = JSON.parse(readFileSync(RULES, "utf8")) as { rules?: unknown };
  if (!Array.isArray(parsed.rules)) throw new Error("rules.json has no rules list");
  return ruleKeys(parsed.rules as { rule_id: string; key: string }[]);
}

/** The keys a source text names in a literal t("key") call or tn("base") call. */
export function calledKeys(text: string): string[] {
  const found: string[] = [];
  for (const match of text.matchAll(/(?<![\w$.])(tn?)\(\s*["']([A-Za-z0-9_]+)["']/g)) {
    const [, fn, key] = match;
    if (key === undefined) continue;
    if (fn === "tn") found.push(`${key}_one`, `${key}_other`);
    else found.push(key);
  }
  return found;
}

/** The en.ts keys a text names as plain string literals, such as a titleByUnit value. */
export function literalKeys(text: string, deck: Readonly<Record<string, string>>): string[] {
  return [...text.matchAll(/["']([A-Za-z0-9_]+)["']/g)]
    .map((match) => match[1] ?? "")
    .filter((word) => Object.hasOwn(deck, word));
}

/** Keys no source uses, after the exempt prefixes and the pending set. */
export function orphanedKeys(
  sources: readonly SourceFile[],
  deck: Readonly<Record<string, string>>,
  pending: ReadonlySet<string>,
  prefixes: readonly (readonly [string, string])[],
  exact: ReadonlySet<string> = new Set(),
): string[] {
  const used = new Set<string>();
  for (const source of sources) {
    for (const key of calledKeys(source.text)) used.add(key);
    if (source.path === "strings/lists.ts" || source.path === "strings/help.ts") {
      for (const key of literalKeys(source.text, deck)) used.add(key);
    }
  }
  return Object.keys(deck).filter(
    (key) =>
      !used.has(key) &&
      !pending.has(key) &&
      !exact.has(key) &&
      !prefixes.some(([prefix]) => key.startsWith(prefix)),
  );
}

const sources = sourceFiles([".ts", ".tsx"]).filter((source) => source.path !== "strings/en.ts");

describe("unused string keys", () => {
  it("scans source files", () => {
    expect(sources.length).toBeGreaterThan(50);
  });

  it("has no en.ts key that no code names", () => {
    expect(orphanedKeys(sources, en, PENDING, EXEMPT_PREFIXES, loadRuleKeys())).toEqual([]);
  });

  it("keeps the pending set to real keys", () => {
    expect([...PENDING].filter((key) => !Object.hasOwn(en, key))).toEqual([]);
  });

  it("lists every exempt prefix with a reason, and each matches a key", () => {
    for (const [prefix, reason] of EXEMPT_PREFIXES) {
      expect(reason.length, prefix).toBeGreaterThan(10);
      expect(
        Object.keys(en).some((key) => key.startsWith(prefix)),
        prefix,
      ).toBe(true);
    }
  });
});

describe("unused key guard catches a planted fault", () => {
  const deck = { a_one: "x", a_other: "xs", b: "y", c: "z", d: "w" };

  it("reads single and double quotes, tn pairs, and skips method calls and longer names", () => {
    const text = [
      't("b")',
      "t('c', { x: 1 })",
      'tn("a", n)',
      'format("d")',
      'i18n.t("d")',
      "t(`d`)",
    ].join("\n");
    expect(calledKeys(text)).toEqual(["b", "c", "a_one", "a_other"]);
  });

  it("fails on a key nothing calls, and passes once something does", () => {
    const planted: SourceFile = { path: "a.tsx", text: 't("b") + tn("a", 2) + t("c")' };
    expect(orphanedKeys([planted], deck, new Set(), [])).toEqual(["d"]);
    const fixed: SourceFile = { path: "a.tsx", text: `${planted.text} + t("d")` };
    expect(orphanedKeys([fixed], deck, new Set(), [])).toEqual([]);
  });

  it("counts a literal in lists.ts and help.ts, but not in another file", () => {
    const text = '{ word: "d" }';
    expect(orphanedKeys([{ path: "strings/lists.ts", text }], deck, new Set(), [])).toContain("b");
    expect(orphanedKeys([{ path: "strings/lists.ts", text }], deck, new Set(), [])).not.toContain(
      "d",
    );
    expect(orphanedKeys([{ path: "x.ts", text }], deck, new Set(), [])).toContain("d");
  });

  it("derives the exact rule keys, and exempts only those", () => {
    const keys = ruleKeys([{ rule_id: "a-rule", key: "modelSettings.maxEffortLevel" }]);
    expect([...keys]).toEqual(["rl_a-rule", "rg_modelSettings_maxEffortLevel"]);
    const rule = { ...deck, "rl_a-rule": "s", rg_modelSettings_maxEffortLevel: "g", rg_today: "t" };
    const none: SourceFile = { path: "a.ts", text: 't("a_one")' };
    expect(orphanedKeys([none], rule, new Set(["b", "c", "d", "a_other"]), [], keys)).toEqual([
      "rg_today",
    ]);
  });

  it("skips pending keys and exempt prefixes", () => {
    const none: SourceFile = { path: "a.ts", text: "" };
    expect(orphanedKeys([none], deck, new Set(["b", "c"]), [["a_", "plural family"]])).toEqual([
      "d",
    ]);
  });
});

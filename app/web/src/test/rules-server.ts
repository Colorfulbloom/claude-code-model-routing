/*
 * A fake server for the Reference page tests. It wraps the app fake and answers /api/rules from the
 * real rules.json (read from disk, so a rule added to the file shows up in the tests), the way the
 * server builds it: outcomes are the distinct condition statuses in first-seen order, and `due`
 * follows the installed version. A test passes `installed` to make rules due, or `mutate` to change
 * rows.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { RuleRow, RulesAnswer } from "@/api/types";
import { fakeServer } from "@/test/server";
import type { FakeServer } from "@/test/server";

const RULES_FILE = resolve(import.meta.dirname, "..", "..", "..", "server", "data", "rules.json");

interface FileRule {
  rule_id: string;
  key: string;
  scope: RuleRow["scope"];
  combine: string;
  layer_order: string[];
  conditions: { status: RuleRow["outcomes"][number] }[];
  quotes: RuleRow["quotes"];
  experiment: string | null;
  confidence: RuleRow["confidence"];
  verified_on: RuleRow["verified_on"];
}

function parts(version: string): number[] {
  return version.split(".").map((part) => Number(part));
}

/** True when `a` is an older version than `b`, comparing dotted numbers. */
export function older(a: string, b: string): boolean {
  const x = parts(a);
  const y = parts(b);
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    const d = (x[i] ?? 0) - (y[i] ?? 0);
    if (d !== 0) return d < 0;
  }
  return false;
}

export interface RulesOptions {
  /** The installed Claude Code version. null means unknown, so no rule is due. */
  installed?: string | null;
  /** Changes the rows after they are built, such as to give one rule another version. */
  mutate?: (rules: RuleRow[]) => void;
}

/** Every rule of rules.json as the API sends it. */
export function ruleRows(options: RulesOptions = {}): RuleRow[] {
  const file = JSON.parse(readFileSync(RULES_FILE, "utf8")) as { rules: FileRule[] };
  const installed = options.installed === undefined ? "2.1.302" : options.installed;
  const rows: RuleRow[] = file.rules
    .map((rule) => ({
      rule_id: rule.rule_id,
      key: rule.key,
      scope: rule.scope,
      combine: rule.combine,
      layer_order: rule.layer_order,
      confidence: rule.confidence,
      verified_on: rule.verified_on,
      quotes: rule.quotes,
      experiment: rule.experiment === null ? null : (rule.experiment.split("/").pop() ?? null),
      outcomes: [...new Set(rule.conditions.map((condition) => condition.status))],
      due: installed !== null && older(rule.verified_on.claude_version, installed),
    }))
    .sort((a, b) => a.rule_id.localeCompare(b.rule_id));
  options.mutate?.(rows);
  return rows;
}

/** The oldest verified version across the rows. */
function oldest(rows: readonly RuleRow[]): string {
  let found = rows[0]?.verified_on.claude_version ?? "";
  for (const row of rows) {
    if (older(row.verified_on.claude_version, found)) found = row.verified_on.claude_version;
  }
  return found;
}

export function rulesAnswer(options: RulesOptions = {}): RulesAnswer {
  const rows = ruleRows(options);
  const installed = options.installed === undefined ? "2.1.302" : options.installed;
  return {
    server_time: "2026-11-10T15:00:00Z",
    etag: "rules-test",
    unchanged: false,
    installed,
    checked_on: oldest(rows),
    rules: rows,
  };
}

type Reply = RulesAnswer | number | Promise<RulesAnswer | number>;

export type RulesServer = FakeServer & { rules: { answer: () => Reply } };

export function rulesServer(options: RulesOptions = {}): RulesServer {
  const server = fakeServer();
  const base = server.fetch;
  const handler = { answer: (): Reply => rulesAnswer(options) };
  server.fetch = async (input, init) => {
    const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (!path.startsWith("/api/rules")) return base(input, init);
    server.calls.push(path);
    const value = await handler.answer();
    if (typeof value === "number") {
      return new Response(JSON.stringify({ code: "unexpected", path: null }), { status: value });
    }
    const etag = new URL(path, "http://x").searchParams.get("etag");
    const body =
      etag === value.etag
        ? { server_time: value.server_time, etag: value.etag, unchanged: true }
        : value;
    return new Response(JSON.stringify(body));
  };
  return Object.assign(server, { rules: handler });
}

/*
 * The page-side closed-enum test for Setup (M4). The server's code registry
 * (app/server/setup_codes.py) lists every code the setup read side can emit, and the page turns
 * each code into words. This test reads that file as text, plus the enums in the OpenAPI
 * document for the codes that live in models.py, and checks that every code has its string in
 * en.ts. A new code with no string fails here, unless it is in an allowlist below.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { en } from "@/strings/en";

const REGISTRY = resolve(import.meta.dirname, "..", "..", "..", "server", "setup_codes.py");
const OPENAPI = resolve(import.meta.dirname, "..", "api", "openapi.json");
const registry = readFileSync(REGISTRY, "utf8");

/** The first capture group of a match. */
function captured(match: RegExpMatchArray): string {
  return match[1] ?? "";
}

/** The text of one top-level assignment in setup_codes.py. */
function block(name: string): string {
  const start = registry.search(new RegExp(`^${name}\\b`, "m"));
  if (start < 0) throw new Error(`setup_codes.py has no ${name}`);
  // The block ends before the next line that starts in column 0 with a name or a comment. A
  // closing bracket in column 0 belongs to the block.
  const rest = registry.slice(start + 1);
  const end = rest.search(/\n(?=[#A-Za-z])/);
  return registry.slice(start, end < 0 ? undefined : start + 1 + end);
}

/** Double-quoted words in a block, with comments dropped first. */
function words(text: string): string[] {
  const code = text
    .split("\n")
    .map((line) => line.replace(/#.*$/, ""))
    .join("\n");
  return [...code.matchAll(/"(\w+)"/g)].map(captured);
}

/** Keys of the PROBLEM_CODES dict. */
function problemCodes(): string[] {
  return [...block("PROBLEM_CODES").matchAll(/^\s+"(\w+)":\s*"\w+",/gm)].map(captured);
}

/** The words of one registry set, such as ITEM_REASON_CODES. */
function setOf(name: string): string[] {
  return words(block(name).replace(/^\w+:[^=]*=/, ""));
}

/** The why codes by problem code. */
function whyCodes(): Record<string, string[]> {
  const text = block("WHY_CODES").replace(/^\w+:[^=]*=/, "");
  // split() with one capture group gives [before, key, body, key, body, ...].
  const pieces = text.split(/"(\w+)":\s*frozenset\(/);
  const out: Record<string, string[]> = {};
  for (let i = 1; i + 1 < pieces.length; i += 2) {
    out[pieces[i] ?? ""] = words(pieces[i + 1] ?? "");
  }
  return out;
}

/** Every enum array in the OpenAPI document. */
function openapiEnums(): string[][] {
  const found: string[][] = [];
  const walk = (node: unknown): void => {
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    if (node !== null && typeof node === "object") {
      const obj = node as Record<string, unknown>;
      if (Array.isArray(obj.enum) && obj.enum.every((v) => typeof v === "string")) {
        found.push(obj.enum);
      }
      Object.values(obj).forEach(walk);
    }
  };
  walk(JSON.parse(readFileSync(OPENAPI, "utf8")));
  return found;
}

/** The one enum that holds all of `members` and has exactly `size` values. */
function enumWith(members: string[], size: number): string[] {
  const matches = openapiEnums().filter(
    (values) => values.length === size && members.every((m) => values.includes(m)),
  );
  const first = matches[0];
  if (first === undefined) throw new Error(`no ${size}-value enum has ${members.join(", ")}`);
  for (const other of matches) expect([...other].sort()).toEqual([...first].sort());
  return first;
}

const strings = en as Record<string, string>;

function missing(keys: string[]): string[] {
  return keys.filter((key) => !(key in strings));
}

/** Both forms of a plural pair. */
function plural(base: string): string[] {
  return [`${base}_one`, `${base}_other`];
}

const parts = enumWith(["settings", "agents", "output_style", "mcp"], 10);
const scopes = enumWith(["managed", "command_line", "project_local", "shell"], 7);
const statuses = enumWith(["in_effect", "overridden", "lowered", "unknown"], 7);
const readOnly = enumWith(["claude_json_command", "command_line", "not_visible"], 5);
const importStates = enumWith(["read", "missing", "cycle", "too_deep", "not_read"], 5);
const loadsKinds = enumWith(["always", "on_demand", "when_no_claude_md"], 3);
const groups = enumWith(["couldnt_read", "wont_load", "not_as_set", "cant_tell", "notice"], 5);
const permissionKinds = enumWith(["allow", "ask", "deny", "default_mode", "directory"], 5);
// Files that could not be read. The two "not read here" reasons make no Couldn't read row.
const readFailures = enumWith(["permission", "not_utf8", "too_large", "vanished"], 7).filter(
  (reason) => reason !== "outside_scope" && reason !== "plugin_outside_plugins",
);

// Deliberate gaps. Each entry says why the deck has no key.
/** Parts with no su_none_<part> line. The output style always has a value (Default). */
const NO_NONE_LINE = new Set(["output_style"]);
/** Problem codes with no _c key, because the cause comes from other keys. */
const NO_CAUSE = new Set([
  // The Couldn't read card builds the cause from cr_r_<reason>.
  "permission",
  "not_utf8",
  "too_large",
  "folder_unlistable",
  "vanished",
  // The cause is the pc_hook_why_<why> and pc_mcp_why_<why> line.
  "hook_bad_handler",
  "mcp_bad_entry",
]);
/** Problem codes with no _q key, because the consequence is shared or counted. */
const NO_CONSEQUENCE = new Set([
  // These three share pc_read_q.
  "permission",
  "not_utf8",
  "too_large",
  // The consequence is the plural pc_hooks_disabled_q_* family.
  "hooks_disabled",
]);
/** Problem codes with no _t key. The notice is a counted sentence, pc_rows_no_usage_one and _other. */
const NO_TITLE = new Set(["rows_no_usage"]);

describe("setup codes parse", () => {
  it("reads the registry", () => {
    expect(problemCodes().length).toBeGreaterThan(30);
    expect(setOf("ITEM_REASON_CODES")).toContain("agent_loads");
    expect(setOf("CANT_FIX_REASONS")).toContain("walk_stopped");
    expect(Object.keys(whyCodes()).sort()).toEqual(["hook_bad_handler", "mcp_bad_entry"]);
  });
});

describe("setup codes have strings", () => {
  it("has a title for every problem code, and its cause and consequence", () => {
    const codes = problemCodes();
    const absent: string[] = [];
    for (const code of codes) {
      const keys: string[] = [];
      if (!NO_TITLE.has(code)) keys.push(`pc_${code}_t`);
      if (!NO_TITLE.has(code) && !NO_CAUSE.has(code)) keys.push(`pc_${code}_c`);
      if (!NO_TITLE.has(code) && !NO_CONSEQUENCE.has(code)) keys.push(`pc_${code}_q`);
      absent.push(...missing(keys));
    }
    expect(absent).toEqual([]);
  });

  it("keeps the allowlists to codes that exist", () => {
    const codes = new Set(problemCodes());
    for (const code of [...NO_CAUSE, ...NO_CONSEQUENCE, ...NO_TITLE]) {
      expect(codes.has(code), code).toBe(true);
    }
  });

  it("has the counted and shared lines the allowlists point to", () => {
    expect(
      missing([
        "pc_read_q",
        "pc_folder_unlistable_q",
        "pc_vanished_q",
        "pc_hook_bad_handler_t_noevent",
        "pc_hook_bad_handler_q",
        "pc_mcp_bad_entry_q",
        ...plural("pc_rows_no_usage"),
        ...plural("pc_hooks_disabled_q_all"),
        ...plural("pc_hooks_disabled_q_managed"),
      ]),
    ).toEqual([]);
  });

  it("has a cause line for each reason a file couldn't be read", () => {
    expect(readFailures.length).toBe(5);
    expect(missing(readFailures.map((r) => `cr_r_${r}`))).toEqual([]);
  });

  it("has a Why line for every item reason and agent check code", () => {
    // The registry spreads STATUSES into ITEM_REASON_CODES, so the seven statuses come from the
    // OpenAPI enum.
    const codes = [...statuses, ...setOf("ITEM_REASON_CODES"), ...setOf("AGENT_CHECK_CODES")];
    expect(codes).toContain("in_effect");
    expect(missing(codes.map((c) => `rs_${c}`))).toEqual([]);
  });

  it("covers every status in the item reasons", () => {
    expect(missing(statuses.map((s) => `rs_${s}`))).toEqual([]);
    expect(missing(statuses.map((s) => `status_${s}`))).toEqual([]);
  });

  it("has a can't-fix line for every reason", () => {
    expect(missing(setOf("CANT_FIX_REASONS").map((r) => `fx_cant_${r}`))).toEqual([]);
  });

  it("has a Why line for every hook and MCP why code", () => {
    const why = whyCodes();
    expect(missing((why.hook_bad_handler ?? []).map((w) => `pc_hook_why_${w}`))).toEqual([]);
    expect(missing((why.mcp_bad_entry ?? []).map((w) => `pc_mcp_why_${w}`))).toEqual([]);
    expect(why.hook_bad_handler?.length).toBeGreaterThan(0);
    expect(why.mcp_bad_entry?.length).toBeGreaterThan(0);
  });

  it("has a read-only line for every read-only code", () => {
    expect(missing(readOnly.map((c) => `ro_${c}`))).toEqual([]);
  });

  it("has a line for every import state and loads kind", () => {
    expect(missing(importStates.map((s) => `ins_imp_${s}`))).toEqual([]);
    expect(missing(loadsKinds.map((k) => `lo_${k}`))).toEqual([]);
  });

  it("has names for every part", () => {
    expect(missing(parts.map((p) => `sf_${p}`))).toEqual([]);
    expect(missing(parts.map((p) => `sp_sub_${p}`))).toEqual([]);
    expect(missing(parts.map((p) => `em_${p}`))).toEqual([]);
    expect(missing(parts.map((p) => `su_cell_${p}_one`))).toEqual([]);
    expect(missing(parts.map((p) => `su_cell_${p}_other`))).toEqual([]);
  });

  it("has a none-found line for every part that can be empty", () => {
    const wanted = parts.filter((p) => !NO_NONE_LINE.has(p));
    expect(wanted.length).toBe(parts.length - NO_NONE_LINE.size);
    expect(missing(wanted.map((p) => `su_none_${p}`))).toEqual([]);
  });

  it("has two lines for every scope", () => {
    expect(missing(scopes.flatMap((s) => [`sc_${s}`, `sc_${s}_2`]))).toEqual([]);
  });

  it("has a group name and question for every problem group", () => {
    expect(missing(groups.flatMap((g) => [`fx_g_${g}`, `fx_q_${g}`]))).toEqual([]);
  });

  it("has a summary line for every part's summary code", () => {
    const summary = block("SUMMARY_CODES");
    const codes = [...summary.matchAll(/"\w+":\s*"(\w+)"/g)].map(captured);
    expect(codes.length).toBe(parts.length);
    // A summary is built from pieces, so any su_r_<code> key (or a piece of it) counts.
    const absent = codes.filter(
      (code) => !Object.keys(strings).some((key) => key.startsWith(`su_r_${code}`)),
    );
    expect(absent).toEqual([]);
  });

  it("has a line for every permission group, agent group, empty reason and action", () => {
    expect(missing(permissionKinds.map((k) => `sp_g_${k}`))).toEqual([]);
    expect(missing(setOf("AGENT_GROUPS").map((g) => `ag_g_${g}`))).toEqual([]);
    expect(missing(["em_nv", "em_a_docs", "em_a_copy_folder", "em_a_copy_file"])).toEqual([]);
  });

  it("has a line for every notice code", () => {
    expect(setOf("NOTICE_CODES")).toEqual(["project_not_listed", "rows_no_usage"]);
    expect(missing(["su_unlisted", ...plural("pc_rows_no_usage")])).toEqual([]);
  });
});

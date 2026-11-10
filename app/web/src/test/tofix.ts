/*
 * Test data for the To fix page and the Agents inspector: problem rows, an agent setup item, and a
 * fake server that answers /api/problems and /api/setup/agents on top of the Review fake. A handler
 * gets the request URL and returns the answer or an HTTP status to fail with.
 */
import type { ProblemList, ProblemRow, SetupItem, SetupPartAnswer } from "@/api/types";
import { reviewServer } from "@/test/review-server";
import type { ReviewHandlers } from "@/test/review-server";
import type { FakeServer } from "@/test/server";

export const SETUP_TIME = "2026-11-10T15:00:00Z";

export function problemRow(over: Partial<ProblemRow> = {}): ProblemRow {
  return {
    id: "json_invalid:settings.json:3",
    kind: "problem",
    group: "wont_load",
    code: "json_invalid",
    thing: "settings.json",
    part: "settings",
    item_id: null,
    file: ".claude/settings.json",
    full_path: "/work/builder/.claude/settings.json",
    line: 3,
    params: {},
    confidence: { level: "documented", tested_on: null },
    fix: { kind: "open_item", target: "settings:model", reason: null },
    ...over,
  };
}

export function problemList(rows: ProblemRow[], over: Partial<ProblemList> = {}): ProblemList {
  return {
    project: "builder",
    server_time: SETUP_TIME,
    as_of: SETUP_TIME,
    etag: "problems-1",
    unchanged: false,
    rows,
    counted: rows.filter((r) => r.group !== "cant_tell" && r.group !== "notice").length,
    ...over,
  };
}

/** An agent item of the setup read. A file agent in the project unless a test says otherwise. */
export function agentItem(over: Partial<SetupItem> = {}): SetupItem {
  return {
    id: "agents:judge",
    part: "agents",
    key: "judge",
    name: "judge",
    label_known: true,
    order: 0,
    group: null,
    scope: "project",
    effective: {
      value: { text: "claude-opus-5-5 / high", masked: false },
      origin: "set",
      by_item: null,
    },
    sources: [
      {
        scope: "project",
        key: "name",
        file: ".claude/agents/judge.md",
        full_path: "/work/builder/.claude/agents/judge.md",
        line: 2,
        value: { text: "judge", masked: false },
        status: "in_effect",
        plugin: null,
      },
      {
        scope: "project",
        key: "model",
        file: ".claude/agents/judge.md",
        full_path: "/work/builder/.claude/agents/judge.md",
        line: 4,
        value: { text: "claude-opus-5-5", masked: false },
        status: "in_effect",
        plugin: null,
      },
      {
        scope: "project",
        key: "effort",
        file: ".claude/agents/judge.md",
        full_path: "/work/builder/.claude/agents/judge.md",
        line: 5,
        value: { text: "high", masked: false },
        status: "in_effect",
        plugin: null,
      },
    ],
    winner: 0,
    reach: [],
    status: "in_effect",
    reason: {
      code: "agent_loads",
      params: { file: ".claude/agents/judge.md" },
      rule_id: null,
      ref_item: null,
    },
    confidence: { level: "tested", tested_on: "2.1.310" },
    loads: null,
    applies: null,
    writable: false,
    read_only_reason: null,
    risk_tier: null,
    feature: "core",
    facts: {
      agent: {
        plugin: null,
        fields: [
          { name: "name", value: { text: "judge", masked: false }, line: 2, ignored: false },
          {
            name: "description",
            value: { text: "Weighs the evidence", masked: false },
            line: 3,
            ignored: false,
          },
          {
            name: "model",
            value: { text: "claude-opus-5-5", masked: false },
            line: 4,
            ignored: false,
          },
          { name: "effort", value: { text: "high", masked: false }, line: 5, ignored: false },
          { name: "tools", value: { text: "Read, Grep", masked: false }, line: 6, ignored: false },
        ],
      },
    },
    usage: null,
    real_path: null,
    not_read: null,
    may_change: false,
    ...over,
  };
}

/** A plugin agent with three ignored fields, for the read-only box and the ignored list. */
export function pluginAgentItem(over: Partial<SetupItem> = {}): SetupItem {
  const base = agentItem();
  const file = "lint-kit agents/linter.md";
  const full = "/work/home/plugins/cache/team/lint-kit/1.4.2/agents/linter.md";
  const src = (key: string, line: number, text: string): SetupItem["sources"][number] => ({
    scope: "plugin",
    key,
    file,
    full_path: full,
    line,
    value: { text, masked: false },
    status: "unknown",
    plugin: "lint-kit",
  });
  return {
    ...base,
    id: "agents:lint-kit:linter",
    key: "linter",
    name: "linter",
    scope: "plugin",
    effective: { value: null, origin: "unknown", by_item: null },
    sources: [src("name", 2, "linter"), src("model", 3, "haiku")],
    winner: 0,
    status: "ignored",
    reason: { code: "agent_loads", params: { file }, rule_id: null, ref_item: null },
    read_only_reason: { code: "plugin", params: { plugin: "lint-kit" }, command: null },
    facts: {
      agent: {
        plugin: "lint-kit",
        fields: [
          { name: "name", value: { text: "linter", masked: false }, line: 2, ignored: false },
          { name: "model", value: { text: "haiku", masked: false }, line: 3, ignored: false },
          {
            name: "permissionMode",
            value: { text: "acceptEdits", masked: false },
            line: 6,
            ignored: true,
          },
          { name: "hooks", value: { text: "1 hook", masked: false }, line: 7, ignored: true },
        ],
      },
    },
    ...over,
  };
}

export function partAnswer(
  items: SetupItem[],
  over: Partial<SetupPartAnswer> = {},
): SetupPartAnswer {
  return {
    project: "builder",
    part: "agents",
    server_time: SETUP_TIME,
    as_of: SETUP_TIME,
    etag: "agents-part-1",
    unchanged: false,
    items,
    groups: [],
    unreadable: [],
    empty: null,
    ...over,
  };
}

type Reply<T> = T | number | Promise<T | number>;

export interface SetupHandlers {
  problems: (url: URL) => Reply<ProblemList>;
  agentsPart: (url: URL) => Reply<SetupPartAnswer>;
}

/** The Review fake plus the two setup routes. Defaults answer an empty feed and an empty part. */
export function setupServer(
  over: Partial<SetupHandlers> = {},
  review: Partial<ReviewHandlers> = {},
): FakeServer & { setup: SetupHandlers; handlers: ReviewHandlers } {
  const setup: SetupHandlers = {
    problems: () => problemList([]),
    agentsPart: () => partAnswer([]),
    ...over,
  };
  const server = reviewServer(review);
  const base = server.fetch;
  async function answer<T>(reply: Reply<T>): Promise<Response> {
    const value = await reply;
    if (typeof value === "number") {
      return new Response(JSON.stringify({ code: "unexpected", path: null }), { status: value });
    }
    return new Response(JSON.stringify(value));
  }
  server.fetch = (input, init) => {
    const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(path, "http://x");
    if (url.pathname === "/api/problems") {
      server.calls.push(path);
      return answer(setup.problems(url));
    }
    if (url.pathname === "/api/setup/agents") {
      server.calls.push(path);
      return answer(setup.agentsPart(url));
    }
    return base(input, init);
  };
  return Object.assign(server, { setup });
}

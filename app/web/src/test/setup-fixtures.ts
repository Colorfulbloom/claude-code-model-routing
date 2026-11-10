/*
 * Builders for the setup answers the Your setup and surface page tests read. Each takes the fields a
 * test cares about and fills the rest with a quiet default: an item that is in effect, set at one
 * scope, with no facts and nothing read-only.
 */
import type {
  ProblemList,
  SetupItem,
  SetupMap,
  SetupPart,
  SetupPartAnswer,
  SetupPartRow,
} from "@/api/types";

export const SERVER_TIME = "2026-11-10T15:00:00Z";
export const STARTED_AT = "2026-11-10T14:21:00Z";

type Source = SetupItem["sources"][number];
type Cell = SetupPartRow["scopes"][number];

export function source(over: Partial<Source> = {}): Source {
  return {
    scope: "project",
    key: "effortLevel",
    file: ".claude/settings.json",
    full_path: "/work/builder/.claude/settings.json",
    line: 2,
    value: { text: "medium", masked: false },
    status: "in_effect",
    plugin: null,
    location: null,
    ...over,
  };
}

export function setupItem(part: SetupPart, key: string, over: Partial<SetupItem> = {}): SetupItem {
  return {
    id: `${part}:${key}`,
    part,
    key,
    name: key,
    label_known: true,
    order: 0,
    group: null,
    scope: "project",
    effective: null,
    sources: [source({ key })],
    winner: 0,
    reach: [],
    status: "in_effect",
    reason: { code: "in_effect", params: {}, rule_id: null, ref_item: null },
    confidence: { level: "documented", tested_on: null },
    loads: null,
    applies: null,
    writable: false,
    read_only_reason: null,
    risk_tier: null,
    feature: "core",
    facts: {
      agent: null,
      instruction: null,
      skill: null,
      hook: null,
      mcp: null,
      permission: null,
      plugin: null,
      output_style: null,
    },
    usage: null,
    real_path: null,
    not_read: null,
    may_change: false,
    location: null,
    ...over,
  };
}

export function partAnswer(
  part: SetupPart,
  items: SetupItem[],
  over: Partial<SetupPartAnswer> = {},
): SetupPartAnswer {
  const groups: Record<string, number> = {};
  for (const item of items)
    if (item.group !== null) groups[item.group] = (groups[item.group] ?? 0) + 1;
  return {
    project: "builder",
    part,
    server_time: SERVER_TIME,
    as_of: SERVER_TIME,
    etag: `part-${part}-${String(items.length)}`,
    unchanged: false,
    items: items.map((item, order) => ({ ...item, order })),
    groups: Object.entries(groups).map(([key, count]) => ({ key, count })),
    unreadable: [],
    empty: null,
    ...over,
  };
}

const SCOPES = [
  "managed",
  "command_line",
  "project_local",
  "project",
  "user",
  "plugin",
  "shell",
] as const;

/** Seven scope cells, none set, with the command line and shell as the server sends them. */
export function cells(over: Partial<Record<(typeof SCOPES)[number], Partial<Cell>>> = {}): Cell[] {
  return SCOPES.map((scope) => ({
    scope,
    state: scope === "command_line" || scope === "shell" ? "not_visible" : "not_set",
    summary: null,
    ...over[scope],
  }));
}

export function partRow(part: SetupPart, over: Partial<SetupPartRow> = {}): SetupPartRow {
  return {
    part,
    summary: { code: part, params: {} },
    statuses: [{ status: "in_effect", count: 1 }],
    counted_problems: 0,
    unreadable: false,
    empty: null,
    scopes: cells(),
    ...over,
  };
}

export function setupMap(parts: SetupPartRow[], over: Partial<SetupMap> = {}): SetupMap {
  return {
    project: "builder",
    server_time: SERVER_TIME,
    server_started_at: STARTED_AT,
    as_of: SERVER_TIME,
    etag: "map-a",
    unchanged: false,
    listed: true,
    notices: [],
    parts,
    ...over,
  };
}

export function problemList(over: Partial<ProblemList> = {}): ProblemList {
  return {
    project: "builder",
    server_time: SERVER_TIME,
    as_of: SERVER_TIME,
    etag: "prob-a",
    unchanged: false,
    counted: 0,
    rows: [],
    ...over,
  };
}

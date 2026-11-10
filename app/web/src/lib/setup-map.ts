/*
 * The setup map as words. Each part row of /api/setup becomes a summary line, its status chips
 * and, with the Switch on, one scope chip per scope that has something to say. Every row carries
 * its scopes always (need 1), so flipping the Switch fetches nothing. The page owns every word, so
 * the summary is built here from the row's code and params.
 */
import type { SetupMap, SetupPart, SetupPartRow } from "@/api/types";
import { modelLabel } from "@/lib/models";
import {
  PART_NAMES,
  PART_NONE,
  SCOPE_NAMES,
  statusWord,
  type Scope,
  type Status,
} from "@/lib/setup-words";
import { t, tn } from "@/strings/t";

export interface MapStatus {
  status: Status;
  label: string;
}

export interface MapChip {
  scope: Scope;
  /** The scope's name, such as "Shared project". */
  name: string;
  /** What that scope holds, such as "3 agents" or "Not visible here". */
  value: string;
}

export interface MapRowView {
  part: SetupPart;
  name: string;
  summary: string;
  /** "Couldn't read all its files", or null. */
  unread: string | null;
  statuses: MapStatus[];
  /** Scope chips in the board's order, empty when the Switch is off. */
  chips: MapChip[];
  /** "Nothing set here" for a row with the Switch on and no chip. */
  noChips: boolean;
  /** The part is empty or Bar Tab can't see it, so the row has no statuses. */
  quiet: boolean;
}

/** The board's chip order. The server sends its own, with the plugin and shell last. */
export const CHIP_ORDER: readonly Scope[] = [
  "managed",
  "command_line",
  "shell",
  "project_local",
  "project",
  "user",
  "plugin",
];

/** Parts a command-line flag can set, so their Command line scope says "Not visible here". */
const HAS_FLAGS: ReadonlySet<SetupPart> = new Set<SetupPart>(["settings", "agents"]);

function num(value: string | undefined): number {
  const n = Number(value ?? "0");
  return Number.isFinite(n) ? n : 0;
}

function join(pieces: readonly (string | null)[], glue = ", "): string {
  return pieces.filter((piece): piece is string => piece !== null && piece !== "").join(glue);
}

/** The model and effort a settings row says. Either can be missing. */
function modelEffort(params: Readonly<Record<string, string>>): string {
  const model = params.model;
  const effort = params.effort;
  if (model !== undefined && effort !== undefined) {
    return t("su_r_model_effort", { model: modelLabel(model), effort });
  }
  if (model !== undefined) return t("su_r_model_effort_model", { model: modelLabel(model) });
  if (effort !== undefined) return t("su_r_model_effort_effort", { effort });
  return t("su_r_model_effort_none");
}

/** What a part row says on the map, from its summary code and params. */
export function summaryText(row: SetupPartRow): string {
  const p = row.summary.params;
  if (row.empty?.reason === "not_visible") return t("su_nv_part");
  if (row.empty?.reason === "none_found") return PART_NONE[row.part]();
  switch (row.part) {
    case "settings":
      return modelEffort(p);
    case "agents": {
      const idle = num(p.no_runs);
      return join([
        tn("su_r_agents", num(p.count)),
        idle > 0 ? t("su_r_agents_idle", { n: idle }) : null,
      ]);
    }
    case "instructions":
      return join([
        tn("su_r_instructions", num(p.count)),
        tn("su_r_instructions_lines", num(p.lines)),
      ]);
    case "rules": {
      const onDemand = num(p.on_demand);
      return join([
        tn("su_r_rules", num(p.count)),
        onDemand > 0 ? tn("su_r_rules_on_demand", onDemand, { globs: p.globs ?? "" }) : null,
      ]);
    }
    case "skills":
      return tn("su_r_skills", num(p.count));
    case "hooks":
      return join([tn("su_r_hooks", num(p.count)), tn("su_r_hooks_events", num(p.events))], " ");
    case "permissions": {
      const allow = num(p.allow);
      const deny = num(p.deny);
      const ask = num(p.ask);
      const mode = p.mode;
      const pieces = [
        deny > 0 ? t("su_r_permissions_deny", { n: deny }) : null,
        ask > 0 ? tn("su_r_permissions_ask", ask) : null,
        allow > 0 ? t("su_r_permissions_allow", { n: allow }) : null,
        mode !== undefined ? t("su_r_permissions_mode", { mode }) : null,
      ];
      const text = join(pieces);
      return text === "" ? t("su_r_permissions_none") : text;
    }
    case "mcp": {
      const off = num(p.not_approved);
      return join([
        tn("su_r_mcp", num(p.count)),
        off > 0 ? t("su_r_mcp_not_approved", { n: off }) : null,
      ]);
    }
    case "plugins": {
      const count = num(p.count);
      const on = num(p.enabled);
      const off = count - on;
      return join([tn("su_r_plugins", on), off > 0 ? t("su_r_plugins_off", { n: off }) : null]);
    }
    case "output_style":
      return p.active === undefined
        ? t("su_r_output_style_default")
        : t("su_r_output_style", { active: p.active });
  }
}

/** One scope cell's count, worded for its part. */
function cellCount(part: SetupPart, n: number): string {
  switch (part) {
    case "settings":
      return tn("su_cell_settings", n);
    case "agents":
      return tn("su_cell_agents", n);
    case "instructions":
      return tn("su_cell_instructions", n);
    case "rules":
      return tn("su_cell_rules", n);
    case "skills":
      return tn("su_cell_skills", n);
    case "hooks":
      return tn("su_cell_hooks", n);
    case "permissions":
      return tn("su_cell_permissions", n);
    case "mcp":
      return tn("su_cell_mcp", n);
    case "plugins":
      return tn("su_cell_plugins", n);
    case "output_style":
      return tn("su_cell_output_style", n);
  }
}

function cellModelEffort(params: Readonly<Record<string, string>>): string {
  const model = params.model;
  const effort = params.effort;
  if (model !== undefined && effort !== undefined) {
    return t("su_cell_model_effort", { model: modelLabel(model), effort });
  }
  if (model !== undefined) return t("su_cell_model", { model: modelLabel(model) });
  if (effort !== undefined) return t("su_cell_effort", { effort });
  return cellCount("settings", 1);
}

/** The scope chips of a row, in the board's order. Scopes with nothing to say give no chip. */
export function chipsOf(row: SetupPartRow, listed: boolean): MapChip[] {
  const chips: MapChip[] = [];
  for (const scope of CHIP_ORDER) {
    const cell = row.scopes.find((c) => c.scope === scope);
    if (cell === undefined) continue;
    let value: string | null = null;
    if (cell.state === "set" && cell.summary !== null) {
      value =
        cell.summary.code === "model_effort"
          ? cellModelEffort(cell.summary.params)
          : cellCount(row.part, num(cell.summary.params.n));
    } else if (cell.state === "unreadable") {
      value = t("sc_unreadable");
    } else if (cell.state === "not_visible") {
      if ((scope === "project_local" || scope === "project") && !listed) value = t("su_nr");
      else if (scope === "command_line" && HAS_FLAGS.has(row.part)) value = t("su_nv");
    }
    if (value !== null) chips.push({ scope, name: SCOPE_NAMES[scope](), value });
  }
  return chips;
}

/** The map's rows, in the server's part order. */
export function mapRows(map: SetupMap, scopesOn: boolean): MapRowView[] {
  return map.parts.map((row) => {
    const quiet = row.empty !== null && row.part !== "output_style";
    const chips = scopesOn ? chipsOf(row, map.listed) : [];
    // An output style that nothing sets runs the default, which the board draws as a status.
    const statuses: MapStatus[] =
      row.part === "output_style" && row.statuses.length === 0 && row.empty?.reason === "none_found"
        ? [{ status: "default", label: statusWord("default") }]
        : row.statuses.map((s) => ({ status: s.status, label: statusWord(s.status) }));
    return {
      part: row.part,
      name: PART_NAMES[row.part](),
      summary: summaryText(row),
      unread: row.unreadable ? t("su_unread") : null,
      statuses,
      chips,
      noChips: scopesOn && chips.length === 0,
      quiet,
    };
  });
}

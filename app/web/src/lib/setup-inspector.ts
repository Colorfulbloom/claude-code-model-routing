/*
 * The inspector of one setup item as words. The server sends codes, ids and masked values, and this
 * module builds the lines the inspector shows: what runs, where it is set and why, the read-only
 * reason, the not-read-here state and the usage line. The facts that differ by kind (agent fields,
 * imports, hook handlers and so on) are drawn by the component from `item.facts`.
 *
 * The page never parses `reason.params`. What runs comes from `effective`, the linked item from
 * `ref_item` and `by_item`, and the path to copy from the source's `full_path`, while the screen
 * shows the short `file`.
 */
import type { SetupItem } from "@/api/types";
import type { ScopeRow, StatusWord } from "@/components/ListInspector/types";
import { clockShort } from "@/lib/clock";
import { isUntilM7 } from "@/lib/edit-page";
import { modelLabel } from "@/lib/models";
import { pluginOf, settingValueText } from "@/lib/setup-list";
import {
  codeWord,
  hookRuns,
  itemLabel,
  scopeMeaning,
  scopeName,
  statusWord,
  word,
  type Scope,
} from "@/lib/setup-words";
import { t, tn } from "@/strings/t";

type SetupSource = SetupItem["sources"][number];

export function statusOf(item: Pick<SetupItem, "status">): StatusWord {
  return { status: item.status, label: statusWord(item.status) };
}

/** "settings.json line 3", "settings.json", or null for a source with no file. */
export function whereOf(source: Pick<SetupSource, "file" | "line">): string | null {
  if (source.file === null) return null;
  return source.line === null
    ? t("loc_file", { file: source.file })
    : t("loc_line", { file: source.file, line: source.line });
}

/** The winning source, or null when nothing wins. */
export function winnerOf(item: SetupItem): SetupSource | null {
  return item.winner === null ? null : (item.sources[item.winner] ?? null);
}

/** The path Copy path puts on the clipboard: the winner's file, else the first source with one. */
export function copyPathOf(item: SetupItem): string | null {
  const win = winnerOf(item);
  if (win?.full_path != null) return win.full_path;
  return item.sources.find((s) => s.full_path !== null)?.full_path ?? null;
}

const MODEL_KEY = /(^|\.|--)(model|anthropic_model)$/i;

/** A source's value as shown, with a model id turned into its name. */
function sourceValue(source: SetupSource): { text: string; masked: boolean } | undefined {
  if (source.value === null) return undefined;
  const text = MODEL_KEY.test(source.key)
    ? modelLabel(source.value.text)
    : settingValueText(source.key, source.value.text);
  return { text, masked: source.value.masked };
}

function scopeLabelOf(scope: Scope, source: SetupSource | null, startedAt: string | null) {
  if (source?.location === "parent") {
    return { name: t("ins_parent"), meaning: scopeMeaning("project", startedAt) };
  }
  return {
    name: scopeName(scope, source?.plugin ?? null),
    meaning: scopeMeaning(scope, startedAt),
  };
}

/**
 * The where-set rows, top wins. Every source is a row in the server's order. A scope Bar Tab can't
 * see (the Command line, and Your shell when no source reads it) gets a row of its own with the
 * reason, after the Managed and Project local rows.
 *
 * An agent's trail is its own files only, the `name` sources. The settings and environment layers
 * that cap or override its model or effort stay in the API's `sources`, and the page says them in
 * the callout's reason instead of as trail rows (a-m4-p11-agents shows two rows).
 */
export function whereRows(item: SetupItem, startedAt: number | string | null): ScopeRow[] {
  const clock = startedAt === null ? null : clockShort(startedAt);
  const agent = item.part === "agents";
  const shown = agent ? item.sources.filter((source) => source.key === "name") : item.sources;
  const rows: ScopeRow[] = shown.map((source, index) => {
    const value = sourceValue(source);
    const place = source.file === null ? undefined : whereLocation(source);
    return {
      id: `${source.scope}:${source.key}:${String(index)}`,
      scope: scopeLabelOf(source.scope, source, clock),
      ...(source.key !== "file" && source.key !== "name" ? { key: source.key } : {}),
      ...(value !== undefined ? { value } : {}),
      status: statusOf(source),
      ...(place !== undefined ? { location: place } : {}),
    };
  });
  if (agent) return rows;
  const have = new Set(item.sources.map((s) => s.scope));
  const unseen: ScopeRow[] = [];
  for (const reach of item.reach) {
    if (reach.visible || have.has(reach.scope)) continue;
    if (reach.scope !== "command_line" && reach.scope !== "shell") continue;
    unseen.push({
      id: `${reach.scope}:not-visible`,
      scope: scopeLabelOf(reach.scope, null, clock),
      note: reach.scope === "shell" ? t("in_nset_shell") : t("su_nv"),
    });
  }
  // The command line comes before the shell, and both come after Managed and Project local.
  unseen.sort((a, b) => Number(a.id.startsWith("shell")) - Number(b.id.startsWith("shell")));
  let at = 0;
  while (
    at < item.sources.length &&
    (item.sources[at]?.scope === "managed" || item.sources[at]?.scope === "project_local")
  ) {
    at += 1;
  }
  rows.splice(at, 0, ...unseen);
  return rows;
}

function whereLocation(source: SetupSource): string {
  const file = source.file ?? "";
  return source.line === null ? file : `${file}:${String(source.line)}`;
}

export interface RunsLine {
  text: string;
  masked: boolean;
}

function parseAgentValue(text: string): { model: string; effort: string } | null {
  const cut = text.indexOf(" / ");
  if (cut < 0) return null;
  return { model: text.slice(0, cut), effort: text.slice(cut + 3) };
}

function permissionRuns(item: SetupItem, mode: string | null): RunsLine | null {
  const facts = item.facts.permission;
  if (facts === null || facts === undefined) return null;
  switch (facts.kind) {
    case "allow":
      return { text: t("pm_runs_allow"), masked: false };
    case "ask":
      return { text: t("pm_runs_ask"), masked: false };
    case "deny":
      return { text: t("pm_runs_deny"), masked: false };
    case "directory":
      return { text: t("pm_runs_directory"), masked: false };
    case "default_mode":
      return mode === null ? null : { text: t("pm_runs_mode", { mode }), masked: false };
  }
}

/** The three causes an origin line names. The pill's status decides which one, never the value. */
export type OriginKind = "cap" | "override" | "unknown";

export interface OriginNote {
  kind: OriginKind;
  text: string;
}

/** The check codes each status can carry. A status paired with another code names no cause. */
const CODES_OF_STATUS: Readonly<Record<string, readonly string[]>> = {
  lowered: ["lowered_by_cap", "lowered_ran_at_pin"],
  overridden: ["pin_overridden"],
  unknown: ["expected_unknown", "unknown_status"],
};

/** "settings in .claude/settings.json line 4 wins." for a layer that replaces the pin, or null. */
function overrideText(params: Readonly<Record<string, string>>): string | null {
  const key = params.by_key ?? "";
  if (params.by_file !== undefined && params.by_line !== undefined) {
    return t("in_origin_override_file", { key, file: params.by_file, line: params.by_line });
  }
  if (params.by_via !== undefined) return t("in_origin_override_via", { via: params.by_via });
  if (params.by_layer !== undefined) {
    return t("in_origin_override_layer", { key, layer: params.by_layer });
  }
  return null;
}

/**
 * The sentence that says why what runs is not what is set, tied to the status pill. An agent with
 * a `check` gets its sentence from the pill's status and the check's code, which the server takes
 * from the same worst setting, so the pill and the sentence name one cause. When a cap lowers its
 * effort and a higher layer replaces its model, the pill reads Overridden and the sentence names
 * the layer that wins, never the cap. A status that carries none of the three causes gets no
 * sentence, and neither does a status that pairs with the code of another cause.
 *
 * An item with no check (a setting, or an agent the Model check does not judge) names the cap only
 * when its status is Lowered, and reads Unknown from an effective value that nothing sets.
 */
export function originNote(item: SetupItem): OriginNote | null {
  const check = item.check ?? null;
  if (check !== null) {
    if (!(CODES_OF_STATUS[item.status]?.includes(check.code) ?? false)) return null;
    switch (item.status) {
      case "lowered": {
        const cap = check.params.cap_key;
        const by = cap === undefined ? (item.effective?.by_item ?? null) : `settings:${cap}`;
        return by === null
          ? null
          : { kind: "cap", text: t("in_origin_cap", { item: itemLabel(by) }) };
      }
      case "overridden": {
        const text = overrideText(check.params);
        return text === null ? null : { kind: "override", text };
      }
      case "unknown":
        return { kind: "unknown", text: t("in_origin_unknown") };
      default:
        return null;
    }
  }
  const eff = item.effective;
  if (eff?.origin === "cap" && eff.by_item !== null && item.status === "lowered") {
    return { kind: "cap", text: t("in_origin_cap", { item: itemLabel(eff.by_item) }) };
  }
  if (eff?.origin === "unknown" && eff.value === null) {
    return { kind: "unknown", text: t("in_origin_unknown") };
  }
  return null;
}

/** The headline of the inspector, "Runs at high", by the item's kind. Null when nothing runs. */
export function runsLine(item: SetupItem): RunsLine | null {
  const value = item.effective?.value ?? null;
  const masked = value?.masked ?? false;
  const plain = (text: string): RunsLine => ({ text, masked: false });
  const origin = originNote(item);
  if (origin?.kind === "unknown") return plain(origin.text);
  switch (item.part) {
    case "settings": {
      if (value === null) return null;
      if (item.key === "model")
        return { text: t("in_runs_model", { value: modelLabel(value.text) }), masked };
      if (item.key === "effortLevel")
        return { text: t("in_runs_effort", { value: value.text }), masked };
      return { text: t("in_runs", { value: settingValueText(item.key, value.text) }), masked };
    }
    case "agents": {
      if (value === null) return null;
      const pair = parseAgentValue(value.text);
      return pair === null
        ? { text: t("in_runs", { value: value.text }), masked }
        : plain(t("ag_runs", { model: modelLabel(pair.model), effort: pair.effort }));
    }
    case "instructions":
    case "rules": {
      const loads = item.loads;
      if (loads === null) return null;
      if (loads.kind === "always") return plain(t("lo_always"));
      if (loads.kind === "when_no_claude_md") return plain(t("lo_when_no_claude_md"));
      const folder = loads.globs[0];
      return plain(
        item.part === "instructions" && folder !== undefined
          ? t("lo_on_demand_folder", { folder })
          : t("lo_on_demand"),
      );
    }
    case "skills":
      return plain(t("sk_runs"));
    case "hooks": {
      const hook = item.facts.hook;
      if (hook === null || hook === undefined) return plain(codeWord("hk_ev_", item.key));
      return plain(hookRuns(hook.event, hook.matcher, hook.handler_type));
    }
    case "permissions":
      return permissionRuns(item, value?.text ?? null);
    case "mcp": {
      const facts = item.facts.mcp;
      if (facts === null || facts === undefined) return null;
      if (facts.command !== null) {
        return {
          text: t("mc_runs_cmd", { command: facts.command.text }),
          masked: facts.command.masked,
        };
      }
      if (facts.url !== null) {
        return { text: t("mc_runs_url", { url: facts.url.text }), masked: facts.url.masked };
      }
      return null;
    }
    case "plugins": {
      if (item.not_read === "plugin_outside_plugins") return plain(t("pl_outside_runs"));
      const contents = item.facts.plugin?.contents ?? [];
      if (contents.length === 0) return plain(t("pl_runs_none"));
      return plain(t("pl_runs", { list: contentsList(contents) }));
    }
    case "output_style": {
      const active = item.facts.output_style?.active ?? null;
      return plain(active === null ? t("st_runs_default") : t("st_runs", { style: active }));
    }
  }
}

/** "1 agent, 1 skill" for the item ids a plugin adds. */
export function contentsList(ids: readonly string[]): string {
  const counts = new Map<string, number>();
  for (const id of ids) {
    const part = id.slice(0, Math.max(id.indexOf(":"), 0));
    counts.set(part, (counts.get(part) ?? 0) + 1);
  }
  const pieces: string[] = [];
  for (const [part, n] of counts) {
    switch (part) {
      case "agents":
        pieces.push(tn("su_cell_agents", n));
        break;
      case "skills":
        pieces.push(tn("su_cell_skills", n));
        break;
      case "hooks":
        pieces.push(tn("su_cell_hooks", n));
        break;
      case "mcp":
        pieces.push(tn("su_cell_mcp", n));
        break;
      case "output_style":
        pieces.push(tn("su_cell_output_style", n));
        break;
      default:
        pieces.push(String(n));
    }
  }
  return pieces.join(", ");
}

/** The "Set to X in Scope, file line N" line, with the cap or default that changes what runs. */
export function setLine(item: SetupItem): string | null {
  const win = winnerOf(item);
  const parts: string[] = [];
  if (win !== null) {
    const where = whereOf(win);
    const value = sourceValue(win);
    if (win.plugin !== null && where !== null) {
      parts.push(t("in_set_plugin", { plugin: win.plugin, where }));
    } else if (win.scope === "shell") {
      parts.push(t("in_set_shell", { key: win.key }));
    } else if (where !== null) {
      const scope = win.location === "parent" ? t("ins_parent") : scopeName(win.scope);
      parts.push(
        item.part === "settings" && value !== undefined
          ? t("in_set_value", { value: value.text, scope, where })
          : t("in_set_at", { scope, where }),
      );
    }
  }
  const origin = originNote(item);
  if (origin !== null && origin.kind !== "unknown") {
    parts.push(origin.text);
  } else if (item.effective?.origin === "default" && win === null) {
    parts.push(t("in_origin_default"));
  }
  return parts.length === 0 ? null : parts.join(" ");
}

export interface ReadOnlyView {
  lockLabel: string;
  reason: string;
  command?: { command: string; copyLabel: string; copiedLabel: string };
  path?: { value: string; label: string; copiedLabel: string; text?: string };
}

/** The path of the box's Copy path row: the full path to copy, and the path as the screen shows it. */
function copyRow(item: SetupItem): Pick<ReadOnlyView, "path"> {
  const value = copyPathOf(item);
  if (value === null) return {};
  const win = winnerOf(item);
  const text = win?.file ?? item.sources.find((s) => s.file !== null)?.file ?? null;
  return {
    path: {
      value,
      label: t("in_copy"),
      copiedLabel: t("an_copied"),
      ...(text !== null ? { text } : {}),
    },
  };
}

/** The plugin's reason. Only an agent has a file to copy into its own folder and edit. */
function pluginReason(item: SetupItem, plugin: string): string {
  const reason = t("ro_plugin", { plugin });
  return item.part === "agents" ? `${reason} ${t("ro_plugin_2")}` : reason;
}

/** The read-only box, or null for an item with no read-only reason. */
export function readOnlyView(item: SetupItem): ReadOnlyView | null {
  const why = item.read_only_reason;
  if (why === null) return null;
  const withPath = why.code !== "command_line" && why.code !== "not_visible" ? copyRow(item) : {};
  const base = { lockLabel: t("ro_h") };
  switch (why.code) {
    case "managed":
      return { ...base, reason: t("ro_managed"), ...withPath };
    case "plugin":
      return {
        ...base,
        reason: pluginReason(item, why.params.plugin ?? pluginOf(item) ?? ""),
        ...withPath,
      };
    case "claude_json_command":
      return {
        ...base,
        reason: t("ro_claude_json_command"),
        ...(why.command !== null
          ? {
              command: {
                command: why.command.text,
                copyLabel: t("lk_copy"),
                copiedLabel: t("an_copied"),
              },
            }
          : {}),
      };
    case "command_line":
      return { ...base, reason: t("ro_command_line") };
    case "not_visible":
      return { ...base, reason: t("ro_not_visible") };
  }
}

/**
 * The read-only box of an item the server calls editable but Bar Tab can't edit yet: a Settings
 * item that waits for M7 (`ro_field_until_m7`), or an agent, whose editing comes next
 * (`ro_agents_next`). Null for every other item, and for one that has its own read-only reason.
 */
export function notYetEditableView(item: SetupItem): ReadOnlyView | null {
  if (item.read_only_reason !== null) return null;
  const withPath = copyRow(item);
  const base = { lockLabel: t("ro_h") };
  if (isUntilM7(item)) return { ...base, reason: t("ro_field_until_m7"), ...withPath };
  if (item.part === "agents") return { ...base, reason: t("ro_agents_next"), ...withPath };
  return null;
}

/** The sentence of the box an item the server did not read gets, or null. The pill is its status. */
export function notReadView(item: SetupItem): { body: string } | null {
  if (item.not_read === null) return null;
  return {
    body: item.not_read === "plugin_outside_plugins" ? t("pl_outside") : t("ins_imp_not_read"),
  };
}

/** The Why line (reason, then what the kind adds) and the confidence line. */
export function whyView(item: SetupItem): { body: string; confidence: string } | null {
  const reason = item.reason;
  const pieces: string[] = [];
  if (reason !== null) {
    pieces.push(
      word(`rs_${reason.code}`, { ...reason.params, where: whereOfWinner(item) }) ?? reason.code,
    );
  }
  if (item.part === "instructions") pieces.push(t("ins_why"));
  else if (item.part === "rules") pieces.push(t("ru_why"));
  else if (item.part === "permissions" && item.facts.permission?.kind !== "directory") {
    pieces.push(t("pm_why"));
  }
  if (pieces.length === 0) return null;
  return { body: pieces.join(" "), confidence: confidenceLine(item) };
}

function whereOfWinner(item: SetupItem): string {
  const win = winnerOf(item);
  return win === null ? "" : (whereOf(win) ?? "");
}

/** How sure Bar Tab is, in words. The shell is always assumed, because Bar Tab can't see it. */
export function confidenceLine(item: SetupItem): string {
  const level = item.confidence.level;
  if (level === "tested") {
    return item.confidence.tested_on === null
      ? t("in_conf_tested_nover")
      : t("in_conf_tested", { version: item.confidence.tested_on });
  }
  if (level === "documented") return t("in_conf_documented");
  return winnerOf(item)?.scope === "shell" ? t("in_conf_assumed_shell") : t("in_conf_assumed");
}

/** The usage line (runs at this value, or an agent's runs), or null. */
export function usageLine(item: SetupItem): string | null {
  const usage = item.usage;
  if (usage === null) return null;
  const p = usage.params;
  const days = Number(p.days ?? "0");
  if (usage.code === "agent_runs") {
    const runs = Number(p.runs ?? "0");
    return runs === 0 ? t("ag_usage_none", { days }) : tn("ag_usage", runs, { days });
  }
  if (usage.code === "runs_at_value") {
    const runs = Number(p.runs ?? "0");
    const total = Number(p.total ?? "0");
    const effort = item.key === "effortLevel";
    const value = effort ? (p.value ?? "") : modelLabel(p.value ?? "");
    if (total === 0) return t("in_usage_none", { days });
    if (runs === total) {
      return effort
        ? t("in_usage_all_effort", { days, total, value })
        : t("in_usage_all", { days, total, value });
    }
    return effort
      ? t("in_usage_some_effort", { days, runs, total, value })
      : t("in_usage_some", { days, runs, total, value });
  }
  return null;
}

/** The "Applies right away" line, or null. */
export function appliesLine(item: SetupItem): string | null {
  switch (item.applies) {
    case "now":
      return t("ap_now");
    case "new_session":
      return t("ap_new_session");
    case "restart":
      return t("ap_restart");
    case "reload_plugins":
      return t("ap_reload_plugins");
    case null:
      return null;
  }
}

/** True when a value the inspector shows is masked, so the page says why it hides values. */
export function hasMaskedValue(item: SetupItem): boolean {
  if (item.effective?.value?.masked === true) return true;
  if (item.sources.some((s) => s.value?.masked === true)) return true;
  const f = item.facts;
  if (f.hook?.command?.masked === true) return true;
  if (f.skill?.description?.masked === true) return true;
  if (f.agent?.fields.some((field) => field.value?.masked === true) === true) return true;
  const mcp = f.mcp;
  if (mcp !== null && mcp !== undefined) {
    if (mcp.command?.masked === true || mcp.url?.masked === true) return true;
    if (mcp.args.some((a) => a.masked)) return true;
    if (Object.values(mcp.headers).some((h) => h.masked)) return true;
  }
  return false;
}

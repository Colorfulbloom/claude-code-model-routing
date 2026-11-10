/*
 * The callout under an agent's header, "judge ran at medium, but its file sets high", with the
 * reason on the line below. The server judges the agent's own file as the Model check does over no
 * runs and sends the result as `check` (a reason code and its params), and the item's status is
 * that outcome. The sentence uses the Model check's own words (`findingFor`), so the Agents
 * inspector and the Model check never say two things. Only a lowered or overridden agent gets one,
 * because those are the two where what runs is not what the file sets.
 */
import type { ModelCheckRow, SetupItem } from "@/api/types";
import type { StatusWord } from "@/components/ListInspector/types";
import { findingFor, STATUS_WORDS } from "@/lib/model-check";
import { modelLabel } from "@/lib/models";
import { t } from "@/strings/t";

export interface AgentCheckView {
  status: StatusWord;
  /** "judge ran at medium, but its file sets high." */
  line: string;
  /** The reason, naming the cap or the layer that wins and the file lines. Null without one. */
  why: string | null;
}

type SetValue = ModelCheckRow["set"]["model"];

/** What the agent's front matter sets for a field, with its file and line. Null when it sets none. */
function setValue(item: SetupItem, name: "model" | "effort"): SetValue {
  const field = item.facts.agent?.fields.find((f) => f.name === name && !f.ignored);
  if (field?.value == null) return null;
  return {
    value: field.value.text,
    file: item.reason?.params.file ?? null,
    line: field.line,
    scope: "agent",
  };
}

/** The callout of an agent that doesn't run as its file sets it, or null. */
export function agentCheckView(item: SetupItem): AgentCheckView | null {
  const check = item.check ?? null;
  if (check === null || (item.status !== "lowered" && item.status !== "overridden")) return null;
  const params = check.params;
  const setting = params.setting === "model" ? "model" : "effort";
  const shown = (value: string | undefined): string =>
    value === undefined ? "" : setting === "model" ? modelLabel(value) : value;
  const agent = item.name;
  const ran = shown(params.expected);
  const value = shown(params.value);
  const line =
    setting === "model"
      ? t("mc_l_pin_overridden_model", { agent, ran, value })
      : t("mc_l_pin_overridden", { agent, ran, value });
  // The Model check's reason for the same code, over a row with no runs. What ran is what the
  // resolver says runs, so the reason never reads a run value.
  const row: ModelCheckRow = {
    agent,
    set: { model: setValue(item, "model"), effort: setValue(item, "effort") },
    ran: {
      model: setting === "model" ? (params.expected ?? null) : null,
      effort: setting === "effort" ? (params.expected ?? null) : null,
      mixed: false,
    },
    status: item.status,
    reason_code: check.code,
    params,
    runs: 0,
    mismatched_runs: 0,
    item_id: item.id,
  };
  const found = findingFor(row);
  return {
    status: { status: item.status, label: STATUS_WORDS[item.status] },
    line,
    why: found === null ? null : found.body,
  };
}

/*
 * The Model check card, from `model_check` in the timeline answer. Each row that is not in effect
 * becomes a finding with a status word, a title and a reason. The title and reason are picked by
 * `reason_code` and by which params the server sent, with a literal t() call per branch, so the
 * static key test sees every key (K-819f). Rows with no agent file group into one line, and the
 * rows in effect become one line that counts them.
 */
import type { ModelCheck, ModelCheckRow } from "@/api/types";
import type { SettingStatus } from "@/components/StatusChip/StatusChip";
import { modelLabel } from "@/lib/models";
import { t, tn } from "@/strings/t";

/** The seven status words, one literal t() call each so the static key test sees them (K-819f). */
export const STATUS_WORDS: Record<SettingStatus, string> = {
  in_effect: t("status_in_effect"),
  overridden: t("status_overridden"),
  ignored: t("status_ignored"),
  lowered: t("status_lowered"),
  invalid: t("status_invalid"),
  default: t("status_default"),
  unknown: t("status_unknown"),
};

export interface McFinding {
  id: string;
  status: SettingStatus | null;
  statusWord: string | null;
  title: string;
  body: string;
  /** The agent's name as the page says it, for the See why link's accessible name. */
  agent: string;
  /** The setup item of the agent this row is about, or null when the server named none. */
  itemId: string | null;
  /** The board's one-line sentence for the compact Review card, where a key covers the reason. */
  oneLine?: string;
}

/** What findingFor gives a row: the title, the reason and, for some reasons, one line. */
interface Found {
  title: string;
  body: string;
  oneLine?: string;
}

export interface McView {
  findings: McFinding[];
  /** "Agents with no agent file" in one line, or null. */
  noFileLine: string | null;
  /** The line under the findings that counts the agents in effect, or null. */
  okLine: string | null;
}

/** A model setting shows its name ("Opus 5.5"), an effort stays as sent. */
function shown(setting: string, value: string | undefined): string {
  if (value === undefined) return "";
  return setting === "model" ? modelLabel(value) : value;
}

function agentName(row: ModelCheckRow): string {
  return row.agent ?? t("tl_main");
}

const present = (value: string | undefined): value is string => value !== undefined && value !== "";

/** The title and reason for a row that is not in effect. Null for the rows that need none. */
export function findingFor(row: ModelCheckRow): Found | null {
  const p = row.params;
  const agent = agentName(row);
  const setting = p.setting ?? "effort";
  const isModel = setting === "model";
  const pair = isModel ? row.set.model : row.set.effort;
  const file = pair?.file ?? null;
  const line = pair?.line ?? null;
  const hasFile = file !== null && line !== null;
  const value = shown(setting, p.value);
  const expected = shown(setting, p.expected);
  const ran = shown(
    setting,
    isModel ? (row.ran.model ?? undefined) : (row.ran.effort ?? undefined),
  );
  const lineText = line === null ? "" : String(line);
  const fileText = file ?? "";
  switch (row.reason_code) {
    case "in_effect":
      return {
        title: t("mc_t_in_effect", { agent }),
        body: hasFile
          ? t("mc_r_in_effect", { setting, value, file: fileText, line: lineText })
          : t("mc_r_in_effect_nofile", { setting, value }),
      };
    case "default":
      return {
        title: t("mc_t_default", { agent, setting }),
        body: hasFile
          ? t("mc_r_default", { value, file: fileText, line: lineText })
          : t("mc_r_default_nofile", { setting, value }),
      };
    case "lowered_by_cap": {
      const title = isModel
        ? t("mc_t_lowered_by_cap_model", { agent, ran })
        : t("mc_t_lowered_by_cap", { agent, ran });
      const capFile = present(p.cap_file) && present(p.cap_line);
      const cap = { cap_file: p.cap_file ?? "", cap_line: p.cap_line ?? "" };
      const capKey = { cap_key: p.cap_key ?? "", cap_value: p.cap_value ?? "" };
      const base = { value, expected, setting };
      const body = hasFile
        ? capFile
          ? t("mc_r_lowered_by_cap", { ...base, ...cap, file: fileText, line: lineText })
          : t("mc_r_lowered_by_cap_nocapfile", {
              ...base,
              ...capKey,
              file: fileText,
              line: lineText,
            })
        : capFile
          ? t("mc_r_lowered_by_cap_nofile", { ...base, ...cap })
          : t("mc_r_lowered_by_cap_nofile_nocapfile", { ...base, ...capKey });
      const oneLine = isModel
        ? t("mc_l_lowered_by_cap_model", { agent, expected, setting, value })
        : t("mc_l_lowered_by_cap", { agent, expected, setting, value });
      return { title, body, oneLine };
    }
    case "lowered_ran_at_pin": {
      const title = isModel
        ? t("mc_t_lowered_ran_at_pin_model", { agent, ran })
        : t("mc_t_lowered_ran_at_pin", { agent, ran });
      const capFile = present(p.cap_file) && present(p.cap_line);
      const body = capFile
        ? t("mc_r_lowered_ran_at_pin", {
            setting,
            cap_file: p.cap_file ?? "",
            cap_line: p.cap_line ?? "",
            value,
            expected,
            ran,
          })
        : t("mc_r_lowered_ran_at_pin_nocapfile", {
            cap_key: p.cap_key ?? "",
            cap_value: p.cap_value ?? "",
            value,
            expected,
            ran,
          });
      return { title, body };
    }
    case "pin_overridden": {
      const byFile = present(p.by_file) && present(p.by_line);
      const title = t("mc_t_pin_overridden", { agent, setting, by_layer: p.by_layer ?? "" });
      let body: string;
      if (present(p.by_via) && !byFile) {
        body = t("mc_r_pin_overridden_via", { value, by_via: p.by_via ?? "", expected });
      } else if (hasFile && byFile) {
        body = t("mc_r_pin_overridden", {
          value,
          file: fileText,
          line: lineText,
          by_key: p.by_key ?? "",
          by_file: p.by_file ?? "",
          by_line: p.by_line ?? "",
          expected,
        });
      } else if (hasFile) {
        body = t("mc_r_pin_overridden_nobyfile", {
          value,
          file: fileText,
          line: lineText,
          by_key: p.by_key ?? "",
          by_layer: p.by_layer ?? "",
          expected,
        });
      } else if (byFile) {
        body = t("mc_r_pin_overridden_nofile", {
          value,
          by_key: p.by_key ?? "",
          by_file: p.by_file ?? "",
          by_line: p.by_line ?? "",
          expected,
        });
      } else {
        // Nothing names a file on either side, so the nearest reason is the one that says so.
        body = t("mc_r_expected_unknown_nofile", { setting, ran });
      }
      const oneLine = isModel
        ? t("mc_l_pin_overridden_model", { agent, ran, value })
        : t("mc_l_pin_overridden", { agent, ran, value });
      return { title, body, oneLine };
    }
    case "pin_ignored": {
      const body = hasFile
        ? present(p.expected)
          ? t("mc_r_pin_ignored_exp", { value, file: fileText, line: lineText, expected })
          : t("mc_r_pin_ignored", { value, file: fileText, line: lineText })
        : t("mc_r_pin_ignored_nofile", { value });
      return { title: t("mc_t_pin_ignored", { agent, setting }), body };
    }
    case "pin_invalid":
      return {
        title: t("mc_t_pin_invalid", { agent, setting }),
        body: hasFile
          ? t("mc_r_pin_invalid", { value, file: fileText, line: lineText, ran })
          : t("mc_r_pin_invalid_nofile", { value, ran }),
      };
    case "expected_unknown":
      return {
        title: t("mc_t_expected_unknown", { agent, setting }),
        body: hasFile
          ? t("mc_r_expected_unknown", { value, file: fileText, line: lineText, ran })
          : t("mc_r_expected_unknown_nofile", { setting, ran }),
      };
    case "unknown_status":
      return {
        title: t("mc_t_unknown_status", { agent }),
        body: t("mc_r_unknown_status", { setting, ran }),
      };
    case "ran_differs": {
      const ranList = (p.ran ?? "")
        .split(", ")
        .map((entry) => shown(setting, entry))
        .join(", ");
      return {
        title: isModel
          ? t("mc_t_ran_differs_model", { agent, ran: ranList, expected })
          : t("mc_t_ran_differs", { agent, ran: ranList, expected }),
        body: t("mc_r_ran_differs", { expected, ran: ranList }),
        oneLine: isModel
          ? t("mc_l_ran_differs_model", { agent, ran: ranList, expected })
          : t("mc_l_ran_differs", { agent, ran: ranList, expected }),
      };
    }
    case "ran_mixed": {
      const ranList = (p.ran ?? "")
        .split(", ")
        .map((entry) => shown(setting, entry))
        .join(", ");
      return {
        title: t("mc_t_ran_mixed", { agent, setting }),
        body: t("mc_r_ran_mixed", { expected, ran: ranList }),
        oneLine: isModel
          ? t("mc_l_ran_differs_model", { agent, ran: ranList, expected })
          : t("mc_l_ran_differs", { agent, ran: ranList, expected }),
      };
    }
    case "unnamed_agent":
      return { title: t("mc_t_unnamed_agent"), body: t("mc_r_unnamed_agent") };
    case "no_pin":
      return {
        title: t("mc_t_no_pin", { agent }),
        body: row.agent === null ? t("mc_r_no_pin_main") : t("mc_r_no_pin"),
      };
    case "no_agent_file":
      return { title: t("mc_t_no_agent_file", { agent }), body: t("mc_r_no_agent_file") };
    default:
      return null;
  }
}

/** Joins names with commas and "and" before the last. */
function nameList(names: readonly string[]): string {
  if (names.length < 2) return names.join("");
  return t("list_and", { list: names.slice(0, -1).join(", "), last: names.at(-1) ?? "" });
}

export function buildModelCheck(check: ModelCheck): McView {
  const findings: McFinding[] = [];
  const noFile: string[] = [];
  let inEffect = 0;
  for (const row of check.rows) {
    if (row.status === "in_effect") {
      inEffect += 1;
      continue;
    }
    if (row.status === null && row.reason_code === "no_agent_file") {
      noFile.push(agentName(row));
      continue;
    }
    const found = findingFor(row);
    if (found === null) continue;
    findings.push({
      id: `${row.agent ?? "main"}-${row.reason_code ?? "none"}`,
      status: row.status,
      statusWord: row.status === null ? null : STATUS_WORDS[row.status],
      agent: agentName(row),
      itemId: row.item_id ?? null,
      ...found,
    });
  }
  const okLine =
    inEffect === 0
      ? null
      : findings.length > 0 || noFile.length > 0
        ? tn("mc_ok", inEffect)
        : tn("mc_all_ok", inEffect);
  return {
    findings,
    noFileLine: noFile.length === 0 ? null : t("mc_nofile_list", { list: nameList(noFile) }),
    okLine,
  };
}

/**
 * The two numbers of "{k} of {n} agents didn't run as set", both from the rows that have a status.
 * A row with no status (no agent file, no pin, no agent type) was not checked, so it is in neither
 * number. A row in effect or at its default ran as set, so it is in n only. Task 21 item 11.
 */
export function checkCounts(check: ModelCheck): { checked: number; notAsSet: number } {
  const checked = check.rows.filter((row) => row.status !== null);
  const notAsSet = checked.filter((row) => row.status !== "in_effect" && row.status !== "default");
  return { checked: checked.length, notAsSet: notAsSet.length };
}

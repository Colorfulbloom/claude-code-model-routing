// What the Agents table and the Agent detail pin card say about an agent's pin check. Plain data, no DOM,
// so both pages share one set of words and the checks can call it on hand-built agents.
//
//   pinView(u, agent) -> { pill, pillLabel, note, pinnedText, pinnedNote, detailPinned, sentences, trailKey }
//
// u is the object fillUsage builds and agent is an AgentAgg from the payload. pill is the first argument of
// pinPill ("match", "overridden", "differs", "unknown") or null for no pill. pillLabel replaces the pill's
// word, and note is the line under it. sentences are plain strings, in model then effort order. trailKey is
// the setting key the trail link opens, or null when the agent has no pin.

import { t } from "./format.js";

// Worst first, as pincheck.STATES orders them.
const STATES = ["differs", "mixed", "overridden", "cannot_check", "matches_lowered", "matches"];

const endsWith = (text, tail) => typeof text === "string" && text.endsWith(tail);

// A value that may be missing: the word "Unknown" in place of null or undefined, so no slot prints "null".
const orUnknown = (value) => (value === null || value === undefined ? t("status_unknown") : value);

// What the winning entry says the value is. Lowered entries carry the value they become.
function expectedOf(e) {
  return e.status === "lowered" ? e.becomes : e.value;
}

// "effortLevel" for the effort row an agent shares with the settings files, else the entry's own key.
function settingName(e) {
  return e.via || (e.key === "effort" ? "effortLevel" : e.key);
}

// Where the winner lives: "path, line 3", "the shell", the path alone, or null.
function sourceOf(e) {
  if (e.file && e.line) return t("file_line", { path: e.file, line: e.line });
  if (e.layer === "env") return t("source_shell");
  if (e.file) return e.file;
  return null;
}

function capSource(cap) {
  if (!cap || !cap.file) return null;
  return cap.line ? t("file_line", { path: cap.file, line: cap.line }) : cap.file;
}

// The sentences for one setting. kind is "model" or "effort".
function settingSentences(u, kind, setting, pin) {
  const e = setting.expected;
  const modelWord = (value) => (value === null || value === undefined ? t("status_unknown") : u.model(value));
  const name = (value) => (kind === "model" ? modelWord(value) : orUnknown(value));
  const expected = name(expectedOf(e));
  const label = settingName(e);
  const source = sourceOf(e);
  const out = [];
  const lowered = e.status === "lowered";

  if (setting.state === "overridden" && !setting.runs_match_pin) {
    let usedReason = false;
    const isModel = kind === "model";
    if (e.file && e.line) {
      const slots = { setting: label, file: e.file, line: e.line };
      out.push(isModel
        ? t("pin_override_model_sentence_line", { ...slots, model: expected })
        : t("pin_override_sentence_line", { ...slots, effort: expected }));
    } else if (source) {
      const slots = { setting: label, file: source };
      out.push(isModel
        ? t("pin_override_model_sentence", { ...slots, model: expected })
        : t("pin_override_sentence", { ...slots, effort: expected }));
    } else if (e.reason) {
      out.push(e.reason);
      usedReason = true;
    }
    if (lowered && e.reason && !usedReason) out.push(e.reason);
  } else if (setting.state === "overridden") {
    const cap = setting.cap;
    if (lowered && endsWith(e.rule_id, "lowered-by-cap") && source) {
      out.push(t("pin_runs_match_cap_sentence", {
        setting: label, source, model: modelWord(cap ? cap.model : e.model), expected,
      }));
    } else if (source) {
      out.push(t("pin_runs_match_sentence", { setting: label, source, expected }));
    } else {
      out.push(t("pin_runs_match_sentence_no_source", { expected }));
    }
  } else if (setting.state === "matches" && setting.runs_match_pin) {
    const cap = setting.cap;
    const model = modelWord(cap ? cap.model : e.model);
    const from = capSource(cap);
    if (endsWith(e.rule_id, "unsupported-level")) {
      out.push(t("pin_runs_match_unsupported_sentence", { model, value: orUnknown(setting.pinned.value), expected }));
    } else if (cap && cap.file) {
      out.push(t("pin_runs_match_lowered_sentence", { model, expected, source: from }));
    } else {
      out.push(t("pin_runs_match_lowered_sentence_no_source", { model, expected }));
    }
  } else if (setting.state === "matches_lowered") {
    if (e.reason) out.push(e.reason);
  } else if (setting.state === "differs" || setting.state === "mixed") {
    // Only the model of an agent file gets a sentence. The Main session's words say "agent file".
    if (kind === "model" && pin.source === "agent_file") {
      const ran = (setting.ran || []).find((value) => value !== setting.pinned.id);
      const pinId = setting.pinned.id;
      if (ran !== undefined && ran !== null && pinId !== null && pinId !== undefined) {
        out.push(t("pin_model_differs_sentence", { ran_model: u.model(ran), pin_model: u.model(pinId) }));
      }
    }
  }
  return out;
}

function pillOf(pin) {
  switch (pin.state) {
    case "matches": case "matches_lowered": return { pill: "match", pillLabel: null };
    case "overridden": return { pill: "overridden", pillLabel: null };
    case "differs": case "mixed": {
      const partial = pin.state === "mixed" || pin.mismatched_runs < pin.total_runs;
      return {
        pill: "differs",
        pillLabel: partial ? t("differs_runs", { n: pin.mismatched_runs, m: pin.total_runs }) : null,
      };
    }
    case "cannot_check": return { pill: "unknown", pillLabel: null };
    default: return { pill: null, pillLabel: null };
  }
}

function noteOf(pin, settings) {
  if (pin.state === "matches_lowered") return t("p_lowered");
  if (pin.state === "overridden") {
    const lost = settings.filter(([, s]) => s.state === "overridden");
    if (lost.length && lost.every(([, s]) => s.runs_match_pin)) return t("pin_runs_match_note");
  }
  return null;
}

// The setting that gave the agent its state: the worse of the two, effort when they tie.
function trailKeyOf(pin) {
  const ordered = [["effort", pin.effort], ["model", pin.model]].filter(([, s]) => s);
  const scored = ordered.filter(([, s]) => s.state);
  let best = null;
  for (const entry of scored) {
    if (best === null || STATES.indexOf(entry[1].state) < STATES.indexOf(best[1].state)) best = entry;
  }
  const pick = best || ordered[0];
  if (!pick) return null;
  const [kind, setting] = pick;
  return (setting.expected && setting.expected.key) || kind;
}

export function pinView(u, agent) {
  const pin = agent.pin;
  const none = { pill: null, pillLabel: null, note: null, pinnedText: "", pinnedNote: null, detailPinned: null, sentences: [], trailKey: null };
  if (!pin) {
    return {
      ...none,
      pinnedText: t("no_pin"), pinnedNote: t("no_pin_note"), sentences: [t("no_pin_sentence")],
    };
  }

  const settings = [["model", pin.model], ["effort", pin.effort]].filter(([, s]) => s);
  // A pin the dashboard cannot name gives no model word, and an effort pin with no value reads "Unknown".
  const modelId = pin.model ? pin.model.pinned.id : null;
  const modelKnown = modelId !== null && modelId !== undefined;
  const modelName = modelKnown ? u.model(modelId) : null;
  const effort = pin.effort ? orUnknown(pin.effort.pinned.value) : null;
  const out = { ...none, ...pillOf(pin) };
  out.pinnedNote = pin.source === "settings" ? t("pin_main_note") : null;
  out.note = noteOf(pin, settings);
  out.trailKey = trailKeyOf(pin);

  if ((pin.pinned === "both" || pin.pinned === "model_only") && !modelKnown) {
    out.pinnedText = out.detailPinned = t("pin_unknown");
  } else if (pin.pinned === "both") {
    out.pinnedText = modelName + ", " + effort;
    out.detailPinned = t("pinned_to", { model: modelName, effort });
  } else if (pin.pinned === "model_only") {
    out.pinnedText = out.detailPinned = t("pinned_model_only", { model: modelName });
  } else if (pin.pinned === "effort_only") {
    out.pinnedText = out.detailPinned = t("pinned_effort_only", { effort });
  } else if (pin.source === "settings") {
    out.pinnedText = out.detailPinned = t("pin_unknown");
  } else {
    out.pinnedText = t("no_pin");
  }

  let cannot = false;
  for (const [kind, setting] of settings) {
    if (setting.state === "cannot_check") {
      if (!cannot) out.sentences.push(t("pin_cannot_check_sentence"));
      cannot = true;
    } else {
      out.sentences.push(...settingSentences(u, kind, setting, pin));
    }
  }
  return out;
}

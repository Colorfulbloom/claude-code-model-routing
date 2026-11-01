// Settings: the main session's model, effort, effort cap, compact window and cache lifetime, as a Stat band of
// cells (pages/band.js) over two panes, the open setting's body and a rail that says why the value is what it is.
// Round 6 design, board a-rest. app.css holds every class used here (section
// "Settings and trail").
//
// The helpers below the page are shared. pages/trail.js and pages/band.js import them, so the trail and the band
// word a value, a source and a layer the same way. Every value, path and reason comes from the server as data, so
// it goes in as text through h.js and renderText, never as markup.

import { h, clear } from "../h.js";
import { t, renderText } from "../format.js";
import { ALL_KEY, MAIN_KEY, BAND_SETTINGS } from "../router.js";
import { pageHead, emptyState, projectPickerEmpty } from "../components.js";
import { bandFor, refitBand, setNotSaved } from "./band.js";
import { readFrame } from "./read_frame.js";
import * as editCard from "../edit_card.js";
// band.js imports from this file and this file imports from band.js: neither may use the other's bindings at the top level.

// The five settings of the band, in the saved order of its cells: the row key and the label of each. The keys are
// the same as BAND_SETTINGS in router.js, which validates ?setting=, and a check holds the two together.
export const TILES = [
  { key: "model", label: () => t("f_model") },
  { key: "effortLevel", label: () => t("f_effort") },
  { key: "maxEffortLevel", label: () => t("cap") },
  { key: "autoCompactWindow", label: () => t("f_compact") },
  { key: "promptCacheTtl", label: () => t("f_cache") },
];

// The settings the Settings page can change in Stage 1. Any other setting rests in the read-only frame
// (pages/read_frame.js). A ticket that makes another setting editable adds its key here.
export const EDITABLE_SETTINGS = ["effortLevel"];

// The setting that is open when the address names none.
export const DEFAULT_SETTING = "effortLevel";

const HIDDEN = "hidden"; // what collect.py leaves in place of a value that looks like a secret

// The two rules that mark the user file's top-level effortLevel Unknown because the model is not known. The
// entry keeps the file's value for the reason text, but the value may not apply, so no screen shows it as the answer.
const VALUE_NOT_SHOWN = ["effort-level-user-settings-model-unknown", "agent-effort-user-settings-model-unknown"];

// True for an Unknown entry of those rules: its value stays in the entry but is not shown as a headline.
export function valueNotShown(entry) {
  return entry.status === "unknown" && Array.isArray(entry.rule_ids)
    && entry.rule_ids.some((id) => VALUE_NOT_SHOWN.includes(id));
}

// The value of an entry as plain text. plain true is the Settings band, where a model shows its display
// name alone. A null value is "" here, and a model row shows its name and id otherwise.
export function valueString(entry, payload, plain = false) {
  const value = entry.value;
  if (value === null || value === undefined || valueNotShown(entry)) return "";
  if (value === HIDDEN) return t("hidden");
  if (value === "") return t("value_empty");
  if (entry.key === "model") {
    const models = (payload && payload.models) || {};
    if (Object.prototype.hasOwnProperty.call(models, value)) {
      return plain ? models[value] : t("model_fmt", { name: models[value], id: value });
    }
    return t("model_not_listed", { name: value });
  }
  return String(value);
}

// What shows for a value: text, or a span that explains a hidden value. Null shows nothing.
export function valueText(entry, payload, plain = false) {
  if (entry.value === null || entry.value === undefined || valueNotShown(entry)) return null;
  const text = valueString(entry, payload, plain);
  if (entry.value === HIDDEN) return h("span", { title: t("hidden_desc") }, text);
  return text;
}

// Where an entry comes from, as the screen words it. A default that names a variable in via, such as
// ENABLE_PROMPT_CACHING_1H, takes its source from the winner of that variable's own row (env.<variable>),
// because the value came through the variable. Without such a row it reads as the default. With short true,
// an entry with a via reads as the file and line, or Shell, as it does without one (the band and the summaries).
export function sourceText(entry, payload, short = false) {
  const file = entry.file;
  if (file === null || file === undefined) {
    const variable = entry.via ? winnerOf(payload, "env." + entry.via) : null;
    if (variable && variable.file !== null && variable.file !== undefined) {
      return sourceText({ ...entry, file: variable.file, line: variable.line }, payload, short);
    }
    return t("default_src");
  }
  const isShell = file === payload.shell_label;
  if (entry.via && !short && isShell) return t("set_by_shell", { variable: entry.via });
  if (entry.via && !short) return t("set_by_block", { variable: entry.via, path: file, line: entry.line });
  if (isShell) return t("shell");
  if (entry.line !== undefined && entry.line !== null) return t("file_line", { path: file, line: entry.line });
  return file;
}

const LAYERS = ["user", "project", "local", "managed"];

// The layer of an entry in words. An entry from an env block has layer env, so with a payload the layer of the
// file it was read from stands in. Any other layer, such as default, gives "" and the caller leaves it out.
export function layerText(entry, payload = null) {
  if (LAYERS.includes(entry.layer)) return t("layer_" + entry.layer);
  const file = ((payload && payload.files) || []).find((f) => f.path === entry.file);
  return file && LAYERS.includes(file.layer) ? t("layer_" + file.layer) : "";
}

// The name of a setting as the screen writes it, for a row name. An unknown key shows as written.
export function settingLabel(key) {
  switch (key) {
    case "model": return t("f_model");
    case "effortLevel": case "effort": return t("f_effort");
    case "promptCacheTtl": case "subagentPromptCacheTtl": return t("f_cache");
    case "autoCompactWindow": return t("f_compact");
    case "maxEffortLevel": return t("cap");
    case "agentFile": return t("f_agentfile");
    case "settingsFile": return t("f_settingsfile");
    case "rulesFile": return t("f_rulesfile");
    default: return String(key);
  }
}

// The name of a setting in lower case, for a title. An unknown key shows as written.
export function settingWord(key) {
  const label = settingLabel(key);
  return label === String(key) ? label : label.toLowerCase();
}

// The first entry with this scope and key is the winner of the row.
export function winnerOf(payload, key, scope = "main") {
  return (payload.entries || []).find((e) => e.scope === scope && e.key === key) || null;
}

// True when the project's folder is gone and no entry resolved. The implicit current project keeps the
// missing_folder state but still resolves, so entries decide.
export function isMissingFolder(payload) {
  return payload.state === "missing_folder" && !(payload.entries || []).length;
}

// The "Folder not found" card, shared by Settings, the trail and Needs attention.
export function missingFolderState(ctx, payload) {
  return emptyState(t("es_missing_h"), t("es_missing_t", {
    name: ctx.project.name, path: payload.path_display, config_file: payload.config_file_display,
  }));
}

// The messages for a project or a config folder that is missing something, drawn into container. Returns the
// settings payload when there is one to show, else null (All projects, no answer yet, a refused answer and a
// missing folder all return null). Shared with the trail, which draws its own head and its panel after this.
export function renderGuards(container, ctx) {
  if (ctx.project.key === ALL_KEY) {
    container.appendChild(projectPickerEmpty());
    return null;
  }
  const res = ctx.data.settings;
  if (!res || !res.ok || !res.data) return null;
  const payload = res.data;
  if (isMissingFolder(payload)) {
    container.appendChild(missingFolderState(ctx, payload));
    return null;
  }
  if (payload.state === "no_claude_folder") {
    container.appendChild(emptyState(t("es_noclaude_h"), t("es_noclaude_t", {
      path: payload.path_display, config_dir: payload.config_dir_display,
    })));
  }
  if (payload.no_user_settings) {
    container.appendChild(emptyState(t("es_nouser_h"), t("es_nouser_t", { config_dir: payload.config_dir_display })));
  }
  return payload;
}

// Depth-first search through childNodes, which a real element and the test DOM both have.
function findNode(node, test) {
  if (node.nodeType === 1 && test(node)) return node;
  for (const child of Array.from(node.childNodes || [])) {
    const found = findNode(child, test);
    if (found) return found;
  }
  return null;
}

// The trail sets this when Escape closes it. The next Settings render takes it and moves focus.
let pendingReturn = null;

// Remember where focus goes when the Settings page is drawn next: the cell of a main session row, else the
// page heading, because a trail opened by route may have no cell behind it.
export function returnFocusTo(agent, setting) {
  pendingReturn = { agent, setting };
}

function takeReturnFocus(root) {
  const { agent, setting } = pendingReturn;
  pendingReturn = null;
  const cell = agent === MAIN_KEY
    ? findNode(root, (n) => n.getAttribute("data-setting") === setting) : null;
  if (cell) {
    cell.focus();
    return;
  }
  const heading = findNode(root, (n) => String(n.tagName).toLowerCase() === "h1");
  if (heading) {
    heading.setAttribute("tabindex", "-1");
    heading.focus();
  }
}

// The cell that is open: ?setting= when the band has it, else Effort.
export function selectedSetting(ctx) {
  const wanted = ctx.route && ctx.route.query ? ctx.route.query.setting : null;
  return BAND_SETTINGS.includes(wanted) ? wanted : DEFAULT_SETTING;
}

// The rail at rest, whichever setting is open: why the value is what it is, in the winner's own reason, and a link
// to the trail of the row. A setting the payload has no entry for has the heading alone. notes is a list of lines
// that sit under the reason (the editing-is-off line, a lock), each a string or nodes, or null for none.
function railBody(ctx, payload, key, notes = null) {
  const winner = winnerOf(payload, key);
  return h("div", { class: "s4-rb" },
    h("h2", { class: "s4-rh" }, t("why_h")),
    winner ? h("p", { class: "s4-p" }, renderText(winner.reason || "")) : null,
    (notes || []).map((line) => h("p", { class: "s4-note" }, line)),
    winner ? h("a", { class: "s4-link", href: ctx.hashFor("trail", { agent: MAIN_KEY, setting: key }, { setting: null }) },
      t("why_rules")) : null);
}

// The setting whose cell or list row has focus, or null. A redraw puts focus back on that setting's cell.
function focusedSetting(root) {
  if (!root.contains(document.activeElement)) return null;
  for (let node = document.activeElement; node && node !== root; node = node.parentNode) {
    if (node.getAttribute && node.getAttribute("data-setting")) return node.getAttribute("data-setting");
  }
  return null;
}

export function render(root, ctx) {
  const keep = focusedSetting(root);
  const editKey = editCard.focusKey(); // an edit control that holds focus keeps it across this draw
  clear(root);
  const page = h("div", { class: "s4 s4-c" });
  root.appendChild(page);
  page.appendChild(h("div", { class: "s4-chead" }, pageHead({ title: t("nav_settings"), intro: t("intro_settings") })));
  const messages = h("div", { class: "s5-msgs" });
  const payload = renderGuards(messages, ctx);
  if (messages.firstChild) page.appendChild(messages);
  if (payload) {
    const selected = selectedSetting(ctx);
    page.classList.add("s5-lock");
    // The edit card hands back the Effort frame, the rail and the foot, drawn again without a page render when a level
    // or a row is picked, and the Set of settings with a change waiting on Save, for the band. A setting that cannot be
    // edited fills the body with the read-only frame, and its rail is the rail at rest unless a change is in progress.
    // With no edit session the page draws as before.
    const edit = editCard.begin(ctx, {
      restRail: (notes) => railBody(ctx, payload, selected, notes), selected, onNotSaved: setNotSaved,
    });
    page.appendChild(bandFor(ctx, payload, selected, edit.notSaved));
    const body = h("div", { class: "s4-body", "data-slot": "body" },
      EDITABLE_SETTINGS.includes(selected) && edit.body ? edit.body : readFrame(ctx, payload, selected));
    const foot = h("div", { class: "s4-rf s5-rf", "data-slot": "foot" }, edit.foot);
    page.appendChild(h("div", { class: "s5-w" }, body,
      h("aside", { class: "s4-rail" }, edit.rail || railBody(ctx, payload, selected), foot)));
    refitBand();
    edit.done(root, editKey);
  }
  // The Settings section also draws when a payload lands, so only the Settings route takes the record.
  if (ctx.route.name === "settings" && pendingReturn) takeReturnFocus(root);
  else if (keep) {
    const cell = findNode(root, (n) => n.getAttribute("data-setting") === keep);
    if (cell) cell.focus();
  }
}

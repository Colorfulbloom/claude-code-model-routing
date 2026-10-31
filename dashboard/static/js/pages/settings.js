// Settings: the main session's model, effort, cache lifetime and compact window, one tile each, with
// the value, its status and where it comes from. Screen 07 in docs/design/usage-stack/a-usage is the
// reference, and app.css already holds every class used here (section "Settings and trail").
//
// The helpers at the top are shared. pages/trail.js imports them, so the trail words a value, a source
// and a layer the same way the tiles do. Every value, path and reason comes from the server as data, so
// it goes in as text through h.js and renderText, never as markup.

import { h, clear } from "../h.js";
import { t, renderText } from "../format.js";
import { ALL_KEY, MAIN_KEY } from "../router.js";
import { pageHead, chip, emptyState, projectPickerEmpty } from "../components.js";

// The four tiles, in the order of the screen: the row key and the label of each.
export const TILES = [
  { key: "model", label: () => t("f_model") },
  { key: "effortLevel", label: () => t("f_effort") },
  { key: "promptCacheTtl", label: () => t("f_cache") },
  { key: "autoCompactWindow", label: () => t("f_compact") },
];

const HIDDEN = "hidden"; // what collect.py leaves in place of a value that looks like a secret

// The value of an entry as plain text. plain true is the Settings tile, where a model shows its display
// name alone. A null value is "" here, and a model row shows its name and id otherwise.
export function valueString(entry, payload, plain = false) {
  const value = entry.value;
  if (value === null || value === undefined) return "";
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
  if (entry.value === null || entry.value === undefined) return null;
  const text = valueString(entry, payload, plain);
  if (entry.value === HIDDEN) return h("span", { title: t("hidden_desc") }, text);
  return text;
}

// Where an entry comes from, as the screen words it. A default that names a variable in via, such as
// ENABLE_PROMPT_CACHING_1H, takes its source from the winner of that variable's own row (env.<variable>),
// because the value came through the variable. Without such a row it reads as the default. With short true,
// an entry with a via reads as the file and line, or Shell, as it does without one (the tile and the summaries).
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

function tile(ctx, payload, spec, entry, active) {
  const label = spec.label();
  const plainValue = valueString(entry, payload, true);
  const word = t("status_" + entry.status);
  const value = valueText(entry, payload, true);
  const hasBecomes = entry.becomes !== undefined && entry.becomes !== null;
  const aria = [label, plainValue, word].filter(Boolean).join(", ") + ". " + t("cell_desc");
  return h("a", {
    class: "tl",
    "data-setting": spec.key,
    href: ctx.hashFor("trail", { agent: MAIN_KEY, setting: spec.key }),
    "aria-label": aria,
    "aria-current": active ? "true" : null,
  },
  h("div", { class: "tl-top" }, h("span", { class: "tl-l" }, label), chip(entry.status)),
  h("div", { class: "tl-mid" },
    value === null ? null : h("span", { class: "tl-v" }, value),
    hasBecomes ? h("span", { class: "runs" }, t("runs_as_cell", { becomes: entry.becomes })) : null),
  h("div", { class: "tl-src" }, renderText(sourceText(entry, payload, true))),
  entry.status === "unknown" && entry.reason ? h("p", { class: "en-note" }, renderText(entry.reason)) : null);
}

// The four tiles of the main session. activeSetting is the row the trail shows, if any.
export function tilesFor(ctx, payload, activeSetting = null) {
  const tiles = h("div", { class: "tiles" });
  for (const spec of TILES) {
    const entry = winnerOf(payload, spec.key);
    if (entry) tiles.appendChild(tile(ctx, payload, spec, entry, spec.key === activeSetting));
  }
  return tiles;
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

// The page head, the messages for a project or a config folder that is missing something, and the tiles.
// Shared with the trail, which adds its panel after the tiles. The tiles come back as the last node.
export function renderSettingsBody(root, ctx, activeSetting = null) {
  root.appendChild(pageHead({ title: t("nav_settings"), intro: t("intro_settings") }));
  if (ctx.project.key === ALL_KEY) {
    root.appendChild(projectPickerEmpty());
    return null;
  }
  const res = ctx.data.settings;
  if (!res || !res.ok || !res.data) return null;
  const payload = res.data;
  if (isMissingFolder(payload)) {
    root.appendChild(missingFolderState(ctx, payload));
    return null;
  }
  if (payload.state === "no_claude_folder") {
    root.appendChild(emptyState(t("es_noclaude_h"), t("es_noclaude_t", {
      path: payload.path_display, config_dir: payload.config_dir_display,
    })));
  }
  if (payload.no_user_settings) {
    root.appendChild(emptyState(t("es_nouser_h"), t("es_nouser_t", { config_dir: payload.config_dir_display })));
  }
  root.appendChild(tilesFor(ctx, payload, activeSetting));
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

// Remember where focus goes when the Settings page is drawn next: the tile of a main session row, else the
// page heading, because a trail opened by route may have no cell behind it.
export function returnFocusTo(agent, setting) {
  pendingReturn = { agent, setting };
}

function takeReturnFocus(root) {
  const { agent, setting } = pendingReturn;
  pendingReturn = null;
  const tile = agent === MAIN_KEY
    ? findNode(root, (n) => n.getAttribute("data-setting") === setting) : null;
  if (tile) {
    tile.focus();
    return;
  }
  const heading = findNode(root, (n) => String(n.tagName).toLowerCase() === "h1");
  if (heading) {
    heading.setAttribute("tabindex", "-1");
    heading.focus();
  }
}

export function render(root, ctx) {
  clear(root);
  renderSettingsBody(root, ctx);
  // Every page draws on every route change, so only the Settings route takes the record.
  if (ctx.route.name === "settings" && pendingReturn) takeReturnFocus(root);
}

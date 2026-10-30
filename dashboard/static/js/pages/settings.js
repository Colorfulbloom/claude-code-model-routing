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
function valueString(entry, payload, plain = false) {
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

// Where an entry comes from, as the screen words it.
export function sourceText(entry, payload) {
  const file = entry.file;
  if (file === null || file === undefined) return t("default_src");
  const isShell = file === payload.shell_label;
  if (entry.via && isShell) return t("set_by_shell", { variable: entry.via });
  if (entry.via) return t("set_by_block", { variable: entry.via, path: file, line: entry.line });
  if (isShell) return t("shell");
  if (entry.line !== undefined && entry.line !== null) return t("file_line", { path: file, line: entry.line });
  return file;
}

const LAYERS = ["user", "project", "local", "managed"];

// The layer of an entry in words. Any other layer, such as default, gives "" and the caller leaves it out.
export function layerText(entry) {
  return LAYERS.includes(entry.layer) ? t("layer_" + entry.layer) : "";
}

// The name of a setting in lower case, for a title. An unknown key shows as written.
export function settingWord(key) {
  switch (key) {
    case "model": return t("f_model").toLowerCase();
    case "effortLevel": case "effort": return t("f_effort").toLowerCase();
    case "promptCacheTtl": case "subagentPromptCacheTtl": return t("f_cache").toLowerCase();
    case "autoCompactWindow": return t("f_compact").toLowerCase();
    case "maxEffortLevel": return t("cap").toLowerCase();
    case "agentFile": return t("f_agentfile").toLowerCase();
    case "settingsFile": return t("f_settingsfile").toLowerCase();
    case "rulesFile": return t("f_rulesfile").toLowerCase();
    default: return String(key);
  }
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
  h("div", { class: "tl-src" }, renderText(sourceText(entry, payload))),
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
  // The implicit current project keeps this state but still resolves, so entries decide the message.
  if (payload.state === "missing_folder" && !(payload.entries || []).length) {
    root.appendChild(emptyState(t("es_missing_h"), t("es_missing_t", {
      name: ctx.project.name, path: payload.path_display, config_file: payload.config_file_display,
    })));
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

export function render(root, ctx) {
  clear(root);
  renderSettingsBody(root, ctx);
}

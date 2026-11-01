// The "Where it's set" rows of the Settings page, shared by the read-only frame (pages/read_frame.js) and the
// Effort body. Round 6 design, board a-shell, classes s6-lvs, s6-rows and s6-r (app.css section "Settings and
// trail"). The row lookups here are also the trail's.
//
// Every value, path and name comes from the server as data, so it goes in as text through h.js, never as markup.

import { h } from "../h.js";
import { t } from "../format.js";
import { chip } from "../components.js";
import { valueText, sourceText, layerText, winnerOf } from "./settings.js";

// The short place name of a layer, or "" for a layer without one.
function layerPlace(layer) {
  switch (layer) {
    case "local": return t("place_local");
    case "project": return t("place_project");
    case "user": return t("place_user");
    default: return "";
  }
}

// ---------------------------------------------------------------- rows

export function rowFor(payload, agent, setting) {
  return (payload.rows || []).find((r) => r.agent === agent && r.setting === setting) || null;
}

export function entriesOf(payload, row) {
  return row.entries.map((i) => payload.entries[i]).filter(Boolean);
}

// True when the value was read from the shell: its file is the shell, or it is a default that came through a
// variable whose own row is a shell value (see sourceText).
export function fromShell(entry, payload) {
  const file = entry.file === null || entry.file === undefined || entry.file === ""
    ? (entry.via ? (winnerOf(payload, "env." + entry.via) || {}).file : null)
    : entry.file;
  return file !== null && file !== undefined && file === payload.shell_label;
}

// ---------------------------------------------------------------- words

// The layer an entry sits in: its own, or for an env block entry the layer of the file it was read from.
function layerOf(entry, payload) {
  if (layerPlace(entry.layer) || entry.layer === "managed") return entry.layer;
  const file = ((payload && payload.files) || []).find((f) => f.path === entry.file);
  return file ? file.layer : entry.layer;
}

// Where an entry sits, as the rows name it: "This project, just you", "Your shell", "Claude Code's default". Managed
// settings, a flag and any other layer keep the words the rest of the page uses.
export function placeName(entry, payload) {
  if (fromShell(entry, payload)) return t("place_shell");
  const layer = layerOf(entry, payload);
  const place = layerPlace(layer);
  if (place) return place;
  if (entry.layer === "default") return t("place_default");
  return layerText(entry, payload) || sourceText(entry, payload, true);
}

// The file of a row as the design writes it: the file name for the project files, the last two parts for the
// user file, the display path unchanged for anything else.
export function shortFile(layer, display) {
  const text = String(display);
  const parts = text.split("/").filter(Boolean);
  if (layer === "local" || layer === "project") return parts.length ? parts[parts.length - 1] : text;
  if (layer === "user") return parts.length > 1 ? parts.slice(-2).join("/") : text;
  return text;
}

// The small line under a row's name: the variable for a shell value, else the short file and its line.
function fileText(entry, payload) {
  if (fromShell(entry, payload)) return entry.via || null;
  if (entry.file === null || entry.file === undefined || entry.file === "") return null;
  const name = shortFile(layerOf(entry, payload), entry.file);
  return entry.line !== undefined && entry.line !== null ? t("file_line", { path: name, line: entry.line }) : name;
}

// ---------------------------------------------------------------- nodes

// One row: who sets it (name, and the file when set), the value with its status chip or the none word, and a
// third cell for an action, empty at rest. name, file and none are text. Live rows (the Effort body once a level is
// chosen) are labels around a hidden radio: radio is { name, value, checked, disabled, focus, onChange }, pick marks
// the picked row and no a row that can't be picked.
export function rowNode({ name, file = null, value = null, none = null, status = null, act = null, cls = null, radio = null, pick = false, no = false }) {
  const cells = [
    h("span", { class: "s6-who" },
      h("span", { class: "s4-ln" }, name),
      file ? h("span", { class: "s4-f" }, file) : null),
    h("span", { class: "s4-lvv" },
      none !== null && none !== undefined
        ? h("span", { class: "s4-none" }, none)
        : [h("span", { class: "s4-v" }, value), status ? h("span", { class: "s4-st" }, chip(status)) : null]),
    act ? h("span", { class: "s6-act" }, act) : h("span"),
  ];
  if (!radio) return h("div", { class: ["s6-r", cls] }, cells);
  return h("label", { class: ["s6-r", pick && "is-pick", no && "is-no", cls] },
    h("input", {
      class: "sr", type: "radio", name: radio.name, value: radio.value, checked: Boolean(radio.checked),
      disabled: Boolean(radio.disabled), "data-edit-focus": radio.focus || null,
      on: radio.onChange ? { change: radio.onChange } : null,
    }),
    cells);
}

// The row of one entry of the payload. An entry with no value to show reads as none.
export function entryRow(entry, payload, cls = null) {
  const value = valueText(entry, payload, true);
  return rowNode({
    name: placeName(entry, payload),
    file: fileText(entry, payload),
    value,
    none: value === null ? t("band_not_known") : null,
    status: value === null ? null : entry.status,
    cls,
  });
}

// The list: heading, the bordered rows, the tail (rows outside the box, such as Claude Code's default) and, only
// when asked, the line about what can beat these files. live makes the box a radio group of the file rows.
export function whereList(heading, rowNodes, tailNodes = [], beyond = false, live = false) {
  return h("div", { class: "s6-lvs" },
    h("p", { class: "s4-lab" }, heading),
    h("div", { class: ["s6-rows", live && "is-live"], role: live ? "radiogroup" : "group", "aria-label": heading }, rowNodes),
    tailNodes,
    beyond ? h("p", { class: "s4-beyond" }, t("where_beyond")) : null);
}

// The read-only frame of the Settings page: the body of a setting that cannot be edited yet (Model, Effort cap,
// Compact window, Cache lifetime, Extended thinking, Fallback models, Allowed models). The lock line, the value,
// and where it is set. No Run at control and no radio, and never the editing-is-off or locked lines, because those
// promise that --allow-edits would make it editable.
// Round 6 design, board a-shell (lock line and rows) and round 5 a12-see (the value). The rows are pages/where.js.
//
// Every value comes from the server as data, so it goes in as text through h.js, never as markup.

import { h } from "../h.js";
import { t } from "../format.js";
import { chip } from "../components.js";
import { lockIcon } from "../edit_ui.js";
import { MAIN_KEY } from "../router.js";
import { settingLabel, winnerOf, valueNotShown } from "./settings.js";
import { valueFor } from "./band.js";
import { rowFor, entriesOf, entryRow, whereList } from "./where.js";

// The model names under the value of a list setting: the merged list that runs (allowed models, or a Lowered
// fallback chain), else the list itself. Null when there is nothing to name, and for an entry whose value is not shown
// (a list of the wrong type, Unknown), because its names are not the answer. Names stay as written, because the rows name real values.
function namesOf(winner, key) {
  if (!winner || (key !== "fallbackModel" && key !== "availableModels") || valueNotShown(winner)) return null;
  const list = Array.isArray(winner.merged) ? winner.merged : winner.value;
  return Array.isArray(list) && list.length ? list.join(", ") : null;
}

// The value of the frame: label, then the value and its status, as the band cell words them. A list setting adds
// one line that names its models.
function valueBlock(payload, key) {
  const winner = winnerOf(payload, key);
  const value = valueFor(key, winner, payload);
  const names = namesOf(winner, key);
  return h("div", { class: "s4-run" },
    h("p", { class: "s4-lab" }, settingLabel(key)),
    h("p", { class: "s4-lvv" },
      h("span", { class: "s4-v" }, value.node),
      winner ? h("span", { class: "s4-st" }, chip(winner.status)) : null),
    names ? h("p", { class: "s4-names" }, names) : null);
}

// Where it is set: one row for each entry of the main session's row, top wins. A default goes below the box.
function whereBlock(payload, key) {
  const row = rowFor(payload, MAIN_KEY, key);
  const entries = row ? entriesOf(payload, row) : [];
  const rows = entries.filter((e) => e.layer !== "default").map((e) => entryRow(e, payload));
  const tail = entries.filter((e) => e.layer === "default").map((e) => entryRow(e, payload, "s6-def"));
  // Allowed models combine the lists of the files when no managed list applies, so the heading says so.
  const merges = key === "availableModels" && entries.length > 0 && entries[0].layer !== "managed"
    && entries[0].layer !== "default";
  return whereList(merges ? t("where_rest_merged") : t("where_rest"), rows, tail);
}

// The nodes for the body slot of a setting that is not editable.
export function readFrame(ctx, payload, key) {
  return [
    h("p", { class: "s4-lock" }, lockIcon(), h("span", null, t("ro_lock"))),
    valueBlock(payload, key),
    whereBlock(payload, key),
  ];
}

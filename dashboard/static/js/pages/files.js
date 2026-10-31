// Installed files: each file this repo installs into the Claude Code config folder, and whether the copy there
// still matches. Screen 09 in docs/design/usage-stack/a-usage is the reference, and app.css already holds every
// class used here (section "Installed files"). The server compares the files (api_settings.files), and the page
// words each state with its mark glyph and its word, never a hue alone. The page is the same for every project,
// and All projects too. Every path comes from the server as data, so it goes in as text through h.js, never as
// markup.

import { h, clear } from "../h.js";
import { t } from "../format.js";
import { pageHead, card, table3 } from "../components.js";

// The word and the next step of each state. Each key is written out, so the strings test sees every call.
function stateWords(state) {
  switch (state) {
    case "match": return { word: t("f_matches"), next: t("f_action_match") };
    case "differs": return { word: t("f_differs"), next: t("f_action_differs") };
    case "missing": return { word: t("f_missing"), next: t("f_action_missing") };
    default: return null;
  }
}

function stateCell(state, word) {
  return h("span", { class: ["st", "st-" + state] }, h("i", { class: "mk", "aria-hidden": "true" }), word);
}

// One table row, or null for a state this page has no word for.
function rowFor(file) {
  const words = stateWords(file.state);
  if (!words) return null;
  return [h("span", { class: "mono" }, file.path), stateCell(file.state, words.word), words.next];
}

export function render(root, ctx) {
  clear(root);
  root.appendChild(pageHead({ title: t("nav_files"), intro: t("intro_files") }));
  const res = ctx.data && ctx.data.files;
  const payload = res && res.ok && res.data ? res.data : null;
  if (!payload) return;
  const rows = (Array.isArray(payload.files) ? payload.files : []).map(rowFor).filter(Boolean);
  root.appendChild(card({
    title: t("c_files_table"), icon: "files",
    body: table3([t("h_file"), t("h_state"), t("h_next")], rows),
  }));
  root.appendChild(h("p", { class: "foot" }, t("files_foot")));
}

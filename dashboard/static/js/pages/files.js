// Installed files: each file this repo installs into the Claude Code config folder, and whether the copy there
// still matches. Screen 09 in docs/design/usage-stack/a-usage is the reference, and app.css already holds every
// class used here (section "Installed files"). The server compares the files (api_settings.files), and the page
// words each state with its mark glyph and its word, never a hue alone. The page is the same for every project,
// and All projects too. Every path comes from the server as data, so it goes in as text through h.js, never as
// markup.

import { h, clear } from "../h.js";
import { t, renderText } from "../format.js";
import { pageHead, card, table3, emptyState } from "../components.js";

// The word and the next step of each state. Each key is written out, so the strings test sees every call.
// A row with caution is one the installer would put back to the repo's default model and effort, so the
// next step is to pick again, not to run it again.
function stateWords(state, caution) {
  switch (state) {
    case "match": return { word: t("f_matches"), next: t("f_action_match") };
    case "differs": return { word: t("f_differs"), next: caution ? t("f_action_differs_choices") : t("f_action_differs") };
    case "missing": return { word: t("f_missing"), next: caution ? t("f_action_differs_choices") : t("f_action_missing") };
    default: return null;
  }
}

function stateCell(state, word) {
  return h("span", { class: ["st", "st-" + state] }, h("i", { class: "mk", "aria-hidden": "true" }), word);
}

// One table row, or null for a state this page has no word for.
function rowFor(file) {
  const words = stateWords(file.state, file.caution === true);
  if (!words) return null;
  return [h("span", { class: "mono" }, file.path), stateCell(file.state, words.word), renderText(words.next)];
}

// The notice about the saved choices file, or null when the installer can use all of it. With every file
// Missing nothing is installed and nobody has picked anything, so the missing notice stays out.
function choicesNotice(payload, files) {
  const choices = payload.choices;
  if (!choices || typeof choices.path !== "string") return null;
  const path = choices.path;
  if (choices.status === "bad") return emptyState(t("files_choices_bad_h"), t("files_choices_bad_t", { path }), "files");
  if (choices.status === "missing") {
    if (files.length > 0 && files.every((file) => file.state === "missing")) return null;
    return emptyState(t("files_choices_missing_h"), t("files_choices_missing_t", { path }), "files");
  }
  const names = Array.isArray(choices.bad) ? choices.bad.filter((name) => typeof name === "string") : [];
  if (choices.status === "ok" && names.length > 0) {
    return emptyState(t("files_choices_partly_h"), t("files_choices_partly_t", { path, names: names.join(", ") }), "files");
  }
  return null;
}

export function render(root, ctx) {
  clear(root);
  root.appendChild(pageHead({ title: t("nav_files"), intro: t("intro_files") }));
  const res = ctx.data && ctx.data.files;
  const payload = res && res.ok && res.data ? res.data : null;
  if (!payload) {
    if (res) root.appendChild(emptyState(t("files_error_h"), t("files_error_t"), "files"));
    return;
  }
  const files = Array.isArray(payload.files) ? payload.files : [];
  const notice = choicesNotice(payload, files);
  if (notice) root.appendChild(notice);
  const rows = files.map(rowFor).filter(Boolean);
  root.appendChild(card({
    title: t("c_files_table"), icon: "files",
    body: table3([t("h_file"), t("h_state"), t("h_next")], rows),
  }));
  root.appendChild(h("p", { class: "foot" }, t("files_foot")));
  root.appendChild(h("p", { class: "foot" }, t("files_scope")));
}

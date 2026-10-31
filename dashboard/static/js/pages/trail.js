// The trail of what decides one value, at #/settings/<agent key>/<setting key>. It draws the Settings head and
// tiles, then the "What decides" panel for the row: the winner, every value that lost, the rules behind
// them and the files read. Screen 07 in docs/design/usage-stack/a-usage is the reference, and app.css holds
// every class used here (section "Settings and trail").
//
// The panel works from the server's rows, entries and rules, not from any tile, so it opens for any row,
// agents included. Every value, path and quote comes from the server as data, so it goes in as text through
// h.js and renderText, never as markup. A link to another site goes through externalLink in h.js.

import { h, clear, externalLink } from "../h.js";
import { t, renderText, fmtTime } from "../format.js";
import { MAIN_KEY } from "../router.js";
import { card, chip } from "../components.js";
import {
  renderSettingsBody, valueText, valueString, sourceText, layerText, settingWord, winnerOf, returnFocusTo,
} from "./settings.js";

const LOST = ["overridden", "ignored", "invalid"]; // the statuses that did not count
const CONFIDENCE_ORDER = ["tested", "documented", "assumed"];

// ---------------------------------------------------------------- rows

function rowFor(payload, agent, setting) {
  return (payload.rows || []).find((r) => r.agent === agent && r.setting === setting) || null;
}

function entriesOf(payload, row) {
  return row.entries.map((i) => payload.entries[i]).filter(Boolean);
}

// The winner of the row of another setting for the same agent, or null when it has no such row.
function winnerFor(payload, agent, setting) {
  const row = rowFor(payload, agent, setting);
  return row ? entriesOf(payload, row)[0] || null : null;
}

// ---------------------------------------------------------------- pieces

// A doc link shows its address without the scheme.
const withoutScheme = (url) => String(url).replace(/^[a-z]+:[\\/]+/i, "");

// The place a value came from, with its layer first: "Project settings, <source>".
function layeredSource(entry, payload) {
  const layer = layerText(entry, payload);
  return (layer ? layer + ", " : "") + sourceText(entry, payload, true);
}

// True when the value was read from the shell: its file is the shell, or it is a default that came through a
// variable whose own row is a shell value (see sourceText).
function fromShell(entry, payload) {
  const file = entry.file === null || entry.file === undefined || entry.file === ""
    ? (entry.via ? (winnerOf(payload, "env." + entry.via) || {}).file : null)
    : entry.file;
  return file !== null && file !== undefined && file === payload.shell_label;
}

// One entry of the row, big for the winner and a card for the others.
function entryNode(entry, payload, big) {
  const value = valueText(entry, payload);
  const layer = layerText(entry, payload);
  const hasBecomes = entry.becomes !== undefined && entry.becomes !== null;
  const shell = fromShell(entry, payload);
  return h("div", { class: ["en", big ? "en-big" : "en-card"], "data-status": entry.status },
    h("div", { class: "en-top" },
      value === null ? null : [h("span", { class: "sr" }, t("lbl_value")), h("span", { class: "val" }, value)],
      h("span", { class: "sr" }, t("lbl_status")),
      chip(entry.status),
      hasBecomes ? h("span", { class: "runs" }, t("runs_as", { becomes: entry.becomes })) : null),
    h("div", { class: "en-src" },
      h("span", { class: "sr" }, t("lbl_source")),
      layer ? h("span", { class: "ly" }, layer) : null,
      h("span", { class: "pa" }, renderText(sourceText(entry, payload)))),
    h("p", { class: "en-rs" }, h("span", { class: "sr" }, t("lbl_reason")), renderText(entry.reason || "")),
    shell ? h("p", { class: "en-note" }, t("shell_note")) : null);
}

// "Model" and "Effort cap" above the cards.
function metaBlock(payload, row) {
  const lines = [];
  const model = winnerFor(payload, row.agent, "model");
  const modelText = model ? valueText(model, payload) : null;
  if (modelText !== null) lines.push(h("div", null, h("dt", null, t("f_model")), h("dd", null, modelText)));
  if (row.setting === "effortLevel" || row.setting === "effort") {
    const cap = winnerFor(payload, MAIN_KEY, "maxEffortLevel");
    // The cap row describes the main session's model, and a per-model cap has no row for other models. An agent
    // row shows the line only when its model is the main session's. Two unknown models aren't the same model.
    const mainModel = winnerFor(payload, MAIN_KEY, "model");
    const known = Boolean(model && mainModel && model.value !== null && model.value !== undefined);
    const sameModel = row.agent === MAIN_KEY || (known && model.value === mainModel.value);
    if (cap && sameModel) {
      const none = cap.status === "default" || cap.value === null || cap.value === undefined;
      lines.push(h("div", null, h("dt", null, t("cap")), h("dd", null,
        none ? t("no_cap") : [
          h("span", { class: "val" }, valueText(cap, payload)),
          chip(cap.status),
          h("span", { class: "src" }, renderText(layeredSource(cap, payload))),
        ])));
    }
  }
  return lines.length ? h("dl", { class: "meta" }, lines) : null;
}

function winnerCard(payload, winner) {
  const value = valueString(winner, payload);
  const summary = (value ? value + " " : "") + t("status_" + winner.status) + ", " + sourceText(winner, payload, true);
  return card({
    title: t("sec_winner"), icon: "flag", summary: renderText(summary), open: true, heading: "h3",
    body: h("div", { class: "win" }, entryNode(winner, payload, true)),
  });
}

function othersCard(payload, others) {
  const n = others.length;
  const m = others.filter((e) => LOST.includes(e.status)).length;
  let summary;
  if (m === 0) summary = n === 1 ? t("sum_values_clean_1") : t("sum_values_clean", { n });
  else summary = n === 1 && m === 1 ? t("sum_values_1") : t("sum_values", { n, m });
  return card({
    title: t("sec_values_other"), icon: "list", summary, open: true, heading: "h3",
    body: h("div", { class: "ens ens-a" }, others.map((e) => entryNode(e, payload, false))),
  });
}

// ---------------------------------------------------------------- rules

function quotesBlock(rule) {
  const quotes = rule.quotes || [];
  if (!quotes.length) return null;
  return h("details", { class: "qd" },
    h("summary", null, t("quotes_toggle", { n: quotes.length })),
    h("ul", { class: "ru-q" }, quotes.map((q) => h("li", null,
      externalLink({}, q.doc_url, withoutScheme(q.doc_url)),
      // The docs mark code with backticks. The screen shows the words alone.
      h("q", null, renderText(String(q.quote).replace(/`/g, "")))))));
}

// One rule. installed is the Claude Code version on this machine, or null. A rule marked due reads as
// due for a new check.
export function ruleItem(rule, installed) {
  const confidence = rule.confidence;
  const verified = rule.verified_on || {};
  const date = verified.date ? fmtTime(verified.date) + ", " + verified.date.slice(0, 4) : "";
  return h("li", { class: ["ru", "ru-" + confidence] },
    h("div", { class: "ru-top" },
      externalLink({ class: "ru-id", "aria-label": t("rule_link_sr", { rule_id: rule.rule_id }) }, rule.reference_url, rule.rule_id),
      h("span", { class: ["cf", "cf-" + confidence] }, t("conf_" + confidence))),
    confidence === "assumed" ? h("p", { class: "ru-def" }, t("assumed_def")) : null,
    // Screen 07 writes the year, and the day here comes from rules.json as YYYY-MM-DD.
    h("p", { class: "ru-ck" }, rule.due
      ? t("checked_old", { version: verified.claude_version, date, installed })
      : t("checked", { version: verified.claude_version, date })),
    quotesBlock(rule),
    rule.experiment ? h("p", { class: "ru-x" },
      h("span", { class: "ru-l" }, t("experiment")),
      externalLink({}, rule.experiment_url, "dashboard/" + rule.experiment)) : null);
}

function rulesCard(payload, row) {
  const rules = row.rule_ids.map((id) => (payload.rules || {})[id]).filter(Boolean);
  if (!rules.length) return null;
  const parts = CONFIDENCE_ORDER
    .map((c) => [c, rules.filter((r) => r.confidence === c).length])
    .filter(([, count]) => count > 0)
    .map(([c, count]) => count + " " + t("conf_" + c))
    .join(", ");
  const summary = rules.length === 1 ? t("sum_rules_1", { parts }) : t("sum_rules", { n: rules.length, parts });
  return card({
    title: t("rules_h"), icon: "rules", summary, open: false, heading: "h3",
    body: h("ul", { class: "rules" }, rules.map((rule) => ruleItem(rule, payload.installed))),
  });
}

// ---------------------------------------------------------------- files

function fileItem(file) {
  const layer = layerText(file);
  const read = file.status === "ok";
  return h("li", { class: "fl" },
    h("div", { class: "fl-top" },
      layer ? h("span", { class: "ly" }, layer) : h("span", null),
      read
        ? h("span", { class: "st st-read" }, h("i", { class: "mk", "aria-hidden": "true" }), t("file_read"))
        : chip(file.entry_status || "unknown")),
    h("span", { class: "pa" }, file.path));
}

function filesCard(payload) {
  const files = payload.files || [];
  if (!files.length) return null;
  const problems = files.filter((f) => f.status !== "ok");
  let summary;
  if (!problems.length) {
    summary = files.length === 1 ? t("sum_files_1") : t("sum_files", { n: files.length });
  } else {
    const status = t("status_" + (problems[0].entry_status || "unknown"));
    summary = files.length === 1 && problems.length === 1
      ? t("sum_files_problem_1", { status }) : t("sum_files_problem", { n: files.length, m: problems.length, status });
  }
  return card({
    title: t("sec_files"), icon: "sources", summary, open: false, heading: "h3",
    body: h("ul", { class: "fls" }, files.map(fileItem)),
  });
}

// ---------------------------------------------------------------- panel

// The panel and its heading. The caller moves focus to the heading.
function buildPanel(payload, row) {
  const entries = entriesOf(payload, row);
  const winner = entries[0];
  const setting = settingWord(row.setting);
  const title = h("h2", { class: "tr-title", tabindex: "-1" },
    row.agent === MAIN_KEY ? t("trail_h", { setting }) : t("trail_h_agent", { setting, agent: row.agent }));
  const panel = h("div", { id: "trail", class: "trail-a" },
    title,
    metaBlock(payload, row),
    winner ? winnerCard(payload, winner) : null,
    entries.length > 1 ? othersCard(payload, entries.slice(1)) : null,
    rulesCard(payload, row),
    filesCard(payload));
  return { panel, title };
}

// ---------------------------------------------------------------- focus and keys

// The trail being shown now, or null on any other route. The Escape listener reads it.
let active = null;
// The route key (agent and setting) that already took focus on arrival. Cleared when the route leaves the trail.
let arrived = null;
// The document the Escape listener is on. The page has one, so it is added once.
let boundTo = null;

function insidePanel(root) {
  for (let node = document.activeElement; node && node !== root; node = node.parentNode) {
    if (node.getAttribute && node.getAttribute("id") === "trail") return true;
  }
  return false;
}

// Escape closes the trail and returns to Settings. The listener sits in the capture phase, so it sees the key
// before shell.js, which closes the sidebar panel on the same key. It leaves a key the sidebar panel owns
// alone, and a key that something else already handled.
function onKeydown(event) {
  if (event.key !== "Escape" || event.defaultPrevented || !active || active.root.hidden) return;
  const sidebar = document.getElementById("sidebar");
  if (sidebar && sidebar.classList.contains("is-open")) return;
  const { agent, setting, ctx } = active;
  returnFocusTo(agent, setting);
  window.location.hash = ctx.hashFor("settings", {});
}

function bindKeys() {
  if (boundTo === document) return;
  boundTo = document;
  document.addEventListener("keydown", onKeydown, true);
}

export function render(root, ctx) {
  const hadFocus = insidePanel(root);
  clear(root);
  if (ctx.route.name !== "trail") { // the route carries the parameters this page needs
    active = null;
    arrived = null;
    return;
  }
  const { agent, setting } = ctx.route.params;
  active = { root, ctx, agent, setting };
  bindKeys();
  const payload = renderSettingsBody(root, ctx, agent === MAIN_KEY ? setting : null);
  if (!payload) return;
  const row = rowFor(payload, agent, setting);
  if (!row) return;
  const { panel, title } = buildPanel(payload, row);
  root.appendChild(panel);
  const key = agent + "\n" + setting;
  if (arrived !== key || hadFocus) {
    arrived = key;
    title.focus();
  }
}

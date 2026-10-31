// Rules reference: every rule the dashboard applies, what backs it and the Claude Code version it was checked
// on, with a search and a filter by confidence. Screen 10 in docs/design/usage-stack/a-usage is the reference,
// and app.css already holds every class used here (section "Rules reference"). Each rule is drawn by ruleItem
// in trail.js, the same item the trail shows, with the rule's reason added. The server sends the reason with
// its slots in braces ({file}, {model}), and reasonText words them. Every value comes from the server as data,
// so it goes in as text through h.js and renderText, never as markup.
//
// The search and the filter live in this module, so they survive a draw again. render() runs when the Rules
// route is shown and when its payload arrives, so a section that already shows the same payload object is
// left as it is, and a keystroke or a filter change rebuilds only the list and the count line.

import { h, clear } from "../h.js";
import { t, renderText } from "../format.js";
import { icon } from "../icons.js";
import { pageHead, card } from "../components.js";
import { ruleItem } from "./trail.js";

const CONFIDENCE = ["tested", "documented", "assumed"];
const KEYS = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };

// ---------------------------------------------------------------- the reason

// The one fixed word for each slot a reason can hold. Each key is written out, so the strings test sees every call.
function slotWord(name) {
  switch (name) {
    case "winner": return t("slot_winner");
    case "file": return t("slot_file");
    case "other_file": return t("slot_other_file");
    case "agent": return t("slot_agent");
    case "model": return t("slot_model");
    case "key": return t("slot_key");
    case "layer": return t("slot_layer");
    case "value": return t("slot_value");
    case "becomes": return t("slot_becomes");
    default: return null;
  }
}

const capital = (word) => word.charAt(0).toUpperCase() + word.slice(1);

// The reason of a rule as plain text, with each slot worded: "{winner} sets the model." reads "The winning
// source sets the model." A slot that opens the reason starts with a capital. Backticks are dropped, as in the
// quotes. A slot with no word stays in braces.
export function reasonText(rule) {
  let text = String(rule.reason === undefined || rule.reason === null ? "" : rule.reason);
  if (rule.rule_id === "agent-file-same-name-one-tree") text = text.replace("the name {agent}", t("slot_same_name"));
  text = text.replace(/`/g, "");
  return text.replace(/\{(\w+)\}/g, (whole, name, offset) => {
    const word = slotWord(name);
    if (word === null) return whole;
    return offset === 0 ? capital(word) : word;
  });
}

// ---------------------------------------------------------------- state

// What the search and the filter hold now. They outlive a draw.
let query = "";
let filter = "all";
// What the section shows now: its root, the payload object and the parts a keystroke changes. Null before the
// first draw, and after a draw that showed the head only.
let drawn = null;

// ---------------------------------------------------------------- pieces

// The first element under node that the test accepts. It walks childNodes, so it needs no selector.
function descend(node, test) {
  for (const child of node.childNodes) {
    if (child.nodeType !== 1) continue;
    if (test(child)) return child;
    const found = descend(child, test);
    if (found) return found;
  }
  return null;
}

const withClass = (name) => (node) => node.classList.contains(name);

function filterButton(key, label, count) {
  const on = key === filter;
  return h("button", {
    type: "button", role: "radio", class: ["seg", on && "is-active"], "aria-checked": on ? "true" : "false",
    tabindex: on ? "0" : "-1", "data-filter": key,
  }, label, " ", h("span", { class: "muted" }, String(count)));
}

function noMatch(view) {
  return h("div", { class: "es", role: "status" },
    h("p", { class: "es-h" }, t("rules_no_match", { q: query.trim() })),
    h("button", {
      type: "button", class: "btn",
      on: { click: () => { query = ""; view.input.value = ""; refresh(view); view.input.focus(); } },
    }, t("rules_clear_search")));
}

// True when the rule shows for the search and the filter.
function shows(entry) {
  if (filter !== "all" && entry.rule.confidence !== filter) return false;
  const words = query.trim().toLowerCase();
  return words === "" || entry.haystack.includes(words);
}

// Builds the list and the count line again from the search and the filter. Nothing else is touched. The items
// are kept, so a details a reader opened stays open when the rule comes back.
function refresh(view) {
  const matched = view.entries.filter(shows);
  const narrowed = query.trim() !== "" || filter !== "all";
  clear(view.sub);
  view.sub.appendChild(document.createTextNode(narrowed
    ? t("rules_match_count", { n: matched.length, m: view.entries.length }) : t("rules_sub")));
  clear(view.list);
  matched.forEach((entry) => view.list.appendChild(entry.item));
  clear(view.body);
  view.body.appendChild(query.trim() !== "" && matched.length === 0 ? noMatch(view) : view.list);
}

function pickFilter(view, key) {
  filter = key;
  view.buttons.forEach((b) => {
    const on = b.getAttribute("data-filter") === key;
    b.setAttribute("aria-checked", on ? "true" : "false");
    b.setAttribute("tabindex", on ? "0" : "-1");
    b.classList.toggle("is-active", on);
  });
  refresh(view);
}

// The radio group, as rangeControl in components.js draws one: a roving tabindex, the arrows move and select,
// and focus stays on the active radio.
function filterGroup(view, counts, total) {
  const group = h("div", { class: "segs segs-range", role: "radiogroup", "aria-label": t("rules_filter_label") });
  const choices = [["all", t("rules_all"), total]]
    .concat(CONFIDENCE.map((c) => [c, t("conf_" + c), counts[c]]));
  view.buttons = choices.map(([key, label, count]) => {
    const button = filterButton(key, label, count);
    button.addEventListener("click", () => pickFilter(view, key));
    return button;
  });
  group.addEventListener("keydown", (event) => {
    const step = KEYS[event.key];
    if (!step) return;
    event.preventDefault();
    const keys = choices.map((c) => c[0]);
    const next = (keys.indexOf(filter) + step + keys.length) % keys.length;
    pickFilter(view, keys[next]);
    view.buttons[next].focus();
  });
  view.buttons.forEach((b) => group.appendChild(b));
  return group;
}

function searchBox(view) {
  const input = h("input", {
    type: "search", placeholder: t("rules_search_placeholder"), "aria-label": t("rules_search_label"),
    autocomplete: "off", spellcheck: "false",
  });
  input.value = query;
  input.addEventListener("input", () => { query = input.value; refresh(view); });
  view.input = input;
  return h("div", { class: "search" }, icon("search"), input);
}

// ---------------------------------------------------------------- the card

function build(payload) {
  const rules = Array.isArray(payload.rules) ? payload.rules : [];
  const counts = {};
  CONFIDENCE.forEach((c) => { counts[c] = rules.filter((r) => r.confidence === c).length; });
  const view = {
    payload,
    entries: rules.map((rule) => {
      const reason = reasonText(rule);
      const item = ruleItem(rule, payload.installed, renderText(reason));
      item.setAttribute("id", rule.rule_id);
      return { rule, item, haystack: (String(rule.rule_id) + "\n" + reason).toLowerCase() };
    }),
    list: h("ul", { class: "rules" }),
    buttons: [], input: null, sub: null, body: null,
  };
  const actions = h("div", { class: "cd-act rules-act" }, searchBox(view), filterGroup(view, counts, rules.length));
  const section = card({
    title: t("c_rules_list"), icon: "rules", sub: t("rules_sub"), actions, cls: "cd-rules", body: view.list,
  });
  view.section = section;
  view.sub = descend(section, withClass("cd-sub"));
  view.sub.setAttribute("aria-live", "polite");
  view.body = descend(section, withClass("cd-bd"));
  refresh(view);
  return view;
}

export function render(root, ctx) {
  const res = ctx.data && ctx.data.rules;
  const payload = res && res.ok && res.data ? res.data : null;
  if (payload && drawn && drawn.root === root && drawn.payload === payload && root.firstChild) return;
  const hadFocus = Boolean(drawn && drawn.root === root && drawn.view.input === document.activeElement);
  drawn = null;
  clear(root);
  root.appendChild(pageHead({ title: t("nav_rules"), intro: t("intro_rules") }));
  if (!payload) return;
  const view = build(payload);
  root.appendChild(view.section);
  drawn = { root, payload, view };
  if (hadFocus) view.input.focus();
}

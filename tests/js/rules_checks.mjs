// Browser-free checks of the Rules reference page, run by tests/test_rules_js.py. They load pages/rules.js and
// the shared modules from dashboard/static/js against the small fake DOM in fakedom.mjs. Nothing here opens a
// browser or a socket. The payloads are real /api/rules answers that the Python test writes into the folder
// named by MR_PAYLOADS: "rules" (no installed version) and "rules-due" (installed 2.1.310). The ones for edge
// cases are written by hand in the same shape. A failed check prints its name and the reason, and the exit
// code is 1.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { FElement, createPage } from "./fakedom.mjs";

const STATIC = new URL("../../dashboard/static/", import.meta.url);
const JS = new URL("js/", STATIC).href;
const STRINGS = JSON.parse(fs.readFileSync(new URL("strings.json", STATIC), "utf8"));
const PAYLOADS = process.env.MR_PAYLOADS;
assert.ok(PAYLOADS, "MR_PAYLOADS names the folder of fixture payloads");

const real = (name) => JSON.parse(fs.readFileSync(path.join(PAYLOADS, name + ".json"), "utf8"));

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

const format = await import(JS + "format.js");
format.setStrings(STRINGS);
const router = await import(JS + "router.js");

// The page keeps its search, its filter and what it drew in module state. Each check gets its own copy of the
// module, so one check never starts with another's search.
let copies = 0;
async function freshModule() {
  copies += 1;
  return import(JS + "pages/rules.js?copy=" + copies);
}

// The setter below catches any attempt to parse text as markup.
const parsed = [];
Object.defineProperty(FElement.prototype, "innerHTML", { set(v) { parsed.push(String(v)); }, get() { return ""; } });
Object.defineProperty(FElement.prototype, "outerHTML", { set(v) { parsed.push(String(v)); }, get() { return ""; } });

const hasClass = (n, c) => n.classList && n.classList.contains(c);
const byClass = (root, c) => root.find((n) => hasClass(n, c));
const byTag = (root, tag) => root.find((n) => n.tagName === tag);
const text = (n) => n.textContent;
const sub = (node, c) => byClass(node, c)[0];

function makeCtx(payload, { res = null } = {}) {
  return {
    route: { name: "rules", params: {} },
    project: { key: "app", name: "App" },
    data: { rules: res || (payload ? { ok: true, status: 200, data: payload } : null) },
    hashFor: (name, params) => router.hashFor(name, params, { project: "app" }),
  };
}

// Draws the page into a fresh section of a fresh page. Returns what a check needs to drive it.
async function open(payload, opts = {}) {
  const mod = opts.mod || await freshModule();
  const page = createPage();
  const root = page.sections.rules;
  const ctx = makeCtx(payload, opts);
  mod.render(root, ctx);
  return { mod, root, ctx, page };
}

const inputOf = (root) => byTag(root, "input")[0];
const buttonsOf = (root) => byClass(root, "seg");
const listOf = (root) => byClass(root, "rules")[0];
const itemsOf = (root) => (listOf(root) ? listOf(root).childNodes : []);
const countLine = (root) => text(sub(root, "cd-sub"));
const idsShown = (root) => itemsOf(root).map((li) => li.getAttribute("id"));

function type(root, value) {
  const input = inputOf(root);
  input.value = value;
  input.dispatch("input");
}

const buttonFor = (root, key) => buttonsOf(root).find((b) => b.getAttribute("data-filter") === key);
const click = (root, key) => buttonFor(root, key).click();
const press = (root, key) => byClass(root, "segs")[0].dispatch("keydown", { key });

const PAYLOAD = real("rules");
const DUE = real("rules-due");
const RULES = PAYLOAD.rules;
const count = (list, confidence) => list.filter((r) => r.confidence === confidence).length;

function hand(rules, over = {}) {
  return { installed: null, rules, ...over };
}

function rule(over) {
  return {
    rule_id: "a-rule", confidence: "tested", verified_on: { claude_version: "2.1.302", date: "2026-10-29" }, due: false,
    quotes: [], experiment: null, experiment_url: null, reference_url: "https://github.com/x/y/blob/main/docs/rules-reference.md#a-rule",
    reason: "{winner} decides.", ...over,
  };
}

// ---------------------------------------------------------------- the reason

test("reasonText: no rule in rules.json keeps a brace, a backtick or a slot name", async () => {
  const { reasonText } = await freshModule();
  assert.ok(RULES.length >= 60, "the real rules");
  for (const r of RULES) {
    const got = reasonText(r);
    assert.equal(/[{}]/.test(got), false, r.rule_id + ": " + got);
    assert.equal(got.includes("`"), false, r.rule_id);
    assert.ok(got.length > 10, r.rule_id);
  }
});

test("reasonText: each slot reads its one fixed word", async () => {
  const { reasonText } = await freshModule();
  const one = (reason) => reasonText({ rule_id: "x", reason });
  assert.equal(one("a {winner}."), "a " + STRINGS.slot_winner + ".");
  assert.equal(one("a {file}."), "a " + STRINGS.slot_file + ".");
  assert.equal(one("a {other_file}."), "a " + STRINGS.slot_other_file + ".");
  assert.equal(one("a {agent}."), "a " + STRINGS.slot_agent + ".");
  assert.equal(one("a {model}."), "a " + STRINGS.slot_model + ".");
  assert.equal(one("a {key}."), "a " + STRINGS.slot_key + ".");
  assert.equal(one("a {layer}."), "a " + STRINGS.slot_layer + ".");
  assert.equal(one("a {value}."), "a " + STRINGS.slot_value + ".");
  assert.equal(one("a {becomes}."), "a " + STRINGS.slot_becomes + ".");
  assert.equal(one("{file} and {file}"), "The file and the file");
});

test("reasonText: a slot that opens the reason gets a capital, one inside does not", async () => {
  const { reasonText } = await freshModule();
  assert.equal(reasonText({ rule_id: "x", reason: "{winner} sets the model." }), "The winning source sets the model.");
  assert.equal(reasonText({ rule_id: "x", reason: "Then {winner} sets it." }), "Then the winning source sets it.");
  const opening = RULES.filter((r) => r.reason.startsWith("{"));
  assert.ok(opening.length > 20, "many real reasons open with a slot");
  for (const r of opening) {
    const got = reasonText(r);
    assert.match(got[0], /[A-Z]/, r.rule_id + ": " + got);
  }
});

test("reasonText: the value and becomes slots read X and Y", async () => {
  const { reasonText } = await freshModule();
  const r = RULES.find((x) => x.rule_id === "effort-lowered-by-cap");
  assert.ok(r);
  assert.equal(reasonText(r), "X from the file runs as Y, because maxEffortLevel caps the model at Y.");
});

test("reasonText: the same-name rule says the same name, not the name of the agent", async () => {
  const { reasonText } = await freshModule();
  const r = RULES.find((x) => x.rule_id === "agent-file-same-name-one-tree");
  assert.ok(r);
  const got = reasonText(r);
  assert.ok(got.startsWith("The file and another file both use the same name, and Claude Code loads only one of them"), got);
  assert.equal(got.includes("the agent"), false);
});

test("reasonText: backticks go, a missing reason is empty, an unknown slot stays", async () => {
  const { reasonText } = await freshModule();
  assert.equal(reasonText({ rule_id: "x", reason: "Run `claude doctor` now." }), "Run claude doctor now.");
  assert.equal(reasonText({ rule_id: "x" }), "");
  assert.equal(reasonText({ rule_id: "x", reason: null }), "");
  assert.equal(reasonText({ rule_id: "x", reason: "{nope} stays." }), "{nope} stays.");
});

// ---------------------------------------------------------------- the page

test("page: the head comes first, then one Rules card", async () => {
  const { root } = await open(PAYLOAD);
  assert.equal(root.childNodes.length, 2);
  assert.equal(root.childNodes[0].classList.contains("ph"), true);
  assert.equal(text(byTag(root, "h1")[0]), "Rules reference");
  assert.equal(text(sub(root, "intro")), STRINGS.intro_rules);
  const card = root.childNodes[1];
  assert.equal(card.tagName, "section");
  assert.equal(hasClass(card, "cd"), true);
  assert.equal(hasClass(card, "cd-rules"), true);
  assert.equal(text(byTag(card, "h2")[0]), "Rules");
  assert.equal(byClass(card, "cd-ic").length, 1, "the rules icon");
});

test("page: a missing, failed or empty payload shows the head only", async () => {
  for (const [label, p] of [
    ["none", null],
    ["not ok", { res: { ok: false, status: 500, data: null } }],
    ["404", { res: { ok: false, status: 404, data: null } }],
    ["no data", { res: { ok: true, status: 200, data: null } }],
  ]) {
    const { root } = await open(null, p || {});
    assert.equal(root.childNodes.length, 1, label);
    assert.equal(root.childNodes[0].classList.contains("ph"), true, label);
  }
});

test("page: the sub line is the question, a polite live region", async () => {
  const { root } = await open(PAYLOAD);
  const line = sub(root, "cd-sub");
  assert.equal(line.tagName, "p");
  assert.equal(text(line), STRINGS.rules_sub);
  assert.equal(line.getAttribute("aria-live"), "polite");
});

test("page: the search box has its icon, placeholder and label, and no autocomplete or spellcheck", async () => {
  const { root } = await open(PAYLOAD);
  const actions = sub(root, "cd-act");
  assert.equal(hasClass(actions, "rules-act"), true);
  assert.deepEqual(actions.childNodes.map((n) => n.getAttribute("class")), ["search", "segs segs-range"]);
  const box = actions.childNodes[0];
  assert.equal(box.tagName, "div");
  assert.equal(box.find((n) => n.tagName === "svg").length, 1, "the search icon");
  const input = inputOf(root);
  assert.equal(input.getAttribute("type"), "search");
  assert.equal(input.getAttribute("placeholder"), STRINGS.rules_search_placeholder);
  assert.equal(input.getAttribute("aria-label"), STRINGS.rules_search_label);
  assert.equal(input.getAttribute("autocomplete"), "off");
  assert.equal(input.getAttribute("spellcheck"), "false");
  assert.equal(input.value, "");
});

test("page: the filter is a radio group of All, Tested, Documented and Assumed with counts over all rules", async () => {
  const { root } = await open(PAYLOAD);
  const group = sub(root, "segs");
  assert.equal(group.getAttribute("role"), "radiogroup");
  assert.equal(group.getAttribute("aria-label"), STRINGS.rules_filter_label);
  const buttons = buttonsOf(root);
  assert.deepEqual(buttons.map(text), [
    "All " + RULES.length, "Tested " + count(RULES, "tested"), "Documented " + count(RULES, "documented"),
    "Assumed " + count(RULES, "assumed")]);
  assert.deepEqual(buttons.map((b) => b.getAttribute("role")), ["radio", "radio", "radio", "radio"]);
  assert.deepEqual(buttons.map((b) => b.getAttribute("aria-checked")), ["true", "false", "false", "false"]);
  assert.deepEqual(buttons.map((b) => b.getAttribute("tabindex")), ["0", "-1", "-1", "-1"]);
  assert.deepEqual(buttons.map((b) => hasClass(b, "is-active")), [true, false, false, false]);
  for (const b of buttons) assert.equal(byClass(b, "muted").length, 1, "the count is a span.muted");
  assert.equal(count(RULES, "tested") + count(RULES, "documented") + count(RULES, "assumed"), RULES.length);
});

test("page: the list is every rule in the server's order, each li with its rule id", async () => {
  const { root } = await open(PAYLOAD);
  const list = listOf(root);
  assert.equal(list.tagName, "ul");
  assert.deepEqual(idsShown(root), RULES.map((r) => r.rule_id));
  assert.equal(new Set(idsShown(root)).size, RULES.length, "ids are unique");
  assert.equal(countLine(root), STRINGS.rules_sub, "nothing narrows the list, so the sub line stays");
});

test("page: a rule item is the trail's item with its reason right after the id line", async () => {
  const { root } = await open(PAYLOAD);
  const li = itemsOf(root)[0];
  assert.equal(li.tagName, "li");
  assert.equal(hasClass(li, "ru"), true);
  assert.equal(hasClass(li, "ru-" + RULES[0].confidence), true);
  assert.equal(hasClass(li.childNodes[0], "ru-top"), true);
  assert.equal(li.childNodes[1].tagName, "p");
  assert.equal(hasClass(li.childNodes[1], "ru-rs"), true);
  const link = sub(li, "ru-id");
  assert.equal(text(link), RULES[0].rule_id);
  assert.equal(link.getAttribute("href"), RULES[0].reference_url);
  assert.equal(link.getAttribute("target"), "_blank");
  assert.equal(link.getAttribute("rel"), "noopener noreferrer");
  assert.equal(text(sub(li, "cf")), STRINGS["conf_" + RULES[0].confidence]);
});

test("page: every item shows its own reason, worded", async () => {
  const mod = await freshModule();
  const { root } = await open(PAYLOAD, { mod });
  const items = itemsOf(root);
  assert.equal(items.length, RULES.length);
  RULES.forEach((r, i) => {
    assert.equal(text(sub(items[i], "ru-rs")), mod.reasonText(r), r.rule_id);
  });
});

test("page: the docs quotes sit in a details that is closed by default", async () => {
  const { root } = await open(PAYLOAD);
  const details = byTag(root, "details").filter((d) => hasClass(d, "qd"));
  assert.ok(details.length > 20, "many rules carry quotes");
  for (const d of details) {
    assert.equal(d.open, false);
    assert.match(text(byTag(d, "summary")[0]), /^From the docs \(\d+\)$/);
  }
});

test("page: the checked line follows the installed version", async () => {
  const none = await open(PAYLOAD);
  const lines = byClass(none.root, "ru-ck").map(text);
  assert.equal(lines.length, RULES.length);
  for (const line of lines) {
    assert.match(line, /^Checked on Claude Code \d/);
    assert.equal(line.includes("due for a new check"), false);
  }
  const due = await open(DUE);
  const items = itemsOf(due.root);
  let marked = 0;
  DUE.rules.forEach((r, i) => {
    const line = text(sub(items[i], "ru-ck"));
    if (r.due) {
      marked += 1;
      assert.ok(line.endsWith("You have 2.1.310, so this rule is due for a new check."), line);
    } else {
      assert.equal(line.includes("due for a new check"), false, line);
    }
  });
  assert.ok(marked > 0, "an install newer than the rules makes some due");
});

test("page: the assumed rules carry their definition line", async () => {
  const { root } = await open(PAYLOAD);
  assert.equal(byClass(root, "ru-def").length, count(RULES, "assumed"));
});

test("page: a stub answer with no rules draws an empty list and zero counts", async () => {
  const { root } = await open({ rules: [] });
  assert.equal(byClass(root, "rules")[0].childNodes.length, 0);
  assert.deepEqual(buttonsOf(root).map(text), ["All 0", "Tested 0", "Documented 0", "Assumed 0"]);
  assert.equal(countLine(root), STRINGS.rules_sub);
  assert.equal(byClass(root, "es").length, 0);
});

// ---------------------------------------------------------------- the search

test("search: it narrows the list live, over the rendered reason, and the count line says so", async () => {
  const mod = await freshModule();
  const { root } = await open(PAYLOAD, { mod });
  type(root, "winning source");
  const want = RULES.filter((r) => mod.reasonText(r).toLowerCase().includes("winning source") || r.rule_id.includes("winning source"));
  assert.ok(want.length > 5 && want.length < RULES.length, "the phrase narrows the list");
  assert.deepEqual(idsShown(root), want.map((r) => r.rule_id));
  assert.equal(countLine(root), want.length + " of " + RULES.length + " rules shown.");
  assert.equal(sub(root, "cd-sub").getAttribute("aria-live"), "polite");
});

test("search: the raw slot name is not searchable, the worded reason is", async () => {
  const { root } = await open(PAYLOAD);
  type(root, "{winner}");
  assert.equal(itemsOf(root).length, 0);
  type(root, "the winning source");
  assert.ok(itemsOf(root).length > 0);
});

test("search: it matches the rule id", async () => {
  const { root } = await open(PAYLOAD);
  type(root, "prompt-cache-ttl");
  const want = RULES.filter((r) => r.rule_id.includes("prompt-cache-ttl")).map((r) => r.rule_id);
  assert.ok(want.length >= 2);
  const shown = idsShown(root);
  for (const id of want) assert.ok(shown.includes(id), id);
  assert.equal(countLine(root), shown.length + " of " + RULES.length + " rules shown.");
});

test("search: case does not matter and the ends are trimmed", async () => {
  const { root } = await open(PAYLOAD);
  type(root, "winning source");
  const lower = idsShown(root);
  type(root, "  WINNING Source \t");
  assert.deepEqual(idsShown(root), lower);
  type(root, "EFFORT-LOWERED-BY-CAP");
  assert.ok(idsShown(root).includes("effort-lowered-by-cap"));
});

test("search: a blank query is no query", async () => {
  const { root } = await open(PAYLOAD);
  type(root, "   ");
  assert.equal(itemsOf(root).length, RULES.length);
  assert.equal(countLine(root), STRINGS.rules_sub);
  assert.equal(byClass(root, "es").length, 0);
});

test("search: clearing the box brings back every rule and the question", async () => {
  const { root } = await open(PAYLOAD);
  type(root, "winning source");
  type(root, "");
  assert.equal(itemsOf(root).length, RULES.length);
  assert.equal(countLine(root), STRINGS.rules_sub);
});

test("search: a keystroke rebuilds only the list and the count line", async () => {
  const { root, page } = await open(PAYLOAD);
  const outside = page.doc.createElement("details");
  outside.setAttribute("open", "");
  root.appendChild(outside);
  const before = [...root.childNodes];
  const card = root.childNodes[1];
  const input = inputOf(root);
  const group = sub(root, "segs");
  const head = byClass(root, "cd-hd")[0];
  input.focus();
  type(root, "winning");
  assert.equal(root.childNodes.length, before.length);
  before.forEach((n, i) => assert.equal(root.childNodes[i], n, "the section's children are the same nodes"));
  assert.equal(root.childNodes[1], card);
  assert.equal(inputOf(root), input, "the input is the same element");
  assert.equal(FElement.focused, input, "and it keeps focus");
  assert.equal(sub(root, "segs"), group);
  assert.equal(byClass(root, "cd-hd")[0], head);
  assert.equal(outside.open, true, "a details outside the list is untouched");
});

test("search: a details a reader opened in the list stays open when its rule comes back", async () => {
  const { root } = await open(PAYLOAD);
  const li = itemsOf(root).find((n) => byTag(n, "details").length);
  const id = li.getAttribute("id");
  byTag(li, "details")[0].setAttribute("open", "");
  type(root, "zzz-no-rule-has-this");
  assert.equal(itemsOf(root).length, 0);
  type(root, "");
  const back = itemsOf(root).find((n) => n.getAttribute("id") === id);
  assert.equal(back, li, "the same item comes back");
  assert.equal(byTag(back, "details")[0].open, true);
});

// ---------------------------------------------------------------- the filter

test("filter: a click shows one confidence, updates the radios and the count line", async () => {
  const { root } = await open(PAYLOAD);
  click(root, "tested");
  assert.equal(itemsOf(root).length, count(RULES, "tested"));
  assert.ok(itemsOf(root).every((li) => hasClass(li, "ru-tested")));
  assert.equal(countLine(root), count(RULES, "tested") + " of " + RULES.length + " rules shown.");
  assert.deepEqual(buttonsOf(root).map((b) => b.getAttribute("aria-checked")), ["false", "true", "false", "false"]);
  assert.deepEqual(buttonsOf(root).map((b) => b.getAttribute("tabindex")), ["-1", "0", "-1", "-1"]);
  assert.deepEqual(buttonsOf(root).map((b) => hasClass(b, "is-active")), [false, true, false, false]);
  assert.deepEqual(buttonsOf(root).map(text), [
    "All " + RULES.length, "Tested " + count(RULES, "tested"), "Documented " + count(RULES, "documented"),
    "Assumed " + count(RULES, "assumed")], "the counts stay over all rules");
  click(root, "assumed");
  assert.equal(itemsOf(root).length, count(RULES, "assumed"));
  click(root, "all");
  assert.equal(itemsOf(root).length, RULES.length);
  assert.equal(countLine(root), STRINGS.rules_sub);
});

test("filter: the arrow keys move and select, wrap round, and focus stays on the active radio", async () => {
  const { root } = await open(PAYLOAD);
  press(root, "ArrowRight");
  assert.equal(buttonFor(root, "tested").getAttribute("aria-checked"), "true");
  assert.equal(FElement.focused, buttonFor(root, "tested"));
  assert.equal(itemsOf(root).length, count(RULES, "tested"));
  press(root, "ArrowDown");
  assert.equal(FElement.focused, buttonFor(root, "documented"));
  assert.equal(itemsOf(root).length, count(RULES, "documented"));
  press(root, "ArrowLeft");
  assert.equal(FElement.focused, buttonFor(root, "tested"));
  press(root, "ArrowUp");
  press(root, "ArrowUp");
  assert.equal(FElement.focused, buttonFor(root, "assumed"), "left of All wraps to Assumed");
  press(root, "ArrowRight");
  assert.equal(FElement.focused, buttonFor(root, "all"), "right of Assumed wraps to All");
  assert.equal(itemsOf(root).length, RULES.length);
  assert.equal(buttonsOf(root).filter((b) => b.getAttribute("tabindex") === "0").length, 1, "one stop in the tab order");
});

test("filter: another key does nothing", async () => {
  const { root } = await open(PAYLOAD);
  press(root, "Enter");
  press(root, "a");
  assert.equal(buttonFor(root, "all").getAttribute("aria-checked"), "true");
  assert.equal(itemsOf(root).length, RULES.length);
});

test("filter and search combine", async () => {
  const mod = await freshModule();
  const { root } = await open(PAYLOAD, { mod });
  type(root, "winning source");
  const matched = RULES.filter((r) => mod.reasonText(r).toLowerCase().includes("winning source"));
  click(root, "tested");
  const want = matched.filter((r) => r.confidence === "tested");
  assert.ok(want.length > 0 && want.length < matched.length, "the filter narrows the search too");
  assert.deepEqual(idsShown(root), want.map((r) => r.rule_id));
  assert.equal(countLine(root), want.length + " of " + RULES.length + " rules shown.");
  click(root, "all");
  assert.equal(itemsOf(root).length, matched.length, "the search stays when the filter goes");
});

// ---------------------------------------------------------------- no match

test("no match: the list gives way to the message and the clear button, and the count line reads zero", async () => {
  const { root } = await open(PAYLOAD);
  type(root, "cache ttl zzz");
  assert.equal(byClass(root, "rules").length, 0, "no list");
  const es = sub(root, "es");
  assert.equal(es.tagName, "div");
  assert.equal(es.getAttribute("role"), "status");
  assert.equal(text(sub(es, "es-h")), "No rule matches “cache ttl zzz” here, so clear the search to see the list again.");
  const button = byTag(es, "button")[0];
  assert.equal(hasClass(button, "btn"), true);
  assert.equal(button.getAttribute("type"), "button");
  assert.equal(text(button), "Clear search");
  assert.equal(countLine(root), "0 of " + RULES.length + " rules shown.");
  assert.equal(byClass(root, "cd-bd")[0].childNodes.length, 1, "the message is the whole body");
});

test("no match: the message names the trimmed query", async () => {
  const { root } = await open(PAYLOAD);
  type(root, "  zzz  ");
  assert.ok(text(sub(root, "es-h")).includes("“zzz”"));
});

test("no match: Clear search empties the box, keeps the filter and focuses the input", async () => {
  const { root } = await open(PAYLOAD);
  click(root, "documented");
  type(root, "zzz");
  assert.equal(itemsOf(root).length, 0);
  byTag(sub(root, "es"), "button")[0].click();
  const input = inputOf(root);
  assert.equal(input.value, "");
  assert.equal(FElement.focused, input);
  assert.equal(buttonFor(root, "documented").getAttribute("aria-checked"), "true", "the filter stays");
  assert.equal(itemsOf(root).length, count(RULES, "documented"));
  assert.equal(byClass(root, "es").length, 0);
  assert.equal(countLine(root), count(RULES, "documented") + " of " + RULES.length + " rules shown.");
});

test("no match: a filter that gives no rows with an empty search draws an empty list, not the message", async () => {
  const only = hand([rule({ rule_id: "one", confidence: "tested" }), rule({ rule_id: "two", confidence: "tested" })]);
  const { root } = await open(only);
  click(root, "assumed");
  assert.equal(byClass(root, "es").length, 0);
  assert.equal(listOf(root).childNodes.length, 0);
  assert.equal(countLine(root), "0 of 2 rules shown.");
  type(root, "zzz");
  assert.equal(byClass(root, "es").length, 1, "with a search the message shows");
  type(root, "");
  assert.equal(byClass(root, "es").length, 0);
  assert.equal(listOf(root).childNodes.length, 0);
});

// ---------------------------------------------------------------- drawing again

test("redraw: the same payload object keeps the DOM as it is", async () => {
  const mod = await freshModule();
  const { root, ctx } = await open(PAYLOAD, { mod });
  const before = [...root.childNodes];
  const input = inputOf(root);
  type(root, "winning");
  const shown = idsShown(root);
  input.focus();
  mod.render(root, ctx);
  mod.render(root, makeCtx(PAYLOAD));
  assert.equal(root.childNodes.length, before.length);
  before.forEach((n, i) => assert.equal(root.childNodes[i], n, "no node was replaced"));
  assert.equal(inputOf(root), input);
  assert.equal(input.value, "winning");
  assert.deepEqual(idsShown(root), shown);
  assert.equal(FElement.focused, input);
});

test("redraw: a new payload object rebuilds the card and keeps the search and the filter", async () => {
  const mod = await freshModule();
  const { root, ctx } = await open(PAYLOAD, { mod });
  click(root, "tested");
  type(root, "winning");
  const shown = idsShown(root);
  const oldCard = root.childNodes[1];
  const oldInput = inputOf(root);
  const copy = JSON.parse(JSON.stringify(PAYLOAD));
  mod.render(root, makeCtx(copy));
  assert.equal(root.childNodes.length, 2);
  assert.notEqual(root.childNodes[1], oldCard);
  assert.notEqual(inputOf(root), oldInput);
  assert.equal(inputOf(root).value, "winning");
  assert.equal(buttonFor(root, "tested").getAttribute("aria-checked"), "true");
  assert.equal(buttonFor(root, "all").getAttribute("aria-checked"), "false");
  assert.deepEqual(idsShown(root), shown);
  assert.equal(countLine(root), shown.length + " of " + RULES.length + " rules shown.");
});

test("redraw: an input that had focus keeps it on a new payload", async () => {
  const mod = await freshModule();
  const { root } = await open(PAYLOAD, { mod });
  inputOf(root).focus();
  mod.render(root, makeCtx(JSON.parse(JSON.stringify(PAYLOAD))));
  assert.equal(FElement.focused, inputOf(root));
});

test("redraw: a failed answer after a good one shows the head only, and a later good one draws again", async () => {
  const mod = await freshModule();
  const { root } = await open(PAYLOAD, { mod });
  mod.render(root, makeCtx(null, { res: { ok: false, status: 503, data: null } }));
  assert.equal(root.childNodes.length, 1);
  mod.render(root, makeCtx(PAYLOAD));
  assert.equal(root.childNodes.length, 2);
  assert.equal(itemsOf(root).length, RULES.length);
});

test("redraw: a section that was cleared draws again for the same payload", async () => {
  const mod = await freshModule();
  const { root } = await open(PAYLOAD, { mod });
  while (root.firstChild) root.removeChild(root.firstChild);
  mod.render(root, makeCtx(PAYLOAD));
  assert.equal(root.childNodes.length, 2);
});

// ---------------------------------------------------------------- text, not markup

test("safety: values from the server go in as text and never as markup", async () => {
  const evil = "<img src=x onerror=alert(1)>";
  const before = parsed.length;
  const bad = hand([rule({
    rule_id: "evil", reason: evil + " {file}", reference_url: "javascript:alert(1)",
    quotes: [{ doc_url: "https://code.claude.com/docs/en/x#y", quote: evil }],
  })]);
  const { root } = await open(bad);
  assert.deepEqual(parsed.slice(before), []);
  assert.equal(root.find((n) => n.tagName === "img").length, 0);
  assert.ok(text(root).includes(evil));
  assert.equal(sub(root, "ru-id").getAttribute("href"), null, "an address that is not https gets no href");
  for (const file of ["rules.js", "files.js"]) {
    const source = fs.readFileSync(new URL("js/pages/" + file, STATIC), "utf8");
    assert.equal(/innerHTML|outerHTML|insertAdjacentHTML|document\.write/.test(source), false, file);
  }
});

// ---------------------------------------------------------------- run

let failed = 0;
for (const [name, fn] of tests) {
  try {
    await fn();
    console.log("ok   " + name);
  } catch (err) {
    failed += 1;
    console.log("FAIL " + name + "\n     " + String(err && err.stack ? err.stack : err).split("\n").slice(0, 6).join("\n     "));
  }
}
console.log((tests.length - failed) + " of " + tests.length + " checks passed");
process.exit(failed ? 1 : 0);

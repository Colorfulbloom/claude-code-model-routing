// Browser-free checks of Needs attention, run by tests/test_attention_js.py. They load pages/attention.js and
// the shared modules from dashboard/static/js against the small fake DOM in fakedom.mjs. Nothing here opens
// a browser or a socket. Payloads for the resolution fixtures are real /api/settings answers that the Python
// test writes into the folder named by MR_PAYLOADS. The ones for states and edge cases are written by hand in
// the same shape. A failed check prints its name and the reason, and the exit code is 1.
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
const attention = await import(JS + "pages/attention.js");

// The setter below catches any attempt to parse text as markup.
const parsed = [];
Object.defineProperty(FElement.prototype, "innerHTML", { set(v) { parsed.push(String(v)); }, get() { return ""; } });
Object.defineProperty(FElement.prototype, "outerHTML", { set(v) { parsed.push(String(v)); }, get() { return ""; } });

function makeCtx(payload, { project = { key: "app", name: "App" }, res = null } = {}) {
  return {
    route: { name: "attention", params: {} },
    project,
    data: { settings: res || (payload ? { ok: true, status: 200, data: payload } : null) },
    hashFor: (name, params) => router.hashFor(name, params, { project: project.key }),
  };
}

function show(payload, opts = {}) {
  const page = createPage();
  const root = page.sections.attention;
  attention.render(root, makeCtx(payload, opts));
  return root;
}

const hasClass = (n, c) => n.classList && n.classList.contains(c);
const byClass = (root, c) => root.find((n) => hasClass(n, c));
const byTag = (root, tag) => root.find((n) => n.tagName === tag);
const text = (n) => n.textContent;
const sub = (node, c) => byClass(node, c)[0];

function entry(over) {
  return { key: "effortLevel", value: "high", status: "overridden", layer: "user", file: "~/.claude/settings.json",
    scope: "main", line: 3, rule_id: "x", rule_ids: ["x"], reason: "because", ...over };
}

// Builds a payload from entries, and groups them the way the server does for the rows named by status.
function handPayload(entries, attentionGroups, over = {}) {
  return {
    project: "app", state: "ok", entries, no_user_settings: false, shell_label: "Shell",
    path_display: "~/work/app", config_dir_display: "~/.claude", config_file_display: "~/.claude/routing-dashboard.json",
    models: { "claude-opus-5-5": "Opus 5.5" }, rows: [], rules: {}, files: [], installed: null,
    attention: attentionGroups, ...over,
  };
}

const route = (agent, setting) => ({ agent, setting });

const ENTRIES = [
  entry({ key: "model", value: null, status: "unknown", file: null, layer: "default", line: undefined }),
  entry({ key: "effortLevel", value: "xhigh", status: "lowered", becomes: "high", file: "~/.claude/settings.json" }),
  entry({ key: "effortLevel", value: "low", status: "overridden", file: ".claude/settings.json", line: 4 }),
  entry({ key: "effort", value: "high", status: "ignored", scope: "agent", agent: "builder", file: "~/.claude/agents/builder.md", line: 5 }),
  entry({ key: "effortLevel", value: "bogus", status: "invalid", file: ".claude/settings.local.json", line: 2 }),
  entry({ key: "agentFile", value: null, status: "overridden", scope: "agent", agent: "scribe", file: "~/.claude/agents/scribe.md", line: undefined }),
];

const GROUPS = [
  { status: "unknown", rows: [{ entry: 0, route: route("@main", "model") }] },
  { status: "lowered", rows: [{ entry: 1, route: route("@main", "effortLevel") }] },
  { status: "ignored", rows: [{ entry: 3, route: route("builder", "effort") }] },
  { status: "overridden", rows: [
    { entry: 2, route: route("@main", "effortLevel") },
    { entry: 5, route: route("scribe", "agentFile") },
  ] },
  { status: "invalid", rows: [{ entry: 4, route: route("@main", "effortLevel") }] },
];

const payloadAll = () => handPayload(ENTRIES, GROUPS);

// ---------------------------------------------------------------- the page

test("page: the head comes first, then one card per group in the order the server gave", () => {
  const root = show(payloadAll());
  assert.equal(root.childNodes[0].classList.contains("ph"), true);
  assert.equal(text(byTag(root, "h1")[0]), "Needs attention");
  assert.equal(text(sub(root, "intro")), STRINGS.intro_attention);
  const cards = byClass(root, "cd");
  assert.deepEqual(cards.map((c) => text(sub(c, "cd-h"))), ["Unknown", "Lowered", "Ignored", "Overridden", "Invalid"]);
  assert.deepEqual(byTag(root, "h2").map(text), ["Unknown", "Lowered", "Ignored", "Overridden", "Invalid"]);
  assert.deepEqual(cards.map((c) => text(sub(c, "cd-sub"))),
    [STRINGS.p_unknown, STRINGS.p_lowered, STRINGS.p_ignored, STRINGS.p_overridden, STRINGS.p_invalid]);
  assert.equal(byClass(root, "cd-ic").length, 0, "no card icon");
  for (const c of cards) {
    const list = sub(c, "at");
    assert.equal(list.tagName, "ul");
    assert.equal(hasClass(list, "at-full"), true);
  }
});

test("page: a row is li > a with a name, a value and status, a source and the way to the trail", () => {
  const root = show(payloadAll());
  const lowered = byClass(root, "cd")[1];
  const li = byTag(lowered, "li");
  assert.equal(li.length, 1);
  const a = li[0].childNodes[0];
  assert.equal(a.tagName, "a");
  assert.equal(a.getAttribute("href"), "#/settings/@main/effortLevel?project=app");
  assert.deepEqual(a.childNodes.map((n) => n.getAttribute("class")), ["at-n", "at-m", "at-s", "at-go"]);
  assert.equal(text(sub(a, "at-n")), "Main session, Effort");
  const meta = sub(a, "at-m");
  assert.equal(text(sub(meta, "at-v")), "xhigh");
  const chip = sub(meta, "st");
  assert.equal(chip.find((n) => hasClass(n, "mk")).length, 1, "a mark glyph");
  assert.equal(text(chip), "Lowered");
  assert.equal(meta.childNodes[0], sub(meta, "at-v"), "the value comes before the chip");
  assert.equal(text(sub(a, "at-s")), "~/.claude/settings.json, line 3");
  const go = sub(a, "at-go");
  assert.equal(text(go), "Open the trail");
  assert.equal(go.find((n) => n.tagName === "svg").length, 1, "the arrow icon");
});

test("page: an agent row names the agent and the setting, and its link carries the agent", () => {
  const root = show(payloadAll());
  const ignored = byClass(root, "cd")[2];
  const a = byTag(ignored, "a")[0];
  assert.equal(text(sub(a, "at-n")), "builder, Effort");
  assert.equal(a.getAttribute("href"), "#/settings/builder/effort?project=app");
  const overridden = byTag(byClass(root, "cd")[3], "a");
  assert.deepEqual(overridden.map((n) => text(sub(n, "at-n"))), ["Main session, Effort", "scribe, Agent file"]);
  assert.deepEqual(overridden.map((n) => n.getAttribute("href")),
    ["#/settings/@main/effortLevel?project=app", "#/settings/scribe/agentFile?project=app"]);
});

test("page: the value is left out when it has no text, and the chip stays", () => {
  const root = show(payloadAll());
  const unknown = byTag(byClass(root, "cd")[0], "a")[0];
  const meta = sub(unknown, "at-m");
  assert.equal(sub(meta, "at-v"), undefined);
  assert.equal(text(meta), "Unknown");
  const scribe = byTag(byClass(root, "cd")[3], "a")[1];
  assert.equal(sub(sub(scribe, "at-m"), "at-v"), undefined, "a null value shows nothing");
  assert.equal(text(sub(sub(scribe, "at-m"), "st")), "Overridden");
});

test("page: an unknown-model effort row shows no value and keeps the chip", () => {
  const entries = [
    entry({ value: "xhigh", status: "unknown", rule_ids: ["effort-level-user-settings-model-unknown"] }),
    entry({ key: "effort", scope: "agent", agent: "builder", value: "xhigh", status: "unknown",
      rule_ids: ["agent-effort-user-settings-model-unknown"] }),
  ];
  const groups = [{ status: "unknown", rows: [
    { entry: 0, route: route("@main", "effortLevel") }, { entry: 1, route: route("builder", "effort") }] }];
  const root = show(handPayload(entries, groups));
  assert.equal(byClass(root, "at-v").length, 0);
  assert.deepEqual(byClass(root, "at-m").map(text), ["Unknown", "Unknown"]);
});

test("page: an empty string shows as the word for empty and a hidden value shows its word", () => {
  const entries = [entry({ value: "", status: "invalid" }), entry({ value: "hidden", status: "invalid", line: 9 })];
  const groups = [{ status: "invalid", rows: [
    { entry: 0, route: route("@main", "effortLevel") }, { entry: 1, route: route("@main", "effortLevel") }] }];
  const root = show(handPayload(entries, groups));
  const values = byClass(root, "at-v").map(text);
  assert.deepEqual(values, ["empty", "hidden"]);
});

test("page: the source of a default reads as the default", () => {
  const root = show(payloadAll());
  const unknown = byTag(byClass(root, "cd")[0], "a")[0];
  assert.equal(text(sub(unknown, "at-s")), STRINGS.default_src);
});

test("page: no groups gives one card with the empty line and no icon", () => {
  const root = show(handPayload(ENTRIES, []));
  const cards = byClass(root, "cd");
  assert.equal(cards.length, 1);
  assert.equal(text(sub(cards[0], "cd-h")), "Needs attention");
  assert.equal(byClass(cards[0], "cd-ic").length, 0);
  const p = sub(cards[0], "at-empty");
  assert.equal(p.tagName, "p");
  assert.equal(text(p), "Every value is In effect or Default");
  assert.equal(byClass(root, "at").length, 0);
});

test("page: All projects shows the head and the picker prompt, nothing else", () => {
  const root = show(payloadAll(), { project: { key: "all", name: "All projects" } });
  assert.equal(root.childNodes.length, 2);
  assert.equal(root.childNodes[0].classList.contains("ph"), true);
  assert.equal(text(sub(root, "cd-h")), STRINGS.s_pick_project_h);
  assert.equal(byClass(root, "at").length, 0);
  assert.equal(byClass(root, "es").length, 1);
});

test("page: a missing or failed payload shows the head only", () => {
  for (const [label, root] of [
    ["none", show(null)],
    ["not ok", show(null, { res: { ok: false, status: 500, data: null } })],
    ["no data", show(null, { res: { ok: true, status: 200, data: null } })],
  ]) {
    assert.equal(root.childNodes.length, 1, label);
    assert.equal(root.childNodes[0].classList.contains("ph"), true, label);
  }
});

test("page: a project whose folder is missing shows the same Folder not found card as Settings", () => {
  const payload = handPayload([], [], { state: "missing_folder", path_display: "~/gone" });
  const root = show(payload, { project: { key: "lantern", name: "Lantern" } });
  assert.equal(root.childNodes.length, 2);
  assert.equal(text(sub(root, "cd-h")), "Folder not found");
  assert.equal(text(sub(root, "es-t")), STRINGS.es_missing_t
    .replaceAll("{name}", "Lantern").replace("{path}", "~/gone").replace("{config_file}", "~/.claude/routing-dashboard.json"));
  assert.equal(byClass(root, "at").length, 0);
});

test("page: the implicit current project keeps missing_folder but still resolves, so the groups show", () => {
  const root = show(handPayload(ENTRIES, GROUPS, { state: "missing_folder" }));
  assert.equal(byClass(root, "cd").length, 5);
});

test("page: it draws again from scratch", () => {
  const page = createPage();
  const root = page.sections.attention;
  const ctx = makeCtx(payloadAll());
  attention.render(root, ctx);
  attention.render(root, ctx);
  assert.equal(byClass(root, "ph").length, 1);
  assert.equal(byClass(root, "cd").length, 5);
});

test("page: values from the server go in as text and never as markup", () => {
  const evil = "<img src=x onerror=alert(1)>";
  const before = parsed.length;
  const entries = [entry({ value: evil, file: evil, status: "invalid", reason: evil })];
  const groups = [{ status: "invalid", rows: [{ entry: 0, route: route(evil, evil) }] }];
  const root = show(handPayload(entries, groups));
  assert.deepEqual(parsed.slice(before), []);
  assert.equal(root.find((n) => n.tagName === "img").length, 0);
  assert.ok(text(root).includes(evil));
  const source = fs.readFileSync(new URL("js/pages/attention.js", STATIC), "utf8");
  assert.equal(/innerHTML|outerHTML|insertAdjacentHTML|document\.write/.test(source), false);
});

// ---------------------------------------------------------------- real payloads

test("real: every row of every fixture answer links to the trail of its route and shows a status word", () => {
  const names = ["effort-user-top-level-xhigh-ignored-opus-5-5", "effort-lowered-by-cap", "model-main-default-unknown",
    "env-block-over-shell", "agent-effort-default-fable-5-1", "settings-user-not-json-skipped"];
  let rows = 0;
  for (const name of names) {
    const payload = real(name);
    const root = show(payload);
    const links = byClass(root, "at-go").length;
    const expected = payload.attention.reduce((n, g) => n + g.rows.length, 0);
    assert.equal(links, expected, name);
    const hrefs = byTag(root, "a").map((a) => a.getAttribute("href"));
    const wanted = payload.attention.flatMap((g) => g.rows.map((r) => router.hashFor("trail", r.route, { project: "app" })));
    assert.deepEqual(hrefs, wanted, name);
    const chips = byClass(root, "st").map(text);
    assert.deepEqual(chips, payload.attention.flatMap((g) => g.rows.map(() => STRINGS["status_" + g.status])), name);
    rows += expected;
  }
  assert.ok(rows > 0, "the fixtures hold rows that need attention");
});

// ---------------------------------------------------------------- the Overview card

test("overviewCard: null with no payload, a failed payload or All projects", () => {
  assert.equal(attention.overviewCard(makeCtx(null)), null);
  assert.equal(attention.overviewCard(makeCtx(null, { res: { ok: false, status: 500, data: null } })), null);
  assert.equal(attention.overviewCard(makeCtx(payloadAll(), { project: { key: "all", name: "All projects" } })), null);
});

test("overviewCard: the first three rows across the groups and a link to see all", () => {
  createPage();
  const node = attention.overviewCard(makeCtx(payloadAll()));
  assert.equal(text(sub(node, "cd-h")), "Needs attention");
  assert.equal(text(sub(node, "cd-sub")), STRINGS.attention_card_sub);
  assert.equal(byClass(node, "cd-ic").length, 1, "the issues icon");
  const list = sub(node, "at");
  assert.equal(hasClass(list, "at-plain"), true);
  assert.equal(hasClass(list, "at-full"), false);
  const lis = byTag(list, "li");
  assert.equal(lis.length, 3);
  const a = lis[0].childNodes[0];
  assert.deepEqual(a.childNodes.map((n) => n.getAttribute("class")), ["at-n", "at-m", "at-p"]);
  assert.equal(byClass(node, "at-go").length, 0);
  assert.equal(byClass(node, "at-s").length, 0);
  assert.deepEqual(lis.map((li) => text(sub(li, "at-n"))), ["Main session, Model", "Main session, Effort", "builder, Effort"]);
  assert.deepEqual(lis.map((li) => text(sub(li, "at-p"))), [STRINGS.p_unknown, STRINGS.p_lowered, STRINGS.p_ignored]);
  assert.equal(lis[1].childNodes[0].getAttribute("href"), "#/settings/@main/effortLevel?project=app");
  const more = sub(node, "at-more");
  assert.equal(more.tagName, "p");
  const link = byTag(more, "a")[0];
  assert.equal(text(link), "See all 6");
  assert.equal(link.getAttribute("href"), "#/attention?project=app");
});

test("overviewCard: fewer than three rows shows them all", () => {
  createPage();
  const groups = [{ status: "lowered", rows: [{ entry: 1, route: route("@main", "effortLevel") }] }];
  const node = attention.overviewCard(makeCtx(handPayload(ENTRIES, groups)));
  assert.equal(byTag(sub(node, "at"), "li").length, 1);
  assert.equal(text(byTag(sub(node, "at-more"), "a")[0]), "See all 1");
});

test("overviewCard: no rows gives the empty line and no list", () => {
  createPage();
  const node = attention.overviewCard(makeCtx(handPayload(ENTRIES, [])));
  assert.equal(text(sub(node, "cd-h")), "Needs attention");
  assert.equal(byClass(node, "at").length, 0);
  assert.equal(byClass(node, "at-more").length, 0);
  assert.equal(text(sub(node, "at-empty")), "Every value is In effect or Default");
});

test("overviewCard: no rows with equal values left out says so", () => {
  createPage();
  const node = attention.overviewCard(makeCtx(handPayload(ENTRIES, [], { attention_equal: 2 })));
  assert.equal(byClass(node, "at").length, 0);
  assert.equal(text(sub(node, "at-empty")),
    "Every value is In effect or Default, or Overridden by a source that sets the same value");
  const zero = attention.overviewCard(makeCtx(handPayload(ENTRIES, [], { attention_equal: 0 })));
  assert.equal(text(sub(zero, "at-empty")), "Every value is In effect or Default");
});

test("page: no groups with equal values left out says so, and a zero count keeps the short line", () => {
  const root = show(handPayload(ENTRIES, [], { attention_equal: 3 }));
  assert.equal(text(sub(root, "at-empty")), STRINGS.at_empty_equal);
  assert.equal(byClass(root, "cd").length, 1);
  assert.equal(text(sub(show(handPayload(ENTRIES, [], { attention_equal: 0 })), "at-empty")), STRINGS.at_empty);
  assert.equal(text(sub(show(handPayload(ENTRIES, [])), "at-empty")), STRINGS.at_empty, "no field at all");
});

test("page: groups with rows ignore attention_equal", () => {
  const root = show(handPayload(ENTRIES, GROUPS, { attention_equal: 5 }));
  assert.equal(byClass(root, "at-empty").length, 0);
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

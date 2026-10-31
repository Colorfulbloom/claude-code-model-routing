// Browser-free checks of the Settings page and its trail, run by tests/test_settings_js.py. They load
// pages/settings.js, pages/trail.js and the shared modules from dashboard/static/js against the small
// fake DOM in fakedom.mjs. Nothing here
// opens a browser or a socket. Payloads for the resolution fixtures are real /api/settings answers that
// the Python test writes into the folder named by MR_PAYLOADS. The ones for states and source forms are
// written by hand in the same shape. A failed check prints its name and the reason, and the exit code is 1.
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
const settings = await import(JS + "pages/settings.js");
const trail = await import(JS + "pages/trail.js");

// The setter below catches any attempt to parse text as markup.
const parsed = [];
Object.defineProperty(FElement.prototype, "innerHTML", { set(v) { parsed.push(String(v)); }, get() { return ""; } });
Object.defineProperty(FElement.prototype, "outerHTML", { set(v) { parsed.push(String(v)); }, get() { return ""; } });

// Renders the page into a fresh section. settingsRes is what ctx.data.settings holds.
function show(payload, { project = { key: "app", name: "App" }, res = null } = {}) {
  const page = createPage();
  const root = page.sections.settings;
  const ctx = {
    route: { name: "settings", params: {} },
    project,
    data: { settings: res || (payload ? { ok: true, status: 200, data: payload } : null) },
    hashFor: (name, params) => router.hashFor(name, params, { project: project.key }),
  };
  settings.render(root, ctx);
  return root;
}

const hasClass = (n, c) => n.classList && n.classList.contains(c);
const byClass = (root, c) => root.find((n) => hasClass(n, c));
const tilesOf = (root) => byClass(root, "tl");
const tileFor = (root, key) => tilesOf(root).find((n) => n.getAttribute("data-setting") === key);
const text = (n) => n.textContent;
const sub = (tile, c) => byClass(tile, c)[0];

function entry(over) {
  return { key: "effortLevel", value: "high", status: "in_effect", layer: "user", file: "~/.claude/settings.json",
    scope: "main", line: 3, rule_id: "x", rule_ids: ["x"], reason: "because", ...over };
}

function handPayload(entries, over = {}) {
  return {
    project: "app", state: "ok", entries, no_user_settings: false, shell_label: "Shell",
    path_display: "~/work/app", config_dir_display: "~/.claude", config_file_display: "~/.claude/routing-dashboard.json",
    models: { "claude-opus-5-5": "Opus 5.5", opus: "Opus 5.5" }, ...over,
  };
}

const FOUR = [
  entry({ key: "model", value: "claude-opus-5-5", line: 2 }),
  entry({ key: "effortLevel", value: "high" }),
  entry({ key: "promptCacheTtl", value: "1h", file: null, status: "default", layer: "default", line: undefined }),
  entry({ key: "autoCompactWindow", value: 1000000, file: null, status: "default", layer: "default", line: undefined }),
];

// ---------------------------------------------------------------- tiles

test("tiles: four, in the order Model, Effort, Cache lifetime, Compact window", () => {
  const root = show(handPayload(FOUR));
  const tiles = tilesOf(root);
  assert.deepEqual(tiles.map((n) => n.getAttribute("data-setting")), ["model", "effortLevel", "promptCacheTtl", "autoCompactWindow"]);
  assert.deepEqual(tiles.map((n) => text(sub(n, "tl-l"))), ["Model", "Effort", "Cache lifetime", "Compact window"]);
  assert.equal(byClass(root, "tiles").length, 1);
});

test("tiles: the page head comes first and a tile links to the trail route of its row", () => {
  const root = show(handPayload(FOUR));
  assert.equal(root.childNodes[0].classList.contains("ph"), true);
  assert.equal(text(root.find((n) => n.tagName === "h1")[0]), "Settings");
  const link = tileFor(root, "effortLevel");
  assert.equal(link.tagName, "a");
  assert.equal(link.getAttribute("href"), "#/settings/@main/effortLevel?project=app");
  assert.match(link.getAttribute("aria-label"), /^Effort, high, In effect\. /);
  assert.ok(link.getAttribute("aria-label").endsWith(STRINGS.cell_desc));
});

test("tiles: every tile shows a mark glyph and a status word, never hue alone", () => {
  const root = show(handPayload(FOUR));
  for (const tile of tilesOf(root)) {
    const chip = sub(tile, "st");
    assert.ok(chip, "a status chip");
    assert.equal(chip.find((n) => hasClass(n, "mk")).length, 1);
    assert.match(text(chip), /^(In effect|Default|Unknown|Lowered)$/);
  }
  assert.equal(text(sub(tileFor(root, "promptCacheTtl"), "st")), "Default");
});

test("tiles: the model shows its display name alone, and a name outside the catalog says so", () => {
  const root = show(handPayload(FOUR));
  assert.equal(text(sub(tileFor(root, "model"), "tl-v")), "Opus 5.5");
  const other = show(handPayload([entry({ key: "model", value: "claude-opus-6-preview" })]));
  assert.equal(text(sub(tileFor(other, "model"), "tl-v")), "claude-opus-6-preview (not in the dashboard's model list)");
});

test("tiles: the compact window shows the raw number", () => {
  const root = show(handPayload(FOUR));
  assert.equal(text(sub(tileFor(root, "autoCompactWindow"), "tl-v")), "1000000");
});

test("tiles: a hidden value shows the word with its explanation as the title", () => {
  const root = show(handPayload([entry({ value: "hidden", status: "invalid" })]));
  const value = sub(tileFor(root, "effortLevel"), "tl-v");
  assert.equal(text(value), "hidden");
  const span = value.find((n) => n.tagName === "span" && n.getAttribute("title"))[0];
  assert.equal(span.getAttribute("title"), STRINGS.hidden_desc);
});

test("tiles: an empty value shows the word for empty and a null value shows nothing", () => {
  const empty = show(handPayload([entry({ value: "" })]));
  assert.equal(text(sub(tileFor(empty, "effortLevel"), "tl-v")), "empty");
  const none = show(handPayload([entry({ value: null, status: "unknown" })]));
  assert.equal(sub(tileFor(none, "effortLevel"), "tl-v"), undefined);
});

test("tiles: a Lowered value shows what it runs as", () => {
  const root = show(real("effort-lowered-by-cap"));
  const tile = tileFor(root, "effortLevel");
  assert.equal(text(sub(tile, "st")), "Lowered");
  const winner = real("effort-lowered-by-cap").entries.find((e) => e.scope === "main" && e.key === "effortLevel");
  assert.ok(winner.becomes, "the fixture lowers the level");
  assert.equal(text(sub(tile, "runs")), "runs as " + winner.becomes);
  assert.equal(text(sub(tile, "tl-v")), winner.value);
  assert.equal(sub(tileFor(root, "model"), "runs"), undefined);
});

// ---------------------------------------------------------------- sources

test("source: the three forms and the cases around them", () => {
  const payload = handPayload([
    entry({ key: "model", value: "opus", file: null, status: "default", layer: "default", line: undefined }),
    entry({ key: "effortLevel", file: "~/work/app/.claude/settings.local.json", line: 3, via: "CLAUDE_CODE_EFFORT_LEVEL", layer: "local" }),
    entry({ key: "promptCacheTtl", file: "Shell", line: undefined, via: "ENABLE_PROMPT_CACHING_1H", layer: "shell" }),
    entry({ key: "autoCompactWindow", file: "Shell", line: undefined, layer: "shell" }),
  ]);
  const root = show(payload);
  assert.equal(text(sub(tileFor(root, "model"), "tl-src")), "Claude Code's default");
  assert.equal(text(sub(tileFor(root, "effortLevel"), "tl-src")),
    "~/work/app/.claude/settings.local.json, line 3");
  assert.equal(text(sub(tileFor(root, "promptCacheTtl"), "tl-src")), "Shell");
  assert.equal(text(sub(tileFor(root, "autoCompactWindow"), "tl-src")), "Shell");
  assert.equal(byClass(root, "en-note").length, 0, "a shell source carries no note on a tile");
});

test("source: a file with a line, and a file with none", () => {
  const p = handPayload([]);
  assert.equal(settings.sourceText(entry({ file: "a/b.json", line: 7 }), p), "a/b.json, line 7");
  assert.equal(settings.sourceText(entry({ file: "a/b.json", line: undefined }), p), "a/b.json");
  assert.equal(settings.sourceText(entry({ file: null }), p), "Claude Code's default");
  assert.equal(settings.sourceText(entry({ file: "session.json:shell_env", line: undefined }), { ...p, shell_label: "session.json:shell_env" }), "Shell");
});

test("helpers: layers, setting words and values", () => {
  assert.equal(settings.layerText({ layer: "user" }), "User settings");
  assert.equal(settings.layerText({ layer: "project" }), "Project settings");
  assert.equal(settings.layerText({ layer: "local" }), "Local settings");
  assert.equal(settings.layerText({ layer: "managed" }), "Managed settings");
  for (const other of ["default", "shell", "flag", undefined]) assert.equal(settings.layerText({ layer: other }), "");
  const words = { model: "model", effortLevel: "effort", effort: "effort", promptCacheTtl: "cache lifetime",
    subagentPromptCacheTtl: "cache lifetime", autoCompactWindow: "compact window", maxEffortLevel: "effort cap",
    agentFile: "agent file", settingsFile: "settings file", rulesFile: "rules file", somethingElse: "somethingElse" };
  for (const [key, word] of Object.entries(words)) assert.equal(settings.settingWord(key), word, key);
  const p = handPayload([]);
  assert.equal(settings.valueText(entry({ key: "model", value: "claude-opus-5-5" }), p), "Opus 5.5 (claude-opus-5-5)");
  assert.equal(settings.valueText(entry({ key: "model", value: "opus" }), p), "Opus 5.5 (opus)");
  assert.equal(settings.valueText(entry({ key: "autoCompactWindow", value: 1000000 }), p), "1000000");
  assert.equal(settings.valueText(entry({ value: null }), p), null);
  assert.equal(settings.valueText(entry({ value: "" }), p), "empty");
});

// ---------------------------------------------------------------- first pair, in payload shape

test("first pair: user xhigh is ignored on Opus 5.5, so Effort shows medium, Default, Claude Code's default", () => {
  const root = show(real("effort-user-top-level-xhigh-ignored-opus-5-5"));
  const tile = tileFor(root, "effortLevel");
  assert.equal(text(sub(tile, "tl-v")), "medium");
  assert.equal(text(sub(tile, "st")), "Default");
  assert.equal(text(sub(tile, "tl-src")), "Claude Code's default");
  assert.equal(text(sub(tileFor(root, "model"), "tl-v")), "Opus 5.5");
  assert.equal(tilesOf(root).length, 4);
});

test("first pair: project xhigh is in effect, from project/.claude/settings.json", () => {
  const payload = real("effort-project-top-level-xhigh-opus-5-5");
  const root = show(payload);
  const tile = tileFor(root, "effortLevel");
  assert.equal(text(sub(tile, "tl-v")), "xhigh");
  assert.equal(text(sub(tile, "st")), "In effect");
  assert.match(text(sub(tile, "tl-src")), /^project\/\.claude\/settings\.json, line \d+$/);
});

test("unknown: model-main-default-unknown shows Unknown with its reason and no value", () => {
  const payload = real("model-main-default-unknown");
  const root = show(payload);
  const tile = tileFor(root, "model");
  assert.equal(text(sub(tile, "st")), "Unknown");
  assert.equal(sub(tile, "tl-v"), undefined);
  const winner = payload.entries.find((e) => e.scope === "main" && e.key === "model");
  assert.ok(winner.reason);
  const note = sub(tile, "en-note");
  assert.equal(note.tagName, "p");
  assert.equal(text(note), winner.reason);
  // The note comes after the source, inside the tile.
  const kids = tile.childNodes.map((n) => n.getAttribute("class").split(" ")[0]);
  assert.deepEqual(kids, ["tl-top", "tl-mid", "tl-src", "en-note"]);
  const effort = tileFor(root, "effortLevel");
  assert.equal(text(sub(effort, "st")), "Unknown");
  assert.ok(sub(effort, "en-note"));
});

test("the env block of a fixture reads as the file and line on a tile", () => {
  const root = show(real("env-block-over-shell"));
  const tile = tileFor(root, "model");
  assert.match(text(sub(tile, "tl-src")), /^config\/settings\.json, line \d+$/);
});

// ---------------------------------------------------------------- states

test("states: no .claude folder and no user settings file both show above the tiles", () => {
  const payload = handPayload(FOUR, { state: "no_claude_folder", no_user_settings: true });
  const root = show(payload);
  const order = root.childNodes.map((n) => (hasClass(n, "tiles") ? "tiles" : hasClass(n, "ph") ? "head" : "card"));
  assert.deepEqual(order, ["head", "card", "card", "tiles"]);
  const heads = root.find((n) => hasClass(n, "cd-h")).map(text);
  assert.deepEqual(heads, ["No .claude folder", "No user settings file"]);
  const bodies = root.find((n) => hasClass(n, "es-t")).map(text);
  assert.match(bodies[0], /^~\/work\/app has no \.claude folder/);
  assert.ok(bodies[0].includes("~/.claude"));
  assert.match(bodies[1], /^~\/\.claude has no settings\.json/);
  assert.equal(tilesOf(root).length, 4);
});

test("states: one message alone, and none when both files are there", () => {
  const noUser = show(handPayload(FOUR, { no_user_settings: true }));
  assert.deepEqual(noUser.find((n) => hasClass(n, "cd-h")).map(text), ["No user settings file"]);
  const noClaude = show(handPayload(FOUR, { state: "no_claude_folder" }));
  assert.deepEqual(noClaude.find((n) => hasClass(n, "cd-h")).map(text), ["No .claude folder"]);
  const fine = show(handPayload(FOUR));
  assert.equal(fine.find((n) => hasClass(n, "cd-h")).length, 0);
});

test("states: a missing folder shows its message with the config file and no tiles", () => {
  const payload = handPayload([], { state: "missing_folder" });
  const root = show(payload, { project: { key: "lantern", name: "Lantern" } });
  assert.deepEqual(root.find((n) => hasClass(n, "cd-h")).map(text), ["Folder not found"]);
  const body = text(root.find((n) => hasClass(n, "es-t"))[0]);
  assert.ok(body.includes("Lantern") && body.includes("~/work/app") && body.includes("~/.claude/routing-dashboard.json"), body);
  assert.equal(tilesOf(root).length, 0);
});

test("states: All projects shows the project picker and nothing else", () => {
  const root = show(handPayload(FOUR), { project: { key: "all", name: "All projects" } });
  assert.equal(tilesOf(root).length, 0);
  assert.deepEqual(root.find((n) => hasClass(n, "cd-h")).map(text), ["Pick a project"]);
  assert.equal(root.find((n) => n.tagName === "button").length, 1);
  assert.equal(text(root.find((n) => n.tagName === "h1")[0]), "Settings");
  const noData = show(null, { project: { key: "all", name: "All projects" } });
  assert.deepEqual(noData.find((n) => hasClass(n, "cd-h")).map(text), ["Pick a project"]);
});

test("states: no payload yet, or a refused one, shows the head only", () => {
  for (const res of [null, { ok: false, status: 404, data: null }, { ok: false, status: 500, data: null }]) {
    const root = show(null, { res });
    assert.equal(root.childNodes.length, 1);
    assert.ok(hasClass(root.childNodes[0], "ph"));
  }
});

test("render clears the section first, so a second render does not stack tiles", () => {
  const page = createPage();
  const root = page.sections.settings;
  const ctx = { route: { name: "settings", params: {} }, project: { key: "app", name: "App" },
    data: { settings: { ok: true, status: 200, data: handPayload(FOUR) } }, hashFor: (n, p) => router.hashFor(n, p, {}) };
  settings.render(root, ctx);
  settings.render(root, ctx);
  assert.equal(tilesOf(root).length, 4);
});

// ---------------------------------------------------------------- text from data

test("data: no string from the payload reaches innerHTML, and markup in it shows as text", () => {
  const evil = "<img src=x onerror=alert(1)>";
  const payload = handPayload([
    entry({ key: "model", value: evil, file: evil, via: evil }),
    entry({ key: "effortLevel", value: evil, status: "unknown", reason: evil, becomes: evil, file: evil, line: 1 }),
    entry({ key: "promptCacheTtl", value: evil, file: evil, line: 2 }),
    entry({ key: "autoCompactWindow", value: evil, file: null }),
  ], { state: "no_claude_folder", no_user_settings: true, path_display: evil, config_dir_display: evil });
  const root = show(payload);
  assert.deepEqual(parsed, []);
  assert.equal(root.find((n) => n.tagName === "img").length, 0);
  assert.ok(text(root).includes(evil));
  const source = fs.readFileSync(new URL("js/pages/settings.js", STATIC), "utf8");
  assert.equal(/innerHTML|outerHTML|insertAdjacentHTML|document\.write/.test(source), false);
});

// ================================================================ the trail (#42)

const REF = "https://github.com/Colorfulbloom/claude-code-model-routing/blob/main/docs/rules-reference.md";
const EXP = "https://github.com/Colorfulbloom/claude-code-model-routing/blob/main/dashboard/";

// The same rows the server builds: one per agent and key, with entry indexes and the rule ids that voted.
function rowsOf(entries) {
  const rows = new Map();
  entries.forEach((e, i) => {
    const agent = e.agent || "@main";
    const id = agent + "\n" + e.key;
    if (!rows.has(id)) rows.set(id, { agent, setting: e.key, scope: e.scope, entries: [], rule_ids: [] });
    const row = rows.get(id);
    row.entries.push(i);
    for (const rule of e.rule_ids || []) if (!row.rule_ids.includes(rule)) row.rule_ids.push(rule);
  });
  return [...rows.values()];
}

function ruleRec(id, over = {}) {
  return { rule_id: id, confidence: "tested", verified_on: { claude_version: "2.1.302", date: "2026-10-29" },
    quotes: [], experiment: null, experiment_url: null, reference_url: REF + "#" + id, ...over };
}

function trailPayload(entries, rules = [], over = {}) {
  const payload = handPayload(entries, over);
  payload.rows = rowsOf(entries);
  payload.rules = Object.fromEntries(rules.map((r) => [r.rule_id, r]));
  payload.files = over.files || [];
  return payload;
}

// Draws the trail route into the trail section of a fresh page. The settings route is drawn first, as the
// app does when a hash changes, so the trail counts as a new arrival.
function mount(payload, agent, setting, { project = { key: "app", name: "App" }, res = null, page = createPage() } = {}) {
  const root = page.sections.trail;
  root.hidden = false;
  const ctx = {
    route: { name: "trail", params: { agent, setting } },
    project,
    data: { settings: res || (payload ? { ok: true, status: 200, data: payload } : null) },
    hashFor: (name, params) => router.hashFor(name, params, { project: project.key }),
  };
  trail.render(root, { ...ctx, route: { name: "settings", params: {} } });
  trail.render(root, ctx);
  return { page, root, ctx, redraw: () => trail.render(root, ctx) };
}

const panelOf = (root) => root.find((n) => n.getAttribute("id") === "trail")[0];
const cardOf = (root, name) => root.find((n) => n.tagName === "details"
  && n.find((m) => m.tagName === "h3" && text(m) === name).length > 0)[0];
const summaryOf = (cardNode) => text(sub(cardNode, "cd-sum"));
const winnerNode = (root) => byClass(root, "en-big")[0];
const metaLine = (root, label) => byClass(panelOf(root), "meta")[0].find((n) => n.tagName === "div"
  && n.find((m) => m.tagName === "dt" && text(m) === label).length > 0)[0];
const ddOf = (line) => line.find((n) => n.tagName === "dd")[0];

const E = (over) => entry({ key: "effortLevel", scope: "main", ...over });

test("trail: the panel follows the tiles, with the four cards in the order of the screen", () => {
  const { root } = mount(real("effort-lowered-by-cap"), "@main", "effortLevel");
  assert.deepEqual(root.childNodes.map((n) => n.getAttribute("class").split(" ")[0]), ["ph", "tiles", "trail-a"]);
  const panel = panelOf(root);
  assert.equal(panel.tagName, "div");
  assert.ok(hasClass(panel, "trail-a"));
  const title = byClass(panel, "tr-title")[0];
  assert.equal(title.tagName, "h2");
  assert.equal(text(title), "What decides the main session's effort");
  assert.equal(title.getAttribute("tabindex"), "-1");
  assert.deepEqual(panel.find((n) => n.tagName === "h3").map(text), ["Winner", "Rules behind this value", "Files read"]);
  assert.ok(cardOf(root, "Winner").open, "the winner is open");
  assert.ok(!cardOf(root, "Rules behind this value").open, "the rules are closed");
  assert.ok(!cardOf(root, "Files read").open, "the files are closed");
  const kids = panel.childNodes.map((n) => n.getAttribute("class").split(" ")[0]);
  assert.deepEqual(kids.slice(0, 2), ["tr-title", "meta"]);
  // The tile of the open row is marked as current, and only that one.
  const current = tilesOf(root).filter((n) => n.getAttribute("aria-current") === "true");
  assert.deepEqual(current.map((n) => n.getAttribute("data-setting")), ["effortLevel"]);
});

test("trail: the winner shows its value, status word and mark, source, layer and reason", () => {
  const payload = trailPayload([
    E({ value: "xhigh", status: "lowered", becomes: "high", layer: "local", file: "~/app/.claude/settings.local.json", line: 3,
      reason: "xhigh runs as high, because of --effort.", rule_ids: ["a"] }),
  ], [ruleRec("a")]);
  const { root } = mount(payload, "@main", "effortLevel");
  const win = winnerNode(root);
  assert.equal(win.getAttribute("data-status"), "lowered");
  assert.equal(text(sub(win, "val")), "xhigh");
  const chip = sub(win, "st");
  assert.equal(text(chip), "Lowered");
  assert.equal(chip.find((n) => hasClass(n, "mk")).length, 1);
  assert.equal(text(sub(win, "runs")), "Runs as high");
  assert.equal(text(sub(win, "ly")), "Local settings");
  assert.equal(text(sub(win, "pa")), "~/app/.claude/settings.local.json, line 3");
  assert.equal(text(sub(win, "en-rs")), "Reasonxhigh runs as high, because of --effort.");
  assert.equal(sub(win, "en-rs").find((n) => hasClass(n, "nw")).length, 1, "flags stay on one line");
  assert.deepEqual(win.find((n) => hasClass(n, "sr")).map(text), ["Value", "Status", "Source", "Reason"]);
  assert.equal(summaryOf(cardOf(root, "Winner")), "xhigh Lowered, ~/app/.claude/settings.local.json, line 3");
  assert.equal(win.parentNode.getAttribute("class"), "win");
});

test("trail: a Lowered value runs as the cap, from the real fixture", () => {
  const payload = real("effort-lowered-by-cap");
  const { root } = mount(payload, "@main", "effortLevel");
  const winner = payload.entries.find((e) => e.scope === "main" && e.key === "effortLevel");
  assert.equal(text(sub(winnerNode(root), "runs")), "Runs as " + winner.becomes);
  assert.equal(text(sub(winnerNode(root), "st")), "Lowered");
  const model = tileFor(root, "model");
  assert.equal(sub(model, "runs"), undefined, "a tile of another row has no runs line");
});

test("trail: other values are cards, and the count leaves the winner out", () => {
  const lost = [
    E({ value: "medium", status: "overridden", layer: "project", file: "p.json", line: 7, reason: "r1" }),
    E({ value: "xhigh", status: "ignored", layer: "user", file: "u.json", line: 3, reason: "r2" }),
  ];
  const { root } = mount(trailPayload([E({ value: "high" }), ...lost]), "@main", "effortLevel");
  const others = cardOf(root, "Other values found");
  assert.ok(others.open);
  assert.equal(summaryOf(others), "2 values, 2 didn't count");
  const cards = byClass(others, "en-card");
  assert.deepEqual(cards.map((n) => n.getAttribute("data-status")), ["overridden", "ignored"]);
  assert.equal(byClass(others, "ens").length, 1);
  assert.deepEqual(cards.map((n) => text(sub(n, "val"))), ["medium", "xhigh"]);
  assert.deepEqual(cards.map((n) => text(sub(n, "ly"))), ["Project settings", "User settings"]);
  assert.deepEqual(cards.map((n) => text(sub(n, "pa"))), ["p.json, line 7", "u.json, line 3"]);
  assert.equal(byClass(winnerNode(root), "en-card").length, 0);
});

test("trail: the count words, one value and none that lost", () => {
  const sum = (entries) => summaryOf(cardOf(mount(trailPayload(entries), "@main", "effortLevel").root, "Other values found"));
  const win = E({ value: "high" });
  const lost = (status) => E({ value: "low", status, layer: "project", file: "p.json" });
  assert.equal(sum([win, lost("overridden")]), "1 value, 1 didn't count");
  assert.equal(sum([win, lost("invalid")]), "1 value, 1 didn't count");
  assert.equal(sum([win, lost("default")]), "1 value");
  assert.equal(sum([win, lost("default"), lost("default")]), "2 values");
  assert.equal(sum([win, lost("overridden"), lost("default")]), "2 values, 1 didn't count");
  assert.equal(sum([win, lost("overridden"), lost("ignored"), lost("invalid")]), "3 values, 3 didn't count");
  const single = mount(trailPayload([win]), "@main", "effortLevel").root;
  assert.equal(cardOf(single, "Other values found"), undefined, "a row with one entry has no other values");
});

test("trail: a shell source carries the note, and a file source does not", () => {
  const payload = real("prompt-cache-force-5m-over-everything");
  const { root } = mount(payload, "@main", "promptCacheTtl");
  const note = STRINGS.shell_note;
  assert.equal(note, "Read when the dashboard started. A session from another terminal may differ.");
  const entries = byClass(root, "en");
  assert.equal(entries.length, 4);
  const noted = entries.map((n) => (sub(n, "en-note") ? text(sub(n, "en-note")) : null));
  // The winner and the next one come from the shell, the user file does not, and the default came through a shell variable.
  assert.deepEqual(noted, [note, note, null, note]);
  const win = winnerNode(root);
  const kids = win.childNodes.map((n) => n.getAttribute("class").split(" ")[0]);
  assert.deepEqual(kids, ["en-top", "en-src", "en-rs", "en-note"], "the note sits beside the reason");
  assert.equal(entries.filter((n) => n.find((m) => m.tagName === "p" && hasClass(m, "en-note")).length).length, 3);
});

test("trail: a value through a variable names the variable and where it was set", () => {
  const forced = mount(real("prompt-cache-force-5m-over-everything"), "@main", "promptCacheTtl").root;
  const sources = byClass(forced, "en").map((n) => text(sub(n, "pa")));
  assert.equal(sources[0], "Set by FORCE_PROMPT_CACHING_5M in the shell");
  assert.equal(sources[1], "Set by CLAUDE_CODE_PROMPT_CACHE_TTL in the shell");
  assert.match(sources[2], /^config\/settings\.json, line \d+$/);
  // A default with a via takes the source of the variable's own row.
  assert.equal(sources[3], "Set by ENABLE_PROMPT_CACHING_1H in the shell");
  const block = mount(real("env-block-over-shell"), "@main", "model").root;
  const win = winnerNode(block);
  assert.match(text(sub(win, "pa")), /^Set by ANTHROPIC_MODEL in the env block of config\/settings\.json, line \d+$/);
  assert.equal(text(sub(win, "ly")), "User settings", "an env block value takes the layer of its file");
  assert.equal(sub(win, "en-note"), undefined, "a settings file is not the shell");
});

test("source: a default with a via reads from the variable's row, and stays the default without one", () => {
  const shellRow = entry({ key: "env.ENABLE_X", value: "1", layer: "env", file: "Shell", line: undefined });
  const blockRow = entry({ key: "env.ENABLE_X", value: "1", layer: "user", file: "~/.claude/settings.json", line: 5 });
  const viaDefault = entry({ key: "promptCacheTtl", value: "1h", file: null, layer: "default", status: "default", via: "ENABLE_X", line: undefined });
  assert.equal(settings.sourceText(viaDefault, handPayload([shellRow, viaDefault])), "Set by ENABLE_X in the shell");
  assert.equal(settings.sourceText(viaDefault, handPayload([blockRow, viaDefault])),
    "Set by ENABLE_X in the env block of ~/.claude/settings.json, line 5");
  assert.equal(settings.sourceText(viaDefault, handPayload([viaDefault])), "Claude Code's default");
  const other = entry({ key: "env.OTHER", value: "1", layer: "env", file: "Shell", line: undefined });
  assert.equal(settings.sourceText(viaDefault, handPayload([other, viaDefault])), "Claude Code's default");
  // The tile on the Settings page reads the same way.
  const tileRoot = show(handPayload([blockRow, { ...viaDefault, key: "promptCacheTtl" }]));
  assert.equal(text(sub(tileFor(tileRoot, "promptCacheTtl"), "tl-src")), "~/.claude/settings.json, line 5");
  // Short drops the variable, and a default with a via still resolves through its row.
  assert.equal(settings.sourceText(viaDefault, handPayload([shellRow, viaDefault]), true), "Shell");
  assert.equal(settings.sourceText(viaDefault, handPayload([blockRow, viaDefault]), true), "~/.claude/settings.json, line 5");
  assert.equal(settings.sourceText(viaDefault, handPayload([viaDefault]), true), "Claude Code's default");
  assert.equal(settings.sourceText(entry({ file: "a/b.json", line: 7, via: "X" }), handPayload([]), true), "a/b.json, line 7");
});

test("trail: a hidden value shows the word, with its explanation", () => {
  const payload = trailPayload([
    E({ value: "hidden", status: "invalid" }),
    E({ value: "hidden", status: "overridden", layer: "project", file: "p.json" }),
  ]);
  const { root } = mount(payload, "@main", "effortLevel");
  for (const node of [winnerNode(root), byClass(root, "en-card")[0]]) {
    const val = sub(node, "val");
    assert.equal(text(val), "hidden");
    assert.equal(val.find((n) => n.getAttribute("title") === STRINGS.hidden_desc).length, 1);
  }
  assert.equal(summaryOf(cardOf(root, "Winner")).startsWith("hidden Invalid, "), true);
});

test("trail: an empty value and a missing value", () => {
  const empty = mount(trailPayload([E({ value: "" })]), "@main", "effortLevel").root;
  assert.equal(text(sub(winnerNode(empty), "val")), "empty");
  const none = mount(trailPayload([E({ value: null, status: "unknown" })]), "@main", "effortLevel").root;
  assert.equal(sub(winnerNode(none), "val"), undefined);
  assert.deepEqual(winnerNode(none).find((n) => hasClass(n, "sr")).map(text), ["Status", "Source", "Reason"]);
});

test("trail: Assumed reads differently from Documented and Tested", () => {
  const entries = [E({ rule_ids: ["t1", "d1", "a1", "a2", "t2"] })];
  const rules = [ruleRec("t1"), ruleRec("d1", { confidence: "documented" }), ruleRec("a1", { confidence: "assumed" }),
    ruleRec("a2", { confidence: "assumed" }), ruleRec("t2")];
  const { root } = mount(trailPayload(entries, rules), "@main", "effortLevel");
  const items = byClass(cardOf(root, "Rules behind this value"), "ru");
  assert.deepEqual(items.map((n) => n.getAttribute("class")), ["ru ru-tested", "ru ru-documented", "ru ru-assumed", "ru ru-assumed", "ru ru-tested"]);
  assert.deepEqual(items.map((n) => text(sub(n, "cf"))), ["Tested", "Documented", "Assumed", "Assumed", "Tested"]);
  assert.deepEqual(items.map((n) => sub(n, "cf").getAttribute("class")),
    ["cf cf-tested", "cf cf-documented", "cf cf-assumed", "cf cf-assumed", "cf cf-tested"]);
  assert.deepEqual(items.map((n) => (sub(n, "ru-def") ? text(sub(n, "ru-def")) : null)),
    [null, null, STRINGS.assumed_def, STRINGS.assumed_def, null]);
  assert.equal(summaryOf(cardOf(root, "Rules behind this value")), "5 rules, 2 Tested, 1 Documented, 2 Assumed");
});

test("trail: the rule summary words, one rule and the order Tested, Documented, Assumed", () => {
  const one = mount(trailPayload([E({ rule_ids: ["a1"] })], [ruleRec("a1", { confidence: "assumed" })]), "@main", "effortLevel").root;
  assert.equal(summaryOf(cardOf(one, "Rules behind this value")), "1 rule, 1 Assumed");
  const mixed = mount(trailPayload([E({ rule_ids: ["a", "d", "t"] })],
    [ruleRec("a", { confidence: "assumed" }), ruleRec("d", { confidence: "documented" }), ruleRec("t")]), "@main", "effortLevel").root;
  assert.equal(summaryOf(cardOf(mixed, "Rules behind this value")), "3 rules, 1 Tested, 1 Documented, 1 Assumed");
  const none = mount(trailPayload([E({ rule_ids: ["gone"] })], []), "@main", "effortLevel").root;
  assert.equal(cardOf(none, "Rules behind this value"), undefined, "no rule record, no rules card");
});

test("trail: each rule links to the reference page and shows its check, quotes and experiment", () => {
  const rule = ruleRec("effort-level-layer-order", {
    quotes: [
      { doc_url: "https://code.claude.com/docs/en/settings-reference#effortlevel",
        quote: "`--effort` takes precedence over this key, and `CLAUDE_CODE_EFFORT_LEVEL` over both" },
      { doc_url: "https://code.claude.com/docs/en/model-config#set-the-effort-level", quote: "Second quote." },
    ],
    experiment: "experiments/2026-10-29-effort-level-order.json",
    experiment_url: EXP + "experiments/2026-10-29-effort-level-order.json",
  });
  const { root } = mount(trailPayload([E({ rule_ids: [rule.rule_id] })], [rule]), "@main", "effortLevel");
  const item = byClass(cardOf(root, "Rules behind this value"), "ru")[0];
  const link = sub(item, "ru-id");
  assert.equal(link.tagName, "a");
  assert.equal(text(link), "effort-level-layer-order");
  assert.equal(link.getAttribute("href"), REF + "#effort-level-layer-order");
  assert.equal(link.getAttribute("target"), "_blank");
  assert.equal(link.getAttribute("rel"), "noopener noreferrer");
  assert.equal(link.getAttribute("aria-label"), "effort-level-layer-order, on the rules reference page");
  assert.equal(text(sub(item, "ru-ck")), "Checked on Claude Code 2.1.302, October 29, 2026");
  const quotes = sub(item, "qd");
  assert.equal(quotes.tagName, "details");
  assert.equal(text(quotes.find((n) => n.tagName === "summary")[0]), "From the docs (2)");
  assert.ok(!quotes.open, "the quotes are closed");
  const lis = quotes.find((n) => n.tagName === "li");
  assert.equal(lis.length, 2);
  const doc = lis[0].find((n) => n.tagName === "a")[0];
  assert.equal(doc.getAttribute("href"), "https://code.claude.com/docs/en/settings-reference#effortlevel");
  assert.equal(text(doc), "code.claude.com/docs/en/settings-reference#effortlevel");
  const q = lis[0].find((n) => n.tagName === "q")[0];
  assert.equal(text(q), "--effort takes precedence over this key, and CLAUDE_CODE_EFFORT_LEVEL over both");
  assert.equal(q.find((n) => hasClass(n, "nw")).length, 1);
  assert.equal(text(lis[1].find((n) => n.tagName === "q")[0]), "Second quote.");
  const exp = sub(item, "ru-x");
  assert.equal(text(sub(exp, "ru-l")), "Experiment record");
  const expLink = exp.find((n) => n.tagName === "a")[0];
  assert.equal(expLink.getAttribute("href"), EXP + "experiments/2026-10-29-effort-level-order.json");
  assert.equal(text(expLink), "dashboard/experiments/2026-10-29-effort-level-order.json");
});

test("trail: a rule marked due reads as due for a new check, and the others read as checked", () => {
  const due = ruleRec("old", { due: true });
  const fine = ruleRec("fine", { due: false });
  const plain = ruleRec("plain");
  const { root } = mount(trailPayload([E({ rule_ids: ["old", "fine", "plain"] })], [due, fine, plain],
    { installed: "2.1.310" }), "@main", "effortLevel");
  const [first, second, third] = byClass(cardOf(root, "Rules behind this value"), "ru");
  assert.equal(text(sub(first, "ru-ck")),
    "Checked on Claude Code 2.1.302, October 29, 2026. You have 2.1.310, so this rule is due for a new check.");
  assert.equal(text(sub(second, "ru-ck")), "Checked on Claude Code 2.1.302, October 29, 2026");
  assert.equal(text(sub(third, "ru-ck")), "Checked on Claude Code 2.1.302, October 29, 2026");
  // ruleItem is exported and takes the installed version as its second argument.
  const node = trail.ruleItem(due, "2.2.0");
  assert.match(text(sub(node, "ru-ck")), /You have 2\.2\.0, so this rule is due for a new check\.$/);
  assert.doesNotMatch(text(sub(trail.ruleItem(fine, "2.2.0"), "ru-ck")), /due/);
});

test("trail: a rule with no quotes and no experiment leaves those parts out", () => {
  const { root } = mount(trailPayload([E({ rule_ids: ["a"] })], [ruleRec("a")]), "@main", "effortLevel");
  const item = byClass(cardOf(root, "Rules behind this value"), "ru")[0];
  assert.equal(sub(item, "qd"), undefined);
  assert.equal(sub(item, "ru-x"), undefined);
});

test("trail: a link only goes in when it passes the external pattern", () => {
  const rule = ruleRec("bad", {
    reference_url: "javascript:alert(1)",
    quotes: [{ doc_url: "http://code.claude.com/x", quote: "q" }, { doc_url: "//evil.example/x", quote: "q2" },
      { doc_url: "https://ok.example/a\nb", quote: "q3" }, { doc_url: "https://user:pw@evil.example/x", quote: "q4" },
      { doc_url: "https://ok.example\\@evil.example/x", quote: "q5" }],
    experiment: "experiments/x.json", experiment_url: "/etc/passwd",
  });
  const { root } = mount(trailPayload([E({ rule_ids: ["bad"] })], [rule]), "@main", "effortLevel");
  const item = byClass(cardOf(root, "Rules behind this value"), "ru")[0];
  const links = item.find((n) => n.tagName === "a");
  assert.equal(links.length, 7);
  for (const a of links) {
    assert.equal(a.getAttribute("href"), null);
    assert.equal(a.getAttribute("target"), null);
  }
  assert.equal(text(links[0]), "bad", "the text still shows");
});

test("trail: the model line shows the display name with its catalog id", () => {
  const entries = [
    entry({ key: "model", value: "claude-opus-5-5" }),
    E({ value: "high" }),
  ];
  const { root } = mount(trailPayload(entries), "@main", "effortLevel");
  const line = metaLine(root, "Model");
  assert.equal(text(ddOf(line)), "Opus 5.5 (claude-opus-5-5)");
  const alias = mount(trailPayload([entry({ key: "model", value: "opus" }), E({ value: "high" })]), "@main", "effortLevel").root;
  assert.equal(text(ddOf(metaLine(alias, "Model"))), "Opus 5.5 (opus)");
  const unlisted = mount(trailPayload([entry({ key: "model", value: "claude-zz-1" }), E({ value: "high" })]), "@main", "effortLevel").root;
  assert.equal(text(ddOf(metaLine(unlisted, "Model"))), "claude-zz-1 (not in the dashboard's model list)");
  // The model row has its own model line, and a row without a model row has none.
  const modelRow = mount(trailPayload(entries), "@main", "model").root;
  assert.equal(text(ddOf(metaLine(modelRow, "Model"))), "Opus 5.5 (claude-opus-5-5)");
  assert.equal(byClass(modelRow, "meta")[0].find((n) => n.tagName === "dt").map(text).join(","), "Model");
  const noModel = mount(trailPayload([E({ value: "high" })]), "@main", "effortLevel").root;
  assert.equal(byClass(noModel, "meta").length, 0, "no model row, no cap row, no meta block");
});

test("trail: the effort cap line shows the cap, its status and its source", () => {
  const entries = [
    entry({ key: "model", value: "claude-opus-5-5" }),
    entry({ key: "maxEffortLevel", value: "high", layer: "project", file: "~/app/.claude/settings.json", line: 3 }),
    E({ value: "xhigh", status: "lowered", becomes: "high" }),
  ];
  const { root } = mount(trailPayload(entries), "@main", "effortLevel");
  const dd = ddOf(metaLine(root, "Effort cap"));
  assert.equal(text(sub(dd, "val")), "high");
  assert.equal(text(sub(dd, "st")), "In effect");
  assert.equal(text(sub(dd, "src")), "Project settings, ~/app/.claude/settings.json, line 3");
  // The cap line is for effort rows alone.
  const model = mount(trailPayload(entries), "@main", "model").root;
  assert.equal(metaLine(model, "Effort cap"), undefined);
});

test("trail: no cap reads 'not set' for a default and for a missing value", () => {
  const model = entry({ key: "model", value: "claude-opus-5-5" });
  const asDefault = entry({ key: "maxEffortLevel", value: null, status: "default", layer: "default", file: null, line: undefined });
  const dd = ddOf(metaLine(mount(trailPayload([model, asDefault, E({ value: "high" })]), "@main", "effortLevel").root, "Effort cap"));
  assert.equal(text(dd), "not set");
  const unknownCap = entry({ key: "maxEffortLevel", value: null, status: "unknown", layer: "default", file: null, line: undefined });
  const dd2 = ddOf(metaLine(mount(trailPayload([model, unknownCap, E({ value: "high" })]), "@main", "effortLevel").root, "Effort cap"));
  assert.equal(text(dd2), "not set");
  const real_ = mount(real("model-main-default-unknown"), "@main", "effortLevel").root;
  assert.ok(panelOf(real_));
});

test("trail: an agent row opens at #/settings/probe/effort with its own title and model line", () => {
  const payload = real("agent-effort-default-fable-5-1");
  const { root } = mount(payload, "probe", "effort");
  assert.equal(text(byClass(root, "tr-title")[0]), "What decides the effort for probe");
  assert.equal(text(ddOf(metaLine(root, "Model"))), "Fable 5.1 (claude-fable-5-1)");
  assert.equal(metaLine(root, "Effort cap"), undefined, "an agent on another model than @main has no cap line");
  assert.equal(summaryOf(cardOf(root, "Winner")), "high Default, Claude Code's default");
  assert.equal(tilesOf(root).filter((n) => n.getAttribute("aria-current") === "true").length, 0, "no tile is current");
  assert.equal(tilesOf(root).length, 4, "the main session tiles still show");
  assert.equal(router.parseHash("#/settings/probe/effort?project=app").name, "trail");
});

test("trail: an agent row shows the cap line only when its model is the main session's", () => {
  const cap = entry({ key: "maxEffortLevel", value: "high", layer: "project", file: "~/app/.claude/settings.json", line: 3 });
  const mainModel = entry({ key: "model", value: "claude-opus-5-5" });
  const agentEffort = (agentModel) => [mainModel, cap,
    entry({ key: "model", agent: "builder", value: agentModel }),
    entry({ key: "effort", agent: "builder", value: "xhigh", status: "lowered", becomes: "high" })];
  const same = mount(trailPayload(agentEffort("claude-opus-5-5")), "builder", "effort").root;
  assert.equal(text(sub(ddOf(metaLine(same, "Effort cap")), "val")), "high");
  const other = mount(trailPayload(agentEffort("claude-fable-5-1")), "builder", "effort").root;
  assert.equal(metaLine(other, "Effort cap"), undefined);
  assert.ok(metaLine(other, "Model"), "the model line stays");
  const main = mount(trailPayload([mainModel, cap, E({ value: "xhigh" })]), "@main", "effortLevel").root;
  assert.ok(metaLine(main, "Effort cap"), "an @main row always shows the cap line");
});

test("layer: an env block value takes the layer of its file, and a shell value has none", () => {
  const block = entry({ layer: "env", file: "~/app/.claude/settings.local.json", line: 3, via: "X" });
  const files = [{ path: "~/app/.claude/settings.local.json", layer: "local" }];
  assert.equal(settings.layerText(block, { files }), "Local settings");
  assert.equal(settings.layerText(block), "");
  assert.equal(settings.layerText(block, { files: [] }), "");
  assert.equal(settings.layerText(entry({ layer: "env", file: "Shell" }), { files }), "");
  assert.equal(settings.layerText(entry({ layer: "user" }), { files }), "User settings");
  const win = winnerNode(mount(trailPayload([block], [], { files }), "@main", "effortLevel").root);
  assert.equal(text(sub(win, "ly")), "Local settings");
  const shell = entry({ layer: "env", file: "Shell", line: undefined });
  assert.equal(sub(winnerNode(mount(trailPayload([shell], [], { files }), "@main", "effortLevel").root), "ly"), undefined);
});

test("trail: an agent file row has no value and names the agent file", () => {
  const payload = real("agent-effort-default-fable-5-1");
  const { root } = mount(payload, "probe", "agentFile");
  assert.equal(text(byClass(root, "tr-title")[0]), "What decides the agent file for probe");
  const win = winnerNode(root);
  assert.equal(sub(win, "val"), undefined);
  assert.equal(text(sub(win, "st")), "In effect");
  assert.equal(text(sub(win, "ly")), "User settings");
  assert.equal(summaryOf(cardOf(root, "Winner")), "In effect, config/agents/probe.md, line 2");
  assert.equal(summaryOf(cardOf(root, "Rules behind this value")), "2 rules, 1 Tested, 1 Documented");
});

test("trail: assumed rules on a real agent row", () => {
  const { root } = mount(real("agent-effort-default-fable-5-1"), "probe", "autoCompactWindow");
  const items = byClass(cardOf(root, "Rules behind this value"), "ru");
  assert.equal(items.length, 2);
  for (const item of items) {
    assert.ok(hasClass(item, "ru-assumed"));
    assert.equal(text(sub(item, "ru-def")), STRINGS.assumed_def);
  }
});

test("trail: a row the payload does not have shows the head and tiles and no panel", () => {
  for (const [agent, setting] of [["@main", "noSuchSetting"], ["ghost", "effort"], ["@main", "env.NOPE"]]) {
    const { root } = mount(real("effort-lowered-by-cap"), agent, setting);
    assert.equal(panelOf(root), undefined, agent + "/" + setting);
    assert.deepEqual(root.childNodes.map((n) => n.getAttribute("class").split(" ")[0]), ["ph", "tiles"]);
    assert.equal(tilesOf(root).length, 4);
    assert.equal(tilesOf(root).filter((n) => n.getAttribute("aria-current") === "true").length, 0);
  }
});

test("trail: All projects shows the picker and no panel", () => {
  const { root } = mount(real("effort-lowered-by-cap"), "@main", "effortLevel", { project: { key: "all", name: "All projects" } });
  assert.equal(panelOf(root), undefined);
  assert.deepEqual(root.find((n) => hasClass(n, "cd-h")).map(text), ["Pick a project"]);
  assert.equal(tilesOf(root).length, 0);
  assert.equal(text(root.find((n) => n.tagName === "h1")[0]), "Settings");
});

test("trail: no payload, a refused payload and a missing folder show no panel", () => {
  for (const res of [null, { ok: false, status: 404, data: null }, { ok: false, status: 500, data: null }]) {
    const { root } = mount(null, "@main", "effortLevel", { res });
    assert.equal(root.childNodes.length, 1);
    assert.ok(hasClass(root.childNodes[0], "ph"));
  }
  const missing = trailPayload([], [], { state: "missing_folder" });
  const { root } = mount(missing, "@main", "effortLevel", { project: { key: "lantern", name: "Lantern" } });
  assert.equal(panelOf(root), undefined);
  assert.deepEqual(root.find((n) => hasClass(n, "cd-h")).map(text), ["Folder not found"]);
  assert.equal(root.childNodes.length, 2, "the head and the message");
});

test("trail: the files read card counts the files and marks a file that did not parse", () => {
  const { root } = mount(real("settings-user-not-json-skipped"), "@main", "model");
  const files = cardOf(root, "Files read");
  assert.equal(summaryOf(files), "2 files, 1 Ignored");
  const items = byClass(files, "fl");
  assert.equal(items.length, 2);
  assert.deepEqual(items.map((n) => text(sub(n, "ly"))), ["Project settings", "User settings"]);
  assert.deepEqual(items.map((n) => text(sub(n, "pa"))), ["project/.claude/settings.json", "config/settings.json"]);
  assert.equal(text(sub(items[0], "st")), "Read");
  assert.equal(sub(items[0], "st").getAttribute("class"), "st st-read");
  assert.equal(text(sub(items[1], "st")), "Ignored");
  assert.equal(sub(items[1], "st").getAttribute("class"), "st st-ignored");
  // The settings file row opens too.
  const row = mount(real("settings-user-not-json-skipped"), "@main", "settingsFile").root;
  assert.equal(text(byClass(row, "tr-title")[0]), "What decides the main session's settings file");
  assert.equal(text(sub(winnerNode(row), "st")), "Ignored");
});

test("trail: the files summary words and no card when no file exists", () => {
  const file = (over) => ({ layer: "user", path: "~/.claude/settings.json", status: "ok", ...over });
  const sum = (files) => cardOf(mount(trailPayload([E({ value: "high" })], [], { files }), "@main", "effortLevel").root, "Files read");
  assert.equal(summaryOf(sum([file()])), "1 file");
  assert.equal(summaryOf(sum([file(), file({ layer: "project" }), file({ layer: "local" })])), "3 files");
  assert.equal(summaryOf(sum([file({ status: "unreadable", entry_status: "unknown" })])), "1 file, 1 Unknown");
  assert.equal(summaryOf(sum([file(), file({ status: "unparsed", entry_status: "ignored" })])), "2 files, 1 Ignored");
  assert.equal(sum([]), undefined);
  const managed = cardOf(mount(trailPayload([E({ value: "high" })], [], { files: [file({ layer: "managed" })] }), "@main", "effortLevel").root, "Files read");
  assert.equal(text(sub(managed, "ly")), "Managed settings");
});

test("trail: the demo's effort trail has winner, losers, rules and file lines", () => {
  const payload = trailPayload([
    entry({ key: "model", value: "claude-opus-5-5", line: 2 }),
    entry({ key: "maxEffortLevel", value: "high", layer: "project", file: "projects/tidewater/.claude/settings.json", line: 3 }),
    E({ value: "xhigh", status: "lowered", becomes: "high", layer: "env", via: "CLAUDE_CODE_EFFORT_LEVEL",
      file: "projects/tidewater/.claude/settings.local.json", line: 3, rule_ids: ["effort-lowered-by-cap", "effort-level-layer-order"] }),
    E({ value: "medium", status: "overridden", layer: "project", file: "projects/tidewater/.claude/settings.json", line: 7, rule_ids: ["effort-level-layer-order"] }),
    E({ value: "xhigh", status: "ignored", layer: "user", file: "config/settings.json", line: 3, rule_ids: ["effort-level-user-settings-opus-5-5"] }),
  ], [ruleRec("effort-lowered-by-cap"), ruleRec("effort-level-layer-order"), ruleRec("effort-level-user-settings-opus-5-5")]);
  const { root } = mount(payload, "@main", "effortLevel");
  assert.equal(summaryOf(cardOf(root, "Winner")),
    "xhigh Lowered, projects/tidewater/.claude/settings.local.json, line 3");
  assert.equal(summaryOf(cardOf(root, "Other values found")), "2 values, 2 didn't count");
  assert.deepEqual(byClass(cardOf(root, "Other values found"), "pa").map(text),
    ["projects/tidewater/.claude/settings.json, line 7", "config/settings.json, line 3"]);
  assert.equal(summaryOf(cardOf(root, "Rules behind this value")), "3 rules, 3 Tested");
  assert.equal(text(sub(ddOf(metaLine(root, "Effort cap")), "src")), "Project settings, projects/tidewater/.claude/settings.json, line 3");
});

// ---------------------------------------------------------------- the trail: keys and focus

test("keys: a tile is an anchor, so Enter opens its trail through the route", () => {
  const root = show(handPayload(FOUR));
  for (const key of ["model", "effortLevel", "promptCacheTtl", "autoCompactWindow"]) {
    const tile = tileFor(root, key);
    assert.equal(tile.tagName, "a");
    const parsed_ = router.parseHash(tile.getAttribute("href"));
    assert.equal(parsed_.name, "trail");
    assert.deepEqual(parsed_.params, { agent: "@main", setting: key });
  }
  assert.deepEqual(router.parseHash("#/settings/builder/effort").params, { agent: "builder", setting: "effort" });
});

// Draws the Settings route when the hash changes to it, as the app does for every route change.
function followHash(m, settingsRoot) {
  m.page.win.addEventListener("hashchange", () => {
    const next = { ...m.ctx, route: { name: "settings", params: {} } };
    settings.render(settingsRoot, next);
    trail.render(m.root, next);
  });
}
const escape = (m, extra = {}) => m.page.doc.dispatch("keydown", { key: "Escape", ...extra });

test("keys: Escape closes the trail and puts focus back on the cell", () => {
  const m = mount(real("effort-lowered-by-cap"), "@main", "effortLevel");
  const settingsRoot = m.page.sections.settings;
  followHash(m, settingsRoot);
  assert.equal(FElement.focused, byClass(m.root, "tr-title")[0]);
  escape(m);
  assert.equal(m.page.win.location.hash, "#/settings?project=app");
  assert.equal(FElement.focused, tileFor(settingsRoot, "effortLevel"));
  assert.equal(panelOf(m.root), undefined, "the trail is gone");
  assert.equal(byClass(settingsRoot, "tl").length, 4);
  // A later render of Settings does not move focus again.
  const moved = FElement.focused;
  const other = tileFor(settingsRoot, "model");
  FElement.focused = other;
  settings.render(settingsRoot, { ...m.ctx, route: { name: "settings", params: {} } });
  assert.equal(FElement.focused, other);
  assert.notEqual(moved, null);
});

test("keys: Escape on a row with no cell puts focus on the Settings heading", () => {
  const m = mount(real("agent-effort-default-fable-5-1"), "probe", "effort");
  const settingsRoot = m.page.sections.settings;
  followHash(m, settingsRoot);
  escape(m);
  assert.equal(m.page.win.location.hash, "#/settings?project=app");
  const h1 = settingsRoot.find((n) => n.tagName === "h1")[0];
  assert.equal(FElement.focused, h1);
  assert.equal(h1.getAttribute("tabindex"), "-1");
  // A main row without a tile, such as the cap, does the same.
  const cap = mount(real("agent-effort-default-fable-5-1"), "@main", "maxEffortLevel");
  const capRoot = cap.page.sections.settings;
  followHash(cap, capRoot);
  escape(cap);
  assert.equal(FElement.focused, capRoot.find((n) => n.tagName === "h1")[0]);
});

test("keys: Escape does nothing while the sidebar panel is open", () => {
  const m = mount(real("effort-lowered-by-cap"), "@main", "effortLevel");
  m.page.win.location.hash = "#/settings/@main/effortLevel?project=app";
  m.page.sidebar.classList.add("is-open");
  escape(m);
  assert.equal(m.page.win.location.hash, "#/settings/@main/effortLevel?project=app");
  m.page.sidebar.classList.remove("is-open");
  escape(m);
  assert.equal(m.page.win.location.hash, "#/settings?project=app");
});

test("keys: Escape is left alone when it was handled, is another key, or the trail is not showing", () => {
  const m = mount(real("effort-lowered-by-cap"), "@main", "effortLevel");
  m.page.win.location.hash = "#/settings/@main/effortLevel?project=app";
  const start = m.page.win.location.hash;
  escape(m, { defaultPrevented: true });
  m.page.doc.dispatch("keydown", { key: "Enter" });
  m.page.doc.dispatch("keydown", { key: "Tab" });
  assert.equal(m.page.win.location.hash, start);
  m.root.hidden = true;
  escape(m);
  assert.equal(m.page.win.location.hash, start, "the section is hidden");
  m.root.hidden = false;
  trail.render(m.root, { ...m.ctx, route: { name: "settings", params: {} } });
  escape(m);
  assert.equal(m.page.win.location.hash, start, "another route is showing");
});

test("keys: the listener is added once per document, however often the trail draws", () => {
  const m = mount(real("effort-lowered-by-cap"), "@main", "effortLevel");
  for (let i = 0; i < 4; i += 1) m.redraw();
  assert.equal((m.page.doc.listeners.keydown || []).length, 1);
});

test("focus: the heading takes focus once on arrival and again after a re-render that rebuilt it", () => {
  const m = mount(real("effort-lowered-by-cap"), "@main", "effortLevel");
  const first = byClass(m.root, "tr-title")[0];
  assert.equal(FElement.focused, first);
  assert.equal(first.focusCalls, 1);
  m.redraw(); // data arrived again, so the page was rebuilt with focus inside it
  const second = byClass(m.root, "tr-title")[0];
  assert.notEqual(second, first);
  assert.equal(FElement.focused, second);
  assert.equal(second.focusCalls, 1);
});

test("focus: a re-render does not take focus from somewhere else", () => {
  const m = mount(real("effort-lowered-by-cap"), "@main", "effortLevel");
  const model = tileFor(m.root, "model");
  model.focus();
  m.redraw();
  assert.equal(FElement.focused, model, "focus stays where the person put it");
  assert.notEqual(FElement.focused, byClass(m.root, "tr-title")[0]);
});

test("focus: a new route key takes focus, and so does coming back to the same key", () => {
  const m = mount(real("effort-lowered-by-cap"), "@main", "effortLevel");
  m.ctx.route = { name: "trail", params: { agent: "@main", setting: "model" } };
  m.redraw();
  assert.equal(FElement.focused, byClass(m.root, "tr-title")[0]);
  assert.equal(text(byClass(m.root, "tr-title")[0]), "What decides the main session's model");
  trail.render(m.root, { ...m.ctx, route: { name: "settings", params: {} } });
  const arrive = byClass(m.root, "tr-title")[0];
  assert.equal(arrive, undefined, "a route away clears the trail");
  FElement.focused = null;
  m.redraw();
  assert.equal(FElement.focused, byClass(m.root, "tr-title")[0]);
});

test("focus: data that arrives after the route takes focus once", () => {
  const page = createPage();
  const first = mount(null, "@main", "effortLevel", { page });
  assert.equal(FElement.focused, null, "no panel yet, so no focus");
  first.ctx.data = { settings: { ok: true, status: 200, data: real("effort-lowered-by-cap") } };
  first.redraw();
  const title = byClass(first.root, "tr-title")[0];
  assert.equal(FElement.focused, title);
  assert.equal(title.focusCalls, 1);
});

test("focus: a row the payload does not have takes no focus", () => {
  mount(real("effort-lowered-by-cap"), "@main", "noSuchSetting");
  assert.equal(FElement.focused, null);
});

// ---------------------------------------------------------------- the trail: text from data

test("trail data: no string from the payload reaches innerHTML, and markup in it shows as text", () => {
  const evil = "<img src=x onerror=alert(1)>";
  const before = parsed.length;
  const payload = trailPayload([
    entry({ key: "model", value: evil }),
    entry({ key: "maxEffortLevel", value: evil, file: evil, layer: "project", line: 1 }),
    E({ value: evil, status: "lowered", becomes: evil, file: evil, line: 2, via: evil, reason: evil, rule_ids: [evil] }),
    E({ value: evil, status: "overridden", file: evil, line: 3, reason: evil, layer: "user" }),
  ], [ruleRec(evil, { quotes: [{ doc_url: evil, quote: evil }], experiment: evil, experiment_url: evil })],
  { files: [{ layer: "user", path: evil, status: "unparsed", entry_status: "ignored" }] });
  const { root } = mount(payload, "@main", "effortLevel");
  assert.deepEqual(parsed.slice(before), []);
  assert.equal(root.find((n) => n.tagName === "img").length, 0);
  assert.ok(text(panelOf(root)).includes(evil));
  const source = fs.readFileSync(new URL("js/pages/trail.js", STATIC), "utf8");
  assert.equal(/innerHTML|outerHTML|insertAdjacentHTML|document\.write/.test(source), false);
  // The unsafe values made no link.
  assert.equal(panelOf(root).find((n) => n.tagName === "a" && n.getAttribute("href") !== null).length, 0);
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

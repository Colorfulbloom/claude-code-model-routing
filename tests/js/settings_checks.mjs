// Browser-free checks of the Settings page, run by tests/test_settings_js.py. They load pages/settings.js
// and the shared modules from dashboard/static/js against the small fake DOM in fakedom.mjs. Nothing here
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
    "Set by CLAUDE_CODE_EFFORT_LEVEL in the env block of ~/work/app/.claude/settings.local.json, line 3");
  assert.equal(text(sub(tileFor(root, "promptCacheTtl"), "tl-src")), "Set by ENABLE_PROMPT_CACHING_1H in the shell");
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

test("the env block of a fixture reads as Set by ... in the env block of ...", () => {
  const root = show(real("env-block-over-shell"));
  const tile = tileFor(root, "model");
  assert.match(text(sub(tile, "tl-src")), /^Set by ANTHROPIC_MODEL in the env block of config\/settings\.json, line \d+$/);
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

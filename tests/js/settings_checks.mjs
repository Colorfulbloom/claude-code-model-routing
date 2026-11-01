// Browser-free checks of the Settings page (the Stat band, the More list and the rail), the band order and its
// trail, run by tests/test_settings_js.py. They load pages/settings.js, pages/band.js, pages/trail.js and the shared
// modules from dashboard/static/js against the small fake DOM in fakedom.mjs. Nothing here
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
const band = await import(JS + "pages/band.js");
const bandOrder = await import(JS + "band_order.js");
const trail = await import(JS + "pages/trail.js");
const where = await import(JS + "pages/where.js");

// The setter below catches any attempt to parse text as markup.
const parsed = [];
Object.defineProperty(FElement.prototype, "innerHTML", { set(v) { parsed.push(String(v)); }, get() { return ""; } });
Object.defineProperty(FElement.prototype, "outerHTML", { set(v) { parsed.push(String(v)); }, get() { return ""; } });

// Renders the page into a fresh section. settingsRes is what ctx.data.settings holds. setting is ?setting=.
function show(payload, { project = { key: "app", name: "App" }, res = null, setting = null, page = createPage(), edit = null } = {}) {
  const root = page.sections.settings;
  const ctx = {
    route: { name: "settings", params: {}, query: { setting } },
    project,
    data: { settings: res || (payload ? { ok: true, status: 200, data: payload } : null) },
    hashFor: (name, params, patch = {}) => router.hashFor(name, params, { project: project.key, ...patch }),
    ...(edit ? { edit: { mode: edit, targets: null, history: null } } : {}),
  };
  settings.render(root, ctx);
  return root;
}

const hasClass = (n, c) => n.classList && n.classList.contains(c);
const byClass = (root, c) => root.find((n) => hasClass(n, c));
// The cells of the band, not the rows of the More list.
const cellsOf = (root) => root.find((n) => n.tagName === "a" && hasClass(n, "s4-stat"));
const cellFor = (root, key) => cellsOf(root).find((n) => n.getAttribute("data-setting") === key);
const rowsOf_ = (root) => root.find((n) => n.tagName === "a" && hasClass(n, "s5-lr"));
const moreOf = (root) => root.find((n) => n.tagName === "button" && hasClass(n, "s5-more"))[0];
const popOf = (root) => byClass(root, "s5-pop")[0];
const text = (n) => n.textContent;
const sub = (cell, c) => byClass(cell, c)[0];
const railOf = (root) => byClass(root, "s4-rail")[0];
// The band draws wide when it has no layout. A check sets the width the nav would measure, then a resize redraws it.
function narrow(page, root, width) {
  byClass(root, "s5-a")[0].clientWidth = width;
  (page.listeners.resize || []).forEach((fn) => fn({}));
}

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

const FIVE = [
  entry({ key: "model", value: "claude-opus-5-5", line: 2 }),
  entry({ key: "effortLevel", value: "high" }),
  entry({ key: "maxEffortLevel", value: null, file: null, status: "default", layer: "default", line: undefined }),
  entry({ key: "autoCompactWindow", value: 1000000, file: null, status: "default", layer: "default", line: undefined }),
  entry({ key: "promptCacheTtl", value: "1h", file: null, status: "default", layer: "default", line: undefined }),
];

// ---------------------------------------------------------------- the band

test("band: five cells, in the order Model, Effort, Effort cap, Compact window, Cache lifetime", () => {
  const root = show(handPayload(FIVE));
  const cells = cellsOf(root);
  assert.deepEqual(cells.map((n) => n.getAttribute("data-setting")), ["model", "effortLevel", "maxEffortLevel", "autoCompactWindow", "promptCacheTtl"]);
  assert.deepEqual(cells.map((n) => text(sub(n, "s4-sl"))), ["Model", "Effort", "Effort cap", "Compact window", "Cache lifetime"]);
  assert.equal(byClass(root, "s5-a").length, 1);
  assert.equal(byClass(root, "s5-a")[0].tagName, "nav");
  assert.equal(byClass(root, "s5-a")[0].getAttribute("aria-label"), STRINGS.band_nav_sr);
  assert.equal(moreOf(root), undefined, "all five fit in a wide band, so there is no More");
  assert.equal(popOf(root), undefined);
  assert.equal(byClass(root, "s5-a")[0].styleMap["--n"], "5");
});

test("band: BAND_SETTINGS in the router holds the same keys as TILES, in the same order", () => {
  assert.deepEqual(router.BAND_SETTINGS, settings.TILES.map((spec) => spec.key));
});

test("band: the page head comes first, a cell links to its setting on the page, and the aria-label says what it does", () => {
  const root = show(handPayload(FIVE));
  const page = root.childNodes[0];
  assert.deepEqual(page.childNodes.map((n) => n.getAttribute("class").split(" ")[0]), ["s4-chead", "s5-band", "s5-w"]);
  assert.equal(page.childNodes[0].childNodes[0].classList.contains("ph"), true);
  assert.equal(text(root.find((n) => n.tagName === "h1")[0]), "Settings");
  assert.equal(text(byClass(root, "intro")[0]), STRINGS.intro_settings);
  const link = cellFor(root, "effortLevel");
  assert.equal(link.tagName, "a");
  assert.equal(link.getAttribute("href"), "#/settings?project=app&setting=effortLevel");
  assert.equal(link.getAttribute("title"), "Effort");
  assert.equal(link.getAttribute("aria-label"), "Effort, high, In effect. " + STRINGS.band_cell_desc);
  assert.equal(router.parseHash(link.getAttribute("href")).query.setting, "effortLevel");
  assert.equal(router.parseHash(link.getAttribute("href")).name, "settings");
});

test("band: every cell shows a mark glyph and a status word, never hue alone", () => {
  const root = show(handPayload(FIVE));
  for (const cell of cellsOf(root)) {
    const chip = sub(cell, "st");
    assert.ok(chip, "a status chip");
    assert.equal(chip.parentNode.getAttribute("class"), "s4-st");
    assert.equal(chip.find((n) => hasClass(n, "mk")).length, 1);
    assert.match(text(chip), /^(In effect|Default|Unknown|Lowered)$/);
  }
  assert.equal(text(sub(cellFor(root, "promptCacheTtl"), "st")), "Default");
});

test("band: the model shows its display name alone, and a name outside the catalog says so", () => {
  const root = show(handPayload(FIVE));
  assert.equal(text(sub(cellFor(root, "model"), "s4-sv")), "Opus 5.5");
  const other = show(handPayload([entry({ key: "model", value: "claude-opus-6-preview" })]));
  assert.equal(text(sub(cellFor(other, "model"), "s4-sv")), "claude-opus-6-preview (not in the dashboard's model list)");
});

test("band: the compact window shows thousands commas, and the screen reader hears them too", () => {
  const root = show(handPayload(FIVE));
  assert.equal(text(sub(cellFor(root, "autoCompactWindow"), "s4-sv")), "1,000,000");
  assert.equal(cellFor(root, "autoCompactWindow").getAttribute("aria-label"), "Compact window, 1,000,000, Default. " + STRINGS.band_cell_desc);
  const small = show(handPayload([entry({ key: "autoCompactWindow", value: 500 })]));
  assert.equal(text(sub(cellFor(small, "autoCompactWindow"), "s4-sv")), "500");
});

test("band: the effort cap reads Not set with no value or with only the default, and Not known with no entry", () => {
  const root = show(handPayload(FIVE));
  assert.equal(text(sub(cellFor(root, "maxEffortLevel"), "s4-sv")), "Not set");
  assert.equal(sub(cellFor(root, "maxEffortLevel"), "s5-sv-none"), undefined, "Not set is a plain value");
  const none = show(handPayload([entry({ key: "maxEffortLevel", value: null, status: "in_effect" })]));
  assert.equal(text(sub(cellFor(none, "maxEffortLevel"), "s4-sv")), "Not set");
  const set = show(handPayload([entry({ key: "maxEffortLevel", value: "high" })]));
  assert.equal(text(sub(cellFor(set, "maxEffortLevel"), "s4-sv")), "high");
  const noEntry = show(handPayload([entry({ key: "model", value: "opus" })]));
  const cell = cellFor(noEntry, "promptCacheTtl");
  assert.equal(text(sub(cell, "s5-sv-none")), "Not known");
  assert.equal(sub(cell, "st"), undefined, "no entry, no status");
  assert.equal(text(sub(cell, "s4-sw")), "");
  assert.equal(cell.getAttribute("aria-label"), "Cache lifetime, Not known. " + STRINGS.band_cell_desc);
});

test("band: a hidden value shows the word with its explanation as the title", () => {
  const root = show(handPayload([entry({ value: "hidden", status: "invalid" })]));
  const value = sub(cellFor(root, "effortLevel"), "s4-sv");
  assert.equal(text(value), "hidden");
  const span = value.find((n) => n.tagName === "span" && n.getAttribute("title"))[0];
  assert.equal(span.getAttribute("title"), STRINGS.hidden_desc);
});

test("band: an empty value shows the word for empty and a null value shows Not known", () => {
  const empty = show(handPayload([entry({ value: "" })]));
  assert.equal(text(sub(cellFor(empty, "effortLevel"), "s4-sv")), "empty");
  const none = show(handPayload([entry({ value: null, status: "unknown" })]));
  assert.equal(text(sub(cellFor(none, "effortLevel"), "s5-sv-none")), "Not known");
});

test("band: a Lowered value keeps its value in the cell and says what it runs as in the name and the title only", () => {
  const payload = real("effort-lowered-by-cap");
  const root = show(payload);
  const cell = cellFor(root, "effortLevel");
  assert.equal(text(sub(cell, "st")), "Lowered");
  const winner = payload.entries.find((e) => e.scope === "main" && e.key === "effortLevel");
  assert.ok(winner.becomes, "the fixture lowers the level");
  assert.equal(text(sub(cell, "s4-sv")), winner.value);
  assert.equal(byClass(cell, "runs").length, 0, "the cell is 132 pixels wide, so it has no runs line");
  const runs = "runs as " + winner.becomes;
  assert.equal(cell.getAttribute("aria-label"), "Effort, " + winner.value + ", Lowered, " + runs + ". " + STRINGS.band_cell_desc);
  assert.equal(cell.getAttribute("title"), "Effort, " + runs);
  assert.equal(cellFor(root, "model").getAttribute("title"), "Model");
});

test("band: ?setting= opens that cell, an unknown or missing value opens Effort, and only the open cell is current", () => {
  const model = show(handPayload(FIVE), { setting: "model" });
  assert.deepEqual(cellsOf(model).filter((n) => n.getAttribute("aria-current") === "true").map((n) => n.getAttribute("data-setting")), ["model"]);
  assert.ok(hasClass(cellFor(model, "model"), "is-on"));
  assert.ok(!hasClass(cellFor(model, "effortLevel"), "is-on"));
  for (const setting of [null, "bogus"]) {
    const root = show(handPayload(FIVE), { setting });
    assert.deepEqual(cellsOf(root).filter((n) => hasClass(n, "is-on")).map((n) => n.getAttribute("data-setting")), ["effortLevel"]);
  }
});

test("router: setting is carried by the hash, validated against the band, and read on the Settings route only", () => {
  assert.equal(router.parseHash("#/settings?setting=model").query.setting, "model");
  assert.equal(router.parseHash("#/settings?setting=nope").query.setting, null);
  assert.equal(router.parseHash("#/settings").query.setting, null);
  assert.equal(router.parseHash("#/agents?setting=model").query.setting, null);
  assert.equal(router.parseHash("#/settings/@main/effortLevel?setting=model").query.setting, null);
  assert.equal(router.hashFor("settings", {}, { project: "app", setting: "model" }), "#/settings?project=app&setting=model");
  assert.equal(router.hashFor("settings", {}, { setting: null }), "#/settings");
  assert.equal(router.hashFor("settings", {}, router.parseHash("#/settings?project=app&range=7d&setting=autoCompactWindow").query),
    "#/settings?project=app&range=7d&setting=autoCompactWindow");
  for (const key of router.BAND_SETTINGS) assert.equal(router.parseHash("#/settings?setting=" + key).query.setting, key);
});

test("band: the band redraws with the page, so a second render does not stack listeners", () => {
  const page = createPage();
  show(handPayload(FIVE), { page });
  show(handPayload(FIVE), { page });
  show(handPayload(FIVE), { page, setting: "model" });
  assert.equal((page.listeners.resize || []).length, 1, "one resize listener");
  assert.equal((page.doc.listeners.keydown || []).length, 1, "one key listener");
  assert.equal((page.doc.listeners.click || []).length, 1, "one click listener");
});

// ---------------------------------------------------------------- the band order

test("band order: 8 keys fit from 1056, which is a 1360 window less the 240 sidebar and the 32 pixel gutters", () => {
  const keys = ["a", "b", "c", "d", "e", "f", "g", "h"];
  assert.equal(1360 - 240 - 2 * 32, 1056);
  assert.deepEqual(bandOrder.fit(keys, 1056, "a"), { cells: keys, more: [] });
  const tight = bandOrder.fit(keys, 1055, "a");
  assert.deepEqual(tight.cells, ["a", "b", "c", "d", "e", "f"]);
  assert.deepEqual(tight.more, ["g", "h"]);
  assert.deepEqual(bandOrder.fit(keys, 5000, "a").more, []);
});

test("band order: 5 keys fit from 660, and the rule is the 132 pixel cell and not a window width", () => {
  const keys = ["a", "b", "c", "d", "e"];
  assert.deepEqual(bandOrder.fit(keys, 660, "a").more, []);
  assert.deepEqual(bandOrder.fit(keys, 659, "a"), { cells: ["a", "b", "c"], more: ["d", "e"] });
  assert.deepEqual(bandOrder.fit(keys, 400, "a", 100), { cells: ["a", "b", "c"], more: ["d", "e"] }, "the cell width is an argument");
  assert.deepEqual(bandOrder.fit(keys, 500, "a", 100).more, []);
  assert.equal(bandOrder.MIN_CELL, 132);
});

test("band order: a phone gives one cell, and that cell is the selected one even when it was in More", () => {
  const keys = ["a", "b", "c", "d", "e"];
  assert.deepEqual(bandOrder.fit(keys, 343, "a"), { cells: ["a"], more: ["b", "c", "d", "e"] });
  assert.deepEqual(bandOrder.fit(keys, 343, "d"), { cells: ["d"], more: ["a", "b", "c", "e"] });
  assert.deepEqual(bandOrder.fit(keys, 0, "c"), { cells: ["c"], more: ["a", "b", "d", "e"] }, "two slots at the least");
});

test("band order: a selected key in More takes the last cell slot and the displaced key goes first in More", () => {
  const keys = ["a", "b", "c", "d", "e", "f", "g", "h"];
  const out = bandOrder.fit(keys, 660, "g");
  assert.deepEqual(out.cells, ["a", "b", "c", "g"]);
  assert.deepEqual(out.more, ["d", "e", "f", "h"]);
  // A selected key that already has a cell moves nothing, and the input is not changed.
  assert.deepEqual(bandOrder.fit(keys, 660, "b"), { cells: ["a", "b", "c", "d"], more: ["e", "f", "g", "h"] });
  assert.deepEqual(keys, ["a", "b", "c", "d", "e", "f", "g", "h"]);
  assert.deepEqual(bandOrder.fit(keys, 660, "zzz").cells, ["a", "b", "c", "d"]);
});

// ---------------------------------------------------------------- More

test("more: a narrow band keeps the open cell and puts the rest behind More, with the count and the summary", () => {
  const page = createPage();
  const root = show(handPayload(FIVE), { page });
  narrow(page, root, 343);
  assert.deepEqual(cellsOf(root).map((n) => n.getAttribute("data-setting")), ["effortLevel"], "Effort is open, so it takes the one cell");
  const more = moreOf(root);
  assert.equal(more.getAttribute("aria-expanded"), "false");
  assert.equal(text(sub(more, "s4-sl")), "More settings");
  assert.equal(text(sub(more, "s4-sv")), "4 more");
  assert.equal(sub(more, "s4-sv").find((n) => n.tagName === "svg").length, 1, "the chevron");
  assert.equal(more.getAttribute("aria-label"), "4 more settings");
  assert.equal(text(sub(more, "s4-sw")), "1 set in a file", "Model is in effect, the other three hidden ones are defaults");
  assert.equal(byClass(root, "s5-a")[0].styleMap["--n"], "2");
  assert.equal(popOf(root).hidden, true);
  // Wide again: five cells and no More.
  narrow(page, root, 1136);
  assert.equal(cellsOf(root).length, 5);
  assert.equal(moreOf(root), undefined);
  // 500 wide: three slots, so two cells and More.
  narrow(page, root, 500);
  assert.deepEqual(cellsOf(root).map((n) => n.getAttribute("data-setting")), ["model", "effortLevel"]);
  assert.equal(text(sub(moreOf(root), "s4-sv")), "3 more");
});

test("more: an open setting that was in More takes the last cell slot and the displaced cell leads the list", () => {
  const page = createPage();
  const root = show(handPayload(FIVE), { page, setting: "promptCacheTtl" });
  narrow(page, root, 500);
  assert.deepEqual(cellsOf(root).map((n) => n.getAttribute("data-setting")), ["model", "promptCacheTtl"]);
  assert.ok(hasClass(cellFor(root, "promptCacheTtl"), "is-on"));
  const hidden = rowsOf_(popOf(root)).filter((n) => !hasClass(n.parentNode, "s5-vc")).map((n) => n.getAttribute("data-setting"));
  assert.deepEqual(hidden, ["effortLevel", "maxEffortLevel", "autoCompactWindow"], "the displaced key goes first, in the saved order after it");
  narrow(page, root, 343);
  assert.deepEqual(cellsOf(root).map((n) => n.getAttribute("data-setting")), ["promptCacheTtl"]);
});

test("more: pressing More opens the list of the hidden settings, Escape closes it and returns focus, a row closes it", () => {
  const page = createPage();
  const root = show(handPayload(FIVE), { page });
  narrow(page, root, 343);
  const more = moreOf(root);
  more.click();
  assert.equal(more.getAttribute("aria-expanded"), "true");
  assert.equal(popOf(root).hidden, false);
  assert.equal(more.getAttribute("aria-controls"), popOf(root).getAttribute("id"));
  const rows = rowsOf_(popOf(root));
  const hiddenRows = rows.filter((n) => !hasClass(n.parentNode, "s5-vc"));
  assert.deepEqual(hiddenRows.map((n) => text(sub(n, "n"))), ["Model", "Effort cap", "Compact window", "Cache lifetime"]);
  assert.deepEqual(hiddenRows.map((n) => text(sub(n, "v"))), ["Opus 5.5", "Not set", "1,000,000", "1h"]);
  assert.deepEqual(hiddenRows.map((n) => text(sub(n, "st"))), ["In effect", "Default", "Default", "Default"]);
  assert.equal(hiddenRows[0].getAttribute("href"), "#/settings?project=app&setting=model");
  // The narrow layout shows every setting, so the cell that has its own cell is in the list too, marked open.
  assert.equal(rows.length, 5);
  const open = rows.find((n) => hasClass(n, "is-on"));
  assert.equal(open.getAttribute("data-setting"), "effortLevel");
  assert.equal(open.getAttribute("aria-current"), "true");
  assert.ok(hasClass(open.parentNode, "s5-vc"), "marked for the narrow layout alone");
  // Escape.
  FElement.focused = null;
  page.doc.dispatch("keydown", { key: "Escape" });
  assert.equal(more.getAttribute("aria-expanded"), "false");
  assert.equal(popOf(root).hidden, true);
  assert.equal(FElement.focused, more);
  // Escape with the list closed does nothing, and another key does nothing.
  FElement.focused = null;
  page.doc.dispatch("keydown", { key: "Escape" });
  assert.equal(FElement.focused, null);
  more.click();
  page.doc.dispatch("keydown", { key: "Enter" });
  assert.equal(more.getAttribute("aria-expanded"), "true");
  // Picking a row closes it. The row is a link, so the route does the rest.
  hiddenRows[1].click();
  assert.equal(more.getAttribute("aria-expanded"), "false");
  assert.equal(popOf(root).hidden, true);
  // A click outside closes it, and a click inside the band does not.
  more.click();
  cellFor(root, "effortLevel").click();
  assert.equal(more.getAttribute("aria-expanded"), "true");
  root.click();
  assert.equal(more.getAttribute("aria-expanded"), "false");
  // Pressing More again closes it.
  more.click();
  more.click();
  assert.equal(more.getAttribute("aria-expanded"), "false");
});

test("more: the summary counts hidden settings that are not defaults, and a problem status takes the count's place", () => {
  const summary = (entries) => {
    const pg = createPage();
    const root = show(handPayload(entries), { page: pg });
    narrow(pg, root, 343);
    return sub(moreOf(root), "s4-sw");
  };
  const dflt = (key) => entry({ key, value: "x", status: "default", file: null, layer: "default", line: undefined });
  const inEffect = (key) => entry({ key, value: "x", status: "in_effect" });
  assert.equal(text(summary([inEffect("effortLevel"), dflt("model"), dflt("maxEffortLevel"), dflt("autoCompactWindow"), dflt("promptCacheTtl")])), "All default");
  assert.equal(text(summary([inEffect("effortLevel"), inEffect("model"), dflt("maxEffortLevel")])), "1 set in a file");
  assert.equal(text(summary([inEffect("effortLevel"), inEffect("model"), inEffect("maxEffortLevel"), dflt("autoCompactWindow")])), "2 set in files");
  for (const status of ["overridden", "ignored", "invalid", "unknown"]) {
    const node = summary([inEffect("effortLevel"), inEffect("model"), entry({ key: "promptCacheTtl", value: "1h", status })]);
    assert.equal(text(node), STRINGS["status_" + status], status);
    assert.equal(sub(node, "mk").getAttribute("aria-hidden"), "true", "the mark");
    assert.equal(node.find((n) => hasClass(n, "st-" + status)).length, 1);
  }
  // A problem in a cell that is shown does not count: it is not behind More.
  const shown = summary([entry({ key: "effortLevel", value: "high", status: "overridden" }), dflt("model")]);
  assert.equal(text(shown), "All default");
});

test("more: a change waiting in a hidden setting shows the mark and Not saved in the summary, the row and the name", () => {
  const page = createPage();
  const payload = handPayload(FIVE);
  const host = band.bandFor({ route: { name: "settings", params: {}, query: {} }, hashFor: (n, p, patch) => router.hashFor(n, p, { project: "app", ...patch }) },
    payload, "effortLevel", new Set(["promptCacheTtl"]));
  const root = page.sections.settings;
  root.appendChild(host);
  byClass(root, "s5-a")[0].clientWidth = 343;
  band.refitBand();
  assert.deepEqual(cellsOf(root).map((n) => n.getAttribute("data-setting")), ["effortLevel"]);
  const more = moreOf(root);
  assert.equal(text(sub(more, "s4-sw")), STRINGS.band_not_saved);
  assert.equal(sub(more, "s4-sw").find((n) => hasClass(n, "s5-pend")).length, 1);
  assert.equal(more.getAttribute("aria-label"), "4 more settings, Cache lifetime not saved");
  const row = rowsOf_(popOf(root)).find((n) => n.getAttribute("data-setting") === "promptCacheTtl");
  assert.equal(text(sub(row, "s5-pend")), STRINGS.band_not_saved);
  assert.equal(sub(row, "st"), undefined, "the mark and word stand in place of the status");
  assert.equal(text(sub(row, "v")), "1h", "the row keeps the current value");
});

function narrowTo(root, width) {
  byClass(root, "s5-a")[0].clientWidth = width;
  band.refitBand();
}

test("more: a change waiting in a cell shows Not saved in place of its status and keeps the value", () => {
  const page = createPage();
  const ctx = { route: { name: "settings", params: {}, query: {} }, hashFor: (n, p, patch) => router.hashFor(n, p, { project: "app", ...patch }) };
  const root = page.sections.settings;
  root.appendChild(band.bandFor(ctx, handPayload(FIVE), "effortLevel", new Set(["effortLevel"])));
  const cell = cellFor(root, "effortLevel");
  assert.equal(text(sub(cell, "s4-sv")), "high");
  assert.equal(text(sub(cell, "s5-pend")), "Not saved");
  assert.equal(sub(cell, "st"), undefined);
  assert.equal(cell.getAttribute("aria-label"), "Effort, high, Not saved. " + STRINGS.band_cell_desc);
  // A pending cell is not behind More, so the name and the summary stay at rest.
  narrowTo(root, 500);
  assert.equal(moreOf(root).getAttribute("aria-label"), "3 more settings");
  assert.equal(text(sub(moreOf(root), "s4-sw")), "All default");
  assert.equal(text(sub(cellFor(root, "effortLevel"), "s5-pend")), "Not saved");
});

test("band: setNotSaved redraws the band alone, keeps its width and focus, and marks the cell or the More button", () => {
  const page = createPage();
  const ctx = { route: { name: "settings", params: {}, query: {} }, hashFor: (n, p, patch) => router.hashFor(n, p, { project: "app", ...patch }) };
  const root = page.sections.settings;
  const host = band.bandFor(ctx, handPayload(FIVE), "effortLevel", new Set());
  root.appendChild(host);
  const nav = byClass(root, "s5-a")[0];
  assert.equal(root.find((n) => hasClass(n, "s5-pend")).length, 0);
  cellFor(root, "effortLevel").focus();
  band.setNotSaved(new Set(["effortLevel"]));
  assert.equal(byClass(root, "s5-band")[0], host, "the band node stays");
  assert.equal(byClass(root, "s5-a")[0], nav);
  assert.equal(text(sub(cellFor(root, "effortLevel"), "s5-pend")), STRINGS.band_not_saved);
  assert.equal(sub(cellFor(root, "effortLevel"), "st"), undefined, "the mark and word stand in place of the status");
  assert.equal(FElement.focused, cellFor(root, "effortLevel"), "focus stays on the same cell");
  // The list of a narrow band: Effort behind More, then marked, then clear again.
  nav.clientWidth = 343;
  band.refitBand();
  band.setNotSaved(new Set());
  assert.deepEqual(cellsOf(root).map((n) => n.getAttribute("data-setting")), ["effortLevel"], "the width is kept");
  const atRest = text(sub(moreOf(root), "s4-sw"));
  assert.notEqual(atRest, STRINGS.band_not_saved);
  band.setNotSaved(new Set(["promptCacheTtl"]));
  assert.deepEqual(cellsOf(root).map((n) => n.getAttribute("data-setting")), ["effortLevel"], "still one cell");
  assert.equal(text(sub(moreOf(root), "s4-sw")), STRINGS.band_not_saved);
  assert.equal(moreOf(root).getAttribute("aria-label"), "4 more settings, Cache lifetime not saved");
  band.setNotSaved(new Set());
  assert.equal(root.find((n) => hasClass(n, "s5-pend")).length, 0);
  assert.equal(text(sub(moreOf(root), "s4-sw")), atRest);
});

test("more: a redraw for a new width keeps focus on the same cell", () => {
  const page = createPage();
  const root = show(handPayload(FIVE), { page });
  cellFor(root, "effortLevel").focus();
  narrow(page, root, 343);
  assert.equal(FElement.focused, cellFor(root, "effortLevel"));
  moreOf(root).focus();
  narrow(page, root, 500);
  assert.equal(FElement.focused, moreOf(root));
});

test("more: a band that has no width yet, or one that stays on the same cells, is not drawn again", () => {
  const page = createPage();
  const root = show(handPayload(FIVE), { page });
  const nav = byClass(root, "s5-a")[0];
  const first = cellFor(root, "model");
  (page.listeners.resize || []).forEach((fn) => fn({}));
  assert.equal(cellFor(root, "model"), first, "no width, so nothing changes");
  nav.clientWidth = 1136;
  (page.listeners.resize || []).forEach((fn) => fn({}));
  assert.equal(cellFor(root, "model"), first, "the same cells, so nothing changes");
});

// ---------------------------------------------------------------- sources

test("source: the three forms and the cases around them", () => {
  const payload = handPayload([
    entry({ key: "model", value: "opus", file: null, status: "default", layer: "default", line: undefined }),
    entry({ key: "effortLevel", file: "~/work/app/.claude/settings.local.json", line: 3, via: "CLAUDE_CODE_EFFORT_LEVEL", layer: "local" }),
    entry({ key: "promptCacheTtl", file: "Shell", line: undefined, via: "ENABLE_PROMPT_CACHING_1H", layer: "shell" }),
    entry({ key: "autoCompactWindow", file: "Shell", line: undefined, layer: "shell" }),
  ]);
  // The band has no room for a source, so these are the words the trail and the rail's winner use.
  const source = (key) => settings.sourceText(settings.winnerOf(payload, key), payload, true);
  assert.equal(source("model"), "Claude Code's default");
  assert.equal(source("effortLevel"), "~/work/app/.claude/settings.local.json, line 3");
  assert.equal(source("promptCacheTtl"), "Shell");
  assert.equal(source("autoCompactWindow"), "Shell");
  assert.equal(byClass(show(payload), "en-note").length, 0, "the band carries no note");
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
  const payload = real("effort-user-top-level-xhigh-ignored-opus-5-5");
  const root = show(payload);
  const cell = cellFor(root, "effortLevel");
  assert.equal(text(sub(cell, "s4-sv")), "medium");
  assert.equal(text(sub(cell, "st")), "Default");
  assert.equal(settings.sourceText(settings.winnerOf(payload, "effortLevel"), payload, true), "Claude Code's default");
  assert.equal(text(sub(cellFor(root, "model"), "s4-sv")), "Opus 5.5");
  assert.equal(cellsOf(root).length, 5);
  // The rail says why, in the winner's own reason.
  const winner = settings.winnerOf(payload, "effortLevel");
  assert.equal(text(sub(railOf(root), "s4-p")), winner.reason);
});

test("first pair: project xhigh is in effect, from project/.claude/settings.json", () => {
  const payload = real("effort-project-top-level-xhigh-opus-5-5");
  const root = show(payload);
  const cell = cellFor(root, "effortLevel");
  assert.equal(text(sub(cell, "s4-sv")), "xhigh");
  assert.equal(text(sub(cell, "st")), "In effect");
  assert.match(settings.sourceText(settings.winnerOf(payload, "effortLevel"), payload, true), /^project\/\.claude\/settings\.json, line \d+$/);
});

test("unknown: model-main-default-unknown shows Unknown with Not known and no value, and the rail has its reason", () => {
  const payload = real("model-main-default-unknown");
  const root = show(payload, { setting: "model" });
  const cell = cellFor(root, "model");
  assert.equal(text(sub(cell, "st")), "Unknown");
  assert.equal(text(sub(cell, "s5-sv-none")), "Not known");
  const winner = payload.entries.find((e) => e.scope === "main" && e.key === "model");
  assert.ok(winner.reason);
  assert.equal(text(sub(railOf(root), "s4-p")), winner.reason);
  assert.equal(text(sub(cellFor(root, "effortLevel"), "st")), "Unknown");
});

test("unknown: the user file's effortLevel under an unknown model shows no value on the cell", () => {
  const payload = real("effort-user-top-level-model-unknown");
  const winner = payload.entries.find((e) => e.scope === "main" && e.key === "effortLevel");
  assert.equal(winner.status, "unknown");
  assert.ok(winner.value, "the entry keeps the file's value");
  const root = show(payload);
  const cell = cellFor(root, "effortLevel");
  assert.equal(text(sub(cell, "st")), "Unknown");
  assert.equal(text(sub(cell, "s5-sv-none")), "Not known");
  assert.equal(text(sub(cell, "s4-sv")).includes(String(winner.value)), false);
  assert.equal(cell.getAttribute("aria-label"), "Effort, Not known, Unknown. " + STRINGS.band_cell_desc);
  assert.ok(text(sub(railOf(root), "s4-p")).includes("sets a top-level effortLevel of " + winner.value));
});

test("unknown: valueString and valueText hide the value of both unknown-model rules and nothing else", () => {
  const p = { models: {} };
  for (const id of ["effort-level-user-settings-model-unknown", "agent-effort-user-settings-model-unknown"]) {
    const e = entry({ value: "xhigh", status: "unknown", rule_id: id, rule_ids: [id] });
    assert.equal(settings.valueString(e, p), "");
    assert.equal(settings.valueText(e, p), null);
  }
  assert.equal(settings.valueString(entry({ value: "xhigh", status: "unknown" }), p), "xhigh");
  assert.equal(settings.valueString(entry({ value: "xhigh", rule_ids: ["effort-level-user-settings-model-unknown"] }), p), "xhigh");
});

test("the env block of a fixture reads as the file and line, in the words of the rail's winner", () => {
  const payload = real("env-block-over-shell");
  const winner = settings.winnerOf(payload, "model");
  assert.match(settings.sourceText(winner, payload, true), /^config\/settings\.json, line \d+$/);
  assert.ok(cellFor(show(payload), "model"));
});

// ---------------------------------------------------------------- states

const pageOf = (root) => root.childNodes[0];
const kinds = (node) => node.childNodes.map((n) => n.getAttribute("class").split(" ")[0]);

test("states: no .claude folder and no user settings file both show above the band", () => {
  const payload = handPayload(FIVE, { state: "no_claude_folder", no_user_settings: true });
  const root = show(payload);
  assert.deepEqual(kinds(pageOf(root)), ["s4-chead", "s5-msgs", "s5-band", "s5-w"]);
  const heads = root.find((n) => hasClass(n, "cd-h")).map(text);
  assert.deepEqual(heads, ["No .claude folder", "No user settings file"]);
  const bodies = root.find((n) => hasClass(n, "es-t")).map(text);
  assert.match(bodies[0], /^~\/work\/app has no \.claude folder/);
  assert.ok(bodies[0].includes("~/.claude"));
  assert.match(bodies[1], /^~\/\.claude has no settings\.json/);
  assert.equal(cellsOf(root).length, 5);
});

test("states: one message alone, and none when both files are there", () => {
  const noUser = show(handPayload(FIVE, { no_user_settings: true }));
  assert.deepEqual(noUser.find((n) => hasClass(n, "cd-h")).map(text), ["No user settings file"]);
  const noClaude = show(handPayload(FIVE, { state: "no_claude_folder" }));
  assert.deepEqual(noClaude.find((n) => hasClass(n, "cd-h")).map(text), ["No .claude folder"]);
  const fine = show(handPayload(FIVE));
  assert.equal(fine.find((n) => hasClass(n, "cd-h")).length, 0);
  assert.equal(byClass(fine, "s5-msgs").length, 0, "no messages, no wrapper");
});

test("states: a missing folder shows its message with the config file and no band", () => {
  const payload = handPayload([], { state: "missing_folder" });
  const root = show(payload, { project: { key: "lantern", name: "Lantern" } });
  assert.deepEqual(root.find((n) => hasClass(n, "cd-h")).map(text), ["Folder not found"]);
  const body = text(root.find((n) => hasClass(n, "es-t"))[0]);
  assert.ok(body.includes("Lantern") && body.includes("~/work/app") && body.includes("~/.claude/routing-dashboard.json"), body);
  assert.equal(cellsOf(root).length, 0);
  assert.equal(byClass(root, "s5-a").length + byClass(root, "s4-rail").length + byClass(root, "s5-lock").length, 0);
});

test("states: All projects shows the project picker and nothing else", () => {
  const root = show(handPayload(FIVE), { project: { key: "all", name: "All projects" } });
  assert.equal(cellsOf(root).length, 0);
  assert.equal(byClass(root, "s5-a").length + byClass(root, "s4-rail").length, 0);
  assert.deepEqual(root.find((n) => hasClass(n, "cd-h")).map(text), ["Pick a project"]);
  assert.equal(root.find((n) => n.tagName === "button").length, 1);
  assert.equal(text(root.find((n) => n.tagName === "h1")[0]), "Settings");
  const noData = show(null, { project: { key: "all", name: "All projects" } });
  assert.deepEqual(noData.find((n) => hasClass(n, "cd-h")).map(text), ["Pick a project"]);
});

test("states: no payload yet, or a refused one, shows the head only", () => {
  for (const res of [null, { ok: false, status: 404, data: null }, { ok: false, status: 500, data: null }]) {
    const root = show(null, { res });
    assert.deepEqual(kinds(pageOf(root)), ["s4-chead"]);
    assert.ok(hasClass(pageOf(root).childNodes[0].childNodes[0], "ph"));
    assert.equal(hasClass(pageOf(root), "s5-lock"), false, "the panes lock only with a band to hold");
  }
});

test("page: the band, then the two panes with the empty body and foot slots, and the Settings-only classes", () => {
  const root = show(handPayload(FIVE));
  const page = pageOf(root);
  assert.ok(hasClass(page, "s4") && hasClass(page, "s4-c") && hasClass(page, "s5-lock"));
  const panes = page.childNodes[2];
  assert.ok(hasClass(panes, "s5-w"));
  assert.deepEqual(kinds(panes), ["s4-body", "s4-rail"]);
  const body = panes.childNodes[0];
  assert.equal(body.getAttribute("data-slot"), "body");
  assert.equal(body.childNodes.length, 3, "with no edit session the body is the read-only frame");
  const foot = byClass(panes, "s4-rf")[0];
  assert.ok(hasClass(foot, "s5-rf"));
  assert.equal(foot.getAttribute("data-slot"), "foot");
  assert.equal(foot.childNodes.length, 0);
  assert.equal(foot.parentNode.tagName, "aside");
  assert.equal(foot.parentNode.childNodes[0].getAttribute("class"), "s4-rb");
});

test("rail: at rest it says why in the winner's reason, and links to the trail of the row, whichever setting is open", () => {
  const payload = real("effort-lowered-by-cap");
  for (const key of router.BAND_SETTINGS) {
    const root = show(payload, { setting: key });
    const rail = railOf(root);
    assert.equal(text(sub(rail, "s4-rh")), "Why this value");
    assert.equal(sub(rail, "s4-rh").tagName, "h2");
    const winner = settings.winnerOf(payload, key);
    assert.equal(byClass(rail, "s4-p").length, 1);
    assert.equal(text(sub(rail, "s4-p")), winner.reason);
    const link = rail.find((n) => n.tagName === "a")[0];
    assert.equal(text(link), "Rules behind this value");
    assert.equal(link.getAttribute("href"), "#/settings/@main/" + key + "?project=app");
  }
  // A setting the payload has no entry for has the heading alone.
  const bare = show(handPayload([entry({ key: "model", value: "opus" })]), { setting: "promptCacheTtl" });
  assert.equal(text(sub(railOf(bare), "s4-rh")), "Why this value");
  assert.equal(byClass(railOf(bare), "s4-p").length, 0);
  assert.equal(railOf(bare).find((n) => n.tagName === "a").length, 0);
});

test("render clears the section first, so a second render does not stack bands", () => {
  const page = createPage();
  const root = page.sections.settings;
  const ctx = { route: { name: "settings", params: {}, query: {} }, project: { key: "app", name: "App" },
    data: { settings: { ok: true, status: 200, data: handPayload(FIVE) } }, hashFor: (n, p) => router.hashFor(n, p, {}) };
  settings.render(root, ctx);
  settings.render(root, ctx);
  assert.equal(cellsOf(root).length, 5);
  assert.equal(byClass(root, "s5-a").length, 1);
});

test("focus: a draw puts focus back on the cell that had it, and a cell chosen by the route keeps focus", () => {
  const page = createPage();
  const root = show(handPayload(FIVE), { page });
  cellFor(root, "model").focus();
  show(handPayload(FIVE), { page, setting: "model" });
  assert.equal(FElement.focused, cellFor(root, "model"));
  FElement.focused = null;
  show(handPayload(FIVE), { page });
  assert.equal(FElement.focused, null, "focus that was elsewhere is left alone");
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
  for (const file of ["pages/settings.js", "pages/band.js", "band_order.js"]) {
    const source = fs.readFileSync(new URL("js/" + file, STATIC), "utf8");
    assert.equal(/innerHTML|outerHTML|insertAdjacentHTML|document\.write/.test(source), false, file);
  }
  // The same payload drawn into a narrow band, with More open, parses nothing either.
  const page = createPage();
  const narrowRoot = show(payload, { page });
  narrow(page, narrowRoot, 343);
  moreOf(narrowRoot).click();
  assert.deepEqual(parsed, []);
  assert.equal(narrowRoot.find((n) => n.tagName === "img").length, 0);
  assert.ok(text(popOf(narrowRoot)).includes(evil));
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
    route: { name: "trail", params: { agent, setting }, query: {} },
    project,
    data: { settings: res || (payload ? { ok: true, status: 200, data: payload } : null) },
    hashFor: (name, params, patch = {}) => router.hashFor(name, params, { project: project.key, ...patch }),
  };
  trail.render(root, { ...ctx, route: { name: "settings", params: {}, query: {} } });
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

test("trail: the panel follows its own head, with the cards in the order of the screen and no band", () => {
  const { root } = mount(real("effort-lowered-by-cap"), "@main", "effortLevel");
  assert.deepEqual(root.childNodes.map((n) => n.getAttribute("class").split(" ")[0]), ["ph", "trail-a"]);
  assert.equal(cellsOf(root).length + byClass(root, "s5-a").length + byClass(root, "s4-rail").length, 0, "the trail draws no band");
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
  // The head links back to the setting on the Settings page, with the cell of the row open.
  const link = byClass(root, "ph")[0].find((n) => n.tagName === "a")[0];
  assert.equal(text(link), "Make changes on the Settings page");
  assert.equal(link.getAttribute("href"), "#/settings?project=app&setting=effortLevel");
  assert.equal(text(root.find((n) => n.tagName === "h1")[0]), "Settings");
});

test("trail: the change link is for a main session row that has a cell, and its target opens that cell", () => {
  const payload = real("effort-lowered-by-cap");
  const linkOf = (root) => byClass(root, "ph")[0].find((n) => n.tagName === "a")[0];
  for (const key of router.BAND_SETTINGS) {
    const href = linkOf(mount(payload, "@main", key).root).getAttribute("href");
    assert.equal(href, "#/settings?project=app&setting=" + key);
    assert.equal(router.parseHash(href).query.setting, key);
  }
  assert.equal(linkOf(mount(payload, "@main", "env.NOPE").root), undefined, "a row with no cell has no link");
  assert.equal(linkOf(mount(real("agent-effort-default-fable-5-1"), "probe", "effort").root), undefined, "an agent row has none");
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

test("trail: the unknown-model effort rules show no value on the winner, in its card summary or on an agent row", () => {
  const main = E({ value: "xhigh", status: "unknown", rule_ids: ["effort-level-user-settings-model-unknown"] });
  const root = mount(trailPayload([main]), "@main", "effortLevel").root;
  assert.equal(sub(winnerNode(root), "val"), undefined);
  assert.equal(summaryOf(cardOf(root, "Winner")).startsWith("Unknown, "), true);
  const agent = entry({ key: "effort", scope: "agent", agent: "builder", value: "xhigh", status: "unknown",
    rule_ids: ["agent-effort-user-settings-model-unknown"] });
  const aroot = mount(trailPayload([agent]), "builder", "effort").root;
  assert.equal(sub(winnerNode(aroot), "val"), undefined);
  assert.equal(summaryOf(cardOf(aroot, "Winner")).startsWith("Unknown, "), true);
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

test("settings: settingLabel gives the label as written and settingWord lower-cases it", () => {
  assert.equal(settings.settingLabel("effortLevel"), "Effort");
  assert.equal(settings.settingLabel("promptCacheTtl"), "Cache lifetime");
  assert.equal(settings.settingLabel("maxEffortLevel"), "Effort cap");
  assert.equal(settings.settingLabel("mystery"), "mystery");
  assert.equal(settings.settingWord("maxEffortLevel"), "effort cap");
  assert.equal(settings.settingWord("effort"), "effort");
  assert.equal(settings.settingWord("Mystery"), "Mystery");
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
  assert.equal(cellsOf(root).length, 0, "the trail draws no cells");
  assert.equal(byClass(root, "ph")[0].find((n) => n.tagName === "a").length, 0, "an agent row has no change link");
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

test("trail: a row the payload does not have shows the head and one line saying so, and no panel", () => {
  const cases = [
    ["@main", "noSuchSetting", "This project has no noSuchSetting for Main session, so there's no trail to show."],
    ["ghost", "effort", "This project has no effort for ghost, so there's no trail to show."],
    ["@main", "env.NOPE", "This project has no env.NOPE for Main session, so there's no trail to show."],
    ["nobody", "effortLevel", "This project has no effort for nobody, so there's no trail to show."],
  ];
  for (const [agent, setting, line] of cases) {
    const { root } = mount(real("effort-lowered-by-cap"), agent, setting);
    assert.equal(panelOf(root), undefined, agent + "/" + setting);
    assert.deepEqual(root.childNodes.map((n) => n.getAttribute("class").split(" ")[0]), ["ph", "foot"]);
    assert.equal(root.childNodes[1].tagName, "p");
    assert.equal(text(root.childNodes[1]), line, agent + "/" + setting);
    assert.equal(cellsOf(root).length, 0);
  }
});


test("trail: All projects shows the picker and no panel", () => {
  const { root } = mount(real("effort-lowered-by-cap"), "@main", "effortLevel", { project: { key: "all", name: "All projects" } });
  assert.equal(panelOf(root), undefined);
  assert.deepEqual(root.find((n) => hasClass(n, "cd-h")).map(text), ["Pick a project"]);
  assert.equal(cellsOf(root).length, 0);
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

test("keys: a cell is an anchor, so Enter opens its setting through the route, and the rail link opens the trail", () => {
  const root = show(handPayload(FIVE));
  for (const key of router.BAND_SETTINGS) {
    const cell = cellFor(root, key);
    assert.equal(cell.tagName, "a");
    const parsed_ = router.parseHash(cell.getAttribute("href"));
    assert.equal(parsed_.name, "settings");
    assert.equal(parsed_.query.setting, key);
  }
  const link = railOf(root).find((n) => n.tagName === "a")[0];
  const trailRoute = router.parseHash(link.getAttribute("href"));
  assert.equal(trailRoute.name, "trail");
  assert.deepEqual(trailRoute.params, { agent: "@main", setting: "effortLevel" });
  assert.deepEqual(router.parseHash("#/settings/builder/effort").params, { agent: "builder", setting: "effort" });
});

// Draws the Settings route when the hash changes to it, as the app does for every route change.
function followHash(m, settingsRoot) {
  m.page.win.addEventListener("hashchange", () => {
    const next = { ...m.ctx, route: { name: "settings", params: {}, query: router.parseHash(m.page.win.location.hash).query } };
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
  assert.equal(m.page.win.location.hash, "#/settings?project=app&setting=effortLevel");
  assert.equal(FElement.focused, cellFor(settingsRoot, "effortLevel"));
  assert.ok(hasClass(cellFor(settingsRoot, "effortLevel"), "is-on"), "Settings opens on the row the trail was for");
  assert.equal(panelOf(m.root), undefined, "the trail is gone");
  assert.equal(cellsOf(settingsRoot).length, 5);
  // A later render of Settings does not take the return focus again. Focus on another cell stays on that setting.
  const moved = FElement.focused;
  FElement.focused = cellFor(settingsRoot, "model");
  settings.render(settingsRoot, { ...m.ctx, route: { name: "settings", params: {}, query: { setting: "effortLevel" } } });
  assert.equal(FElement.focused, cellFor(settingsRoot, "model"));
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
  // A main row without a cell, such as an env row, does the same, and the address carries no setting.
  const env = mount(real("env-block-over-shell"), "@main", "env.ANTHROPIC_MODEL");
  const envRoot = env.page.sections.settings;
  followHash(env, envRoot);
  escape(env);
  assert.equal(env.page.win.location.hash, "#/settings?project=app");
  assert.equal(FElement.focused, envRoot.find((n) => n.tagName === "h1")[0]);
  // The cap now has a cell, so Escape from its trail opens Settings on it and focuses it.
  const cap = mount(real("agent-effort-default-fable-5-1"), "@main", "maxEffortLevel");
  const capRoot = cap.page.sections.settings;
  followHash(cap, capRoot);
  escape(cap);
  assert.equal(cap.page.win.location.hash, "#/settings?project=app&setting=maxEffortLevel");
  assert.equal(FElement.focused, cellFor(capRoot, "maxEffortLevel"));
});

test("keys: Escape does nothing while the sidebar panel is open", () => {
  const m = mount(real("effort-lowered-by-cap"), "@main", "effortLevel");
  m.page.win.location.hash = "#/settings/@main/effortLevel?project=app";
  m.page.sidebar.classList.add("is-open");
  escape(m);
  assert.equal(m.page.win.location.hash, "#/settings/@main/effortLevel?project=app");
  m.page.sidebar.classList.remove("is-open");
  escape(m);
  assert.equal(m.page.win.location.hash, "#/settings?project=app&setting=effortLevel");
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
  const model = m.root.find((n) => n.tagName === "a")[0];
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

// ---------------------------------------------------------------- the read-only frame

const bodyOf_ = (root) => root.find((n) => n.getAttribute("data-slot") === "body")[0];
const FRAME_KEYS = settings.TILES.map((x) => x.key).filter((k) => !settings.EDITABLE_SETTINGS.includes(k));
const framePayload = (entries, over = {}) => trailPayload(entries, [], over);

test("frame: each key of TILES is editable or draws no radio and no Run at control", () => {
  const payload = framePayload(FIVE);
  for (const spec of settings.TILES) {
    const body = bodyOf_(show(payload, { setting: spec.key }));
    if (settings.EDITABLE_SETTINGS.includes(spec.key)) continue;
    assert.equal(body.find((n) => n.tagName === "input").length, 0, spec.key + " draws a radio");
    assert.equal(body.find((n) => hasClass(n, "s4-run") && /Run at/.test(text(n))).length, 0, spec.key);
    assert.equal(text(body).includes(STRINGS.run_at), false, spec.key + " says Run at");
  }
  assert.deepEqual(FRAME_KEYS, ["model", "maxEffortLevel", "autoCompactWindow", "promptCacheTtl"]);
  assert.equal(bodyOf_(show(payload, { setting: "effortLevel" })).childNodes.length, 3, "with no edit session Effort's body is the read-only frame");
});

test("frame: the four cells draw the lock line and never the editing off or locked lines, in every mode", () => {
  const payload = framePayload(FIVE);
  for (const mode of ["off", "locked", "ready"]) {
    for (const key of FRAME_KEYS) {
      const root = show(payload, { setting: key, edit: mode });
      const body = bodyOf_(root);
      assert.equal(byClass(body, "s4-lock").length, 1, key + " " + mode);
      assert.equal(text(byClass(body, "s4-lock")[0]), STRINGS.ro_lock);
      assert.equal(text(root).includes(STRINGS.ed_off), false, key + " " + mode);
      assert.equal(text(root).includes(STRINGS.ed_locked), false, key + " " + mode);
    }
  }
});

test("frame: a null winner draws without throwing and says Not known", () => {
  for (const key of FRAME_KEYS) {
    const root = show(framePayload([]), { setting: key });
    const body = bodyOf_(root);
    assert.equal(byClass(body, "s4-lock").length, 1);
    assert.ok(text(body).includes(STRINGS.band_not_known), key);
    assert.equal(byClass(body, "s6-r").length, 0, "no rows");
  }
});

test("frame: the Effort cap with no value or only the default says Not set", () => {
  const body = bodyOf_(show(framePayload(FIVE), { setting: "maxEffortLevel" }));
  assert.ok(text(body).includes(STRINGS.band_not_set));
});

test("frame: a hidden value shows the hidden word and a planted value never shows", () => {
  // collect.py leaves "hidden" where a secret was. A planted value in a field the page never draws stays out too.
  const planted = "sk-planted-secret-1234";
  const payload = framePayload([entry({ key: "model", value: "hidden", reason: "r", planted })]);
  const root = show(payload, { setting: "model" });
  const body = bodyOf_(root);
  assert.ok(text(body).includes(STRINGS.hidden));
  assert.equal(text(root).includes(planted), false);
});

test("frame: a value from a managed file names the managed layer", () => {
  const payload = framePayload([
    entry({ key: "autoCompactWindow", value: 500000, layer: "managed", file: "/etc/claude/managed-settings.json", line: 4 }),
    entry({ key: "autoCompactWindow", value: 1000000, file: null, status: "default", layer: "default", line: undefined }),
  ]);
  const body = bodyOf_(show(payload, { setting: "autoCompactWindow" }));
  const rows = byClass(body, "s6-r");
  assert.equal(text(byClass(rows[0], "s4-ln")[0]), STRINGS.layer_managed);
  assert.equal(rows.length, 2);
  assert.ok(hasClass(rows[1], "s6-def"));
  assert.equal(text(byClass(rows[1], "s4-ln")[0]), STRINGS.place_default);
  assert.equal(hasClass(rows[1].parentNode, "s6-rows"), false, "the default sits outside the box");
});

test("frame: rows name the places the design names, in order, with short files", () => {
  const payload = framePayload([
    entry({ key: "promptCacheTtl", value: "5m", layer: "local", file: "/w/app/.claude/settings.local.json", line: 2 }),
    entry({ key: "promptCacheTtl", value: "1h", layer: "project", file: "/w/app/.claude/settings.json", line: 7, status: "overridden" }),
    entry({ key: "promptCacheTtl", value: "1h", layer: "user", file: "/home/me/.claude/config/settings.json", line: 3, status: "ignored" }),
  ]);
  const body = bodyOf_(show(payload, { setting: "promptCacheTtl" }));
  const rows = byClass(body, "s6-r");
  assert.deepEqual(rows.map((r) => text(byClass(r, "s4-ln")[0])), [STRINGS.place_local, STRINGS.place_project, STRINGS.place_user]);
  assert.deepEqual(rows.map((r) => text(byClass(r, "s4-f")[0])),
    ["settings.local.json, line 2", "settings.json, line 7", "config/settings.json, line 3"]);
  assert.equal(byClass(body, "s4-beyond").length, 0, "where_beyond belongs to Effort");
  assert.equal(byClass(body, "s6-rows")[0].getAttribute("aria-label"), STRINGS.where_rest);
});

test("frame: a shell value reads as the shell with its variable", () => {
  const payload = framePayload([
    entry({ key: "promptCacheTtl", value: "1h", layer: "env", file: "Shell", line: undefined, via: "ENABLE_PROMPT_CACHING_1H" }),
  ]);
  const body = bodyOf_(show(payload, { setting: "promptCacheTtl" }));
  const row = byClass(body, "s6-r")[0];
  assert.equal(text(byClass(row, "s4-ln")[0]), STRINGS.place_shell);
  assert.equal(text(byClass(row, "s4-f")[0]), "ENABLE_PROMPT_CACHING_1H");
  assert.equal(where.fromShell(payload.entries[0], payload), true);
});

test("frame: the value text equals the cell text for each setting", () => {
  const payload = framePayload([
    ...FIVE.slice(0, 3),
    entry({ key: "autoCompactWindow", value: 1000000, file: null, status: "default", layer: "default", line: undefined }),
    entry({ key: "promptCacheTtl", value: "1h", file: null, status: "default", layer: "default", line: undefined }),
    entry({ key: "maxEffortLevel", value: "high", line: 9 }),
  ]);
  payload.entries.splice(2, 1);
  payload.rows = rowsOf(payload.entries);
  for (const key of FRAME_KEYS) {
    const root = show(payload, { setting: key });
    const cell = text(sub(cellFor(root, key), "s4-sv"));
    const frame = text(byClass(bodyOf_(root), "s4-v")[0]);
    assert.equal(frame, cell, key);
  }
  const root = show(framePayload(FIVE), { setting: "maxEffortLevel" });
  assert.equal(text(byClass(bodyOf_(root), "s4-v")[0]), text(sub(cellFor(root, "maxEffortLevel"), "s4-sv")));
});

test("where: shortFile and rowNode build the shared rows", () => {
  assert.equal(where.shortFile("local", "/a/b/settings.local.json"), "settings.local.json");
  assert.equal(where.shortFile("user", "~/.claude/config/settings.json"), "config/settings.json");
  assert.equal(where.shortFile("managed", "/etc/x.json"), "/etc/x.json");
  const row = where.rowNode({ name: "N", file: "f", none: "Not set" });
  assert.equal(row.tagName, "div");
  assert.ok(hasClass(row, "s6-r"));
  assert.equal(text(byClass(row, "s4-none")[0]), "Not set");
  assert.equal(row.childNodes.length, 3);
  const list = where.whereList("Head", [row], [], true);
  assert.ok(hasClass(list, "s6-lvs"));
  assert.equal(byClass(list, "s4-beyond").length, 1);
  assert.equal(byClass(where.whereList("Head", [row]), "s4-beyond").length, 0);
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

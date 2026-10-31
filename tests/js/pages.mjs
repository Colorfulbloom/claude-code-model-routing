// Browser-free checks of the dashboard pages, run by tests/test_pages_js.py. They boot the real app.js on the
// fake DOM in fakedom.mjs and answer every fetch from a JSON file that the Python test wrote from a server
// running on the demo set (argv[2], keyed by path plus query). Nothing here opens a browser or a socket.
// A failed check prints its name and the reason, and the exit code is 1.
import assert from "node:assert/strict";
import fs from "node:fs";
import { createPage } from "./fakedom.mjs";

const STATIC = new URL("../../dashboard/static/", import.meta.url);
const JS = new URL("js/", STATIC).href;
const CHECKS = new URL("../e2e_checks/", import.meta.url);
const STRINGS = JSON.parse(fs.readFileSync(new URL("strings.json", STATIC), "utf8"));
const DATA = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));

const tests = [];
const test = (name, fn) => tests.push([name, fn]);
const tick = (ms = 0) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(cond, what) {
  for (let i = 0; i < 400; i++) {
    if (cond()) return;
    await tick(5);
  }
  throw new Error("timed out waiting for " + what);
}

// A page render that throws is caught by renderPages and only logged, so every console.error is kept and
// the runner fails a check that logged "failed to render".
const logged = [];
console.error = (...args) => { logged.push(args.map(String).join(" ")); };

// ---------------------------------------------------------------- the demo data

const TIDEWATER = DATA["/api/projects"].body.projects.find((p) => p.name === "Tidewater reporting").key;
const usageOf = (key) => DATA["/api/usage?project=" + key].body;
const viewOf = (key, range) => usageOf(key).views[range];
const keyOf = (name) => DATA["/api/projects"].body.projects.find((p) => p.name === name).key;
const SESSION = viewOf(TIDEWATER, "30d").sessions[0].session_id;

// ---------------------------------------------------------------- boot

let runs = 0;

// Starts the app on a fresh page. respond(pathname, search, n) may return a promise of [status, body], or of
// null to use the demo data. Unanswered routes give a 404, as the server does for a route it does not have.
// With usage set, boot also waits for data-usage, which comes after data-rendered.
async function boot({ hash = "", respond = () => null, usage = true } = {}) {
  const page = createPage({ narrow: false });
  page.win.location._hash = hash;
  const calls = [];
  const counts = new Map();
  globalThis.fetch = async (path) => {
    calls.push(path);
    const url = new URL(path, "http://127.0.0.1");
    const n = (counts.get(url.pathname) || 0) + 1;
    counts.set(url.pathname, n);
    let answer = await respond(url.pathname, url.searchParams, n);
    if (!answer) {
      if (url.pathname === "/static/strings.json") answer = [200, STRINGS];
      else if (DATA[path]) answer = [DATA[path].status, DATA[path].body];
      else answer = [404, { error: "not_found" }];
    }
    const [status, body] = answer;
    return { ok: status >= 200 && status < 300, status, json: async () => body, text: async () => "" };
  };
  runs += 1;
  await import(JS + "app.js?run=" + runs);
  const root = page.doc.documentElement;
  await until(() => root.getAttribute("data-rendered") !== null, "boot");
  if (usage) await until(() => root.getAttribute("data-usage") === "1", "the first usage answer");
  await tick(10);
  const count = (pathname) => calls.filter((c) => new URL(c, "http://127.0.0.1").pathname === pathname).length;
  const go = async (to) => { page.win.location.hash = to; await tick(20); };
  const section = (name) => page.sections[name];
  return { ...page, calls, count, go, root, section };
}

// ---------------------------------------------------------------- reading the tree

const hasClass = (node, name) => Boolean(node.classList) && node.classList.contains(name);
const byClass = (root, name) => root.find((n) => hasClass(n, name));
const flat = (node) => node.textContent.replace(/\s+/g, " ").trim();
const texts = (root, name) => byClass(root, name).map(flat);

// The card whose heading reads title.
function cardOf(section, title) {
  const found = section.find((n) => n.tagName === "section" && hasClass(n, "cd") && byClass(n, "cd-h").some((hd) => flat(hd) === title));
  assert.equal(found.length, 1, "one card titled " + title);
  return found[0];
}

const visible = (app) => Object.entries(app.sections).filter(([, el]) => !el.hidden).map(([name]) => name);

// ---------------------------------------------------------------- every route in tests/e2e_checks

// The same text files the browser sweep uses, so a later ticket's texts are checked here for free.
const checkFiles = fs.readdirSync(CHECKS).filter((f) => f.endsWith(".json")).sort();
for (const file of checkFiles) {
  const check = JSON.parse(fs.readFileSync(new URL(file, CHECKS), "utf8"));
  for (const route of check.routes) {
    const hash = route.hash.replace("{session}", SESSION);
    test("route " + hash + " shows the " + check.page + " page with its texts", async () => {
      const app = await boot({ hash });
      assert.deepEqual(visible(app), [check.page]);
      const shown = flat(app.section(check.page)).toLowerCase();
      for (const text of route.texts) {
        assert.ok(shown.includes(text.toLowerCase()), "text " + JSON.stringify(text) + " is not on " + hash);
      }
    });
  }
}

// ---------------------------------------------------------------- overview

test("overview 30 days: four tiles in order, each with a delta and its lines", async () => {
  const app = await boot({ hash: "#/overview" });
  const page = app.section("overview");
  assert.deepEqual(texts(page, "tl-l"), ["Tokens", "Estimated cost", "Cache hit rate", "Agent runs"]);
  const tiles = byClass(page, "kpi");
  assert.equal(tiles.length, 4);
  const view = viewOf(TIDEWATER, "30d");
  assert.equal(flat(byClass(tiles[3], "kpi-v")[0]), String(view.totals.runs));
  assert.match(flat(byClass(tiles[1], "kpi-v")[0]), /^\$\d/);
  assert.equal(flat(byClass(tiles[0], "kpi-v")[0]), "117.2M");
  assert.equal(flat(byClass(tiles[2], "kpi-v")[0]), "78%");
  for (const tile of tiles) assert.match(flat(byClass(tile, "delta")[0]), /vs previous 30 days$/, flat(tile));
  assert.deepEqual(texts(tiles[1], "est"), ["Estimated at API list price"], "one est line, nothing is unpriced");
  assert.deepEqual(texts(tiles[2], "kpi-def"), ["Share of prompt tokens read from cache"]);
  assert.match(flat(byClass(tiles[2], "delta")[0]), /points vs previous 30 days$/, "the hit rate moves in points");
});

test("overview 30 days: cost legend in cost order with its shares, then the agents, effort and footer", async () => {
  const app = await boot({ hash: "#/overview" });
  const page = app.section("overview");
  const usage = usageOf(TIDEWATER);
  const view = usage.views["30d"];

  const byCost = [...view.by_model].sort((a, b) => b.cost - a.cost);
  const cost = cardOf(page, "Estimated cost by model");
  const rows = byClass(cost, "lg")[0].find((n) => n.tagName === "tbody")[0].find((n) => n.tagName === "tr");
  assert.deepEqual(rows.map((r) => flat(r.find((n) => n.tagName === "th")[0])), byCost.map((r) => usage.model_names[r.model]));
  assert.deepEqual(rows.map((r) => flat(byClass(r, "share")[0])), byCost.map((r) => (r.share_lt1 ? "<1%" : r.share_pct + "%")));
  assert.equal(flat(byClass(cost, "est")[0]), "Estimated at API list price");
  assert.equal(byClass(cost, "rseg").length, byCost.length, "one ring segment per priced model");

  const agentNames = view.by_agent.map((a) => a.display);
  const tokens = cardOf(page, "Tokens by agent");
  assert.deepEqual(texts(tokens, "sb-n"), agentNames, "agents follow the payload order");
  assert.deepEqual(texts(tokens, "sb-s"), view.by_agent.map((a) => usage.model_names[a.ran_with[0].model] + " · " + a.ran_with[0].effort + (a.ran_with.length > 1 ? " and " + (a.ran_with.length - 1) + " more" : "")));
  assert.equal(byClass(tokens, "klg").length, 1, "the stacked bars keep their legend totals");
  const costs = view.by_agent.map((a) => a.cost);
  assert.deepEqual(costs, [...costs].sort((a, b) => b - a), "the payload lists agents by cost");

  const cache = cardOf(page, "Cache hit rate by agent");
  assert.deepEqual(texts(cache, "mini-l"), agentNames);
  assert.ok(texts(cache, "mini-s").every((s) => s.endsWith("cache read")));

  const effort = cardOf(page, "Tokens by effort level");
  assert.deepEqual(texts(effort, "hb-l"), ["low", "medium", "high", "xhigh"]);
  assert.equal(texts(effort, "hb-v")[0], "0", "the zero row is kept");

  const foot = flat(byClass(page, "foot")[0]);
  assert.match(foot, /^Read from the transcripts in .+\/projects\. /);
  assert.match(foot, /Read at \d{1,2}:\d{2} [AP]M on [A-Z][a-z]+ \d{1,2}\. Reload the page to update\.$/);
  assert.equal(byClass(page, "foot").length, 1);
  assert.equal(byClass(page, "cd").length, 5, "five cards, and no Needs attention card");
});

test("overview Today: hourly columns with the Hour line", async () => {
  const app = await boot({ hash: "#/overview?range=today" });
  const page = app.section("overview");
  const view = viewOf(TIDEWATER, "today");
  assert.equal(view.bucket_unit, "hour");
  const card = cardOf(page, "Tokens per hour");
  assert.deepEqual(texts(card, "ring-sum"), ["Hour"]);
  assert.equal(byClass(card, "dx")[0].childNodes.length, Math.ceil(view.buckets.length / 7));
  assert.equal(flat(byClass(card, "dx")[0].childNodes[0]), "12 AM");
  assert.equal(byClass(card, "dbars")[0].getAttribute("aria-label"), "Tokens per hour");
  assert.equal(byClass(card, "col").length, view.buckets.reduce((sum, b) => sum + Object.values(b.by_model).filter((v) => v > 0).length, 0));
  assert.equal(texts(page, "tl-l").length, 4);
  assert.match(flat(byClass(page, "kpi")[0]), /vs yesterday/);
});

test("overview 7 days: seven day columns and no Hour line", async () => {
  const app = await boot({ hash: "#/overview?range=7d" });
  const card = cardOf(app.section("overview"), "Tokens per day");
  const view = viewOf(TIDEWATER, "7d");
  assert.equal(view.buckets.length, 7);
  assert.equal(byClass(card, "dx")[0].childNodes.length, 7);
  assert.equal(byClass(card, "ring-sum").length, 0);
  const names = usageOf(TIDEWATER).model_names;
  const seen = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-1"]
    .filter((m) => view.buckets.some((b) => b.by_model[m] > 0)).map((m) => names[m]);
  assert.ok(seen.length > 0);
  assert.deepEqual(byClass(card, "klg")[0].find((n) => n.tagName === "li").map(flat), seen, "the legend lists the models that appear");
});

test("range change: makes no /api/usage request after a real payload, and redraws the view", async () => {
  const app = await boot({ hash: "#/overview" });
  assert.equal(app.count("/api/usage"), 1);
  const before = app.calls.length;
  await app.go("#/overview?range=today");
  assert.ok(texts(app.section("overview"), "cd-h").includes("Tokens per hour"));
  await app.go("#/overview?range=7d");
  assert.ok(texts(app.section("overview"), "cd-h").includes("Tokens per day"));
  await app.go("#/overview?range=30d");
  assert.equal(byClass(app.section("overview"), "dx")[0].childNodes.length, 5);
  assert.equal(app.count("/api/usage"), 1);
  assert.equal(app.calls.length, before, "a range switch fetches nothing");
});

// ---------------------------------------------------------------- the usage payload held back or failing

test("usage held back: data-rendered reaches 1 and data-usage stays unset, then the answer draws the page", async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const app = await boot({
    hash: "#/settings",
    usage: false,
    respond: async (pathname) => { if (pathname === "/api/usage") await gate; return null; },
  });
  assert.equal(app.root.getAttribute("data-rendered"), "1", "boot did not wait for /api/usage");
  assert.equal(app.root.getAttribute("data-usage"), null);
  assert.deepEqual(visible(app), ["settings"]);
  assert.ok(flat(byClass(app.section("settings"), "ph")[0]).includes("Settings"), "Settings still renders");
  await app.go("#/overview");
  assert.deepEqual(visible(app), ["overview"]);
  assert.equal(byClass(app.section("overview"), "kpi").length, 0, "no tiles before the answer");
  release();
  await until(() => app.root.getAttribute("data-usage") === "1", "data-usage");
  assert.equal(byClass(app.section("overview"), "kpi").length, 4);
});

test("usage failing: data-usage is set whatever the status, and the page keeps its head only", async () => {
  const app = await boot({ hash: "#/overview", respond: async (pathname) => (pathname === "/api/usage" ? [503, { error: "down" }] : null) });
  assert.equal(app.root.getAttribute("data-usage"), "1");
  const page = app.section("overview");
  assert.equal(byClass(page, "kpi").length, 0);
  assert.equal(byClass(page, "foot").length, 0);
  assert.equal(byClass(page, "ph").length, 1);
});

// ---------------------------------------------------------------- other projects

test("overview Driftwood 30 days: no earlier data on every tile, and the partly priced line", async () => {
  const app = await boot({ hash: "#/overview?project=" + keyOf("Driftwood") });
  const page = app.section("overview");
  assert.equal(viewOf(keyOf("Driftwood"), "30d").previous, null);
  const tiles = byClass(page, "kpi");
  assert.equal(tiles.length, 4);
  for (const tile of tiles) assert.deepEqual(texts(tile, "delta"), ["No earlier data to compare"]);
  assert.deepEqual(texts(tiles[1], "est"), [
    "Estimated at API list price",
    "The dashboard has no list price for one model here, so the total leaves it out.",
  ]);
  const cost = cardOf(page, "Estimated cost by model");
  const rows = byClass(cost, "lg")[0].find((n) => n.tagName === "tbody")[0].find((n) => n.tagName === "tr");
  const last = rows[rows.length - 1];
  assert.equal(flat(last.find((n) => n.tagName === "th")[0]), "claude-opus-6-preview", "a model the catalog lacks keeps its id, last");
  assert.equal(flat(last.find((n) => n.tagName === "td")[0]), "Not priced");
  assert.equal(byClass(last, "share").length, 0, "a model with no cost has no share");
});

test("overview Harbor Light on Today draws without throwing", async () => {
  const app = await boot({ hash: "#/overview?range=today&project=" + keyOf("Harbor Light") });
  const page = app.section("overview");
  assert.equal(byClass(page, "kpi").length, 4);
  assert.equal(viewOf(keyOf("Harbor Light"), "today").totals.tokens, 0);
  assert.equal(logged.filter((m) => m.includes("failed to render")).length, 0);
});

test("overview for a project with no usage draws without throwing", async () => {
  for (const name of ["Saltmarsh", "Lantern"]) {
    const app = await boot({ hash: "#/overview?project=" + keyOf(name) });
    assert.equal(byClass(app.section("overview"), "kpi").length, 4, name);
  }
});

// ---------------------------------------------------------------- the helpers pages share

test("usage-page: ticksOf, ranWithLine and shareText", async () => {
  createPage();
  const format = await import(JS + "format.js");
  format.setStrings(STRINGS);
  const { ticksOf, ranWithLine } = await import(JS + "usage-page.js");
  assert.deepEqual(ticksOf([0, 5, 10, 15]), { step: 5, steps: 3 });
  assert.deepEqual(ticksOf([0, 2500000, 5000000, 7500000, 10000000]), { step: 2500000, steps: 4 });
  assert.deepEqual(ticksOf([0]), { step: 1, steps: 1 });
  assert.deepEqual(ticksOf([]), { step: 1, steps: 1 });
  const u = { model: (id) => ({ a: "Alpha" }[id] || id) };
  assert.equal(ranWithLine(u, { ran_with: [{ model: "a", effort: "high" }] }), "Alpha · high");
  assert.equal(ranWithLine(u, { ran_with: [{ model: "a", effort: null }] }), "Alpha · effort not recorded");
  assert.equal(ranWithLine(u, { ran_with: [{ model: "a", effort: "high" }, { model: "b", effort: "low" }, { model: "a", effort: "low" }] }), "Alpha · high and 2 more");
  assert.equal(format.shareText(19, false), "19%");
  assert.equal(format.shareText(0, true), "<1%");
});

// ---------------------------------------------------------------- run

let failed = 0;
for (const [name, fn] of tests) {
  logged.length = 0;
  try {
    await fn();
    const bad = logged.filter((m) => m.includes("failed to render"));
    assert.deepEqual(bad, [], "a page failed to render");
    console.log("ok   " + name);
  } catch (err) {
    failed += 1;
    console.log("FAIL " + name + "\n     " + String(err && err.stack ? err.stack : err).split("\n").slice(0, 6).join("\n     "));
    for (const line of logged.slice(0, 3)) console.log("     console.error: " + line.split("\n")[0]);
  }
}
console.log((tests.length - failed) + " of " + tests.length + " checks passed");
process.exit(failed ? 1 : 0);

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
// With usage set, boot also waits for data-usage. It can arrive before or after data-rendered, so both are awaited.
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
      const shown = flat(app.section(check.page));
      for (const text of route.texts) {
        assert.ok(shown.includes(text), "text " + JSON.stringify(text) + " is not on " + hash);
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

test("usage failing: data-usage is set whatever the status, and the page keeps its head and the transcripts state", async () => {
  const app = await boot({ hash: "#/overview", respond: async (pathname) => (pathname === "/api/usage" ? [503, { error: "down" }] : null) });
  assert.equal(app.root.getAttribute("data-usage"), "1");
  const page = app.section("overview");
  assert.equal(byClass(page, "kpi").length, 0);
  assert.equal(byClass(page, "foot").length, 0);
  assert.equal(byClass(page, "ph").length, 1);
  assert.deepEqual(texts(page, "cd-h"), ["Can't read the transcripts"]);
  assert.ok(flat(page).includes(DATA["/api/projects"].body.transcripts_dir_display), "the state names the folder");
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

test("overview Harbor Light on Today: the no-range card, with the project sentence and a range switch", async () => {
  const app = await boot({ hash: "#/overview?range=today&project=" + keyOf("Harbor Light") });
  const page = app.section("overview");
  assert.equal(viewOf(keyOf("Harbor Light"), "today").totals.requests, 0);
  assert.equal(byClass(page, "kpi").length, 0);
  assert.deepEqual(texts(page, "es-h"), ["No usage in this range"]);
  assert.deepEqual(texts(page, "es-t"), [STRINGS.s_no_range_t]);
  assert.deepEqual(texts(page, "cd-h"), ["Tokens per day"]);
  assert.equal(byClass(page, "segs-range").length, 2, "the page head's switch and the card's");
  assert.equal(byClass(page, "foot").length, 1, "the footer follows");
});

test("overview no-range card: the longest range gets its own sentence, and a click on the card's switch changes the range", async () => {
  const key = keyOf("Harbor Light");
  const app = await boot({ hash: "#/overview?project=" + key, respond: patchedUsage((b) => { b.views["30d"].totals.requests = 0; }) });
  assert.deepEqual(texts(app.section("overview"), "es-t"), [STRINGS.s_no_range_longest_t]);
  const radios = byClass(byClass(app.section("overview"), "cd")[0], "seg");
  assert.equal(radios.length, 3);
  radios[0].click();
  await tick(20);
  assert.ok(app.win.location.hash.includes("range=today"), app.win.location.hash);
});

test("overview Saltmarsh: No usage yet, and the sentence, with the footer", async () => {
  const app = await boot({ hash: "#/overview?project=" + keyOf("Saltmarsh") });
  const page = app.section("overview");
  assert.equal(usageOf(keyOf("Saltmarsh")).no_usage, true);
  assert.equal(byClass(page, "kpi").length, 0);
  assert.deepEqual(texts(page, "cd-h"), ["No usage yet"]);
  assert.deepEqual(texts(page, "es-t"), [STRINGS.s_no_usage_t]);
  assert.equal(byClass(page, "foot").length, 1);
});

test("overview Lantern: Folder not found with the project's path and the config file, at once and with usage held back", async () => {
  const lantern = DATA["/api/projects"].body.projects.find((p) => p.name === "Lantern");
  assert.equal(lantern.state, "missing_folder");
  const check = (app) => {
    const page = app.section("overview");
    const note = byClass(page, "nt-empty");
    assert.equal(note.length, 1);
    assert.equal(note[0].getAttribute("aria-label"), "Folder not found");
    assert.deepEqual(texts(page, "nt-h"), ["Folder not found"]);
    assert.deepEqual(texts(page, "nt-t"), [
      "The project list points Lantern at " + lantern.path_display + ", and there's no folder there. Fix the path in "
      + DATA["/api/projects"].body.config_file_display + ", or take Lantern off the list.",
    ]);
    assert.equal(byClass(page, "kpi").length, 0);
    assert.equal(byClass(page, "foot").length, 0);
  };
  check(await boot({ hash: "#/overview?project=" + lantern.key }));
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const held = await boot({
    hash: "#/overview?project=" + lantern.key,
    usage: false,
    respond: async (pathname) => { if (pathname === "/api/usage") await gate; return null; },
  });
  check(held);
  release();
  await until(() => held.root.getAttribute("data-usage") === "1", "data-usage");
  check(held);
});

test("overview All projects with no requests in the range: the all-projects sentence", async () => {
  const app = await boot({
    hash: "#/overview?project=all&range=today",
    respond: patchedUsage((b) => { b.views.today.totals.requests = 0; }),
  });
  const page = app.section("all-projects");
  assert.equal(byClass(page, "kpi").length, 0);
  assert.deepEqual(texts(page, "es-t"), [STRINGS.s_no_range_all_t]);
  assert.deepEqual(texts(page, "es-h"), ["No usage in this range"]);
});

test("overview All projects with no usage at all: the all-projects sentence, not the this-project one", async () => {
  const app = await boot({
    hash: "#/overview?project=all",
    respond: patchedUsage((b) => { b.no_usage = true; }),
  });
  const page = app.section("all-projects");
  assert.deepEqual(texts(page, "es-t"), [STRINGS.s_no_range_all_t]);
  assert.ok(!flat(page).includes("this project"), flat(page));
});

test("every usage page: no-range and no-usage states come from fillUsage, so Agents, Models and Sessions show them too", async () => {
  const quiet = keyOf("Harbor Light");
  for (const [hash, section] of [["#/agents", "agents"], ["#/models", "models"], ["#/sessions", "sessions"], ["#/agents/builder", "agent-detail"]]) {
    const app = await boot({ hash: hash + "?range=today&project=" + quiet });
    const page = app.section(section);
    assert.deepEqual(texts(page, "es-h"), ["No usage in this range"], hash);
    assert.equal(byClass(page, "kpi").length, 0, hash);
    const none = await boot({ hash: hash + "?project=" + keyOf("Saltmarsh") });
    assert.deepEqual(texts(none.section(section), "cd-h"), ["No usage yet"], hash);
  }
});

test("session detail on Today: a session outside today's view still draws", async () => {
  const quiet = keyOf("Harbor Light");
  const list = viewOf(quiet, "30d").sessions;
  assert.ok(list.length > 0, "Harbor Light has sessions in 30 days");
  assert.equal(viewOf(quiet, "today").totals.requests, 0);
  const app = await boot({ hash: "#/sessions/" + encodeURIComponent(list[0].session_id) + "?range=today&project=" + quiet });
  const page = app.section("session-detail");
  assert.equal(byClass(page, "kpi").length, 4);
  assert.deepEqual(texts(page, "es-h"), []);
});

test("session detail: a project with no usage still gets No usage yet", async () => {
  const app = await boot({ hash: "#/sessions/anything?project=" + keyOf("Saltmarsh") });
  assert.deepEqual(texts(app.section("session-detail"), "cd-h"), ["No usage yet"]);
});

// ---------------------------------------------------------------- the transcripts folder

const projectsWith = (fix) => (pathname) => {
  if (pathname !== "/api/projects") return null;
  const body = structuredClone(DATA["/api/projects"].body);
  fix(body);
  return [200, body];
};

test("reader.readable false: every usage page says it can't read the transcripts, and Settings keeps working", async () => {
  const respond = projectsWith((b) => { b.reader.readable = false; });
  const path = DATA["/api/projects"].body.transcripts_dir_display;
  for (const [hash, section] of [["#/overview", "overview"], ["#/overview?project=all", "all-projects"], ["#/agents", "agents"],
    ["#/agents/builder", "agent-detail"], ["#/models", "models"], ["#/sessions", "sessions"], ["#/sessions/x", "session-detail"]]) {
    const app = await boot({ hash, respond });
    const page = app.section(section);
    assert.deepEqual(texts(page, "cd-h"), ["Can't read the transcripts"], hash);
    assert.ok(flat(page).includes("The dashboard can't find or read " + path), hash);
    assert.equal(byClass(page, "kpi").length, 0, hash);
  }
  const app = await boot({ hash: "#/settings", respond });
  assert.ok(flat(byClass(app.section("settings"), "ph")[0]).includes("Settings"));
  assert.ok(!flat(app.section("settings")).includes("Can't read the transcripts"));
});

test("reader.readable false shows at once, with usage held back", async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const app = await boot({
    hash: "#/overview",
    usage: false,
    respond: async (pathname, params, n) => {
      if (pathname === "/api/usage") await gate;
      return projectsWith((b) => { b.reader.readable = false; })(pathname, params, n);
    },
  });
  assert.deepEqual(texts(app.section("overview"), "cd-h"), ["Can't read the transcripts"]);
  assert.equal(byClass(app.section("overview"), "es-t").filter((n) => n.getAttribute("role") === "status").length, 0);
  release();
  await until(() => app.root.getAttribute("data-usage") === "1", "data-usage");
});

// ---------------------------------------------------------------- the waiting line

const WAITING = ["settings", "attention", "files", "rules"];

test("usage held back: one waiting line with the file count, then it clears on the answer", async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const app = await boot({
    hash: "#/overview",
    usage: false,
    respond: async (pathname, params, n) => {
      if (pathname === "/api/usage") await gate;
      return projectsWith((b) => { b.reader.files = 538; })(pathname, params, n);
    },
  });
  const status = () => byClass(app.section("overview"), "es-t").filter((n) => n.getAttribute("role") === "status");
  assert.equal(status().length, 1);
  assert.equal(flat(status()[0]), "Reading 538 transcript files. Only the first load takes this long.");
  assert.equal(byClass(app.section("overview"), "foot").length, 0);
  release();
  await until(() => app.root.getAttribute("data-usage") === "1", "data-usage");
  assert.equal(status().length, 0, "the line is gone once the page redraws");
  assert.equal(byClass(app.section("overview"), "kpi").length, 4);
});

test("usage held back: no file count gives the line without a number", async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const app = await boot({
    hash: "#/models",
    usage: false,
    respond: async (pathname, params, n) => {
      if (pathname === "/api/usage") await gate;
      return projectsWith((b) => { b.reader.files = null; b.reader.warm = true; })(pathname, params, n);
    },
  });
  const lines = byClass(app.section("models"), "es-t").map(flat);
  assert.deepEqual(lines, ["Reading your transcripts. Only the first load takes this long."]);
  release();
  await until(() => app.root.getAttribute("data-usage") === "1", "data-usage");
});

test("usage held back: Settings, Needs attention, Installed files and Rules reference never show the waiting line", async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const app = await boot({
    hash: "#/settings",
    usage: false,
    respond: async (pathname) => { if (pathname === "/api/usage") await gate; return null; },
  });
  for (const name of WAITING) {
    await app.go("#/" + name);
    assert.deepEqual(visible(app), [name]);
    assert.ok(!flat(app.section(name)).includes("Only the first load takes this long"), name);
    assert.equal(byClass(app.section(name), "es-t").filter((n) => n.getAttribute("role") === "status").length, 0, name);
  }
  release();
  await until(() => app.root.getAttribute("data-usage") === "1", "data-usage");
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

// ---------------------------------------------------------------- agents and agent detail

const tagged = (root, tag) => root.find((n) => n.tagName === tag);
const headers = (table) => tagged(tagged(table, "thead")[0], "th").map(flat);
const bodyRows = (table) => tagged(tagged(table, "tbody")[0], "tr");
const cellsOf = (row) => tagged(row, "td");
const agentsTable = (page) => byClass(cardOf(page, "Agents"), "dt")[0];
const rowFor = (table, name) => {
  const row = bodyRows(table).find((r) => flat(cellsOf(r)[0]) === name);
  assert.ok(row, "a row for " + name);
  return row;
};
const hrefOf = (node) => tagged(node, "a")[0].getAttribute("href");

test("agents: eight columns, the server's order, and the note once under the table", async () => {
  const app = await boot({ hash: "#/agents" });
  const page = app.section("agents");
  const view = viewOf(TIDEWATER, "30d");
  const table = agentsTable(page);
  assert.deepEqual(headers(table), ["Agent", "Runs", "Tokens", "Estimated cost", "Cache hit rate", "Ran with", "Pinned to", "Pin check"]);
  assert.deepEqual(bodyRows(table).map((r) => flat(cellsOf(r)[0])), view.by_agent.map((a) => a.display), "Agents follow by_agent order");
  assert.equal(byClass(table, "lnk").length, view.by_agent.length);
  const notes = texts(cardOf(page, "Agents"), "est");
  assert.equal(notes.filter((n) => n.startsWith("This check reads today's files")).length, 1, "the pin note shows once");
  assert.equal(byClass(page, "foot").length, 1);
  const main = rowFor(table, "Main session");
  assert.match(flat(cellsOf(main)[1]), /^\d+ sessions?$/);
  assert.equal(texts(cellsOf(main)[1], "muted").length, 1);
  assert.ok(flat(cellsOf(main)[6]).includes("From your settings files, not an agent file."));
});

test("agents: builder and reviewer show Pin overridden, scribe shows Differs from pin, each with its mark", async () => {
  const app = await boot({ hash: "#/agents" });
  const table = agentsTable(app.section("agents"));
  for (const name of ["builder", "reviewer"]) {
    const pill = byClass(cellsOf(rowFor(table, name))[7], "st")[0];
    assert.ok(flat(pill).startsWith("Pin overridden"), name + ": " + flat(pill));
    assert.ok(hasClass(pill, "st-overridden"), name);
    assert.equal(byClass(pill, "mk").length, 1, name + " has its mark");
  }
  const scribe = byClass(cellsOf(rowFor(table, "scribe"))[7], "st")[0];
  assert.ok(flat(scribe).startsWith("Differs"), flat(scribe));
  assert.ok(hasClass(scribe, "st-differs"));
  assert.equal(byClass(scribe, "mk").length, 1);
  assert.ok(flat(cellsOf(rowFor(table, "scribe"))[7]).includes("Differs from pin") || /Differs in \d+ of \d+ runs/.test(flat(scribe)));
});

test("agents: Ran with shows the first pair and the count of others, and Pinned to shows a model and effort", async () => {
  const app = await boot({ hash: "#/agents" });
  const table = agentsTable(app.section("agents"));
  const usage = usageOf(TIDEWATER);
  for (const a of usage.views["30d"].by_agent) {
    const cell = cellsOf(rowFor(table, a.display))[5];
    const first = a.ran_with[0];
    assert.ok(flat(cell).startsWith(usage.model_names[first.model] + ", " + (first.effort === null ? "effort not recorded" : first.effort)), a.display + ": " + flat(cell));
    assert.equal(byClass(cell, "cell-note").length, a.ran_with.length > 1 ? 1 : 0, a.display);
  }
});

test("agents All projects: no Pinned to or Pin check column and no note", async () => {
  const app = await boot({ hash: "#/agents?project=all" });
  const page = app.section("agents");
  const table = agentsTable(page);
  assert.deepEqual(headers(table), ["Agent", "Runs", "Tokens", "Estimated cost", "Cache hit rate", "Ran with"]);
  assert.ok(bodyRows(table).every((r) => cellsOf(r).length === 6));
  assert.equal(byClass(page, "st").length, 0, "no pills");
  assert.ok(!flat(page).includes("This check reads today's files"));
  assert.ok(!flat(page).includes("Pinned to"));
});

test("agents Driftwood: a Main session that can't be checked shows Can't check pin with the Unknown mark", async () => {
  const app = await boot({ hash: "#/agents?project=" + keyOf("Driftwood") });
  const table = agentsTable(app.section("agents"));
  const pill = byClass(cellsOf(rowFor(table, "Main session"))[7], "st")[0];
  assert.equal(flat(pill), "Can't check pin");
  assert.ok(hasClass(pill, "st-unknown"));
  assert.equal(byClass(pill, "mk").length, 1);
});

test("agent detail builder: the tiles, the pin card, both charts and the recent runs", async () => {
  const app = await boot({ hash: "#/agents/builder" });
  const page = app.section("agent-detail");
  const a = viewOf(TIDEWATER, "30d").by_agent.find((row) => row.route_key === "builder");
  assert.deepEqual(texts(page, "tl-l"), ["Agent runs", "Tokens", "Estimated cost", "Cache hit rate"]);
  assert.equal(flat(byClass(byClass(page, "kpi")[0], "kpi-v")[0]), String(a.runs));
  assert.equal(byClass(page, "g21-pin").length, 1);
  const pin = cardOf(page, "Did it run as pinned?");
  assert.ok(hasClass(byClass(pin, "st")[0], "st-overridden"));
  assert.equal(flat(byClass(pin, "pin-top")[0]).includes("Pinned to Fable 5.1 at xhigh. Ran with"), true, flat(byClass(pin, "pin-top")[0]));
  assert.ok(byClass(pin, "en-rs").length >= 1, "a sentence follows the pill");
  const link = tagged(byClass(pin, "pin-link")[0], "a")[0];
  assert.equal(flat(link), "Open the trail");
  assert.ok(link.getAttribute("href").startsWith("#/settings/builder/"), link.getAttribute("href"));

  const runs = cardOf(page, "Runs over time");
  assert.deepEqual(texts(runs, "ring-sum"), ["Runs per day"]);
  const labels = byClass(runs, "dy")[0].childNodes.map(flat);
  assert.deepEqual(labels, [...a.runs_ticks.slice(1)].reverse().map(String).concat("0"), "the y axis uses the agent's own ticks");
  assert.ok(labels.every((l) => /^\d+$/.test(l)), "integer ticks");

  const tokens = cardOf(page, "Tokens and estimated cost");
  assert.equal(byClass(tokens, "sb-row").length, 1);
  assert.deepEqual(headers(byClass(tokens, "dt-kinds")[0]), ["Kind", "Tokens", "Estimated cost"]);
  assert.equal(bodyRows(byClass(tokens, "dt-kinds")[0]).length, 4);
  assert.equal(flat(tokens).includes("thinking tokens"), Boolean(a.thinking));
  assert.equal(byClass(tokens, "est").length, 1);
});

test("agent detail: Recent runs shows at most eight runs, each linking its session", async () => {
  const app = await boot({ hash: "#/agents/builder" });
  const a = viewOf(TIDEWATER, "30d").by_agent.find((row) => row.route_key === "builder");
  assert.ok(a.recent_runs.length <= 8);
  const recent = cardOf(app.section("agent-detail"), "Recent runs");
  const table = byClass(recent, "dt")[0];
  assert.deepEqual(headers(table), ["Started", "Session", "Model", "Effort", "Tokens", "Estimated cost"]);
  const rows = bodyRows(table);
  assert.equal(rows.length, a.recent_runs.length);
  rows.forEach((row, i) => {
    assert.ok(hrefOf(cellsOf(row)[1]).startsWith("#/sessions/" + encodeURIComponent(a.recent_runs[i].session_id)), hrefOf(cellsOf(row)[1]));
    assert.ok(flat(cellsOf(row)[1]).startsWith("Session from "));
  });
  const busiest = viewOf(TIDEWATER, "30d").by_agent.map((x) => x.recent_runs.length);
  assert.ok(Math.max(...busiest) <= 8);
});

test("agent detail Main session: its sessions tile, Matches pin and the Lowered note", async () => {
  const app = await boot({ hash: "#/agents/@main" });
  const page = app.section("agent-detail");
  assert.deepEqual(texts(page, "tl-l")[0], "Sessions");
  const a = viewOf(TIDEWATER, "30d").by_agent.find((row) => row.route_key === "@main");
  assert.equal(flat(byClass(byClass(page, "kpi")[0], "kpi-v")[0]), String(a.sessions));
  const pin = cardOf(page, "Did it run as pinned?");
  assert.ok(hasClass(byClass(pin, "st")[0], "st-match"));
  assert.ok(flat(pin).includes("Runs at a lower level than it's set to"));
  assert.ok(byClass(pin, "pin-link").length === 1);
});

test("agent detail All projects: tiles alone, no pin card, and Recent runs gains Project", async () => {
  const app = await boot({ hash: "#/agents/builder?project=all" });
  const page = app.section("agent-detail");
  assert.equal(byClass(page, "g21-pin").length, 0);
  assert.equal(byClass(page, "pin").length, 0);
  assert.equal(byClass(page, "kpi").length, 4);
  const table = byClass(cardOf(page, "Recent runs"), "dt")[0];
  assert.deepEqual(headers(table), ["Started", "Session", "Project", "Model", "Effort", "Tokens", "Estimated cost"]);
  const a = viewOf("all", "30d").by_agent.find((row) => row.route_key === "builder");
  assert.deepEqual(bodyRows(table).map((r) => flat(cellsOf(r)[2])), a.recent_runs.map((r) => r.project));
});

test("agent detail: an agent not in this view gets the empty state, and the name is plain text", async () => {
  const app = await boot({ hash: "#/agents/no-such-agent" });
  const page = app.section("agent-detail");
  assert.equal(flat(byClass(page, "ph")[0]).includes("no-such-agent"), true);
  assert.equal(byClass(page, "kpi").length, 0);
  assert.deepEqual(texts(page, "cd-h"), ["No usage in this range"]);
  const unnamed = await boot({ hash: "#/agents/@unnamed" });
  assert.ok(flat(byClass(unnamed.section("agent-detail"), "h1")[0] || byClass(unnamed.section("agent-detail"), "ph")[0]).includes("Unnamed agent"));
});

test("agent detail Today: the runs chart is hourly with its Runs per hour line", async () => {
  const app = await boot({ hash: "#/agents/builder?range=today" });
  const page = app.section("agent-detail");
  const card = cardOf(page, "Runs over time");
  assert.deepEqual(texts(card, "ring-sum"), ["Runs per hour"]);
});

// ---------------------------------------------------------------- pinView on hand-built agents

const NAMES = { "claude-fable-5-1": "Fable 5.1", "claude-opus-5-5": "Opus 5.5", "claude-sonnet-5-5": "Sonnet 5.5" };
const U = { model: (id) => NAMES[id] || id };
const FABLE = "claude-fable-5-1";
const SONNET = "claude-sonnet-5-5";

function setting(state, o = {}) {
  return {
    state,
    pinned: { value: o.pv ?? "xhigh", file: "agents/a.md", line: 3, status: "in_effect", id: o.id ?? o.pv ?? "xhigh" },
    expected: {
      value: "xhigh", status: "in_effect", becomes: null, key: "effort", file: null, line: null, layer: "agent",
      via: null, reason: null, rule_id: null, ...(o.e || {}),
    },
    cap: o.cap ?? null,
    ran: o.ran ?? [],
    runs_match_pin: o.rmp ?? false,
  };
}
function agentOf(pinned, state, model, effort, extra = {}) {
  return { pin: { state, pinned, source: "agent_file", mismatched_runs: 0, total_runs: 2, model, effort, ...extra } };
}

test("pinView: model-only, effort-only and no pin", async () => {
  createPage();
  const format = await import(JS + "format.js");
  format.setStrings(STRINGS);
  const { pinView } = await import(JS + "pin-view.js");

  const modelOnly = pinView(U, agentOf("model_only", "matches", setting("matches", { pv: FABLE, e: { key: "model", value: FABLE } }), null));
  assert.equal(modelOnly.pinnedText, "Fable 5.1, effort not pinned");
  assert.equal(modelOnly.detailPinned, "Fable 5.1, effort not pinned");
  assert.equal(modelOnly.pill, "match");
  assert.equal(modelOnly.pillLabel, null);
  assert.equal(modelOnly.note, null);
  assert.deepEqual(modelOnly.sentences, []);
  assert.equal(modelOnly.trailKey, "model");
  assert.equal(modelOnly.pinnedNote, null);

  const effortOnly = pinView(U, agentOf("effort_only", "matches", null, setting("matches", { pv: "high", e: { value: "high" } })));
  assert.equal(effortOnly.pinnedText, "high, model not pinned");
  assert.equal(effortOnly.detailPinned, "high, model not pinned");
  assert.equal(effortOnly.trailKey, "effort");

  const both = pinView(U, agentOf("both", "matches", setting("matches", { pv: FABLE, e: { key: "model", value: FABLE } }), setting("matches")));
  assert.equal(both.pinnedText, "Fable 5.1, xhigh");
  assert.equal(both.detailPinned, "Pinned to Fable 5.1 at xhigh.");
  assert.equal(both.trailKey, "effort", "effort when the states tie");

  const plugin = pinView(U, { pin: null });
  assert.equal(plugin.pill, null);
  assert.equal(plugin.pinnedText, "No pin found");
  assert.equal(plugin.pinnedNote, "No agent file in the folders the dashboard reads.");
  assert.equal(plugin.sentences.length, 1);
  assert.ok(plugin.sentences[0].startsWith("The dashboard found no agent file"));
  assert.equal(plugin.trailKey, null);
  assert.equal(plugin.note, null);

  const fileNone = pinView(U, agentOf("none", null, null, null));
  assert.equal(fileNone.pinnedText, "No pin found");
  assert.equal(fileNone.pinnedNote, null);
  assert.deepEqual(fileNone.sentences, []);
  assert.equal(fileNone.pill, null);
  const mainNone = pinView(U, agentOf("none", null, null, null, { source: "settings" }));
  assert.equal(mainNone.pinnedText, "The dashboard can't tell what this agent is pinned to.");
  assert.equal(mainNone.detailPinned, "The dashboard can't tell what this agent is pinned to.");
  assert.equal(mainNone.pinnedNote, "From your settings files, not an agent file.");

  const cannot = pinView(U, agentOf("both", "cannot_check", setting("matches", { pv: FABLE }), setting("cannot_check")));
  assert.equal(cannot.pill, "unknown");
  assert.equal(cannot.sentences.length, 1);
  assert.ok(cannot.sentences[0].startsWith("The dashboard can't tell what this agent should run with"));
});

test("pinView: a Lowered pin with every run at the pin", async () => {
  createPage();
  const format = await import(JS + "format.js");
  format.setStrings(STRINGS);
  const { pinView } = await import(JS + "pin-view.js");
  const lowered = { status: "lowered", value: "xhigh", becomes: "high", rule_id: "effort-lowered-by-cap", model: FABLE };
  const withFile = { key: "maxEffortLevel", value: "high", model: FABLE, file: "~/.claude/settings.json", line: 4 };
  const one = pinView(U, agentOf("effort_only", "matches", null, setting("matches", { rmp: true, e: lowered, cap: withFile })));
  assert.equal(one.pill, "match");
  assert.equal(one.note, null, "no Lowered note when every run still equals the pin");
  assert.deepEqual(one.sentences, ["These runs match the pin. Right now maxEffortLevel caps Fable 5.1 at high from ~/.claude/settings.json, line 4, so new runs should use high."]);

  const noFile = pinView(U, agentOf("effort_only", "matches", null, setting("matches", { rmp: true, e: lowered, cap: { ...withFile, file: null, line: null } })));
  assert.deepEqual(noFile.sentences, ["These runs match the pin. Right now maxEffortLevel caps Fable 5.1 at high, so new runs should use high."]);

  const unsupported = { status: "lowered", value: "max", becomes: "xhigh", rule_id: "effort-unsupported-level", model: SONNET };
  const un = pinView(U, agentOf("effort_only", "matches", null, setting("matches", {
    pv: "max", rmp: true, e: unsupported, cap: { key: "maxEffortLevel", value: "xhigh", model: SONNET, file: null, line: null },
  })));
  assert.deepEqual(un.sentences, ["These runs match the pin. Right now Sonnet 5.5 has no max level, so new runs should use xhigh."]);

  const ml = pinView(U, agentOf("effort_only", "matches_lowered", null, setting("matches_lowered", { e: { ...lowered, reason: "Capped by maxEffortLevel." } })));
  assert.equal(ml.pill, "match");
  assert.equal(ml.note, "Runs at a lower level than it's set to");
  assert.deepEqual(ml.sentences, ["Capped by maxEffortLevel."]);
});

test("pinView: a lost pin with every run at the pin, and without", async () => {
  createPage();
  const format = await import(JS + "format.js");
  format.setStrings(STRINGS);
  const { pinView } = await import(JS + "pin-view.js");
  const cap = { key: "maxEffortLevel", value: "high", model: FABLE, file: "~/.claude/settings.json", line: 9 };
  const capped = { status: "lowered", value: "xhigh", becomes: "high", key: "effortLevel", layer: "user", file: "~/.claude/settings.json", line: 7, rule_id: "effort-lowered-by-cap", model: FABLE, reason: "maxEffortLevel caps it." };
  const viaCap = pinView(U, agentOf("effort_only", "overridden", null, setting("overridden", { rmp: true, e: capped, cap })));
  assert.equal(viaCap.pill, "overridden");
  assert.equal(viaCap.note, "Ran as pinned, but another setting wins right now");
  assert.deepEqual(viaCap.sentences, ["These runs match the pin. Right now effortLevel overrides it from ~/.claude/settings.json, line 7. maxEffortLevel caps Fable 5.1 at high, so new runs should use high."]);

  const winner = { value: "max", key: "effortLevel", layer: "user", file: "~/.claude/settings.json", line: 7 };
  const viaSource = pinView(U, agentOf("effort_only", "overridden", null, setting("overridden", { rmp: true, e: winner })));
  assert.deepEqual(viaSource.sentences, ["These runs match the pin. Right now effortLevel overrides it from ~/.claude/settings.json, line 7, so new runs should use max."]);

  const none = pinView(U, agentOf("effort_only", "overridden", null, setting("overridden", { rmp: true, e: { value: "max", key: "effortLevel", layer: "managed" } })));
  assert.deepEqual(none.sentences, ["These runs match the pin. Right now another setting wins, so new runs should use max."]);

  const shell = { value: "max", key: "effort", layer: "env", file: "Shell", line: null };
  const shellRuns = pinView(U, agentOf("effort_only", "overridden", null, setting("overridden", { rmp: true, e: shell })));
  assert.deepEqual(shellRuns.sentences, ["These runs match the pin. Right now effortLevel overrides it from the shell, so new runs should use max."]);

  // The runs did not match the pin: the override sentences, and the cap's reason after them.
  const plain = pinView(U, agentOf("effort_only", "overridden", null, setting("overridden", { ran: ["max"], e: winner })));
  assert.equal(plain.note, null);
  assert.deepEqual(plain.sentences, ["effortLevel in ~/.claude/settings.json, line 7, overrides this pin, so the agent runs at max."]);
  const shellLost = pinView(U, agentOf("effort_only", "overridden", null, setting("overridden", { ran: ["max"], e: shell })));
  assert.deepEqual(shellLost.sentences, ["effortLevel in the shell overrides this pin, so the agent runs at max."]);
  const lostCap = pinView(U, agentOf("effort_only", "overridden", null, setting("overridden", { ran: ["high"], e: capped, cap })));
  assert.deepEqual(lostCap.sentences, [
    "effortLevel in ~/.claude/settings.json, line 7, overrides this pin, so the agent runs at high.",
    "maxEffortLevel caps it.",
  ]);
  const modelLost = pinView(U, agentOf("model_only", "overridden", setting("overridden", { pv: FABLE, ran: [SONNET], e: { key: "model", value: SONNET, file: "~/.claude/settings.json", line: 2, layer: "user" } }), null));
  assert.deepEqual(modelLost.sentences, ["model in ~/.claude/settings.json, line 2, overrides this pin, so the agent runs on Sonnet 5.5."]);

  // One lost setting that did not run at the pin keeps the note off.
  const mixedNote = pinView(U, agentOf("both", "overridden",
    setting("overridden", { pv: FABLE, rmp: true, e: { key: "model", value: SONNET, file: "m.json", line: 1 } }),
    setting("overridden", { ran: ["max"], e: winner })));
  assert.equal(mixedNote.note, null);
});

test("pinView: mixed runs name how many differ, and only an agent file's model gets a sentence", async () => {
  createPage();
  const format = await import(JS + "format.js");
  format.setStrings(STRINGS);
  const { pinView } = await import(JS + "pin-view.js");
  const mixed = pinView(U, agentOf("effort_only", "mixed", null, setting("mixed", { ran: ["xhigh", "low"] }), { mismatched_runs: 2, total_runs: 5 }));
  assert.equal(mixed.pill, "differs");
  assert.equal(mixed.pillLabel, "Differs in 2 of 5 runs");
  assert.deepEqual(mixed.sentences, [], "effort gets no sentence");
  const every = pinView(U, agentOf("effort_only", "differs", null, setting("differs", { ran: ["low"] }), { mismatched_runs: 2, total_runs: 2 }));
  assert.equal(every.pillLabel, null);
  const fewer = pinView(U, agentOf("effort_only", "differs", null, setting("differs", { ran: ["low"] }), { mismatched_runs: 1, total_runs: 2 }));
  assert.equal(fewer.pillLabel, "Differs in 1 of 2 runs");

  const model = setting("differs", { pv: FABLE, ran: [SONNET], e: { key: "model", value: FABLE } });
  const file = pinView(U, agentOf("model_only", "differs", model, null));
  assert.deepEqual(file.sentences, ["Ran on Sonnet 5.5, but its agent file pins Fable 5.1."]);
  const main = pinView(U, agentOf("model_only", "differs", model, null, { source: "settings" }));
  assert.deepEqual(main.sentences, []);
  assert.equal(main.pinnedNote, "From your settings files, not an agent file.");
});

// ---------------------------------------------------------------- models and the prices tooltip

const modelsTable = (page) => byClass(cardOf(page, "Models"), "dt")[0];
const byCostOrder = (view) => [...view.by_model].sort((a, b) => (a.cost === null ? 1 : 0) - (b.cost === null ? 1 : 0) || (b.cost || 0) - (a.cost || 0));

test("models: six columns, rows in cost order, the id beside the display name, and Used by from the row's agents", async () => {
  const app = await boot({ hash: "#/models" });
  const page = app.section("models");
  const view = viewOf(TIDEWATER, "30d");
  const table = modelsTable(page);
  assert.deepEqual(headers(table), ["Model", "Requests", "Tokens", "Estimated cost", "Cache hit rate", "Used by"]);
  const want = byCostOrder(view);
  assert.deepEqual(bodyRows(table).map((r) => flat(cellsOf(r)[0])), want.map((r) => r.display_name + " " + r.model));
  bodyRows(table).forEach((row, i) => {
    assert.equal(flat(cellsOf(row)[5]), want[i].agents.join(", "), "Used by for " + want[i].model);
    assert.equal(texts(row, "mono")[0], want[i].model);
    assert.equal(hasClass(byClass(row, "swatch")[0], "cat-other"), want[i].cat === "other", "swatch for " + want[i].model);
  });
  assert.equal(texts(cardOf(page, "Models"), "est")[0], "Estimated at API list price");
  assert.equal(texts(cardOf(page, "Models"), "est").length, 1, "no unpriced note when every model has a price");
  const tokens = cardOf(page, "Tokens by model");
  assert.deepEqual(texts(tokens, "sb-n"), want.map((r) => r.display_name), "Tokens by model follows the same order");
  assert.equal(byClass(tokens, "klg").length, 1);
  assert.equal(byClass(page, "foot").length, 1);
});

test("models Driftwood: the unpriced model draws hatched, shows Not priced with no share, and carries its note", async () => {
  const app = await boot({ hash: "#/models?project=" + keyOf("Driftwood") });
  const page = app.section("models");
  const table = modelsTable(page);
  const rows = bodyRows(table);
  const last = rows[rows.length - 1];
  assert.equal(texts(last, "mono")[0], "claude-opus-6-preview", "a model with no cost comes last");
  assert.ok(hasClass(byClass(last, "swatch")[0], "cat-other"));
  assert.equal(flat(cellsOf(last)[3]), "Not priced");
  assert.equal(byClass(last, "share").length, 0);
  assert.deepEqual(texts(cardOf(page, "Models"), "est"), [
    "Estimated at API list price",
    "The dashboard has no list price for claude-opus-6-preview, so totals leave it out.",
  ]);
});

test("models: a range switch keeps one /api/usage request and redraws the view", async () => {
  const app = await boot({ hash: "#/models" });
  assert.equal(app.count("/api/usage"), 1);
  const before = app.calls.length;
  await app.go("#/models?range=today");
  assert.ok(visible(app).includes("models"));
  assert.equal(modelsTable(app.section("models")).find((n) => n.tagName === "tbody").length, 1);
  await app.go("#/models?range=7d");
  await app.go("#/models?range=30d");
  assert.equal(app.count("/api/usage"), 1);
  assert.equal(app.calls.length, before, "a range switch fetches nothing");
});

test("est line: the title says what estimated means and when the prices were checked, on Overview and Models", async () => {
  for (const name of ["overview", "models"]) {
    const app = await boot({ hash: "#/" + name });
    const lines = byClass(app.section(name), "est").filter((n) => flat(n) === "Estimated at API list price");
    assert.ok(lines.length > 0, name + " has an est line");
    for (const line of lines) {
      const title = line.getAttribute("title");
      assert.ok(title.startsWith(STRINGS.est_tip + " "), name + " title starts with the tip");
      assert.ok(title.endsWith(" Prices checked on October 30"), name + " title: " + title);
    }
  }
});

test("estLine: the title is the tip alone when the price list has no date", async () => {
  createPage();
  const format = await import(JS + "format.js");
  format.setStrings(STRINGS);
  const { estLine } = await import(JS + "components.js");
  assert.equal(estLine(null).getAttribute("title"), STRINGS.est_tip);
  assert.equal(estLine().getAttribute("title"), STRINGS.est_tip);
  assert.equal(estLine("2026-10-30").getAttribute("title"), STRINGS.est_tip + " Prices checked on October 30");
});

// ---------------------------------------------------------------- sessions and session detail

const tagOf = (root, name) => root.find((n) => n.tagName === name);
const sessionsTable = (page) => byClass(cardOf(page, "Sessions"), "dt")[0];
const sessionHref = (id) => "#/sessions/" + encodeURIComponent(id);
const PLANT = "<script>alert(1)</script>";

// Answers /api/usage with a copy of the demo payload that fix(body, key) has changed. Every other path
// uses the demo data.
const patchedUsage = (fix) => (pathname, params) => {
  if (pathname !== "/api/usage") return null;
  const key = params.get("project");
  const body = structuredClone(usageOf(key));
  fix(body, key);
  return [200, body];
};

async function fmtTimeOf() {
  const format = await import(JS + "format.js");
  return format.fmtTime;
}

test("sessions: six columns, the newest ten in the server's order, and the cells of each row", async () => {
  const app = await boot({ hash: "#/sessions" });
  const page = app.section("sessions");
  const fmtTime = await fmtTimeOf();
  const list = viewOf(TIDEWATER, "30d").sessions;
  assert.ok(list.length > 10);
  assert.deepEqual(headers(sessionsTable(page)), ["Started", "Session", "Branch", "Agent runs", "Tokens", "Estimated cost"]);
  const rows = bodyRows(sessionsTable(page));
  assert.equal(rows.length, 10);
  const starts = list.map((s) => Date.parse(s.started));
  assert.deepEqual(starts, [...starts].sort((a, b) => b - a), "newest first");
  rows.forEach((row, i) => {
    const s = list[i];
    const cells = cellsOf(row);
    assert.equal(flat(cells[0]), fmtTime(s.started));
    assert.equal(flat(cells[1]), "Session from " + fmtTime(s.started));
    assert.ok(hrefOf(cells[1]).startsWith(sessionHref(s.session_id)), hrefOf(cells[1]));
    assert.equal(flat(cells[2]), s.branch);
    assert.ok(hasClass(byClass(cells[2], "mono")[0], "mono"));
    assert.equal(flat(cells[3]), s.agents.length ? s.runs + " " + s.agents.join(", ") : "none");
    assert.equal(byClass(cells[3], "muted").length, 1);
  });
  assert.equal(texts(page, "at-more").length, 1);
  assert.equal(texts(cardOf(page, "Sessions"), "est").length, 1);
  assert.equal(byClass(page, "foot").length, 1);
});

test("sessions Driftwood: a session with no agent runs shows none, and nine rows have no more line", async () => {
  const app = await boot({ hash: "#/sessions?project=" + keyOf("Driftwood") });
  const page = app.section("sessions");
  const list = viewOf(keyOf("Driftwood"), "30d").sessions;
  const rows = bodyRows(sessionsTable(page));
  assert.equal(rows.length, list.length);
  const quiet = list.findIndex((s) => s.agents.length === 0);
  assert.ok(quiet >= 0, "the demo has a session with no agent runs");
  assert.equal(flat(cellsOf(rows[quiet])[3]), "none");
  assert.ok(hasClass(byClass(cellsOf(rows[quiet])[3], "muted")[0], "muted"));
  assert.equal(byClass(page, "at-more").length, 0);
});

test("sessions All projects: Project follows Session and shows each session's project", async () => {
  const app = await boot({ hash: "#/sessions?project=all" });
  const page = app.section("sessions");
  assert.deepEqual(headers(sessionsTable(page)), ["Started", "Session", "Project", "Branch", "Agent runs", "Tokens", "Estimated cost"]);
  const list = viewOf("all", "30d").sessions;
  assert.deepEqual(bodyRows(sessionsTable(page)).map((r) => flat(cellsOf(r)[2])), list.slice(0, 10).map((s) => s.project));
});

test("sessions: the more line counts the hidden sessions and Show all names the total", async () => {
  const app = await boot({ hash: "#/sessions" });
  const total = viewOf(TIDEWATER, "30d").sessions.length;
  const more = byClass(app.section("sessions"), "at-more")[0];
  assert.equal(flat(more), (total - 10) + " more sessions in this range Show all " + total + " sessions");
  assert.equal(tagOf(more, "button").length, 1);
  assert.ok(hasClass(tagOf(more, "button")[0], "btn"));
  const one = await boot({
    hash: "#/sessions",
    respond: patchedUsage((body) => { body.views["30d"].sessions = body.views["30d"].sessions.slice(0, 11); }),
  });
  assert.equal(flat(byClass(one.section("sessions"), "at-more")[0]), "1 more session in this range Show all 11 sessions");
});

test("sessions: a start across local midnight keeps its first main row, and a missing branch reads no branch", async () => {
  const early = "2026-10-29T23:50:00-04:00";
  const app = await boot({
    hash: "#/sessions",
    respond: patchedUsage((body) => {
      const s = body.views["30d"].sessions[0];
      s.started = early;
      s.branch = null;
    }),
  });
  const fmtTime = await fmtTimeOf();
  const first = cellsOf(bodyRows(sessionsTable(app.section("sessions")))[0]);
  assert.equal(flat(first[0]), fmtTime(early));
  assert.equal(flat(first[1]), "Session from " + fmtTime(early));
  assert.equal(flat(first[2]), "no branch");
  assert.ok(hasClass(byClass(first[2], "muted")[0], "muted"));
  assert.equal(byClass(first[2], "mono").length, 0);
});

test("sessions: the demo's started and branch come from the session, and Tidewater carries one branch", async () => {
  const list = viewOf(TIDEWATER, "30d").sessions;
  assert.ok(list.every((s) => s.branch === "feature/quarter-close"));
  assert.ok(list.every((s) => typeof s.started === "string" && !Number.isNaN(Date.parse(s.started))));
});

test("sessions: a branch and an agent name that look like a script render as text and plant no script", async () => {
  const fix = patchedUsage((body) => {
    const s = body.views["30d"].sessions[0];
    s.branch = PLANT;
    s.agents = [PLANT];
    s.by_agent[0].agent = PLANT;
  });
  const app = await boot({ hash: "#/sessions", respond: fix });
  const page = app.section("sessions");
  const first = cellsOf(bodyRows(sessionsTable(page))[0]);
  assert.ok(flat(first[2]).includes(PLANT));
  assert.ok(flat(first[3]).includes(PLANT));
  const planted = Object.values(app.sections).flatMap((el) => tagOf(el, "script"));
  assert.equal(planted.length, 0, "no script element on any page");

  const sid = viewOf(TIDEWATER, "30d").sessions[0].session_id;
  const detail = await boot({ hash: "#/sessions/" + encodeURIComponent(sid), respond: fix });
  const dpage = detail.section("session-detail");
  assert.ok(flat(byClass(dpage, "intro")[0]).includes(PLANT));
  assert.ok(flat(cardOf(dpage, "Agents in this session")).includes(PLANT));
  assert.ok(flat(cardOf(dpage, "Tokens by agent")).includes(PLANT));
  assert.equal(Object.values(detail.sections).flatMap((el) => tagOf(el, "script")).length, 0);
});

test("session detail: the real head, four tiles with no deltas, and both cards", async () => {
  const s = viewOf(TIDEWATER, "30d").sessions[0];
  const app = await boot({ hash: "#/sessions/" + encodeURIComponent(s.session_id) });
  const page = app.section("session-detail");
  const fmtTime = await fmtTimeOf();
  assert.equal(flat(tagOf(page, "h1")[0]), "Session from " + fmtTime(s.started));
  assert.equal(tagOf(page, "h1").length, 1, "the id head is replaced, not kept beside it");
  assert.equal(flat(byClass(page, "intro")[0]), "On " + s.branch + " in Tidewater reporting.");
  assert.equal(byClass(page, "segs-range").length, 0, "no range control");
  assert.equal(hrefOf(byClass(page, "crumbs")[0]).startsWith("#/sessions"), true);
  assert.deepEqual(texts(page, "tl-l"), ["Tokens", "Estimated cost", "Cache hit rate", "Agent runs"]);
  assert.equal(byClass(page, "delta").length, 0);
  const tiles = byClass(page, "kpi");
  assert.equal(flat(byClass(tiles[3], "kpi-v")[0]), String(s.runs));
  assert.deepEqual(texts(tiles[1], "est"), ["Estimated at API list price"]);
  assert.deepEqual(texts(tiles[2], "kpi-def"), ["Share of prompt tokens read from cache"]);
  assert.equal(byClass(page, "g2").length, 1);
  const agents = cardOf(page, "Agents in this session");
  assert.deepEqual(headers(byClass(agents, "dt")[0]), ["Agent", "Runs", "Tokens", "Estimated cost", "Cache hit rate"]);
  assert.equal(texts(agents, "est").length, 1);
  const tokens = cardOf(page, "Tokens by agent");
  assert.equal(byClass(tokens, "sb-row").length, s.by_agent.length);
  assert.equal(byClass(tokens, "klg").length, 1);
  assert.equal(byClass(page, "foot").length, 1);
});

test("session detail: every agent row links to its route in the server's order, Main to @main with one run", async () => {
  const s = viewOf(TIDEWATER, "30d").sessions[0];
  const app = await boot({
    hash: "#/sessions/" + encodeURIComponent(s.session_id),
    respond: patchedUsage((body) => {
      const row = body.views["30d"].sessions[0];
      row.by_agent.push({ ...row.by_agent[0], agent: "@unnamed", runs: 3 });
    }),
  });
  const table = byClass(cardOf(app.section("session-detail"), "Agents in this session"), "dt")[0];
  const rows = bodyRows(table);
  const want = [...s.by_agent.map((r) => r.agent), "@unnamed"];
  assert.equal(rows.length, want.length);
  rows.forEach((row, i) => {
    const key = want[i] === null ? "@main" : want[i];
    assert.equal(hrefOf(cellsOf(row)[0]).split("?")[0], "#/agents/" + (key === "@main" ? key : encodeURIComponent(key)));
    const shown = want[i] === null ? "Main session" : want[i] === "@unnamed" ? "Unnamed agent" : want[i];
    assert.equal(flat(cellsOf(row)[0]), shown);
    if (want[i] === null) assert.equal(flat(cellsOf(row)[1]), "1");
    if (want[i] === "@unnamed") assert.equal(flat(cellsOf(row)[1]), "3");
  });
});

test("session detail: no branch gives the no-branch intro, and an unknown id gives the empty state", async () => {
  const s = viewOf(TIDEWATER, "30d").sessions[0];
  const app = await boot({
    hash: "#/sessions/" + encodeURIComponent(s.session_id),
    respond: patchedUsage((body) => { body.views["30d"].sessions[0].branch = null; }),
  });
  assert.equal(flat(byClass(app.section("session-detail"), "intro")[0]), "In Tidewater reporting.");

  const gone = await boot({ hash: "#/sessions/no-such-session" });
  const page = gone.section("session-detail");
  assert.equal(flat(tagOf(page, "h1")[0]), "no-such-session");
  assert.deepEqual(texts(page, "cd-h"), ["No usage in this range"]);
  assert.ok(flat(page).includes("No session ran during the last 30 days."));
  assert.equal(byClass(page, "kpi").length, 0);
  assert.equal(byClass(page, "foot").length, 1);
});

test("session detail: it finds the session from the 30 day view whatever range the address holds", async () => {
  const s = viewOf(TIDEWATER, "30d").sessions[viewOf(TIDEWATER, "7d").sessions.length + 2];
  assert.ok(!viewOf(TIDEWATER, "7d").sessions.some((x) => x.session_id === s.session_id));
  const app = await boot({ hash: "#/sessions/" + encodeURIComponent(s.session_id) + "?range=7d" });
  assert.equal(byClass(app.section("session-detail"), "kpi").length, 4);
  assert.equal(app.count("/api/usage"), 1);
});

test("agent detail: a Recent runs link opens the session detail for that same session", async () => {
  const app = await boot({ hash: "#/agents/builder" });
  const fmtTime = await fmtTimeOf();
  const row = bodyRows(byClass(cardOf(app.section("agent-detail"), "Recent runs"), "dt")[0])[0];
  const run = viewOf(TIDEWATER, "30d").by_agent.find((a) => a.route_key === "builder").recent_runs[0];
  await app.go(hrefOf(cellsOf(row)[1]));
  assert.deepEqual(visible(app), ["session-detail"]);
  const page = app.section("session-detail");
  const s = viewOf(TIDEWATER, "30d").sessions.find((x) => x.session_id === run.session_id);
  assert.equal(flat(tagOf(page, "h1")[0]), "Session from " + fmtTime(s.started));
  assert.equal(fmtTime(run.session_started), fmtTime(s.started));
  assert.equal(app.count("/api/usage"), 1);
});

// This one goes last of the sessions checks: the expanded state lives in the module, as it does in a tab.
test("sessions: Show all expands from the payload, keeps focus, and holds only for the same project and range", async () => {
  const app = await boot({ hash: "#/sessions" });
  const total = viewOf(TIDEWATER, "30d").sessions.length;
  const page = () => app.section("sessions");
  assert.equal(bodyRows(sessionsTable(page())).length, 10);
  const before = app.calls.length;
  tagOf(byClass(page(), "at-more")[0], "button")[0].click();
  assert.equal(bodyRows(sessionsTable(page())).length, total);
  assert.equal(byClass(page(), "at-more").length, 0, "the more line goes with the button");
  assert.equal(app.calls.length, before, "no new request");
  assert.equal(app.count("/api/usage"), 1);
  const eleventh = tagOf(bodyRows(sessionsTable(page()))[10], "a")[0];
  assert.equal(app.doc.activeElement, eleventh, "focus lands on the link in row 11");

  await app.go("#/overview");
  await app.go("#/sessions");
  assert.equal(bodyRows(sessionsTable(page())).length, total, "a redraw of the same view stays expanded");

  await app.go("#/sessions?range=7d");
  const week = viewOf(TIDEWATER, "7d").sessions.length;
  assert.ok(week > 10);
  assert.equal(bodyRows(sessionsTable(page())).length, 10, "another range starts short");
  assert.equal(byClass(page(), "at-more").length, 1);

  await app.go("#/sessions?range=30d&project=all");
  assert.equal(bodyRows(sessionsTable(page())).length, 10, "another project starts short");
  assert.equal(app.count("/api/usage"), 2, "one request per project");
});

// ---------------------------------------------------------------- all projects

const allView = (range = "30d") => viewOf("all", range);
const byTokens = (view) => [...view.by_project].sort((a, b) => b.tokens - a.tokens);
const selectOf = (app) => app.topbar.find((n) => n.tagName === "select")[0];
const projectsTable = (page) => byClass(cardOf(page, "Projects"), "dt")[0];
const rowNamed = (page, name) => bodyRows(projectsTable(page)).find((r) => flat(cellsOf(r)[0]).startsWith(name));
const starNotes = (page) => byClass(cardOf(page, "Projects"), "est").filter((n) => flat(n).startsWith("*")).map(flat);

test("all projects: Tokens by project and the Projects table show every folder in token order", async () => {
  const app = await boot({ hash: "#/overview?project=all" });
  const page = app.section("all-projects");
  assert.deepEqual(visible(app), ["all-projects"]);
  const want = byTokens(allView());
  assert.ok(want.length >= 4 && want.some((r) => !r.listed), "the demo has an unlisted folder");
  const stacked = cardOf(page, "Tokens by project");
  assert.deepEqual(texts(stacked, "sb-n"), want.map((r) => r.name));
  assert.equal(byClass(stacked, "klg").length, 1, "the kinds legend sits under the bars");
  const table = projectsTable(page);
  assert.deepEqual(headers(table), ["Project", "Sessions", "Agent runs", "Tokens", "Estimated cost", "Cache hit rate"]);
  assert.deepEqual(bodyRows(table).map((r) => flat(cellsOf(r)[0]).replace(/Not on the list$/, "")), want.map((r) => r.name));
  bodyRows(table).forEach((row, i) => {
    assert.equal(flat(cellsOf(row)[1]), want[i].sessions.toLocaleString("en-US"));
    assert.equal(flat(cellsOf(row)[2]), want[i].runs.toLocaleString("en-US"));
  });
  assert.equal(texts(page, "intro")[0], "Usage across every project folder, listed or not, over the last 30 days.");
  assert.equal(byClass(page, "foot").length, 1);
  assert.equal(texts(cardOf(page, "Projects"), "est").pop(), "Estimated at API list price", "the est line closes the card");
});

test("all projects: a listed row links to that project and keeps the range, never project=all", async () => {
  const app = await boot({ hash: "#/overview?project=all&range=7d" });
  const page = app.section("all-projects");
  const listed = allView("7d").by_project.filter((r) => r.listed);
  assert.ok(listed.length >= 3);
  for (const row of listed) {
    const cell = cellsOf(rowNamed(page, row.name))[0];
    const href = hrefOf(cell);
    assert.ok(href.startsWith("#/overview?"), href);
    const query = new URLSearchParams(href.slice(href.indexOf("?") + 1));
    assert.equal(query.get("project"), row.key, "the link opens " + row.name);
    assert.equal(query.get("range"), "7d", "the range stays");
    assert.ok(!href.includes("project=all"), href);
    assert.ok(hasClass(tagged(cell, "a")[0], "lnk"));
  }
  await app.go(hrefOf(cellsOf(rowNamed(page, "Driftwood"))[0]));
  assert.deepEqual(visible(app), ["overview"], "the link opens that project's overview");
  assert.equal(selectOf(app).value, keyOf("Driftwood"));
});

test("all projects: an unlisted folder is plain text with the Not on the list note and stays out of the switcher", async () => {
  const app = await boot({ hash: "#/overview?project=all" });
  const page = app.section("all-projects");
  const view = allView();
  const unlisted = view.by_project.filter((r) => !r.listed);
  assert.ok(unlisted.length >= 1);
  const options = selectOf(app).find((n) => n.tagName === "option").map(flat);
  for (const row of unlisted) {
    const first = cellsOf(rowNamed(page, row.name))[0];
    assert.equal(tagged(first, "a").length, 0, "no link");
    assert.deepEqual(texts(first, "cell-note"), ["Not on the list"]);
    assert.equal(flat(first), row.name + "Not on the list");
    assert.ok(!options.some((o) => o.includes(row.name)), "no option names " + row.name);
  }
  const listed = DATA["/api/projects"].body.projects.map((p) => p.name);
  assert.equal(options.length, listed.length + 1, "the listed projects, then All projects");
  listed.forEach((name, i) => assert.ok(options[i].startsWith(name), options[i] + " is " + name));
  assert.equal(options[options.length - 1], "All projects");
  const noted = bodyRows(projectsTable(page)).filter((r) => byClass(r, "cell-note").length > 0);
  assert.equal(noted.length, unlisted.length, "only unlisted rows carry the note");
});

test("all projects: Driftwood's row has the star, one note names its 150 requests, and the cost tile says one model is left out", async () => {
  const app = await boot({ hash: "#/overview?project=all" });
  const page = app.section("all-projects");
  const drift = allView().by_project.find((r) => r.name === "Driftwood");
  assert.equal(drift.unpriced_requests, 150);
  for (const row of bodyRows(projectsTable(page))) {
    const marks = byClass(cellsOf(row)[4], "fn");
    assert.equal(marks.length, flat(cellsOf(row)[0]) === "Driftwood" ? 1 : 0, "the star on " + flat(cellsOf(row)[0]));
  }
  const cost = cellsOf(rowNamed(page, "Driftwood"))[4];
  const mark = byClass(cost, "fn")[0];
  assert.equal(mark.tagName, "sup");
  assert.equal(mark.getAttribute("aria-hidden"), "true");
  assert.equal(flat(mark), "*");
  assert.equal(byClass(cost, "cw").length, 1);
  assert.deepEqual(starNotes(page), ["* The cost for Driftwood leaves out 150 requests with no list price."]);
  const note = byClass(cardOf(page, "Projects"), "est").find((n) => flat(n).startsWith("*"));
  assert.equal(tagged(note, "span")[0].getAttribute("aria-hidden"), "true");
  assert.deepEqual(texts(byClass(page, "kpi")[1], "est"), [
    "Estimated at API list price",
    "The dashboard has no list price for one model here, so the total leaves it out.",
  ]);
});

test("all projects: a row with one unpriced request uses the one-request sentence", async () => {
  const respond = patchedUsage((body, key) => {
    if (key !== "all") return;
    const rows = body.views["30d"].by_project;
    rows.find((r) => r.name === "Tidewater reporting").unpriced_requests = 1;
    rows.find((r) => r.name === "Driftwood").unpriced_requests = 0;
  });
  const app = await boot({ hash: "#/overview?project=all", respond });
  const page = app.section("all-projects");
  assert.deepEqual(starNotes(page), ["* The cost for Tidewater reporting leaves out 1 request with no list price."]);
  assert.equal(byClass(cellsOf(rowNamed(page, "Tidewater reporting"))[4], "fn").length, 1);
  assert.equal(byClass(cellsOf(rowNamed(page, "Driftwood"))[4], "fn").length, 0);
});

test("all projects: the sidebar says All projects with Overview active, and a project says This project", async () => {
  const app = await boot({ hash: "#/overview?project=all" });
  assert.deepEqual(texts(app.sidebar, "sb-g"), ["All projects", "Reference"]);
  const active = byClass(app.sidebar, "is-active");
  assert.equal(active.length, 1);
  assert.equal(flat(active[0]), "Overview");
  assert.equal(active[0].getAttribute("aria-current"), "page");
  assert.equal(selectOf(app).value, "all");

  await app.go("#/overview?project=" + TIDEWATER);
  assert.equal(texts(app.sidebar, "sb-g")[0], "This project");
  assert.equal(flat(byClass(app.sidebar, "is-active")[0]), "Overview");
});

test("all projects: a range switch keeps one /api/usage request and redraws the view", async () => {
  const app = await boot({ hash: "#/overview?project=all" });
  assert.equal(app.count("/api/usage"), 1);
  const before = app.calls.length;
  const bars = () => texts(cardOf(app.section("all-projects"), "Tokens by project"), "sb-n");
  await app.go("#/overview?project=all&range=today");
  assert.deepEqual(visible(app), ["all-projects"]);
  assert.equal(texts(app.section("all-projects"), "intro")[0], "Usage across every project folder, listed or not, today.");
  assert.deepEqual(bars(), byTokens(allView("today")).map((r) => r.name));
  await app.go("#/overview?project=all&range=7d");
  assert.deepEqual(bars(), byTokens(allView("7d")).map((r) => r.name));
  await app.go("#/overview?project=all&range=30d");
  assert.deepEqual(bars(), byTokens(allView("30d")).map((r) => r.name));
  assert.equal(app.count("/api/usage"), 1);
  assert.equal(app.calls.length, before, "a range switch fetches nothing");
});

// ---------------------------------------------------------------- unknown pins never print null

const NULLISH = /\bnull\b|\bundefined\b/;
const withPin = (s, pinned) => ({ ...s, pinned: { ...s.pinned, ...pinned } });
// The words a pinView holds. A field that is null on purpose is not a word, so only strings are read.
const noNull = (view, what) => {
  const words = Object.values(view).flat().filter((v) => typeof v === "string");
  assert.ok(words.every((w) => !NULLISH.test(w)), what + " " + JSON.stringify(words));
};

test("pinView: a pin the dashboard can't name says so and never prints null", async () => {
  createPage();
  const format = await import(JS + "format.js");
  format.setStrings(STRINGS);
  const { pinView } = await import(JS + "pin-view.js");
  const UNKNOWN = "The dashboard can't tell what this agent is pinned to.";
  const noModel = (state = "matches", extra = {}) => withPin(setting(state, { pv: FABLE, ...extra }), { value: null, id: null });
  const noEffort = (state = "matches", extra = {}) => withPin(setting(state, extra), { value: null, id: null });

  const both = pinView(U, agentOf("both", "matches", noModel(), noEffort(), { source: "settings" }));
  assert.equal(both.pinnedText, UNKNOWN);
  assert.equal(both.detailPinned, UNKNOWN);
  noNull(both, "both unset");

  const modelUnset = pinView(U, agentOf("both", "matches", noModel(), setting("matches", { pv: "high" }), { source: "settings" }));
  assert.equal(modelUnset.pinnedText, UNKNOWN, "model unset alone");
  assert.equal(modelUnset.detailPinned, UNKNOWN);
  noNull(modelUnset, "model unset alone");

  const effortUnset = pinView(U, agentOf("both", "matches", setting("matches", { pv: FABLE, e: { key: "model", value: FABLE } }), noEffort()));
  assert.equal(effortUnset.pinnedText, "Fable 5.1, Unknown");
  assert.equal(effortUnset.detailPinned, "Pinned to Fable 5.1 at Unknown.");
  noNull(effortUnset, "effort unset");

  const modelOnly = pinView(U, agentOf("model_only", "matches", noModel(), null));
  assert.equal(modelOnly.pinnedText, UNKNOWN);
  assert.equal(modelOnly.detailPinned, UNKNOWN);
  noNull(modelOnly, "model_only unset");

  const effortOnly = pinView(U, agentOf("effort_only", "matches", null, noEffort()));
  assert.equal(effortOnly.pinnedText, "Unknown, model not pinned");
  assert.equal(effortOnly.detailPinned, "Unknown, model not pinned");
  noNull(effortOnly, "effort_only unset");

  const mainNone = pinView(U, agentOf("none", null, null, null, { source: "settings" }));
  assert.equal(mainNone.pinnedText, UNKNOWN);
  assert.equal(mainNone.detailPinned, UNKNOWN);
  const fileNone = pinView(U, agentOf("none", null, null, null));
  assert.equal(fileNone.detailPinned, null, "an agent file with no pin keeps its own words");

  // The differs sentence is never filled with a null pin_model.
  const unknownPin = withPin(setting("differs", { pv: FABLE, ran: [SONNET], e: { key: "model", value: FABLE } }), { value: null, id: null });
  const differs = pinView(U, agentOf("model_only", "differs", unknownPin, null));
  assert.deepEqual(differs.sentences, []);
  noNull(differs, "differs with an unknown pin");
  const known = pinView(U, agentOf("model_only", "differs", setting("differs", { pv: FABLE, ran: [SONNET], e: { key: "model", value: FABLE } }), null));
  assert.equal(known.sentences.length, 1, "a known pin still gets its sentence");

  // A cap or a pin with no model or value falls back to the word Unknown, not null.
  const lowered = { value: "max", status: "lowered", becomes: "high", key: "effortLevel", layer: "user", file: "~/.claude/settings.json", line: 2, rule_id: "x-lowered-by-cap" };
  const cap = { key: "maxEffortLevel", value: "high", model: null, file: null, line: null };
  const capped = pinView(U, agentOf("effort_only", "matches", null, setting("matches", { rmp: true, e: lowered, cap })));
  noNull(capped, "a cap with no model");
  const unsupportedEntry = { ...lowered, rule_id: "x-unsupported-level", model: null };
  const unsupported = pinView(U, agentOf("effort_only", "matches", null, withPin(setting("matches", { rmp: true, e: unsupportedEntry }), { value: null })));
  noNull(unsupported, "an unsupported level with no pin value");
});

// The demo copy without model or effortLevel in its settings (tests/test_pages_js.py saves its answers under
// "nomodel " plus the path).
const NOMODEL = (path) => DATA["nomodel " + path];
const nomodelRespond = (pathname, params) => {
  const query = params.toString();
  const saved = NOMODEL(pathname + (query ? "?" + query : ""));
  return saved ? [saved.status, saved.body] : null;
};

test("agents pages on a project that sets neither model nor effortLevel: the word null appears nowhere", async () => {
  const usage = NOMODEL("/api/usage?project=harbor-light");
  assert.ok(usage, "the saved answers hold the copy");
  const main = usage.body.views["30d"].by_agent.find((a) => a.route_key === "@main");
  assert.equal(main.pin.model.pinned.id, null, "the copy really has an unknown model pin");
  assert.equal(main.pin.effort.pinned.value, null, "and an unknown effort pin");
  for (const [hash, section] of [["#/agents?project=harbor-light", "agents"], ["#/agents/@main?project=harbor-light", "agent-detail"]]) {
    const app = await boot({ hash, respond: nomodelRespond });
    const page = app.section(section);
    assert.ok(byClass(page, "dt").length + byClass(page, "pin").length > 0, hash + " drew its body");
    assert.ok(!NULLISH.test(flat(page)), hash + " shows " + flat(page).match(/.{0,40}\b(null|undefined)\b.{0,40}/));
    assert.ok(flat(page).includes("The dashboard can't tell what this agent is pinned to."), hash);
  }
});

// ---------------------------------------------------------------- a project whose folder is gone, usage kept

const GONE = () => DATA["/api/projects"].body.projects.find((p) => p.name === "Lantern");
const fillSlots = (key, slots) => STRINGS[key].replace(/\{(\w+)\}/g, (whole, name) => (name in slots ? slots[name] : whole));
const keptNote = () => fillSlots("es_missing_usage_t", {
  path: GONE().path_display, name: "Lantern", config_file: DATA["/api/projects"].body.config_file_display,
});
// Lantern's /api/usage answered with another project's views, as a server does for a missing folder that
// still has saved transcripts. fix(body) may change the copy.
const keptUsage = (fix = () => {}) => (pathname, params) => {
  if (pathname !== "/api/usage" || params.get("project") !== GONE().key) return null;
  const body = structuredClone(usageOf(TIDEWATER));
  body.no_usage = false;
  fix(body);
  return [200, body];
};
const notes = (page) => byClass(page, "nt").filter((n) => !hasClass(n, "nt-empty"));
const kids = (page) => page.childNodes.filter((n) => n.tagName);
const indexOfNode = (page, node) => kids(page).findIndex((k) => k === node || k.contains(node));
const folderNotFound = (page) => byClass(page, "nt-empty").length === 1 && texts(page, "nt-h").join() === "Folder not found";

function assertNote(page, where) {
  const found = notes(page);
  assert.equal(found.length, 1, where + ": one note");
  assert.equal(found[0].tagName, "section");
  assert.equal(found[0].getAttribute("aria-label"), "Folder not found");
  assert.deepEqual(texts(found[0], "nt-t"), [keptNote()], where);
  assert.equal(byClass(page, "nt-empty").length, 0, where + ": not the Folder not found state");
  return found[0];
}

test("folder gone, usage kept: Overview shows the note above the tiles", async () => {
  const app = await boot({ hash: "#/overview?project=" + GONE().key, respond: keptUsage() });
  const page = app.section("overview");
  const note = assertNote(page, "overview");
  assert.equal(byClass(page, "kpi").length, 4);
  assert.ok(indexOfNode(page, note) < indexOfNode(page, byClass(page, "kpis")[0]), "the note sits above the tiles");
  assert.ok(indexOfNode(page, byClass(page, "ph")[0]) < indexOfNode(page, note), "and below the head");
  assert.equal(byClass(page, "foot").length, 1);
});

test("folder gone, usage kept: Agents shows the note, the table and the pin cells", async () => {
  const app = await boot({ hash: "#/agents?project=" + GONE().key, respond: keptUsage() });
  const page = app.section("agents");
  const note = assertNote(page, "agents");
  assert.equal(byClass(page, "dt").length > 0, true);
  assert.ok(indexOfNode(page, note) < indexOfNode(page, byClass(page, "g2")[0]));
  assert.ok(!NULLISH.test(flat(page)), "no null on screen");
});

test("folder gone, usage kept: session detail keeps the note under the real head", async () => {
  const app = await boot({ hash: "#/sessions/" + encodeURIComponent(SESSION) + "?project=" + GONE().key, respond: keptUsage() });
  const page = app.section("session-detail");
  const note = assertNote(page, "session detail");
  const s = viewOf(TIDEWATER, "30d").sessions.find((x) => x.session_id === SESSION);
  const fmtTime = await fmtTimeOf();
  assert.equal(page.find((n) => n.tagName === "h1").length, 1);
  assert.equal(flat(page.find((n) => n.tagName === "h1")[0]), "Session from " + fmtTime(s.started));
  const order = kids(page);
  assert.ok(hasClass(order[0], "ph"), "the head comes first");
  assert.equal(order[1], note, "the note is right under the head");
  assert.equal(byClass(page, "kpi").length, 4);
  assert.ok(indexOfNode(page, note) < indexOfNode(page, byClass(page, "kpis")[0]));
});

test("folder gone, usage kept: the note also sits above the no-range card", async () => {
  const fix = (body) => { body.views["30d"].totals.requests = 0; };
  const app = await boot({ hash: "#/overview?project=" + GONE().key, respond: keptUsage(fix) });
  const page = app.section("overview");
  const note = assertNote(page, "no-range");
  assert.deepEqual(texts(page, "es-h"), ["No usage in this range"]);
  assert.ok(indexOfNode(page, note) < indexOfNode(page, byClass(page, "es-h")[0]));
});

test("folder gone: a pending payload shows Folder not found, then the answer swaps it for the note and the tiles", async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const kept = keptUsage();
  const app = await boot({
    hash: "#/overview?project=" + GONE().key,
    usage: false,
    respond: async (pathname, params, n) => {
      if (pathname === "/api/usage") await gate;
      return kept(pathname, params, n);
    },
  });
  assert.ok(folderNotFound(app.section("overview")), "while the payload is pending");
  assert.equal(byClass(app.section("overview"), "kpi").length, 0);
  release();
  await until(() => app.root.getAttribute("data-usage") === "1", "data-usage");
  assertNote(app.section("overview"), "after the answer");
  assert.equal(byClass(app.section("overview"), "kpi").length, 4);
});

test("folder gone: a failed payload, no_usage and an unreadable transcripts folder all stay Folder not found", async () => {
  const failed = await boot({
    hash: "#/overview?project=" + GONE().key,
    respond: (pathname, params) => (pathname === "/api/usage" && params.get("project") === GONE().key ? [500, { error: "boom" }] : null),
  });
  assert.ok(folderNotFound(failed.section("overview")), "failed payload");
  assert.equal(notes(failed.section("overview")).length, 0);

  const noUsage = await boot({ hash: "#/overview?project=" + GONE().key, respond: keptUsage((body) => { body.no_usage = true; }) });
  assert.ok(folderNotFound(noUsage.section("overview")), "no_usage true");
  assert.equal(byClass(noUsage.section("overview"), "kpi").length, 0);
  assert.equal(notes(noUsage.section("overview")).length, 0);

  const kept = keptUsage();
  const unreadable = await boot({
    hash: "#/overview?project=" + GONE().key,
    respond: (pathname, params, n) => projectsWith((b) => { b.reader.readable = false; })(pathname, params, n) || kept(pathname, params, n),
  });
  assert.ok(folderNotFound(unreadable.section("overview")), "unreadable folder");
  assert.deepEqual(texts(unreadable.section("overview"), "cd-h"), []);
});

// ---------------------------------------------------------------- the token axis reads whole

test("overview Today on Tidewater: the token axis labels hold no decimal point", async () => {
  const app = await boot({ hash: "#/overview?project=" + TIDEWATER + "&range=today" });
  const page = app.section("overview");
  const axis = byClass(page, "dy")[0];
  const labels = axis.childNodes.filter((n) => n.tagName === "span").map(flat);
  assert.ok(labels.length >= 3, "an axis with labels: " + labels.join());
  assert.equal(labels[labels.length - 1], "0");
  for (const label of labels) assert.ok(!label.includes("."), "axis label " + label);
  const format = await import(JS + "format.js");
  assert.equal(format.fmtTick(5e6), "5M");
  assert.equal(format.fmtTick(2e9), "2B");
  assert.equal(format.fmtTick(150000), "150K");
  assert.equal(format.fmtTick(1500000), "1.5M", "only a trailing .0 goes");
  assert.equal(format.fmtTokens(5e6), "5.0M", "bars, titles and totals keep fmtTokens");
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
console.log((tests.length - failed) + " of " + tests.length + " checks passed");process.exit(failed ? 1 : 0);

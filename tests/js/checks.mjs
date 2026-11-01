// Browser-free checks of the dashboard's scripts, run by tests/test_shell_js.py. They load the real modules
// from dashboard/static/js against the small fake DOM in fakedom.mjs and a fake fetch. Nothing here opens a
// browser or a socket. A failed check prints its name and the reason, and the exit code is 1.
import assert from "node:assert/strict";
import fs from "node:fs";
import { FElement, createPage } from "./fakedom.mjs";

const STATIC = new URL("../../dashboard/static/", import.meta.url);
const JS = new URL("js/", STATIC).href;
const STRINGS = JSON.parse(fs.readFileSync(new URL("strings.json", STATIC), "utf8"));

const tests = [];
const test = (name, fn) => tests.push([name, fn]);
const tick = (ms = 0) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(cond, what) {
  for (let i = 0; i < 200; i++) {
    if (cond()) return;
    await tick(5);
  }
  throw new Error("timed out waiting for " + what);
}

const PROJECTS = {
  projects: [
    { key: "storefront", name: "Storefront", path_display: "~/work/storefront", state: "ok" },
    { key: "docs", name: "Docs", path_display: "~/work/docs", state: "ok" },
  ],
  current: "storefront",
};

let runs = 0;

// Starts the app on a fresh page. respond(pathname, search, n) returns [status, body], or throws for a
// network error; n counts the calls to that pathname. Unanswered routes give a 404, as the server does
// for a route it does not have yet.
async function boot({ hash = "", respond = () => null, narrow = true } = {}) {
  const page = createPage({ narrow });
  page.win.location._hash = hash;
  const calls = [];
  const counts = new Map();
  globalThis.fetch = async (path) => {
    calls.push(path);
    const url = new URL(path, "http://127.0.0.1");
    const n = (counts.get(url.pathname) || 0) + 1;
    counts.set(url.pathname, n);
    let answer = respond(url.pathname, url.searchParams, n);
    if (!answer) {
      if (url.pathname === "/static/strings.json") answer = [200, STRINGS];
      else if (url.pathname === "/api/projects") answer = [200, PROJECTS];
      else if (url.pathname === "/api/settings") answer = [url.searchParams.get("project") === "all" ? 400 : 200, { rows: [] }];
      else answer = [404, { error: "not_found" }];
    }
    const [status, body] = answer;
    return { ok: status >= 200 && status < 300, status, json: async () => body };
  };
  runs += 1;
  await import(JS + "app.js?run=" + runs);
  await until(() => page.doc.documentElement.getAttribute("data-rendered") !== null, "boot");
  await tick(10);
  const count = (pathname) => calls.filter((c) => new URL(c, "http://127.0.0.1").pathname === pathname).length;
  const go = async (to) => { page.win.location.hash = to; await tick(20); };
  const menu = page.topbar.find((n) => n.tagName === "button")[0];
  const select = page.topbar.find((n) => n.tagName === "select")[0];
  const optionValues = () => select.find((n) => n.tagName === "option").map((o) => o.value);
  return { ...page, calls, count, go, menu, select, optionValues, root: page.doc.documentElement };
}

// ---------------------------------------------------------------- api.js

test("api: a network error and a 503 are not cached, a 404 is, a later 200 is", async () => {
  const { createApi } = await import(JS + "api.js");
  const answers = [
    { ok: false, status: 0, data: null },
    { ok: false, status: 503, data: null },
    { ok: true, status: 200, data: { v: 1 } },
  ];
  let n = 0;
  const api = createApi(async () => answers[n++]);
  for (let i = 0; i < 4; i++) {
    await api.rules();
    await tick();
  }
  assert.equal(n, 3, "two failures asked again, then the 200 kept");
  assert.equal((await api.rules()).status, 200);

  let k = 0;
  const notFound = createApi(async () => { k++; return { ok: false, status: 404, data: null }; });
  await notFound.files();
  await tick();
  await notFound.files();
  assert.equal(k, 1, "a 404 is kept");

  let m = 0;
  const refused = createApi(async () => { m++; return { ok: false, status: 400, data: null }; });
  await refused.settings("all");
  await tick();
  await refused.settings("all");
  assert.equal(m, 1, "a 400 is kept");
});

test("api: fetchJSON turns a thrown fetch into status 0 and a bad body into ok false", async () => {
  const { fetchJSON } = await import(JS + "api.js");
  globalThis.fetch = async () => { throw new TypeError("network"); };
  assert.deepEqual(await fetchJSON("/api/x"), { ok: false, status: 0, data: null });
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => { throw new SyntaxError("bad"); } });
  assert.deepEqual(await fetchJSON("/api/x"), { ok: false, status: 200, data: null });
});

// A response nobody reads never finishes, so the browser's resource timing leaves it out. That hid the 404
// on /api/usage from the end-to-end request count.
test("api: fetchJSON reads an error body, and a body that can't be read changes nothing", async () => {
  const { fetchJSON } = await import(JS + "api.js");
  for (const status of [400, 404, 503]) {
    let read = 0;
    globalThis.fetch = async () => ({ ok: false, status, text: async () => { read += 1; return "{}"; } });
    assert.deepEqual(await fetchJSON("/api/x"), { ok: false, status, data: null });
    assert.equal(read, 1, "status " + status);
  }
  globalThis.fetch = async () => ({ ok: false, status: 404, text: async () => { throw new TypeError("gone"); } });
  assert.deepEqual(await fetchJSON("/api/x"), { ok: false, status: 404, data: null });
});

// ---------------------------------------------------------------- h.js

test("h: SAFE_URL drops every off-site or control-character value and keeps local ones", async () => {
  createPage();
  const { h } = await import(JS + "h.js");
  const href = (value) => h("a", { href: value }).getAttribute("href");
  for (const ok of ["#", "#/x", "/", "/api/x"]) assert.equal(href(ok), ok, ok);
  const refused = ["/\t/evil.example/x", "/\n/evil.example/x", "/\r\\evil.example/x", "//evil", "/\\evil",
    "https://x", "javascript:x", " /x", "/x\n", "", "mailto:a@b", "x/y"];
  for (const bad of refused) assert.equal(href(bad), null, JSON.stringify(bad));
  const src = h("img", { src: "/\t/evil.example/x" });
  assert.equal(src.getAttribute("src"), null);
});

test("h: a link attribute name is compared in lower case, so HREF and Href get no off-site value", async () => {
  createPage();
  const { h } = await import(JS + "h.js");
  for (const name of ["HREF", "Href", "hReF", "SRC", "Action", "FormAction", "XLINK:HREF"]) {
    const el = h("a", { [name]: "javascript:x" });
    assert.equal(el.getAttribute(name), null, name);
    assert.equal(el.getAttribute(name.toLowerCase()), null, name);
  }
  assert.equal(h("a", { HREF: "/api/x" }).getAttribute("HREF"), "/api/x", "a local value is kept");
});

// ---------------------------------------------------------------- app.js

test("range control: focus stays on the checked radio after the page head is rebuilt", async () => {
  const app = await boot({ hash: "#/overview?project=storefront" });
  const group = () => app.sections.overview.find((n) => n.getAttribute("role") === "radiogroup")[0];
  const radios = () => group().find((n) => n.getAttribute("role") === "radio");
  radios().find((r) => r.getAttribute("aria-checked") === "true").focus();
  group().dispatch("keydown", { key: "ArrowLeft" });
  await tick(20);
  let now = FElement.focused;
  assert.equal(now.getAttribute("role"), "radio");
  assert.equal(now.getAttribute("aria-checked"), "true");
  assert.ok(radios().includes(now), "focus is on a radio of the rebuilt control");
  app.win.location.hash = "#/overview?project=storefront&range=today";
  await tick(20);
  now = FElement.focused;
  assert.equal(now.getAttribute("aria-checked"), "true");
  assert.ok(radios().includes(now));
});

const usageDown = (pathname, search) => (pathname === "/api/usage" ? [503, { error: "down" }] : null);

test("range change: fetches nothing", async () => {
  const app = await boot({ hash: "#/overview?project=storefront" });
  const before = app.calls.length;
  await app.go("#/overview?project=storefront&range=today");
  await app.go("#/overview?project=storefront&range=7d");
  await app.go("#/overview?project=storefront&range=30d&theme=dark");
  assert.equal(app.calls.length, before);
});

test("range change: fetches nothing after a failed project payload, and a route change asks again", async () => {
  const app = await boot({ hash: "#/overview?project=storefront", respond: usageDown });
  assert.equal(app.count("/api/usage"), 1);
  const before = app.calls.length;
  await app.go("#/overview?project=storefront&range=today");
  await app.go("#/overview?project=storefront&range=7d");
  assert.equal(app.calls.length, before, "a range switch retries nothing");
  await app.go("#/agents?project=storefront&range=7d");
  assert.equal(app.count("/api/usage"), 2, "the next route change asks for the payload again");
});

test("project change: a project picked again fetches nothing, 404 and 400 answers included", async () => {
  const app = await boot({ hash: "#/overview?project=storefront" });
  const asked = (key) => app.calls.filter((c) => c.endsWith("?project=" + key)).sort();
  for (const key of ["docs", "all", "docs"]) await app.go("#/overview?project=" + key);
  assert.deepEqual(asked("docs"), ["/api/settings?project=docs", "/api/usage?project=docs"]);
  assert.deepEqual(asked("all"), ["/api/settings?project=all", "/api/usage?project=all"]);
  assert.equal(app.count("/api/projects"), 1);
});

test("project change: asks again for a payload that failed", async () => {
  const app = await boot({ hash: "#/overview?project=storefront", respond: usageDown });
  await app.go("#/overview?project=docs");
  assert.equal(app.count("/api/usage"), 2, "docs was fetched once");
  await app.go("#/overview?project=storefront");
  assert.equal(app.count("/api/usage"), 3, "the failed storefront payload was asked for again");
});

test("retry: a failed /api/projects recovers on the next route change", async () => {
  const app = await boot({
    hash: "#/overview",
    respond: (pathname, search, n) => (pathname === "/api/projects" && n === 1 ? [503, {}] : null),
  });
  assert.equal(app.root.getAttribute("data-rendered"), "error");
  assert.deepEqual(app.optionValues(), ["all"]);
  await app.go("#/overview?range=today");
  assert.equal(app.count("/api/projects"), 1, "a range change does not retry");
  assert.equal(app.root.getAttribute("data-rendered"), "error");
  await app.go("#/agents?range=today");
  await until(() => app.root.getAttribute("data-rendered") === "1", "the retry");
  assert.equal(app.count("/api/projects"), 2);
  assert.deepEqual(app.optionValues(), ["storefront", "docs", "all"]);
  assert.equal(app.select.value, "storefront");
  await app.go("#/models");
  assert.equal(app.count("/api/projects"), 2, "a recovered load is kept");
});

test("retry: a network error on /api/projects recovers the same way", async () => {
  const app = await boot({
    hash: "#/overview",
    respond: (pathname, search, n) => {
      if (pathname === "/api/projects" && n === 1) throw new TypeError("network");
      return null;
    },
  });
  assert.equal(app.root.getAttribute("data-rendered"), "error");
  await app.go("#/sessions");
  await until(() => app.root.getAttribute("data-rendered") === "1", "the retry");
  assert.deepEqual(app.optionValues(), ["storefront", "docs", "all"]);
});

test("retry: a 404 on /api/projects is the answer and is not asked for again", async () => {
  const app = await boot({ hash: "#/overview", respond: (pathname) => (pathname === "/api/projects" ? [404, {}] : null) });
  await app.go("#/agents");
  await app.go("#/models");
  assert.equal(app.count("/api/projects"), 1);
  assert.equal(app.root.getAttribute("data-rendered"), "error");
});

test("retry: rules and files that failed are asked for on a route change, a 404 is not", async () => {
  const app = await boot({
    hash: "#/overview?project=storefront",
    respond: (pathname, search, n) => {
      if (pathname === "/api/rules") return n === 1 ? [503, {}] : [200, { rules: [] }];
      if (pathname === "/api/files") return [404, {}];
      return null;
    },
  });
  assert.equal(app.count("/api/rules"), 1);
  await app.go("#/overview?project=storefront&range=today");
  assert.equal(app.count("/api/rules"), 1, "a range change asks for nothing");
  await app.go("#/rules?project=storefront");
  assert.equal(app.count("/api/rules"), 2);
  await app.go("#/files?project=storefront");
  await app.go("#/agents?project=storefront");
  assert.equal(app.count("/api/rules"), 2, "the 200 is kept");
  assert.equal(app.count("/api/files"), 1, "the 404 is kept");
});

// ---------------------------------------------------------------- shell.js menu

const OPEN_HASH = "#/overview?project=storefront";

async function openMenu(options = {}) {
  const app = await boot({ hash: OPEN_HASH, ...options });
  app.topbar.rect.bottom = 96;
  app.menu.click();
  return app;
}

// The nodes the open menu must mark: the children of .main other than the top bar, and the children of
// the top bar other than the button.
const behind = (app) => [
  ...app.wrap.childNodes.filter((n) => n !== app.topbar),
  ...app.topbar.childNodes.filter((n) => n !== app.menu),
];
const inertNodes = (app) => [...app.wrap.childNodes, ...app.topbar.childNodes, app.wrap, app.topbar, app.menu, app.sidebar]
  .filter((n) => n.hasAttribute("inert"));

function assertClosed(app) {
  assert.equal(app.menu.getAttribute("aria-expanded"), "false");
  assert.ok(!app.sidebar.classList.contains("is-open"));
  assert.deepEqual(inertNodes(app), [], "nothing is inert");
  assert.equal(app.sidebar.style.top, "", "top is cleared");
  assert.equal(app.sidebar.style.height, "", "height is cleared");
}

test("menu: open marks the nodes behind the panel inert and leaves the button out", async () => {
  const app = await openMenu();
  assert.equal(app.menu.getAttribute("aria-expanded"), "true");
  assert.ok(app.sidebar.classList.contains("is-open"));
  const want = behind(app);
  assert.ok(want.length >= 3, "the content, the title and the right group");
  assert.deepEqual(inertNodes(app), want);
  assert.ok(!app.wrap.hasAttribute("inert"), ".main itself is not inert");
  assert.ok(!app.topbar.hasAttribute("inert"), "the top bar itself is not inert");
  assert.ok(!app.menu.hasAttribute("inert"), "the button is not inert");
  assert.ok(!app.sidebar.hasAttribute("inert"), "the panel is not inert");
});

test("menu: the panel opens below the top bar", async () => {
  const app = await openMenu();
  assert.equal(app.sidebar.style.top, "96px");
  assert.equal(app.sidebar.style.height, "calc(100vh - 96px)");
  assert.equal(FElement.focused, app.sidebar.find((n) => n.tagName === "a")[0], "focus is on the first nav link");
});

test("menu: a negative measure is clamped at 0", async () => {
  const app = await boot({ hash: OPEN_HASH });
  app.topbar.rect.bottom = -12;
  app.menu.click();
  assert.equal(app.sidebar.style.top, "0px");
  assert.equal(app.sidebar.style.height, "calc(100vh - 0px)");
});

test("menu: the button closes the menu and keeps focus", async () => {
  const app = await openMenu();
  app.menu.click();
  assertClosed(app);
  assert.equal(FElement.focused, app.menu);
});

test("menu: Escape closes it and focus returns to the button", async () => {
  const app = await openMenu();
  app.doc.dispatch("keydown", { key: "Escape" });
  assertClosed(app);
  assert.equal(FElement.focused, app.menu);
});

test("menu: Escape does nothing while closed", async () => {
  const app = await boot({ hash: OPEN_HASH });
  const before = app.menu.focusCalls || 0;
  app.doc.dispatch("keydown", { key: "Escape" });
  assert.equal(app.menu.focusCalls || 0, before);
});

test("menu: a nav link closes it, and the hashchange that follows does no second round", async () => {
  const app = await openMenu();
  const link = app.sidebar.find((n) => n.tagName === "a")[1];
  const before = app.menu.focusCalls || 0;
  link.click();
  assertClosed(app);
  assert.equal(FElement.focused, app.menu);
  app.win.location.hash = "#/agents?project=storefront";
  await tick(20);
  assertClosed(app);
  assert.equal(app.menu.focusCalls, before + 1, "focus moved to the button once");
});

test("menu: a click outside closes it and focus returns to the button", async () => {
  const app = await openMenu();
  app.content.click();
  assertClosed(app);
  assert.equal(FElement.focused, app.menu);
});

test("menu: a click inside the panel, off a link, keeps it open", async () => {
  const app = await openMenu();
  app.sidebar.find((n) => n.getAttribute("class") === "sb-brand")[0].click();
  assert.equal(app.menu.getAttribute("aria-expanded"), "true");
  assert.deepEqual(inertNodes(app), behind(app));
});

test("menu: a hashchange closes it and focus returns to the button", async () => {
  const app = await openMenu();
  app.win.location.hash = "#/models?project=storefront";
  await tick(20);
  assertClosed(app);
  assert.equal(FElement.focused, app.menu);
});

test("menu: widening past the breakpoint closes it without moving focus", async () => {
  const app = await openMenu();
  const link = app.sidebar.find((n) => n.tagName === "a")[0];
  assert.equal(FElement.focused, link);
  app.media.matches = false;
  app.media.listeners.forEach((fn) => fn({ matches: false }));
  assertClosed(app);
  assert.equal(FElement.focused, link, "focus did not move");
});

test("menu: a media change that stays narrow leaves it open", async () => {
  const app = await openMenu();
  app.media.listeners.forEach((fn) => fn({ matches: true }));
  assert.equal(app.menu.getAttribute("aria-expanded"), "true");
});

test("menu: it opens and closes again, and the second round marks and clears the same nodes", async () => {
  const app = await openMenu();
  app.menu.click();
  assertClosed(app);
  app.topbar.rect.bottom = 120;
  app.menu.click();
  assert.deepEqual(inertNodes(app), behind(app));
  assert.equal(app.sidebar.style.top, "120px");
  app.doc.dispatch("keydown", { key: "Escape" });
  assertClosed(app);
});

// ---------------------------------------------------------------- shell.js project picker

test("project picker: a project with a change waiting on Save says Not saved, and a missing folder keeps its own words", async () => {
  const page = createPage();
  const format = await import(JS + "format.js");
  format.setStrings(STRINGS);
  const { createShell } = await import(JS + "shell.js");
  const shell = createShell({ sidebar: page.sidebar, topbar: page.topbar, onProject() {} });
  const projects = [
    { key: "a", name: "Alpha", state: "ok" },
    { key: "b", name: "Beta", state: "missing_folder" },
    { key: "c", name: "Gamma", state: "ok" },
  ];
  const options = () => page.topbar.find((n) => n.tagName === "option").map((n) => [n.value, n.textContent]);
  const state = (notSaved) => ({ projects, project: "a", nav: "settings", query: {}, version: null, notSaved });
  const all = ["all", STRINGS.all_projects];
  shell.update(state());
  assert.deepEqual(options(), [["a", "Alpha"], ["b", "Beta, folder not found"], ["c", "Gamma"], all], "no list given, nothing waits");
  shell.update(state([]));
  assert.deepEqual(options()[0], ["a", "Alpha"]);
  shell.update(state(["a", "c"]));
  assert.deepEqual(options(), [["a", "Alpha, Not saved"], ["b", "Beta, folder not found"], ["c", "Gamma, Not saved"], all]);
  assert.equal(options()[0][1], STRINGS.opt_not_saved.replace("{name}", "Alpha"));
  shell.update(state(["b"]));
  assert.deepEqual(options()[1], ["b", "Beta, folder not found"], "a missing folder keeps opt_missing");
  assert.deepEqual(options()[0], ["a", "Alpha"], "and the others go back");
  const select = page.topbar.find((n) => n.tagName === "select")[0];
  assert.equal(select.value, "a", "the open project stays selected");
  shell.update(state(["a"]));
  assert.equal(select.value, "a");
  assert.equal(options()[0][1], "Alpha, Not saved");
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

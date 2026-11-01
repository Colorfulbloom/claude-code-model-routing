// Browser-free checks of the edit session, run by tests/test_edit_session_js.py. Two levels.
// Unit checks run createEditSession (js/edit_session.js), postJSON and createApi (js/api.js) with fakes.
// App checks boot the real app.js on the fake DOM in fakedom.mjs with a fake fetch, from a copy of
// dashboard/static/js in a temp folder whose pages/trail.js also hands its context to the check, so a check
// can call ctx.edit as the Settings screens will. Nothing here opens a browser or a socket, and the tokens
// and payloads are made up. A failed check prints its name and the reason, and the exit code is 1.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { createPage } from "./fakedom.mjs";

const STATIC = new URL("../../dashboard/static/", import.meta.url);
const JS = new URL("js/", STATIC).href;
const STRINGS = JSON.parse(fs.readFileSync(new URL("strings.json", STATIC), "utf8"));

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

const logged = [];
console.error = (...args) => { logged.push(args.map(String).join(" ")); };

const { createEditSession } = await import(JS + "edit_session.js");
const { createApi, postJSON } = await import(JS + "api.js");

const TOKEN = "Tok-en_A1b2C3d4";
const OTHER = "Zz9-Yy8_Xx7";

// ---------------------------------------------------------------- unit: the session

function mkSession({ hash = "", status = [{ ok: true, status: 200, data: { enabled: true, launch_id: "L1" } }],
  post = {}, storage = new Map(), blocked = false } = {}) {
  const box = { hash, replaced: [], changes: 0, writes: 0, order: [], posts: [], statusCalls: 0 };
  const store = blocked ? {
    getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); }, removeItem() { throw new Error("blocked"); },
  } : {
    getItem: (k) => (storage.has(k) ? storage.get(k) : null),
    setItem: (k, v) => { storage.set(k, String(v)); },
    removeItem: (k) => { storage.delete(k); },
  };
  const answer = (name) => async (body, token) => {
    box.posts.push({ name, body, token });
    box.order.push("post " + name);
    const fn = post[name] || (() => ({ ok: true, status: 200, data: { ok: true } }));
    return fn(body, token);
  };
  const api = {
    editStatus: async () => {
      const i = Math.min(box.statusCalls, status.length - 1);
      box.statusCalls += 1;
      const one = status[i];
      return typeof one === "function" ? one() : one;
    },
    editPreview: answer("preview"),
    editSave: answer("save"),
    editUndo: answer("undo"),
  };
  const session = createEditSession({
    api,
    storage: store,
    getHash: () => box.hash,
    replaceHash: (h) => { box.replaced.push(h); box.hash = h; },
    onChange: () => { box.changes += 1; },
    onWrite: async () => { box.order.push("write start"); await tick(5); box.order.push("write end"); box.writes += 1; },
  });
  return { session, box, storage };
}

const ON = (launch) => ({ ok: true, status: 200, data: { enabled: true, launch_id: launch } });

test("take: removes edit=, keeps the route and every other query value", () => {
  const { session, box } = mkSession({ hash: "#/settings?project=api&edit=" + TOKEN + "&theme=dark" });
  assert.equal(session.take(), true);
  assert.deepEqual(box.replaced, ["#/settings?project=api&theme=dark"]);
});

test("take: drops the ? when edit= was the only value", () => {
  const { session, box } = mkSession({ hash: "#/settings/@main/effortLevel?edit=" + TOKEN });
  assert.equal(session.take(), true);
  assert.deepEqual(box.replaced, ["#/settings/@main/effortLevel"]);
});

test("take: an empty edit= is stripped and keeps no token", async () => {
  const { session, box, storage } = mkSession({ hash: "#/settings?edit=&range=7d" });
  assert.equal(session.take(), true);
  assert.deepEqual(box.replaced, ["#/settings?range=7d"]);
  assert.equal(storage.size, 0);
  await session.refresh();
  assert.equal(session.mode(), "locked");
});

test("take: no edit= returns false and leaves the address alone", () => {
  for (const hash of ["", "#/settings", "#/settings?project=api", "#/settings?editor=1"]) {
    const { session, box } = mkSession({ hash });
    assert.equal(session.take(), false, hash);
    assert.deepEqual(box.replaced, [], hash);
  }
});

test("take: the token is never logged", async () => {
  const seen = [];
  const keep = {};
  for (const m of ["log", "info", "warn", "error", "debug"]) {
    keep[m] = console[m];
    console[m] = (...a) => { seen.push(a.map(String).join(" ")); };
  }
  try {
    const { session } = mkSession({ hash: "#/settings?edit=" + TOKEN });
    session.take();
    await session.refresh();
    await session.preview("p", "t", "v");
  } finally {
    for (const m of Object.keys(keep)) console[m] = keep[m];
  }
  assert.equal(seen.join("\n").includes(TOKEN), false);
});

test("refresh: a freshly taken token stores launch_id beside it and goes ready", async () => {
  const { session, box, storage } = mkSession({ hash: "#/settings?edit=" + TOKEN, status: [ON("L1")] });
  session.take();
  assert.equal(session.mode(), null);
  await session.refresh();
  assert.equal(session.mode(), "ready");
  assert.equal(storage.get("mr_edit_token"), TOKEN);
  assert.equal(storage.get("mr_edit_launch"), "L1");
  assert.equal(box.changes, 1);
});

test("refresh: a stored token with the same launch_id is ready", async () => {
  const storage = new Map([["mr_edit_token", TOKEN], ["mr_edit_launch", "L1"]]);
  const { session } = mkSession({ storage, status: [ON("L1")] });
  await session.refresh();
  assert.equal(session.mode(), "ready");
});

test("refresh: a dead launch_id clears the token and locks", async () => {
  const storage = new Map([["mr_edit_token", TOKEN], ["mr_edit_launch", "OLD"]]);
  const { session, box } = mkSession({ storage, status: [ON("L2")] });
  await session.refresh();
  assert.equal(session.mode(), "locked");
  assert.equal(storage.size, 0);
  assert.equal(box.changes, 1);
  const out = await session.preview("p", "t", "v");
  assert.equal(out.kind, "locked");
  assert.equal(box.posts.length, 0, "no POST without a token");
});

test("refresh: enabled with no token is locked, edits off clears the token", async () => {
  const a = mkSession({ status: [ON("L1")] });
  await a.session.refresh();
  assert.equal(a.session.mode(), "locked");
  const storage = new Map([["mr_edit_token", TOKEN], ["mr_edit_launch", "L1"]]);
  const b = mkSession({ storage, status: [{ ok: true, status: 200, data: { enabled: false, launch_id: null } }] });
  await b.session.refresh();
  assert.equal(b.session.mode(), "off");
  assert.equal(storage.size, 0);
});

test("refresh: a failed answer leaves the mode as it is, null at boot", async () => {
  for (const bad of [{ ok: false, status: 404, data: null }, { ok: false, status: 0, data: null }, { ok: true, status: 200, data: null }]) {
    const storage = new Map([["mr_edit_token", TOKEN], ["mr_edit_launch", "L1"]]);
    const { session, box } = mkSession({ storage, status: [bad] });
    await session.refresh();
    assert.equal(session.mode(), null);
    assert.equal(box.changes, 0);
    assert.equal(storage.get("mr_edit_token"), TOKEN, "a failed answer does not clear the token");
  }
  const { session } = mkSession({ status: [ON("L1"), { ok: false, status: 500, data: null }] });
  await session.refresh();
  assert.equal(session.mode(), "locked");
  await session.refresh();
  assert.equal(session.mode(), "locked", "a later failure keeps the mode");
});

test("refresh: overlapping calls, only the latest decides", async () => {
  let release;
  const slow = () => new Promise((resolve) => { release = () => resolve({ ok: true, status: 200, data: { enabled: false, launch_id: null } }); });
  const { session } = mkSession({ status: [slow, ON("L1")] });
  const first = session.refresh();
  const second = session.refresh();
  await second;
  assert.equal(session.mode(), "locked");
  release();
  await first;
  assert.equal(session.mode(), "locked", "the older answer is dropped");
});

test("storage: a blocked storage still works for this page load", async () => {
  const { session, box } = mkSession({ blocked: true, hash: "#/settings?edit=" + TOKEN, status: [ON("L1")] });
  session.take();
  await session.refresh();
  assert.equal(session.mode(), "ready");
  const out = await session.preview("p", "t", "v");
  assert.equal(out.kind, "ok");
  assert.equal(box.posts[0].token, TOKEN);
  const none = createEditSession({
    api: { editStatus: async () => ON("L1") }, storage: null, getHash: () => "#/x?edit=" + TOKEN, replaceHash() {}, onChange() {}, onWrite() {},
  });
  none.take();
  await none.refresh();
  assert.equal(none.mode(), "ready");
});

async function ready(over = {}) {
  const made = mkSession({ hash: "#/settings?edit=" + TOKEN, status: [ON("L1")], ...over });
  made.session.take();
  await made.session.refresh();
  assert.equal(made.session.mode(), "ready");
  return made;
}

test("outcomes: bad_token on preview, save and undo clears the token and locks", async () => {
  const bad = () => ({ ok: false, status: 403, data: { error: "bad_token" } });
  for (const op of ["preview", "save", "undo"]) {
    const { session, box, storage } = await ready({ post: { [op]: bad } });
    const before = box.changes;
    const out = op === "preview" ? await session.preview("p", "t", "v")
      : op === "save" ? await session.save("p", { base_file: "a", base_trail: "b", base_others: "c" }, "t", "v")
        : await session.undo("p", "e1");
    assert.equal(out.kind, "locked", op);
    assert.equal(out.res.status, 403);
    assert.equal(session.mode(), "locked", op);
    assert.equal(storage.size, 0, op);
    assert.equal(box.changes, before + 1, op);
    assert.equal(box.writes, 0, op);
    const again = await session.preview("p", "t", "v");
    assert.equal(again.kind, "locked");
    assert.equal(box.posts.length, 1, "no second POST");
  }
});

test("outcomes: stale gives one POST, no retry, and the new preview in res", async () => {
  const stale = () => ({ ok: false, status: 409, data: { error: "stale", changed: true, changed_files: [], preview: { base_file: "n" } } });
  const { session, box } = await ready({ post: { save: stale } });
  const out = await session.save("p", { base_file: "a", base_trail: "b", base_others: "c" }, "t", "v");
  assert.equal(out.kind, "stale");
  assert.deepEqual(out.res.data.preview, { base_file: "n" });
  assert.equal(box.posts.length, 1);
  assert.equal(box.writes, 0);
});

test("outcomes: save and undo ok, raced and unverified call onWrite once, awaited before the return", async () => {
  const raced = () => ({ ok: false, status: 409, data: { error: "raced", edit: "e" } });
  const unverified = () => ({ ok: false, status: 500, data: { error: "unverified", stage: "x", file_unchanged: false } });
  const cases = [
    ["save", "ok", undefined, "ok"], ["undo", "ok", undefined, "ok"],
    ["save", "raced", raced, "raced"], ["undo", "raced", raced, "raced"],
    ["save", "unverified", unverified, "unverified"], ["undo", "unverified", unverified, "unverified"],
  ];
  for (const [op, label, fn, kind] of cases) {
    const { session, box } = await ready(fn ? { post: { [op]: fn } } : {});
    const out = op === "save" ? await session.save("p", {}, "t", "v") : await session.undo("p", "e1");
    assert.equal(out.kind, kind, op + " " + label);
    assert.equal(box.writes, 1, op + " " + label);
    assert.deepEqual(box.order.slice(-3), ["post " + op, "write start", "write end"], "onWrite finished before the return");
  }
});

test("outcomes: a preview drops nothing, whatever it answers", async () => {
  for (const reply of [{ ok: true, status: 200, data: { ok: true } }, { ok: false, status: 500, data: { error: "unverified" } },
    { ok: false, status: 409, data: { error: "raced" } }]) {
    const { session, box } = await ready({ post: { preview: () => reply } });
    await session.preview("p", "t", "v");
    assert.equal(box.writes, 0);
  }
});

test("outcomes: any other code is an error, and no onWrite", async () => {
  const { session, box } = await ready({ post: { save: () => ({ ok: false, status: 400, data: { error: "bad_value" } }),
    undo: () => ({ ok: false, status: 0, data: null }) } });
  const a = await session.save("p", {}, "t", "v");
  const b = await session.undo("p", "e");
  assert.equal(a.kind, "error");
  assert.equal(b.kind, "error");
  assert.equal(box.writes, 0);
  assert.equal(session.mode(), "ready");
});

test("outcomes: the bodies carry the project, target, value and the preview's base values unchanged", async () => {
  const { session, box } = await ready();
  await session.preview("p1", "tgt", { a: 1 });
  await session.save("p1", { base_file: "F", base_trail: "T", base_others: "O", extra: 1 }, "tgt", { a: 1 });
  await session.undo("p1", "ed-9");
  assert.deepEqual(box.posts.map((p) => p.body), [
    { project: "p1", target: "tgt", value: { a: 1 } },
    { project: "p1", target: "tgt", value: { a: 1 }, base_file: "F", base_trail: "T", base_others: "O" },
    { project: "p1", edit: "ed-9" },
  ]);
  assert.ok(box.posts.every((p) => p.token === TOKEN));
});

// ---------------------------------------------------------------- unit: postJSON and the api

function fakeFetch(answer) {
  const seen = [];
  globalThis.fetch = async (url, opts) => {
    seen.push({ url, opts });
    const a = typeof answer === "function" ? answer(url, opts) : answer;
    if (a === "throw") throw new Error("offline");
    return { ok: a.status < 300, status: a.status, json: async () => { if (a.bad) throw new Error("bad json"); return a.body; }, text: async () => "" };
  };
  return seen;
}

test("postJSON: sends the method, the three headers and the body, and reads an error body", async () => {
  const seen = fakeFetch({ status: 409, body: { error: "stale", preview: null } });
  const res = await postJSON("/api/edit/save", { project: "p" }, TOKEN);
  assert.deepEqual(res, { ok: false, status: 409, data: { error: "stale", preview: null } });
  const { url, opts } = seen[0];
  assert.equal(url, "/api/edit/save");
  assert.equal(opts.method, "POST");
  assert.equal(opts.credentials, "same-origin");
  assert.deepEqual(opts.headers, { Accept: "application/json", "Content-Type": "application/json", "X-Dashboard-Token": TOKEN });
  assert.equal(opts.body, JSON.stringify({ project: "p" }));
  assert.equal(url.includes(TOKEN), false);
});

test("postJSON: an unreadable body gives data null, a network error gives status 0, and it never throws", async () => {
  fakeFetch({ status: 500, bad: true });
  assert.deepEqual(await postJSON("/x", {}, TOKEN), { ok: false, status: 500, data: null });
  fakeFetch({ status: 200, body: { ok: true } });
  assert.deepEqual(await postJSON("/x", {}, TOKEN), { ok: true, status: 200, data: { ok: true } });
  fakeFetch("throw");
  assert.deepEqual(await postJSON("/x", {}, TOKEN), { ok: false, status: 0, data: null });
});

test("api: the edit calls are never cached, dropProjects clears project keys and keeps shared ones", async () => {
  const paths = [];
  const posts = [];
  const api = createApi(async (p) => { paths.push(p); return { ok: true, status: 200, data: {} }; },
    async (p, b, t) => { posts.push([p, b, t]); return { ok: true, status: 200, data: {} }; });
  await api.editStatus(); await api.editStatus();
  await api.editTargets("a b"); await api.editTargets("a b");
  await api.editHistory("a b"); await api.editHistory("a b");
  assert.deepEqual(paths, ["/api/edit", "/api/edit", "/api/edit/targets?project=a%20b", "/api/edit/targets?project=a%20b",
    "/api/edit/history?project=a%20b", "/api/edit/history?project=a%20b"]);
  await api.editPreview({ a: 1 }, "t"); await api.editSave({ b: 2 }, "t"); await api.editUndo({ c: 3 }, "t");
  assert.deepEqual(posts.map((p) => p[0]), ["/api/edit/preview", "/api/edit/save", "/api/edit/undo"]);
  paths.length = 0;
  await api.usage("k"); await api.usage("k"); await api.settings("k"); await api.rules(); await api.rules();
  assert.equal(paths.length, 3);
  assert.equal(api.hasProject("k"), true);
  api.dropProjects();
  assert.equal(api.hasProject("k"), false);
  await api.usage("k"); await api.settings("k"); await api.rules();
  assert.equal(paths.length, 5, "usage and settings fetched again, rules kept");
});

// ---------------------------------------------------------------- app: the real app.js on the fake DOM

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "mr-edit-js-"));
process.on("exit", () => { try { fs.rmSync(TMP, { recursive: true, force: true }); } catch (err) { /* nothing to do */ } });
fs.cpSync(new URL("js/", STATIC), path.join(TMP, "js"), { recursive: true });
fs.writeFileSync(path.join(TMP, "package.json"), '{"type":"module"}');
{
  // The copy's trail page keeps what it was handed, then draws as before.
  const file = path.join(TMP, "js", "pages", "trail.js");
  const src = fs.readFileSync(file, "utf8");
  assert.equal(src.split("export function render(").length, 2, "trail.js has one render");
  fs.writeFileSync(file, src.replace("export function render(", "function realRender(") +
    "\nexport function render(root, ctx) {\n  globalThis.__trail = { ctx, n: ((globalThis.__trail && globalThis.__trail.n) || 0) + 1 };\n" +
    "  return realRender(root, ctx);\n}\n");
}
const APP = pathToFileURL(path.join(TMP, "js", "app.js")).href;

const settingsPayload = (project, effort) => ({
  project, state: "ok",
  entries: [
    { key: "model", value: "claude-opus-5-5", status: "in_effect", layer: "user", file: "~/a.json", scope: "main", line: 2, rule_id: "x", rule_ids: ["x"], reason: "r" },
    { key: "effortLevel", value: effort, status: "in_effect", layer: "user", file: "~/a.json", scope: "main", line: 3, rule_id: "x", rule_ids: ["x"], reason: "r" },
  ],
  no_user_settings: false, shell_label: "Shell", path_display: "~/work/" + project, config_dir_display: "~/.claude",
  config_file_display: "~/.claude/routing-dashboard.json", models: { "claude-opus-5-5": "Opus 5.5" },
});

const TRAIL = "#/settings/@main/effortLevel?project=p1";
let runs = 0;

// Boots a fresh copy of app.js. Options: hash, preset (storage items), blocked, edit ([status, body] or null for a 404,
// or a function that returns one),
// settings (project, n) -> payload, gate (pathname, search, n) -> promise to wait on, post (path, body) -> [status, body].
async function boot({ hash = TRAIL, preset = {}, blocked = false, edit = [200, { enabled: true, launch_id: "L1" }],
  settings = (project) => settingsPayload(project, "high"), targets = null, gate = () => null, post = () => [200, { ok: true }] } = {}) {
  const page = createPage({ narrow: false });
  page.win.location._hash = hash;
  for (const [k, v] of Object.entries(preset)) page.win.sessionStorage.items.set(k, v);
  if (blocked) Object.defineProperty(page.win, "sessionStorage", { get() { throw new Error("blocked"); } });
  globalThis.__trail = null;
  const calls = [];
  const posts = [];
  const counts = new Map();
  globalThis.fetch = async (url, opts = {}) => {
    const u = new URL(url, "http://127.0.0.1");
    const key = u.pathname + u.search;
    const method = opts.method || "GET";
    calls.push({ url, key, method, headers: opts.headers || {} });
    let answer;
    if (method === "POST") {
      const body = JSON.parse(opts.body);
      posts.push({ path: u.pathname, body, headers: opts.headers });
      answer = post(u.pathname, body);
    } else {
      const n = (counts.get(key) || 0) + 1;
      counts.set(key, n);
      const wait = gate(u.pathname, u.searchParams, n);
      if (wait) await wait;
      const project = u.searchParams.get("project");
      if (u.pathname === "/static/strings.json") answer = [200, STRINGS];
      else if (u.pathname === "/api/projects") answer = [200, { projects: [{ key: "p1", name: "P One" }, { key: "p2", name: "P Two" }], current: "p1" }];
      else if (u.pathname === "/api/settings") answer = [200, settings(project, n)];
      else if (u.pathname === "/api/edit") answer = (typeof edit === "function" ? edit() : edit) || [404, { error: "not_found" }];
      else if (u.pathname === "/api/edit/targets" && targets) answer = [200, targets(project)];
      else if (u.pathname === "/api/edit/targets" || u.pathname === "/api/edit/history") answer = [200, { enabled: true, project, n }];
      else answer = [404, { error: "not_found" }];
    }
    const [status, body] = answer;
    return { ok: status >= 200 && status < 300, status, json: async () => body, text: async () => "" };
  };
  runs += 1;
  await import(APP + "?run=" + runs);
  const root = page.doc.documentElement;
  await until(() => root.getAttribute("data-rendered") !== null, "boot");
  await tick(20);
  const count = (pathname, project) => calls.filter((c) => c.method === "GET" && c.key === pathname + (project ? "?project=" + project : "")).length;
  const store = blocked ? { items: new Map() } : page.win.sessionStorage;
  let flip = false;
  // A fresh context: a range change draws the page again without any fetch.
  const ctxNow = async () => {
    flip = !flip;
    const before = globalThis.__trail ? globalThis.__trail.n : 0;
    page.win.location.hash = page.win.location.hash.replace(/[?&]range=\w+/, "") + (page.win.location.hash.includes("?") ? "&" : "?") + "range=" + (flip ? "7d" : "30d");
    await until(() => globalThis.__trail && globalThis.__trail.n > before, "the trail to draw");
    return globalThis.__trail.ctx;
  };
  const go = async (to) => { page.win.location.hash = to; await tick(30); };
  return { ...page, calls, posts, count, root, ctxNow, go, store };
}

const settingsText = (app) => app.sections.settings.textContent.replace(/\s+/g, " ").trim();

test("app: a token in the first address is taken at boot, stored and kept out of every URL", async () => {
  const app = await boot({ hash: TRAIL + "&edit=" + TOKEN });
  assert.equal(app.win.location.hash, TRAIL);
  assert.equal(app.store.items.get("mr_edit_token"), TOKEN);
  assert.equal(app.store.items.get("mr_edit_launch"), "L1");
  assert.equal(app.count("/api/edit"), 1);
  const ctx = await app.ctxNow();
  assert.equal(ctx.edit.mode, "ready");
  assert.equal(app.root.getAttribute("data-rendered"), "1");
  assert.equal(app.count("/api/edit/targets", "p1"), 1);
  assert.equal(app.count("/api/edit/history", "p1"), 1);
  assert.deepEqual(app.calls.filter((c) => c.url.includes(TOKEN)), []);
});

test("app: the router never sees edit= at boot, and other query values are kept", async () => {
  const app = await boot({ hash: "#/settings?edit=" + TOKEN + "&range=7d&theme=dark&project=p2" });
  assert.equal(app.win.location.hash, "#/settings?range=7d&theme=dark&project=p2");
  assert.equal(app.root.getAttribute("data-theme"), "dark");
  assert.equal(app.count("/api/settings", "p2"), 1);
  assert.equal(app.store.items.get("mr_edit_token"), TOKEN);
});

test("app: a token pasted into an open tab is taken on hashchange before the router reads the hash", async () => {
  const app = await boot({ hash: "#/settings?project=p1" });
  assert.equal(app.store.items.has("mr_edit_token"), false);
  assert.equal(app.count("/api/edit"), 1);
  const heard = app.listeners.hashchange;
  assert.ok(heard.length >= 2, "the session's listener and the router's");
  const seen = [];
  heard.forEach((fn, i) => { heard[i] = (e) => { seen.push(app.win.location.hash); return fn(e); }; });
  await app.go("#/agents?project=p1&edit=" + OTHER + "&range=7d");
  assert.ok(seen[0].includes("edit="), "the first listener saw the pasted address");
  assert.equal(seen.slice(1).some((h) => h.includes("edit=")), false, "no later listener saw edit=");
  assert.equal(app.win.location.hash, "#/agents?project=p1&range=7d");
  assert.equal(app.store.items.get("mr_edit_token"), OTHER);
  assert.equal(app.store.items.get("mr_edit_launch"), "L1");
  assert.equal(app.count("/api/edit"), 2);
  assert.equal(app.sections.agents.hidden, false, "the route was still handled");
  assert.deepEqual(app.calls.filter((c) => c.url.includes(OTHER)), []);
});

test("app: a stored token from a dead launch is cleared and the page is locked", async () => {
  const app = await boot({ preset: { mr_edit_token: TOKEN, mr_edit_launch: "OLD" } });
  assert.equal(app.store.items.has("mr_edit_token"), false);
  assert.equal(app.store.items.has("mr_edit_launch"), false);
  const ctx = await app.ctxNow();
  assert.equal(ctx.edit.mode, "locked");
  assert.equal((await ctx.edit.preview("t", "v")).kind, "locked");
  assert.equal(app.posts.length, 0);
});

test("app: a stored token with the live launch stays ready after a reload", async () => {
  const app = await boot({ preset: { mr_edit_token: TOKEN, mr_edit_launch: "L1" } });
  assert.equal((await app.ctxNow()).edit.mode, "ready");
});

test("app: with no /api/edit answer the mode stays null, nothing is fetched and the page is unchanged", async () => {
  const plain = await boot({ edit: null, hash: TRAIL });
  const ctx = await plain.ctxNow();
  assert.equal(ctx.edit.mode, null);
  assert.equal(plain.count("/api/edit/targets", "p1"), 0);
  assert.equal(plain.count("/api/edit/history", "p1"), 0);
  assert.equal(plain.root.getAttribute("data-rendered"), "1");
  const withToken = await boot({ edit: null, hash: TRAIL + "&edit=" + TOKEN });
  assert.equal(withToken.win.location.hash, TRAIL, "the token is still stripped");
  assert.equal((await withToken.ctxNow()).edit.mode, null);
});

test("app: edits off gives mode off, fetches targets and no history, and keeps the history null", async () => {
  const app = await boot({ edit: [200, { enabled: false, launch_id: null }], preset: { mr_edit_token: TOKEN, mr_edit_launch: "L1" },
    targets: (project) => ({ enabled: false, project, levels: [], files: [] }) });
  const ctx = await app.ctxNow();
  assert.equal(ctx.edit.mode, "off");
  assert.equal(app.count("/api/edit/targets", "p1"), 1);
  assert.equal(app.count("/api/edit/history", "p1"), 0);
  assert.equal(ctx.edit.targets.data.enabled, false);
  assert.equal(ctx.edit.history, null);
  assert.equal(app.store.items.has("mr_edit_token"), false);
});

test("app: loadEdit fetches targets and history in locked and ready, and targets alone in off", async () => {
  const preset = { mr_edit_token: TOKEN, mr_edit_launch: "L1" };
  const locked = await boot({ hash: TRAIL });
  assert.equal((await locked.ctxNow()).edit.mode, "locked");
  assert.equal(locked.count("/api/edit/targets", "p1"), 1);
  assert.equal(locked.count("/api/edit/history", "p1"), 1);
  const ready = await boot({ hash: TRAIL, preset });
  assert.equal((await ready.ctxNow()).edit.mode, "ready");
  assert.equal(ready.count("/api/edit/targets", "p1"), 1);
  assert.equal(ready.count("/api/edit/history", "p1"), 1);
  const off = await boot({ hash: TRAIL, edit: [200, { enabled: false, launch_id: null }] });
  const ctx = await off.ctxNow();
  assert.equal(ctx.edit.mode, "off");
  assert.equal(off.count("/api/edit/targets", "p1"), 1);
  assert.equal(off.count("/api/edit/history", "p1"), 0);
  assert.notEqual(ctx.edit.targets, null);
  assert.equal(ctx.edit.history, null);
  await ctx.edit.reload();
  assert.equal(off.count("/api/edit/targets", "p1"), 2, "reload asks for targets in off");
  assert.equal(off.count("/api/edit/history", "p1"), 0, "reload never asks for history in off");
});

test("app: on All projects loadEdit fetches neither targets nor history, in any mode", async () => {
  const preset = { mr_edit_token: TOKEN, mr_edit_launch: "L1" };
  for (const [name, options] of [["off", { edit: [200, { enabled: false, launch_id: null }] }], ["locked", {}], ["ready", { preset }]]) {
    for (const hash of ["#/settings?project=all", "#/settings/@main/effortLevel?project=all"]) {
      const app = await boot({ hash, ...options });
      await tick(30);
      assert.equal(app.root.getAttribute("data-rendered"), "1", name + " " + hash);
      if (hash.includes("effortLevel")) {
        const ctx = await app.ctxNow();
        assert.equal(ctx.edit.mode, name);
        await ctx.edit.reload();
      }
      for (const project of ["p1", "p2", "all"]) {
        assert.equal(app.count("/api/edit/targets", project), 0, name + " " + hash + " targets " + project);
        assert.equal(app.count("/api/edit/history", project), 0, name + " " + hash + " history " + project);
      }
    }
  }
});

test("app: Settings asks for targets in off, locked and ready, and not before the mode is known", async () => {
  const off = await boot({ hash: SETTINGS, edit: [200, { enabled: false, launch_id: null }] });
  assert.equal(off.count("/api/edit/targets", "p1"), 1, "Settings in off asks for targets");
  assert.equal(off.count("/api/edit/history", "p1"), 0);
  const locked = await boot({ hash: SETTINGS });
  assert.equal(locked.count("/api/edit/targets", "p1"), 1, "Settings in locked asks for targets");
  const ready = await boot({ hash: SETTINGS, preset: { mr_edit_token: TOKEN, mr_edit_launch: "L1" } });
  assert.equal(ready.count("/api/edit/targets", "p1"), 1, "Settings in ready asks for targets");
  const none = await boot({ hash: SETTINGS, edit: null });
  assert.equal(none.count("/api/edit/targets", "p1"), 0, "no mode, no targets");
  const other = await boot({ hash: "#/agents?project=p1", edit: [200, { enabled: false, launch_id: null }] });
  assert.equal(other.count("/api/edit/targets", "p1"), 0, "a page that shows no edit data asks for none");
});

test("app: refresh loads the project data and the edit data again, and does not wait on usage", async () => {
  let release;
  const held = new Promise((resolve) => { release = resolve; });
  const app = await boot({
    preset: { mr_edit_token: TOKEN, mr_edit_launch: "L1" },
    gate: (p, q, n) => (p === "/api/usage" && q.get("project") === "p1" && n === 2 ? held : null),
  });
  const ctx = await app.ctxNow();
  const before = { s: app.count("/api/settings", "p1"), t: app.count("/api/edit/targets", "p1"), h: app.count("/api/edit/history", "p1") };
  const timeout = tick(500).then(() => "waiting on usage");
  const done = await Promise.race([ctx.edit.refresh().then(() => "done"), timeout]);
  assert.equal(done, "done", "refresh waited on /api/usage");
  assert.equal(app.count("/api/settings", "p1"), before.s + 1);
  assert.equal(app.count("/api/usage", "p1"), 2);
  assert.equal(app.count("/api/edit/targets", "p1"), before.t + 1);
  assert.equal(app.count("/api/edit/history", "p1"), before.h + 1);
  assert.equal(app.posts.length, 0, "a refresh saves nothing");
  release();
  await tick(20);
});

test("app: a mode change draws the open page again and loads the targets that fit the new mode", async () => {
  let answer = [200, { enabled: true, launch_id: "L1" }];
  let serverOff = false;
  const app = await boot({ preset: { mr_edit_token: TOKEN, mr_edit_launch: "L1" }, edit: () => answer,
    targets: (project) => (serverOff ? { enabled: false, project, levels: [], files: [] } : { enabled: true, project, targets: [], levels: [] }) });
  const ctx = await app.ctxNow();
  assert.equal(ctx.edit.mode, "ready");
  assert.equal(ctx.edit.targets.data.enabled, true);
  assert.equal(ctx.edit.history.data.enabled, true);
  answer = [200, { enabled: false, launch_id: null }];
  serverOff = true;
  const drawn = globalThis.__trail.n;
  await app.go(TRAIL + "&edit=" + OTHER);
  await until(() => app.count("/api/edit") === 2, "the second mode answer");
  await until(() => app.count("/api/edit/targets", "p1") === 2, "the read-only targets");
  await tick(30);
  assert.ok(globalThis.__trail.n > drawn, "the trail was drawn again");
  const now = globalThis.__trail.ctx;
  assert.equal(now.edit.mode, "off");
  assert.equal(now.edit.targets.data.enabled, false, "the write data is gone and the read-only answer is held");
  assert.equal(now.edit.history, null, "the history was dropped and not asked for");
  assert.equal(app.count("/api/edit/history", "p1"), 1, "no history was fetched for the new mode");
});

test("app: a change to a mode with write access drops a held read-only answer and loads the full one", async () => {
  let answer = [200, { enabled: false, launch_id: null }];
  let serverOff = true;
  const app = await boot({ edit: () => answer,
    targets: (project) => (serverOff ? { enabled: false, project, levels: [], files: [] } : { enabled: true, project, targets: [], levels: [] }) });
  const ctx = await app.ctxNow();
  assert.equal(ctx.edit.mode, "off");
  assert.equal(ctx.edit.targets.data.enabled, false);
  answer = [200, { enabled: true, launch_id: "L1" }];
  serverOff = false;
  await app.go(TRAIL + "&edit=" + TOKEN);
  await until(() => app.count("/api/edit/history", "p1") === 1, "the history");
  await tick(30);
  const now = globalThis.__trail.ctx;
  assert.equal(now.edit.mode, "ready");
  assert.equal(now.edit.targets.data.enabled, true, "the read-only answer was replaced");
  assert.notEqual(now.edit.history, null);
});

test("app: targets and history load only on the main session's effortLevel trail and on Settings in ready mode", async () => {
  const other = await boot({ hash: "#/settings?project=p1&edit=" + TOKEN });
  await other.go("#/settings/@main/model?project=p1");
  await other.go("#/agents?project=p1");
  await other.go("#/settings/builder/effortLevel?project=p1");
  assert.equal(other.count("/api/edit/targets", "p1"), 1, "only the Settings route fetched, once");
  await other.go(TRAIL);
  assert.equal(other.count("/api/edit/targets", "p1"), 2);
  assert.equal(other.count("/api/edit/history", "p1"), 2);
  await other.go(TRAIL + "&range=7d");
  assert.equal(other.count("/api/edit/targets", "p1"), 2, "a range change fetches nothing");
  await other.go("#/settings/@main/effortLevel?project=p2");
  assert.equal(other.count("/api/edit/targets", "p2"), 1);
});

test("app: a project change clears targets and history, and a late answer for the old project is dropped", async () => {
  let release;
  const held = new Promise((resolve) => { release = resolve; });
  const app = await boot({ preset: { mr_edit_token: TOKEN, mr_edit_launch: "L1" }, gate: (p, q) => (p === "/api/edit/targets" && q.get("project") === "p1" && globalThis.__hold ? held : null) });
  globalThis.__hold = true;
  const ctx = await app.ctxNow();
  const first = ctx.edit.reload();
  await app.go("#/settings/@main/effortLevel?project=p2&range=7d");
  await until(() => app.count("/api/edit/targets", "p2") === 1, "targets for p2");
  release();
  await first;
  await tick(20);
  globalThis.__hold = false;
  const now = await app.ctxNow();
  assert.equal(now.project.key, "p2");
  assert.equal(now.edit.targets.data.project, "p2");
  assert.equal(now.edit.history.data.project, "p2");
});

async function writeScenario(post) {
  const app = await boot({ preset: { mr_edit_token: TOKEN, mr_edit_launch: "L1" }, post });
  // Visit p2 too, so its answers are cached before the write.
  await app.go("#/settings/@main/effortLevel?project=p2");
  await app.go(TRAIL);
  const ctx = await app.ctxNow();
  const before = {
    s1: app.count("/api/settings", "p1"), u1: app.count("/api/usage", "p1"),
    s2: app.count("/api/settings", "p2"), u2: app.count("/api/usage", "p2"),
    t: app.count("/api/edit/targets", "p1"), h: app.count("/api/edit/history", "p1"),
  };
  assert.deepEqual([before.s1, before.u1, before.s2, before.u2], [1, 1, 1, 1]);
  return { app, ctx, before };
}

test("app: after a save, every project's settings and usage are fetched again and targets and history are fresh", async () => {
  const { app, ctx, before } = await writeScenario();
  const out = await ctx.edit.save({ base_file: "F", base_trail: "T", base_others: "O" }, "tgt", "max");
  assert.equal(out.kind, "ok");
  assert.equal(app.count("/api/settings", "p1"), before.s1 + 1);
  assert.equal(app.count("/api/usage", "p1"), before.u1 + 1);
  assert.equal(app.count("/api/edit/targets", "p1"), before.t + 1);
  assert.equal(app.count("/api/edit/history", "p1"), before.h + 1);
  // The other project was dropped too: opening it asks again.
  await app.go("#/settings/@main/effortLevel?project=p2");
  assert.equal(app.count("/api/settings", "p2"), before.s2 + 1);
  assert.equal(app.count("/api/usage", "p2"), before.u2 + 1);
  const sent = app.posts[0];
  assert.equal(sent.path, "/api/edit/save");
  assert.equal(sent.headers["X-Dashboard-Token"], TOKEN);
  assert.equal(sent.headers["Content-Type"], "application/json");
  assert.deepEqual(sent.body, { project: "p1", target: "tgt", value: "max", base_file: "F", base_trail: "T", base_others: "O" });
  assert.deepEqual(app.calls.filter((c) => c.url.includes(TOKEN)), []);
});

test("app: after an undo the data is dropped the same way", async () => {
  const { app, ctx, before } = await writeScenario();
  const out = await ctx.edit.undo("edit-1");
  assert.equal(out.kind, "ok");
  assert.equal(app.posts[0].path, "/api/edit/undo");
  assert.deepEqual(app.posts[0].body, { project: "p1", edit: "edit-1" });
  assert.equal(app.count("/api/settings", "p1"), before.s1 + 1);
  assert.equal(app.count("/api/usage", "p1"), before.u1 + 1);
  assert.equal(app.count("/api/edit/targets", "p1"), before.t + 1);
});

test("app: raced and unverified drop the data like a save", async () => {
  const raced = await writeScenario(() => [409, { error: "raced", edit: "e" }]);
  assert.equal((await raced.ctx.edit.save({}, "t", "v")).kind, "raced");
  assert.equal(raced.app.count("/api/settings", "p1"), raced.before.s1 + 1);
  assert.equal(raced.app.count("/api/usage", "p1"), raced.before.u1 + 1);
  const unverified = await writeScenario(() => [500, { error: "unverified", stage: "s", file_unchanged: false }]);
  assert.equal((await unverified.ctx.edit.undo("e")).kind, "unverified");
  assert.equal(unverified.app.count("/api/settings", "p1"), unverified.before.s1 + 1);
  assert.equal(unverified.app.count("/api/edit/history", "p1"), unverified.before.h + 1);
});

test("app: a preview drops nothing and fetches nothing", async () => {
  const { app, ctx, before } = await writeScenario(() => [200, { ok: true, base_file: "F" }]);
  const out = await ctx.edit.preview("tgt", "max");
  assert.equal(out.kind, "ok");
  assert.deepEqual(app.posts[0].body, { project: "p1", target: "tgt", value: "max" });
  assert.equal(app.count("/api/settings", "p1"), before.s1);
  assert.equal(app.count("/api/usage", "p1"), before.u1);
  assert.equal(app.count("/api/edit/targets", "p1"), before.t);
});

test("app: stale makes one POST, no retry and no reload", async () => {
  const { app, ctx, before } = await writeScenario(() => [409, { error: "stale", changed: true, changed_files: [], preview: { base_file: "N" } }]);
  const out = await ctx.edit.save({ base_file: "F" }, "t", "v");
  assert.equal(out.kind, "stale");
  assert.deepEqual(out.res.data.preview, { base_file: "N" });
  assert.equal(app.posts.length, 1);
  assert.equal(app.count("/api/settings", "p1"), before.s1);
  assert.equal(app.count("/api/edit/targets", "p1"), before.t);
});

test("app: bad_token on a preview locks the page and clears the token", async () => {
  const { app, ctx } = await writeScenario(() => [403, { error: "bad_token" }]);
  assert.equal((await ctx.edit.preview("t", "v")).kind, "locked");
  assert.equal(app.store.items.has("mr_edit_token"), false);
  assert.equal(app.store.items.has("mr_edit_launch"), false);
  await tick(20);
  assert.equal((await app.ctxNow()).edit.mode, "locked");
});

// The Settings page draws no line about the edit state above its cells. The rail of the Effort cell carries it, and
// a read-only cell never does. The page asks for the targets in any mode the server answered.
const SETTINGS = "#/settings?project=p1";
const stateLine = (app) => app.sections.settings.find((n) => n.getAttribute && n.getAttribute("data-edit") === "state")[0] || null;
const bandOf = (app) => app.sections.settings.find((n) => n.getAttribute && n.getAttribute("class") === "s5-a")[0] || null;

test("app: the Settings page draws the band and no edit state line, and only the Effort rail says off or locked", async () => {
  const off = await boot({ hash: SETTINGS, edit: [200, { enabled: false, launch_id: null }] });
  assert.equal(stateLine(off), null);
  assert.ok(bandOf(off), "the band is drawn");
  const none = await boot({ hash: SETTINGS, edit: null });
  assert.equal(stateLine(none), null);
  assert.ok(bandOf(none));
  const locked = await boot({ hash: SETTINGS });
  assert.equal(stateLine(locked), null);
  assert.ok(bandOf(locked));
  const ready = await boot({ hash: SETTINGS, preset: { mr_edit_token: TOKEN, mr_edit_launch: "L1" } });
  assert.equal(stateLine(ready), null);
  assert.ok(bandOf(ready));
  // Effort is the cell that opens by default, so its rail says it.
  assert.equal(settingsText(off).includes(STRINGS.ed_off), true);
  assert.equal(settingsText(locked).includes(STRINGS.ed_locked), true);
  assert.equal(settingsText(ready).includes(STRINGS.ed_off) || settingsText(ready).includes(STRINGS.ed_locked), false);
  // A read-only cell never promises that --allow-edits or the printed link would make it editable.
  const offModel = await boot({ hash: SETTINGS + "&setting=model", edit: [200, { enabled: false, launch_id: null }] });
  assert.equal(settingsText(offModel).includes(STRINGS.ed_off), false);
  const lockedModel = await boot({ hash: SETTINGS + "&setting=model" });
  assert.equal(settingsText(lockedModel).includes(STRINGS.ed_locked), false);
});

test("app: a level chosen on Settings marks its project in the picker and the band, a switch and back keeps it, and Cancel clears it", async () => {
  const targets = (project) => ({
    project, enabled: true, levels_state: "ok", saveable: true, project_lock: null, runs_as: "low", blocked: [],
    levels: [
      { level: "low", result: "now", saveable: false, limits: [], files: [], certain: true },
      { level: "high", result: "offered", saveable: true, preselect: null, limits: [], certain: true,
        files: [{ layer: "project", target: "t1", pickable: true, line: 2, effect: "applies", lock_reason: null, op: "replace" }] },
    ],
    files: [{ layer: "project", file_display: "p/.claude/settings.json", state: "has_line", line: 2, value: "low", status: "in_effect", target: "t1", shared: true, lock_reason: null }],
    targets: [{ target: "t1", ref: "r1", layer: "project", file_display: "p/.claude/settings.json", line: 2 }],
  });
  const app = await boot({ hash: SETTINGS, preset: { mr_edit_token: TOKEN, mr_edit_launch: "L1" }, targets });
  const options = () => app.topbar.find((n) => n.tagName === "option").map((n) => [n.value, n.textContent]);
  const pending = () => app.sections.settings.find((n) => n.getAttribute && n.getAttribute("class") === "s5-pend").length;
  const choose = async (level) => {
    app.sections.settings.find((n) => n.tagName === "input" && n.getAttribute("name") === "p2-level").find((r) => r.value === level)
      .dispatch("change");
    await tick(30);
  };
  assert.deepEqual(options(), [["p1", "P One"], ["p2", "P Two"], ["all", STRINGS.all_projects]]);
  assert.equal(pending(), 0);
  await choose("high");
  assert.deepEqual(options()[0], ["p1", STRINGS.opt_not_saved.replace("{name}", "P One")], "the option says Not saved");
  assert.equal(options()[1][1], "P Two");
  assert.equal(pending(), 1, "and the band's Effort cell says it too, with no page render of its own");
  // The other project, and back.
  await app.go("#/settings?project=p2");
  assert.deepEqual(options()[0], ["p1", "P One, Not saved"], "the project put away still waits");
  assert.equal(options()[1][1], "P Two");
  assert.equal(pending(), 0);
  await app.go(SETTINGS);
  assert.equal(options()[0][1], "P One, Not saved");
  assert.equal(pending(), 1);
  // A page that is not Settings keeps the picker's mark.
  await app.go("#/agents?project=p1");
  assert.equal(options()[0][1], "P One, Not saved");
  await app.go(SETTINGS);
  const cancel = app.sections.settings.find((n) => n.tagName === "button" && n.textContent === STRINGS.ed_cancel)[0];
  assert.ok(cancel, "Cancel is in the foot");
  cancel.click();
  await tick(30);
  assert.deepEqual(options()[0], ["p1", "P One"]);
  assert.equal(pending(), 0);
});

test("app: Settings in ready mode loads the targets itself, and a dead key still draws the open page again", async () => {
  const preset = { mr_edit_token: TOKEN, mr_edit_launch: "L1" };
  const withTargets = () => ({ levels: ["low", "high"], levels_state: "ok", targets: [{ target: "t1", ref: "r1" }], blocked: [] });
  const fresh = await boot({ hash: SETTINGS, preset, targets: withTargets });
  assert.equal(fresh.count("/api/edit/targets", "p1"), 1, "a fresh boot on Settings loads the targets itself");
  const allProjects = await boot({ hash: "#/settings?project=all", preset, targets: withTargets });
  assert.equal(allProjects.count("/api/edit/targets", "p1"), 0, "All projects loads none");
  const { app, ctx } = await writeScenario(() => [403, { error: "bad_token" }]);
  await app.go(SETTINGS);
  const before = bandOf(app);
  assert.equal((await ctx.edit.preview("t", "v")).kind, "locked");
  await tick(30);
  assert.notEqual(bandOf(app), before, "the open Settings page was drawn again");
  assert.equal(stateLine(app), null);
});

test("app: the Settings page shows no edit line for All projects", async () => {
  const app = await boot({ hash: "#/settings?project=all" });
  assert.equal(app.sections.settings.hidden, false);
  assert.equal(stateLine(app), null);
  assert.equal(app.count("/api/edit"), 1, "the mode is known, locked, and the page still shows no line");
});

test("app: the state is cleared at the drop, and an old in-flight answer cannot land after it", async () => {
  // The first /api/settings for p2 is held. A save then drops everything and loads p2 again, and the old answer
  // is released last. The page must keep drawing the new value.
  let release;
  const held = new Promise((resolve) => { release = resolve; });
  const ready = { mr_edit_token: TOKEN, mr_edit_launch: "L1" }; // the same mode, so the pages differ by the payload alone
  const refApp = await boot({ hash: "#/settings?project=p2", preset: ready, settings: (project) => settingsPayload(project, "low") });
  const lowText = settingsText(refApp);
  const highApp = await boot({ hash: "#/settings?project=p2", preset: ready, settings: (project) => settingsPayload(project, "high") });
  const highText = settingsText(highApp);
  assert.notEqual(lowText, highText, "the two payloads draw differently");

  const app = await boot({
    preset: { mr_edit_token: TOKEN, mr_edit_launch: "L1" },
    settings: (project, n) => settingsPayload(project, project === "p2" && n === 1 ? "high" : "low"),
    gate: (p, q, n) => (p === "/api/settings" && q.get("project") === "p2" && n === 1 ? held : null),
  });
  const ctx = await app.ctxNow();
  await app.go("#/settings?project=p2");
  await until(() => app.count("/api/settings", "p2") === 1, "the old settings request");
  const saving = ctx.edit.save({}, "t", "v");
  const out = await saving;
  assert.equal(out.kind, "ok");
  await until(() => app.count("/api/settings", "p2") === 2, "the new settings request");
  await tick(20);
  assert.equal(settingsText(app), lowText, "the new value is drawn");
  release();
  await tick(40);
  assert.equal(settingsText(app), lowText, "the old answer did not come back");
});

test("app: while the new answer is held after a drop, the page holds no old data", async () => {
  let release;
  const held = new Promise((resolve) => { release = resolve; });
  const app = await boot({
    preset: { mr_edit_token: TOKEN, mr_edit_launch: "L1" },
    settings: (project, n) => settingsPayload(project, n === 1 ? "high" : "low"),
    gate: (p, q, n) => ((p === "/api/settings" || p === "/api/usage") && q.get("project") === "p1" && n === 2 ? held : null),
  });
  const ctx = await app.ctxNow();
  assert.notEqual(ctx.data.settings, null);
  assert.notEqual(ctx.data.usage, null);
  const saving = ctx.edit.save({}, "t", "v");
  await until(() => app.count("/api/settings", "p1") === 2, "the second settings request");
  const midway = await app.ctxNow();
  assert.equal(midway.data.settings, null, "state.settings was cleared");
  assert.equal(midway.data.usage, null, "state.usage was cleared");
  release();
  await saving;
  const after = await app.ctxNow();
  assert.notEqual(after.data.settings, null);
});

test("app: a save returns while /api/usage is still held back, with settings, targets and history fresh", async () => {
  let release;
  const held = new Promise((resolve) => { release = resolve; });
  const app = await boot({
    preset: { mr_edit_token: TOKEN, mr_edit_launch: "L1" },
    settings: (project, n) => settingsPayload(project, n === 1 ? "high" : "low"),
    gate: (p, q, n) => (p === "/api/usage" && q.get("project") === "p1" && n === 2 ? held : null),
  });
  const ctx = await app.ctxNow();
  const before = { t: app.count("/api/edit/targets", "p1"), h: app.count("/api/edit/history", "p1") };
  const timeout = tick(500).then(() => "waiting on usage");
  const out = await Promise.race([ctx.edit.save({}, "t", "v"), timeout]);
  assert.notEqual(out, "waiting on usage", "the save waited on /api/usage");
  assert.equal(out.kind, "ok");
  assert.equal(app.count("/api/usage", "p1"), 2, "usage was asked for again");
  assert.equal(app.count("/api/settings", "p1"), 2);
  assert.equal(app.count("/api/edit/targets", "p1"), before.t + 1);
  assert.equal(app.count("/api/edit/history", "p1"), before.h + 1);
  assert.notEqual((await app.ctxNow()).data.settings, null);
  release();
  await tick(20);
});

test("app: a blocked sessionStorage still takes the token for this page load", async () => {
  const app = await boot({ hash: TRAIL + "&edit=" + TOKEN, blocked: true });
  assert.equal(app.win.location.hash, TRAIL);
  const ctx = await app.ctxNow();
  assert.equal(ctx.edit.mode, "ready");
  assert.equal((await ctx.edit.preview("t", "v")).kind, "ok");
  assert.equal(app.posts[0].headers["X-Dashboard-Token"], TOKEN);
});

test("app: the token never appears in any fetch URL across a whole session", async () => {
  const app = await boot({ hash: TRAIL + "&edit=" + TOKEN });
  const ctx = await app.ctxNow();
  await ctx.edit.preview("t", "v");
  await ctx.edit.save({}, "t", "v");
  await ctx.edit.undo("e");
  await app.go("#/agents?project=p2");
  assert.ok(app.calls.length > 8);
  assert.deepEqual(app.calls.filter((c) => c.url.includes(TOKEN) || c.key.includes(TOKEN)), []);
  assert.equal(app.win.location.hash.includes(TOKEN), false);
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

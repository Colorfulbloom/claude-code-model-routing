// Browser-free checks of the Installed files page, run by tests/test_files_js.py. They load pages/files.js and
// the shared modules from dashboard/static/js against the small fake DOM in fakedom.mjs. Nothing here opens a
// browser or a socket. The payload "files" is a real /api/files answer for the committed demo set (builder and
// reviewer match, scribe differs, tech-writer is missing), which the Python test writes into the folder named
// by MR_PAYLOADS. The ones for edge cases are written by hand in the same shape. A failed check prints its name
// and the reason, and the exit code is 1.
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
const files = await import(JS + "pages/files.js");

// The setter below catches any attempt to parse text as markup.
const parsed = [];
Object.defineProperty(FElement.prototype, "innerHTML", { set(v) { parsed.push(String(v)); }, get() { return ""; } });
Object.defineProperty(FElement.prototype, "outerHTML", { set(v) { parsed.push(String(v)); }, get() { return ""; } });

const hasClass = (n, c) => n.classList && n.classList.contains(c);
const byClass = (root, c) => root.find((n) => hasClass(n, c));
const byTag = (root, tag) => root.find((n) => n.tagName === tag);
const text = (n) => n.textContent;
const sub = (node, c) => byClass(node, c)[0];

function show(payload, { project = { key: "app", name: "App" }, res = null } = {}) {
  const page = createPage();
  const root = page.sections.files;
  const ctx = {
    route: { name: "files", params: {} },
    project,
    data: { files: res || (payload ? { ok: true, status: 200, data: payload } : null) },
    hashFor: (name, params) => router.hashFor(name, params, { project: project.key }),
  };
  files.render(root, ctx);
  return root;
}

const FILES = real("files");
const rowsOf = (root) => byTag(root, "tbody")[0].childNodes;
const cells = (tr) => tr.childNodes;

const WORDS = {
  match: ["Matches", "Nothing to do"],
  differs: ["Differs", "Run the installer again to update it"],
  missing: ["Missing", "Run the installer to add it"],
};

// ---------------------------------------------------------------- the page

test("page: the head comes first, then the Installed files card, then the foot line outside it", () => {
  const root = show(FILES);
  assert.equal(root.childNodes.length, 3);
  assert.equal(root.childNodes[0].classList.contains("ph"), true);
  assert.equal(text(byTag(root, "h1")[0]), "Installed files");
  assert.equal(text(sub(root, "intro")), STRINGS.intro_files);
  const card = root.childNodes[1];
  assert.equal(card.tagName, "section");
  assert.equal(hasClass(card, "cd"), true);
  assert.equal(text(byTag(card, "h2")[0]), "Installed files");
  assert.equal(byClass(card, "cd-ic").length, 1, "the files icon");
  const foot = root.childNodes[2];
  assert.equal(foot.tagName, "p");
  assert.equal(hasClass(foot, "foot"), true);
  assert.equal(text(foot), "Compared when the page loaded.");
  assert.equal(card.contains(foot), false);
});

test("page: the table has File, State and What to do, each cell carrying its column name", () => {
  const root = show(FILES);
  const table = byTag(root, "table")[0];
  assert.equal(hasClass(table, "dt"), true);
  assert.deepEqual(byTag(table, "th").map(text), ["File", "State", "What to do"]);
  assert.deepEqual(byTag(table, "th").map((th) => th.getAttribute("scope")), ["col", "col", "col"]);
  for (const tr of rowsOf(root)) {
    assert.deepEqual(cells(tr).map((td) => td.getAttribute("data-l")), ["File", "State", "What to do"]);
  }
});

test("page: one row per file, in the server's order, with the path in a mono span", () => {
  const root = show(FILES);
  const rows = rowsOf(root);
  assert.equal(rows.length, FILES.files.length);
  assert.ok(rows.length >= 3);
  FILES.files.forEach((file, i) => {
    const path = sub(cells(rows[i])[0], "mono");
    assert.equal(path.tagName, "span");
    assert.equal(text(path), file.path);
  });
  assert.deepEqual(FILES.files.map((f) => f.path.split("/").pop()),
    ["builder.md", "reviewer.md", "scribe.md", "tech-writer.md", "writing.md", "model-routing-choices.json"]);
});

test("page: each state shows its mark glyph and its word, never a hue alone", () => {
  const root = show(FILES);
  const seen = new Set();
  FILES.files.forEach((file, i) => {
    const [word, next] = WORDS[file.state];
    const cell = cells(rowsOf(root)[i])[1];
    const pill = cell.childNodes[0];
    assert.equal(pill.tagName, "span");
    assert.equal(pill.getAttribute("class"), "st st-" + file.state);
    const mark = pill.childNodes[0];
    assert.equal(mark.tagName, "i");
    assert.equal(mark.getAttribute("class"), "mk");
    assert.equal(mark.getAttribute("aria-hidden"), "true");
    assert.equal(text(pill), word);
    assert.equal(text(cells(rowsOf(root)[i])[2]), next);
    seen.add(file.state);
  });
  assert.deepEqual([...seen].sort(), ["differs", "match", "missing"], "the demo holds all three states");
});

test("page: the demo answer reads Matches, Matches, Differs, Missing, Matches, Matches", () => {
  const root = show(FILES);
  assert.deepEqual(rowsOf(root).map((tr) => text(cells(tr)[1])), ["Matches", "Matches", "Differs", "Missing", "Matches", "Matches"]);
  assert.deepEqual(rowsOf(root).map((tr) => text(cells(tr)[2])), [
    "Nothing to do", "Nothing to do", "Run the installer again to update it", "Run the installer to add it",
    "Nothing to do", "Nothing to do"]);
});

test("page: the words are the strings in strings.json", () => {
  assert.equal(STRINGS.f_matches, "Matches");
  assert.equal(STRINGS.f_differs, "Differs");
  assert.equal(STRINGS.f_missing, "Missing");
  const root = show(FILES);
  const words = new Set(byClass(root, "st").map(text));
  assert.deepEqual([...words].sort(), [STRINGS.f_differs, STRINGS.f_matches, STRINGS.f_missing].sort());
});

test("page: All projects shows the same page", () => {
  const one = show(FILES);
  const all = show(FILES, { project: { key: "all", name: "All projects" } });
  assert.equal(all.childNodes.length, 3);
  assert.equal(text(all), text(one));
  assert.equal(byClass(all, "es").length, 0, "no picker prompt");
});

test("page: a missing or failed payload shows the head only", () => {
  for (const [label, root] of [
    ["none", show(null)],
    ["not ok", show(null, { res: { ok: false, status: 500, data: null } })],
    ["404", show(null, { res: { ok: false, status: 404, data: null } })],
    ["no data", show(null, { res: { ok: true, status: 200, data: null } })],
  ]) {
    assert.equal(root.childNodes.length, 1, label);
    assert.equal(root.childNodes[0].classList.contains("ph"), true, label);
  }
});

test("page: an answer with no files draws the table with no rows and the foot line", () => {
  const root = show({ files: [] });
  assert.equal(root.childNodes.length, 3);
  assert.equal(rowsOf(root).length, 0);
  assert.equal(byTag(root, "th").length, 3);
  assert.equal(text(root.childNodes[2]), STRINGS.files_foot);
});

test("page: an answer with no files list is the same as an empty one", () => {
  const root = show({});
  assert.equal(root.childNodes.length, 3);
  assert.equal(rowsOf(root).length, 0);
});

test("page: a state the page has no word for is left out", () => {
  const root = show({ files: [
    { path: "config/a.md", state: "match" }, { path: "config/b.md", state: "weird" }, { path: "config/c.md", state: "missing" }] });
  assert.deepEqual(rowsOf(root).map((tr) => text(cells(tr)[0])), ["config/a.md", "config/c.md"]);
});

test("page: it draws again from scratch", () => {
  const page = createPage();
  const root = page.sections.files;
  const ctx = { route: { name: "files", params: {} }, project: { key: "app" }, data: { files: { ok: true, status: 200, data: FILES } } };
  files.render(root, ctx);
  files.render(root, ctx);
  assert.equal(byClass(root, "ph").length, 1);
  assert.equal(byClass(root, "cd").length, 1);
  assert.equal(byClass(root, "foot").length, 1);
  assert.equal(rowsOf(root).length, FILES.files.length);
});

test("page: values from the server go in as text and never as markup", () => {
  const evil = "<img src=x onerror=alert(1)>";
  const before = parsed.length;
  const root = show({ files: [{ path: evil, state: "differs" }] });
  assert.deepEqual(parsed.slice(before), []);
  assert.equal(root.find((n) => n.tagName === "img").length, 0);
  assert.equal(text(sub(root, "mono")), evil);
  const source = fs.readFileSync(new URL("js/pages/files.js", STATIC), "utf8");
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

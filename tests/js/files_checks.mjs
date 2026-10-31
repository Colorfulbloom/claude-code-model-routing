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

test("page: the head comes first, then the Installed files card, then two foot lines outside it", () => {
  const root = show(FILES);
  assert.equal(root.childNodes.length, 4);
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
  const scope = root.childNodes[3];
  assert.equal(scope.tagName, "p");
  assert.equal(hasClass(scope, "foot"), true);
  assert.equal(text(scope), STRINGS.files_scope);
  assert.equal(card.contains(scope), false);
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
  assert.equal(all.childNodes.length, 4);
  assert.equal(text(all), text(one));
  assert.equal(byClass(all, "es").length, 0, "no picker prompt");
});

test("page: no answer yet shows the head only", () => {
  const root = show(null);
  assert.equal(root.childNodes.length, 1);
  assert.equal(root.childNodes[0].classList.contains("ph"), true);
});

test("page: a failed answer shows the head and the Can't compare the files state, with no table and no foot", () => {
  for (const [label, res] of [
    ["not ok", { ok: false, status: 500, data: null }],
    ["404", { ok: false, status: 404, data: null }],
    ["no data", { ok: true, status: 200, data: null }],
  ]) {
    const root = show(null, { res });
    assert.equal(root.childNodes.length, 2, label);
    assert.equal(root.childNodes[0].classList.contains("ph"), true, label);
    assert.equal(text(byTag(root.childNodes[1], "h2")[0]), "Can't compare the files", label);
    assert.equal(text(sub(root, "es-t")), STRINGS.files_error_t, label);
    assert.equal(byClass(root, "cd-ic").length, 1, label);
    assert.equal(byTag(root, "table").length, 0, label);
    assert.equal(byClass(root, "foot").length, 0, label);
  }
});

test("page: an answer with no files draws the table with no rows and the foot line", () => {
  const root = show({ files: [] });
  assert.equal(root.childNodes.length, 4);
  assert.equal(rowsOf(root).length, 0);
  assert.equal(byTag(root, "th").length, 3);
  assert.equal(text(root.childNodes[2]), STRINGS.files_foot);
  assert.equal(text(root.childNodes[3]), STRINGS.files_scope);
});

test("page: an answer with no files list is the same as an empty one", () => {
  const root = show({});
  assert.equal(root.childNodes.length, 4);
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
  assert.equal(byClass(root, "foot").length, 2);
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

// ---------------------------------------------------------------- saved choices

const CHOICES_PATH = "config/model-routing-choices.json";
const agentFiles = (state) => [
  { path: "config/agents/scout.md", state, caution: true },
  { path: "config/agents/judge.md", state: "match" },
  { path: "config/rules/one.md", state: "match" },
  { path: CHOICES_PATH, state: "match" },
];

const noticeOf = (root) => {
  const heads = byTag(root, "h2").map(text);
  return heads.filter((x) => /choices/.test(x));
};

test("choices: the demo answer has status ok and shows no notice", () => {
  assert.equal(FILES.choices.status, "ok");
  assert.deepEqual(FILES.choices.bad, []);
  const root = show(FILES);
  assert.deepEqual(noticeOf(root), []);
  assert.equal(byClass(root, "cd").length, 1);
});

test("choices: a broken file shows its heading and text above the table card, with the path", () => {
  const root = show({ files: agentFiles("differs"), choices: { status: "bad", bad: [], path: CHOICES_PATH } });
  assert.equal(root.childNodes.length, 5);
  const notice = root.childNodes[1];
  assert.equal(hasClass(notice, "cd"), true);
  assert.equal(text(byTag(notice, "h2")[0]), "Can't use the saved choices");
  assert.equal(text(sub(notice, "es-t")),
    CHOICES_PATH + " is broken, so the installer uses the repo's default model and effort for every agent. " +
    "With --yes, that undoes any pick you made. Run it in a terminal without --yes and pick again.");
  assert.equal(byClass(notice, "cd-ic").length, 1);
  assert.equal(byTag(root.childNodes[2], "table").length, 1, "the table card follows");
  assert.equal(byClass(root, "nt").length, 0, "not a div.nt notice");
});

test("choices: a missing file shows its notice, unless every row is Missing", () => {
  const some = show({ files: agentFiles("differs").slice(0, 2).concat([{ path: CHOICES_PATH, state: "missing", caution: true }]),
    choices: { status: "missing", bad: [], path: CHOICES_PATH } });
  assert.deepEqual(noticeOf(some), ["No saved choices file"]);
  assert.equal(text(sub(some.childNodes[1], "es-t")),
    CHOICES_PATH + " is missing, so the installer uses the repo's default model and effort for every agent. " +
    "With --yes, that undoes any pick you made. Run it in a terminal without --yes and pick again.");
  const none = show({ files: [{ path: "config/a.md", state: "missing" }, { path: CHOICES_PATH, state: "missing" }],
    choices: { status: "missing", bad: [], path: CHOICES_PATH } });
  assert.deepEqual(noticeOf(none), []);
  assert.equal(none.childNodes.length, 4, "head, card and the two foot lines");
});

test("choices: an ok file with bad names lists them joined with a comma and a space", () => {
  const root = show({ files: agentFiles("differs"), choices: { status: "ok", bad: ["scout", "judge"], path: CHOICES_PATH } });
  assert.deepEqual(noticeOf(root), ["Can't use some saved choices"]);
  assert.equal(text(sub(root.childNodes[1], "es-t")),
    CHOICES_PATH + " has no usable choice for scout, judge, so the installer uses the repo's default model and effort instead. " +
    "With --yes, that undoes any pick you made. Run it in a terminal without --yes and pick again.");
});

test("choices: an ok file with no bad names, or no choices field, shows no notice", () => {
  assert.deepEqual(noticeOf(show({ files: agentFiles("match"), choices: { status: "ok", bad: [], path: CHOICES_PATH } })), []);
  assert.deepEqual(noticeOf(show({ files: agentFiles("match") })), []);
});

test("choices: a Differs row with caution reads the pick-again words, others keep the update words", () => {
  const root = show({ files: [
    { path: "config/agents/scout.md", state: "differs", caution: true },
    { path: "config/agents/judge.md", state: "differs" },
    { path: "config/agents/fast-worker.md", state: "match" },
  ], choices: { status: "ok", bad: ["scout"], path: CHOICES_PATH } });
  assert.deepEqual(rowsOf(root).map((tr) => text(cells(tr)[2])), [
    "Run the installer without --yes and pick again", "Run the installer again to update it", "Nothing to do"]);
  assert.deepEqual(rowsOf(root).map((tr) => text(cells(tr)[1])), ["Differs", "Differs", "Matches"]);
});

test("choices: the flag in the What to do cell stays on one line", () => {
  const root = show({ files: [{ path: "config/agents/scout.md", state: "differs", caution: true }] });
  const flag = sub(cells(rowsOf(root)[0])[2], "nw");
  assert.equal(flag.tagName, "span");
  assert.equal(text(flag), "--yes");
});

test("choices: a missing row with caution reads the pick-again words, others keep the add words", () => {
  const root = show({ files: [
    { path: CHOICES_PATH, state: "missing", caution: true },
    { path: "config/agents/scout.md", state: "missing" },
  ] });
  const [first, second] = rowsOf(root);
  assert.equal(text(cells(first)[2]), "Run the installer without --yes and pick again");
  assert.equal(text(cells(second)[2]), "Run the installer to add it");
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

// Browser-free checks of dashboard/static/js/edit_ref.js, run by tests/test_api_edit.py with Node.
// The shared table in tests/fixtures/edit_ref_table.json holds {entry, ref} rows. The Python test
// proves api_edit.ref_of gives each ref, and this file proves editRef gives the same string, so the
// server's match key and the page's cannot drift apart. A failed check prints its name and the exit
// code is 1.
import assert from "node:assert/strict";
import fs from "node:fs";
import { editRef } from "../../dashboard/static/js/edit_ref.js";

const TABLE = JSON.parse(fs.readFileSync(new URL("../fixtures/edit_ref_table.json", import.meta.url), "utf8"));

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

test("the table holds about ten rows", () => {
  assert.ok(TABLE.length >= 10, "only " + TABLE.length + " rows");
});

for (const row of TABLE) {
  test("editRef matches the table: " + row.note, () => {
    assert.equal(editRef(row.entry), row.ref);
  });
}

test("a ref is a JSON array of five values", () => {
  for (const row of TABLE) {
    const parts = JSON.parse(editRef(row.entry));
    assert.equal(parts.length, 5, row.note);
  }
});

test("the line is not part of the ref", () => {
  const base = { key: "effortLevel", layer: "user", file: "config/settings.json" };
  assert.equal(editRef({ ...base, line: 1 }), editRef({ ...base, line: 99 }));
  assert.equal(editRef({ ...base, line: 1 }), editRef(base));
});

test("a missing agent is the main session and a missing path is the key", () => {
  const parts = JSON.parse(editRef({ key: "effortLevel", layer: "user", file: "a.json", agent: "", path: "" }));
  assert.deepEqual(parts, ["@main", "effortLevel", "user", "a.json", "effortLevel"]);
});

test("a missing file is null and an empty file stays empty", () => {
  assert.equal(JSON.parse(editRef({ key: "k", layer: "default" }))[3], null);
  assert.equal(JSON.parse(editRef({ key: "k", layer: "default", file: null }))[3], null);
  assert.equal(JSON.parse(editRef({ key: "k", layer: "default", file: "" }))[3], "");
});

test("a dotted model name stays one piece, so the path is never split", () => {
  const path = "modelSettings.claude-opus-4.6.effortLevel";
  assert.equal(JSON.parse(editRef({ key: "effortLevel", layer: "user", file: "f", path }))[4], path);
});

let failed = 0;
for (const [name, fn] of tests) {
  try {
    fn();
    console.log("ok   " + name);
  } catch (err) {
    failed += 1;
    console.log("FAIL " + name + "\n     " + String(err && err.stack ? err.stack : err).split("\n").slice(0, 6).join("\n     "));
  }
}
console.log((tests.length - failed) + " of " + tests.length + " checks passed");
process.exit(failed ? 1 : 0);

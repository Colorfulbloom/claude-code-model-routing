// Browser-free checks of the Effort body, its rail and foot on the Settings page, and of the undo strip, run by
// tests/test_edit_card_js.py. They load pages/settings.js and js/edit_card.js from dashboard/static/js against the
// fake DOM in fakedom.mjs, and give the page a ctx shaped like the one app.js builds: ctx.edit holds the mode,
// the targets, the history and the preview, save, undo, reload and refresh actions. The answers are real route
// answers that the Python test writes into the folder named by MR_PAYLOADS. Bodies a real run can't reach
// (unverified, raced, a failed write) are written here by hand, and so are the worlds the server doesn't build
// yet (a cleared project row, a stopped level). Nothing opens a browser or a socket, and every value is made up.
// A failed check prints its name and the reason, and the exit code is 1.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { FElement, createPage } from "./fakedom.mjs";

const STATIC = new URL("../../dashboard/static/", import.meta.url);
const JS = new URL("js/", STATIC).href;
const STRINGS = JSON.parse(fs.readFileSync(new URL("strings.json", STATIC), "utf8"));
const PAYLOADS = process.env.MR_PAYLOADS;
assert.ok(PAYLOADS, "MR_PAYLOADS names the folder of route answers");

const real = (name) => JSON.parse(fs.readFileSync(path.join(PAYLOADS, name + ".json"), "utf8"));
const clone = (x) => JSON.parse(JSON.stringify(x));

const tests = [];
const test = (name, fn) => tests.push([name, fn]);
const tick = (ms = 0) => new Promise((resolve) => setTimeout(resolve, ms));
const settle = async () => { for (let i = 0; i < 4; i++) await tick(); };

const format = await import(JS + "format.js");
format.setStrings(STRINGS);
const T = (key, slots) => format.t(key, slots);
const router = await import(JS + "router.js");
const settingsPage = await import(JS + "pages/settings.js");
const trail = await import(JS + "pages/trail.js");
const pickMod = await import(JS + "edit_pick.js");
const flowMod = await import(JS + "edit_flow.js");
const bandMod = await import(JS + "pages/band.js");

// The setter below catches any attempt to parse text as markup.
const parsed = [];
Object.defineProperty(FElement.prototype, "innerHTML", { set(v) { parsed.push(String(v)); }, get() { return ""; } });
Object.defineProperty(FElement.prototype, "outerHTML", { set(v) { parsed.push(String(v)); }, get() { return ""; } });

// ---------------------------------------------------------------- the page

const hasClass = (n, c) => Boolean(n.classList && n.classList.contains(c));
const byClass = (root, c) => root.find((n) => hasClass(n, c));
const text = (n) => n.textContent.replace(/\s+/g, " ").trim();
const tag = (root, name) => root.find((n) => n.tagName === name);
const buttons = (root) => tag(root, "button");
const btn = (root, label) => buttons(root).find((b) => text(b) === label);
const inputs = (root, name) => root.find((n) => n.tagName === "input" && n.getAttribute("type") === "radio" && n.getAttribute("name") === name);
const levelInputs = (root) => inputs(root, "p2-level");
const rowInputs = (root) => inputs(root, "p2-row");
const lvl = (root, level) => levelInputs(root).find((r) => r.value === level);
const rowIn = (root, layer) => rowInputs(root).find((r) => r.value === layer);
const rowOf = (input) => input.parentNode;
const checkedOf = (list) => list.filter((r) => r.hasAttribute("checked")).map((r) => r.value);
const off = (n) => n.hasAttribute("disabled");
const notes = (root) => byClass(root, "nt").filter((n) => hasClass(n, "p2-nt"));
// A result in the foot is drawn as a few siblings in the strip slot, so the slot stands for it: none when it is empty.
const stripOf = (root) => slotOf(root, "strip");
// The status row of a result in the foot (mark and line), the mark alone, and the path line under it.
const okRow = (root) => byClass(stripOf(root), "s4-ok")[0];
const okLine = (root) => text(tag(okRow(root), "span").find((n) => !hasClass(n, "s4-okm")));
const okMark = (root) => text(byClass(okRow(root), "s4-okm")[0]);
const pathLine = (root) => { const n = byClass(stripOf(root), "s4-hint")[0]; return n ? text(n) : null; };
const strips = (root) => (stripOf(root) && stripOf(root).childNodes.length ? [stripOf(root)] : []);
const nts = (root, kind) => notes(root).filter((n) => hasClass(n, "p2-nt-" + kind));
const headNote = (root) => text(byClass(root, "s4-runs")[0]);
// The values of the review's change line, the arrow between them kept: ["low", "→", "high"], or one value alone.
const bigs = (root) => {
  const chg = byClass(root, "s4-chg")[0];
  return chg ? tag(chg, "span").filter((n) => !hasClass(n, "sr")).map(text) : [];
};
// The foot's own buttons by label, and the review's notes in the rail.
const footButtons = (a) => tag(slotOf(a.root, "pick"), "button");
const footTexts = (a) => footButtons(a).map(text);
const slotOf = (root, name) => root.find((n) => n.getAttribute("data-edit") === name)[0] || null;
const anyKey = (root) => /\b(?:ed|where|row|place|review)_[a-z_]+\b/.test(root.textContent);
const plainRows = (root) => byClass(root, "s6-r").filter((n) => n.tagName === "div");
const liveRows = (root) => byClass(root, "s6-r").filter((n) => n.tagName === "label");
const noteTexts = (root) => byClass(root, "s4-note").map(text);

function flat(node, out = []) {
  out.push(node);
  for (const child of node.childNodes || []) flat(child, out);
  return out;
}
const order = (root, node) => flat(root).indexOf(node);

let uid = 0;
const wrap = (body) => (body === undefined || body === null ? null : body.fail ? { ok: false, status: 0, data: null } : { ok: true, status: 200, data: body });
const ok = (data) => ({ kind: "ok", res: { ok: true, status: 200, data } });
const bad = (kind, status, data) => ({ kind, res: { ok: false, status, data } });

// A Settings page with the edit session faked. data holds the settings, targets and history bodies. backend holds
// the preview, save, undo, reload and refresh answers. A save and an undo draw the page again before they
// resolve, as app.js does when it loads the new data, so the flow has to live through it. The targets answer
// carries the key of the project, as the server's does. a.use() moves the page to another project.
function app({ mode = "ready", data = {}, backend = {}, setting = null, key = "p" + (++uid) } = {}) {
  const page = createPage({ narrow: false });
  const root = page.sections.settings;
  root.hidden = false;
  const a = { page, root, key, log: { preview: [], save: [], undo: [], reload: 0, refresh: 0, draws: 0, shell: 0 } };
  const forKey = (body) => (body && typeof body === "object" && !body.fail ? { ...body, project: a.key } : body);
  const wrapT = (body) => wrap(forKey(body));
  const st = { mode, settings: data.settings, targets: wrapT(data.targets), history: wrap(data.history) };
  const log = a.log;
  const take = (fresh) => {
    if (!fresh) return;
    if ("settings" in fresh) st.settings = fresh.settings;
    if ("targets" in fresh) st.targets = wrapT(fresh.targets);
    if ("history" in fresh) st.history = wrap(fresh.history);
  };
  const makeCtx = () => ({
    route: { name: "settings", params: {}, query: { setting } },
    project: { key: a.key, name: "P" },
    data: { settings: st.settings ? { ok: true, status: 200, data: st.settings } : null },
    hashFor: (name, params, patch) => router.hashFor(name, params, { project: a.key, ...patch }),
    edit: {
      mode: st.mode,
      targets: st.targets,
      history: st.history,
      preview: async (target, value) => {
        log.preview.push([target, value]);
        return backend.preview(target, value, a);
      },
      save: async (pv, target, value) => {
        log.save.push({ pv, target, value });
        return after(await backend.save(pv, target, value, a));
      },
      undo: async (id) => {
        log.undo.push(id);
        return after(await backend.undo(id, a));
      },
      reload: async () => {
        log.reload += 1;
        if (backend.reload) { take(backend.reload(a)); a.draw(); }
      },
      refresh: async () => {
        log.refresh += 1;
        if (backend.refresh) { take(backend.refresh(a)); a.draw(); }
      },
      // app.js draws the project picker again from this, after a choice with no page render.
      syncShell: () => { log.shell += 1; },
    },
  });
  const after = (out) => {
    if (out.kind === "locked") {
      st.mode = "locked";
      a.draw();
    } else if (out.after) {
      take(out.after);
      a.draw();
    }
    return out;
  };
  a.st = st;
  a.wrapT = wrapT;
  a.makeCtx = makeCtx;
  a.draw = () => { log.draws += 1; settingsPage.render(root, makeCtx()); };
  a.body = () => slotOf(root, "body");
  a.rail = () => slotOf(root, "rail");
  a.foot = () => slotOf(root, "foot");
  a.choose = async (level) => { lvl(root, level).dispatch("change"); await settle(); };
  a.pickRow = async (layer) => { rowIn(root, layer).dispatch("change"); await settle(); };
  a.press = async (label) => { const b = btn(root, label); assert.ok(b, "a button named " + label); b.click(); await settle(); };
  a.setMode = (m) => { st.mode = m; };
  // Moves the page to another project with that project's answers, and draws.
  a.use = (nextKey, nextData) => {
    a.key = nextKey;
    st.settings = nextData.settings;
    st.targets = wrapT(nextData.targets);
    st.history = wrap(nextData.history);
    a.draw();
  };
  a.draw();
  return a;
}

// Scenario helpers.
const S = real("base");
const baseData = (over = {}) => ({ settings: S.start.settings, targets: S.start.targets, history: S.start.history, ...over });
const worldData = (name, over = {}) => {
  const w = real(name);
  return { settings: w.settings, targets: w.targets, history: w.history, ...over };
};
const afterSave = () => ({ settings: S.after_save.settings, targets: S.after_save.targets, history: S.after_save.history });
const LOCAL_SAVE = T("ed_save_to", { file: "settings.local.json" });

const levelOf = (targets, name) => targets.levels.find((l) => l.level === name);
const fileOf = (targets, name, layer) => levelOf(targets, name).files.find((f) => f.layer === layer);
const rowOfFiles = (targets, layer) => targets.files.find((f) => f.layer === layer);
const targetOf = (targets, layer) => targets.targets.find((x) => x.layer === layer);
const recount = (targets) => {
  for (const level of targets.levels) level.saveable = level.files.some((f) => f.pickable);
  targets.saveable = targets.levels.some((l) => l.saveable);
  return targets;
};
// Makes the file row of one layer pickable under the named levels (a has_line target of that layer must exist).
function open(targets, layer, names) {
  const tgt = targetOf(targets, layer);
  for (const name of names) {
    const f = fileOf(targets, name, layer);
    Object.assign(f, { target: tgt.target, op: "replace", line: tgt.line, effect: "applies", lock_reason: null, pickable: true });
  }
  return recount(targets);
}
// Greys the file rows of one layer under every level.
function grey(targets, layer, reason = "not_editable", names = null) {
  for (const level of targets.levels) {
    if (names && !names.includes(level.level)) continue;
    const f = level.files.find((x) => x.layer === layer);
    if (f) Object.assign(f, { target: null, op: null, effect: null, lock_reason: reason, pickable: false });
    if (level.preselect && f && level.preselect === (targetOf(targets, layer) || {}).target) level.preselect = null;
  }
  return recount(targets);
}
// A settings payload with Claude Code's default added below the winner, as the real one has.
function withDefault(settings) {
  const out = clone(settings);
  const row = out.rows.find((r) => r.agent === "@main" && r.setting === "effortLevel");
  out.entries.push({ key: "effortLevel", scope: "main", value: "medium", layer: "default", file: null, status: "default", reason: "r", rule_ids: [], line: null });
  row.entries.push(out.entries.length - 1);
  return out;
}
// Makes one level unsaveable: every row under it is off.
function shut(targets, name) {
  for (const f of levelOf(targets, name).files) Object.assign(f, { target: null, op: null, effect: null, lock_reason: f.lock_reason, pickable: false });
  levelOf(targets, name).preselect = null;
  return recount(targets);
}
// Three files that all have a line: the local file is a symbolic link (no preselect), the project and user files are
// open. No level preselects, and a press on a row is the only way to pick one.
function trio() {
  const targets = clone(S.start.targets);
  const proj = { target: "t-proj", ref: "[\"@main\",\"effortLevel\",\"project\",\"project/.claude/settings.json\",\"effortLevel\"]", layer: "project", file_display: "project/.claude/settings.json", line: 3, current_value: "high", status: "overridden", shared: true, in_effect: false };
  const usr = { target: "t-user", ref: "[\"@main\",\"effortLevel\",\"user\",\"config/settings.json\",\"effortLevel\"]", layer: "user", file_display: "config/settings.json", line: 4, current_value: "xhigh", status: "ignored", shared: false, in_effect: false };
  targets.targets = [targets.targets[0], proj, usr];
  const local = rowOfFiles(targets, "local");
  Object.assign(local, { state: "locked", lock_reason: "symlink", target: null, value: "low" });
  Object.assign(rowOfFiles(targets, "project"), { state: "has_line", line: 3, value: "high", status: "overridden", target: "t-proj", shared: true, lock_reason: null });
  Object.assign(rowOfFiles(targets, "user"), { state: "has_line", line: 4, value: "xhigh", status: "ignored", target: "t-user", lock_reason: null });
  for (const level of targets.levels) {
    if (level.result === "now") continue;
    level.preselect = null;
    Object.assign(level.files.find((f) => f.layer === "local"), { target: null, op: null, effect: null, lock_reason: "symlink", pickable: false });
  }
  open(targets, "project", ["medium", "high", "xhigh"]);
  open(targets, "user", ["medium", "high", "xhigh"]);
  for (const name of ["medium", "high", "xhigh"]) fileOf(targets, name, "project").effect = "wont_apply";
  return targets;
}
// The same three files, with the local file open and preselected under the three other levels.
function trioLocal() {
  const targets = trio();
  open(targets, "local", ["medium", "high", "xhigh"]);
  Object.assign(rowOfFiles(targets, "local"), { state: "has_line", lock_reason: null, target: targetOf(targets, "local").target });
  for (const name of ["medium", "high", "xhigh"]) levelOf(targets, name).preselect = targetOf(targets, "local").target;
  return targets;
}
// What the server answers with edits off: no targets, no target ids, no save flags, and only now or offered levels.
function offAnswer(targets) {
  const out = clone(targets);
  out.enabled = false;
  delete out.targets;
  delete out.blocked;
  delete out.saveable;
  out.files = out.files.map(({ target, ...rest }) => rest);
  out.levels = out.levels.map((l) => ({ level: l.level, result: l.result === "now" ? "now" : "offered" }));
  return out;
}
const previewsOf = (m) => async (target, v) => ok(m.previews.project[v]);
const saveFlow = () => ({
  preview: async (t, v) => ok(S.previews[v]),
  save: async () => ({ ...ok(S.save), after: S.after_save }),
  undo: async () => ({ ...ok(S.undo), after: S.after_undo }),
});
// A preview of the base file with a warning of the given status on it, the way the project row would carry one.
const WARNED = real("overridden").previews.project.high.warning;
const warned = (over = {}) => {
  const pv = clone(S.previews.high);
  pv.warning = { ...clone(WARNED), ...over };
  return pv;
};

// ---------------------------------------------------------------- pure rules

const NAMES = ["low", "medium", "high", "xhigh"];

test("pickerState: at rest the running level is checked and every level is on", () => {
  assert.deepEqual(pickMod.pickerState(NAMES, "medium", null, "ready", {}), { checked: "medium", disabled: [] });
  assert.deepEqual(pickMod.pickerState(NAMES, "medium", undefined, "ready"), { checked: "medium", disabled: [] });
  assert.deepEqual(pickMod.pickerState(NAMES, null, null, "ready", {}), { checked: null, disabled: [] }, "no level runs");
  const rows = NAMES.map((level) => ({ level }));
  assert.deepEqual(pickMod.pickerState(rows, "medium", null, "ready", {}), { checked: "medium", disabled: [] }, "level rows work too");
});

test("pickerState: a level a cap holds with nothing to save is off at rest and while another is chosen", () => {
  const rows = [
    { level: "low", result: "now", saveable: false, limits: [] },
    { level: "medium", result: "offered", saveable: true, limits: [] },
    { level: "high", result: "stopped", saveable: false, limits: [{ kind: "cap" }] },
    { level: "xhigh", result: "stopped", saveable: true, limits: [{ kind: "cap" }] },
    { level: "max", result: "stopped", saveable: false, limits: [{ kind: "model" }] },
  ];
  assert.deepEqual(pickMod.pickerState(rows, "low", null, "ready", {}), { checked: "low", disabled: ["high"] });
  assert.deepEqual(pickMod.pickerState(rows, "low", "medium", "ready", {}), { checked: "medium", disabled: ["high", "low"] });
});

test("rest: a cap note names who caps what from the layer, and says effort when no model is set", () => {
  const w = worldData("nomodel_cap");
  const a = app({ data: w });
  const cap = w.targets.levels.flatMap((l) => l.limits).find((l) => l.kind === "cap");
  const who = { project: STRINGS.ed_cap_who_project, local: STRINGS.ed_cap_who_project, user: STRINGS.ed_cap_who_user, managed: STRINGS.ed_cap_who_managed }[cap.layer] || STRINGS.ed_cap_who_other;
  assert.ok(noteTexts(a.body())[1].startsWith(who + " caps " + STRINGS.ed_cap_what_effort + " at " + cap.value + " in "));
  for (const [layer, word] of [["managed", STRINGS.ed_cap_who_managed], ["local", STRINGS.ed_cap_who_project], ["flag", STRINGS.ed_cap_who_other]]) {
    const data = worldData("nomodel_cap");
    for (const l of data.targets.levels) for (const x of l.limits) if (x.kind === "cap") x.layer = layer;
    assert.ok(noteTexts(app({ data }).body())[1].startsWith(word + " caps "), layer);
  }
});

test("pickerState: a chosen level is checked and the running level is off, so arrows and presses skip it", () => {
  assert.deepEqual(pickMod.pickerState(NAMES, "medium", "high", "ready", {}), { checked: "high", disabled: ["medium"] });
  assert.deepEqual(pickMod.pickerState(NAMES, null, "high", "ready", {}), { checked: "high", disabled: [] });
  assert.deepEqual(pickMod.pickerState(NAMES, "medium", "medium", "ready", {}), { checked: "medium", disabled: [] }, "the running level chosen is rest");
});

test("pickerState: a mode that isn't ready, a project lock or nothing to save turns every level off with the running one checked", () => {
  const all = NAMES.slice();
  for (const mode of ["off", "locked", null, undefined]) {
    assert.deepEqual(pickMod.pickerState(NAMES, "medium", null, mode, {}), { checked: "medium", disabled: all }, String(mode));
    assert.deepEqual(pickMod.pickerState(NAMES, "medium", "high", mode, {}), { checked: "medium", disabled: all }, "a chosen level can't outlive the mode " + mode);
  }
  assert.deepEqual(pickMod.pickerState(NAMES, "medium", null, "ready", { projectLock: "not_repo_root" }), { checked: "medium", disabled: all });
  assert.deepEqual(pickMod.pickerState(NAMES, "medium", "high", "ready", { projectLock: "not_repo_root" }), { checked: "medium", disabled: all });
  assert.deepEqual(pickMod.pickerState(NAMES, "medium", null, "ready", { saveable: false }), { checked: "medium", disabled: all });
});

test("pickerState: busy turns every level off and leaves the checked one where it is", () => {
  const all = NAMES.slice();
  assert.deepEqual(pickMod.pickerState(NAMES, "medium", "high", "ready", { busy: true }), { checked: "high", disabled: all });
  assert.deepEqual(pickMod.pickerState(NAMES, "medium", null, "ready", { busy: true }), { checked: "medium", disabled: all });
});

const LV = { saveable: true, limits: [] };
const base_ = { mode: "ready", projectLock: null, saveable: true, level: "high", row: "local", levelRow: LV };

test("railCase: each case, and the order the first match wins in", () => {
  const c = (over) => pickMod.railCase({ ...base_, ...over });
  assert.equal(c({}), "review");
  assert.equal(c({ row: null }), "pick_file");
  assert.equal(c({ level: null, row: null, levelRow: null }), "rest");
  assert.equal(c({ levelRow: { saveable: false, limits: [{ kind: "cap" }] } }), "stop");
  assert.equal(c({ levelRow: { saveable: false, limits: [{ kind: "model" }] } }), "stop");
  assert.equal(c({ levelRow: { saveable: false, limits: [{ kind: "winner" }] } }), "nothing_level");
  assert.equal(c({ levelRow: { saveable: false, limits: [{ kind: "model_unknown" }] } }), "nothing_level");
  assert.equal(c({ levelRow: { saveable: false, limits: [] } }), "nothing_level");
  assert.equal(c({ levelRow: { saveable: false } }), "nothing_level", "a level with no limits list");
  assert.equal(c({ saveable: false }), "nothing_project");
  assert.equal(c({ saveable: false, level: null, row: null, levelRow: null }), "nothing_project", "before a level is chosen too");
  assert.equal(c({ mode: "off" }), "off");
  assert.equal(c({ mode: "locked" }), "locked");
  assert.equal(c({ projectLock: "not_repo_root" }), "project_lock");
  assert.equal(c({ mode: null }), "rest", "no mode, nothing to say");
});

test("railCase: a project lock beats every mode, and off and locked beat the saveable rules", () => {
  const c = (over) => pickMod.railCase({ ...base_, ...over });
  for (const mode of ["off", "locked", "ready", null]) assert.equal(c({ mode, projectLock: "not_repo_root" }), "project_lock", String(mode));
  assert.equal(c({ mode: "off", saveable: false }), "off");
  assert.equal(c({ mode: "locked", saveable: false }), "locked");
  assert.equal(c({ mode: "off", level: null, row: null }), "off");
  assert.equal(c({ saveable: false, projectLock: null, levelRow: LV }), "nothing_project", "the project rule beats a saveable level");
});

test("settleRow: the current row stays while that level's row is pickable", () => {
  const lv = { preselect: "t-local", files: [{ layer: "local", target: "t-local", pickable: true }, { layer: "project", target: "t-proj", pickable: true }, { layer: "user", target: null, pickable: false }] };
  assert.equal(pickMod.settleRow(lv, "project"), "project");
  assert.equal(pickMod.settleRow(lv, "local"), "local");
});

test("settleRow: a row that is gone falls back to the preselect, else to nothing, never to another shared row", () => {
  const lv = { preselect: "t-local", files: [{ layer: "local", target: "t-local", pickable: true }, { layer: "project", target: null, pickable: false }, { layer: "user", target: "t-user", pickable: true }] };
  assert.equal(pickMod.settleRow(lv, "project"), "local", "a cleared project row lands on the local file");
  assert.equal(pickMod.settleRow(lv, null), "local");
  assert.equal(pickMod.settleRow(lv, "elsewhere"), "local");
  const none = { preselect: null, files: [{ layer: "local", target: null, pickable: false }, { layer: "project", target: null, pickable: false }, { layer: "user", target: "t-user", pickable: true }] };
  assert.equal(pickMod.settleRow(none, "project"), null, "a cleared project row lands on nothing, not on the user file");
  assert.equal(pickMod.settleRow(none, null), null);
  const shared = { preselect: null, files: [{ layer: "local", target: null, pickable: false }, { layer: "project", target: "t-proj", pickable: true }] };
  assert.equal(pickMod.settleRow(shared, "user"), null, "a project row that is open is not taken on its own");
  assert.equal(pickMod.settleRow(null, "local"), null);
  assert.equal(pickMod.settleRow({ preselect: "t-gone", files: [] }, "local"), null);
});

// ---------------------------------------------------------------- the page at rest

test("rest: the Effort body draws Run at, the four levels with the running one checked, and the rows, with no preview call", () => {
  const a = app({ data: baseData() });
  assert.deepEqual(levelInputs(a.root).map((r) => r.value), ["low", "medium", "high", "xhigh"]);
  assert.equal(a.log.preview.length, 0);
  const run = byClass(a.body(), "s4-run")[0];
  assert.equal(text(byClass(run, "s4-lab")[0]), STRINGS.run_at);
  const group = byClass(a.root, "p2-segs")[0];
  assert.equal(group.getAttribute("role"), "radiogroup");
  assert.equal(group.getAttribute("aria-label"), STRINGS.ed_level_group_sr);
  assert.deepEqual(byClass(group, "p2-sn").map(text), [STRINGS.ed_seg_now, "", "", ""]);
  assert.ok(byClass(group, "p2-sn").every((n) => n.textContent.length > 0), "the empty note is a non-breaking space");
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["low"]);
  assert.ok(levelInputs(a.root).every((r) => !off(r)), "every level is on, the running one too");
  assert.ok(hasClass(rowOf(lvl(a.root, "low")), "s6-now"));
  assert.equal(byClass(a.root, "s6-on").length, 0);
  assert.equal(byClass(a.root, "is-off").length, 0);
  assert.equal(anyKey(a.root), false);
});

test("rest: the rows are plain divs in a group, in the order of the files, with the default outside the box", () => {
  const w = real("shell");
  const a = app({ data: { settings: withDefault(w.settings), targets: w.targets, history: w.history } });
  const rows = byClass(a.root, "s6-rows")[0];
  assert.equal(rows.getAttribute("role"), "group");
  assert.equal(rows.getAttribute("aria-label"), STRINGS.where_rest);
  assert.equal(hasClass(rows, "is-live"), false);
  assert.equal(liveRows(a.root).length, 0);
  assert.equal(rowInputs(a.root).length, 0);
  const names = plainRows(rows).map((r) => text(byClass(r, "s4-ln")[0]));
  assert.deepEqual(names.slice(-3), [STRINGS.place_local, STRINGS.place_project, STRINGS.place_user]);
  assert.equal(names[0], STRINGS.place_shell, "the shell comes above the files, as a plain row");
  const files = plainRows(rows).slice(-3);
  assert.deepEqual(files.map((r) => text(byClass(r, "s4-f")[0])), [
    T("where_no_file", { file: "settings.local.json" }), "settings.json, line 2", T("where_no_line", { file: "config/settings.json" })]);
  assert.deepEqual(files.map((r) => text(byClass(r, "s4-none")[0] || { textContent: "" })), [STRINGS.where_not_set, "", STRINGS.where_not_set]);
  assert.deepEqual(files.map((r) => byClass(r, "s6-act").length), [0, 0, 0], "a resting row has nothing in its third cell");
  assert.equal(text(byClass(files[1], "s4-v")[0]), "low");
  assert.equal(byClass(files[1], "st-overridden").length, 1);
  const tail = byClass(a.root, "s6-def")[0];
  assert.equal(hasClass(tail.parentNode, "s6-rows"), false);
  assert.equal(text(byClass(tail, "s4-ln")[0]), STRINGS.place_default);
  assert.equal(text(byClass(tail, "s4-none")[0]), T("where_not_used", { value: "medium" }), "a default that doesn't win is not used");
  assert.equal(text(byClass(a.root, "s4-beyond")[0]), STRINGS.where_beyond);
});

test("rest: a default that wins shows its value and chip", () => {
  const settings = clone(S.start.settings);
  const row = settings.rows.find((r) => r.agent === "@main" && r.setting === "effortLevel");
  settings.entries = [{ key: "effortLevel", scope: "main", value: "medium", layer: "default", file: null, status: "default", reason: "r", rule_ids: [], line: null }];
  row.entries = [0];
  const b = app({ data: baseData({ settings }) });
  const tail = byClass(b.root, "s6-def")[0];
  assert.equal(text(byClass(tail, "s4-v")[0]), "medium");
  assert.equal(byClass(tail, "st-default").length, 1);
  assert.equal(byClass(tail, "s4-none").length, 0);
});

test("rest: the rail says why, and nothing else, and the foot is empty", () => {
  const a = app({ data: baseData() });
  assert.equal(text(byClass(a.rail(), "s4-rh")[0]), STRINGS.why_h);
  assert.equal(byClass(a.rail(), "s4-note").length, 0);
  assert.equal(byClass(a.rail(), "p2-df").length, 0);
  assert.equal(buttons(a.root).length, 0);
  assert.equal(strips(a.root).length, 0, "the history is empty");
});

test("page: the body, the rail and the foot sit in the panes, and a page without an edit session draws as before", () => {
  const a = app({ data: baseData() });
  const panes = byClass(a.root, "s5-w")[0];
  assert.deepEqual(panes.childNodes.map((n) => n.getAttribute("class")), ["s4-body", "s4-rail"]);
  const body = panes.childNodes[0];
  assert.equal(body.getAttribute("data-slot"), "body");
  assert.equal(body.childNodes[0], a.body());
  const aside = panes.childNodes[1];
  assert.equal(aside.childNodes[0], a.rail());
  assert.equal(hasClass(aside.childNodes[1], "s4-rf"), true);
  assert.equal(aside.childNodes[1].getAttribute("data-slot"), "foot");
  assert.equal(aside.childNodes[1].childNodes[0], a.foot());
  assert.deepEqual(a.foot().childNodes.map((n) => n.getAttribute("data-edit")), ["pick", "strip"]);
  const none = app({ mode: null, data: baseData() });
  assert.equal(slotOf(none.root, "body"), null);
  assert.equal(slotOf(none.root, "rail"), null);
  assert.equal(levelInputs(none.root).length + rowInputs(none.root).length, 0);
  assert.equal(byClass(none.root, "s4-body")[0].childNodes.length, 3, "Effort's body is the read-only frame without a session");
  assert.equal(text(byClass(none.root, "s4-lab")[0]), STRINGS.f_effort);
  assert.equal(text(byClass(none.root, "s4-rh")[0]), STRINGS.why_h);
  assert.equal(byClass(none.root, "s4-rf")[0].childNodes.length, 0);
});

test("page: a cell that isn't Effort draws its read-only frame and the plain rail, in every mode", () => {
  for (const mode of ["off", "locked", "ready"]) {
    const a = app({ mode, setting: "model", data: baseData() });
    assert.equal(levelInputs(a.root).length + rowInputs(a.root).length, 0, mode);
    assert.equal(a.root.textContent.includes(STRINGS.ed_off) || a.root.textContent.includes(STRINGS.ed_locked), false, mode);
    assert.equal(byClass(a.rail(), "s4-note").length, 0, mode);
    assert.equal(byClass(a.root, "s4-lock").length, 1, mode);
    assert.equal(strips(a.root).length, 0, mode);
  }
});

test("rest: the level notes are now, over cap, can't reach and none", () => {
  const cap = worldData("nomodel_cap");
  const a = app({ data: cap });
  assert.deepEqual(byClass(a.root, "p2-sn").map(text), [STRINGS.ed_seg_now, STRINGS.ed_seg_over_cap, STRINGS.ed_seg_over_cap, STRINGS.ed_seg_over_cap]);
  const managed = app({ data: worldData("managed_cap") });
  assert.deepEqual(byClass(managed.root, "p2-sn").map(text), [STRINGS.ed_seg_now, "", STRINGS.ed_seg_over_cap, STRINGS.ed_seg_over_cap], "a managed cap is a cap too");
  const shell = app({ data: worldData("shell") });
  assert.deepEqual(byClass(shell.root, "p2-sn").map(text), [STRINGS.ed_seg_stopped, STRINGS.ed_seg_stopped, STRINGS.ed_seg_now, STRINGS.ed_seg_stopped]);
  const model = app({ data: worldData("model_limit") });
  assert.deepEqual(byClass(model.root, "p2-sn").map(text), [STRINGS.ed_seg_now, "", "", ""], "a stopped level that can be saved has no note");
  const open_ = clone(model.st.targets.data);
  shut(open_, "xhigh");
  const shut_ = app({ data: { ...worldData("model_limit"), targets: open_ } });
  assert.deepEqual(byClass(shut_.root, "p2-sn").map(text), [STRINGS.ed_seg_now, "", "", STRINGS.ed_seg_stopped], "a stopped level that can't be saved says can't reach");
});

test("rest: the cap line names who caps what, then says to change the cap by hand, and a level a cap only lowers stays pressable", () => {
  const lowered = worldData("lowered");
  const a = app({ data: lowered });
  const cap = lowered.targets.levels.find((l) => l.limits.length).limits[0];
  assert.equal(cap.kind, "cap");
  assert.equal(cap.layer, "user");
  assert.deepEqual(noteTexts(a.body()), [T("ed_limit_cap", { who: STRINGS.ed_cap_who_user, what: "Sonnet 5.5", value: cap.value, file: "config/settings.json", line: cap.line }), STRINGS.ed_lock_cap_later]);
  assert.deepEqual(byClass(byClass(a.body(), "s4-note")[0], "pa").map(text), ["config/settings.json"]);
  assert.equal(levelInputs(a.root).filter(off).length, 0, "no level is off at rest");
  assert.deepEqual(noteTexts(app({ data: baseData() }).body()), [], "no cap, no line");
});

test("rest: a target answer that isn't there draws nothing, and a failed one draws the network line", () => {
  const none = app({ data: { settings: S.start.settings, targets: null, history: S.start.history } });
  assert.equal(levelInputs(none.root).length, 0);
  assert.equal(none.body().childNodes.length, 0);
  assert.equal(text(byClass(none.rail(), "s4-rh")[0]), STRINGS.why_h);
  const failed = app({ data: { settings: S.start.settings, targets: { fail: true }, history: S.start.history } });
  assert.equal(levelInputs(failed.root).length, 0);
  assert.deepEqual(byClass(failed.body(), "p2-hint").map(text), [STRINGS.ed_err_network]);
});

test("rest: a targets answer for another project is not drawn", () => {
  const a = app({ data: baseData() });
  assert.equal(levelInputs(a.root).length, 4);
  a.st.targets = { ok: true, status: 200, data: { ...S.start.targets, project: a.key + "-other" } };
  a.draw();
  assert.equal(levelInputs(a.root).length, 0, "the rows of another project are never drawn");
  assert.equal(a.body().childNodes.length, 0);
});

test("levels_state no_effort_support: the card says so in every mode, with no picker and no rows", () => {
  const h = real("haiku");
  assert.equal(h.targets.levels_state, "no_effort_support");
  for (const mode of ["ready", "locked", "off"]) {
    const targets = mode === "off" ? offAnswer(h.targets) : h.targets;
    const a = app({ mode, data: { settings: h.settings, targets, history: h.history } });
    assert.equal(levelInputs(a.root).length + rowInputs(a.root).length, 0, mode);
    assert.deepEqual(byClass(a.body(), "p2-lock").map(text), [STRINGS.ed_levels_no_support], mode);
    assert.equal(text(byClass(a.body(), "cd-h")[0]), STRINGS.ed_card);
    assert.equal(byClass(a.body(), "p2-head").length, 0, "runs_as is null, so no head");
    assert.equal(byClass(a.rail(), "p2-df").length, 0);
  }
  const withRuns = clone(h.targets);
  withRuns.runs_as = "high";
  const b = app({ data: { settings: h.settings, targets: withRuns, history: h.history } });
  assert.deepEqual(byClass(b.root, "p2-head").map(text), ["high"]);
  assert.equal(noteTexts(b.rail()).includes(STRINGS.ed_nosave_project), false, "a model with no levels is not a project that can't save");
});

test("levels_state model_unknown: the note sits under the radios and the group points at it", () => {
  const m = worldData("nomodel_project");
  const a = app({ data: m });
  assert.equal(m.targets.levels_state, "model_unknown");
  const note = byClass(a.body(), "s4-note").find((n) => text(n) === STRINGS.ed_levels_model_unknown);
  assert.ok(note);
  assert.equal(byClass(a.root, "p2-segs")[0].getAttribute("aria-describedby"), note.getAttribute("id"));
  assert.equal(byClass(app({ data: baseData() }).root, "p2-segs")[0].getAttribute("aria-describedby"), null);
});

// ---------------------------------------------------------------- off, locked and the project lock

test("off: the picker is off, the rows are plain from files[], no review, and one rail line", () => {
  const a = app({ mode: "off", data: baseData({ targets: offAnswer(S.start.targets) }) });
  assert.equal(levelInputs(a.root).length, 4);
  assert.ok(levelInputs(a.root).every(off), "every level is off");
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["low"], "the running level is checked");
  assert.deepEqual(byClass(a.root, "p2-sn").map(text), [STRINGS.ed_seg_now, "", "", ""], "offered levels carry no note");
  assert.equal(plainRows(a.root).filter((r) => !hasClass(r, "s6-def")).length, 3);
  assert.equal(liveRows(a.root).length + rowInputs(a.root).length, 0);
  assert.equal(byClass(a.root, "p2-df").length + byClass(a.root, "p2-df").length, 0);
  assert.deepEqual(noteTexts(a.rail()), [STRINGS.ed_off]);
  assert.match(text(byClass(a.rail(), "s4-note")[0]), /--allow-edits/);
  assert.equal(buttons(a.root).length, 0);
  assert.equal(strips(a.root).length, 0);
  assert.equal(a.log.preview.length, 0);
  lvl(a.root, "high").dispatch("change");
  assert.equal(a.log.preview.length, 0, "a press on an off level does nothing");
});

test("locked: the picker is off, the rows are plain, and the rail says to open the printed link", () => {
  const sh = real("shell");
  const a = app({ mode: "locked", data: { settings: sh.settings, targets: sh.targets, history: real("changed_since_save").history } });
  assert.ok(levelInputs(a.root).every(off));
  assert.deepEqual(noteTexts(a.rail()), [STRINGS.ed_locked]);
  assert.match(STRINGS.ed_locked, /printed in the terminal/);
  assert.equal(liveRows(a.root).length, 0);
  assert.equal(buttons(a.root).length, 0);
  assert.equal(strips(a.root).length, 0, "the strip is gone");
  assert.equal(byClass(a.root, "p2-df").length, 0);
});

test("project lock: the picker is off and the one rail line is the lock, ahead of the off and locked lines, in every mode", () => {
  for (const mode of ["off", "locked", "ready"]) {
    const targets = clone(S.start.targets);
    targets.project_lock = "not_repo_root";
    const a = app({ mode, data: baseData({ targets: mode === "off" ? offAnswer(targets) : targets }) });
    assert.ok(levelInputs(a.root).every(off), mode);
    assert.deepEqual(noteTexts(a.rail()), [STRINGS.ed_lock_not_repo_root], mode);
    assert.equal(a.root.textContent.includes(STRINGS.ed_off) || a.root.textContent.includes(STRINGS.ed_locked), false, mode);
    assert.equal(liveRows(a.root).length + byClass(a.root, "p2-df").length, 0, mode);
    assert.equal(plainRows(a.root).filter((r) => !hasClass(r, "s6-def")).length, 3, mode);
    assert.equal(buttons(a.root).length, 0, mode);
  }
});

test("project lock: a press on a level does nothing, and no preview goes out", () => {
  const targets = clone(S.start.targets);
  targets.project_lock = "not_repo_root";
  const a = app({ data: baseData({ targets }) });
  lvl(a.root, "high").dispatch("change");
  assert.equal(a.log.preview.length, 0);
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["low"]);
});

test("nothing to save at project level: the picker is off and the rail says so, with the first lock and no Cancel", () => {
  const w = worldData("nomodel_cap");
  assert.equal(w.targets.saveable, false);
  const a = app({ data: w });
  assert.ok(levelInputs(a.root).every(off));
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["low"]);
  assert.deepEqual(noteTexts(a.rail()), [STRINGS.ed_nosave_project, STRINGS.ed_lock_cap_later]);
  assert.equal(buttons(a.root).length, 0, "nothing is chosen, so there is no Cancel");
  assert.equal(liveRows(a.root).length, 0);
  const plain = clone(w.targets);
  for (const level of plain.levels) level.limits = [];
  const b = app({ data: { ...w, targets: plain } });
  assert.deepEqual(noteTexts(b.rail()), [STRINGS.ed_nosave_project], "no limit, no lock line");
});

test("a-shell: a value your shell sets draws the lock line over the disabled picker, and the rail is the plain rest rail", () => {
  const w = worldData("shell");
  assert.equal(w.targets.saveable, false);
  const first = w.targets.levels.flatMap((l) => l.limits).find((l) => l && l.lock_reason);
  assert.equal(first.lock_reason, "env_shell", "the first limit found is the shell's");
  const a = app({ data: w });
  const lock = byClass(a.body(), "s4-lock");
  assert.equal(lock.length, 1);
  assert.equal(text(lock[0]), STRINGS.ed_lock_env_shell);
  assert.equal(byClass(lock[0], "ic").length, 1, "the lock icon");
  assert.ok(order(a.body(), lock[0]) < order(a.body(), byClass(a.body(), "s4-run")[0]), "the line sits above the picker");
  assert.ok(levelInputs(a.root).every(off), "the picker is off");
  assert.equal(text(byClass(a.rail(), "s4-rh")[0]), STRINGS.why_h, "the plain rest rail");
  assert.equal(byClass(a.rail(), "s4-note").length, 0, "no note, because there is no change in progress");
  assert.equal(buttons(a.root).length, 0);
  // Another lock reason keeps the old words in the rail and no lock line in the body.
  const cap = app({ data: worldData("nomodel_cap") });
  assert.equal(byClass(cap.body(), "s4-lock").length, 0);
  assert.deepEqual(noteTexts(cap.rail()), [STRINGS.ed_nosave_project, STRINGS.ed_lock_cap_later]);
});

test("nothing to save at this level: the rail says so with the winner's line and Cancel, and Cancel goes back", async () => {
  const w = worldData("lowered");
  const targets = clone(w.targets);
  shut(targets, "high");
  levelOf(targets, "high").limits = [{ kind: "winner", value: "xhigh", layer: "user", file_display: "config/settings.json", line: 3, editable: false, target: null, lock_reason: "env_shell" }];
  const a = app({ data: { ...w, targets }, backend: { preview: async () => { throw new Error("no preview"); } } });
  await a.choose("high");
  assert.equal(a.log.preview.length, 0);
  const warn = nts(a.rail(), "warn")[0];
  assert.equal(text(byClass(warn, "p2-nt-h")[0]), "▲" + T("ed_nosave_level", { level: "high" }));
  assert.deepEqual(tag(warn, "p").map(text), [T("ed_limit_winner", { value: "xhigh", file: "config/settings.json", line: 3 }), STRINGS.ed_lock_env_shell]);
  assert.deepEqual(tag(warn, "button").map(text), [STRINGS.ed_cancel]);
  assert.equal(byClass(a.root, "p2-df").length, 0);
  assert.equal(liveRows(a.root).length, 0, "the rows stay at rest");
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["high"]);
  assert.ok(off(lvl(a.root, "low")), "the running level is off while a level is chosen");
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.equal(notes(a.root).length, 0);
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["low"]);
  assert.equal(FElement.focused, lvl(a.root, "low"), "focus goes back to the checked level");
});

// ---------------------------------------------------------------- picking a level

test("pick: a level with a local preselect opens the review in the rail and the live rows, with one preview call", async () => {
  const a = app({ data: baseData(), backend: { preview: async (target, level) => ok(S.previews[level]) } });
  await a.choose("high");
  const level = levelOf(S.start.targets, "high");
  assert.equal(level.preselect, S.target);
  assert.deepEqual(a.log.preview, [[level.preselect, "high"]]);
  // the picker
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["high"]);
  assert.deepEqual(levelInputs(a.root).filter(off).map((r) => r.value), ["low"], "the running level is off, with its word kept");
  assert.deepEqual(byClass(a.root, "p2-sn").map(text), [STRINGS.ed_seg_now, "", "", ""]);
  assert.ok(hasClass(rowOf(lvl(a.root, "low")), "s6-now"));
  assert.ok(hasClass(rowOf(lvl(a.root, "high")), "s6-on"));
  // the rows are live
  const rows = byClass(a.root, "s6-rows")[0];
  assert.ok(hasClass(rows, "is-live"));
  assert.equal(rows.getAttribute("role"), "radiogroup");
  assert.equal(rows.getAttribute("aria-label"), STRINGS.where_live);
  assert.equal(text(byClass(a.root, "s6-lvs")[0].childNodes[0]), STRINGS.where_live);
  assert.deepEqual(liveRows(a.root).map((r) => text(byClass(r, "s4-ln")[0])), [STRINGS.place_local, STRINGS.place_project, STRINGS.place_user]);
  assert.deepEqual(checkedOf(rowInputs(a.root)), ["local"]);
  assert.deepEqual(rowInputs(a.root).map((r) => off(r)), [false, true, true]);
  const picked = rowOf(rowIn(a.root, "local"));
  assert.ok(hasClass(picked, "is-pick"));
  assert.equal(text(byClass(picked, "s6-act")[0]), T("row_edits", { n: 2 }));
  assert.equal(byClass(picked, "ic").length, 1, "the check mark");
  assert.deepEqual(liveRows(a.root).slice(1).map((r) => hasClass(r, "is-no")), [true, true]);
  assert.deepEqual(liveRows(a.root).slice(1).map((r) => text(byClass(r, "s6-act")[0])), [STRINGS.ed_row_lock_create_later, STRINGS.ed_row_lock_add_later]);
  assert.ok(liveRows(a.root).slice(1).every((r) => byClass(r, "ic").length === 1), "a lock icon on a locked row");
  // the review is in the rail, as the board a-norm draws it
  const rb = byClass(a.rail(), "s4-rb")[0];
  assert.ok(rb, "the review is the rail's body");
  assert.equal(byClass(a.root, "s4-rb").length, 1);
  assert.equal(text(byClass(rb, "s4-rh")[0]), STRINGS.review_h);
  assert.deepEqual(bigs(a.root), ["low", "→", "high"]);
  const chg = byClass(rb, "s4-chg")[0];
  assert.deepEqual(tag(chg, "span").map((n) => n.getAttribute("class") || n.getAttribute("aria-hidden")), ["s4-was", "true", "sr", "s4-to"]);
  assert.equal(text(byClass(chg, "sr")[0]), STRINGS.ed_to);
  assert.equal(headNote(a.root), STRINGS.ed_runs);
  const dl = byClass(rb, "s4-dl")[0];
  const pairs = tag(dl, "div").map((row) => [text(tag(row, "dt")[0]), text(tag(row, "dd")[0])]);
  assert.deepEqual(pairs.map((p) => p[0]), [STRINGS.review_after, STRINGS.review_comes]);
  assert.match(pairs[0][1], /^high\s*.*In effect/);
  assert.equal(pairs[1][1], STRINGS.place_local);
  assert.equal(byClass(dl, "st-in_effect").length, 1, "the winner's chip");
  assert.equal(byClass(a.root, "p2-tbl").length, 0, "the trail table is gone");
  // the diff
  assert.equal(text(byClass(rb, "s4-sub")[0]), T("ed_card_line", { file: "settings.local.json", line: 2 }));
  assert.ok(order(rb, byClass(rb, "s4-sub")[0]) < order(rb, byClass(rb, "p2-df")[0]), "the file heading sits over the diff");
  const figure = byClass(a.root, "p2-df")[0];
  assert.equal(text(byClass(figure, "pa")[0]), S.previews.high.diff.file_display);
  const ol = tag(figure, "ol");
  assert.equal(ol.length, S.previews.high.diff.hunks.length);
  assert.equal(ol[0].getAttribute("aria-label"), T("ed_diff_sr", { file: "settings.local.json" }));
  const lines = tag(ol[0], "li");
  assert.equal(lines.length, S.previews.high.diff.hunks[0].lines.length);
  const del = lines.find((l) => hasClass(l, "p2-del"));
  const add = lines.find((l) => hasClass(l, "p2-add"));
  assert.equal(tag(del, "code")[0].textContent, '  "effortLevel": "low"');
  assert.equal(tag(add, "code")[0].textContent, '  "effortLevel": "high"');
  assert.deepEqual(tag(del, "mark").map(text), ["low"]);
  assert.deepEqual(tag(add, "mark").map(text), ["high"]);
  assert.equal(text(byClass(del, "p2-n")[0]), "2");
  assert.equal(text(byClass(del, "p2-m")[0]), "−");
  assert.equal(text(byClass(add, "p2-m")[0]), "+");
  assert.equal(text(byClass(del, "sr")[0]), STRINGS.ed_diff_del_sr);
  assert.equal(text(byClass(add, "sr")[0]), STRINGS.ed_diff_add_sr);
  const context = lines.find((l) => !hasClass(l, "p2-del") && !hasClass(l, "p2-add"));
  assert.equal(byClass(context, "sr").length, 0);
  assert.equal(text(byClass(context, "p2-m")[0]), "");
  // Save and Cancel are in the foot, side by side, and the rail holds none
  assert.equal(buttons(a.rail()).length, 0, "no button in the rail");
  assert.deepEqual(footTexts(a), [LOCAL_SAVE, STRINGS.ed_cancel]);
  const [save, cancelBtn] = footButtons(a);
  assert.ok(hasClass(save, "p2-pri") && hasClass(save, "s4-wide"));
  assert.ok(hasClass(cancelBtn, "s4-wide") && !hasClass(cancelBtn, "p2-pri"));
  assert.equal(save.parentNode, cancelBtn.parentNode, "side by side in one slot");
  assert.equal(text(byClass(slotOf(a.root, "pick"), "s4-hint")[0]), STRINGS.ed_nothing_yet);
  assert.equal(btn(a.root, LOCAL_SAVE) !== undefined && buttons(a.root).filter((b) => text(b) === LOCAL_SAVE).length, 1, "one Save in the page");
  assert.ok(!noteTexts(a.root).includes(STRINGS.ed_shared), "the local file is not shared");
  assert.equal(anyKey(a.root), false);
});

test("pick: the rail swaps between rest and review with no page render, and the strip's slot stays", async () => {
  const a = app({ data: afterSave(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  const stripSlot = slotOf(a.root, "strip");
  const bar = stripSlot.childNodes[0];
  assert.ok(bar, "the saved result is in the strip slot");
  const title = byClass(a.root, "ph")[0];
  const rail = a.rail();
  await a.choose("medium");
  assert.equal(a.rail(), rail, "the slot stays");
  assert.equal(slotOf(a.root, "strip"), stripSlot);
  assert.equal(stripSlot.childNodes.length, 0, "the last change waits while a level is chosen");
  assert.equal(byClass(a.root, "ph")[0], title);
  assert.equal(byClass(a.root, "p2-df").length, 1);
  assert.equal(a.log.draws, 1, "the page was drawn once, at the start");
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.equal(byClass(a.root, "p2-df").length, 0);
  assert.equal(text(byClass(a.rail(), "s4-rh")[0]), STRINGS.why_h);
  assert.equal(a.log.draws, 1);
});

test("pick: pressing the running level sends nothing, and a level chosen then can't be undone by it", async () => {
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  lvl(a.root, "low").dispatch("change");
  await settle();
  assert.equal(a.log.preview.length, 0);
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["low"]);
  assert.equal(byClass(a.root, "p2-df").length, 0);
  await a.choose("high");
  assert.equal(a.log.preview.length, 1);
  lvl(a.root, "low").dispatch("change"); // a press that gets past the off radio
  await settle();
  assert.equal(a.log.preview.length, 1, "no new preview");
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["high"], "the chosen level stays");
  assert.equal(byClass(a.root, "p2-df").length, 1);
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["low"], "only Cancel goes back");
});

test("pick: another level while one is chosen starts a fresh preview, and the old one is gone", async () => {
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await a.choose("high");
  await a.choose("xhigh");
  assert.deepEqual(a.log.preview.map((p) => p[1]), ["high", "xhigh"]);
  assert.deepEqual(bigs(a.root), ["low", "→", "xhigh"]);
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["xhigh"]);
});

test("pick: an older preview answer that lands after a newer pick is dropped, and Cancel drops one on its way", async () => {
  const waits = {};
  const a = app({
    data: baseData(),
    backend: { preview: (target, level) => new Promise((resolve) => { waits[level] = () => resolve(ok(S.previews[level])); }) },
  });
  lvl(a.root, "medium").dispatch("change");
  lvl(a.root, "high").dispatch("change");
  await settle();
  waits.high();
  await settle();
  waits.medium();
  await settle();
  assert.deepEqual(bigs(a.root), ["low", "→", "high"]);
  assert.equal(a.log.preview.length, 2);
  // Cancel, which is there while the preview is on its way, drops an answer on its way too.
  const b = app({ data: baseData(), backend: { preview: (t2, level) => new Promise((resolve) => { waits.late = () => resolve(ok(S.previews[level])); }) } });
  lvl(b.root, "medium").dispatch("change");
  await settle();
  assert.equal(byClass(b.root, "p2-df").length, 0, "the review is not there yet");
  btn(b.root, STRINGS.ed_cancel).click();
  await settle();
  waits.late();
  await settle();
  assert.equal(byClass(b.root, "p2-df").length, 0);
  assert.deepEqual(checkedOf(levelInputs(b.root)), ["low"]);
});

test("pick: a preview that is on its way is not asked for again when the page draws", async () => {
  let resolve;
  const a = app({ data: baseData(), backend: { preview: () => new Promise((r) => { resolve = r; }) } });
  lvl(a.root, "high").dispatch("change");
  await settle();
  a.st.targets = a.wrapT(clone(S.start.targets)); // a new targets object, so settle runs again
  a.draw();
  a.draw();
  await settle();
  assert.equal(a.log.preview.length, 1);
  resolve(ok(S.previews.high));
  await settle();
  assert.equal(byClass(a.root, "p2-df").length, 1);
});

// ---------------------------------------------------------------- picking a row

test("pick a file: a level with no preselect draws the review headline and Pick a file, Save off, and sends no preview", async () => {
  const m = worldData("project_only");
  const level = levelOf(m.targets, "high");
  assert.equal(level.result, "reachable");
  assert.equal(level.preselect, null);
  const a = app({ data: m, backend: { preview: previewsOf(m.previews ? m : real("project_only")) } });
  await a.choose("high");
  assert.deepEqual(a.log.preview, []);
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["high"]);
  // the rail
  const rail = a.rail();
  assert.equal(text(byClass(rail, "s4-rh")[0]), STRINGS.review_h);
  assert.equal(byClass(rail, "s4-rh")[0].tagName, "h2");
  const chg = byClass(rail, "s4-chg")[0];
  assert.deepEqual(chg.childNodes.map(text), ["low", "→", STRINGS.ed_to, "high"]);
  assert.equal(chg.childNodes[1].getAttribute("aria-hidden"), "true");
  assert.ok(hasClass(chg.childNodes[2], "sr"));
  assert.equal(text(byClass(rail, "s4-runs")[0]), STRINGS.ed_runs);
  assert.deepEqual(noteTexts(rail), [STRINGS.ed_pick_file]);
  assert.equal(byClass(rail, "p2-df").length + byClass(rail, "p2-df").length, 0);
  // the foot
  const foot = slotOf(a.root, "pick");
  const [save, cancel, hint] = foot.childNodes;
  assert.equal(text(save), STRINGS.ed_save_plain);
  assert.ok(off(save));
  assert.ok(hasClass(save, "p2-pri") && hasClass(save, "s4-wide"));
  assert.equal(text(cancel), STRINGS.ed_cancel);
  assert.ok(hasClass(cancel, "s4-wide") && !off(cancel));
  assert.ok(hasClass(hint, "s4-hint"));
  assert.equal(text(hint), STRINGS.ed_nothing_yet);
  // the rows: the project row is open and nothing is picked
  assert.deepEqual(checkedOf(rowInputs(a.root)), []);
  assert.deepEqual(rowInputs(a.root).map((r) => [r.value, off(r)]), [["local", true], ["project", false], ["user", true]]);
  assert.equal(byClass(a.root, "is-pick").length, 0);
  assert.equal(text(byClass(rowOf(rowIn(a.root, "project")), "s6-act")[0]), T("row_edits", { n: 2 }));
  // Cancel is in the foot and goes back
  cancel.click();
  await settle();
  assert.equal(slotOf(a.root, "pick").childNodes.length, 0);
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["low"]);
  assert.equal(FElement.focused, lvl(a.root, "low"));
});

test("pick a file: a locked local row gives no preselect, project and user stay unpicked until pressed, and a press previews only its target", async () => {
  const targets = trio();
  const pvs = real("project_only").previews.project;
  const a = app({ data: baseData({ targets }), backend: { preview: async (t, v) => ok(pvs[v]) } });
  await a.choose("medium");
  assert.deepEqual(a.log.preview, [], "no preselect, so no preview");
  assert.deepEqual(noteTexts(a.rail()), [STRINGS.ed_pick_file]);
  const local = rowOf(rowIn(a.root, "local"));
  assert.ok(off(rowIn(a.root, "local")) && hasClass(local, "is-no"));
  assert.equal(text(byClass(local, "s6-act")[0]), STRINGS.ed_row_lock_symlink);
  assert.equal(byClass(local, "ic").length, 1);
  assert.equal(text(byClass(local, "s4-f")[0]), T("file_line", { path: "settings.local.json", line: 2 }), "the line the file holds");
  assert.deepEqual(rowInputs(a.root).map(off), [true, false, false]);
  assert.deepEqual(checkedOf(rowInputs(a.root)), []);
  // the press on the project row
  await a.pickRow("project");
  assert.deepEqual(a.log.preview, [["t-proj", "medium"]], "only that target");
  assert.deepEqual(checkedOf(rowInputs(a.root)), ["project"]);
  assert.ok(hasClass(rowOf(rowIn(a.root, "project")), "is-pick"));
  assert.equal(text(byClass(rowOf(rowIn(a.root, "project")), "s6-act")[0]), T("row_edits", { n: 3 }));
  assert.equal(text(byClass(rowOf(rowIn(a.root, "user")), "s6-act")[0]), T("row_edits", { n: 4 }), "an open row that isn't picked still says what it edits");
  assert.equal(byClass(a.root, "p2-df").length, 1);
  assert.deepEqual(footTexts(a), [T("ed_save_to", { file: "settings.json" }), STRINGS.ed_cancel], "the review's Save and Cancel sit in the foot");
  assert.ok(!off(footButtons(a)[0]), "Save is on once a preview is drawn");
  // the press on the user row asks for the user target and nothing more
  await a.pickRow("user");
  assert.deepEqual(a.log.preview, [["t-proj", "medium"], ["t-user", "medium"]]);
  assert.deepEqual(checkedOf(rowInputs(a.root)), ["user"]);
});

test("pick a file: a row that can't be picked takes no press, and a press while busy does nothing", async () => {
  const targets = trio();
  const pvs = real("project_only").previews.project;
  const a = app({ data: baseData({ targets }), backend: { preview: async (t, v) => ok(pvs[v]) } });
  await a.choose("medium");
  rowIn(a.root, "local").dispatch("change");
  await settle();
  assert.deepEqual(a.log.preview, []);
  assert.deepEqual(checkedOf(rowInputs(a.root)), []);
});

test("rows: an unknown effect and a row that won't change what runs each say so in the third cell", async () => {
  const targets = trio();
  fileOf(targets, "medium", "user").effect = "unknown";
  const a = app({ data: baseData({ targets }), backend: { preview: async (t, v) => ok(real("project_only").previews.project[v]) } });
  await a.choose("medium");
  assert.equal(text(byClass(rowOf(rowIn(a.root, "user")), "s6-act")[0]), STRINGS.ed_unknown_row);
  const wont = clone(trio());
  Object.assign(fileOf(wont, "medium", "project"), { pickable: false, effect: "wont_apply" });
  const b = app({ data: baseData({ targets: recount(wont) }) });
  await b.choose("medium");
  const row = rowOf(rowIn(b.root, "project"));
  assert.equal(text(byClass(row, "s6-act")[0]), STRINGS.row_wont);
  assert.ok(hasClass(row, "is-no") && off(rowIn(b.root, "project")));
  // A lock reason with no line of its own draws nothing, and builds no key.
  const odd = trio();
  fileOf(odd, "medium", "user").lock_reason = "a_reason_nobody_knows";
  Object.assign(fileOf(odd, "medium", "user"), { pickable: false });
  const c = app({ data: baseData({ targets: recount(odd) }) });
  await c.choose("medium");
  assert.equal(byClass(rowOf(rowIn(c.root, "user")), "s6-act").length, 0);
  assert.equal(/ed_row_lock_/.test(c.root.textContent), false);
});

// ---------------------------------------------------------------- the review

test("review: a certain false level adds the hint and the headline note, and Save is on", async () => {
  const m = worldData("nomodel_project");
  const full = real("nomodel_project");
  const a = app({ data: m, backend: { preview: async (target, level) => ok(full.previews.local[level]) } });
  await a.choose("medium");
  assert.equal(levelOf(m.targets, "medium").certain, false);
  assert.ok(byClass(a.rail(), "s4-note").some((n) => text(n) === STRINGS.ed_certain_note), "the note is a rail note");
  assert.equal(headNote(a.root), T("ed_runs_uncertain", { level: "medium" }));
  const save = btn(a.root, LOCAL_SAVE);
  assert.ok(save && !off(save));
});

test("review: a preview of the project file says the file is shared", async () => {
  const targets = trio();
  const pvs = real("project_only").previews.project;
  const a = app({ data: baseData({ targets }), backend: { preview: async (t, v) => ok(pvs[v]) } });
  await a.choose("high");
  await a.pickRow("project");
  assert.deepEqual(a.log.preview, [["t-proj", "high"]]);
  assert.ok(byClass(a.rail(), "s4-note").some((n) => text(n) === STRINGS.ed_shared), "the note is a rail note");
});

test("review: pressing the project row removes the Pick a file line only, so the rail keeps a note (the e2e waits on that line by text)", async () => {
  const targets = trio();
  const pvs = real("project_only").previews.project;
  const a = app({ data: baseData({ targets }), backend: { preview: async (t, v) => ok(pvs[v]) } });
  await a.choose("high");
  assert.ok(noteTexts(a.rail()).includes(STRINGS.ed_pick_file));
  await a.pickRow("project");
  const notes = noteTexts(a.rail());
  assert.ok(!notes.includes(STRINGS.ed_pick_file), "the Pick a file line is gone");
  assert.ok(notes.includes(STRINGS.ed_shared), "the shared-file line stays");
  assert.ok(notes.length > 0, "a bare .s4-note wait would never see the rail clear");
  assert.equal(byClass(a.rail(), "s4-dl").length, 1, "the After list is drawn in the same pass as the diff");
  assert.equal(byClass(a.rail(), "p2-df").length, 1);
});

test("review: every status shows its mark glyph and its word", async () => {
  const a = app({ data: baseData(), backend: { preview: async (target, level) => ok(S.previews[level]) } });
  await a.choose("xhigh");
  const chips = byClass(byClass(a.rail(), "s4-dl")[0], "st");
  assert.ok(chips.length >= 1);
  for (const chip of chips) {
    assert.equal(byClass(chip, "mk").length, 1);
    assert.match(text(chip), /^(In effect|Lowered|Overridden|Ignored|Invalid|Default|Unknown)$/);
  }
  const marks = new Set(["✓", "▲", "✕"]);
  const b = app({ data: baseData(), backend: { preview: async () => ok(warned({ status: "overridden", in_effect_changes: false })) } });
  await b.choose("high");
  assert.ok(byClass(b.root, "p2-nt").length >= 1);
  for (const n of byClass(b.root, "p2-nt")) {
    const mk = byClass(n, "p2-mk")[0];
    assert.ok(marks.has(text(mk)));
    assert.equal(mk.getAttribute("aria-hidden"), "true");
    assert.ok(text(byClass(n, "p2-nt-h")[0]).length > 1, "a word beside the mark");
  }
});

test("review: other agents that move go under Also changes, one row for each, with their status chips", async () => {
  const pv = clone(S.previews.high);
  const line = (value, status = "in_effect") => ({ value, status, layer: "user", file: "config/settings.json", line: 3, runs_as: value });
  pv.changes.push({ agent: "reviewer", setting: "effort", before: line("xhigh"), after: line("medium", "lowered") });
  pv.changes.push({ agent: "planner", setting: "effort", before: line("low"), after: { ...line("high"), runs_as: "medium" } });
  const a = app({ data: baseData(), backend: { preview: async () => ok(pv) } });
  await a.choose("high");
  const rb = byClass(a.rail(), "s4-rb")[0];
  const sub = byClass(rb, "s4-sub").find((n) => text(n) === STRINGS.ed_also);
  assert.ok(sub, "the Also changes heading");
  const dls = byClass(rb, "s4-dl");
  assert.equal(dls.length, 2, "the winner list and the also list");
  const rows = tag(dls[1], "div");
  assert.equal(rows.length, 2);
  assert.equal(text(tag(rows[0], "dt")[0]), T("ed_also_agent", { agent: "reviewer" }));
  assert.match(text(tag(rows[0], "dd")[0]), /^xhigh.*In effect.*→.*medium.*Lowered$/);
  assert.equal(byClass(rows[0], "st").length, 2, "a chip for each side");
  assert.equal(text(tag(rows[1], "dt")[0]), T("ed_also_agent", { agent: "planner" }));
  assert.match(text(tag(rows[1], "dd")[0]), new RegExp(T("runs_as_cell", { becomes: "medium" })), "what it runs as, when that differs");
  assert.ok(order(rb, sub) > order(rb, byClass(rb, "p2-df")[0]), "it comes after the diff");
  // The main session alone adds no heading and no second list.
  const b = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await b.choose("high");
  assert.equal(byClass(b.rail(), "s4-dl").length, 1);
  assert.equal(byClass(b.rail(), "s4-sub").filter((n) => text(n) === STRINGS.ed_also).length, 0);
});

test("review: one value when runs_before equals runs_after or is null, and the was half and the arrow drop with it", async () => {
  const same = clone(S.previews.high);
  same.runs_before = "medium";
  same.runs_after = "medium";
  const a = app({ data: baseData(), backend: { preview: async () => ok(same) } });
  await a.choose("high");
  assert.deepEqual(bigs(a.root), ["medium"], "equal values show once");
  assert.equal(byClass(a.root, "s4-was").length, 0);
  assert.equal(byClass(byClass(a.root, "s4-chg")[0], "sr").length, 0);
  const unknown = clone(S.previews.high);
  unknown.runs_before = null;
  const b = app({ data: baseData(), backend: { preview: async () => ok(unknown) } });
  await b.choose("high");
  assert.deepEqual(bigs(b.root), [unknown.runs_after], "a null before shows the after alone");
  assert.equal(byClass(b.root, "s4-was").length, 0);
  // The preview's own fields decide, not the targets answer's runs_as.
  const other = clone(S.previews.high);
  other.runs_before = "xhigh";
  other.runs_after = "high";
  const c = app({ data: baseData(), backend: { preview: async () => ok(other) } });
  await c.choose("high");
  assert.deepEqual(bigs(c.root), ["xhigh", "→", "high"]);
  assert.equal(text(byClass(c.root, "s4-to")[0]), "high");
});

test("review: the other files that still lose get a note, with the comma form for the project and local places", async () => {
  const w = real("overridden");
  const a = app({ data: { settings: w.settings, targets: w.targets, history: w.history }, backend: { preview: async (t, v) => ok(w.previews.local[v]) } });
  await a.choose("high");
  const still = byClass(a.rail(), "s4-note").map(text).filter((n) => / is still /.test(n));
  assert.ok(still.length >= 1, "at least one note: " + JSON.stringify(noteTexts(a.rail())));
  const entries = (w.previews.local.high.after.rows.find((r) => r.agent === "@main" && r.setting === "effortLevel").entries).map((i) => w.previews.local.high.after.entries[i]);
  const expected = entries.filter((e) => ["local", "project", "user"].includes(e.layer) && ["overridden", "ignored", "invalid"].includes(e.status));
  assert.ok(expected.length >= 1);
  const editedRef = w.local_target ? w.targets.targets.find((x) => x.target === w.local_target).ref : null;
  const lines = expected.filter((e) => JSON.stringify([e.agent || "@main", e.key, e.layer, e.file ?? null, e.path || e.key]) !== editedRef).map((e) => {
    const place = e.layer === "user" ? STRINGS.place_user : e.layer === "project" ? STRINGS.place_project : STRINGS.place_local;
    const slots = { value: e.value, place, status: STRINGS["status_" + e.status] };
    return e.layer === "user" ? T("still_status", slots) : T("still_status_c", slots);
  });
  assert.deepEqual(still, lines);
  assert.ok(still.every((n) => !/\{/.test(n)));
});

test("review: no_change draws the note and Cancel only", async () => {
  const n = real("no_change");
  const targets = clone(n.targets);
  open(targets, "project", ["high"]);
  const a = app({ data: { settings: n.settings, targets, history: n.history }, backend: { preview: async () => ok(n.preview_same) } });
  await a.choose("high");
  await a.pickRow("project");
  assert.equal(n.preview_same.no_change, true);
  assert.deepEqual(footTexts(a), [STRINGS.ed_cancel]);
  assert.equal(text(byClass(slotOf(a.root, "pick"), "s4-hint")[0]), STRINGS.ed_no_change_note);
  assert.equal(buttons(a.root).filter((b) => /^Save/.test(text(b))).length, 0);
});

// ---------------------------------------------------------------- the warning

test("warning: it shows before the Save action and doesn't block it", async () => {
  const a = app({ data: baseData(), backend: { preview: async () => ok(warned()), save: async () => bad("error", 500, { error: "write_failed" }) } });
  await a.choose("high");
  assert.deepEqual(a.log.preview.map((p) => p[1]), ["high"]);
  const warn = byClass(a.rail(), "p2-nt-warn")[0];
  assert.equal(warn.getAttribute("role"), "status");
  assert.equal(text(byClass(warn, "p2-nt-h")[0]), "▲" + STRINGS.ed_warn_h);
  const paras = tag(warn, "p").map(text);
  assert.equal(paras[0], STRINGS.ed_warn_overridden_t);
  assert.match(paras[1], new RegExp(T("ed_limit_winner", { value: "medium", file: "project/.claude/settings.local.json", line: 2 })));
  const go = btn(a.root, STRINGS.ed_save_anyway);
  assert.ok(go && !off(go));
  assert.ok(order(a.root, warn) < order(a.root, go), "the warning comes first");
  assert.ok(a.rail().contains(warn) && !warn.contains(go), "the warning is in the rail body, the buttons in the foot");
  assert.deepEqual(tag(warn, "button").map(text), []);
  assert.deepEqual(footTexts(a), [STRINGS.ed_save_anyway, STRINGS.ed_cancel]);
  assert.ok(hasClass(go, "s4-wide") && !hasClass(go, "p2-pri"), "Save anyway is not the primary button");
  assert.equal(byClass(slotOf(a.root, "pick"), "s4-hint").length, 0);
  assert.equal(buttons(a.root).filter((b) => /^Save to/.test(text(b))).length, 0);
  assert.equal(headNote(a.root), STRINGS.ed_nochange);
  assert.equal(WARNED.limits[0].lock_reason, null, "a winner limit that is editable carries no lock text");
  assert.equal(anyKey(a.root), false);
  go.click();
  await settle();
  assert.equal(a.log.save.length, 1);
  assert.equal(a.log.save[0].target, S.target);
  assert.equal(a.log.save[0].value, "high");
});

test("warning: a cap that lowers the level names the caps and says the effort that runs moves", async () => {
  const w = real("lowered");
  const a = app({ data: { settings: w.settings, targets: w.targets, history: w.history }, backend: { preview: async (t, v) => ok(w.previews[v]) } });
  await a.choose("xhigh");
  assert.deepEqual(a.log.preview, [], "the project is the only open row, and it is not preselected");
  await a.pickRow("project");
  assert.deepEqual(a.log.preview, [[w.target, "xhigh"]]);
  const warn = byClass(a.rail(), "p2-nt-warn")[0];
  assert.equal(text(byClass(warn, "p2-nt-h")[0]), "▲" + STRINGS.ed_warn_part_h);
  const paras = tag(warn, "p").map(text);
  assert.equal(paras[0], STRINGS.ed_warn_cap_t);
  assert.equal(paras.length, 3, "the text and one line for each of the two caps, and no cap_later lock line");
  assert.match(paras[1], /Your user file caps Sonnet 5\.5 at medium in config\/settings\.json, line 3/);
  assert.match(paras[2], /This project caps Sonnet 5\.5 at high in settings\.json, line 3/);
  assert.deepEqual(bigs(a.root), ["low", "→", "medium"]);
  assert.equal(headNote(a.root), STRINGS.ed_runs);
  // A cap that another reason holds is not cap_later, so its lock line replaces the cap text.
  const other = clone(w.previews.xhigh);
  other.warning.limits[0].lock_reason = "managed";
  const b = app({ data: { settings: w.settings, targets: w.targets, history: w.history }, backend: { preview: async () => ok(other) } });
  await b.choose("xhigh");
  await b.pickRow("project");
  const lines = tag(byClass(b.rail(), "p2-nt-warn")[0], "p").map(text);
  assert.equal(lines.includes(STRINGS.ed_warn_cap_t), false);
  assert.ok(lines.includes(STRINGS.ed_lock_managed));
});

test("warning: no model and a cap below the level says the cap still applies", async () => {
  const c = real("nomodel_cap");
  const targets = clone(c.targets);
  open(targets, "project", ["high"]);
  const a = app({ data: { settings: c.settings, targets, history: c.history }, backend: { preview: async (t, v) => ok(c.previews.project[v]) } });
  await a.choose("high");
  await a.pickRow("project");
  assert.equal(c.previews.project.high.warning.status, "in_effect");
  assert.equal(tag(byClass(a.rail(), "p2-nt-warn")[0], "p").map(text)[0], STRINGS.ed_warn_nomodel_cap_t);
  assert.equal(text(byClass(a.rail(), "p2-nt-h")[0]), "▲" + STRINGS.ed_warn_h);
});

test("warning: a cap that bites when a model is set does not say that no model is set", async () => {
  const c = real("nomodel_cap");
  const targets = clone(c.targets);
  open(targets, "project", ["high"]);
  const pv = clone(c.previews.project.high);
  pv.warning.model_known = true;
  const a = app({ data: { settings: c.settings, targets, history: c.history }, backend: { preview: async () => ok(pv) } });
  await a.choose("high");
  await a.pickRow("project");
  const lines = tag(byClass(a.rail(), "p2-nt-warn")[0], "p").map(text);
  assert.equal(lines.includes(STRINGS.ed_warn_nomodel_cap_t), false);
});

test("warning: a model limit and each winner status use their own text", async () => {
  const wants = { overridden: STRINGS.ed_warn_overridden_t, ignored: STRINGS.ed_warn_ignored_t, invalid: STRINGS.ed_warn_invalid_t, unknown: STRINGS.ed_warn_unknown_t };
  for (const [status, line] of Object.entries(wants)) {
    const a = app({ data: baseData(), backend: { preview: async () => ok(warned({ status })) } });
    await a.choose("high");
    assert.equal(tag(byClass(a.rail(), "p2-nt-warn")[0], "p").map(text)[0], line, status);
  }
  const pv = warned({ status: "lowered", in_effect_changes: true, limits: [{ kind: "model", value: "high", layer: null, file_display: null, line: null, editable: false, target: null, lock_reason: "model" }] });
  const a = app({ data: baseData(), backend: { preview: async () => ok(pv) } });
  await a.choose("high");
  assert.deepEqual(tag(byClass(a.rail(), "p2-nt-warn")[0], "p").map(text), [STRINGS.ed_warn_model_t, STRINGS.ed_lock_model]);
});

test("warning: an unknown status says the dashboard can't tell, in the heading and the saved banner", async () => {
  const barOf = async (warning) => {
    const pv = warning ? warned(warning) : clone(S.previews.high);
    const a = app({ data: baseData(), backend: { preview: async () => ok(pv), save: async () => ({ ...ok(S.save), after: S.after_save }) } });
    await a.choose("high");
    const heading = warning ? text(byClass(byClass(a.rail(), "p2-nt-warn")[0], "p2-nt-h")[0]) : null;
    btn(a.root, warning ? STRINGS.ed_save_anyway : LOCAL_SAVE).click();
    await settle();
    return { heading, line: okLine(a.root), path: pathLine(a.root), ok: okMark(a.root) === "✓" };
  };
  const slots = { file: "settings.local.json", level: "high" };
  const backup = T("ed_saved_backup", { path: S.save.edit.backup_display });
  const none = await barOf(null);
  assert.equal(none.line, T("ed_saved_t", slots));
  assert.equal(none.path, backup, "the backup path is its own line under the result");
  const noEffect = await barOf({ status: "overridden", in_effect_changes: false });
  assert.equal(noEffect.heading, "▲" + STRINGS.ed_warn_h);
  assert.equal(noEffect.line, T("ed_saved_no_effect_t", slots));
  const part = await barOf({ status: "lowered", in_effect_changes: true });
  assert.equal(part.heading, "▲" + STRINGS.ed_warn_part_h);
  assert.equal(part.line, T("ed_saved_part_t", slots));
  for (const changes of [false, true]) {
    const unknown = await barOf({ status: "unknown", in_effect_changes: changes });
    assert.equal(unknown.heading, "▲" + STRINGS.ed_warn_unknown_h);
    assert.equal(unknown.line, T("ed_saved_unknown_t", slots));
    assert.equal(unknown.path, backup);
    assert.ok(unknown.ok);
  }
});

test("warning: an unknown status says the dashboard can't tell what runs, ahead of the no change note", async () => {
  for (const changes of [false, true]) {
    const a = app({ data: baseData(), backend: { preview: async () => ok(warned({ status: "unknown", in_effect_changes: changes })) } });
    await a.choose("high");
    assert.equal(headNote(a.root), STRINGS.ed_nochange_unknown, String(changes));
  }
  assert.equal(STRINGS.ed_nochange_unknown, "can't tell what runs");
});

// ---------------------------------------------------------------- the stop panel

test("stop: a level held by a cap, with no row to save to, is off and says over cap, so it opens nothing", async () => {
  const w = real("lowered");
  const targets = clone(w.targets);
  shut(targets, "high");
  const a = app({ data: { settings: w.settings, targets, history: w.history }, backend: { preview: async () => { throw new Error("no preview"); } } });
  assert.ok(off(lvl(a.root, "high")), "an over-cap level can't be pressed");
  assert.deepEqual(byClass(a.root, "p2-sn").map(text).filter((x) => x === STRINGS.ed_seg_over_cap).length > 0, true);
  await a.choose("high");
  assert.equal(a.log.preview.length, 0);
  assert.equal(nts(a.rail(), "warn").length, 0, "no stop panel");
  assert.equal(byClass(a.root, "p2-df").length, 0);
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["low"], "nothing was chosen");
  // The cap note carries the change-it-by-hand line.
  assert.ok(noteTexts(a.body()).includes(STRINGS.ed_lock_cap_later));
});

test("stop: the model uses its own text", async () => {
  const run = async (name, level) => {
    const s = real(name);
    const targets = clone(s.targets);
    shut(targets, level);
    const a = app({ data: { settings: s.settings, targets, history: s.history } });
    await a.choose(level);
    return tag(byClass(a.rail(), "p2-nt-warn")[0], "p").map(text);
  };
  const model = await run("model_limit", "xhigh");
  assert.equal(model[0], T("ed_stop_model_t", { level: "xhigh", runs_as: "high" }));
  assert.equal(model[1], STRINGS.ed_lock_model);
});

test("stop: a level held by something else is the nothing-to-save rail, not the stop panel", async () => {
  const u = real("user_unknown");
  const targets = clone(u.targets);
  for (const name of ["low", "medium", "high"]) shut(targets, name);
  fileOf(targets, "xhigh", "user").pickable = true; // one level stays open, so the project can save
  recount(targets);
  const a = app({ data: { settings: u.settings, targets, history: u.history } });
  await a.choose("high");
  const warn = byClass(a.rail(), "p2-nt-warn")[0];
  assert.equal(text(byClass(warn, "p2-nt-h")[0]), "▲" + T("ed_nosave_level", { level: "high" }));
  assert.equal(tag(warn, "p").length, 0, "a limit with no winner adds no line");
});

// ---------------------------------------------------------------- save and undo

test("saved: the strip shows the backup path and Undo, and the picker goes back to rest with the new level running", async () => {
  const gate = {};
  const a = app({
    data: baseData(),
    backend: { ...saveFlow(), save: () => new Promise((resolve) => { gate.go = () => resolve({ ...ok(S.save), after: S.after_save }); }) },
  });
  await a.choose("high");
  btn(a.root, LOCAL_SAVE).click();
  await settle();
  // in flight: the buttons are off and the state survives a draw from new data
  a.draw();
  const busy = btn(a.root, STRINGS.ed_saving);
  assert.ok(off(busy) && busy.getAttribute("aria-busy") === "true");
  assert.ok(off(btn(a.root, STRINGS.ed_cancel)));
  assert.ok(levelInputs(a.root).every(off), "every level is off while saving");
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["high"], "the checked level stays");
  assert.ok(rowInputs(a.root).every(off), "so is every row");
  assert.ok(byClass(a.root, "sr").some((n) => text(n) === T("ed_saving_sr", { file: "settings.local.json" })));
  assert.equal(byClass(a.root, "p2-df").length, 1);
  gate.go();
  await settle();
  const bar = stripOf(a.root);
  assert.equal(okRow(a.root).getAttribute("role"), "status");
  assert.ok(hasClass(okRow(a.root), "s4-ok") && !hasClass(okRow(a.root), "s4-ok-warn"));
  assert.equal(byClass(okRow(a.root), "s4-okm")[0].getAttribute("aria-hidden"), "true");
  assert.equal(okMark(a.root), "✓");
  assert.equal(okLine(a.root), T("ed_saved_t", { file: "settings.local.json", level: "high" }));
  assert.equal(pathLine(a.root), T("ed_saved_backup", { path: S.save.edit.backup_display }), "the backup path is a hint line");
  assert.equal(text(byClass(bar, "pa")[0]), S.save.edit.backup_display);
  assert.deepEqual(tag(bar, "button").map(text), [STRINGS.ed_undo]);
  const undoBtn = tag(bar, "button")[0];
  assert.ok(hasClass(undoBtn, "s4-wide") && byClass(undoBtn, "ic").length === 1, "Undo is wide, with its icon");
  assert.ok(a.foot().contains(bar), "the result is in the foot");
  assert.equal(buttons(a.root).filter((b) => /^Save/.test(text(b))).length, 0, "no Save once the change is saved");
  // the page is at rest, with the new level now
  assert.equal(byClass(a.root, "p2-df").length, 0);
  assert.deepEqual(byClass(a.root, "p2-sn").map(text), ["", "", STRINGS.ed_seg_now, ""]);
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["high"]);
  assert.ok(levelInputs(a.root).every((r) => !off(r)));
  assert.equal(liveRows(a.root).length, 0);
  assert.equal(a.log.save.length, 1);
  assert.equal(a.log.save[0].value, "high");
  assert.equal(a.log.save[0].target, levelOf(S.start.targets, "high").preselect);
  assert.equal(anyKey(a.root), false);
});

test("undo: one undo level shows, and after an undo no Undo shows and the strip names the restored-from path", async () => {
  const a = app({ data: afterSave(), backend: saveFlow() });
  const bar = stripOf(a.root);
  assert.deepEqual(tag(bar, "button").map(text), [STRINGS.ed_undo]);
  assert.equal(strips(a.root).length, 1);
  assert.equal(S.after_save.history.rows.length, 1);
  await a.press(STRINGS.ed_undo);
  assert.deepEqual(a.log.undo, [S.save.edit.id]);
  const done = stripOf(a.root);
  assert.equal(okMark(a.root), "✓");
  assert.equal(okRow(a.root).getAttribute("role"), "status");
  assert.equal(okLine(a.root), T("ed_undone_t", { file: "settings.local.json" }));
  assert.deepEqual(tag(done, "button").map(text), [STRINGS.ed_dismiss]);
  assert.equal(pathLine(a.root), T("ed_undone_path", { path: S.undo.restored_from_display }), "the restored path is a hint line");
  assert.equal(buttons(a.root).filter((b) => text(b) === STRINGS.ed_undo).length, 0);
  assert.deepEqual(byClass(done, "pa").map(text), [S.undo.restored_from_display]);
  assert.notEqual(S.undo.restored_from_display, S.undo.edit.backup_display);
  assert.equal(text(done).includes(S.undo.edit.backup_display), false);
  assert.match(text(done), new RegExp(T("ed_undone_t", { file: "settings.local.json" }).slice(0, 30)));
  assert.equal(FElement.focused, tag(done, "button")[0], "focus goes to Dismiss, because Undo is gone");
  // Dismiss brings back the row of the newest ledger entry, an undo, with one path and no Undo.
  tag(done, "button")[0].click();
  await settle();
  const rest = stripOf(a.root);
  assert.equal(S.after_undo.history.rows[0].kind, "undo");
  assert.equal(tag(rest, "button").length, 0);
  assert.equal(byClass(rest, "s4-okm").length, 0);
  assert.deepEqual(byClass(rest, "pa").map(text), [S.after_undo.history.rows[0].restored_from_display]);
  assert.equal(anyKey(a.root), false);
});

test("strip: the newest row on load is a quiet line with its time, the values, the backup path and Undo", () => {
  const row = S.after_save.history.rows[0];
  const a = app({ data: afterSave() });
  const bar = stripOf(a.root);
  assert.equal(byClass(bar, "s4-ok").length, 0, "the row at rest is a note, not a status frame");
  assert.equal(byClass(bar, "s4-okm").length, 0);
  const line = T("ed_last_t", { when: format.fmtTime(row.time), old: "low", new: "high", file: "settings.local.json" });
  const note = byClass(bar, "s4-note")[0];
  assert.equal(note.tagName, "p");
  assert.equal(text(note), line + " " + T("ed_saved_backup", { path: row.backup_display }));
  assert.deepEqual(byClass(bar, "pa").map(text), [row.backup_display]);
  assert.deepEqual(tag(bar, "button").map(text), [STRINGS.ed_undo]);
});

test("strip: a chosen level hides the last change and its Undo, and Cancel brings them back", async () => {
  const a = app({ data: afterSave() });
  assert.deepEqual(tag(stripOf(a.root), "button").map(text), [STRINGS.ed_undo]);
  await a.choose("low");
  assert.equal(tag(stripOf(a.root), "button").length, 0, "the foot holds Save and Cancel alone during a change");
  assert.equal(byClass(stripOf(a.root), "s4-note").length, 0);
  footButtons(a).find((b) => text(b) === STRINGS.ed_cancel).click();
  await settle();
  assert.deepEqual(tag(stripOf(a.root), "button").map(text), [STRINGS.ed_undo]);
});

test("changed file: the row shows no Undo, names the backup path, and a press answer says the same with Dismiss", async () => {
  const c = real("changed_since_save");
  assert.equal(c.history.rows[0].not_undoable_reason, "changed_since_save");
  const rest = app({ data: { settings: c.settings, targets: c.targets, history: c.history } });
  const bar = stripOf(rest.root);
  assert.ok(hasClass(okRow(rest.root), "s4-ok-warn"));
  assert.equal(okMark(rest.root), "▲");
  assert.equal(tag(bar, "button").length, 0);
  assert.deepEqual(byClass(bar, "pa").map(text), [c.history.rows[0].backup_display]);
  assert.match(text(bar), new RegExp(T("ed_undo_stale_h", { file: "settings.json" })));
  assert.equal(buttons(rest.root).filter((b) => text(b) === STRINGS.ed_undo).length, 0);
  // The page showed Undo (an older history), and the server answered 409.
  const press = app({
    data: afterSave(),
    backend: { undo: async () => bad("error", 409, c.undo_answer), refresh: () => ({ settings: c.settings, targets: c.targets, history: c.history }) },
  });
  await press.press(STRINGS.ed_undo);
  assert.equal(press.log.refresh, 1, "the answer loads the page data again");
  const warn = stripOf(press.root);
  assert.ok(hasClass(okRow(press.root), "s4-ok-warn"));
  assert.equal(okRow(press.root).getAttribute("role"), "status");
  assert.deepEqual(byClass(warn, "pa").map(text), [c.undo_answer.backup_display]);
  assert.deepEqual(tag(warn, "button").map(text), [STRINGS.ed_dismiss]);
  tag(warn, "button")[0].click();
  await settle();
  const back = stripOf(press.root);
  assert.deepEqual(tag(back, "button").map(text), [], "the row's own strip is back, with no dead Undo");
  assert.ok(hasClass(okRow(press.root), "s4-ok-warn"));
  assert.match(text(back), new RegExp(T("ed_undo_stale_h", { file: "settings.json" })));
});

test("backup_damaged: at rest a warning with no buttons, and on a press an alert that replaces the strip", async () => {
  const d = real("backup_damaged");
  const rest = app({ data: { settings: d.settings, targets: d.targets, history: d.history } });
  const bar = stripOf(rest.root);
  assert.ok(hasClass(okRow(rest.root), "s4-ok-warn"));
  assert.equal(tag(bar, "button").length, 0);
  assert.equal(okLine(rest.root), T("ed_backup_damaged_rest", { path: d.history.rows[0].backup_display }));
  const press = app({ data: afterSave(), backend: { undo: async () => bad("error", 409, d.undo_answer) } });
  await press.press(STRINGS.ed_undo);
  assert.equal(byClass(stripOf(press.root), "s4-ok").length + byClass(stripOf(press.root), "s4-note").length, 0, "the alert replaces the strip");
  const alert = byClass(slotOf(press.root, "strip"), "p2-nt-err")[0];
  assert.equal(alert.getAttribute("role"), "alert");
  assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + STRINGS.ed_backup_damaged_h);
  assert.deepEqual(byClass(alert, "pa").map(text), [d.undo_answer.backup_display]);
  assert.deepEqual(tag(alert, "button").map(text), [STRINGS.ed_dismiss]);
  assert.equal(FElement.focused, tag(alert, "button")[0]);
});

test("strip: a pruned backup at rest is a quiet line, and not_undoable on a press is an alert with Dismiss", async () => {
  const p = real("backup_pruned");
  const a = app({ data: { settings: p.settings, targets: p.targets, history: p.history } });
  const bar = strips(a.root)[0];
  assert.equal(text(bar), STRINGS.ed_backup_pruned_rest);
  assert.equal(tag(bar, "button").length, 0);
  const n = real("not_undoable");
  const b = app({ data: afterSave(), backend: { undo: async () => bad("error", 409, n.undo_answer) } });
  await b.press(STRINGS.ed_undo);
  const alert = byClass(slotOf(b.root, "strip"), "p2-nt-err")[0];
  assert.equal(alert.getAttribute("role"), "alert");
  assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + STRINGS.ed_not_undoable);
  assert.equal(FElement.focused, tag(alert, "button")[0]);
});

test("unverified: a save shows its own alert with the backup path and Dismiss, with no table, no diff and no retry", async () => {
  for (const stage of ["reread", "fsync"]) {
    const body = { error: "unverified", stage, file_unchanged: false, backup_display: "config/routing-dashboard/backups/x/000001-a.bak" };
    const a = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("unverified", 500, body) } });
    await a.choose("high");
    btn(a.root, LOCAL_SAVE).click();
    await settle();
    const alert = byClass(a.rail(), "p2-nt-err")[0];
    assert.equal(alert.getAttribute("role"), "alert");
    const h = stage === "fsync" ? STRINGS.ed_unverified_fsync_h : STRINGS.ed_unverified_reread_h;
    assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + h);
    assert.deepEqual(byClass(alert, "pa").map(text), [body.backup_display]);
    assert.equal(byClass(a.root, "p2-df").length + byClass(a.root, "p2-df").length, 0);
    const labels = buttons(a.root).map(text);
    assert.equal(labels.includes(STRINGS.ed_try_again) || labels.includes(STRINGS.ed_saving) || labels.some((l) => /^Save/.test(l)), false);
    const dismiss = btn(a.root, STRINGS.ed_dismiss);
    assert.equal(FElement.focused, dismiss);
    assert.equal(levelInputs(a.root).length, 4, "the picker stays");
    dismiss.click();
    await settle();
    assert.equal(byClass(a.root, "p2-nt").length, 0);
    assert.deepEqual(checkedOf(levelInputs(a.root)), ["low"], "back to the picker at rest");
  }
  const body = { error: "unverified", stage: "reread", file_unchanged: false, backup_display: "config/b/000001-z.bak" };
  const u = app({ data: afterSave(), backend: { undo: async () => bad("unverified", 500, body) } });
  await u.press(STRINGS.ed_undo);
  const alert = byClass(slotOf(u.root, "strip"), "p2-nt-err")[0];
  assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + STRINGS.ed_unverified_reread_h);
  assert.deepEqual(byClass(alert, "pa").map(text), [body.backup_display]);
  assert.equal(FElement.focused, tag(alert, "button")[0]);
});

test("raced: a save and an undo each show their own warning, and Dismiss goes back to the picker", async () => {
  const path_ = "config/routing-dashboard/backups/x/000001-a.bak";
  const a = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("raced", 409, { error: "raced", edit: S.save.edit, backup_display: path_, settings: S.save.settings }) } });
  await a.choose("high");
  btn(a.root, LOCAL_SAVE).click();
  await settle();
  const warn = byClass(a.rail(), "p2-nt-warn")[0];
  assert.equal(warn.getAttribute("role"), "status");
  assert.equal(text(byClass(warn, "p2-nt-h")[0]), "▲" + T("ed_raced_h", { file: "settings.local.json" }));
  assert.equal(text(tag(warn, "p")[0]), T("ed_raced_t", { path: path_ }));
  assert.deepEqual(byClass(warn, "pa").map(text), [path_]);
  assert.equal(byClass(a.root, "p2-df").length, 0);
  assert.equal(FElement.focused, btn(a.root, STRINGS.ed_dismiss));
  btn(a.root, STRINGS.ed_dismiss).click();
  await settle();
  assert.equal(byClass(a.root, "p2-nt").length, 0);
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["low"]);
  const restored = "config/routing-dashboard/backups/x/000002-b.bak";
  const u = app({ data: afterSave(), backend: { undo: async () => bad("raced", 409, { error: "raced", edit: S.undo.edit, backup_display: path_, settings: S.undo.settings, matches_backup: false, restored_from_display: restored }) } });
  await u.press(STRINGS.ed_undo);
  const alert = byClass(slotOf(u.root, "strip"), "p2-nt-warn")[0];
  assert.equal(text(tag(alert, "p")[0]), T("ed_raced_undo_t", { path: restored }));
  assert.deepEqual(byClass(alert, "pa").map(text), [restored]);
  assert.equal(FElement.focused, tag(alert, "button")[0]);
});

test("write_failed: the review stays and the actions slot offers Try again, with focus on it", async () => {
  let n = 0;
  const a = app({ data: baseData(), backend: { ...saveFlow(), save: async () => (++n === 1 ? bad("error", 500, { error: "write_failed", file_unchanged: true }) : { ...ok(S.save), after: S.after_save }) } });
  await a.choose("high");
  btn(a.root, LOCAL_SAVE).click();
  await settle();
  const alert = byClass(a.rail(), "p2-nt-err")[0];
  assert.equal(alert.getAttribute("role"), "alert");
  assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + STRINGS.ed_fail_h);
  assert.equal(text(tag(alert, "p")[0]), T("ed_fail_t", { file: "settings.local.json" }));
  assert.equal(byClass(a.root, "p2-df").length, 1);
  const again = btn(a.root, STRINGS.ed_try_again);
  assert.equal(FElement.focused, again);
  assert.ok(btn(a.root, STRINGS.ed_cancel));
  again.click();
  await settle();
  assert.equal(a.log.save.length, 2);
  assert.equal(strips(a.root).length, 1);
});

test("write_failed: a missing config folder names the folder under the same heading, on the review and in the strip", async () => {
  const answer = { error: "config_dir_missing", file_unchanged: true, config_dir_display: "~/gone/.claude" };
  const a = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("error", 500, answer) } });
  await a.choose("high");
  btn(a.root, LOCAL_SAVE).click();
  await settle();
  const alert = byClass(a.rail(), "p2-nt-err")[0];
  assert.equal(alert.getAttribute("role"), "alert");
  assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + STRINGS.ed_fail_h);
  assert.equal(text(tag(alert, "p")[0]), T("ed_fail_config_dir_t", { config_dir: answer.config_dir_display }));
  assert.deepEqual(byClass(alert, "pa").map(text), [answer.config_dir_display]);
  assert.equal(byClass(a.root, "p2-df").length, 1, "the review stays");
  assert.ok(btn(a.root, STRINGS.ed_try_again));
  const u = app({ data: afterSave(), backend: { ...saveFlow(), undo: async () => bad("error", 500, answer) } });
  await u.press(STRINGS.ed_undo);
  const note = byClass(u.root, "p2-nt-err")[0];
  assert.equal(text(byClass(note, "p2-nt-h")[0]), "✕" + STRINGS.ed_fail_h);
  assert.equal(text(tag(note, "p")[0]), T("ed_fail_config_dir_t", { config_dir: answer.config_dir_display }));
  assert.deepEqual(byClass(note, "pa").map(text), [answer.config_dir_display]);
  assert.deepEqual(tag(note, "button").map(text), [STRINGS.ed_dismiss]);
  assert.equal(anyKey(u.root), false);
});

test("stale: a changed file returns to the new preview with a warning, and a changed trail names the files", async () => {
  const s = real("stale");
  const a = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("stale", 409, s.stale_file) } });
  await a.choose("high");
  btn(a.root, LOCAL_SAVE).click();
  await settle();
  const warn = byClass(a.rail(), "p2-nt-warn")[0];
  assert.equal(warn.getAttribute("role"), "status");
  assert.equal(text(byClass(warn, "p2-nt-h")[0]), "▲" + T("ed_stale_file_h", { file: "settings.local.json" }));
  assert.equal(text(tag(warn, "p")[0]), STRINGS.ed_stale_file_t);
  assert.equal(tag(warn, "button").length, 0);
  assert.ok(order(a.root, warn) < order(a.root, byClass(a.root, "p2-df")[0]), "the notice sits over the new preview");
  assert.equal(byClass(a.root, "p2-df").length, 1);
  assert.ok(btn(a.root, LOCAL_SAVE), "the new preview's own actions");
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["high"]);
  const t2 = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("stale", 409, s.stale_trail) } });
  await t2.choose("high");
  btn(t2.root, LOCAL_SAVE).click();
  await settle();
  const trailNote = byClass(t2.rail(), "p2-nt-warn")[0];
  assert.equal(text(byClass(trailNote, "p2-nt-h")[0]), "▲" + STRINGS.ed_stale_trail_h);
  assert.equal(text(tag(trailNote, "p")[0]), T("ed_stale_trail_t", { files: "settings.json" }));
  const general = clone(s.stale_trail);
  general.changed_files = [];
  const g = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("stale", 409, general) } });
  await g.choose("high");
  btn(g.root, LOCAL_SAVE).click();
  await settle();
  assert.equal(text(tag(byClass(g.rail(), "p2-nt-warn")[0], "p")[0]), STRINGS.ed_stale_trail_general_t);
  // A null preview: the line is gone, so the notice sits over the rail at rest.
  const gone = clone(s.stale_file);
  gone.preview = null;
  const n = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("stale", 409, gone), refresh: () => ({}) } });
  await n.choose("high");
  btn(n.root, LOCAL_SAVE).click();
  await settle();
  const note = byClass(n.rail(), "p2-nt-warn")[0];
  assert.equal(text(byClass(note, "p2-nt-h")[0]), "▲" + T("ed_stale_file_h", { file: "settings.local.json" }));
  assert.equal(text(tag(note, "p")[0]), STRINGS.ed_stale_gone_t);
  assert.equal(byClass(n.root, "p2-df").length, 0);
  assert.equal(levelInputs(n.root).length, 4);
  assert.equal(anyKey(n.root), false);
});

test("stale: a stale save reloads the edit data once, does not save again, and keeps the new preview and notice", async () => {
  const s = real("stale");
  const a = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("stale", 409, s.stale_file), refresh: () => ({}) } });
  await a.choose("high");
  btn(a.root, LOCAL_SAVE).click();
  await settle();
  assert.equal(a.log.refresh, 1);
  assert.equal(a.log.reload, 0, "the full refresh covers the targets and history");
  assert.equal(a.log.save.length, 1);
  const draws = a.log.draws;
  a.draw();
  assert.equal(a.log.draws, draws + 1);
  assert.equal(byClass(a.root, "p2-nt-warn").length, 1);
  assert.equal(text(tag(byClass(a.root, "p2-nt-warn")[0], "p")[0]), STRINGS.ed_stale_file_t);
  assert.equal(byClass(a.root, "p2-df").length, 1);
  assert.ok(btn(a.root, LOCAL_SAVE));
  assert.equal(a.log.refresh, 1);
  assert.equal(a.log.save.length, 1);
  assert.equal(a.log.preview.length, 1, "the fresh preview is kept, and no preview is asked for again");
});

test("stale: a stale save refreshes the tiles and the rows too, not only the targets and history", async () => {
  const s = real("stale");
  const fresh = S.after_save.settings;
  const a = app({
    data: baseData(),
    backend: { ...saveFlow(), save: async () => bad("stale", 409, s.stale_file), refresh: () => ({ settings: fresh }) },
  });
  const old = text(a.root);
  await a.choose("high");
  btn(a.root, LOCAL_SAVE).click();
  await settle();
  assert.equal(a.log.refresh, 1);
  assert.deepEqual(a.st.settings, fresh, "the settings came back from the refresh");
  assert.notEqual(text(a.root), old, "the page drew the new settings");
  assert.equal(byClass(a.root, "p2-nt-warn").length, 1, "the notice survives the refresh");
  assert.ok(btn(a.root, LOCAL_SAVE), "the review survives the refresh");
});

test("token: a locked outcome from a press draws the alert where the press was, then the Locked line", async () => {
  const card = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("locked", 403, { error: "bad_token" }) } });
  await card.choose("high");
  btn(card.root, LOCAL_SAVE).click();
  await settle();
  const alert = byClass(card.rail(), "p2-nt-err")[0];
  assert.equal(alert.getAttribute("role"), "alert");
  assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + STRINGS.ed_token_h);
  assert.equal(text(tag(alert, "p")[0]), STRINGS.ed_token_t);
  assert.deepEqual(noteTexts(card.rail()), [STRINGS.ed_locked]);
  assert.equal(buttons(card.root).length, 0);
  assert.ok(levelInputs(card.root).every(off));
  const undo = app({ data: afterSave(), backend: { undo: async () => bad("locked", 403, { error: "bad_token" }) } });
  await undo.press(STRINGS.ed_undo);
  const where = byClass(slotOf(undo.root, "strip"), "p2-nt-err")[0];
  assert.equal(text(byClass(where, "p2-nt-h")[0]), "✕" + STRINGS.ed_token_h);
  assert.deepEqual(noteTexts(undo.rail()), [STRINGS.ed_locked]);
  assert.equal(buttons(undo.root).filter((b) => text(b) !== STRINGS.ed_dismiss).length, 0);
});

test("locked: every flow resets, and the picker is fresh when the mode is ready again", async () => {
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await a.choose("high");
  assert.equal(byClass(a.root, "p2-df").length, 1);
  a.setMode("locked");
  a.draw();
  assert.equal(byClass(a.root, "p2-df").length, 0);
  assert.ok(levelInputs(a.root).every(off));
  a.setMode("ready");
  a.draw();
  assert.equal(byClass(a.root, "p2-df").length, 0);
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["low"]);
});

test("off: a mode change to off clears every project's flow, not only the open one", async () => {
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await a.choose("high");
  const other = baseData();
  a.use(a.key + "-b", other);
  assert.equal(byClass(a.root, "p2-df").length, 0);
  const keyA = a.key.replace(/-b$/, "");
  a.setMode("off");
  a.draw();
  a.setMode("ready");
  a.use(keyA, baseData());
  assert.equal(byClass(a.root, "p2-df").length, 0, "the first project's flow went with the mode change");
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["low"]);
});

test("errors: any other error is an alert with Dismiss, worded by its code, and no key is built from a null", async () => {
  const cases = [
    [400, { error: "not_editable" }, STRINGS.ed_err_not_editable],
    [422, { error: "managed" }, STRINGS.ed_lock_managed],
    [422, { error: "key_missing" }, STRINGS.ed_err_key_missing],
    [404, { error: "unknown_project" }, STRINGS.ed_err_unknown_project],
    [0, null, STRINGS.ed_err_network],
    [500, { error: null }, STRINGS.ed_err_network],
    [422, { error: null }, STRINGS.ed_err_network],
    [500, {}, STRINGS.ed_err_network],
    [418, { error: "a_code_nobody_knows" }, STRINGS.ed_err_forbidden],
    [422, { error: "" }, STRINGS.ed_err_network],
  ];
  for (const [status, body, want] of cases) {
    const a = app({ data: baseData(), backend: { preview: async () => bad("error", status, body) } });
    await a.choose("high");
    const alert = byClass(a.rail(), "p2-nt-err")[0];
    assert.equal(alert.getAttribute("role"), "alert", String(status));
    assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + want, JSON.stringify(body));
    assert.equal(/ed_(lock|err)_(null|undefined)/.test(a.root.textContent), false);
    assert.equal(anyKey(a.root), false);
    tag(alert, "button")[0].click();
    await settle();
    assert.equal(byClass(a.root, "p2-nt").length, 0);
  }
  // A save that fails with another code keeps the review.
  const s = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("error", 400, { error: "bad_value" }) } });
  await s.choose("high");
  btn(s.root, LOCAL_SAVE).click();
  await settle();
  assert.equal(text(byClass(byClass(s.rail(), "p2-nt-err")[0], "p2-nt-h")[0]), "✕" + STRINGS.ed_err_bad_value);
  assert.equal(byClass(s.root, "p2-df").length, 1);
});

test("refused save: a 400 not_editable or a 422 clears the review, keeps a notice and loads the files again", async () => {
  const pvs = real("project_only").previews.project;
  const flow = (fresh, status, body) => ({
    preview: async (t, v) => ok(pvs[v]),
    save: async () => bad("error", status, body),
    refresh: () => ({ targets: fresh }),
  });
  for (const [status, body, want] of [[400, { error: "not_editable" }, STRINGS.ed_err_not_editable], [422, { error: "symlink" }, STRINGS.ed_lock_symlink]]) {
    // The fresh files say the local row is locked, so nothing is picked and the rail asks for a file.
    const fresh = trioLocal();
    grey(fresh, "local", "symlink");
    const a = app({ data: baseData({ targets: trioLocal() }), backend: flow(fresh, status, body) });
    await a.choose("high");
    const local = targetOf(trioLocal(), "local").target;
    assert.deepEqual(a.log.preview, [[local, "high"]]);
    btn(a.root, LOCAL_SAVE).click();
    await settle();
    assert.equal(a.log.refresh, 1, String(status));
    assert.equal(a.log.save.length, 1);
    const alert = byClass(a.rail(), "p2-nt-err")[0];
    assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + want, String(status));
    assert.equal(byClass(a.root, "p2-df").length, 0, "the review is gone");
    assert.ok(noteTexts(a.rail()).includes(STRINGS.ed_pick_file), "settle ran on the fresh files and found no row");
    assert.deepEqual(checkedOf(rowInputs(a.root)), []);
    assert.equal(a.log.preview.length, 1, "nothing is previewed again");
    assert.deepEqual(checkedOf(levelInputs(a.root)), ["high"]);
  }
  // Fresh files that still take the local row preview it again, and the notice stays.
  const b = app({ data: baseData({ targets: trioLocal() }), backend: flow(trioLocal(), 422, { error: "managed" }) });
  await b.choose("high");
  btn(b.root, LOCAL_SAVE).click();
  await settle();
  assert.equal(b.log.preview.length, 2);
  assert.equal(byClass(b.root, "p2-df").length, 1);
  assert.equal(text(byClass(byClass(b.rail(), "p2-nt-err")[0], "p2-nt-h")[0]), "✕" + STRINGS.ed_lock_managed);
});

// ---------------------------------------------------------------- the damaged ledger

test("ledger: at rest a warning names each damaged record, above the row's own strip", () => {
  const l = real("ledger");
  assert.equal(l.history.damaged_ledgers.length, 1);
  const only = app({ data: { settings: l.settings, targets: l.targets, history: l.history } });
  const bars = byClass(stripOf(only.root), "s4-ok");
  assert.equal(bars.length, 1);
  assert.ok(hasClass(bars[0], "s4-ok-warn"));
  assert.equal(bars[0].getAttribute("role"), null);
  assert.equal(text(byClass(bars[0], "s4-okm")[0]), "▲");
  assert.equal(tag(stripOf(only.root), "button").length, 0);
  assert.deepEqual(byClass(bars[0], "pa").map(text), [l.history.damaged_ledgers[0].ledger_display]);
  assert.equal(text(tag(bars[0], "span").find((n) => !hasClass(n, "s4-okm") && !hasClass(n, "pa"))).length > 0, true);
  assert.equal(text(bars[0]).slice(1), T("ed_ledger_rest_t", { file: "settings.local.json", path: l.history.damaged_ledgers[0].ledger_display }));
  const both = clone(l.history);
  both.damaged_ledgers.push({ layer: "user", file_display: "config/settings.json", ledger_display: "config/routing-dashboard/backups/zz/ledger.json" });
  both.rows = S.after_save.history.rows;
  const two = app({ data: { settings: l.settings, targets: l.targets, history: both } });
  const list = stripOf(two.root).childNodes;
  const frames = list.filter((n) => hasClass(n, "s4-ok"));
  assert.equal(frames.length, 2, "one warning for each damaged record");
  assert.ok(frames.every((n) => hasClass(n, "s4-ok-warn")));
  assert.ok(order(stripOf(two.root), frames[1]) < order(stripOf(two.root), byClass(stripOf(two.root), "s4-note")[0]), "above the row's own note");
  assert.deepEqual(tag(stripOf(two.root), "button").map(text), [STRINGS.ed_undo]);
  const offApp = app({ mode: "off", data: { settings: l.settings, targets: offAnswer(l.targets), history: l.history } });
  assert.equal(strips(offApp.root).length, 0);
});

test("ledger: a preview of the damaged file draws no Save while another file's preview does", async () => {
  const l = real("ledger");
  const targets = clone(l.targets);
  open(targets, "project", ["high"]);
  const a = app({
    data: { settings: l.settings, targets, history: l.history },
    backend: { preview: async (target, level) => ok(target === l.local_target ? l.previews.local[level] : l.previews.project[level]) },
  });
  // The local file's record is damaged, and the local file is preselected.
  await a.choose("high");
  assert.equal(buttons(a.root).filter((b) => /^Save/.test(text(b))).length, 0);
  assert.equal(byClass(a.root, "p2-df").length, 1, "the full preview stays");
  assert.equal(byClass(a.root, "p2-df").length, 1);
  const notice = nts(a.rail(), "warn")[0];
  assert.equal(text(byClass(notice, "p2-nt-h")[0]), "▲" + T("ed_ledger_preview_t", { file: "settings.local.json" }));
  assert.deepEqual(tag(notice, "button").map(text), [], "the notice is in the rail body");
  assert.deepEqual(footTexts(a), [STRINGS.ed_cancel], "the foot holds Cancel alone");
  // The project file's record is sound, so its preview keeps a Save.
  await a.pickRow("project");
  assert.deepEqual(a.log.preview.map((p) => p[0]), [l.local_target, l.project_target]);
  assert.ok(btn(a.root, T("ed_save_to", { file: "settings.json" })) || btn(a.root, STRINGS.ed_save_anyway), "a Save action for the other file");
  assert.equal(a.log.save.length, 0);
});

test("ledger: a save answered 500 ledger_damaged shows the alert with the record's path, and Dismiss loads the data again", async () => {
  const l = real("ledger");
  let draws = 0;
  const a = app({
    data: baseData(),
    backend: {
      ...saveFlow(),
      save: async () => bad("error", 500, l.save_answer),
      reload: () => { draws += 1; return {}; },
    },
  });
  await a.choose("high");
  btn(a.root, LOCAL_SAVE).click();
  await settle();
  const alert = byClass(a.rail(), "p2-nt-err")[0];
  assert.equal(alert.getAttribute("role"), "alert");
  assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + T("ed_ledger_h", { file: "settings.local.json" }));
  assert.deepEqual(byClass(alert, "pa").map(text), [l.save_answer.ledger_display]);
  assert.equal(buttons(a.root).filter((b) => /^Save|Try/.test(text(b))).length, 0);
  assert.equal(FElement.focused, btn(a.root, STRINGS.ed_dismiss));
  assert.equal(a.log.reload, 0);
  btn(a.root, STRINGS.ed_dismiss).click();
  await settle();
  assert.equal(a.log.reload, 1);
  assert.equal(draws, 1);
  const u = app({ data: afterSave(), backend: { undo: async () => bad("error", 500, l.save_answer) } });
  await u.press(STRINGS.ed_undo);
  const where = byClass(slotOf(u.root, "strip"), "p2-nt-err")[0];
  assert.equal(text(byClass(where, "p2-nt-h")[0]), "✕" + T("ed_ledger_h", { file: "settings.local.json" }));
  btn(u.root, STRINGS.ed_dismiss).click();
  await settle();
  assert.equal(u.log.reload, 1);
});

// ---------------------------------------------------------------- the flow over time

test("flow: the state survives a draw, leaving Settings for another page and coming back, and a changed route query", async () => {
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await a.choose("high");
  a.draw(); // the same project, drawn again from new data
  assert.equal(byClass(a.root, "p2-df").length, 1, "the review survives a draw");
  // Overview and the trail are other pages: Settings is not drawn, and the trail draws on its own.
  const ctx = a.makeCtx();
  trail.render(a.page.sections.trail, { ...ctx, route: { name: "trail", params: { agent: "@main", setting: "effortLevel" }, query: {} } });
  trail.render(a.page.sections.trail, { ...ctx, route: { name: "overview", params: {}, query: {} } });
  a.draw();
  assert.equal(byClass(a.root, "p2-df").length, 1, "the review is there on the way back");
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["high"]);
  assert.deepEqual(checkedOf(rowInputs(a.root)), ["local"]);
  // Another cell, then Effort again.
  settingsPage.render(a.root, { ...a.makeCtx(), route: { name: "settings", params: {}, query: { setting: "model" } } });
  assert.equal(levelInputs(a.root).length, 0);
  assert.equal(byClass(a.root, "p2-df").length, 1, "the review stays on another cell");
  assert.deepEqual(footTexts(a), [LOCAL_SAVE, STRINGS.ed_cancel], "and so do Save and Cancel");
  a.draw();
  assert.equal(byClass(a.root, "p2-df").length, 1);
  assert.equal(a.log.preview.length, 1, "none of this asked for a preview again");
});

test("flow: the state survives a project switch and back, and the other project starts at rest", async () => {
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  const keyA = a.key;
  await a.choose("high");
  assert.equal(byClass(a.root, "p2-df").length, 1);
  a.use(keyA + "-b", baseData());
  assert.equal(byClass(a.root, "p2-df").length, 0, "another project starts at rest");
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["low"]);
  assert.equal(liveRows(a.root).length, 0);
  await a.choose("medium");
  assert.deepEqual(a.log.preview.map((p) => p[1]), ["high", "medium"]);
  a.use(keyA, baseData());
  assert.equal(byClass(a.root, "p2-df").length, 1, "the first project's review is back");
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["high"]);
  assert.deepEqual(bigs(a.root), ["low", "→", "high"]);
  assert.equal(a.log.preview.length, 2, "no preview was asked for again");
  a.use(keyA + "-b", baseData());
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["medium"], "and so is the second project's");
});

// The copy of the page code a reload would load: its own module instances, so its flow is empty.
let copy = null;
async function reloaded() {
  if (copy) return copy;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mr-edit-card-js-"));
  process.on("exit", () => { try { fs.rmSync(dir, { recursive: true, force: true }); } catch (err) { /* nothing to do */ } });
  fs.cpSync(new URL("js/", STATIC), path.join(dir, "js"), { recursive: true });
  fs.writeFileSync(path.join(dir, "package.json"), '{"type":"module"}');
  const fmt = await import(pathToFileURL(path.join(dir, "js", "format.js")).href);
  fmt.setStrings(STRINGS);
  copy = await import(pathToFileURL(path.join(dir, "js", "pages", "settings.js")).href);
  return copy;
}

test("flow: a page reload drops it", async () => {
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await a.choose("high");
  assert.equal(byClass(a.root, "p2-df").length, 1);
  const fresh = await reloaded();
  const root = a.page.sections.settings;
  fresh.render(root, a.makeCtx());
  assert.equal(byClass(root, "p2-df").length, 0, "a reloaded page starts at rest");
  assert.deepEqual(checkedOf(levelInputs(root)), ["low"]);
  assert.equal(a.log.preview.length, 1);
});

test("flow: a late save answer from one project does not touch another project's flow", async () => {
  const gate = {};
  const a = app({
    data: baseData(),
    backend: { ...saveFlow(), save: () => new Promise((resolve) => { gate.go = () => resolve(ok(S.save)); }) },
  });
  const keyA = a.key;
  await a.choose("high");
  btn(a.root, LOCAL_SAVE).click();
  await settle();
  assert.ok(btn(a.root, STRINGS.ed_saving));
  a.use(keyA + "-b", baseData());
  await a.choose("medium");
  assert.equal(byClass(a.root, "p2-df").length, 1);
  assert.ok(btn(a.root, LOCAL_SAVE), "project B has its own Save, and it is on");
  assert.equal(btn(a.root, STRINGS.ed_saving), undefined);
  gate.go();
  await settle();
  assert.equal(strips(a.root).length, 0, "the saved strip of A is not drawn in B");
  assert.equal(byClass(a.root, "p2-df").length, 1, "B's review stays");
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["medium"]);
  assert.ok(!off(btn(a.root, LOCAL_SAVE)));
  assert.equal(a.log.save.length, 1);
  // The file was written, so A's flow heard it: the picker stops saying Not saved for A, and B alone waits on Save.
  assert.ok(flowMod.notSavedProjects().includes(a.key) && !flowMod.notSavedProjects().includes(keyA), "A no longer waits on Save");
  assert.ok(a.log.shell >= 1, "the project picker is asked to draw again");
  // Back in A the change is gone and the saved result waits in the foot, with Save and the preview nowhere.
  a.use(keyA, baseData());
  assert.equal(strips(a.root).length, 1);
  assert.deepEqual(strips(a.root).map((n) => tag(n, "button").map(text)), [[STRINGS.ed_undo]]);
  assert.equal(byClass(a.root, "p2-df").length, 0);
  assert.equal(btn(a.root, LOCAL_SAVE), undefined);
  assert.equal(flowMod.notSavedProjects().includes(keyA), false);
});

test("flow: a late stale save answer drops the put-away preview, so A asks for a new one", async () => {
  const gate = {};
  const a = app({
    data: baseData(),
    backend: { ...saveFlow(), save: () => new Promise((resolve) => { gate.go = () => resolve({ kind: "stale", res: { status: 409 }, data: { error: "stale" } }); }) },
  });
  const keyA = a.key;
  await a.choose("high");
  btn(a.root, LOCAL_SAVE).click();
  await settle();
  a.use(keyA + "-b", baseData());
  gate.go();
  await settle();
  const asked = a.log.preview.length;
  a.use(keyA, baseData());
  await settle();
  assert.equal(strips(a.root).length, 0, "a stale answer leaves no saved result");
  assert.equal(a.log.preview.length, asked + 1, "the dropped preview is asked for again, not reused");
});

test("flow: a late undo answer from one project does not touch another project's strip", async () => {
  const gate = {};
  const a = app({
    data: afterSave(),
    backend: { ...saveFlow(), undo: () => new Promise((resolve) => { gate.go = () => resolve(ok(S.undo)); }) },
  });
  const keyA = a.key;
  await a.press(STRINGS.ed_undo);
  assert.ok(off(btn(a.root, STRINGS.ed_undo)), "A is busy");
  a.use(keyA + "-b", afterSave());
  assert.ok(btn(a.root, STRINGS.ed_undo) && !off(btn(a.root, STRINGS.ed_undo)), "B has its own Undo");
  gate.go();
  await settle();
  assert.deepEqual(strips(a.root).map((n) => tag(n, "button").map(text)), [[STRINGS.ed_undo]], "B's strip is as it was");
  assert.ok(!off(btn(a.root, STRINGS.ed_undo)));
});

test("flow: a late undo answer lands in the put-away flow, so A shows the result and not a spent Undo", async () => {
  const gate = {};
  const a = app({
    data: afterSave(),
    backend: { ...saveFlow(), undo: () => new Promise((resolve) => { gate.go = () => resolve(ok(S.undo)); }) },
  });
  const keyA = a.key;
  await a.press(STRINGS.ed_undo);
  a.use(keyA + "-b", afterSave());
  gate.go();
  await settle();
  a.use(keyA, afterSave());
  assert.equal(btn(a.root, STRINGS.ed_undo), undefined, "the Undo is spent");
  assert.ok(btn(a.root, STRINGS.ed_dismiss), "the result waits with Dismiss");
});

test("flow: a preview answer from one project is dropped when the page is on another", async () => {
  const gate = {};
  const a = app({ data: baseData(), backend: { preview: () => new Promise((resolve) => { gate.go = () => resolve(ok(S.previews.high)); }) } });
  const keyA = a.key;
  lvl(a.root, "high").dispatch("change");
  await settle();
  a.use(keyA + "-b", baseData());
  gate.go();
  await settle();
  assert.equal(byClass(a.root, "p2-df").length, 0);
  a.use(keyA, baseData());
  await settle();
  assert.equal(a.log.preview.length, 2, "A asks again for a preview that was dropped, once");
  a.draw();
  assert.equal(a.log.preview.length, 2, "and not again for the same data");
  gate.go();
  await settle();
  assert.equal(byClass(a.root, "p2-df").length, 1);
});

test("settle: a chosen level that becomes the running one after a refresh clears the flow", async () => {
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await a.choose("high");
  assert.equal(byClass(a.root, "p2-df").length, 1);
  a.st.targets = a.wrapT(S.after_save.targets);
  a.draw();
  await settle();
  assert.equal(byClass(a.root, "p2-df").length, 0);
  assert.equal(byClass(a.root, "p2-df").length, 0);
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["high"], "high is the running level now");
  assert.ok(levelInputs(a.root).every((r) => !off(r)));
  assert.equal(liveRows(a.root).length, 0);
  assert.equal(text(byClass(a.rail(), "s4-rh")[0]), STRINGS.why_h);
  assert.equal(a.log.preview.length, 1);
});

test("settle: a row that goes grey on a refresh clears, and lands on the local file or on nothing", async () => {
  // The project row is picked, then the fresh files grey it: the local file is the preselect, so it lands there.
  const first = trioLocal();
  const pvs = real("project_only").previews.project;
  const a = app({ data: baseData({ targets: first }), backend: { preview: async (t, v) => ok(pvs[v]) } });
  await a.choose("medium");
  assert.deepEqual(a.log.preview.map((p) => p[0]), [targetOf(first, "local").target], "the preselect is previewed");
  await a.pickRow("project");
  assert.deepEqual(checkedOf(rowInputs(a.root)), ["project"]);
  const second = clone(first);
  grey(second, "project");
  a.st.targets = a.wrapT(second);
  a.draw();
  await settle();
  assert.deepEqual(checkedOf(rowInputs(a.root)), ["local"], "the cleared project row lands on the local file");
  assert.deepEqual(a.log.preview.map((p) => p[0]), [targetOf(first, "local").target, "t-proj", targetOf(first, "local").target]);
  assert.equal(byClass(a.root, "p2-df").length, 1);
  // With no preselect it lands on nothing, and the user row stays unpicked.
  const b = app({ data: baseData({ targets: trio() }), backend: { preview: async (t, v) => ok(pvs[v]) } });
  await b.choose("medium");
  await b.pickRow("project");
  const gone = trio();
  grey(gone, "project");
  b.st.targets = b.wrapT(gone);
  b.draw();
  await settle();
  assert.deepEqual(checkedOf(rowInputs(b.root)), [], "never another shared row");
  assert.equal(byClass(b.root, "p2-df").length, 0, "the review is cleared");
  assert.deepEqual(noteTexts(b.rail()), [STRINGS.ed_pick_file]);
  assert.equal(b.log.preview.length, 1, "no new preview for nothing");
  assert.ok(!off(rowIn(b.root, "user")));
});

test("settle: the level itself going away or the files going all grey clears or relabels the rail", async () => {
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await a.choose("xhigh");
  const gone = clone(S.start.targets);
  shut(gone, "xhigh");
  a.st.targets = a.wrapT(gone);
  a.draw();
  await settle();
  assert.equal(byClass(a.root, "p2-df").length, 0);
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["xhigh"], "the level stays chosen");
  assert.equal(notes(a.root).length, 1, "and the rail says nothing can be saved there");
  assert.equal(text(byClass(a.rail(), "p2-nt-h")[0]), "▲" + T("ed_nosave_level", { level: "xhigh" }));
  const none = clone(S.start.targets);
  none.levels = none.levels.filter((l) => l.level !== "xhigh");
  a.st.targets = a.wrapT(none);
  a.draw();
  await settle();
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["low"], "a level that is not offered any more clears the flow");
  assert.equal(notes(a.root).length, 0);
});

// ---------------------------------------------------------------- focus

test("focus: an edit control that held focus has it again after a draw from new data, and the heading does not take it", async () => {
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await a.choose("high");
  const high = lvl(a.root, "high");
  high.focus();
  a.draw();
  assert.notEqual(lvl(a.root, "high"), high, "the nodes were rebuilt");
  assert.equal(FElement.focused, lvl(a.root, "high"));
  assert.ok(lvl(a.root, "high").hasAttribute("checked"));
  const cancel = btn(a.root, STRINGS.ed_cancel);
  cancel.focus();
  a.draw();
  assert.equal(FElement.focused, btn(a.root, STRINGS.ed_cancel));
  // A row keeps it too.
  const row = rowIn(a.root, "local");
  row.focus();
  a.draw();
  assert.equal(FElement.focused.getAttribute("data-edit-focus"), "row:local");
  assert.notEqual(FElement.focused, row);
  // The strip lives in the foot, and its button keeps focus as well.
  const s = app({ data: afterSave() });
  const undo = btn(s.root, STRINGS.ed_undo);
  undo.focus();
  s.draw();
  assert.equal(FElement.focused, btn(s.root, STRINGS.ed_undo));
  assert.notEqual(FElement.focused, undo);
});

test("focus: a focus on the page that isn't an edit control is not moved into one", () => {
  const a = app({ data: baseData() });
  byClass(a.root, "s4-chead")[0].focus();
  a.draw();
  assert.equal(levelInputs(a.root).includes(FElement.focused) || rowInputs(a.root).includes(FElement.focused), false);
});

test("pick: after a preview that failed, the rail keeps the Pick a file frame with no note, Save is off, and Cancel is the way back", async () => {
  const a = app({ data: baseData(), backend: { preview: async () => bad("error", 500, { error: "write_failed" }) } });
  await a.choose("high");
  const err = byClass(a.rail(), "p2-nt-err")[0];
  assert.ok(a.rail().contains(err), "the error notice is in the rail");
  assert.equal(text(byClass(a.rail(), "s4-rh")[0]), STRINGS.review_h, "the frame stays under the notice");
  assert.deepEqual(bigs(a.root), ["low", "→", "high"]);
  assert.deepEqual(footTexts(a), [STRINGS.ed_save_plain, STRINGS.ed_cancel], "Save is off and Cancel is there");
  assert.ok(off(footButtons(a)[0]) && !off(footButtons(a)[1]));
  tag(err, "button")[0].click();
  await settle();
  assert.equal(byClass(a.root, "p2-nt").length, 0);
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["high"]);
  assert.equal(text(byClass(a.rail(), "s4-rh")[0]), STRINGS.review_h, "Dismiss leaves the frame");
  assert.deepEqual(noteTexts(a.rail()), [], "no note: a file is picked and its preview failed");
  assert.deepEqual(buttons(a.rail()).map(text), []);
  assert.deepEqual(footTexts(a), [STRINGS.ed_save_plain, STRINGS.ed_cancel]);
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["low"]);
  assert.equal(buttons(a.root).length, 0);
});

test("focus: a row that goes grey on a refresh leaves focus in its group", async () => {
  const pvs = real("project_only").previews.project;
  const a = app({ data: baseData({ targets: trio() }), backend: { preview: async (t, v) => ok(pvs[v]) } });
  await a.choose("medium");
  await a.pickRow("project");
  const project = rowIn(a.root, "project");
  project.focus();
  assert.equal(FElement.focused, project);
  const gone = trio();
  grey(gone, "project");
  a.st.targets = a.wrapT(gone);
  a.draw();
  await settle();
  const now = FElement.focused;
  assert.equal(now.getAttribute("data-edit-focus"), "row:user", "the first enabled row takes it");
  assert.ok(!off(now));
  assert.ok(off(rowIn(a.root, "project")), "the grey row is off, and a disabled radio takes no focus");
  // With no row left open, focus falls to the checked level radio.
  const none = trio();
  grey(none, "project");
  grey(none, "user", "not_editable", ["medium"]); // medium has no open row, and the other levels keep the project saveable
  a.st.targets = a.wrapT(none);
  rowIn(a.root, "user").focus();
  a.draw();
  await settle();
  assert.equal(FElement.focused, lvl(a.root, "medium"), "the checked level radio");
  // The checked row comes first when there is one.
  const c = app({ data: baseData({ targets: trio() }), backend: { preview: async (t, v) => ok(pvs[v]) } });
  await c.choose("medium");
  await c.pickRow("user");
  rowIn(c.root, "user").focus();
  const g2 = trio();
  open(g2, "project", ["medium"]);
  c.st.targets = c.wrapT(g2);
  rowIn(c.root, "project").focus();
  const g3 = trio();
  grey(g3, "project");
  c.st.targets = c.wrapT(g3);
  c.draw();
  await settle();
  assert.equal(FElement.focused.getAttribute("data-edit-focus"), "row:user", "the checked row");
});

test("focus: the running level goes off when a level is chosen, and focus on it falls to the checked level radio", async () => {
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  lvl(a.root, "low").focus();
  assert.equal(FElement.focused, lvl(a.root, "low"));
  await a.choose("high");
  assert.ok(off(lvl(a.root, "low")));
  assert.equal(FElement.focused, lvl(a.root, "high"));
  assert.equal(FElement.focused.getAttribute("data-edit-focus"), "radio:high");
});

test("focus: after a save, focus goes to Undo when the edit can be undone, else to the checked level", async () => {
  const a = app({ data: baseData(), backend: saveFlow() });
  await a.choose("high");
  btn(a.root, LOCAL_SAVE).click();
  await settle();
  assert.equal(S.save.edit.undoable, true);
  assert.equal(FElement.focused, btn(a.root, STRINGS.ed_undo));
  const body = clone(S.save);
  body.edit.undoable = false;
  const b = app({ data: baseData(), backend: { ...saveFlow(), save: async () => ({ ...ok(body), after: S.after_save }) } });
  await b.choose("high");
  btn(b.root, LOCAL_SAVE).click();
  await settle();
  assert.equal(FElement.focused.getAttribute("type"), "radio");
  assert.equal(FElement.focused, lvl(b.root, "high"), "the checked level, which runs now");
});

// ---------------------------------------------------------------- text nodes

const HOSTILE = ["<img src=x onerror=alert(1)>", "</code><script>alert(1)</script>"];

test("text nodes: diff lines are drawn as text, never as markup, even when they hold tags", async () => {
  const pv = clone(S.previews.high);
  const lines = pv.diff.hunks[0].lines;
  lines.find((l) => l.kind === "add").text = HOSTILE[0];
  lines.find((l) => l.kind === "context").text = HOSTILE[1];
  const made = [];
  const before = parsed.length;
  const a = app({ data: baseData(), backend: { preview: async () => ok(pv) } });
  const create = document.createTextNode.bind(document);
  document.createTextNode = (data) => { made.push(String(data)); return create(data); };
  try {
    await a.choose("high");
    assert.equal(a.root.find((n) => n.tagName === "img" || n.tagName === "script").length, 0);
    assert.equal(parsed.length, before, "no text was handed to a markup setter");
    const codes = tag(byClass(a.root, "p2-df")[0], "code");
    const add = codes.find((c) => c.textContent === HOSTILE[0]);
    const ctx = codes.find((c) => c.textContent === HOSTILE[1]);
    assert.ok(add && ctx, "the code element's text equals the line exactly");
    for (const code of [add, ctx]) {
      assert.deepEqual(code.childNodes.map((c) => c.nodeType), [3], "one text node and nothing else");
      assert.equal(code.childNodes[0].data, code.textContent);
    }
    for (const line of HOSTILE) assert.ok(made.includes(line), "createTextNode made " + line);
    assert.equal(a.root.find((n) => n.tagName === "code" && n.find((c) => c.tagName).length > 1).length, 0, "no element hides inside a code element except a mark");
  } finally {
    document.createTextNode = create;
  }
});

test("text nodes: a mark splits a changed pair into three text parts and holds nothing else", async () => {
  const a = app({ data: baseData(), backend: { preview: async () => ok(S.previews.high) } });
  await a.choose("high");
  const del = byClass(a.root, "p2-del")[0];
  const code = tag(del, "code")[0];
  assert.deepEqual(code.childNodes.map((c) => c.nodeType), [3, 1, 3]);
  assert.deepEqual(code.childNodes.map((c) => c.textContent), ['  "effortLevel": "', "low", '"']);
  assert.equal(code.childNodes[1].tagName, "mark");
  assert.deepEqual(code.childNodes[1].childNodes.map((c) => c.nodeType), [3]);
});

test("text nodes: every server value on the page is text, so a hostile path and value make no element", async () => {
  const evil = HOSTILE[0];
  const pv = clone(S.previews.high);
  pv.diff.file_display = evil;
  const targets = clone(S.start.targets);
  targets.targets[0].file_display = evil;
  targets.runs_as = evil;
  for (const f of targets.files) { f.file_display = evil; f.value = evil; }
  for (const level of targets.levels) { level.limits = [{ kind: "cap", value: evil, file_display: evil, line: 1, lock_reason: "cap_later" }]; }
  const history = clone(S.after_save.history);
  history.rows[0].backup_display = evil;
  history.rows[0].file_display = evil;
  history.rows[0].old_value = evil;
  const a = app({ data: { settings: S.start.settings, targets, history }, backend: { preview: async () => ok(pv) } });
  assert.equal(a.root.find((n) => n.tagName === "img").length, 0);
  assert.ok(a.root.textContent.includes(evil));
  await a.choose("high");
  assert.equal(a.root.find((n) => n.tagName === "img").length, 0);
  assert.ok(a.root.textContent.includes(evil));
  assert.equal(parsed.length, 0);
});

test("text nodes: the card files hold no call that parses markup, no style, and every diff text goes through h()", () => {
  const source = ["edit_card", "edit_flow", "edit_pick", "edit_review", "edit_foot", "edit_ui"]
    .map((name) => fs.readFileSync(new URL("js/" + name + ".js", STATIC), "utf8")).join("\n");
  for (const banned of ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "DOMParser", "createContextualFragment"]) {
    assert.equal(source.includes(banned), false, banned);
  }
  assert.equal(/\.style\b|\bstyle\s*:/.test(source.replace(/\/\/.*$/gm, "")), false);
  // The diff text is the argument of h("code", ...), and h() makes a text node of a string child.
  assert.match(source, /h\("code", null, parts \|\| text\(line\.text\)\)/);
  const h = fs.readFileSync(new URL("js/h.js", STATIC), "utf8");
  assert.match(h, /document\.createTextNode\(String\(child\)\)/);
  // edit_pick.js has no DOM at all.
  const pure = fs.readFileSync(new URL("js/edit_pick.js", STATIC), "utf8").replace(/\/\/.*$/gm, "");
  assert.equal(/document|window|import /.test(pure), false, "the pure module touches no DOM and imports nothing");
});

test("css: no element on the page carries a style from the card, the review or the strips", async () => {
  const a = app({ data: afterSave(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await a.choose("high");
  const inCard = [a.body(), a.rail(), a.foot()].flatMap((slot) => flat(slot));
  for (const n of inCard) {
    if (n.styleMap) assert.deepEqual(Object.keys(n.styleMap), [], n.tagName);
    if (n.getAttribute) assert.equal(n.getAttribute("style"), null);
  }
});

// ---------------------------------------------------------------- review fixes

test("fix: an answer with a status and an unknown code is never the network line", async () => {
  const a = app({ data: baseData(), backend: { preview: async () => bad("error", 500, { error: "write_failed" }) } });
  await a.choose("high");
  const alert = byClass(a.rail(), "p2-nt-err")[0];
  assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + STRINGS.ed_err_forbidden);
  assert.notEqual(STRINGS.ed_err_forbidden, STRINGS.ed_err_network);
  const none = app({ data: baseData(), backend: { preview: async () => bad("error", 0, null) } });
  await none.choose("high");
  assert.equal(text(byClass(byClass(none.rail(), "p2-nt-err")[0], "p2-nt-h")[0]), "✕" + STRINGS.ed_err_network);
});

test("fix: an undo that answers write_failed shows the failed-write strip with Dismiss and no Try again", async () => {
  const a = app({
    data: afterSave(),
    backend: { ...saveFlow(), undo: async () => bad("error", 500, { error: "write_failed" }) },
  });
  await a.press(STRINGS.ed_undo);
  const alert = byClass(a.root, "p2-nt-err")[0];
  assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + STRINGS.ed_fail_h);
  assert.equal(text(tag(alert, "p")[0]), T("ed_fail_t", { file: "settings.local.json" }));
  assert.deepEqual(tag(alert, "button").map(text), [STRINGS.ed_dismiss]);
  assert.equal(btn(a.root, STRINGS.ed_try_again), undefined);
  assert.equal(FElement.focused, tag(alert, "button")[0]);
  assert.equal(anyKey(a.root), false);
});

// ---------------------------------------------------------------- the foot, Not saved and the other cells

const pendOf = (root) => byClass(root, "s4-stat").concat(byClass(root, "s5-more")).filter((n) => byClass(n, "s5-pend").length > 0);
const cellOf = (root, key) => byClass(root, "s4-stat").find((n) => n.getAttribute("data-setting") === key);
const countOf = (root, label) => buttons(root).filter((b) => text(b) === label).length;
const saveButtons = (root) => buttons(root).filter((b) => /^Save/.test(text(b)));
const never = () => new Promise(() => {});
// The flows are kept for the whole run, so a check that counts projects with a change waiting starts from a mode
// change, which clears every flow.
function fresh() {
  app({ mode: "off", data: baseData({ targets: offAnswer(S.start.targets) }) });
  assert.deepEqual(flowMod.notSavedProjects(), []);
}

test("foot: Save and Cancel sit side by side in the foot, and the rail holds neither", async () => {
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await a.choose("high");
  const pick = slotOf(a.root, "pick");
  assert.ok(a.foot().contains(pick));
  const [save, cancel] = tag(pick, "button");
  assert.equal(text(save), LOCAL_SAVE);
  assert.equal(text(cancel), STRINGS.ed_cancel);
  assert.equal(save.parentNode, cancel.parentNode, "one parent, so one grid row");
  assert.ok(hasClass(save, "p2-pri") && hasClass(save, "s4-wide"));
  assert.ok(hasClass(cancel, "s4-wide") && !hasClass(cancel, "p2-pri"));
  assert.equal(buttons(a.rail()).length, 0);
  assert.equal(saveButtons(a.root).length, 1, "no second Save in the page, for a narrow window or any other");
  assert.equal(byClass(a.root, "s5-dock").length + byClass(a.root, "s4-inl").length, 0);
  assert.ok(hasClass(a.foot().parentNode, "s4-rf") && hasClass(a.foot().parentNode, "s5-rf"), "the foot is the rail's own foot");
});

test("foot: every state with a chosen level has a way back, and the page holds one Save at most", async () => {
  const pvs = real("project_only").previews.project;
  const states = [];
  // Pick a file
  const pickFile = app({ data: baseData({ targets: trio() }), backend: { preview: async (t, v) => ok(pvs[v]) } });
  await pickFile.choose("medium");
  states.push(["pick a file", pickFile]);
  // A preview on its way
  const loading = app({ data: baseData(), backend: { preview: never } });
  await loading.choose("high");
  states.push(["loading", loading]);
  // A preview that failed
  const failedPv = app({ data: baseData(), backend: { preview: async () => bad("error", 500, { error: "write_failed" }) } });
  await failedPv.choose("high");
  states.push(["failed preview", failedPv]);
  // The review: plain, with a warning, with no change, with a damaged record
  const plain = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await plain.choose("high");
  states.push(["plain", plain]);
  const warn = app({ data: baseData(), backend: { preview: async () => ok(warned()) } });
  await warn.choose("high");
  states.push(["warning", warn]);
  const n = real("no_change");
  const noChangeTargets = clone(n.targets);
  open(noChangeTargets, "project", ["high"]);
  const same = app({ data: { settings: n.settings, targets: noChangeTargets, history: n.history }, backend: { preview: async () => ok(n.preview_same) } });
  await same.choose("high");
  await same.pickRow("project");
  states.push(["no change", same]);
  const l = real("ledger");
  const ledgerApp = app({ data: { settings: l.settings, targets: l.targets, history: l.history }, backend: { preview: async (t, v) => ok(l.previews.local[v]) } });
  await ledgerApp.choose("high");
  states.push(["ledger", ledgerApp]);
  // A failed write
  const failedSave = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("error", 500, { error: "write_failed", file_unchanged: true }) } });
  await failedSave.choose("high");
  await failedSave.press(LOCAL_SAVE);
  states.push(["failed save", failedSave]);
  // A save on its way
  const busy = app({ data: baseData(), backend: { ...saveFlow(), save: never } });
  await busy.choose("high");
  await busy.press(LOCAL_SAVE);
  states.push(["busy", busy]);
  for (const [name, a] of states) {
    assert.ok(a.log.draws >= 1);
    assert.equal(countOf(a.root, STRINGS.ed_cancel), 1, name + ": one Cancel");
    assert.ok(a.foot().contains(btn(a.root, STRINGS.ed_cancel)), name + ": in the foot");
    assert.ok(saveButtons(a.root).length <= 1, name + ": at most one Save");
    assert.deepEqual(buttons(a.rail()).map(text).filter((l) => l !== STRINGS.ed_dismiss), [], name + ": no Save or Cancel in the rail");
    assert.equal(byClass(a.root, "s5-dock").length, 0, name);
  }
  assert.ok(off(btn(states[0][1].root, STRINGS.ed_save_plain)) && off(btn(states[1][1].root, STRINGS.ed_save_plain)) && off(btn(states[2][1].root, STRINGS.ed_save_plain)), "Save is off until a preview is drawn");
  assert.equal(saveButtons(ledgerApp.root).length, 0, "no Save for a damaged record");
  assert.equal(saveButtons(same.root).length, 0, "no Save for a file that holds the value");
  // The stop rows and a result frame carry their own way back in the rail.
  const s = real("model_limit");
  const stopTargets = clone(s.targets);
  shut(stopTargets, "xhigh");
  const stop = app({ data: { settings: s.settings, targets: stopTargets, history: s.history } });
  await stop.choose("xhigh");
  assert.deepEqual(tag(stop.rail(), "button").map(text), [STRINGS.ed_cancel]);
  assert.equal(stop.foot().childNodes.every((slot) => slot.childNodes.length === 0), true, "nothing waits to be saved, so the foot is empty");
  const raced = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("raced", 409, { error: "raced", backup_display: "config/routing-dashboard/backups/x/000001-a.bak" }) } });
  await raced.choose("high");
  await raced.press(LOCAL_SAVE);
  assert.deepEqual(tag(raced.rail(), "button").map(text), [STRINGS.ed_dismiss]);
  assert.equal(footButtons(raced).length, 0);
});

test("foot: the waiting frame has the headline and no Pick a file note while a preview is on its way", async () => {
  const a = app({ data: baseData(), backend: { preview: never } });
  await a.choose("high");
  assert.equal(text(byClass(a.rail(), "s4-rh")[0]), STRINGS.review_h);
  assert.deepEqual(bigs(a.root), ["low", "→", "high"]);
  assert.equal(headNote(a.root), STRINGS.ed_runs);
  assert.deepEqual(noteTexts(a.rail()), []);
  assert.deepEqual(footTexts(a), [STRINGS.ed_save_plain, STRINGS.ed_cancel]);
  assert.equal(text(byClass(slotOf(a.root, "pick"), "s4-hint")[0]), STRINGS.ed_nothing_yet);
  assert.equal(byClass(a.root, "p2-df").length, 0, "no diff yet");
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.equal(footButtons(a).length, 0);
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["low"]);
});

test("reviewFoot: each branch draws its own foot", async () => {
  // plain
  const plain = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await plain.choose("high");
  assert.deepEqual(footTexts(plain), [LOCAL_SAVE, STRINGS.ed_cancel]);
  assert.ok(hasClass(footButtons(plain)[0], "p2-pri"));
  assert.equal(text(byClass(slotOf(plain.root, "pick"), "s4-hint")[0]), STRINGS.ed_nothing_yet);
  // warning: Save anyway, not primary
  const warn = app({ data: baseData(), backend: { preview: async () => ok(warned()) } });
  await warn.choose("high");
  assert.deepEqual(footTexts(warn), [STRINGS.ed_save_anyway, STRINGS.ed_cancel]);
  assert.ok(!hasClass(footButtons(warn)[0], "p2-pri"), "a pick with a warning has Save anyway, not primary");
  assert.ok(nts(warn.rail(), "warn").length === 1 && warn.rail().contains(nts(warn.rail(), "warn")[0]));
  // ledger: no Save, only Cancel, with its notice in the rail
  const l = real("ledger");
  const led = app({ data: { settings: l.settings, targets: l.targets, history: l.history }, backend: { preview: async (t, v) => ok(l.previews.local[v]) } });
  await led.choose("high");
  assert.deepEqual(footTexts(led), [STRINGS.ed_cancel]);
  assert.ok(nts(led.rail(), "warn").some((n) => text(byClass(n, "p2-nt-h")[0]) === "▲" + T("ed_ledger_preview_t", { file: "settings.local.json" })));
  // ledger_damaged on the preview alone, with no record in the history
  const flagged = clone(S.previews.high);
  flagged.ledger_damaged = true;
  const fl = app({ data: baseData(), backend: { preview: async () => ok(flagged) } });
  await fl.choose("high");
  assert.deepEqual(footTexts(fl), [STRINGS.ed_cancel], "the preview's own flag counts");
  // no change: Cancel and the note
  const n = real("no_change");
  const targets = clone(n.targets);
  open(targets, "project", ["high"]);
  const same = app({ data: { settings: n.settings, targets, history: n.history }, backend: { preview: async () => ok(n.preview_same) } });
  await same.choose("high");
  await same.pickRow("project");
  assert.deepEqual(footTexts(same), [STRINGS.ed_cancel]);
  assert.equal(text(byClass(slotOf(same.root, "pick"), "s4-hint")[0]), STRINGS.ed_no_change_note);
  // failed: Try again (primary) and Cancel, with the error in the rail body
  let calls = 0;
  const failed = app({ data: baseData(), backend: { ...saveFlow(), save: async () => (++calls === 1 ? bad("error", 500, { error: "write_failed", file_unchanged: true }) : { ...ok(S.save), after: S.after_save }) } });
  await failed.choose("high");
  await failed.press(LOCAL_SAVE);
  assert.deepEqual(footTexts(failed), [STRINGS.ed_try_again, STRINGS.ed_cancel]);
  assert.ok(hasClass(footButtons(failed)[0], "p2-pri"));
  assert.ok(failed.rail().contains(byClass(failed.rail(), "p2-nt-err")[0]), "the notice is in the rail body");
  assert.equal(FElement.focused, footButtons(failed)[0], "focus is on Try again");
  // busy: Saving with both buttons off, and the status line for a screen reader
  const gate = {};
  const busy = app({ data: baseData(), backend: { ...saveFlow(), save: () => new Promise((resolve) => { gate.go = () => resolve({ ...ok(S.save), after: S.after_save }); }) } });
  await busy.choose("high");
  await busy.press(LOCAL_SAVE);
  assert.deepEqual(footTexts(busy), [STRINGS.ed_saving, STRINGS.ed_cancel]);
  assert.ok(footButtons(busy).every(off));
  assert.equal(footButtons(busy)[0].getAttribute("aria-busy"), "true");
  const saying = byClass(slotOf(busy.root, "pick"), "sr")[0];
  assert.equal(saying.getAttribute("role"), "status");
  assert.equal(text(saying), T("ed_saving_sr", { file: "settings.local.json" }));
  gate.go();
  await settle();
  assert.equal(footButtons(busy).length, 0, "the saved change has no Save left");
});

test("foot: a saved result shows with Undo and its icon, and a null backup path shows no path line", async () => {
  const saved = clone(S.save);
  saved.edit.backup_display = null;
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]), save: async () => ({ ...ok(saved), after: S.after_save }) } });
  await a.choose("high");
  await a.press(LOCAL_SAVE);
  assert.equal(okMark(a.root), "✓");
  assert.equal(okLine(a.root), T("ed_saved_t", { file: "settings.local.json", level: "high" }));
  assert.equal(pathLine(a.root), null, "no backup path line");
  assert.equal(byClass(stripOf(a.root), "pa").length, 0);
  assert.equal(/\bnull\b/.test(a.root.textContent) || /undefined/.test(a.root.textContent), false);
  const undo = btn(a.root, STRINGS.ed_undo);
  assert.ok(undo && a.foot().contains(undo));
  assert.equal(byClass(undo, "ic").length, 1);
  assert.equal(tag(byClass(undo, "ic")[0], "path").length, 2);
  assert.equal(tag(byClass(undo, "ic")[0], "path")[0].getAttribute("d"), "M4 9h11a5 5 0 0 1 0 10H9");
  assert.equal(tag(byClass(undo, "ic")[0], "path")[1].getAttribute("d"), "M8 5L4 9l4 4");
  // An undone result: Dismiss, and the restored path line only when there is a path.
  const none = clone(S.undo);
  none.restored_from_display = null;
  const b = app({ data: afterSave(), backend: { ...saveFlow(), undo: async () => ({ ...ok(none), after: S.after_undo }) } });
  await b.press(STRINGS.ed_undo);
  assert.equal(okMark(b.root), "✓");
  assert.equal(pathLine(b.root), null);
  assert.ok(btn(b.root, STRINGS.ed_dismiss));
  // A warning result uses the same frame with the triangle.
  const c = real("changed_since_save");
  const w = app({ data: afterSave(), backend: { undo: async () => bad("error", 409, c.undo_answer), refresh: () => ({ settings: c.settings, targets: c.targets, history: c.history }) } });
  await w.press(STRINGS.ed_undo);
  assert.equal(okMark(w.root), "▲");
  assert.ok(hasClass(okRow(w.root), "s4-ok"));
});

test("not saved: a chosen level marks the Effort cell with no page render, and Cancel clears it", async () => {
  fresh();
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  assert.equal(pendOf(a.root).length, 0);
  assert.equal(a.log.shell, 0);
  await a.choose("high");
  assert.equal(a.log.draws, 1, "no page render");
  const cell = cellOf(a.root, "effortLevel");
  assert.equal(text(byClass(cell, "s5-pend")[0]), STRINGS.band_not_saved);
  assert.equal(byClass(cell, "st").length, 0, "the mark and word stand in place of the status");
  assert.equal(text(byClass(cell, "s4-sv")[0]), "low", "the cell keeps the value that runs");
  assert.equal(cell.getAttribute("aria-label"), "Effort, low, " + STRINGS.band_not_saved + ". " + STRINGS.band_cell_desc);
  assert.deepEqual(flowMod.notSavedProjects(), [a.key]);
  assert.equal(a.log.shell, 1, "the project picker is asked to draw again");
  // A row pick keeps it, and does not ask again.
  await a.choose("medium");
  assert.equal(pendOf(a.root).length, 1);
  assert.equal(a.log.shell, 1);
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.equal(pendOf(a.root).length, 0);
  assert.equal(byClass(cellOf(a.root, "effortLevel"), "st").length, 1, "the status is back");
  assert.deepEqual(flowMod.notSavedProjects(), []);
  assert.equal(a.log.shell, 2);
  assert.equal(a.log.draws, 1);
});

test("not saved: it stays until Save or Cancel, a save clears it, and a draw from new data keeps it", async () => {
  fresh();
  const a = app({ data: baseData(), backend: saveFlow() });
  await a.choose("high");
  a.draw();
  assert.equal(pendOf(a.root).length, 1, "a draw keeps it");
  a.draw();
  assert.equal(text(byClass(cellOf(a.root, "effortLevel"), "s5-pend")[0]), STRINGS.band_not_saved);
  await a.press(LOCAL_SAVE);
  assert.equal(pendOf(a.root).length, 0, "saved, so nothing waits");
  assert.deepEqual(flowMod.notSavedProjects(), []);
});

test("not saved: the two stop rows and the rest rows don't count", async () => {
  fresh();
  // A level held by the model: the stop panel.
  const s = real("model_limit");
  const stopTargets = clone(s.targets);
  shut(stopTargets, "xhigh");
  const stop = app({ data: { settings: s.settings, targets: stopTargets, history: s.history } });
  await stop.choose("xhigh");
  assert.equal(nts(stop.rail(), "warn").length, 1);
  assert.equal(pendOf(stop.root).length, 0, "the stop panel");
  assert.deepEqual(flowMod.notSavedProjects(), []);
  assert.equal(stop.log.shell, 0);
  // A level that nothing can save, with the project still able to save another.
  const u = real("user_unknown");
  const targets = clone(u.targets);
  for (const name of ["low", "medium", "high"]) shut(targets, name);
  fileOf(targets, "xhigh", "user").pickable = true;
  recount(targets);
  const none = app({ data: { settings: u.settings, targets, history: u.history } });
  await none.choose("high");
  assert.equal(text(byClass(none.rail(), "p2-nt-h")[0]), "▲" + T("ed_nosave_level", { level: "high" }));
  assert.equal(pendOf(none.root).length, 0, "nothing to save at this level");
  assert.deepEqual(flowMod.notSavedProjects(), []);
  // Pick a file and the review do count, and so does a preview on its way.
  const loading = app({ data: baseData(), backend: { preview: never } });
  await loading.choose("high");
  assert.equal(pendOf(loading.root).length, 1);
  assert.deepEqual(flowMod.notSavedProjects(), [loading.key]);
  const pickFile = app({ data: baseData({ targets: trio() }), backend: { preview: async () => ok(real("project_only").previews.project.medium) } });
  await pickFile.choose("medium");
  assert.equal(pendOf(pickFile.root).length, 1);
});

test("not saved: in More, with one visible cell, the summary and the list row carry the mark and word", async () => {
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await a.choose("high");
  // Another cell opens, and the band is narrow: Effort is behind More.
  settingsPage.render(a.root, { ...a.makeCtx(), route: { name: "settings", params: {}, query: { setting: "model" } } });
  byClass(a.root, "s5-a")[0].clientWidth = 343;
  bandMod.refitBand();
  const cells = byClass(a.root, "s4-stat").filter((n) => n.tagName === "a");
  assert.deepEqual(cells.map((n) => n.getAttribute("data-setting")), ["model"], "one visible cell");
  const more = byClass(a.root, "s5-more")[0];
  assert.equal(text(byClass(more, "s4-sw")[0]), STRINGS.band_not_saved);
  assert.equal(byClass(more, "s5-pend").length, 1);
  assert.match(more.getAttribute("aria-label"), /Effort not saved/);
  const row = byClass(a.root, "s5-lr").find((n) => n.getAttribute("data-setting") === "effortLevel");
  assert.equal(text(byClass(row, "s5-pend")[0]), STRINGS.band_not_saved);
  assert.equal(byClass(row, "st").length, 0);
  // Cancel on that cell draws the band again at the same width, and clears the mark.
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.equal(byClass(a.root, "s5-pend").length, 0);
  assert.deepEqual(byClass(a.root, "s4-stat").filter((n) => n.tagName === "a").map((n) => n.getAttribute("data-setting")), ["model"], "the width is kept");
});

test("not saved: a project switch and back keeps it, and the project picker is told which projects wait", async () => {
  fresh();
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  const keyA = a.key;
  await a.choose("high");
  assert.deepEqual(flowMod.notSavedProjects(), [keyA]);
  a.use(keyA + "-b", baseData());
  assert.equal(pendOf(a.root).length, 0, "the other project has nothing waiting");
  assert.deepEqual(flowMod.notSavedProjects(), [keyA], "the project put away still waits");
  await a.choose("medium");
  assert.deepEqual(flowMod.notSavedProjects().sort(), [keyA, keyA + "-b"].sort());
  a.use(keyA, baseData());
  assert.equal(pendOf(a.root).length, 1, "back on the first project, its mark is back");
  assert.deepEqual(flowMod.notSavedProjects().sort(), [keyA, keyA + "-b"].sort());
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.deepEqual(flowMod.notSavedProjects(), [keyA + "-b"]);
  // A put-away project whose level can't be saved, or has none chosen, does not wait.
  a.use(keyA + "-c", baseData());
  assert.deepEqual(flowMod.notSavedProjects().sort(), [keyA + "-b"].sort());
  a.use(keyA + "-b", baseData());
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.deepEqual(flowMod.notSavedProjects(), []);
});

test("cells: picking Model during a change keeps the review, the foot and Not saved, and Effort brings the live picker back", async () => {
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await a.choose("high");
  settingsPage.render(a.root, { ...a.makeCtx(), route: { name: "settings", params: {}, query: { setting: "model" } } });
  // the body is the read-only frame of Model
  assert.equal(levelInputs(a.root).length + rowInputs(a.root).length, 0);
  assert.equal(text(byClass(a.root, "s4-lock")[0]), STRINGS.ro_lock);
  assert.equal(text(byClass(a.root, "s4-lab")[0]), STRINGS.f_model);
  // the rail keeps the review, and the foot keeps Save and Cancel
  assert.equal(text(byClass(a.rail(), "s4-rh")[0]), STRINGS.review_h);
  assert.deepEqual(bigs(a.root), ["low", "→", "high"]);
  assert.equal(byClass(a.root, "p2-df").length, 1);
  assert.deepEqual(footTexts(a), [LOCAL_SAVE, STRINGS.ed_cancel]);
  assert.equal(saveButtons(a.root).length, 1);
  // and the band says Not saved on the Effort cell
  assert.equal(text(byClass(cellOf(a.root, "effortLevel"), "s5-pend")[0]), STRINGS.band_not_saved);
  // Cancel on Model ends the change
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.equal(byClass(a.root, "p2-df").length, 0);
  assert.equal(pendOf(a.root).length, 0);
  assert.equal(text(byClass(a.rail(), "s4-rh")[0]), STRINGS.why_h);
  // a cell with no change in progress is untouched: the plain rail, no foot
  const plain = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  settingsPage.render(plain.root, { ...plain.makeCtx(), route: { name: "settings", params: {}, query: { setting: "model" } } });
  assert.equal(text(byClass(plain.rail(), "s4-rh")[0]), STRINGS.why_h);
  assert.equal(footButtons(plain).length, 0);
  // Effort again, with the same pick
  const b = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await b.choose("high");
  settingsPage.render(b.root, { ...b.makeCtx(), route: { name: "settings", params: {}, query: { setting: "model" } } });
  settingsPage.render(b.root, { ...b.makeCtx(), route: { name: "settings", params: {}, query: { setting: "effortLevel" } } });
  assert.deepEqual(checkedOf(levelInputs(b.root)), ["high"], "the live picker, with the same pick");
  assert.deepEqual(checkedOf(rowInputs(b.root)), ["local"]);
  assert.equal(b.log.preview.length, 1, "no new preview");
  assert.deepEqual(footTexts(b), [LOCAL_SAVE, STRINGS.ed_cancel]);
});

test("cells: a Save pressed on another cell shows its result in the foot with Undo", async () => {
  // The save answer carries no new data, so the page is not drawn again on Effort and the card must draw the result.
  const a = app({ data: baseData(), backend: { ...saveFlow(), save: async () => ok(S.save) } });
  await a.choose("high");
  settingsPage.render(a.root, { ...a.makeCtx(), route: { name: "settings", params: {}, query: { setting: "model" } } });
  btn(a.root, LOCAL_SAVE).click();
  await settle();
  assert.equal(a.log.save.length, 1);
  assert.deepEqual(strips(a.root).map((n) => tag(n, "button").map(text)), [[STRINGS.ed_undo]]);
  // At rest, a cell that isn't Effort still hides the last change.
  const plain = app({ data: afterSave(), backend: saveFlow() });
  settingsPage.render(plain.root, { ...plain.makeCtx(), route: { name: "settings", params: {}, query: { setting: "model" } } });
  assert.equal(strips(plain.root).length, 0);
});

test("settle: a new targets answer asks for the preview again, and the same answer drawn again does not", async () => {
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await a.choose("high");
  assert.equal(a.log.preview.length, 1);
  a.draw();
  await settle();
  assert.equal(a.log.preview.length, 1, "the same targets object, so no new preview");
  a.st.targets = a.wrapT(clone(S.start.targets));
  a.draw();
  await settle();
  assert.equal(a.log.preview.length, 2, "new targets, so the files may have changed under the preview");
  assert.equal(byClass(a.root, "p2-df").length, 1);
});

test("settle: a refresh that brings a project lock or no save clears the chosen level and its foot", async () => {
  for (const patch of [{ project_lock: "not_repo_root" }, { saveable: false }]) {
    const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
    await a.choose("high");
    assert.equal(byClass(a.root, "p2-df").length, 1);
    a.st.targets = a.wrapT({ ...clone(S.start.targets), ...patch });
    a.draw();
    await settle();
    assert.equal(byClass(a.root, "p2-df").length, 0, JSON.stringify(patch));
    assert.equal(pendOf(a.root).length, 0, JSON.stringify(patch));
    assert.equal(flowMod.S.level, null, JSON.stringify(patch));
  }
});

test("flow: a kept flow that the next render clears tells the project picker", async () => {
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  const keyA = a.key;
  await a.choose("high");
  a.use(keyA + "-b", baseData());
  const before = a.log.shell;
  a.use(keyA, afterSave()); // high is the running level now, so the kept change goes
  await settle();
  assert.equal(flowMod.notSavedProjects().includes(keyA), false);
  assert.ok(a.log.shell > before, "the picker is asked to draw again");
});

test("cells: a stop state on another cell keeps its own Cancel in the rail", async () => {
  const s = real("model_limit");
  const targets = clone(s.targets);
  shut(targets, "xhigh");
  const a = app({ data: { settings: s.settings, targets, history: s.history } });
  await a.choose("xhigh");
  settingsPage.render(a.root, { ...a.makeCtx(), route: { name: "settings", params: {}, query: { setting: "model" } } });
  assert.deepEqual(tag(a.rail(), "button").map(text), [STRINGS.ed_cancel]);
  assert.equal(footButtons(a).length, 0);
  assert.equal(pendOf(a.root).length, 0);
});

test("op guard: a preview whose op is not its row's op loads the targets once, and Save waits for the new preview", async () => {
  const odd = (v) => ({ ...clone(S.previews[v]), op: "append" });
  const a = app({
    data: baseData(),
    backend: {
      preview: async (t, v) => ok(odd(v)),
      refresh: () => ({ targets: S.start.targets }),
    },
  });
  await a.choose("high");
  await settle();
  assert.equal(a.log.refresh, 1, "the targets were loaded once, through refresh");
  assert.equal(a.log.preview.length, 2, "and the preview was asked for again from the new targets");
  assert.equal(a.log.refresh, 1, "once for this preview, not again");
  // The same op as the row's op needs no reload.
  const b = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]), refresh: () => ({ targets: S.start.targets }) } });
  await b.choose("high");
  assert.equal(b.log.refresh, 0);
  assert.equal(S.previews.high.op, "replace");
  assert.equal(fileOf(S.start.targets, "high", "local").op, "replace");
  // While the reload is on its way, Save is not on screen.
  const gate = {};
  const c = app({
    data: baseData(),
    backend: { preview: async (t, v) => ok(odd(v)), refresh: () => new Promise((resolve) => { gate.go = resolve; }) },
  });
  await c.choose("high");
  assert.equal(c.log.refresh, 1);
  assert.equal(saveButtons(c.root).filter((x) => !off(x)).length, 0, "no Save that can be pressed");
  assert.deepEqual(footTexts(c), [STRINGS.ed_save_plain, STRINGS.ed_cancel]);
  assert.ok(off(footButtons(c)[0]));
  // A reload that brings a matching preview shows Save.
  let n = 0;
  const d = app({
    data: baseData(),
    backend: { preview: async (t, v) => ok(++n === 1 ? odd(v) : S.previews[v]), refresh: () => ({ targets: S.start.targets }) },
  });
  await d.choose("high");
  await settle();
  assert.equal(d.log.refresh, 1);
  assert.deepEqual(footTexts(d), [LOCAL_SAVE, STRINGS.ed_cancel]);
});

// ---------------------------------------------------------------- run

// MR_ONLY=<text> runs the checks whose name holds the text, for a quick look at one of them.
const only = process.env.MR_ONLY || "";
let failed = 0;
for (const [name, fn] of tests) {
  if (only && !name.includes(only)) continue;
  try {
    await fn();
    console.log("ok   " + name);
  } catch (err) {
    failed += 1;
    console.log("FAIL " + name + "\n     " + String(err && err.stack ? err.stack : err).split("\n").slice(0, 7).join("\n     "));
  }
}
console.log((tests.length - failed) + " of " + tests.length + " checks passed");
process.exit(failed ? 1 : 0);

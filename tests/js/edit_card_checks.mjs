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
// The Arrange button in the page head is the band's, not the edit card's, so these counts leave it out.
const buttons = (root) => tag(root, "button").filter((n) => !hasClass(n, "s6-arr"));
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
// Every line under the status row, each its own paragraph.
const hintLines = (root) => byClass(stripOf(root), "s4-hint").map(text);
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
  const a = { page, root, key, setting, log: { preview: [], save: [], undo: [], backup: [], anyway: [], restore: [], opened: [], previewSetting: [], saveSetting: [], reload: 0, refresh: 0, draws: 0, shell: 0 } };
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
    route: { name: "settings", params: {}, query: { setting: a.setting } },
    project: { key: a.key, name: "P" },
    data: { settings: st.settings ? { ok: true, status: 200, data: st.settings } : null },
    hashFor: (name, params, patch) => router.hashFor(name, params, { project: a.key, ...patch }),
    edit: {
      mode: st.mode,
      targets: st.targets,
      history: st.history,
      // A remove has no value, and its calls carry the action. A set logs what it always logged.
      preview: async (target, value, action, setting) => {
        log.preview.push(action === "remove" ? [target, value, action] : [target, value]);
        log.previewSetting.push(setting);
        return backend.preview(target, value, a, action);
      },
      save: async (pv, target, value, action, setting) => {
        log.save.push(action === "remove" ? { pv, target, value, action } : { pv, target, value });
        log.saveSetting.push(setting);
        return after(await backend.save(pv, target, value, a, action));
      },
      undo: async (id) => {
        log.undo.push(id);
        return after(await backend.undo(id, a));
      },
      // The preview of an Undo anyway or a restore, and the two writes. The write sends the hash its preview carried.
      backupPreview: async (id, kind) => {
        log.backup.push([id, kind]);
        return backend.backupPreview(id, kind, a);
      },
      undoAnyway: async (id, baseFile) => {
        log.anyway.push([id, baseFile]);
        return after(await backend.undoAnyway(id, baseFile, a));
      },
      restore: async (id, baseFile) => {
        log.restore.push([id, baseFile]);
        return after(await backend.restore(id, baseFile, a));
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
      // Opens a cell of the band. app.js changes the address, drops the targets and loads the new cell's, so the cell draws with
      // none until land() delivers them.
      openSetting: (name) => {
        log.opened.push(name);
        a.setting = name;
        st.targets = null;
        a.draw();
      },
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
  // Delivers the targets answer of the open cell, as app.js does when the load finishes.
  a.land = (targets) => { st.targets = wrapT(targets); a.draw(); };
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
// The history the page loads again after a refused Undo: the row that was pressed, with what the server now says of it.
const refreshed = (history, over = {}) => {
  const out = clone(history);
  Object.assign(out.rows[0], over);
  return out;
};
const NOW_STALE = { undoable: false, not_undoable_reason: "changed_since_save", restore_state: null, undo_anyway: true };

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
// What the server answered before a cap line could be changed from the page: every level a cap holds is stopped, with the
// cap's file as the reason, and no level waits on a cap change. Used for the caps nobody can change here (a managed cap).
function lockedCaps(targets, reason = "managed") {
  for (const level of targets.levels) {
    if (level.result === "now") continue;
    level.cap_first = false;
    level.via = null;
    for (const limit of level.limits) {
      if (limit.kind !== "cap") continue;
      Object.assign(limit, { editable: false, target: null, lock_reason: reason });
      delete limit.via;
    }
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
  assert.deepEqual(buttons(a.root).map(text), [STRINGS.row_remove], "the only control is the Remove line link of the one row with a line");
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

test("page: a cell the page doesn't edit draws its read-only frame and the plain rail, in every mode", () => {
  for (const mode of ["off", "locked", "ready"]) {
    const a = app({ mode, setting: "promptCacheTtl", data: baseData() });
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
  assert.deepEqual(byClass(a.root, "p2-sn").map(text), [STRINGS.ed_seg_now, STRINGS.ed_seg_two_changes, STRINGS.ed_seg_two_changes, STRINGS.ed_seg_two_changes],
    "a cap line the page can change makes each level above it take two changes");
  const locked = app({ data: { ...cap, targets: lockedCaps(clone(cap.targets)) } });
  assert.deepEqual(byClass(locked.root, "p2-sn").map(text), [STRINGS.ed_seg_now, STRINGS.ed_seg_over_cap, STRINGS.ed_seg_over_cap, STRINGS.ed_seg_over_cap],
    "a cap nobody can change here still says over cap");
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

test("rest: the cap line names who caps what, and says why only when this page can't change the cap", () => {
  const lowered = worldData("lowered");
  const a = app({ data: lowered });
  const cap = lowered.targets.levels.find((l) => l.limits.length).limits[0];
  assert.equal(cap.kind, "cap");
  assert.equal(cap.layer, "user");
  assert.equal(cap.editable, true);
  const line = T("ed_limit_cap", { who: STRINGS.ed_cap_who_user, what: "Sonnet 5.5", value: cap.value, file: "config/settings.json", line: cap.line });
  assert.deepEqual(noteTexts(a.body()), [line], "a cap line the page can change carries no lock text");
  const locked = app({ data: { ...lowered, targets: lockedCaps(clone(lowered.targets)) } });
  assert.deepEqual(noteTexts(locked.body()), [line, STRINGS.ed_lock_managed], "a cap nobody can change here says so");
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
  const base = worldData("nomodel_cap");
  assert.equal(base.targets.saveable, true, "a cap line the page can change leaves a level to pick");
  const w = { ...base, targets: lockedCaps(clone(base.targets)) };
  assert.equal(w.targets.saveable, false);
  const a = app({ data: w });
  assert.ok(levelInputs(a.root).every(off));
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["low"]);
  assert.deepEqual(noteTexts(a.rail()), [STRINGS.ed_nosave_project, STRINGS.ed_lock_managed]);
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
  const base = worldData("nomodel_cap");
  const cap = app({ data: { ...base, targets: lockedCaps(clone(base.targets)) } });
  assert.equal(byClass(cap.body(), "s4-lock").length, 0);
  assert.deepEqual(noteTexts(cap.rail()), [STRINGS.ed_nosave_project, STRINGS.ed_lock_managed]);
});

test("nothing to save at this level: the rail says so with the winner's line and Cancel, and Cancel goes back", async () => {
  const w = worldData("lowered");
  const targets = clone(w.targets);
  levelOf(targets, "high").cap_first = false;
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
  assert.deepEqual(liveRows(a.root).slice(1).map((r) => text(byClass(r, "s6-act")[0])), [STRINGS.row_wont, STRINGS.row_wont]);
  assert.ok(liveRows(a.root).slice(1).every((r) => byClass(r, "ic").length === 0), "no lock icon: the project create and the user insert are rows that won't change what runs, not locked rows");
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

// The server answers a level with a cap line the page can change as one that needs the cap first, so its effort row has no
// file to pick. These checks pick the project row anyway, to read the warning a preview of that row carries.
function pickableLevel(targets, name, layers) {
  levelOf(targets, name).cap_first = false;
  for (const layer of layers) open(targets, layer, [name]);
  return targets;
}

test("warning: a cap the page can change names the caps, says the effort that runs moves and offers Start with the cap", async () => {
  const w = real("lowered");
  const targets = pickableLevel(clone(w.targets), "xhigh", ["project"]);
  const a = app({ data: { settings: w.settings, targets, history: w.history }, backend: { preview: async (t, v) => ok(w.previews[v]) } });
  await a.choose("xhigh");
  assert.deepEqual(a.log.preview, [], "the project is the only open row, and it is not preselected");
  await a.pickRow("project");
  assert.deepEqual(a.log.preview, [[w.target, "xhigh"]]);
  const warn = byClass(a.rail(), "p2-nt-warn")[0];
  assert.equal(text(byClass(warn, "p2-nt-h")[0]), "▲" + STRINGS.ed_warn_part_h);
  const paras = tag(warn, "p").map(text);
  assert.equal(paras[0], STRINGS.ed_warn_cap_t);
  assert.equal(paras.length, 3, "the text and one line for each of the two caps, and no lock line");
  assert.match(paras[1], /Your user file caps Sonnet 5\.5 at medium in config\/settings\.json, line 3/);
  assert.match(paras[2], /This project caps Sonnet 5\.5 at high in settings\.json, line 3/);
  assert.deepEqual(tag(warn, "button").map(text), [STRINGS.ed_start_cap], "the warning offers Start with the cap");
  assert.deepEqual(bigs(a.root), ["low", "→", "medium"]);
  assert.equal(headNote(a.root), STRINGS.ed_runs);
  // A cap nobody can change here is worded as that, with its lock line and no Start with the cap.
  const other = clone(w.previews.xhigh);
  for (const limit of other.warning.limits) Object.assign(limit, { editable: false, target: null, lock_reason: "managed" });
  const b = app({ data: { settings: w.settings, targets, history: w.history }, backend: { preview: async () => ok(other) } });
  await b.choose("xhigh");
  await b.pickRow("project");
  const lines = tag(byClass(b.rail(), "p2-nt-warn")[0], "p").map(text);
  assert.equal(lines[0], STRINGS.ed_warn_cap_locked_t);
  assert.equal(lines.includes(STRINGS.ed_warn_cap_t), false);
  assert.ok(lines.includes(STRINGS.ed_lock_managed));
  assert.deepEqual(tag(byClass(b.rail(), "p2-nt-warn")[0], "button").map(text), []);
});

test("warning: Start with the cap in a warning drops the pick and opens the Effort cap cell with the level to choose", async () => {
  const w = real("lowered");
  const targets = pickableLevel(clone(w.targets), "xhigh", ["project"]);
  const a = app({ data: { settings: w.settings, targets, history: w.history }, backend: { preview: async (t, v) => ok(w.previews[v]) } });
  await a.choose("xhigh");
  await a.pickRow("project");
  assert.equal(flowMod.S.level, "xhigh");
  btn(a.root, STRINGS.ed_start_cap).click();
  await settle();
  assert.deepEqual(a.log.opened, ["maxEffortLevel"]);
  assert.equal(flowMod.S.level, null, "the effort pick is gone");
  assert.deepEqual(flowMod.S.carry, { setting: "maxEffortLevel", level: "xhigh", from: "effortLevel" });
  assert.equal(a.log.save.length, 0, "nothing was written");
  assert.equal(a.log.preview.length, 1, "no preview for the cap yet");
});

test("warning: no model and a cap below the level shows the cap warning", async () => {
  const c = real("nomodel_cap");
  const targets = clone(c.targets);
  pickableLevel(targets, "high", ["project"]);
  const a = app({ data: { settings: c.settings, targets, history: c.history }, backend: { preview: async (t, v) => ok(c.previews.project[v]) } });
  await a.choose("high");
  await a.pickRow("project");
  assert.equal(c.previews.project.high.warning.status, "lowered");
  assert.equal(c.previews.project.high.warning.model_known, false);
  const warn = byClass(a.rail(), "p2-nt-warn")[0];
  assert.equal(tag(warn, "p").map(text)[0], STRINGS.ed_warn_cap_t, "the user file's cap can be changed, as with a model set");
  assert.equal(text(byClass(a.rail(), "p2-nt-h")[0]), "▲" + STRINGS.ed_warn_h);
  assert.deepEqual(tag(warn, "button").map(text), [STRINGS.ed_start_cap], "the warning offers Start with the cap");
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
  const targets = lockedCaps(clone(w.targets));
  shut(targets, "high");
  const a = app({ data: { settings: w.settings, targets, history: w.history }, backend: { preview: async () => { throw new Error("no preview"); } } });
  assert.ok(off(lvl(a.root, "high")), "an over-cap level can't be pressed");
  assert.deepEqual(byClass(a.root, "p2-sn").map(text).filter((x) => x === STRINGS.ed_seg_over_cap).length > 0, true);
  await a.choose("high");
  assert.equal(a.log.preview.length, 0);
  assert.equal(nts(a.rail(), "warn").length, 0, "no stop panel");
  assert.equal(byClass(a.root, "p2-df").length, 0);
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["low"], "nothing was chosen");
  // The cap note carries the line that says why this page can't change the cap.
  assert.ok(noteTexts(a.body()).includes(STRINGS.ed_lock_managed));
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
  assert.deepEqual(tag(done, "button").map(text), [STRINGS.ed_dismiss, STRINGS.ed_older_link], "the saved row is an older backup now");
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
  assert.deepEqual(tag(rest, "button").map(text), [STRINGS.ed_older_link], "no Undo, only the link to the older backups");
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
  assert.equal(c.history.rows[0].undo_anyway, true);
  // The backup is good, so the line offers Undo anyway and does not name the backup (the preview does).
  assert.deepEqual(tag(bar, "button").map(text), [STRINGS.ed_anyway_btn], "the one row is Undo anyway's, so the list has none left and no link");
  assert.equal(byClass(bar, "pa").length, 0);
  assert.match(text(bar), new RegExp(T("ed_undo_stale_h", { file: "settings.json" })));
  assert.equal(buttons(rest.root).filter((b) => text(b) === STRINGS.ed_undo).length, 0);
  // The page showed Undo (an older history), and the server answered 409.
  const press = app({
    data: afterSave(),
    backend: {
      undo: async () => bad("error", 409, c.undo_answer),
      refresh: () => ({ settings: c.settings, targets: c.targets, history: refreshed(c.history, { id: S.after_save.history.rows[0].id }) }),
    },
  });
  await press.press(STRINGS.ed_undo);
  assert.equal(press.log.refresh, 1, "the answer loads the page data again");
  const warn = stripOf(press.root);
  assert.ok(hasClass(okRow(press.root), "s4-ok-warn"));
  assert.equal(okRow(press.root).getAttribute("role"), "status");
  assert.equal(byClass(warn, "pa").length, 0, "the offer line names no path");
  assert.equal(text(okRow(press.root)).endsWith(STRINGS.ed_anyway_offer_t), true);
  assert.deepEqual(tag(warn, "button").map(text), [STRINGS.ed_anyway_btn, STRINGS.ed_dismiss]);
  tag(warn, "button")[1].click();
  await settle();
  const back = stripOf(press.root);
  assert.deepEqual(tag(back, "button").map(text), [STRINGS.ed_anyway_btn], "the row's own strip is back, with no dead Undo");
  assert.ok(hasClass(okRow(press.root), "s4-ok-warn"));
  assert.match(text(back), new RegExp(T("ed_undo_stale_h", { file: "settings.json" })));
  // The offer follows the history loaded after the refusal. A backup Undo anyway can't use (restore_state set) draws the
  // plain stale line with the path, and so does a history that never came back.
  const id = S.after_save.history.rows[0].id;
  const cannot = (history) => app({
    data: afterSave(),
    backend: { undo: async () => bad("error", 409, c.undo_answer), refresh: () => ({ history }) },
  });
  const grey = cannot(refreshed(c.history, { id, restore_state: "backup_unparsed", undo_anyway: false }));
  await grey.press(STRINGS.ed_undo);
  assert.equal(anywayBtn(grey.root), undefined, "no Undo anyway for a row the server says it can't restore");
  assert.equal(byClass(stripOf(grey.root), "pa").length, 1, "the plain stale line names the backup");
  const none = cannot(undefined);
  await none.press(STRINGS.ed_undo);
  assert.equal(anywayBtn(none.root), undefined, "no offer from the row the press was made from");
  assert.deepEqual(tag(stripOf(none.root), "button").map(text), [STRINGS.ed_dismiss]);
});

test("backup_damaged: at rest a warning with no buttons, and on a press an alert that replaces the strip", async () => {
  const d = real("backup_damaged");
  const rest = app({ data: { settings: d.settings, targets: d.targets, history: d.history } });
  const bar = stripOf(rest.root);
  assert.ok(hasClass(okRow(rest.root), "s4-ok-warn"));
  assert.deepEqual(tag(bar, "button").map(text), [STRINGS.ed_older_link], "no Undo, only the link");
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
  assert.equal(text(byClass(bar, "s4-note")[0]), STRINGS.ed_backup_pruned_rest);
  assert.deepEqual(tag(bar, "button").map(text), [STRINGS.ed_older_link]);
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
  assert.equal(text(byClass(note, "p2-nt-h")[0]), "✕" + STRINGS.ed_undo_fail_h);
  assert.equal(text(tag(note, "p")[0]), T("ed_undo_fail_config_dir_t", { config_dir: answer.config_dir_display }));
  assert.deepEqual(byClass(note, "pa").map(text), [answer.config_dir_display]);
  assert.deepEqual(tag(note, "button").map(text), [STRINGS.ed_dismiss]);
  assert.equal(anyKey(u.root), false);
  tag(note, "button")[0].click();
  await settle();
  assert.equal(byClass(u.root, "p2-nt-err").length, 0, "Dismiss clears the notice");
  assert.ok(btn(u.root, STRINGS.ed_undo), "Undo is offered again after Dismiss");
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
  const pvs = S.previews;
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
  assert.deepEqual(buttons(a.root).map(text), [STRINGS.row_remove], "only the Remove line link of the row with a line is left");
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
  for (const level of targets.levels) { level.limits = [{ kind: "cap", value: evil, file_display: evil, line: 1, lock_reason: "managed" }]; }
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
  const source = ["edit_card", "edit_flow", "edit_pick", "edit_review", "edit_foot", "edit_backup", "edit_ui", "edit_setting", "edit_words"]
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
  assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + STRINGS.ed_undo_fail_h);
  assert.equal(text(tag(alert, "p")[0]), T("ed_undo_fail_t", { file: "settings.local.json" }));
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

test("cells: picking Cache lifetime during a change keeps the review, the foot and Not saved, and Effort brings the live picker back", async () => {
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await a.choose("high");
  settingsPage.render(a.root, { ...a.makeCtx(), route: { name: "settings", params: {}, query: { setting: "promptCacheTtl" } } });
  // the body is the read-only frame of Cache lifetime
  assert.equal(levelInputs(a.root).length + rowInputs(a.root).length, 0);
  assert.equal(text(byClass(a.root, "s4-lock")[0]), STRINGS.ro_lock);
  assert.equal(text(byClass(a.root, "s4-lab")[0]), STRINGS.f_cache);
  // the rail keeps the review, and the foot keeps Save and Cancel
  assert.equal(text(byClass(a.rail(), "s4-rh")[0]), STRINGS.review_h);
  assert.deepEqual(bigs(a.root), ["low", "→", "high"]);
  assert.equal(byClass(a.root, "p2-df").length, 1);
  assert.deepEqual(footTexts(a), [LOCAL_SAVE, STRINGS.ed_cancel]);
  assert.equal(saveButtons(a.root).length, 1);
  // and the band says Not saved on the Effort cell
  assert.equal(text(byClass(cellOf(a.root, "effortLevel"), "s5-pend")[0]), STRINGS.band_not_saved);
  // Cancel on Cache lifetime ends the change
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.equal(byClass(a.root, "p2-df").length, 0);
  assert.equal(pendOf(a.root).length, 0);
  assert.equal(text(byClass(a.rail(), "s4-rh")[0]), STRINGS.why_h);
  // a cell with no change in progress is untouched: the plain rail, no foot
  const plain = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  settingsPage.render(plain.root, { ...plain.makeCtx(), route: { name: "settings", params: {}, query: { setting: "promptCacheTtl" } } });
  assert.equal(text(byClass(plain.rail(), "s4-rh")[0]), STRINGS.why_h);
  assert.equal(footButtons(plain).length, 0);
  // Effort again, with the same pick
  const b = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await b.choose("high");
  settingsPage.render(b.root, { ...b.makeCtx(), route: { name: "settings", params: {}, query: { setting: "promptCacheTtl" } } });
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
  settingsPage.render(a.root, { ...a.makeCtx(), route: { name: "settings", params: {}, query: { setting: "promptCacheTtl" } } });
  btn(a.root, LOCAL_SAVE).click();
  await settle();
  assert.equal(a.log.save.length, 1);
  assert.deepEqual(strips(a.root).map((n) => tag(n, "button").map(text)), [[STRINGS.ed_undo]]);
  // At rest, a cell that isn't Effort still hides the last change.
  const plain = app({ data: afterSave(), backend: saveFlow() });
  settingsPage.render(plain.root, { ...plain.makeCtx(), route: { name: "settings", params: {}, query: { setting: "promptCacheTtl" } } });
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

test("op guard: a second mismatch for the same target and value never shows Save and says so in an error note", async () => {
  const odd = (v) => ({ ...clone(S.previews[v]), op: "append" });
  const a = app({
    data: baseData(),
    backend: { preview: async (t, v) => ok(odd(v)), refresh: () => ({ targets: S.start.targets }) },
  });
  await a.choose("high");
  await settle();
  assert.equal(a.log.refresh, 1, "the first mismatch loads the targets once");
  assert.equal(a.log.preview.length, 2, "and asks for the preview again");
  const shown = (x) => x.root.textContent + x.rail().textContent;
  assert.ok(shown(a).includes(STRINGS.ed_op_mismatch), "the error note says the kinds of change differ");
  assert.equal(nts(a.rail(), "err").length + nts(a.root, "err").length > 0, true, "it is an error note");
  assert.equal(byClass(a.root, "p2-df").length, 0, "no review is drawn");
  assert.equal(saveButtons(a.root).filter((x) => !off(x)).length, 0, "no Save that can be pressed");
  assert.equal(footTexts(a).includes(LOCAL_SAVE), false, "and no Save to the local file");
  assert.equal(a.log.refresh, 1, "no third round");
  assert.equal(a.log.preview.length, 2, "and no third preview");
});

test("op guard: a first mismatch reloads once and a matching second preview shows Save, with no error note", async () => {
  const odd = (v) => ({ ...clone(S.previews[v]), op: "append" });
  let n = 0;
  const a = app({
    data: baseData(),
    backend: { preview: async (t, v) => ok(++n === 1 ? odd(v) : S.previews[v]), refresh: () => ({ targets: S.start.targets }) },
  });
  await a.choose("high");
  await settle();
  assert.equal(a.log.refresh, 1, "reloaded once");
  assert.equal(a.log.preview.length, 2, "previewed twice");
  assert.deepEqual(footTexts(a), [LOCAL_SAVE, STRINGS.ed_cancel]);
  assert.equal((a.root.textContent + a.rail().textContent).includes(STRINGS.ed_op_mismatch), false, "no mismatch note");
});

// ---------------------------------------------------------------- add a line, create a file, remove a line

const uiMod = await import(JS + "edit_ui.js");
const CR = real("create");
const CRD = real("create_dir");
const INS = real("insert");
const RM = real("remove");
const RMLAST = real("remove_last");
const RMREP = real("remove_repeated");
const RMUNK = real("remove_unknown");
const NST = real("new_stale");

const dataOf = (state, over = {}) => ({ settings: state.settings, targets: state.targets, history: state.history, ...over });
// The fake server for one recorded world: a set previews what the world recorded for its value, a remove the line it
// removed, and a save and an undo answer with the recorded answers and the data that comes after them.
const worldFlow = (m, over = {}) => ({
  preview: async (target, value, a, action) => {
    if (action === "remove") return ok(target === m.project_target ? m.project_preview : m.local_preview);
    return ok(target === m.project_target ? m.project_previews[value] : m.previews[value]);
  },
  save: async () => ({ ...ok(m.save), after: m.after_save }),
  undo: async () => ({ ...ok(m.undo), after: m.after_undo }),
  ...over,
});
const removeLink = (root, layer) => buttons(root).find((b) => b.getAttribute("data-edit-focus") === "remove:" + layer);
const removeLinks = (root) => buttons(root).filter((b) => text(b) === STRINGS.row_remove);
const wordsOf = (root) => liveRows(root).map((r) => text(byClass(r, "s6-act")[0]));
const LOCAL = "settings.local.json";
// No gap shows on the page: no null or undefined, no slot left open, no space before a full stop or a comma.
const noGaps = (root, why = "") => assert.doesNotMatch(root.textContent.replace(/\s+/g, " "), /\bnull\b|\bundefined\b|\{\w+\}| [.,](?!\w)/, why);
const withGit = (pv, state) => ({ ...clone(pv), git_ignore: state });
const quiet = (root) => text(byClass(stripOf(root), "s4-note")[0]);
const when = (row) => format.fmtTime(row.time);

test("railCase: a chosen remove is its own case, behind the mode rules and ahead of the save rules", () => {
  const c = (over) => pickMod.railCase({ ...base_, level: null, row: null, levelRow: null, ...over });
  assert.equal(c({ remove: { blocked: false } }), "remove");
  assert.equal(c({ remove: { blocked: true } }), "remove_blocked");
  assert.equal(c({ remove: null }), "rest");
  assert.equal(c({}), "rest", "a caller with no remove field is unchanged");
  assert.equal(c({ remove: { blocked: false }, saveable: false }), "remove", "the remove rule comes before the save rule");
  assert.equal(c({ remove: { blocked: false }, mode: "off" }), "off");
  assert.equal(c({ remove: { blocked: false }, mode: "locked" }), "locked");
  assert.equal(c({ remove: { blocked: true }, projectLock: "not_repo_root" }), "project_lock");
  assert.equal(c({ remove: { blocked: false }, mode: null }), "rest");
});

test("pickerState: while a remove is chosen the page asks for busy, so every radio is off and the running level stays checked", () => {
  assert.deepEqual(pickMod.pickerState(NAMES, "medium", null, "ready", { busy: true }), { checked: "medium", disabled: NAMES.slice() });
});

test("lockText and rowLockText know a line that may not be read and a repeated setting", () => {
  assert.equal(uiMod.lockText("not_on_trail"), STRINGS.ed_lock_not_on_trail);
  assert.equal(uiMod.lockText("repeated_key"), STRINGS.ed_lock_repeated_key);
  assert.equal(uiMod.rowLockText("not_on_trail"), STRINGS.ed_row_lock_not_on_trail);
  assert.equal(uiMod.rowLockText("repeated_key"), STRINGS.ed_row_lock_repeated_key);
  assert.equal(uiMod.lockText("create_later"), null, "the old later reasons are gone");
  assert.equal(uiMod.rowLockText("add_later"), null);
  assert.equal(uiMod.rowLockText(null), null);
});

test("rows: a row that may not be read says so with the lock icon, in place of a word", async () => {
  const targets = clone(INS.start.targets);
  for (const name of ["low", "high", "xhigh"]) Object.assign(fileOf(targets, name, "project"), { target: null, op: null, effect: null, lock_reason: "not_on_trail", pickable: false });
  recount(targets);
  const a = app({ data: dataOf(INS.start, { targets }), backend: worldFlow(INS) });
  await a.choose("high");
  assert.deepEqual(wordsOf(a.root), [STRINGS.row_adds, STRINGS.ed_row_lock_not_on_trail, STRINGS.row_adds]);
  assert.equal(byClass(liveRows(a.root)[1], "ic").length, 1, "a lock icon on the locked row");
  assert.ok(hasClass(liveRows(a.root)[1], "is-no"));
  assert.equal(anyKey(a.root), false);
});

test("rows: each op has its word, picked and not picked, and Save names the file it creates", async () => {
  // replace
  const r = app({ data: baseData(), backend: saveFlow() });
  await r.choose("high");
  assert.deepEqual(wordsOf(r.root)[0], T("row_edits", { n: 2 }), "a replace says which line it edits");
  assert.equal(byClass(liveRows(r.root)[0], "ic").length, 1);
  // create: the local file is picked, the project file is a create too, the user file takes a line
  const a = app({ data: dataOf(CR.start), backend: worldFlow(CR) });
  await a.choose("high");
  assert.deepEqual(rowInputs(a.root).map((x) => x.value), ["local", "project", "user"], "the board's order");
  assert.deepEqual(wordsOf(a.root), [STRINGS.row_creates, STRINGS.row_creates, STRINGS.row_adds]);
  assert.deepEqual(checkedOf(rowInputs(a.root)), ["local"]);
  assert.deepEqual(liveRows(a.root).map((x) => byClass(x, "ic").length), [1, 0, 0], "only the picked row has the check");
  assert.deepEqual(footTexts(a), ["Create " + LOCAL, STRINGS.ed_cancel]);
  assert.equal(footTexts(a)[0], T("ed_save_create", { file: LOCAL }));
  assert.ok(hasClass(footButtons(a)[0], "p2-pri") && !off(footButtons(a)[0]));
  await a.pickRow("project");
  assert.deepEqual(wordsOf(a.root), [STRINGS.row_creates, STRINGS.row_creates, STRINGS.row_adds], "the same words with the check moved");
  assert.deepEqual(liveRows(a.root).map((x) => byClass(x, "ic").length), [0, 1, 0]);
  assert.deepEqual(footTexts(a), ["Create settings.json", STRINGS.ed_cancel]);
  assert.equal(text(byClass(a.rail(), "s4-sub")[0]), T("ed_card_new", { file: "settings.json" }));
  assert.ok(noteTexts(a.rail()).includes(STRINGS.ed_shared), "the project file is shared");
  // insert: a line to add, and Save keeps its usual words
  const b = app({ data: dataOf(INS.start), backend: worldFlow(INS) });
  await b.choose("high");
  assert.deepEqual(wordsOf(b.root), [STRINGS.row_adds, STRINGS.row_adds, STRINGS.row_adds]);
  assert.deepEqual(liveRows(b.root).map((x) => byClass(x, "ic").length), [1, 0, 0]);
  assert.deepEqual(footTexts(b), [LOCAL_SAVE, STRINGS.ed_cancel]);
  assert.equal(text(byClass(b.rail(), "s4-sub")[0]), T("ed_card_add", { line: INS.previews.high.line, file: LOCAL }));
  assert.equal(byClass(b.rail(), "p2-tag").length, 0, "an insert is not a new file");
  assert.deepEqual(bigs(b.root), ["medium", "→", "high"]);
  assert.equal(anyKey(b.root) || anyKey(a.root), false);
});

test("create: a preselected local create shows the New file tag and its note, and the longer note when the folder is new", async () => {
  const a = app({ data: dataOf(CR.start), backend: worldFlow(CR) });
  await a.choose("high");
  assert.equal(text(byClass(a.rail(), "s4-sub")[0]), T("ed_card_new", { file: LOCAL }));
  const caption = byClass(a.rail(), "p2-df-h")[0];
  assert.deepEqual(byClass(caption, "p2-tag").map(text), [STRINGS.ed_diff_new_tag]);
  assert.ok(order(caption, byClass(caption, "p2-tag")[0]) > order(caption, byClass(caption, "pa")[0]), "the tag follows the path");
  assert.equal(byClass(a.rail(), "p2-add").length, 3);
  assert.equal(byClass(a.rail(), "p2-del").length, 0);
  assert.deepEqual(noteTexts(a.rail()), [T("ed_new_file_note", { file: LOCAL })]);
  assert.deepEqual(bigs(a.root), ["medium", "→", "high"]);
  const d = app({ data: dataOf(CRD.start), backend: worldFlow(CRD) });
  await d.choose("high");
  assert.equal(CRD.previews.high.creates_dir, true);
  assert.deepEqual(noteTexts(d.rail()), [T("ed_new_dir_note", { file: LOCAL })], "the longer note stands in place of the shorter one");
  assert.deepEqual(byClass(d.rail(), "p2-tag").map(text), [STRINGS.ed_diff_new_tag]);
  // a change to a file that exists has no tag and no new-file note
  const r = app({ data: baseData(), backend: saveFlow() });
  await r.choose("high");
  assert.equal(byClass(r.rail(), "p2-tag").length, 0);
  assert.deepEqual(noteTexts(r.rail()), []);
});

// The owner's browser run: a project line at high and no local or user file. A level opens straight onto the local
// create, so the Pick a file line never shows, and a press on the project row moves the pick to it. The browser test
// waits on these signs, so a change to them fails here first.
test("owner path: a level opens on the local create with no Pick a file line, and the project row then takes the pick", async () => {
  const m = real("owner");
  const level = levelOf(m.start.targets, "medium");
  assert.equal(level.preselect, m.local_target, "the absent local file is the preselect");
  assert.equal(fileOf(m.start.targets, "medium", "local").op, "create");
  assert.equal(fileOf(m.start.targets, "medium", "project").pickable, true);
  const a = app({ data: dataOf(m.start), backend: worldFlow({ ...m, previews: { medium: m.local_preview }, project_previews: { medium: m.project_preview }, project_target: m.project_target }) });
  assert.equal(checkedOf(rowInputs(a.root)).length, 0, "nothing is picked at rest");
  await a.choose("medium");
  assert.deepEqual(a.log.preview, [[m.local_target, "medium"]], "the local create is previewed on the press");
  assert.deepEqual(checkedOf(rowInputs(a.root)), ["local"]);
  assert.equal(liveRows(a.root).filter((r) => hasClass(r, "is-pick")).length, 1);
  assert.ok(!noteTexts(a.rail()).includes(STRINGS.ed_pick_file), "no Pick a file line once the preselect is previewed");
  assert.equal(byClass(a.rail(), "p2-df").length, 1, "the diff is drawn");
  assert.equal(byClass(a.rail(), "p2-del").length, 0, "a create deletes nothing");
  assert.deepEqual(byClass(byClass(a.rail(), "p2-df-h")[0], "p2-tag").map(text), [STRINGS.ed_diff_new_tag], "the diff caption wears the New file tag");
  assert.deepEqual(bigs(a.root), ["high", "→", "medium"], "the change line holds what runs now and the level");
  assert.deepEqual(footTexts(a), [T("ed_save_create", { file: LOCAL }), STRINGS.ed_cancel]);
  assert.ok(!off(footButtons(a)[0]), "Save is on for the local create");
  // The project row: the pick moves to it, the diff holds the old and the new value, and Save writes the project file.
  await a.pickRow("project");
  assert.deepEqual(a.log.preview[1], [m.project_target, "medium"]);
  assert.deepEqual(checkedOf(rowInputs(a.root)), ["project"]);
  assert.equal(liveRows(a.root).filter((r) => hasClass(r, "is-pick")).length, 1);
  assert.ok(hasClass(rowOf(rowIn(a.root, "project")), "is-pick"));
  assert.equal(byClass(a.rail(), "p2-tag").length, 0, "the project file is not new");
  assert.ok(!noteTexts(a.rail()).includes(STRINGS.ed_pick_file));
  assert.ok(noteTexts(a.rail()).includes(STRINGS.ed_shared), "the project file is shared");
  assert.ok(byClass(a.rail(), "p2-del").some((n) => text(n).includes('"high"')), "the old value is a deleted line");
  assert.ok(byClass(a.rail(), "p2-add").some((n) => text(n).includes('"medium"')), "the new value is an added line");
  assert.equal(byClass(a.rail(), "s4-dl").length, 1, "the After list is drawn");
  assert.deepEqual(bigs(a.root), ["high", "→", "medium"]);
  assert.deepEqual(footTexts(a), [T("ed_save_to", { file: "settings.json" }), STRINGS.ed_cancel]);
  assert.ok(!off(footButtons(a)[0]));
});

test("remove: Remove line shows at rest on a row with a line, named for the line and the file, and not on a row without one", () => {
  const a = app({ data: dataOf(RM.start) });
  const links = removeLinks(a.root);
  assert.deepEqual(links.map((b) => b.getAttribute("data-edit-focus")), ["remove:local", "remove:project"]);
  assert.deepEqual(links.map((b) => b.getAttribute("aria-label")), [
    T("row_remove_sr", { line: 2, file: LOCAL }), T("row_remove_sr", { line: 2, file: "settings.json" })]);
  assert.ok(links.every((b) => hasClass(b, "s4-link") && b.getAttribute("type") === "button" && hasClass(b.parentNode, "s6-act")));
  assert.deepEqual(plainRows(a.root).filter((r) => !hasClass(r, "s6-def")).map((r) => tag(r, "button").length), [1, 1, 0], "the user row has no line");
  assert.equal(removeLinks(app({ data: dataOf(CR.start) }).root).length, 0, "files that don't exist have no line");
  assert.equal(removeLinks(app({ data: dataOf(INS.start) }).root).length, 0, "files with no effort line have none");
  assert.equal(a.log.preview.length, 0, "drawing the link asks for nothing");
});

test("remove: the link is gone during a level change, and in off, locked, a project lock and nothing to save", async () => {
  const a = app({ data: dataOf(RM.start), backend: { preview: never } });
  assert.equal(removeLinks(a.root).length, 2);
  await a.choose("low");
  assert.equal(removeLinks(a.root).length, 0, "a level is chosen");
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.equal(removeLinks(a.root).length, 2, "Cancel brings it back");
  const targetsOff = offAnswer(RM.start.targets);
  assert.equal(removeLinks(app({ mode: "off", data: dataOf(RM.start, { targets: targetsOff }) }).root).length, 0, "off");
  assert.equal(removeLinks(app({ mode: "locked", data: dataOf(RM.start) }).root).length, 0, "locked");
  const lockedProject = clone(RM.start.targets);
  lockedProject.project_lock = "not_repo_root";
  assert.equal(removeLinks(app({ data: dataOf(RM.start, { targets: lockedProject }) }).root).length, 0, "project lock");
  const nothing = clone(RM.start.targets);
  nothing.saveable = false;
  assert.equal(removeLinks(app({ data: dataOf(RM.start, { targets: nothing }) }).root).length, 0, "saveable false");
  // a line the server won't remove, for any reason but a repeated key, has no link either
  const locked = clone(RM.start.targets);
  targetOf(locked, "project").remove.lock_reason = "not_editable";
  assert.deepEqual(removeLinks(app({ data: dataOf(RM.start, { targets: locked }) }).root).map((b) => b.getAttribute("data-edit-focus")), ["remove:local"]);
  const b = app({ data: dataOf(RM.start, { targets: locked }), backend: worldFlow(RM) });
  flowMod.startRemove(rowOfFiles(locked, "project"));
  await settle();
  assert.equal(b.log.preview.length, 0, "and pressing it by code does nothing");
});

test("remove: a press asks for a remove preview with no value, opens the review, and focus goes to Cancel", async () => {
  fresh();
  const a = app({ data: dataOf(RM.start), backend: worldFlow(RM) });
  removeLink(a.root, "local").click();
  await settle();
  assert.deepEqual(a.log.preview, [[RM.local_target, null, "remove"]]);
  const rail = a.rail();
  assert.equal(text(byClass(rail, "s4-rh")[0]), STRINGS.review_h);
  assert.equal(text(byClass(rail, "s4-sub")[0]), T("ed_card_remove", { line: 2, file: LOCAL }));
  assert.deepEqual(bigs(a.root), ["high", "→", "low"]);
  assert.equal(headNote(rail), STRINGS.ed_runs);
  assert.equal(byClass(rail, "p2-del").length, 1);
  assert.equal(byClass(rail, "p2-add").length, 0);
  assert.equal(byClass(rail, "p2-tag").length, 0);
  assert.deepEqual(footTexts(a), [T("ed_save_remove", { line: 2, file: LOCAL }), STRINGS.ed_cancel]);
  assert.equal(footTexts(a)[0], "Remove line 2 from " + LOCAL);
  assert.ok(hasClass(footButtons(a)[0], "p2-pri") && !off(footButtons(a)[0]));
  assert.equal(text(byClass(slotOf(a.root, "pick"), "s4-hint")[0]), STRINGS.ed_nothing_yet);
  assert.equal(FElement.focused, btn(a.root, STRINGS.ed_cancel), "focus is on Cancel, because the pressed link is gone");
  assert.equal(removeLinks(a.root).length, 0, "Remove line hides while a change is open");
  assert.equal(noteTexts(rail).includes(STRINGS.ed_shared), false, "the local file is not shared");
  assert.equal(anyKey(a.root), false);
  noGaps(a.root);
});

test("remove: the picker is off while a remove is open, a level press does nothing, and Not saved shows until Cancel", async () => {
  fresh();
  const a = app({ data: dataOf(RM.start), backend: worldFlow(RM) });
  assert.equal(pendOf(a.root).length, 0);
  removeLink(a.root, "local").click();
  await settle();
  assert.ok(levelInputs(a.root).every(off), "every level is off");
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["high"], "the running level stays checked");
  assert.equal(pendOf(a.root).length, 1, "Not saved");
  assert.deepEqual(flowMod.notSavedProjects(), [a.key]);
  assert.equal(text(byClass(cellOf(a.root, "effortLevel"), "s5-pend")[0]), STRINGS.band_not_saved);
  lvl(a.root, "low").dispatch("change");
  await settle();
  assert.equal(a.log.preview.length, 1, "a level press sends nothing");
  assert.equal(byClass(a.root, "p2-df").length, 1, "and the remove review stays");
  assert.equal(liveRows(a.root).length, 0);
  flowMod.startRemove(rowOfFiles(RM.start.targets, "project"));
  await settle();
  assert.equal(a.log.preview.length, 1, "a second remove is not started either");
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.equal(pendOf(a.root).length, 0, "Cancel clears Not saved");
  assert.deepEqual(flowMod.notSavedProjects(), []);
  assert.ok(levelInputs(a.root).every((r) => !off(r)));
  assert.equal(removeLinks(a.root).length, 2);
  assert.equal(byClass(a.root, "p2-df").length, 0);
  assert.equal(strips(a.root).length, 0);
});

test("remove: a level change and a remove exclude each other, so a chosen level hides the link and a press by code does nothing", async () => {
  const a = app({ data: dataOf(RM.start), backend: { preview: never } });
  await a.choose("low");
  flowMod.startRemove(rowOfFiles(RM.start.targets, "local"));
  await settle();
  assert.deepEqual(a.log.preview.map((x) => x.length), [2], "only the level's preview");
  assert.equal(byClass(a.rail(), "s4-sub").length, 0);
});

test("remove: a line that changes nothing warns, offers Remove anyway as a plain button, and notes the last line and the shared file", async () => {
  const a = app({ data: dataOf(RM.start), backend: worldFlow(RM) });
  removeLink(a.root, "project").click();
  await settle();
  const pv = RM.project_preview;
  assert.deepEqual([pv.no_effect, pv.last_line, pv.shared], [true, true, true]);
  assert.deepEqual(bigs(a.root), ["high"], "one value");
  assert.equal(headNote(a.rail()), STRINGS.ed_nochange);
  const warn = nts(a.rail(), "warn");
  assert.equal(warn.length, 1);
  assert.equal(text(byClass(warn[0], "p2-nt-h")[0]), "▲" + STRINGS.ed_remove_noeffect_h);
  assert.equal(text(tag(warn[0], "p")[0]), STRINGS.ed_remove_noeffect_t);
  assert.deepEqual(footTexts(a), [STRINGS.ed_remove_anyway, STRINGS.ed_cancel]);
  assert.ok(!hasClass(footButtons(a)[0], "p2-pri"), "not the primary button");
  assert.ok(!off(footButtons(a)[0]), "and not off");
  assert.equal(byClass(slotOf(a.root, "pick"), "s4-hint").length, 0, "no reassurance line under a warned save");
  assert.deepEqual(noteTexts(a.rail()), [T("ed_remove_last_note", { file: "settings.json" }), STRINGS.ed_shared], "last line, then shared");
  assert.ok(order(a.rail(), byClass(a.rail(), "p2-df")[0]) < order(a.rail(), byClass(a.rail(), "s4-note")[0]), "the notes follow the diff");
  assert.equal(text(byClass(a.rail(), "s4-sub")[0]), T("ed_card_remove", { line: 2, file: "settings.json" }));
  noGaps(a.root);
});

test("remove: the last line of a file says the file stays, and an unknown result draws no empty value", async () => {
  const a = app({ data: dataOf(RMLAST.start), backend: { preview: async () => ok(RMLAST.local_preview) } });
  removeLink(a.root, "local").click();
  await settle();
  assert.deepEqual(noteTexts(a.rail()), [T("ed_remove_last_note", { file: LOCAL })]);
  assert.deepEqual(bigs(a.root), ["low", "→", "medium"]);
  assert.equal(nts(a.rail(), "warn").length, 0);
  assert.deepEqual(footTexts(a), [T("ed_save_remove", { line: RMLAST.local_preview.line, file: LOCAL }), STRINGS.ed_cancel]);
  // Nothing is known about what runs: no value, and the line says so.
  const u = app({ data: dataOf(RMUNK.start), backend: { preview: async () => ok(RMUNK.user_preview) } });
  removeLink(u.root, "user").click();
  await settle();
  assert.equal(byClass(u.rail(), "s4-chg").length, 0, "no empty value");
  assert.equal(headNote(u.rail()), STRINGS.ed_nochange_unknown);
  assert.equal(footTexts(u).length, 2);
  noGaps(u.root);
  // What ran before is known and what runs after is not: the one value and the same line.
  const half = clone(RMUNK.user_preview);
  half.runs_before = "high";
  const h2 = app({ data: dataOf(RMUNK.start), backend: { preview: async () => ok(half) } });
  removeLink(h2.root, "user").click();
  await settle();
  assert.deepEqual(bigs(h2.root), ["high"]);
  assert.equal(headNote(h2.rail()), STRINGS.ed_nochange_unknown);
});

test("remove: a setting in the file twice opens the blocked rail with Cancel, asks for no preview, and is not Not saved", async () => {
  fresh();
  const a = app({ data: dataOf(RMREP) });
  const link = removeLink(a.root, "local");
  assert.ok(link, "the link shows, so the page can say why not");
  link.click();
  await settle();
  assert.equal(a.log.preview.length, 0, "no preview");
  const note = nts(a.rail(), "warn");
  assert.equal(note.length, 1);
  assert.equal(text(byClass(note[0], "p2-nt-h")[0]), "▲" + T("ed_remove_blocked_h", { line: 1 }));
  assert.equal(text(tag(note[0], "p")[0]), STRINGS.ed_remove_blocked_t);
  assert.deepEqual(tag(note[0], "button").map(text), [STRINGS.ed_cancel]);
  assert.equal(saveButtons(a.root).length, 0, "no Save");
  assert.equal(footButtons(a).length, 0, "and nothing in the foot");
  assert.equal(pendOf(a.root).length, 0, "nothing waits to be saved");
  assert.deepEqual(flowMod.notSavedProjects(), []);
  assert.equal(FElement.focused, tag(note[0], "button")[0]);
  assert.ok(levelInputs(a.root).every(off), "the picker is off");
  tag(note[0], "button")[0].click();
  await settle();
  assert.equal(nts(a.rail(), "warn").length, 0);
  assert.equal(removeLinks(a.root).length, 1);
  assert.ok(levelInputs(a.root).every((r) => !off(r)));
});

test("remove: a preview that failed keeps the frame, Save off and Cancel, and Dismiss leaves the frame", async () => {
  const a = app({ data: dataOf(RM.start), backend: { preview: async () => bad("error", 500, { error: "write_failed" }) } });
  removeLink(a.root, "local").click();
  await settle();
  const err = byClass(a.rail(), "p2-nt-err")[0];
  assert.ok(err);
  assert.equal(text(byClass(a.rail(), "s4-rh")[0]), STRINGS.review_h);
  assert.equal(byClass(a.rail(), "s4-chg").length, 0, "no change line without a preview");
  assert.deepEqual(footTexts(a), [STRINGS.ed_save_plain, STRINGS.ed_cancel]);
  assert.ok(off(footButtons(a)[0]) && !off(footButtons(a)[1]));
  tag(err, "button")[0].click();
  await settle();
  assert.equal(byClass(a.root, "p2-nt").length, 0);
  assert.equal(text(byClass(a.rail(), "s4-rh")[0]), STRINGS.review_h);
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.equal(removeLinks(a.root).length, 2);
});

// One round of each op through the fake server: the saved line, the undone line, and the last-change line a reload
// draws from the history. Nothing shows a null, an undefined or an open slot.
async function round(m, name, begin, want) {
  const a = app({ data: dataOf(m.start), backend: worldFlow(m) });
  await begin(a);
  btn(a.root, want.save).click();
  await settle();
  assert.equal(okMark(a.root), "✓", name);
  assert.equal(okLine(a.root), want.saved, name);
  assert.equal(pathLine(a.root), want.backup, name + ": the backup line");
  noGaps(a.root, name + " after the save");
  assert.equal(a.log.save.length, 1, name);
  await a.press(STRINGS.ed_undo);
  assert.equal(okLine(a.root), want.undone, name);
  assert.equal(pathLine(a.root), want.restored, name + ": the restored line");
  noGaps(a.root, name + " after the undo");
  // After a reload the history draws the last change, from the row alone.
  const saved = app({ data: dataOf(m.after_save) });
  assert.equal(quiet(saved.root), want.lastSaved, name);
  noGaps(saved.root, name + " last change");
  const undone = app({ data: dataOf(m.after_undo) });
  assert.equal(quiet(undone.root), want.lastUndone, name);
  noGaps(undone.root, name + " last undo");
  return a;
}

test("round: create a file, save and undo, with no backup line and the words for a file removed", async () => {
  const edit = CR.save.edit;
  const row = CR.after_undo.history.rows[0];
  const a = await round(CR, "create", (x) => x.choose("high"), {
    save: "Create " + LOCAL,
    saved: T("ed_saved_created_t", { file: LOCAL, level: "high" }),
    backup: null,
    undone: T("ed_undone_removed_file_t", { file: LOCAL }),
    restored: null,
    lastSaved: T("ed_last_created_t", { when: when(edit), file: LOCAL, new: "high" }),
    lastUndone: T("ed_last_undone_t", { when: when(row), file: LOCAL }),
  });
  assert.equal(a.log.save[0].value, "high");
  assert.equal(a.log.save[0].target, CR.target);
  assert.equal(byClass(stripOf(a.root), "cmp").length + byClass(stripOf(a.root), "pa").length, 0, "no path and no cmp line");
});

test("round: create a file and its folder, and undo removes both", async () => {
  const edit = CRD.save.edit;
  const row = CRD.after_undo.history.rows[0];
  assert.deepEqual([CRD.undo.removed_file, CRD.undo.removed_dir], [true, true]);
  await round(CRD, "create_dir", (x) => x.choose("high"), {
    save: "Create " + LOCAL,
    saved: T("ed_saved_created_t", { file: LOCAL, level: "high" }),
    backup: null,
    undone: T("ed_undone_removed_both_t", { file: LOCAL }),
    restored: null,
    lastSaved: T("ed_last_created_t", { when: when(edit), file: LOCAL, new: "high" }),
    lastUndone: T("ed_last_undone_t", { when: when(row), file: LOCAL }),
  });
});

test("round: add a line to a file, save and undo", async () => {
  const edit = INS.save.edit;
  const row = INS.after_undo.history.rows[0];
  await round(INS, "insert", (x) => x.choose("high"), {
    save: LOCAL_SAVE,
    saved: T("ed_saved_t", { file: LOCAL, level: "high" }),
    backup: T("ed_saved_backup", { path: edit.backup_display }),
    undone: T("ed_undone_t", { file: LOCAL }),
    restored: T("ed_undone_path", { path: INS.undo.restored_from_display }),
    lastSaved: T("ed_last_added_t", { when: when(edit), file: LOCAL, new: "high" }) + " " + T("ed_saved_backup", { path: edit.backup_display }),
    lastUndone: T("ed_last_undone_t", { when: when(row), file: LOCAL }) + " " + T("ed_undone_path", { path: row.restored_from_display }),
  });
});

test("round: remove a line, save and undo, and the saved line says what a new session runs", async () => {
  const edit = RM.save.edit;
  const row = RM.after_undo.history.rows[0];
  const a = await round(RM, "remove", async (x) => { removeLink(x.root, "local").click(); await settle(); }, {
    save: "Remove line 2 from " + LOCAL,
    saved: T("ed_saved_removed_t", { file: LOCAL, level: "low" }),
    backup: T("ed_saved_backup", { path: edit.backup_display }),
    undone: T("ed_undone_t", { file: LOCAL }),
    restored: T("ed_undone_path", { path: RM.undo.restored_from_display }),
    lastSaved: T("ed_last_removed_t", { when: when(edit), file: LOCAL, old: "high" }) + " " + T("ed_saved_backup", { path: edit.backup_display }),
    lastUndone: T("ed_last_undone_t", { when: when(row), file: LOCAL }) + " " + T("ed_undone_path", { path: row.restored_from_display }),
  });
  assert.deepEqual(a.log.save[0], { pv: RM.local_preview, target: RM.local_target, value: null, action: "remove" });
  assert.equal(removeLinks(a.root).length, 2, "the link is back at rest");
});

test("round: a remove saves with its own words when it changes nothing or the result is not known", async () => {
  // The line didn't decide what runs.
  const pv = RM.project_preview;
  const projectEdit = { ...RM.save.edit, file_display: "project/.claude/settings.json" };
  const a = app({ data: dataOf(RM.start), backend: worldFlow(RM, { save: async () => ok({ edit: projectEdit }) }) });
  removeLink(a.root, "project").click();
  await settle();
  btn(a.root, STRINGS.ed_remove_anyway).click();
  await settle();
  assert.equal(pv.no_effect, true);
  assert.equal(okLine(a.root), T("ed_saved_removed_no_effect_t", { file: "settings.json" }));
  // The dashboard can't say what runs after it.
  const u = app({ data: dataOf(RMUNK.start), backend: { preview: async () => ok(RMUNK.user_preview), save: async () => ok({ edit: { ...RM.save.edit, file_display: "config/settings.json" } }) } });
  removeLink(u.root, "user").click();
  await settle();
  btn(u.root, T("ed_save_remove", { line: 2, file: "settings.json" })).click();
  await settle();
  assert.equal(okLine(u.root), T("ed_saved_removed_unknown_t", { file: "settings.json" }));
  noGaps(u.root);
});

test("git: a local file git doesn't ignore warns and keeps Save on, an unknown result is a quiet line, and the rest say nothing", async () => {
  const gitOf = async (state) => {
    const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(withGit(S.previews[v], state)) } });
    await a.choose("high");
    return a;
  };
  const warn = await gitOf("not_ignored");
  const notes_ = nts(warn.rail(), "warn");
  assert.equal(notes_.length, 1);
  assert.equal(text(byClass(notes_[0], "p2-nt-h")[0]), "▲" + STRINGS.ed_git_warn_h);
  assert.equal(text(tag(notes_[0], "p")[0]), T("ed_git_warn_t", { file: LOCAL }));
  assert.deepEqual(footTexts(warn), [LOCAL_SAVE, STRINGS.ed_cancel], "Save keeps its usual words");
  assert.ok(hasClass(footButtons(warn)[0], "p2-pri") && !off(footButtons(warn)[0]), "Save stays on and primary");
  assert.equal(text(byClass(slotOf(warn.root, "pick"), "s4-hint")[0]), STRINGS.ed_nothing_yet);
  const unknown = await gitOf("unknown");
  assert.equal(nts(unknown.rail(), "warn").length, 0);
  assert.deepEqual(noteTexts(unknown.rail()), [T("ed_git_unknown", { file: LOCAL })]);
  assert.ok(hasClass(footButtons(unknown)[0], "p2-pri"));
  for (const state of ["ignored", "no_repo", null]) {
    const quietOne = await gitOf(state);
    assert.equal(nts(quietOne.rail(), "warn").length, 0, String(state));
    assert.deepEqual(noteTexts(quietOne.rail()), [], String(state));
    assert.equal(quietOne.rail().textContent.includes(STRINGS.ed_git_warn_h) || quietOne.rail().textContent.includes("git ignores"), false, String(state));
  }
});

test("stale: a file that appeared and a file that went each have their heading, and show the fresh preview", async () => {
  const a = app({ data: dataOf(CR.start), backend: worldFlow(CR, { save: async () => bad("stale", 409, NST.appeared) }) });
  await a.choose("high");
  btn(a.root, "Create " + LOCAL).click();
  await settle();
  const warn = byClass(a.rail(), "p2-nt-warn")[0];
  assert.equal(text(byClass(warn, "p2-nt-h")[0]), "▲" + T("ed_stale_appeared_h", { file: LOCAL }));
  assert.equal(text(tag(warn, "p")[0]), STRINGS.ed_stale_appeared_t);
  assert.equal(NST.appeared.preview.op, "insert");
  assert.equal(text(byClass(a.rail(), "s4-sub")[0]), T("ed_card_add", { line: NST.appeared.preview.line, file: LOCAL }), "the fresh preview is an add");
  assert.deepEqual(footTexts(a), [LOCAL_SAVE, STRINGS.ed_cancel]);
  assert.equal(byClass(a.rail(), "p2-tag").length, 0);
  assert.equal(a.log.refresh, 1);
  assert.equal(a.log.save.length, 1);
  const g = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("stale", 409, NST.removed) } });
  await g.choose("high");
  btn(g.root, LOCAL_SAVE).click();
  await settle();
  const gone = byClass(g.rail(), "p2-nt-warn")[0];
  assert.equal(text(byClass(gone, "p2-nt-h")[0]), "▲" + T("ed_stale_removed_h", { file: LOCAL }));
  assert.equal(text(tag(gone, "p")[0]), STRINGS.ed_stale_removed_t);
  assert.equal(NST.removed.preview.op, "create");
  assert.deepEqual(byClass(g.rail(), "p2-tag").map(text), [STRINGS.ed_diff_new_tag], "the fresh preview is a new file");
  assert.deepEqual(footTexts(g), ["Create " + LOCAL, STRINGS.ed_cancel]);
  assert.ok(order(g.root, gone) < order(g.root, byClass(g.root, "p2-df")[0]));
  noGaps(g.root);
});

test("stale: a remove with no fresh preview says the line is gone and drops back to rest, with the notice over it", async () => {
  fresh();
  const stale = { error: "stale", changed: "file", changed_files: [{ layer: "local", file_display: "project/.claude/settings.local.json" }], preview: null };
  const a = app({ data: dataOf(RM.start), backend: worldFlow(RM, { save: async () => bad("stale", 409, stale), refresh: () => ({}) }) });
  removeLink(a.root, "local").click();
  await settle();
  btn(a.root, T("ed_save_remove", { line: 2, file: LOCAL })).click();
  await settle();
  assert.deepEqual(a.log.save.map((x) => x.action), ["remove"]);
  const note = byClass(a.rail(), "p2-nt-warn")[0];
  assert.equal(text(byClass(note, "p2-nt-h")[0]), "▲" + T("ed_stale_file_h", { file: LOCAL }));
  assert.equal(text(tag(note, "p")[0]), STRINGS.ed_stale_gone_t);
  assert.equal(byClass(a.root, "p2-df").length, 0);
  assert.equal(footButtons(a).length, 0);
  assert.ok(levelInputs(a.root).every((r) => !off(r)), "the picker is back");
  assert.equal(removeLinks(a.root).length, 2, "and so are the links");
  assert.equal(pendOf(a.root).length, 0);
  assert.deepEqual(flowMod.notSavedProjects(), []);
  assert.equal(a.log.refresh, 1);
  // With a fresh preview the remove stays, as the fresh remove preview.
  const kept = clone(RM.local_preview);
  const b = app({ data: dataOf(RM.start), backend: worldFlow(RM, { save: async () => bad("stale", 409, { ...stale, preview: kept }), refresh: () => ({}) }) });
  removeLink(b.root, "local").click();
  await settle();
  btn(b.root, T("ed_save_remove", { line: 2, file: LOCAL })).click();
  await settle();
  assert.equal(text(tag(byClass(b.rail(), "p2-nt-warn")[0], "p")[0]), STRINGS.ed_stale_file_t);
  assert.deepEqual(footTexts(b), [T("ed_save_remove", { line: 2, file: LOCAL }), STRINGS.ed_cancel]);
  btn(b.root, T("ed_save_remove", { line: 2, file: LOCAL })).click();
  await settle();
  assert.deepEqual(b.log.save.map((x) => x.action), ["remove", "remove"], "the second Save is still a remove");
});

test("remove: a save the server refuses ends the remove and loads the files again", async () => {
  const a = app({ data: dataOf(RM.start), backend: worldFlow(RM, { save: async () => bad("error", 400, { error: "not_editable" }) }) });
  removeLink(a.root, "local").click();
  await settle();
  btn(a.root, T("ed_save_remove", { line: 2, file: LOCAL })).click();
  await settle();
  assert.equal(a.log.refresh, 1);
  assert.equal(text(byClass(byClass(a.rail(), "p2-nt-err")[0], "p2-nt-h")[0]), "✕" + STRINGS.ed_err_not_editable);
  assert.equal(byClass(a.root, "p2-df").length, 0);
  assert.equal(pendOf(a.root).length, 0);
  assert.equal(removeLinks(a.root).length, 2);
});

test("create: a failed write names the folder, and says the dashboard made one when it did", async () => {
  const folder = "project/.claude";
  const run = async (body) => {
    const a = app({ data: dataOf(CR.start), backend: worldFlow(CR, { save: async () => bad("error", 500, body) }) });
    await a.choose("high");
    btn(a.root, "Create " + LOCAL).click();
    await settle();
    return a;
  };
  const left = await run({ error: "write_failed", file_unchanged: true, dir_left: true });
  const alert = byClass(left.rail(), "p2-nt-err")[0];
  assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + STRINGS.ed_fail_create_h);
  assert.deepEqual(tag(alert, "p").map(text), [T("ed_fail_create_t", { folder }), STRINGS.ed_fail_dir_left]);
  assert.deepEqual(byClass(alert, "pa").map(text), [folder]);
  assert.equal(byClass(left.root, "p2-df").length, 1, "the review stays");
  assert.ok(btn(left.root, STRINGS.ed_try_again));
  assert.equal(FElement.focused, btn(left.root, STRINGS.ed_try_again));
  noGaps(left.root);
  const plain = await run({ error: "write_failed", file_unchanged: true });
  assert.deepEqual(tag(byClass(plain.rail(), "p2-nt-err")[0], "p").map(text), [T("ed_fail_create_t", { folder })], "no left-over line");
  // the next attempt starts clean
  const again = app({ data: dataOf(CR.start), backend: worldFlow(CR, { save: async () => bad("error", 500, { error: "write_failed", dir_left: true }) }) });
  await again.choose("high");
  btn(again.root, "Create " + LOCAL).click();
  await settle();
  assert.equal(tag(byClass(again.rail(), "p2-nt-err")[0], "p").length, 2);
  btn(again.root, STRINGS.ed_cancel).click();
  await settle();
  await again.choose("high");
  assert.equal(byClass(again.rail(), "p2-nt-err").length, 0, "Cancel and a new pick clear the failure");
  // a write that fails on an existing file keeps its own words, whatever dir_left says
  const old = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("error", 500, { error: "write_failed", dir_left: true }) } });
  await old.choose("high");
  btn(old.root, LOCAL_SAVE).click();
  await settle();
  assert.equal(text(byClass(byClass(old.rail(), "p2-nt-err")[0], "p2-nt-h")[0]), "✕" + STRINGS.ed_fail_h);
});

test("project folder gone: a refused save or preview says so for the two project files and uses the lock line for the user file", async () => {
  const gone = { error: "file_missing" };
  const save = async (layer) => {
    const pv = clone(CR.previews.high);
    pv.layer = layer;
    const a = app({ data: dataOf(CR.start), backend: worldFlow(CR, { preview: async () => ok(pv), save: async () => bad("error", 422, gone) }) });
    await a.choose("high");
    btn(a.root, "Create " + LOCAL).click();
    await settle();
    return text(byClass(byClass(a.rail(), "p2-nt-err")[0], "p2-nt-h")[0]);
  };
  assert.equal(await save("local"), "✕" + STRINGS.ed_fail_project_gone);
  assert.equal(await save("project"), "✕" + STRINGS.ed_fail_project_gone);
  assert.equal(await save("user"), "✕" + STRINGS.ed_lock_file_missing);
  // A preview refused the same way, for a pick of the local file and of a remove.
  const a = app({ data: dataOf(CR.start), backend: { preview: async () => bad("error", 422, gone) } });
  await a.choose("high");
  assert.equal(text(byClass(byClass(a.rail(), "p2-nt-err")[0], "p2-nt-h")[0]), "✕" + STRINGS.ed_fail_project_gone);
  const r = app({ data: dataOf(RM.start), backend: { preview: async () => bad("error", 422, gone) } });
  removeLink(r.root, "local").click();
  await settle();
  assert.equal(text(byClass(byClass(r.rail(), "p2-nt-err")[0], "p2-nt-h")[0]), "✕" + STRINGS.ed_fail_project_gone);
  // A repeated key refused on save is a lock line like the others.
  const k = app({ data: dataOf(RM.start), backend: worldFlow(RM, { save: async () => bad("error", 422, { error: "repeated_key" }) }) });
  removeLink(k.root, "local").click();
  await settle();
  btn(k.root, T("ed_save_remove", { line: 2, file: LOCAL })).click();
  await settle();
  assert.equal(text(byClass(byClass(k.rail(), "p2-nt-err")[0], "p2-nt-h")[0]), "✕" + STRINGS.ed_lock_repeated_key);
  assert.equal(removeLinks(k.root).length, 2);
});

test("undo of a create: a file put back says to check it, with no path, and an unverified reread says the same", async () => {
  const row = CR.save.edit;
  const raced = app({ data: dataOf(CR.after_save), backend: { undo: async () => bad("raced", 409, { error: "raced", edit: CR.undo.edit, matches_backup: false, restored_from_display: null, settings: CR.undo.settings }) } });
  await raced.press(STRINGS.ed_undo);
  const warn = byClass(stripOf(raced.root), "p2-nt-warn")[0];
  assert.equal(text(byClass(warn, "p2-nt-h")[0]), "▲" + T("ed_raced_h", { file: LOCAL }));
  assert.deepEqual(tag(warn, "p").map(text), [STRINGS.ed_raced_create_t]);
  assert.equal(byClass(warn, "pa").length, 0, "no path");
  assert.equal(CR.save.edit.backup_display, null);
  const unverified = app({ data: dataOf(CR.after_save), backend: { undo: async () => bad("unverified", 500, { error: "unverified", stage: "reread", file_unchanged: false, edit: row }) } });
  await unverified.press(STRINGS.ed_undo);
  const alert = byClass(stripOf(unverified.root), "p2-nt-err")[0];
  assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + STRINGS.ed_unverified_reread_h);
  assert.deepEqual(tag(alert, "p").map(text), [STRINGS.ed_unverified_create_t]);
  // The other stage and the other ops keep their own words.
  const fsync = app({ data: dataOf(CR.after_save), backend: { undo: async () => bad("unverified", 500, { error: "unverified", stage: "fsync", file_unchanged: false }) } });
  await fsync.press(STRINGS.ed_undo);
  assert.equal(text(byClass(byClass(stripOf(fsync.root), "p2-nt-err")[0], "p2-nt-h")[0]), "✕" + STRINGS.ed_unverified_fsync_h);
  const path_ = "config/routing-dashboard/backups/x/000001-a.bak";
  const other = app({ data: afterSave(), backend: { undo: async () => bad("unverified", 500, { error: "unverified", stage: "reread", backup_display: path_ }) } });
  await other.press(STRINGS.ed_undo);
  assert.equal(text(tag(byClass(stripOf(other.root), "p2-nt-err")[0], "p")[0]), T("ed_unverified_reread_t", { path: path_ }));
  noGaps(raced.root);
});

test("undo of a create: a file that changed after the save leaves no Undo, and the line says to delete it by hand", async () => {
  const history = clone(CR.after_save.history);
  Object.assign(history.rows[0], { undoable: false, not_undoable_reason: "changed_since_save" });
  const a = app({ data: dataOf(CR.after_save, { history }) });
  assert.ok(hasClass(okRow(a.root), "s4-ok-warn"), "a warning row");
  const line = text(okRow(a.root));
  assert.equal(line, "▲" + T("ed_undo_stale_h", { file: LOCAL }) + " " + STRINGS.ed_undo_stale_created_t);
  assert.equal(byClass(stripOf(a.root), "pa").length, 0, "no path");
  assert.deepEqual(tag(stripOf(a.root), "button").map(text), [STRINGS.ed_older_link]);
  // The press answer offers Undo anyway, which deletes the created file.
  const c = app({
    data: dataOf(CR.after_save),
    backend: {
      undo: async () => bad("error", 409, { error: "changed_since_save", backup_display: null }),
      refresh: () => ({ history: refreshed(CR.after_save.history, NOW_STALE) }),
    },
  });
  await c.press(STRINGS.ed_undo);
  assert.equal(okLine(c.root), T("ed_undo_stale_h", { file: LOCAL }) + " " + STRINGS.ed_anyway_offer_created_t);
  assert.equal(pathLine(c.root), null);
  assert.deepEqual(tag(stripOf(c.root), "button").map(text).slice(0, 2), [STRINGS.ed_anyway_btn, STRINGS.ed_dismiss]);
  const r = app({ data: dataOf(RM.after_save) });
  assert.equal(quiet(r.root).startsWith("Last change"), true);
  const h2 = clone(RM.after_save.history);
  Object.assign(h2.rows[0], { undoable: false, not_undoable_reason: "changed_since_save" });
  const s = app({ data: dataOf(RM.after_save, { history: h2 }) });
  assert.equal(text(byClass(stripOf(s.root), "s4-ok")[0]), "▲" + T("ed_undo_stale_h", { file: LOCAL }) + " " + T("ed_undo_stale_t", { path: h2.rows[0].backup_display }));
});

test("settle: a remove asks for its preview again on a new targets answer, blocks on a repeated key, and ends when its line goes", async () => {
  fresh();
  const a = app({ data: dataOf(RM.start), backend: worldFlow(RM) });
  removeLink(a.root, "local").click();
  await settle();
  assert.equal(a.log.preview.length, 1);
  a.draw();
  assert.equal(a.log.preview.length, 1, "the same answer drawn again asks for nothing");
  a.st.targets = a.wrapT(clone(RM.start.targets));
  a.draw();
  await settle();
  assert.equal(a.log.preview.length, 2, "a new answer asks again");
  assert.deepEqual(a.log.preview[1], [RM.local_target, null, "remove"]);
  assert.equal(byClass(a.root, "p2-df").length, 1);
  // The server now says the setting is in the file twice.
  const twice = clone(RM.start.targets);
  targetOf(twice, "local").remove.lock_reason = "repeated_key";
  a.st.targets = a.wrapT(twice);
  a.draw();
  await settle();
  assert.equal(a.log.preview.length, 2, "a blocked remove asks for nothing");
  assert.equal(text(byClass(nts(a.rail(), "warn")[0], "p2-nt-h")[0]), "▲" + T("ed_remove_blocked_h", { line: 2 }));
  assert.equal(saveButtons(a.root).length, 0);
  assert.equal(byClass(a.root, "p2-df").length, 0);
  assert.equal(pendOf(a.root).length, 0);
  // Back to a line that can go: the preview is asked for again.
  a.st.targets = a.wrapT(clone(RM.start.targets));
  a.draw();
  await settle();
  assert.equal(a.log.preview.length, 3);
  assert.deepEqual(footTexts(a), [T("ed_save_remove", { line: 2, file: LOCAL }), STRINGS.ed_cancel]);
  assert.equal(pendOf(a.root).length, 1);
  // The line goes: the remove ends, and the rest rail is back.
  const goneT = clone(RM.start.targets);
  goneT.targets = goneT.targets.filter((x) => x.layer !== "local");
  Object.assign(rowOfFiles(goneT, "local"), { state: "no_line", line: null, value: null, status: null, target: null });
  a.st.targets = a.wrapT(goneT);
  a.draw();
  await settle();
  assert.equal(byClass(a.root, "p2-df").length, 0);
  assert.equal(text(byClass(a.rail(), "s4-rh")[0]), STRINGS.why_h);
  assert.deepEqual(removeLinks(a.root).map((b) => b.getAttribute("data-edit-focus")), ["remove:project"]);
  assert.equal(pendOf(a.root).length, 0);
  assert.ok(levelInputs(a.root).every((r) => !off(r)));
  // A project lock ends it too.
  removeLink(a.root, "project").click();
  await settle();
  assert.equal(byClass(a.root, "p2-df").length, 1);
  const lock = clone(goneT);
  lock.project_lock = "not_repo_root";
  a.st.targets = a.wrapT(lock);
  a.draw();
  assert.deepEqual(noteTexts(a.rail()), [STRINGS.ed_lock_not_repo_root]);
  assert.equal(pendOf(a.root).length, 0);
});

test("flow: a late save answer for a remove lands in its project's flow, clears it and shows the result when the owner comes back", async () => {
  const gate = {};
  const a = app({
    data: dataOf(RM.start),
    backend: worldFlow(RM, { save: () => new Promise((resolve) => { gate.go = () => resolve(ok(RM.save)); }) }),
  });
  const keyA = a.key;
  removeLink(a.root, "local").click();
  await settle();
  btn(a.root, T("ed_save_remove", { line: 2, file: LOCAL })).click();
  await settle();
  a.use(keyA + "-b", dataOf(RM.start));
  assert.equal(byClass(a.root, "p2-df").length, 0, "project B starts at rest");
  assert.equal(removeLinks(a.root).length, 2, "and has its links");
  gate.go();
  await settle();
  assert.equal(strips(a.root).length, 0, "A's result is not drawn in B");
  assert.equal(flowMod.notSavedProjects().includes(keyA), false, "A no longer waits on Save");
  a.use(keyA, dataOf(RM.start));
  assert.equal(byClass(a.root, "p2-df").length, 0);
  assert.equal(okLine(a.root), T("ed_saved_removed_t", { file: LOCAL, level: "low" }));
  assert.equal(removeLinks(a.root).length, 2);
});

test("text nodes: a hostile path, line and folder in a create, an add and a remove make no element", async () => {
  const evil = "<img src=x onerror=alert(1)>";
  parsed.length = 0;
  const pv = clone(CR.previews.high);
  pv.diff.file_display = "project/" + evil + "/settings.local.json";
  pv.diff.hunks[0].lines[1].text = evil;
  const a = app({ data: dataOf(CR.start), backend: worldFlow(CR, { preview: async () => ok(pv), save: async () => bad("error", 500, { error: "write_failed", dir_left: true }) }) });
  await a.choose("high");
  btn(a.root, "Create " + LOCAL).click();
  await settle();
  assert.equal(a.root.find((n) => n.tagName === "img").length, 0);
  assert.ok(a.root.textContent.includes(evil), "shown as text");
  const rm = clone(RM.local_preview);
  rm.diff.hunks[0].lines.find((l) => l.kind === "del").text = evil;
  const b = app({ data: dataOf(RM.start), backend: { preview: async () => ok(rm) } });
  removeLink(b.root, "local").click();
  await settle();
  assert.equal(b.root.find((n) => n.tagName === "img").length, 0);
  assert.deepEqual(parsed, []);
});

// ---------------------------------------------------------------- verifier batch

test("undo: an edit the server no longer knows says so and loads the history again", async () => {
  const a = app({ data: dataOf(CR.after_save), backend: { undo: async () => bad("error", 404, { error: "unknown_edit" }), refresh: () => ({}) } });
  await a.press(STRINGS.ed_undo);
  assert.equal(a.log.refresh, 1, "the page refreshes, so Dismiss cannot bring the dead Undo back");
  assert.match(text(stripOf(a.root)), new RegExp(STRINGS.ed_err_unknown_edit.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
});

test("undo: a stale undo (409 stale) shows the stale-undo line and loads the history again", async () => {
  const body = { error: "stale", changed: "file", changed_files: [], preview: null };
  const a = app({ data: afterSave(), backend: { undo: async () => bad("stale", 409, body), refresh: () => ({ history: refreshed(S.after_save.history, NOW_STALE) }) } });
  await a.press(STRINGS.ed_undo);
  assert.equal(a.log.refresh, 1);
  assert.ok(hasClass(okRow(a.root), "s4-ok-warn"));
  assert.match(text(stripOf(a.root)), new RegExp(T("ed_undo_stale_h", { file: "settings.local.json" })));
  assert.equal(text(stripOf(a.root)).includes(STRINGS.ed_err_forbidden), false, "not the generic refusal line");
  assert.deepEqual(tag(stripOf(a.root), "button").map(text).slice(0, 2), [STRINGS.ed_anyway_btn, STRINGS.ed_dismiss]);
});

test("strip: a replace row with no old value reads as an added line, and its undo as an undone change", () => {
  const row = clone(S.after_save.history.rows[0]);
  delete row.old_value;
  const a = app({ data: { ...afterSave(), history: { ...S.after_save.history, rows: [row] } } });
  const added = T("ed_last_added_t", { when: format.fmtTime(row.time), new: "high", file: "settings.local.json" });
  assert.equal(text(byClass(stripOf(a.root), "s4-note")[0]).startsWith(added), true);
  const undo = { ...row, kind: "undo", old_value: "high" };
  delete undo.new_value;
  const b = app({ data: { ...afterSave(), history: { ...S.after_save.history, rows: [undo] } } });
  const undone = T("ed_last_undone_t", { when: format.fmtTime(undo.time), file: "settings.local.json" });
  assert.equal(text(byClass(stripOf(b.root), "s4-note")[0]).startsWith(undone), true);
  assert.equal(text(stripOf(b.root)).includes(" to ."), false);
});

test("create: a raced or unverified save has a body that says there is no backup", async () => {
  const run = async (kind, body) => {
    const a = app({ data: dataOf(CR.start), backend: worldFlow(CR, { save: async () => bad(kind, kind === "raced" ? 409 : 500, body) }) });
    await a.choose("high");
    btn(a.root, "Create " + LOCAL).click();
    await settle();
    return a;
  };
  const raced = await run("raced", { error: "raced", edit: CR.save.edit, backup_display: null, settings: CR.save.settings });
  assert.deepEqual(tag(byClass(raced.rail(), "p2-nt-warn")[0], "p").map(text), [STRINGS.ed_raced_new_t]);
  for (const stage of ["reread", "fsync"]) {
    const un = await run("unverified", { error: "unverified", stage, file_unchanged: false, backup_display: null });
    const want = stage === "fsync" ? STRINGS.ed_unverified_fsync_new_t : STRINGS.ed_unverified_new_t;
    assert.deepEqual(tag(byClass(un.rail(), "p2-nt-err")[0], "p").map(text), [want], stage);
  }
});

test("create: a failed write with a missing config folder names the folder, not the project folder", async () => {
  const answer = { error: "config_dir_missing", file_unchanged: true, config_dir_display: "~/gone/.claude" };
  const a = app({ data: dataOf(CR.start), backend: worldFlow(CR, { save: async () => bad("error", 500, answer) }) });
  await a.choose("high");
  btn(a.root, "Create " + LOCAL).click();
  await settle();
  const alert = byClass(a.rail(), "p2-nt-err")[0];
  assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + STRINGS.ed_fail_h);
  assert.deepEqual(tag(alert, "p").map(text), [T("ed_fail_config_dir_t", { config_dir: answer.config_dir_display })]);
  assert.deepEqual(byClass(alert, "pa").map(text), [answer.config_dir_display]);
  assert.ok(btn(a.root, STRINGS.ed_try_again));
});

test("stale: a remove with no fresh preview leaves a notice with a Dismiss that clears it", async () => {
  fresh();
  const stale = { error: "stale", changed: "file", changed_files: [{ layer: "local", file_display: "project/.claude/settings.local.json" }], preview: null };
  const a = app({ data: dataOf(RM.start), backend: worldFlow(RM, { save: async () => bad("stale", 409, stale), refresh: () => ({}) }) });
  removeLink(a.root, "local").click();
  await settle();
  btn(a.root, T("ed_save_remove", { line: 2, file: LOCAL })).click();
  await settle();
  const note = byClass(a.rail(), "p2-nt-warn")[0];
  assert.deepEqual(tag(note, "button").map(text), [STRINGS.ed_dismiss]);
  tag(note, "button")[0].click();
  await settle();
  assert.equal(byClass(a.rail(), "p2-nt-warn").length, 0);
});

// ---------------------------------------------------------------- the last review fixes

const inRail = (n) => hasClass(n.parentNode, "s4-rb");

test("frames: raced, unverified and ledger notices sit in the rail body with Dismiss inside them, and Not saved goes after a write", async () => {
  const path_ = "config/routing-dashboard/backups/x/000001-a.bak";
  const cases = [
    ["raced", () => bad("raced", 409, { error: "raced", edit: S.save.edit, backup_display: path_, settings: S.save.settings }), "p2-nt-warn", 0],
    ["unverified", () => bad("unverified", 500, { error: "unverified", stage: "reread", file_unchanged: false, backup_display: path_ }), "p2-nt-err", 0],
    ["ledger", () => bad("error", 500, { error: "ledger_damaged", file_unchanged: true, ledger_display: "config/routing-dashboard/backups/x/ledger.json" }), "p2-nt-err", 1],
  ];
  for (const [name, answer, cls, pending] of cases) {
    const a = app({ data: baseData(), backend: { ...saveFlow(), save: async () => answer() } });
    await a.choose("high");
    btn(a.root, LOCAL_SAVE).click();
    await settle();
    const note = byClass(a.rail(), cls)[0];
    assert.ok(note, name);
    assert.ok(inRail(note), name + ": wrapped in the rail body");
    assert.equal(byClass(a.rail(), "p2-ctl").length, 0, name + ": no loose control row");
    assert.deepEqual(tag(note, "button").map(text), [STRINGS.ed_dismiss], name);
    assert.ok(hasClass(tag(note, "button")[0].parentNode, "p2-btns"), name + ": Dismiss is the notice's own button");
    assert.equal(FElement.focused, tag(note, "button")[0], name);
    assert.equal(pendOf(a.root).length, pending, name + ": Not saved");
    assert.deepEqual(flowMod.notSavedProjects(), pending ? [a.key] : [], name);
  }
});

test("rail notices: the stop panel, the nothing-to-save rail and the blocked remove sit in the rail body", async () => {
  const s = real("model_limit");
  const stopTargets = clone(s.targets);
  shut(stopTargets, "xhigh");
  const stop = app({ data: { settings: s.settings, targets: stopTargets, history: s.history } });
  await stop.choose("xhigh");
  assert.ok(inRail(nts(stop.rail(), "warn")[0]), "stop panel");
  const u = real("user_unknown");
  const targets = clone(u.targets);
  for (const name of ["low", "medium", "high"]) shut(targets, name);
  fileOf(targets, "xhigh", "user").pickable = true;
  recount(targets);
  const none = app({ data: { settings: u.settings, targets, history: u.history } });
  await none.choose("high");
  assert.ok(inRail(nts(none.rail(), "warn")[0]), "nothing to save");
  fresh();
  const blocked = app({ data: dataOf(RMREP) });
  removeLink(blocked.root, "local").click();
  await settle();
  assert.ok(inRail(nts(blocked.rail(), "warn")[0]), "blocked remove");
});

test("nothing to save: when every file is locked, the first file's lock sits under the Can't save line", async () => {
  const w = worldData("lowered");
  const targets = clone(w.targets);
  levelOf(targets, "high").cap_first = false;
  shut(targets, "high");
  levelOf(targets, "high").limits = [];
  levelOf(targets, "high").files.forEach((f, i) => { f.lock_reason = i === 0 ? "not_on_trail" : "symlink"; });
  const a = app({ data: { ...w, targets }, backend: { preview: never } });
  await a.choose("high");
  const warn = nts(a.rail(), "warn")[0];
  assert.equal(text(byClass(warn, "p2-nt-h")[0]), "▲" + T("ed_nosave_level", { level: "high" }));
  assert.deepEqual(tag(warn, "p").map(text), [STRINGS.ed_lock_not_on_trail]);
  // One file without a lock, and the line stays out.
  const open_ = clone(targets);
  levelOf(open_, "high").files[1].lock_reason = null;
  const b = app({ data: { ...w, targets: open_ }, backend: { preview: never } });
  await b.choose("high");
  assert.deepEqual(tag(nts(b.rail(), "warn")[0], "p").map(text), []);
});

test("remove: the row whose line goes wears the picked style, and the others do not", async () => {
  fresh();
  const a = app({ data: dataOf(RM.start), backend: worldFlow(RM) });
  assert.equal(byClass(a.root, "is-pick").length, 0, "none at rest");
  removeLink(a.root, "local").click();
  await settle();
  const picked = byClass(a.root, "is-pick");
  assert.equal(picked.length, 1);
  assert.ok(text(picked[0]).includes(LOCAL));
  assert.ok(plainRows(a.root).includes(picked[0]), "a plain row, not a radio");
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.equal(byClass(a.root, "is-pick").length, 0, "gone after Cancel");
});

test("remove: Cancel puts focus back on that row's Remove line link", async () => {
  fresh();
  const a = app({ data: dataOf(RM.start), backend: worldFlow(RM) });
  removeLink(a.root, "project").click();
  await settle();
  assert.equal(FElement.focused, btn(a.root, STRINGS.ed_cancel));
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.equal(FElement.focused, removeLink(a.root, "project"));
  // A level change still hands focus back to the level radio
  await a.choose("low");
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.equal(FElement.focused, lvl(a.root, "high"));
  // and so does the blocked rail's Cancel
  const blocked = app({ data: dataOf(RMREP) });
  removeLink(blocked.root, "local").click();
  await settle();
  btn(blocked.root, STRINGS.ed_cancel).click();
  await settle();
  assert.equal(FElement.focused, removeLink(blocked.root, "local"));
});

// The browser test for Add waits on these signs: pressing the project row of an insert moves the pick to it, and the
// diff holds one added line, no deleted line and no New file tag. Save stays on.
test("add: the project row of an insert is picked on its own, with the effort line added and no New file tag", async () => {
  fresh();
  const a = app({ data: dataOf(INS.start), backend: worldFlow(INS) });
  await a.choose("high");
  assert.equal(fileOf(INS.start.targets, "high", "project").op, "insert");
  await a.pickRow("project");
  assert.deepEqual(checkedOf(rowInputs(a.root)), ["project"]);
  assert.ok(hasClass(rowOf(rowIn(a.root, "project")), "is-pick"));
  // The line above the new one gains a comma, so the diff may show it as deleted. No deleted line holds the setting.
  assert.ok(byClass(a.rail(), "p2-del").every((n) => !text(n).includes("effortLevel")), "an add removes no effort line");
  assert.ok(byClass(a.rail(), "p2-add").some((n) => text(n).includes('"effortLevel"') && text(n).includes('"high"')), "the added line holds the level");
  assert.equal(byClass(a.rail(), "p2-tag").length, 0, "an insert is not a new file");
  assert.ok(!off(footButtons(a)[0]), "Save is on");
  assert.deepEqual(a.log.save, []);
});

// The browser test for Remove then Cancel waits on these signs: nothing is saved or undone, the link is back and
// focused, the levels are on again and the diff and the marked row are gone.
test("remove: Cancel after a press saves nothing, and the link, the levels and the rest rows come back", async () => {
  fresh();
  const a = app({ data: dataOf(RM.start), backend: worldFlow(RM) });
  removeLink(a.root, "project").click();
  await settle();
  assert.equal(FElement.focused, btn(a.root, STRINGS.ed_cancel));
  assert.ok(levelInputs(a.root).every(off), "every level is off");
  assert.equal(byClass(a.root, "is-pick").length, 1);
  assert.ok(byClass(a.rail(), "p2-del").length > 0, "the diff deletes a line");
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.deepEqual(a.log.save, [], "nothing was saved");
  assert.equal(FElement.focused, removeLink(a.root, "project"));
  assert.ok(levelInputs(a.root).every((r) => !off(r)), "every level is on again");
  assert.equal(byClass(a.root, "is-pick").length, 0);
  assert.equal(byClass(a.root, "p2-df").length, 0);
  assert.equal(strips(a.root).length, 0, "no result line");
});

test("remove: the git warning stays off a removal and shows on a set", async () => {
  fresh();
  const pv = clone(RM.local_preview);
  pv.git_ignore = "not_ignored";
  const a = app({ data: dataOf(RM.start), backend: worldFlow(RM, { preview: async () => ok(pv) }) });
  removeLink(a.root, "local").click();
  await settle();
  assert.equal(nts(a.rail(), "warn").filter((n) => text(byClass(n, "p2-nt-h")[0]).includes(STRINGS.ed_git_warn_h)).length, 0);
  const setPv = clone(S.previews.high);
  setPv.git_ignore = "not_ignored";
  const b = app({ data: baseData(), backend: { ...saveFlow(), preview: async () => ok(setPv) } });
  await b.choose("high");
  assert.equal(nts(b.rail(), "warn").filter((n) => text(byClass(n, "p2-nt-h")[0]).includes(STRINGS.ed_git_warn_h)).length, 1);
});

test("write_failed: the failed-write notice scrolls into view, nearest, and focus stays on Try again", async () => {
  const calls = [];
  const original = FElement.prototype.scrollIntoView;
  FElement.prototype.scrollIntoView = function scrollIntoView(arg) { calls.push([this, arg]); };
  try {
    const a = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("error", 500, { error: "write_failed", file_unchanged: true }) } });
    await a.choose("high");
    btn(a.root, LOCAL_SAVE).click();
    await settle();
    const alert = byClass(a.rail(), "p2-nt-err")[0];
    assert.equal(calls.length, 1);
    assert.equal(calls[0][0], alert);
    assert.deepEqual(calls[0][1], { block: "nearest" });
    assert.equal(FElement.focused, btn(a.root, STRINGS.ed_try_again));
    // A save that works scrolls nothing
    const b = app({ data: baseData(), backend: saveFlow() });
    await b.choose("high");
    btn(b.root, LOCAL_SAVE).click();
    await settle();
    assert.equal(calls.length, 1);
  } finally {
    if (original) FElement.prototype.scrollIntoView = original; else delete FElement.prototype.scrollIntoView;
  }
  // With no scrollIntoView on the node the failure still draws
  const c = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("error", 500, { error: "write_failed", file_unchanged: true }) } });
  await c.choose("high");
  btn(c.root, LOCAL_SAVE).click();
  await settle();
  assert.equal(byClass(c.rail(), "p2-nt-err").length, 1);
});

test("create: a failed save that left the .claude folder behind drops the folder note", async () => {
  const run = async (answer) => {
    const a = app({ data: dataOf(CRD.start), backend: worldFlow(CRD, { save: async () => bad("error", 500, answer) }) });
    await a.choose("high");
    assert.deepEqual(noteTexts(a.rail()), [T("ed_new_dir_note", { file: LOCAL })]);
    btn(a.root, "Create " + LOCAL).click();
    await settle();
    return a;
  };
  const left = await run({ error: "write_failed", file_unchanged: true, dir_left: true });
  assert.deepEqual(noteTexts(left.rail()), [], "no note that says the folder isn't there");
  const plain = await run({ error: "write_failed", file_unchanged: true });
  assert.deepEqual(noteTexts(plain.rail()), [T("ed_new_dir_note", { file: LOCAL })], "the folder is still not there");
});

// ---------------------------------------------------------------- older backups, Undo anyway and restore

const backupMod = await import(JS + "edit_backup.js");
// The confirm drops a press that comes soon after its preview drew. The checks press it at once, so they turn the wait
// off, and the double-click check turns it back on.
flowMod.guard.ms = 0;
const BK = real("changed_since_save");
const BKFILE = "settings.json";
const BKPATH = "config/routing-dashboard/backups/x/000001-a.bak";
const bkRow = (over = {}) => ({ ...clone(BK.history.rows[0]), ...over });
const bkHist = (rows) => ({ ...clone(BK.history), rows });
// The newest row of a changed file with a good backup: Undo anyway reaches it, so the list leaves it out.
const rNewest = (over = {}) => bkRow({ id: "e9", undoable: false, not_undoable_reason: "changed_since_save", restore_state: null, undo_anyway: true, ...over });
const rOld = (id, over = {}) => bkRow({
  id, undoable: false, not_undoable_reason: "not_newest", restore_state: null, undo_anyway: false, before_absent: false, old_value: "low", ...over,
});
const bkPv = (over = {}) => ({
  edit: "e9", kind: "undo", layer: "project", shared: false, file_display: "project/.claude/settings.json", op: "replace", result: "replace",
  no_change: false, changed: "file", file_unparsed: false, removes_dir: false, creates_dir: false, backup_display: BKPATH,
  base_file: "HASH1", runs_before: "xhigh", runs_after: "low", repo_locked: false, git_ignore: "ignored", old_value: "xhigh", new_value: "low",
  diff: { file_display: "project/.claude/settings.json", hunks: [{ lines: [
    { kind: "del", old_line: 2, new_line: null, text: "  \"effortLevel\": \"xhigh\"" },
    { kind: "add", old_line: null, new_line: 2, text: "  \"effortLevel\": \"low\"" },
  ] }] },
  ...over,
});
const bkDone = (over = {}) => ({
  edit: bkRow({ id: "e10", kind: "undo", undoable: false, not_undoable_reason: "undo_row" }), settings: {}, matches_backup: true,
  restored_from_display: BKPATH, removed_file: false, removed_dir: false, replaced_display: "config/routing-dashboard/backups/x/000002-b.bak",
  replaced_file: true, ...over,
});
const bkBackend = (over = {}) => ({
  backupPreview: async (id, kind) => ok(bkPv({ edit: id, kind })),
  undoAnyway: async () => ok(bkDone()),
  restore: async () => ok(bkDone()),
  ...over,
});
const bkApp = (rows, { backend = {}, targets = BK.targets, ...rest } = {}) =>
  app({ data: { settings: BK.settings, targets, history: bkHist(rows) }, backend: bkBackend(backend), ...rest });
const focusKeyOf = () => (FElement.focused ? FElement.focused.getAttribute("data-edit-focus") : null);
const olderLink = (root) => buttons(root).find((b) => b.getAttribute("data-edit-focus") === "older");
const anywayBtn = (root) => buttons(root).find((b) => b.getAttribute("data-edit-focus") === "btn:anyway");
const railHead = (a) => text(byClass(a.rail(), "s4-rh")[0]);
const bkRows = (a) => byClass(a.rail(), "s4-bkrow");
// A level the picker takes: not the running one.
const offeredLevel = (root) => levelInputs(root).find((r) => !off(r) && !r.hasAttribute("checked")).value;
const bkBack = (over = {}) => ({ view: "review", kind: "undo", row: rNewest(), pv: bkPv(), busy: false, stale: false, from: "foot", ...over });

test("older rows: every row but the first when Undo or Undo anyway reaches it, in order, and none when the history is missing", () => {
  const rows = [rNewest(), rOld("e8"), bkRow({ id: "e7", undoable: true, undo_anyway: false }), rOld("e6", { restore_state: "same_as_file" })];
  // The foot draws the first row alone, so the newest row of a second file stays in the list.
  assert.deepEqual(backupMod.olderRows({ rows }).map((r) => r.id), ["e8", "e7", "e6"]);
  assert.deepEqual(backupMod.olderRows({ rows: [bkRow({ id: "e1", undoable: true, undo_anyway: false }), ...rows.slice(1)] }).map((r) => r.id), ["e8", "e7", "e6"]);
  assert.deepEqual(backupMod.olderRows({ rows: [rOld("e2"), rNewest()] }).map((r) => r.id), ["e2", "e9"], "only the first row is held back");
  assert.deepEqual(backupMod.olderRows(null), []);
  assert.deepEqual(backupMod.olderRows({}), []);
  assert.deepEqual(backupMod.olderRows({ rows: "x" }), []);
  assert.deepEqual(pickMod.olderRows({ rows }).map((r) => r.id), ["e8", "e7", "e6"], "the flow reads the same rule");
});

test("older backups: a second file's newest row can be reached from the list and restored", async () => {
  // Two files: the foot draws the newest row (file A, changed since the save), and file B's own newest row is undoable.
  const second = bkRow({ id: "e5", undoable: true, not_undoable_reason: null, restore_state: null, undo_anyway: false, layer: "local", file_display: "project/.claude/settings.local.json", old_value: "low" });
  const a = bkApp([rNewest(), second]);
  assert.ok(olderLink(a.root), "the link shows with only a second file's row left");
  olderLink(a.root).click();
  await settle();
  assert.deepEqual(bkRows(a).map((n) => n.getAttribute("data-edit-focus")), ["backup:e5"]);
  assert.equal(focusKeyOf(), "backup:e5");
  bkRows(a)[0].click();
  await settle();
  assert.deepEqual(a.log.backup, [["e5", "restore"]]);
  footButtons(a)[0].click();
  await settle();
  assert.deepEqual(a.log.restore, [["e5", "HASH1"]]);
  assert.equal(okLine(a.root), T("ed_back_done_restored_t", { file: BKFILE }));
});

test("rest strip: undo_anyway offers Undo anyway under the stale line, and a created file says it deletes the file", () => {
  const a = bkApp([rNewest()]);
  assert.ok(hasClass(okRow(a.root), "s4-ok-warn"));
  assert.equal(okRow(a.root).getAttribute("role"), "status");
  assert.equal(okLine(a.root), T("ed_undo_stale_h", { file: BKFILE }) + " " + STRINGS.ed_anyway_offer_t);
  const any = anywayBtn(a.root);
  assert.equal(text(any), STRINGS.ed_anyway_btn);
  assert.ok(hasClass(any, "s4-wide"));
  assert.equal(hasClass(any, "p2-pri"), false, "not the primary button");
  assert.equal(off(any), false);
  const made = bkApp([rNewest({ op: "create" })]);
  assert.equal(okLine(made.root), T("ed_undo_stale_h", { file: BKFILE }) + " " + STRINGS.ed_anyway_offer_created_t);
  assert.ok(anywayBtn(made.root));
  assert.equal(anyKey(made.root), false);
  noGaps(made.root);
});

test("rest strip: undo_anyway false keeps the stale line with the backup path and no button", () => {
  const a = bkApp([rNewest({ undo_anyway: false })]);
  assert.equal(okLine(a.root).startsWith(T("ed_undo_stale_h", { file: BKFILE })), true);
  assert.equal(okLine(a.root).includes(STRINGS.ed_anyway_offer_t), false);
  assert.equal(anywayBtn(a.root), undefined);
  assert.deepEqual(byClass(stripOf(a.root), "pa").map(text), [BK.history.rows[0].backup_display]);
  const made = bkApp([rNewest({ undo_anyway: false, op: "create", backup_display: null })]);
  assert.equal(okLine(made.root), T("ed_undo_stale_h", { file: BKFILE }) + " " + STRINGS.ed_undo_stale_created_t);
});

test("undo anyway: the button opens the preview, writes nothing, and the confirm sends the hash it carried", async () => {
  const a = bkApp([rNewest()]);
  await a.press(STRINGS.ed_anyway_btn);
  assert.deepEqual(a.log.backup, [["e9", "undo"]]);
  assert.equal(a.log.anyway.length + a.log.restore.length + a.log.undo.length, 0, "a preview writes nothing");
  assert.equal(railHead(a), STRINGS.ed_back_h_undo);
  assert.deepEqual(footTexts(a), [STRINGS.ed_back_go_undo, STRINGS.ed_cancel]);
  const [go, cancel] = footButtons(a);
  assert.equal(hasClass(go, "p2-pri"), false, "an Undo anyway is never the primary button");
  assert.equal(FElement.focused, cancel, "focus goes to Cancel");
  assert.equal(flowMod.S.back.view, "review");
  assert.equal(stripOf(a.root).childNodes.length, 0, "the last change waits");
  assert.equal(olderLink(a.root), undefined);
  go.click();
  await settle();
  assert.deepEqual(a.log.anyway, [["e9", "HASH1"]]);
  assert.equal(flowMod.S.back, null);
  assert.equal(okMark(a.root), "✓");
  assert.equal(okRow(a.root).getAttribute("role"), "status");
  assert.equal(okLine(a.root), T("ed_back_done_undo_t", { file: BKFILE }));
  assert.deepEqual(tag(stripOf(a.root), "button").filter((b) => !hasClass(b, "s4-link")).map(text), [STRINGS.ed_dismiss]);
  assert.equal(FElement.focused, btn(a.root, STRINGS.ed_dismiss));
  assert.deepEqual(hintLines(a.root), [T("ed_back_kept", { path: "config/routing-dashboard/backups/x/000002-b.bak" }), T("ed_undone_path", { path: BKPATH })], "two lines, one for each backup");
  assert.deepEqual(byClass(stripOf(a.root), "pa").map(text), ["config/routing-dashboard/backups/x/000002-b.bak", BKPATH]);
  assert.equal(flowMod.S.stripBusy, false);
});

test("undo anyway: Cancel from the foot returns to rest, with focus on Undo anyway, else on the link", async () => {
  const a = bkApp([rNewest()]);
  await a.press(STRINGS.ed_anyway_btn);
  footButtons(a).find((b) => text(b) === STRINGS.ed_cancel).click();
  await settle();
  assert.equal(flowMod.S.back, null);
  assert.equal(a.log.anyway.length, 0);
  assert.equal(okLine(a.root), T("ed_undo_stale_h", { file: BKFILE }) + " " + STRINGS.ed_anyway_offer_t, "the rest strip is back");
  assert.equal(FElement.focused, anywayBtn(a.root));
  assert.equal(flowMod.S.want, null);
  // With an older row too, the button that opened the review still takes focus.
  const b = bkApp([rNewest(), rOld("e8")]);
  await b.press(STRINGS.ed_anyway_btn);
  footButtons(b).find((x) => text(x) === STRINGS.ed_cancel).click();
  await settle();
  assert.equal(FElement.focused, anywayBtn(b.root));
  // When the button is gone by then (the row went grey), the link takes focus.
  const c = bkApp([rNewest(), rOld("e8")]);
  await c.press(STRINGS.ed_anyway_btn);
  c.st.history = wrap(bkHist([rNewest({ undo_anyway: false }), rOld("e8")]));
  c.draw();
  footButtons(c).find((x) => text(x) === STRINGS.ed_cancel).click();
  await settle();
  assert.equal(anywayBtn(c.root), undefined);
  assert.equal(FElement.focused, olderLink(c.root));
  assert.equal(flowMod.S.want, null);
  // A review opened from the list still returns to the link.
  const d = bkApp([rNewest(), rOld("e8")]);
  olderLink(d.root).click();
  await settle();
  bkRows(d)[0].click();
  await settle();
  footButtons(d)[1].click();
  await settle();
  footButtons(d)[0].click();
  await settle();
  assert.equal(FElement.focused, olderLink(d.root));
});

test("undo anyway: the press does nothing while a change is chosen or an undo is on its way", async () => {
  const a = bkApp([rNewest(), rOld("e8")]);
  await a.choose(offeredLevel(a.root));
  assert.notEqual(flowMod.S.level, null);
  await flowMod.startBack("undo", rNewest(), "foot");
  flowMod.openOlder();
  assert.equal(flowMod.S.back, null);
  assert.equal(a.log.backup.length, 0);
});

test("older backups: the link shows with a row left, hides with none, and opens the list with focus on the first row", async () => {
  const rows = [rNewest(), rOld("e8"), rOld("e7", { before_absent: true, old_value: undefined }), rOld("e5", { old_value: undefined })];
  const a = bkApp(rows);
  const link = olderLink(a.root);
  assert.equal(link.tagName, "button");
  assert.ok(hasClass(link, "s4-link"));
  assert.equal(text(link), STRINGS.ed_older_link);
  assert.equal(link.getAttribute("type"), "button");
  link.click();
  await settle();
  assert.equal(railHead(a), STRINGS.ed_older_h);
  assert.equal(text(byClass(a.rail(), "s4-sub")[0]), STRINGS.ed_older_intro);
  assert.equal(byClass(a.rail(), "s4-bk")[0].tagName, "ul");
  const list = bkRows(a);
  assert.equal(list.length, 3, "the newest row, Undo anyway's, is left out");
  assert.deepEqual(list.map(text), [
    T("ed_older_row_value_t", { file: BKFILE, when: when(rows[1]), value: "low" }),
    T("ed_older_row_absent_t", { file: BKFILE, when: when(rows[2]) }),
    T("ed_older_row_t", { file: BKFILE, when: when(rows[3]) }),
  ]);
  assert.deepEqual(list.map((n) => n.tagName), ["button", "button", "button"]);
  assert.deepEqual(list.map((n) => n.getAttribute("data-edit-focus")), ["backup:e8", "backup:e7", "backup:e5"]);
  assert.equal(list[0].getAttribute("type"), "button");
  assert.equal(focusKeyOf(), "backup:e8");
  assert.deepEqual(footTexts(a), [STRINGS.ed_older_close]);
  assert.equal(footButtons(a)[0].getAttribute("data-edit-focus"), "btn:older-close");
  assert.equal(stripOf(a.root).childNodes.length, 0);
  assert.equal(a.log.backup.length, 0, "opening the list asks for nothing");
  footButtons(a)[0].click();
  await settle();
  assert.equal(flowMod.S.back, null);
  assert.equal(focusKeyOf(), "older");
  assert.equal(FElement.focused, olderLink(a.root));
  // No row left, so no link.
  assert.equal(olderLink(bkApp([rNewest()]).root), undefined);
  assert.equal(olderLink(bkApp([]).root), undefined);
  const onlyUndoable = bkApp([bkRow({ undoable: true, not_undoable_reason: null, restore_state: null, undo_anyway: false })]);
  assert.equal(olderLink(onlyUndoable.root), undefined, "the row Undo reaches is not an older backup");
});

test("older backups: a row that can't be restored is grey with its reason, one for each state", async () => {
  const states = [
    ["same_as_file", STRINGS.ed_older_same],
    ["backup_unparsed", STRINGS.ed_older_unparsed],
    ["backup_damaged", STRINGS.ed_older_damaged],
    ["backup_pruned", STRINGS.ed_older_pruned],
    ["file_refused", STRINGS.ed_older_file_refused],
  ];
  const rows = [rOld("e8"), ...states.map(([state], i) => rOld("g" + i, { restore_state: state }))];
  const a = bkApp(rows);
  olderLink(a.root).click();
  await settle();
  const offRows = byClass(a.rail(), "is-off");
  assert.equal(offRows.length, 5);
  assert.deepEqual(offRows.map((n) => n.tagName), ["li", "li", "li", "li", "li"]);
  assert.ok(offRows.every((n) => hasClass(n, "s4-bkrow")));
  states.forEach(([state, reason], i) => {
    assert.equal(text(byClass(offRows[i], "s4-note")[0]), reason, state);
    assert.equal(tag(offRows[i], "button").length, 0, "a grey row takes no press");
    assert.equal(text(offRows[i]).startsWith(T("ed_older_row_value_t", { file: BKFILE, when: when(rows[i + 1]), value: "low" })), true);
  });
  assert.equal(tag(a.rail(), "button").length, 1, "one row can be restored");
  assert.equal(anyKey(a.root), false);
  noGaps(a.rail());
  // With every row grey the focus goes to Close.
  const b = bkApp([rOld("g0", { restore_state: "same_as_file" })]);
  olderLink(b.root).click();
  await settle();
  assert.equal(focusKeyOf(), "btn:older-close");
});

test("restore: a row opens its preview, the confirm is the primary button, Cancel returns to the list, Close returns to rest", async () => {
  const a = bkApp([rNewest(), rOld("e8"), rOld("e7")]);
  olderLink(a.root).click();
  await settle();
  bkRows(a)[0].click();
  await settle();
  assert.deepEqual(a.log.backup, [["e8", "restore"]]);
  assert.equal(a.log.restore.length + a.log.anyway.length, 0);
  assert.equal(railHead(a), STRINGS.ed_back_h_restore);
  assert.deepEqual(footTexts(a), [STRINGS.ed_back_go_restore, STRINGS.ed_cancel]);
  assert.ok(hasClass(footButtons(a)[0], "p2-pri"), "a restore that writes is the primary button");
  assert.equal(focusKeyOf(), "btn:cancel");
  footButtons(a)[1].click();
  await settle();
  assert.equal(railHead(a), STRINGS.ed_older_h, "Cancel goes back to the list");
  assert.equal(flowMod.S.back.view, "list");
  assert.equal(focusKeyOf(), "backup:e8", "focus is on the row that opened it");
  footButtons(a)[0].click();
  await settle();
  assert.equal(flowMod.S.back, null);
  assert.equal(focusKeyOf(), "older");
  assert.equal(a.log.restore.length, 0, "nothing was written");
});

test("restore: the confirm sends the preview's hash, and the strip says restored with both paths", async () => {
  const a = bkApp([rNewest(), rOld("e8")], { backend: { backupPreview: async (id, kind) => ok(bkPv({ edit: id, kind, base_file: "HASH-R" })) } });
  olderLink(a.root).click();
  await settle();
  bkRows(a)[0].click();
  await settle();
  footButtons(a)[0].click();
  await settle();
  assert.deepEqual(a.log.restore, [["e8", "HASH-R"]]);
  assert.equal(okLine(a.root), T("ed_back_done_restored_t", { file: BKFILE }));
  assert.equal(flowMod.S.back, null);
});

test("review rail: a replace shows the main line, the diff, what runs, the shared note, the backup path and the git warning", () => {
  const rail = backupMod.backRail(bkBack({ pv: bkPv({ shared: true, git_ignore: "not_ignored" }) }), {});
  assert.equal(rail.tagName, "div");
  assert.ok(hasClass(rail, "s4-rb"));
  assert.equal(text(byClass(rail, "s4-rh")[0]), STRINGS.ed_back_h_undo);
  assert.equal(text(byClass(rail, "s4-sub")[0]), T("ed_back_replace_t", { file: BKFILE }));
  assert.equal(byClass(rail, "p2-df").length, 1);
  assert.equal(byClass(byClass(rail, "p2-df")[0], "ly").length, 1, "the diff caption names the layer");
  assert.equal(text(byClass(rail, "s4-runs")[0]), T("ed_back_runs_t", { level: "low" }));
  assert.deepEqual(noteTexts(rail), [STRINGS.ed_shared]);
  assert.equal(text(byClass(rail, "p2-nt-h")[0]), "▲" + STRINGS.ed_git_warn_h);
  const hint = byClass(rail, "s4-hint")[0];
  assert.equal(text(hint), T("ed_back_source", { path: BKPATH }));
  assert.deepEqual(byClass(hint, "pa").map(text), [BKPATH]);
  // The order: line, diff, runs, notes, the hint last.
  const order2 = [byClass(rail, "s4-sub")[0], byClass(rail, "p2-df")[0], byClass(rail, "s4-runs")[0], hint].map((n) => order(rail, n));
  assert.deepEqual(order2, [...order2].sort((x, y) => x - y));
  const unknown = backupMod.backRail(bkBack({ pv: bkPv({ git_ignore: "unknown" }) }), {});
  assert.deepEqual(noteTexts(unknown), [T("ed_git_unknown", { file: BKFILE })]);
  assert.equal(byClass(unknown, "p2-nt").length, 0);
  assert.deepEqual(noteTexts(backupMod.backRail(bkBack({ pv: bkPv() }), {})), []);
});

test("review rail: a delete, a create, an unparsed file and a no-change preview each say their own thing", () => {
  const del = backupMod.backRail(bkBack({ pv: bkPv({ result: "delete", op: "create", removes_dir: true, diff: null }) }), {});
  assert.equal(text(byClass(del, "s4-sub")[0]), T("ed_back_delete_t", { file: BKFILE }));
  assert.deepEqual(noteTexts(del), [STRINGS.ed_back_delete_dir_t]);
  assert.equal(byClass(del, "p2-df").length, 0);
  const nofolder = backupMod.backRail(bkBack({ pv: bkPv({ result: "delete", removes_dir: false, diff: null }) }), {});
  assert.deepEqual(noteTexts(nofolder), []);
  const empty = backupMod.backRail(bkBack({ pv: bkPv({ diff: { file_display: "project/.claude/settings.json", hunks: [] } }) }), {});
  assert.equal(byClass(empty, "p2-df").length, 0, "a diff with no hunks draws no figure");
  const create = backupMod.backRail(bkBack({ kind: "restore", pv: bkPv({ result: "create", kind: "restore" }) }), {});
  assert.equal(text(byClass(create, "s4-rh")[0]), STRINGS.ed_back_h_restore);
  assert.equal(text(byClass(create, "s4-sub")[0]), T("ed_back_create_t", { file: BKFILE }));
  assert.deepEqual(noteTexts(create), [], "the main line already says the file is created, and no Undo follows a restore");
  const dir = backupMod.backRail(bkBack({ pv: bkPv({ result: "create", creates_dir: true }) }), {});
  assert.deepEqual(noteTexts(dir), [T("ed_back_create_dir_t", { file: BKFILE })]);
  const gone = backupMod.backRail(bkBack({ pv: bkPv({ result: "delete", diff: null, git_ignore: "not_ignored" }) }), {});
  assert.deepEqual(noteTexts(gone), [], "a file that goes takes no git warning");
  const bad2 = backupMod.backRail(bkBack({ pv: bkPv({ file_unparsed: true, diff: null }) }), {});
  assert.deepEqual(noteTexts(bad2), [T("ed_back_unparsed_t", { file: BKFILE })]);
  const same = backupMod.backRail(bkBack({ pv: bkPv({ no_change: true, diff: null }) }), {});
  assert.equal(text(byClass(same, "s4-sub")[0]), T("ed_back_no_change_t", { file: BKFILE }));
  assert.equal(byClass(same, "s4-runs").length, 0, "nothing runs differently, so no runs line");
});

test("review rail: what a new session runs is unknown, the same, or a level", () => {
  const line = (over) => text(byClass(backupMod.backRail(bkBack({ pv: bkPv(over) }), {}), "s4-runs")[0]);
  assert.equal(line({ runs_after: null }), STRINGS.ed_back_runs_unknown_t);
  assert.equal(line({ runs_after: "low", runs_before: "low" }), STRINGS.ed_back_runs_same_t);
  assert.equal(line({ runs_after: "high", runs_before: "low" }), T("ed_back_runs_t", { level: "high" }));
  assert.equal(line({ runs_after: "high", runs_before: null }), T("ed_back_runs_t", { level: "high" }));
});

test("review rail: with no preview yet the rail is the heading alone, and a stale one opens with a warning", () => {
  const wait = backupMod.backRail(bkBack({ pv: null }), {});
  assert.deepEqual(wait.childNodes.map((n) => n.tagName), ["h2"]);
  assert.equal(text(wait), STRINGS.ed_back_h_undo);
  const stale = backupMod.backRail(bkBack({ stale: true }), {});
  const first = stale.childNodes[0];
  assert.ok(hasClass(first, "p2-nt-warn"));
  assert.equal(text(byClass(first, "p2-nt-h")[0]), "▲" + T("ed_back_stale_h", { file: BKFILE }));
  assert.equal(text(first.find((n) => n.tagName === "p")[0]), STRINGS.ed_back_stale_t);
  assert.equal(stale.childNodes[1].tagName, "h2");
  const staleWait = backupMod.backRail(bkBack({ stale: true, pv: null }), {});
  assert.deepEqual(staleWait.childNodes.map((n) => n.tagName), ["div", "h2"]);
});

test("review foot: the label and the primary button for each kind and result, Working while busy, Cancel alone with nothing to do", () => {
  const env = { closeBack() {}, confirmBack() {} };
  const feet = (over) => backupMod.backFoot(bkBack(over), env).filter(Boolean);
  const goOf = (over) => feet(over)[0];
  assert.equal(text(goOf({})), STRINGS.ed_back_go_undo);
  assert.equal(hasClass(goOf({}), "p2-pri"), false);
  assert.equal(text(goOf({ pv: bkPv({ result: "delete" }) })), T("ed_back_go_delete", { file: BKFILE }));
  assert.equal(hasClass(goOf({ pv: bkPv({ result: "delete" }) }), "p2-pri"), false, "a delete is never primary");
  const restore = { kind: "restore", from: "list" };
  assert.equal(text(goOf(restore)), STRINGS.ed_back_go_restore);
  assert.ok(hasClass(goOf(restore), "p2-pri"));
  assert.ok(hasClass(goOf({ ...restore, pv: bkPv({ result: "create" }) }), "p2-pri"));
  assert.equal(text(goOf({ ...restore, pv: bkPv({ result: "delete" }) })), T("ed_back_go_delete", { file: BKFILE }));
  assert.equal(hasClass(goOf({ ...restore, pv: bkPv({ result: "delete" }) }), "p2-pri"), false);
  assert.equal(goOf({}).getAttribute("data-edit-focus"), "btn:save");
  assert.equal(feet({})[1].getAttribute("data-edit-focus"), "btn:cancel");
  assert.ok(feet({}).filter((n) => n.tagName === "button").every((b) => hasClass(b, "s4-wide")));
  const busy = feet({ busy: true });
  assert.equal(text(busy[0]), STRINGS.ed_back_busy);
  assert.equal(off(busy[0]), true);
  assert.equal(off(busy[1]), true);
  assert.equal(busy[0].getAttribute("aria-busy"), "true");
  assert.equal(text(busy[2]), T("ed_back_busy_sr", { file: BKFILE }));
  assert.equal(busy[2].getAttribute("role"), "status");
  assert.ok(hasClass(busy[2], "sr"));
  for (const over of [{ pv: null }, { pv: bkPv({ no_change: true }) }]) {
    const only = feet(over);
    assert.deepEqual(only.filter((n) => n.tagName === "button").map(text), [STRINGS.ed_cancel]);
    assert.equal(only[0].getAttribute("data-edit-focus"), "btn:cancel");
  }
  const list = backupMod.backFoot({ view: "list" }, env).filter(Boolean);
  assert.deepEqual(list.map(text), [STRINGS.ed_older_close]);
  assert.equal(list[0].getAttribute("data-edit-focus"), "btn:older-close");
});

test("restore: the busy button shows Working with both buttons off, and Cancel does nothing while the write is on its way", async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const a = bkApp([rNewest()], { backend: { undoAnyway: async () => { await gate; return ok(bkDone()); } } });
  await a.press(STRINGS.ed_anyway_btn);
  const go = footButtons(a)[0];
  go.click();
  await settle();
  assert.deepEqual(footTexts(a), [STRINGS.ed_back_busy, STRINGS.ed_cancel]);
  assert.deepEqual(footButtons(a).map(off), [true, true]);
  flowMod.closeBack();
  assert.equal(flowMod.S.back.view, "review", "busy returns");
  flowMod.confirmBack();
  assert.equal(a.log.anyway.length, 1, "a second confirm sends nothing");
  release();
  await settle();
  assert.equal(flowMod.S.back, null);
  assert.equal(okLine(a.root), T("ed_back_done_undo_t", { file: BKFILE }));
});

test("stale: a changed file answers with a fresh preview that replaces the old one, with a warning, and the confirm is sent again", async () => {
  const stale = { error: "stale", changed: "file", changed_files: [{ layer: "project", file_display: "project/.claude/settings.json" }], preview: bkPv({ base_file: "HASH2", runs_after: "high" }) };
  let n = 0;
  const a = bkApp([rNewest()], { backend: { undoAnyway: async () => (++n === 1 ? bad("stale", 409, stale) : ok(bkDone())) }, });
  await a.press(STRINGS.ed_anyway_btn);
  footButtons(a)[0].click();
  await settle();
  assert.deepEqual(a.log.anyway, [["e9", "HASH1"]]);
  assert.equal(a.log.refresh, 1, "the page loads the files again");
  assert.equal(flowMod.S.back.stale, true);
  assert.equal(flowMod.S.back.pv.base_file, "HASH2");
  assert.equal(flowMod.S.back.busy, false);
  assert.equal(text(byClass(a.rail(), "p2-nt-h")[0]), "▲" + T("ed_back_stale_h", { file: BKFILE }));
  assert.equal(text(byClass(a.rail(), "s4-runs")[0]), T("ed_back_runs_t", { level: "high" }), "the preview is the new one");
  assert.deepEqual(footTexts(a), [STRINGS.ed_back_go_undo, STRINGS.ed_cancel]);
  assert.equal(footButtons(a).every((b) => !off(b)), true);
  assert.equal(focusKeyOf(), "btn:cancel");
  footButtons(a)[0].click();
  await settle();
  assert.deepEqual(a.log.anyway, [["e9", "HASH1"], ["e9", "HASH2"]]);
  assert.equal(okLine(a.root), T("ed_back_done_undo_t", { file: BKFILE }));
});

test("stale: with no preview the review ends, nothing is written, and the strip says the backup moved", async () => {
  const stale = { error: "stale", changed: "file_removed", changed_files: [], preview: null };
  const a = bkApp([rNewest()], { backend: { undoAnyway: async () => bad("stale", 409, stale) } });
  await a.press(STRINGS.ed_anyway_btn);
  footButtons(a)[0].click();
  await settle();
  assert.equal(flowMod.S.back, null);
  assert.equal(a.log.refresh, 1);
  const alert = byClass(stripOf(a.root), "p2-nt-err")[0];
  assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + STRINGS.ed_back_gone_t);
  assert.equal(flowMod.S.stripBusy, false);
});

test("answers: each written result has its own line, and the paths under it show only when they exist", async () => {
  const run = async (kind, body) => {
    const a = bkApp([rNewest(), rOld("e8")], { backend: { undoAnyway: async () => ok(body), restore: async () => ok(body) } });
    if (kind === "undo") await a.press(STRINGS.ed_anyway_btn);
    else {
      olderLink(a.root).click();
      await settle();
      bkRows(a)[0].click();
      await settle();
    }
    footButtons(a)[0].click();
    await settle();
    return a;
  };
  const cases = [
    ["undo", {}, T("ed_back_done_undo_t", { file: BKFILE })],
    ["restore", {}, T("ed_back_done_restored_t", { file: BKFILE })],
    ["undo", { removed_file: true }, T("ed_back_done_deleted_t", { file: BKFILE })],
    ["restore", { removed_file: true }, T("ed_back_done_deleted_t", { file: BKFILE })],
    ["undo", { removed_file: true, removed_dir: true }, T("ed_back_done_deleted_both_t", { file: BKFILE })],
    ["restore", { replaced_file: false, replaced_display: null }, T("ed_back_done_created_t", { file: BKFILE })],
    ["undo", { replaced_file: false, replaced_display: null }, T("ed_back_done_created_t", { file: BKFILE })],
  ];
  for (const [kind, over, line] of cases) {
    const a = await run(kind, bkDone(over));
    assert.equal(okLine(a.root), line, kind + JSON.stringify(over));
    assert.equal(okMark(a.root), "✓");
    assert.equal(a.log.refresh, 0, "the write reloaded the page already");
    assert.equal(flowMod.S.back, null);
  }
  // A file that was gone has nothing replaced, so only the restored path shows.
  const gone = await run("restore", bkDone({ replaced_file: false, replaced_display: null }));
  assert.equal(pathLine(gone.root), T("ed_undone_path", { path: BKPATH }));
  // A replaced file that has no path, and no restored path, shows no empty line.
  const none = await run("undo", bkDone({ replaced_display: null, restored_from_display: null }));
  assert.equal(pathLine(none.root), null);
  assert.equal(byClass(stripOf(none.root), "s4-hint").length, 0);
  const kept = await run("undo", bkDone({ restored_from_display: null }));
  assert.equal(pathLine(kept.root), T("ed_back_kept", { path: "config/routing-dashboard/backups/x/000002-b.bak" }));
});

test("answers: a refused backup, a refused write and a damaged ledger each leave their own strip", async () => {
  const press = async (kind, out, rows = [rNewest(), rOld("e8")]) => {
    const a = bkApp(rows, { backend: { undoAnyway: async () => out, restore: async () => out } });
    if (kind === "undo") await a.press(STRINGS.ed_anyway_btn);
    else {
      olderLink(a.root).click();
      await settle();
      bkRows(a)[0].click();
      await settle();
    }
    footButtons(a)[0].click();
    await settle();
    return a;
  };
  const head = (a) => text(byClass(byClass(stripOf(a.root), "p2-nt")[0], "p2-nt-h")[0]);
  const unparsed = await press("restore", bad("error", 422, { error: "backup_unparsed" }));
  assert.equal(head(unparsed), "✕" + STRINGS.ed_backup_unparsed_h);
  assert.equal(unparsed.log.refresh, 1, "the history loads again");
  assert.equal(flowMod.S.back, null);
  const none = await press("undo", bad("error", 400, { error: "no_change" }));
  assert.equal(head(none), "✕" + STRINGS.ed_back_no_change_h);
  assert.equal(none.log.refresh, 1);
  const failedRestore = await press("restore", bad("error", 500, { error: "write_failed", file_unchanged: true }));
  assert.equal(head(failedRestore), "✕" + STRINGS.ed_restore_fail_h);
  assert.equal(text(byClass(stripOf(failedRestore.root), "p2-nt")[0].find((n) => n.tagName === "p")[0]), T("ed_restore_fail_t", { file: BKFILE }));
  const failedUndo = await press("undo", bad("error", 500, { error: "write_failed", file_unchanged: true }));
  assert.equal(head(failedUndo), "✕" + STRINGS.ed_undo_fail_h);
  const damaged = await press("undo", bad("error", 409, { error: "backup_damaged", backup_display: BKPATH }));
  assert.equal(head(damaged), "✕" + STRINGS.ed_backup_damaged_h);
  const notUndoable = await press("restore", bad("error", 409, { error: "not_undoable", reason: "backup_pruned" }));
  assert.equal(head(notUndoable), "✕" + STRINGS.ed_older_pruned, "a pruned backup says it is gone");
  assert.equal(notUndoable.log.refresh, 1, "the history loads again, so the row goes grey");
  const otherReason = await press("restore", bad("error", 409, { error: "not_undoable", reason: "not_newest" }));
  assert.equal(head(otherReason), "✕" + STRINGS.ed_not_undoable);
  const ledger = await press("undo", bad("error", 500, { error: "ledger_damaged", ledger_display: "config/routing-dashboard/backups/x/ledger.json" }));
  assert.equal(head(ledger), "✕" + T("ed_ledger_h", { file: BKFILE }));
  const raced = await press("restore", bad("raced", 409, { error: "raced", restored_from_display: BKPATH }));
  assert.equal(head(raced), "▲" + T("ed_raced_h", { file: BKFILE }));
  const unknown = await press("restore", bad("error", 404, { error: "unknown_edit" }));
  assert.equal(unknown.log.refresh, 1);
  const unverified = await press("undo", bad("unverified", 500, { error: "unverified", stage: "reread", backup_display: BKPATH }));
  assert.equal(head(unverified), "✕" + STRINGS.ed_unverified_reread_h);
});

test("answers: the preview itself can be refused, and the review then ends with the reason", async () => {
  const a = bkApp([rNewest(), rOld("e8")], { backend: { backupPreview: async () => bad("error", 422, { error: "backup_unparsed" }) } });
  olderLink(a.root).click();
  await settle();
  bkRows(a)[0].click();
  await settle();
  assert.equal(flowMod.S.back, null);
  assert.equal(text(byClass(byClass(stripOf(a.root), "p2-nt")[0], "p2-nt-h")[0]), "✕" + STRINGS.ed_backup_unparsed_h);
  assert.equal(a.log.refresh, 1);
  const b = bkApp([rNewest()], { backend: { backupPreview: async () => bad("error", 409, { error: "not_undoable", reason: "backup_pruned" }) } });
  await b.press(STRINGS.ed_anyway_btn);
  assert.equal(flowMod.S.back, null);
  assert.equal(text(byClass(byClass(stripOf(b.root), "p2-nt")[0], "p2-nt-h")[0]), "✕" + STRINGS.ed_older_pruned);
  assert.equal(b.log.refresh, 1);
  assert.equal(focusKeyOf(), "btn:dismiss-strip", "focus goes to Dismiss");
});

test("answers: a lost token on the preview or on the write ends the review and shows the token notice", async () => {
  const a = bkApp([rNewest()], { backend: { backupPreview: async () => ({ kind: "locked", res: null }) } });
  await a.press(STRINGS.ed_anyway_btn);
  assert.equal(flowMod.S.back, null);
  assert.deepEqual(flowMod.S.token, { where: "strip" });
  const b = bkApp([rNewest()], { backend: { undoAnyway: async () => ({ kind: "locked", res: null }) } });
  await b.press(STRINGS.ed_anyway_btn);
  footButtons(b)[0].click();
  await settle();
  assert.equal(flowMod.S.back, null);
  assert.equal(b.st.mode, "locked");
});

test("answers: a preview that comes after Cancel is dropped", async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const a = bkApp([rNewest(), rOld("e8")], { backend: { backupPreview: async (id, kind) => { await gate; return ok(bkPv({ edit: id, kind })); } } });
  olderLink(a.root).click();
  await settle();
  bkRows(a)[0].click();
  await settle();
  assert.equal(flowMod.S.back.pv, null);
  assert.deepEqual(footTexts(a), [STRINGS.ed_cancel], "Cancel alone while the preview is on its way");
  assert.deepEqual(byClass(a.rail(), "s4-rh").map(text), [STRINGS.ed_back_h_restore]);
  footButtons(a)[0].click();
  await settle();
  assert.equal(flowMod.S.back.view, "list");
  release();
  await settle();
  assert.equal(flowMod.S.back.view, "list", "the late answer does not reopen the review");
});

test("answers: a write that lands after a project switch clears that project's review and shows the result when it comes back", async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const a = bkApp([rNewest()], { backend: { undoAnyway: async () => { await gate; return ok(bkDone()); } } });
  const home = a.key;
  await a.press(STRINGS.ed_anyway_btn);
  footButtons(a)[0].click();
  await settle();
  a.use("other", baseData());
  assert.equal(flowMod.S.back, null);
  release();
  await settle();
  a.use(home, { settings: BK.settings, targets: BK.targets, history: bkHist([rNewest()]) });
  assert.equal(flowMod.S.back, null);
  assert.equal(okLine(a.root), T("ed_back_done_undo_t", { file: BKFILE }));
});

test("restore row: the last change reads as a restore, with the path and no Undo", () => {
  const row = bkRow({ id: "e11", kind: "restore", undoable: false, not_undoable_reason: "restore_row", restore_state: null, undo_anyway: false, restored_from_display: BKPATH });
  const a = bkApp([row, rOld("e8")]);
  assert.equal(quiet(a.root).startsWith(T("ed_last_restored_t", { when: when(row), file: BKFILE })), true);
  assert.equal(btn(a.root, STRINGS.ed_undo), undefined);
  assert.equal(anywayBtn(a.root), undefined);
  assert.deepEqual(byClass(stripOf(a.root), "pa").map(text), [BKPATH]);
  assert.equal(text(byClass(stripOf(a.root), "s4-note")[0]).endsWith(T("ed_undone_path", { path: BKPATH })), true);
  assert.deepEqual(tag(stripOf(a.root), "button").map(text), [STRINGS.ed_older_link]);
  // The restore row is itself an older backup, one that can be restored.
  assert.deepEqual(backupMod.olderRows({ rows: [row, rOld("e8")] }).map((r) => r.id), ["e11", "e8"]);
  const bare = bkApp([{ ...row, restored_from_display: null }]);
  assert.equal(byClass(stripOf(bare.root), "pa").length, 0);
  noGaps(bare.root);
});

test("one change at a time: the picker is off and the Remove line links are gone while the list or a review is open", async () => {
  const a = app({ data: { settings: RM.start.settings, targets: RM.start.targets, history: bkHist([rOld("e8")]) }, backend: bkBackend() });
  assert.ok(removeLinks(a.root).length > 0, "the links show at rest");
  assert.equal(levelInputs(a.root).every(off), false);
  olderLink(a.root).click();
  await settle();
  assert.equal(removeLinks(a.root).length, 0);
  assert.equal(levelInputs(a.root).every(off), true);
  assert.deepEqual(levelInputs(a.root).filter((r) => r.hasAttribute("checked")).length, 1, "the running level stays checked");
  // The flow's own actions do nothing meanwhile.
  flowMod.pick("high");
  flowMod.pickRow("local");
  assert.equal(flowMod.S.level, null);
  assert.equal(flowMod.S.remove, null);
  await flowMod.doUndo(rOld("e8"));
  assert.equal(a.log.undo.length, 0);
  bkRows(a)[0].click();
  await settle();
  assert.equal(removeLinks(a.root).length, 0);
  assert.equal(levelInputs(a.root).every(off), true);
  footButtons(a)[1].click();
  await settle();
  footButtons(a)[0].click();
  await settle();
  assert.ok(removeLinks(a.root).length > 0, "the links come back with the rest");
  assert.equal(levelInputs(a.root).every(off), false);
  assert.equal(flowMod.S.back, null);
});

test("one change at a time: a chosen level or a chosen line keeps the Older backups link and Undo anyway out of reach", async () => {
  const a = bkApp([rNewest(), rOld("e8")]);
  await a.choose(offeredLevel(a.root));
  assert.equal(olderLink(a.root), undefined, "the link waits with the last change");
  assert.equal(anywayBtn(a.root), undefined);
  flowMod.openOlder();
  assert.equal(flowMod.S.back, null);
  const b = app({ data: { settings: RM.start.settings, targets: RM.start.targets, history: bkHist([rOld("e8")]) }, backend: bkBackend() });
  removeLinks(b.root)[0].click();
  await settle();
  assert.equal(olderLink(b.root), undefined);
  flowMod.openOlder();
  assert.equal(flowMod.S.back, null);
});

test("project lock: the link and the flow still work, because Undo stays open under the lock", async () => {
  const targets = clone(BK.targets);
  targets.project_lock = "not_repo_root";
  const a = bkApp([rNewest(), rOld("e8")], { targets });
  assert.ok(olderLink(a.root), "the link shows under the lock");
  assert.ok(anywayBtn(a.root), "and so does Undo anyway");
  olderLink(a.root).click();
  await settle();
  assert.equal(railHead(a), STRINGS.ed_older_h);
  bkRows(a)[0].click();
  await settle();
  assert.deepEqual(a.log.backup, [["e8", "restore"]]);
  assert.equal(railHead(a), STRINGS.ed_back_h_restore);
  footButtons(a)[1].click();
  await settle();
  footButtons(a)[0].click();
  await settle();
  assert.equal(flowMod.S.back, null);
  assert.equal(railHead(a) === STRINGS.ed_older_h, false);
  assert.ok(olderLink(a.root));
  await a.press(STRINGS.ed_anyway_btn);
  assert.equal(railHead(a), STRINGS.ed_back_h_undo);
  footButtons(a)[0].click();
  await settle();
  assert.equal(a.log.anyway.length, 1);
});

test("edits off or locked: no link and no review", () => {
  for (const mode of ["off", "locked"]) {
    const a = bkApp([rNewest(), rOld("e8")], { mode });
    assert.equal(olderLink(a.root), undefined, mode);
    assert.equal(anywayBtn(a.root), undefined, mode);
  }
});

test("a page render keeps the list and the review, and another cell keeps them too", async () => {
  const a = bkApp([rNewest(), rOld("e8")]);
  olderLink(a.root).click();
  await settle();
  a.draw();
  assert.equal(railHead(a), STRINGS.ed_older_h);
  assert.equal(focusKeyOf(), "backup:e8", "focus survives the render");
  assert.deepEqual(footTexts(a), [STRINGS.ed_older_close]);
  const ctx = a.makeCtx();
  ctx.route.query = { setting: "model" };
  settingsPage.render(a.root, ctx);
  assert.equal(railHead(a), STRINGS.ed_older_h, "another cell keeps the list");
  assert.deepEqual(footTexts(a), [STRINGS.ed_older_close]);
  bkRows(a)[0].click();
  await settle();
  a.draw();
  assert.equal(railHead(a), STRINGS.ed_back_h_restore);
  assert.deepEqual(footTexts(a), [STRINGS.ed_back_go_restore, STRINGS.ed_cancel]);
  assert.equal(text(byClass(a.rail(), "s4-sub")[0]), T("ed_back_replace_t", { file: BKFILE }));
  settingsPage.render(a.root, ctx);
  assert.equal(railHead(a), STRINGS.ed_back_h_restore);
  footButtons(a)[1].click();
  await settle();
  footButtons(a)[0].click();
  await settle();
  assert.equal(flowMod.S.back, null);
});

test("a flow keeps its list per project", async () => {
  const a = bkApp([rNewest(), rOld("e8")]);
  const home = a.key;
  olderLink(a.root).click();
  await settle();
  a.use("other", baseData());
  assert.equal(flowMod.S.back, null);
  assert.equal(olderLink(a.root), undefined);
  a.use(home, { settings: BK.settings, targets: BK.targets, history: bkHist([rNewest(), rOld("e8")]) });
  assert.equal(flowMod.S.back.view, "list");
  assert.equal(railHead(a), STRINGS.ed_older_h);
  footButtons(a)[0].click();
  await settle();
});

test("a review waiting on its preview does not outlive a project switch", async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const a = bkApp([rNewest(), rOld("e8")], { backend: { backupPreview: async (id, kind) => { await gate; return ok(bkPv({ edit: id, kind })); } } });
  const home = a.key;
  olderLink(a.root).click();
  await settle();
  bkRows(a)[0].click();
  await settle();
  a.use("other", baseData());
  release();
  await settle();
  a.use(home, { settings: BK.settings, targets: BK.targets, history: bkHist([rNewest(), rOld("e8")]) });
  assert.equal(flowMod.S.back, null);
  assert.ok(olderLink(a.root));
});

test("text nodes: a hostile value, file and path in the list and the review make no element", async () => {
  const evil = "<img src=x onerror=alert(1)>";
  const a = bkApp([rNewest(), rOld("e8", { old_value: evil })], {
    backend: { backupPreview: async (id, kind) => ok(bkPv({ edit: id, kind, backup_display: evil, diff: { file_display: evil, hunks: [{ lines: [{ kind: "add", old_line: null, new_line: 1, text: evil }] }] } })) },
  });
  olderLink(a.root).click();
  await settle();
  assert.equal(a.root.find((n) => n.tagName === "img").length, 0);
  assert.ok(a.root.textContent.includes(evil));
  bkRows(a)[0].click();
  await settle();
  assert.equal(a.root.find((n) => n.tagName === "img").length, 0);
  assert.ok(a.root.textContent.includes(evil));
  assert.equal(parsed.length, 0);
});

// ---------------------------------------------------------------- Stage 4 fixes

const noteHead = (root) => text(byClass(byClass(stripOf(root), "p2-nt")[0], "p2-nt-h")[0]);
const noteBody = (root) => text(byClass(stripOf(root), "p2-nt")[0].find((n) => n.tagName === "p")[0]);
const BKPATH2 = "config/routing-dashboard/backups/x/000002-b.bak";
// An Undo anyway (or a restore) on a stale row, previewed with over, and confirmed into out.
const confirmed = async (out, { pv = {}, row = {}, kind = "undo" } = {}) => {
  const a = bkApp([rNewest(row), rOld("e8")], { backend: {
    backupPreview: async (id, k) => ok(bkPv({ edit: id, kind: k, ...pv })),
    undoAnyway: async () => out,
    restore: async () => out,
  } });
  if (kind === "undo") await a.press(STRINGS.ed_anyway_btn);
  else {
    olderLink(a.root).click();
    await settle();
    bkRows(a)[0].click();
    await settle();
  }
  footButtons(a)[0].click();
  await settle();
  return a;
};

test("answers: a raced or unverified forced write names the backup it kept, and a file that was absent before has none", async () => {
  // op create on the row does not mean the write had no backup: the file held the owner's bytes when the write came.
  const raced = await confirmed(bad("raced", 409, { error: "raced", backup_display: BKPATH2, restored_from_display: BKPATH }), { row: { op: "create" } });
  assert.equal(noteHead(raced.root), "▲" + T("ed_raced_h", { file: BKFILE }));
  assert.equal(noteBody(raced.root), T("ed_back_raced_t", { backup: BKPATH2 }));
  assert.deepEqual(byClass(stripOf(raced.root), "pa").map(text), [BKPATH2]);
  assert.equal(FElement.focused, btn(raced.root, STRINGS.ed_dismiss));
  const absent = await confirmed(bad("raced", 409, { error: "raced", backup_display: BKPATH2 }), { pv: { result: "create" } });
  assert.equal(noteBody(absent.root), STRINGS.ed_back_raced_new_t, "the file was gone before the write, so there is no backup to name");
  assert.equal(byClass(stripOf(absent.root), "pa").length, 0);
  const reread = await confirmed(bad("unverified", 500, { error: "unverified", stage: "reread", backup_display: BKPATH2 }), { row: { op: "create" } });
  assert.equal(noteHead(reread.root), "✕" + STRINGS.ed_unverified_reread_h);
  assert.equal(noteBody(reread.root), T("ed_back_unverified_t", { backup: BKPATH2 }));
  const fsync = await confirmed(bad("unverified", 500, { error: "unverified", stage: "fsync", backup_display: BKPATH2 }), { kind: "restore" });
  assert.equal(noteHead(fsync.root), "✕" + STRINGS.ed_unverified_fsync_h);
  assert.equal(noteBody(fsync.root), T("ed_unverified_fsync_t", { path: BKPATH2 }));
  const none = await confirmed(bad("unverified", 500, { error: "unverified", stage: "reread", backup_display: BKPATH2 }), { pv: { result: "create" } });
  assert.equal(noteBody(none.root), STRINGS.ed_unverified_new_t);
  const noneFsync = await confirmed(bad("unverified", 500, { error: "unverified", stage: "fsync" }), { pv: { result: "create" } });
  assert.equal(noteBody(noneFsync.root), STRINGS.ed_unverified_fsync_new_t);
  // A 200 whose file does not match the backup is a raced write too, and its answer names the backup in replaced_display.
  const mismatch = await confirmed(ok(bkDone({ matches_backup: false })));
  assert.equal(noteHead(mismatch.root), "▲" + T("ed_raced_h", { file: BKFILE }));
  assert.equal(noteBody(mismatch.root), T("ed_back_raced_t", { backup: BKPATH2 }));
  assert.equal(mismatch.log.refresh, 0);
});

test("answers: a failed Undo anyway or restore that left the .claude folder says so, and one that did not keeps the plain line", async () => {
  const left = await confirmed(bad("error", 500, { error: "write_failed", file_unchanged: true, dir_left: true }));
  assert.equal(noteHead(left.root), "✕" + STRINGS.ed_undo_fail_dir_h);
  assert.equal(noteBody(left.root), T("ed_back_fail_dir_left_t", { file: BKFILE }));
  const leftRestore = await confirmed(bad("error", 500, { error: "write_failed", file_unchanged: true, dir_left: true }), { kind: "restore" });
  assert.equal(noteHead(leftRestore.root), "✕" + STRINGS.ed_restore_fail_dir_h);
  assert.equal(noteBody(leftRestore.root), T("ed_back_fail_dir_left_t", { file: BKFILE }));
  const plain = await confirmed(bad("error", 500, { error: "write_failed", file_unchanged: true }));
  assert.equal(noteHead(plain.root), "✕" + STRINGS.ed_undo_fail_h);
  assert.equal(noteBody(plain.root), T("ed_undo_fail_t", { file: BKFILE }));
});

test("answers: over a file that did not parse, the strip names the backup and does not point at Older backups", async () => {
  const bare = await confirmed(ok(bkDone()), { pv: { file_unparsed: true, diff: null } });
  assert.deepEqual(hintLines(bare.root), [T("ed_back_kept_unparsed_t", { path: BKPATH2 }), T("ed_undone_path", { path: BKPATH })]);
  assert.equal(hintLines(bare.root).some((line) => line.includes("Older backups")), false);
  const parsed = await confirmed(ok(bkDone()));
  assert.equal(hintLines(parsed.root)[0], T("ed_back_kept", { path: BKPATH2 }));
  assert.ok(hintLines(parsed.root)[0].includes("Older backups"), "a file that parsed can be restored from the list");
});

test("answers: a refused preview or write leaves focus on Dismiss, and the strip is drawn from the answer", async () => {
  const preview = bkApp([rNewest()], { backend: { backupPreview: async () => bad("error", 404, { error: "unknown_edit" }) } });
  await preview.press(STRINGS.ed_anyway_btn);
  assert.equal(flowMod.S.back, null);
  assert.equal(FElement.focused, btn(preview.root, STRINGS.ed_dismiss));
  const write = await confirmed(bad("error", 404, { error: "unknown_edit" }));
  assert.equal(FElement.focused, btn(write.root, STRINGS.ed_dismiss));
  const odd = await confirmed(bad("error", 500, { error: "something_new" }));
  assert.equal(FElement.focused, btn(odd.root, STRINGS.ed_dismiss));
});

test("answers: a lost token on a preview that came after Cancel is still told, and the open list stays", async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const a = bkApp([rNewest(), rOld("e8")], { backend: { backupPreview: async () => { await gate; return { kind: "locked", res: null }; } } });
  olderLink(a.root).click();
  await settle();
  bkRows(a)[0].click();
  await settle();
  footButtons(a)[0].click();
  await settle();
  assert.equal(flowMod.S.back.view, "list");
  release();
  await settle();
  assert.deepEqual(flowMod.S.token, { where: "strip" });
  assert.equal(flowMod.S.back.view, "list", "the list is not the review that was waiting");
});

test("answers: a write answer that lands after a project switch still loads the history again when it changes it", async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const stale = { error: "stale", changed: "file_removed", changed_files: [], preview: null };
  const a = bkApp([rNewest()], { backend: { undoAnyway: async () => { await gate; return bad("stale", 409, stale); } } });
  await a.press(STRINGS.ed_anyway_btn);
  footButtons(a)[0].click();
  await settle();
  a.use("other", baseData());
  release();
  await settle();
  assert.equal(a.log.refresh, 1);
});

test("undo anyway: a second press right after the preview draws is dropped with no sign, and a press after the wait writes", async () => {
  flowMod.guard.ms = 500;
  try {
    const a = bkApp([rNewest(), rOld("e8")]);
    await a.press(STRINGS.ed_anyway_btn); // the first click of a double click opens the review
    footButtons(a)[0].click(); // the second lands on the confirm that replaced the button
    await settle();
    assert.deepEqual(a.log.anyway, [], "nothing was written");
    assert.equal(flowMod.S.back.busy, false);
    assert.equal(off(footButtons(a)[0]), false, "the confirm is not shown as busy or off");
    assert.equal(notes(a.root).length, 0, "and nothing was said");
    assert.equal(focusKeyOf(), "btn:cancel");
    await tick(520);
    footButtons(a)[0].click();
    await settle();
    assert.deepEqual(a.log.anyway, [["e9", "HASH1"]]);
    // A restore from the list has the same wait.
    const b = bkApp([rNewest(), rOld("e8")]);
    olderLink(b.root).click();
    await settle();
    bkRows(b)[0].click();
    await settle();
    footButtons(b)[0].click();
    await settle();
    assert.deepEqual(b.log.restore, []);
    await tick(520);
    footButtons(b)[0].click();
    await settle();
    assert.deepEqual(b.log.restore, [["e8", "HASH1"]]);
    // A fresh preview after a stale answer is a preview nobody has read yet, so it waits again.
    const stalePv = { error: "stale", changed: "file", changed_files: [], preview: bkPv({ base_file: "HASH2" }) };
    let n = 0;
    const c = bkApp([rNewest()], { backend: { undoAnyway: async () => (++n === 1 ? bad("stale", 409, stalePv) : ok(bkDone())) } });
    await c.press(STRINGS.ed_anyway_btn);
    await tick(520);
    footButtons(c)[0].click();
    await settle();
    assert.equal(c.log.anyway.length, 1);
    footButtons(c)[0].click();
    await settle();
    assert.equal(c.log.anyway.length, 1, "the press on the fresh preview is dropped");
    await tick(520);
    footButtons(c)[0].click();
    await settle();
    assert.deepEqual(c.log.anyway, [["e9", "HASH1"], ["e9", "HASH2"]]);
  } finally {
    flowMod.guard.ms = 0;
  }
});

test("review: a long diff draws every line, and the rail lays its rows out at their own height", () => {
  const lines = Array.from({ length: 400 }, (_, i) => ({ kind: i % 2 ? "add" : "del", old_line: i % 2 ? null : i + 1, new_line: i % 2 ? i + 1 : null, text: "  \"key" + i + "\": " + i }));
  const rail = backupMod.backRail(bkBack({ pv: bkPv({ diff: { file_display: "project/.claude/settings.json", hunks: [{ lines }] } }) }), {});
  assert.equal(byClass(rail, "p2-df")[0].find((n) => n.tagName === "li").length, 400, "no line is cut");
  assert.ok(hasClass(rail, "s4-rb"));
  // Row heights are CSS. The rail is a grid of rows that would shrink to the pane unless each takes its content's height.
  const css = fs.readFileSync(new URL("app.css", STATIC), "utf8");
  assert.match(css, /\.s4-rb\{[^}]*overflow:auto[^}]*grid-auto-rows:max-content[^}]*\}/);
});

test("review rail: the shared-file line is left off a preview that changes nothing", () => {
  assert.ok(noteTexts(backupMod.backRail(bkBack({ pv: bkPv({ shared: true }) }), {})).includes(STRINGS.ed_shared));
  const same = backupMod.backRail(bkBack({ pv: bkPv({ shared: true, no_change: true, diff: { file_display: "x", hunks: [] } }) }), {});
  assert.equal(noteTexts(same).includes(STRINGS.ed_shared), false);
});

test("review foot: a loaded preview is announced in a status line that says what it does and what runs after", async () => {
  const a = bkApp([rNewest()]);
  await a.press(STRINGS.ed_anyway_btn);
  const say = byClass(slotOf(a.root, "pick"), "sr").filter((n) => n.getAttribute("role") === "status");
  assert.equal(say.length, 1);
  assert.equal(text(say[0]), T("ed_back_replace_t", { file: BKFILE }) + " " + T("ed_back_runs_t", { level: "low" }));
  // Nothing to say while the preview is on its way, and a preview that changes nothing says only that.
  const none = backupMod.backFoot(bkBack({ pv: null }), {}).filter(Boolean);
  assert.equal(none.length, 1);
  const same = backupMod.backFoot(bkBack({ pv: bkPv({ no_change: true }) }), {}).filter(Boolean);
  assert.deepEqual(same.map(text), [STRINGS.ed_cancel, T("ed_back_no_change_t", { file: BKFILE })]);
  // A list with every row grey says what the list is for, because focus is on Close.
  const grey = bkApp([rNewest(), rOld("g0", { restore_state: "same_as_file" })]);
  olderLink(grey.root).click();
  await settle();
  const greySay = byClass(slotOf(grey.root, "pick"), "sr");
  assert.deepEqual(greySay.map(text), [STRINGS.ed_older_intro]);
  const some = bkApp([rNewest(), rOld("e8"), rOld("g0", { restore_state: "same_as_file" })]);
  olderLink(some.root).click();
  await settle();
  assert.equal(byClass(slotOf(some.root, "pick"), "sr").length, 0);
});

test("review: the heading scrolls into view when the list or a review opens, and focus stays put", async () => {
  const calls = [];
  const original = FElement.prototype.scrollIntoView;
  FElement.prototype.scrollIntoView = function scrollIntoView(arg) { calls.push([this, arg]); };
  try {
    const a = bkApp([rNewest(), rOld("e8")]);
    a.page.media.matches = true; // 1240 and under: the rail sits under the body
    await a.press(STRINGS.ed_anyway_btn);
    assert.equal(calls.length, 1, "once, when the preview has drawn");
    assert.ok(hasClass(calls[0][0], "s4-rh"));
    assert.deepEqual(calls[0][1], { block: "start" });
    assert.equal(focusKeyOf(), "btn:cancel");
    footButtons(a).find((b) => text(b) === STRINGS.ed_cancel).click();
    await settle();
    assert.equal(calls.length, 1, "closing scrolls nothing");
    olderLink(a.root).click();
    await settle();
    assert.equal(calls.length, 2);
    assert.equal(text(calls[1][0]), STRINGS.ed_older_h);
    assert.equal(focusKeyOf(), "backup:e8");
  } finally {
    if (original) FElement.prototype.scrollIntoView = original; else delete FElement.prototype.scrollIntoView;
  }
  // With no scrollIntoView on the node the review still draws.
  const b = bkApp([rNewest()]);
  b.page.media.matches = true;
  await b.press(STRINGS.ed_anyway_btn);
  assert.equal(flowMod.S.back.view, "review");
});

test("review: above 1240 nothing scrolls, because the rail keeps its place beside the body", async () => {
  const calls = [];
  const original = FElement.prototype.scrollIntoView;
  FElement.prototype.scrollIntoView = function scrollIntoView(arg) { calls.push([this, arg]); };
  try {
    const a = bkApp([rNewest(), rOld("e8")]);
    assert.equal(a.page.media.matches, false);
    await a.press(STRINGS.ed_anyway_btn);
    assert.equal(flowMod.S.back.view, "review");
    footButtons(a).find((b) => text(b) === STRINGS.ed_cancel).click();
    await settle();
    olderLink(a.root).click();
    await settle();
    assert.equal(flowMod.S.back.view, "list");
    assert.equal(calls.length, 0);
  } finally {
    if (original) FElement.prototype.scrollIntoView = original; else delete FElement.prototype.scrollIntoView;
  }
});

test("review: the rail is a focusable region named by its heading", async () => {
  const a = bkApp([rNewest()]);
  await a.press(STRINGS.ed_anyway_btn);
  const rb = byClass(a.rail(), "s4-rb")[0];
  assert.equal(rb.getAttribute("tabindex"), "0");
  const head = byClass(rb, "s4-rh")[0];
  assert.ok(head.getAttribute("id"), "the heading has an id");
  assert.equal(rb.getAttribute("aria-labelledby"), head.getAttribute("id"));
  // The id is on the one heading, in the rail with a preview and in the one without.
  const bare = backupMod.backRail(bkBack({ pv: null }), {});
  assert.equal(bare.getAttribute("tabindex"), "0");
  assert.equal(bare.getAttribute("aria-labelledby"), byClass(bare, "s4-rh")[0].getAttribute("id"));
});

test("focus: Cancel is focused as soon as the review opens, before the preview comes", async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const a = bkApp([rNewest()], { backend: { backupPreview: async () => { await gate; return ok(bkPv()); } } });
  await a.press(STRINGS.ed_anyway_btn);
  assert.equal(flowMod.S.back.pv, null);
  assert.equal(focusKeyOf(), "btn:cancel");
  release();
  await settle();
  assert.equal(focusKeyOf(), "btn:cancel");
});

test("focus: Dismiss hands focus to the Older backups link, else Undo anyway, else the level radios", async () => {
  const run = async (rows) => {
    const a = bkApp(rows, { backend: { undoAnyway: async () => ok(bkDone()) } });
    await a.press(STRINGS.ed_anyway_btn);
    footButtons(a)[0].click();
    await settle();
    btn(a.root, STRINGS.ed_dismiss).click();
    await settle();
    return a;
  };
  const link = await run([rNewest(), rOld("e8")]);
  assert.equal(focusKeyOf(), "older");
  assert.equal(flowMod.S.want, null);
  const anyway = await run([rNewest()]);
  assert.equal(FElement.focused, anywayBtn(anyway.root));
  // A strip with neither: an Undo that the server refused, over a row that Undo reaches (so no Undo anyway, no link).
  const n = real("not_undoable");
  const radios = app({ data: afterSave(), backend: { undo: async () => bad("error", 409, n.undo_answer) } });
  await radios.press(STRINGS.ed_undo);
  btn(radios.root, STRINGS.ed_dismiss).click();
  await settle();
  assert.ok(focusKeyOf().startsWith("radio:"), "the level radios: " + focusKeyOf());
});

test("focus: a wish for a list row or a link that is not there ends, and takes no later focus", async () => {
  const a = bkApp([rNewest(), rOld("e8")]);
  flowMod.S.want = "backup:nope";
  a.draw();
  assert.equal(flowMod.S.want, null);
  // A wish for Undo anyway when only the link is there lands on the link, once.
  const b = bkApp([rNewest({ undo_anyway: false })]);
  assert.equal(anywayBtn(b.root), undefined);
  flowMod.S.want = "anyway";
  b.draw();
  assert.equal(FElement.focused, olderLink(b.root));
  assert.equal(flowMod.S.want, null);
});

test("settings page: the rail's foot height goes in --s4-foot on the rail, one watcher at a time", async () => {
  const watchers = [];
  globalThis.ResizeObserver = class {
    constructor(fn) { this.fn = fn; this.seen = []; this.off = false; watchers.push(this); }
    observe(node) { this.seen.push(node); }
    disconnect() { this.off = true; }
  };
  Object.defineProperty(FElement.prototype, "offsetHeight", { configurable: true, get() { return 284; } });
  try {
    const a = bkApp([rNewest()]);
    assert.equal(watchers.length, 1);
    const foot = watchers[0].seen[0];
    assert.equal(foot.getAttribute("data-slot"), "foot");
    watchers[0].fn();
    assert.equal(foot.parentNode.styleMap["--s4-foot"], "284px");
    a.draw();
    assert.equal(watchers.length, 2);
    assert.equal(watchers[0].off, true, "the old foot is no longer watched");
    assert.equal(watchers[1].off, false);
  } finally {
    delete globalThis.ResizeObserver;
    delete FElement.prototype.offsetHeight;
  }
});

test("css: the list rows carry only classes app.css defines, with a 44px row at the phone breakpoint", () => {
  const css = fs.readFileSync(new URL("app.css", STATIC), "utf8");
  for (const name of ["s4-bk", "s4-bkrow", "is-off"]) assert.ok(new RegExp("\\." + name + "\\b").test(css), name);
  assert.match(css, /\.s4-bkrow\{min-height:44px;scroll-margin:130px 0 96px\}/);
});

test("css: the docked rail keeps one :has() per selector, and the heading and a notice clear the band", () => {
  const css = fs.readFileSync(new URL("app.css", STATIC), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  assert.match(css, /\.s4-rail:has\(\.s4-rf :not\(\.s4-slot\)\)\{padding-bottom:/);
  assert.match(css, /\.s4-rb \.s4-rh,\.s4-rb \.nt\{scroll-margin-top:110px\}/);
  assert.doesNotMatch(css, /:has\([^{}]*:has\(/, "a :has() nested in a :has() drops the whole rule");
  assert.match(css, /(^|[^\w-])\.s4-hint\{[^}]*text-align:left/);
});

// ---------------------------------------------------------------- run

// MR_ONLY=<text> runs the checks whose name holds the text, for a quick look at one of them.
// ================================================================ the cap, the model and the compact window (round 6, stage 6)

// A world's three answers for one cell, as app.js holds them when the cell is open.
const cellData = (w, which, key = null) => {
  const state = key ? w[key] : w;
  return { settings: state.settings, targets: state.targets, history: state.history };
};
const selectOf = (root) => root.find((n) => n.tagName === "select")[0] || null;
const optionsOf = (root) => selectOf(root).find((n) => n.tagName === "option");
const numberBox = (root) => root.find((n) => n.tagName === "input" && n.getAttribute("id") === "p2-compact")[0] || null;
const typeIn = async (box, value) => { box.value = value; box.dispatch("change"); await settle(); };
const answerFor = (w, layer, value) => ok(w[layer][String(value)]);

test("cap panel: the same card with the cap's title, group label, levels and the max note", () => {
  const w = real("cap_panel");
  const a = app({ setting: "maxEffortLevel", data: cellData(w, "cap", "cap") });
  const group = byClass(a.root, "p2-segs")[0];
  assert.equal(group.getAttribute("aria-label"), STRINGS.ed_level_group_sr_cap);
  assert.deepEqual(levelInputs(a.root).map((r) => r.value), ["low", "medium", "high", "xhigh", "max"]);
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["medium"]);
  assert.equal(byClass(a.root, "p2-sn").map(text).pop(), STRINGS.ed_seg_no_cap, "max sets no cap");
  assert.equal(text(byClass(a.root, "s4-lab")[0]), STRINGS.cap);
  assert.equal(a.log.preview.length, 0, "nothing is previewed until a level is picked");
});

test("cap panel: a pick previews the cap line with setting maxEffortLevel, the review words the cap, and nothing is written", async () => {
  const w = real("cap_panel");
  const user = w.cap_previews.project;
  const a = app({ setting: "maxEffortLevel", data: cellData(w, "cap", "cap"), backend: { preview: async (t, v) => ok(user[v]) } });
  await a.choose("xhigh");
  assert.equal(a.log.preview.length, 0, "the cap line is in the shared file, so the owner picks the row");
  await a.pickRow("project");
  assert.deepEqual(a.log.previewSetting, ["maxEffortLevel"]);
  assert.equal(a.log.preview.length, 1);
  assert.equal(headNote(a.root), STRINGS.ed_runs_cap);
  assert.deepEqual(bigs(a.root), ["medium", "→", "xhigh"]);
  assert.equal(a.log.save.length, 0, "a pick writes nothing");
  assert.equal(pendOf(a.root).length, 1, "Not saved shows");
  assert.equal(text(byClass(cellOf(a.root, "maxEffortLevel"), "s5-pend")[0]), STRINGS.band_not_saved);
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.equal(a.log.save.length, 0, "Cancel writes nothing either");
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["medium"]);
});

test("cap panel: Save sends setting maxEffortLevel and the saved line words the cap", async () => {
  const w = real("cap_panel");
  const user = w.cap_previews.project;
  const layer = "project";
  const target = w.cap.targets.targets.find((t) => t.layer === layer).target;
  const a = app({
    setting: "maxEffortLevel", data: cellData(w, "cap", "cap"),
    backend: { preview: async (t, v) => ok(user[v]), save: async () => ok({ edit: { id: "e1", layer, file_display: "f", backup_display: "b", key_path: ["maxEffortLevel"], old_value: "medium", new_value: "high", op: "replace" }, runs_before: "medium", runs_after: "high", cleaned_up: false }) },
  });
  await a.choose("high");
  await a.pickRow("project");
  const save = saveButtons(a.root)[0];
  assert.ok(save);
  save.click();
  await settle();
  assert.deepEqual(a.log.saveSetting, ["maxEffortLevel"]);
  assert.equal(a.log.save[0].target, target);
  assert.equal(a.log.save[0].value, "high");
});

test("effort via the cap: the level says raise cap, its rows are the cap's file rows, and the review is of the cap line", async () => {
  const w = real("cap_via");
  const row = w.effort.targets.levels.find((l) => l.via === "cap");
  assert.ok(row);
  const a = app({ data: cellData(w, "effort", "effort"), backend: { preview: async (t, v) => ok(w.cap_previews.local[v]) } });
  assert.equal(text(byClass(rowOf(lvl(a.root, "high")), "p2-sn")[0]), STRINGS.ed_seg_raise_cap);
  assert.equal(off(lvl(a.root, "high")), false);
  await a.choose("high");
  assert.deepEqual(a.log.previewSetting, ["maxEffortLevel"], "the preview is of the cap line");
  assert.equal(a.log.preview[0][0], row.preselect, "the cap line's own target");
  assert.equal(a.log.preview[0][1], "high");
  assert.ok(liveRows(a.root).length > 0, "the cap's file rows are live");
  assert.equal(headNote(a.root), STRINGS.ed_runs_cap, "the line is the cap's");
  assert.equal(a.log.save.length, 0);
  // Save goes through the cap setting with the row's target.
  const saved = [];
  const b = app({
    data: cellData(w, "effort", "effort"),
    backend: { preview: async (t, v) => ok(w.cap_previews.local[v]), save: async (pv, t, v) => { saved.push([t, v]); return ok({ edit: { id: "e2", layer: "local", file_display: "f", backup_display: "b", key_path: ["maxEffortLevel"], op: "replace" }, runs_before: "low", runs_after: "high" }); } },
  });
  await b.choose("high");
  saveButtons(b.root)[0].click();
  await settle();
  assert.deepEqual(b.log.saveSetting, ["maxEffortLevel"]);
  assert.deepEqual(saved, [[row.preselect, "high"]]);
});

test("effort with the cap first: the level says 2 changes, the rail offers Start with the cap and no file rows or save", async () => {
  const w = real("cap_first");
  const a = app({ data: cellData(w, "effort", "effort"), backend: { preview: async () => { throw new Error("no preview"); } } });
  assert.deepEqual(byClass(a.root, "p2-sn").map(text), [STRINGS.ed_seg_now, STRINGS.ed_seg_two_changes, STRINGS.ed_seg_two_changes, STRINGS.ed_seg_two_changes]);
  assert.ok(levelInputs(a.root).slice(1).every((r) => !off(r)), "both radios stay enabled");
  await a.choose("high");
  assert.equal(a.log.preview.length, 0, "no preview, because there is nothing to save");
  const warn = nts(a.rail(), "warn")[0];
  assert.equal(text(byClass(warn, "p2-nt-h")[0]), "▲" + T("ed_two_h", { level: "high" }));
  const paras = tag(warn, "p").map(text);
  assert.equal(paras[0], T("ed_two_t", { cap: "low", line: "low", level: "high" }));
  assert.equal(paras[1], STRINGS.ed_two_undo_t);
  assert.deepEqual(tag(warn, "button").map(text).sort(), [STRINGS.ed_cancel, STRINGS.ed_start_cap].sort());
  assert.equal(liveRows(a.root).length, 0, "no file rows");
  assert.equal(saveButtons(a.root).length, 0, "no Save");
  assert.equal(pendOf(a.root).length, 0, "nothing waits on Save");
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["low"]);
});

test("effort with several caps below the level: the stop says more than one cap sits below", async () => {
  const w = real("cap_several");
  const a = app({ data: cellData(w, "effort", "effort") });
  await a.choose("xhigh");
  const warn = nts(a.rail(), "warn")[0];
  assert.equal(tag(warn, "p").map(text)[0], T("ed_two_several_t", { level: "xhigh" }));
  assert.deepEqual(tag(warn, "button").map(text).includes(STRINGS.ed_start_cap), true);
});

test("Start with the cap: drops the effort pick, opens the cap cell with the same level and previews it there", async () => {
  const w = real("cap_first");
  const a = app({ data: cellData(w, "effort", "effort"), backend: { preview: async (t, v) => ok(w.cap_previews.user[v]) } });
  await a.choose("high");
  await a.press(STRINGS.ed_start_cap);
  assert.deepEqual(a.log.opened, ["maxEffortLevel"]);
  assert.equal(flowMod.S.level, null, "the effort pick is gone");
  assert.equal(a.log.preview.length, 0, "nothing is previewed until the cap targets arrive");
  assert.equal(a.log.save.length, 0);
  a.land(w.cap.targets);
  await settle();
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["high"], "the same level is chosen on the cap");
  const row = w.cap.targets.levels.find((l) => l.level === "high");
  if (row.preselect === null) await a.pickRow("user");
  assert.deepEqual(a.log.previewSetting, ["maxEffortLevel"]);
  assert.equal(headNote(a.root), STRINGS.ed_runs_cap);
  assert.equal(a.log.save.length, 0, "nothing was written");
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.equal(a.log.save.length, 0);
});

test("Start with the cap: an owner who leaves the cap cell drops the carried level", async () => {
  const w = real("cap_first");
  const a = app({ data: cellData(w, "effort", "effort"), backend: { preview: async (t, v) => ok(w.cap_previews.user[v]) } });
  await a.choose("high");
  await a.press(STRINGS.ed_start_cap);
  a.setting = "model";
  a.land(w.cap.targets);
  await settle();
  assert.equal(flowMod.S.level, null);
  assert.equal(a.log.preview.length, 0);
});

test("model pop-up: a labelled select, the display names, an alias with the model it means, now and not allowed", () => {
  const w = real("model_blocked");
  const a = app({ setting: "model", data: w });
  const select = selectOf(a.root);
  assert.ok(select, "a native select");
  const label = byClass(a.root, "s4-lab").find((n) => n.getAttribute("for") === select.getAttribute("id"));
  assert.equal(text(label), STRINGS.ed_model_label);
  const options = optionsOf(a.root);
  assert.deepEqual(options.map((o) => o.value), w.targets.levels.map((l) => l.level));
  const opus = options.find((o) => o.value === "opus");
  assert.equal(text(opus), T("ed_model_opt_alias", { alias: "opus", name: "Opus 5.5" }) + " (" + STRINGS.ed_model_opt_blocked + ")");
  assert.ok(off(opus), "a blocked option is disabled");
  const sonnet = options.find((o) => o.value === "sonnet");
  assert.equal(text(sonnet), T("ed_model_opt_alias", { alias: "sonnet", name: "Sonnet 5.5" }) + " (" + STRINGS.ed_model_opt_now + ")");
  assert.ok(sonnet.hasAttribute("selected"));
  const id = options.find((o) => o.value === "claude-sonnet-5-5");
  assert.equal(text(id), "Sonnet 5.5");
  assert.equal(off(id), false);
  assert.equal(levelInputs(a.root).length, 0, "no level radios on the model cell");
});

test("model pop-up: choosing a model previews with setting model, shows the review and writes nothing", async () => {
  const w = real("model_panel");
  const layer = w.previews.project ? "project" : "user";
  const a = app({ setting: "model", data: w, backend: { preview: async (t, v) => ok(w.previews[layer][v]) } });
  const select = selectOf(a.root);
  select.value = "claude-opus-5-5";
  select.dispatch("change");
  await settle();
  assert.deepEqual(a.log.previewSetting, ["model"]);
  assert.equal(a.log.preview[0][1], "claude-opus-5-5");
  assert.equal(headNote(a.root), STRINGS.ed_runs);
  assert.equal(a.log.save.length, 0);
  assert.equal(pendOf(a.root).length, 1);
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.equal(a.log.save.length, 0);
  assert.equal(pendOf(a.root).length, 0);
  assert.ok(optionsOf(a.root).find((o) => o.value === "sonnet").hasAttribute("selected"), "the running model is back");
});

test("model pop-up: choosing the running model does nothing, and a blocked one is refused", async () => {
  const w = real("model_blocked");
  const a = app({ setting: "model", data: w, backend: { preview: async () => { throw new Error("no preview"); } } });
  const select = selectOf(a.root);
  select.value = "sonnet";
  select.dispatch("change");
  await settle();
  assert.equal(a.log.preview.length, 0);
  assert.equal(flowMod.S.level, null);
  select.value = "opus";
  select.dispatch("change");
  await settle();
  assert.equal(a.log.preview.length, 0);
  assert.equal(flowMod.S.level, null);
});

test("model pop-up: a blocked file row says so, and an unclear allowlist adds its note to the review", async () => {
  const w = real("model_unclear");
  const row = w.targets.levels.find((l) => l.allow === "unclear" && l.result !== "now");
  assert.ok(row, "the allowlist is unclear");
  const layer = Object.keys(w.previews)[0];
  const a = app({ setting: "model", data: w, backend: { preview: async (t, v) => ok(w.previews[layer][v] || Object.values(w.previews[layer])[0]) } });
  const select = selectOf(a.root);
  select.value = "claude-sonnet-5-5";
  select.dispatch("change");
  await settle();
  assert.ok(a.rail().textContent.includes(STRINGS.ed_allow_unclear_t));
  // A blocked level's file rows show the lock word.
  const blocked = real("model_blocked");
  const b = app({ setting: "model", data: blocked });
  const opus = blocked.targets.levels.find((l) => l.allow === "blocked");
  assert.ok(opus.files.every((f) => f.lock_reason === "model_blocked"));
  assert.ok(STRINGS.ed_row_lock_model_blocked);
  assert.equal(b.root.textContent.includes(STRINGS.ed_row_lock_model_blocked), false, "rows stay plain until a level is chosen");
});

test("model review: the change line shows display names, and an unknown model keeps its raw id", async () => {
  const w = real("model_panel");
  const layer = w.previews.project ? "project" : "user";
  const a = app({ setting: "model", data: w, backend: { preview: async (t, v) => {
    const pv = clone(w.previews[layer][v]);
    pv.runs_before = "claude-sonnet-5-5";
    pv.runs_after = v === "claude-opus-5-5" ? "claude-opus-5-5" : "claude-unlisted-9";
    pv.after = { ...(pv.after || {}), models: { "claude-sonnet-5-5": "Sonnet 5.5", "claude-opus-5-5": "Opus 5.5" } };
    return ok(pv);
  } } });
  const select = selectOf(a.root);
  select.value = "claude-opus-5-5";
  select.dispatch("change");
  await settle();
  const chg = byClass(a.rail(), "s4-chg")[0];
  assert.equal(text(byClass(chg, "s4-was")[0]), "Sonnet 5.5");
  assert.equal(text(byClass(chg, "s4-to")[0]), "Opus 5.5");
  assert.equal(chg.textContent.includes("claude-"), false);
});

test("compact box: a labelled text box with a hint and Auto, showing what runs", () => {
  const w = real("window_panel");
  const a = app({ setting: "autoCompactWindow", data: w });
  const box = numberBox(a.root);
  assert.ok(box);
  assert.equal(box.getAttribute("inputmode"), "numeric");
  assert.equal(box.value, "200000");
  assert.equal(text(byClass(a.root, "s4-lab").find((n) => n.getAttribute("for") === "p2-compact")), STRINGS.ed_compact_label);
  assert.ok(noteTexts(a.root).includes(STRINGS.ed_compact_hint));
  assert.ok(btn(a.root, STRINGS.ed_compact_auto));
});

test("compact box: commas and spaces are dropped, a good number picks the number row with the typed value", async () => {
  const w = real("window_panel");
  const a = app({ setting: "autoCompactWindow", data: w, backend: { preview: async (t, v) => ok(w.previews.project[String(v)] || w.previews.project["300000"]) } });
  await typeIn(numberBox(a.root), "300,000");
  assert.equal(a.log.preview.length, 1);
  assert.equal(a.log.preview[0][1], 300000);
  assert.deepEqual(a.log.previewSetting, ["autoCompactWindow"]);
  assert.equal(headNote(a.root), STRINGS.ed_runs_compact);
  assert.equal(numberBox(a.root).value, "300000", "the typed value shows, not the probe");
  assert.deepEqual(bigs(a.root), ["200000", "→", "300000"]);
  assert.equal(a.log.save.length, 0);
  await typeIn(numberBox(a.root), "250 000");
  assert.equal(a.log.preview[a.log.preview.length - 1][1], 250000);
});

test("compact box: a word, a decimal, and numbers out of range say what it takes and pick nothing", async () => {
  const w = real("window_panel");
  const a = app({ setting: "autoCompactWindow", data: w, backend: { preview: async () => { throw new Error("no preview"); } } });
  for (const bad of ["lots", "300000.5", "99,999", "1,000,001", "", "1e6", "-300000"]) {
    await typeIn(numberBox(a.root), bad);
    assert.equal(a.log.preview.length, 0, JSON.stringify(bad));
    assert.equal(flowMod.S.level, null, JSON.stringify(bad));
    assert.ok(noteTexts(a.root).includes(STRINGS.ed_compact_bad), JSON.stringify(bad));
    assert.equal(numberBox(a.root).value, bad, "the typed text stays");
  }
  await typeIn(numberBox(a.root), "100000");
  assert.equal(a.log.preview.length, 1, "the floor is a good number");
});

test("compact box: a bad value after a number was chosen stays in the box, flagged, and the pick stays", async () => {
  const w = real("window_panel");
  const a = app({ setting: "autoCompactWindow", data: w, backend: { preview: async (t, v) => ok(w.previews.project[String(v)] || w.previews.project["300000"]) } });
  await typeIn(numberBox(a.root), "250000");
  assert.equal(flowMod.S.number, 250000);
  const count = a.log.preview.length;
  for (const bad of ["99999", "abc"]) {
    await typeIn(numberBox(a.root), bad);
    assert.equal(numberBox(a.root).value, bad, "the typed text stays");
    assert.equal(numberBox(a.root).getAttribute("aria-invalid"), "true", bad);
    assert.ok(noteTexts(a.root).includes(STRINGS.ed_compact_bad), bad);
    assert.equal(flowMod.S.level, "number", bad);
    assert.equal(flowMod.S.number, 250000, bad);
    assert.equal(a.log.preview.length, count, "nothing new is picked");
  }
});

test("compact box: the running value typed while another number is held picks nothing and the box shows the held number", async () => {
  const w = real("window_panel");
  const a = app({ setting: "autoCompactWindow", data: w, backend: { preview: async (t, v) => ok(w.previews.project[String(v)] || w.previews.project["300000"]) } });
  await typeIn(numberBox(a.root), "250000");
  const count = a.log.preview.length;
  await typeIn(numberBox(a.root), "200000");
  assert.equal(a.log.preview.length, count);
  assert.equal(flowMod.S.number, 250000);
  assert.equal(numberBox(a.root).value, "250000");
  assert.equal(noteTexts(a.root).includes(STRINGS.ed_compact_bad), false);
});

test("compact box: a number equal to what runs now does nothing", async () => {
  const w = real("window_panel");
  const a = app({ setting: "autoCompactWindow", data: w, backend: { preview: async () => { throw new Error("no preview"); } } });
  await typeIn(numberBox(a.root), "200,000");
  assert.equal(a.log.preview.length, 0);
  assert.equal(flowMod.S.level, null);
  assert.equal(noteTexts(a.root).includes(STRINGS.ed_compact_bad), false);
});

test("compact box: Auto picks the auto row, and with no model it says Auto needs a model", async () => {
  const w = real("window_panel");
  const a = app({ setting: "autoCompactWindow", data: w, backend: { preview: async (t, v) => ok(w.previews.project[String(v)]) } });
  await a.press(STRINGS.ed_compact_auto);
  assert.equal(a.log.preview.length, 1);
  assert.equal(a.log.preview[0][1], "auto");
  assert.deepEqual(a.log.previewSetting, ["autoCompactWindow"]);
  assert.equal(a.log.save.length, 0);
  assert.ok(bigs(a.root).includes(STRINGS.ed_compact_auto));
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  const none = real("window_nomodel");
  assert.equal(none.targets.model, null);
  const b = app({ setting: "autoCompactWindow", data: none, backend: { preview: async () => { throw new Error("no preview"); } } });
  await b.press(STRINGS.ed_compact_auto);
  assert.equal(b.log.preview.length, 0);
  assert.ok(noteTexts(b.root).includes(STRINGS.ed_compact_auto_nomodel));
  assert.equal(flowMod.S.level, null);
});

test("held change: another editable cell draws read-only while a change is held, and the rail keeps the review", async () => {
  const w = real("cap_via");
  const a = app({ data: cellData(w, "effort", "effort"), backend: { preview: async (t, v) => ok(w.cap_previews.local[v]) } });
  await a.choose("high");
  assert.equal(pendOf(a.root).length, 1);
  // Open the model cell with its own targets.
  const m = real("model_panel");
  a.setting = "model";
  a.land(m.targets);
  await settle();
  const select = selectOf(a.root);
  assert.ok(select && off(select), "the model pop-up is off while a change is held");
  select.value = "claude-opus-5-5";
  select.dispatch("change");
  await settle();
  assert.equal(a.log.preview.length, 1, "no second preview");
  assert.equal(text(byClass(a.rail(), "s4-rh")[0]), STRINGS.review_h, "the review stays");
  assert.deepEqual(footTexts(a).length, 2, "Save and Cancel stay");
  assert.equal(text(byClass(cellOf(a.root, "effortLevel"), "s5-pend")[0]), STRINGS.band_not_saved, "the mark stays on the cell that changed");
  assert.equal(byClass(cellOf(a.root, "model"), "s5-pend").length, 0);
  // The held change saves with its own setting and target even from the other cell.
  saveButtons(a.root)[0].click();
  await settle();
  assert.deepEqual(a.log.saveSetting, ["maxEffortLevel"]);
  assert.equal(a.log.save[0].target, w.effort.targets.levels.find((l) => l.via === "cap").preselect);
});

test("held change: the cap cell's radios and the compact box are off while a change is held on another cell", async () => {
  const w = real("cap_via");
  const a = app({ data: cellData(w, "effort", "effort"), backend: { preview: async (t, v) => ok(w.cap_previews.local[v]) } });
  await a.choose("high");
  const cap = real("cap_panel");
  a.setting = "maxEffortLevel";
  a.land(cap.cap.targets);
  await settle();
  assert.ok(levelInputs(a.root).every(off), "the cap radios are off");
  assert.deepEqual(checkedOf(levelInputs(a.root)), ["medium"], "the level that runs is the one checked");
  const win = real("window_panel");
  a.setting = "autoCompactWindow";
  a.land(win.targets);
  await settle();
  assert.ok(off(numberBox(a.root)));
  assert.ok(off(btn(a.root, STRINGS.ed_compact_auto)));
  assert.equal(a.log.preview.length, 1);
});

test("held change: Cancel on another cell drops the change and the cell draws live again", async () => {
  const w = real("cap_via");
  const a = app({ data: cellData(w, "effort", "effort"), backend: { preview: async (t, v) => ok(w.cap_previews.local[v]) } });
  await a.choose("high");
  const m = real("model_panel");
  a.setting = "model";
  a.land(m.targets);
  await settle();
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.equal(off(selectOf(a.root)), false);
  assert.equal(pendOf(a.root).length, 0);
});

test("read-only frame: Cache lifetime stays the read-only frame and keeps the held change", async () => {
  const w = real("cap_via");
  const a = app({ data: cellData(w, "effort", "effort"), backend: { preview: async (t, v) => ok(w.cap_previews.local[v]) } });
  await a.choose("high");
  a.setting = "promptCacheTtl";
  a.draw();
  assert.equal(levelInputs(a.root).length + rowInputs(a.root).length, 0);
  assert.equal(selectOf(a.root), null);
  assert.equal(text(byClass(a.root, "s4-lock")[0]), STRINGS.ro_lock);
  assert.equal(text(byClass(a.rail(), "s4-rh")[0]), STRINGS.review_h);
});

// A cell with its save and undo answered by the real server: change the value, Save, then Undo.
async function tripOf(name, setting, pick, press) {
  const w = real(name);
  const trip = w.trip;
  const data = name === "cap_panel" ? w.cap : w;
  const previews = (name === "cap_panel" ? w.cap_previews : w.previews).project;
  const afterSave = (state) => ({ settings: state.settings, targets: state.targets, history: state.history });
  // The page preselects the local file, where the world has none yet. The trip is at the project file, so the owner picks that row.
  const targets = clone(data.targets);
  for (const level of targets.levels) level.preselect = null;
  const a = app({
    setting, data: { settings: data.settings, targets, history: data.history },
    backend: {
      preview: async (t, v) => ok(previews[String(v)]),
      save: async () => ({ ...ok(trip.save), after: afterSave(trip.after_save) }),
      undo: async () => ({ ...ok(trip.undo), after: afterSave(trip.after_undo) }),
    },
  });
  await pick(a);
  assert.equal(a.log.save.length, 0, "a pick writes nothing");
  saveButtons(a.root)[0].click();
  await settle();
  assert.deepEqual(a.log.saveSetting, [setting]);
  assert.equal(a.log.save[0].target, trip.target);
  const saved = okLine(a.root);
  return { a, trip, saved };
}

test("words: a saved cap, then its Undo, are worded for the cap and the undo has no new session line", async () => {
  const { a, trip, saved } = await tripOf("cap_panel", "maxEffortLevel", async (x) => { await x.choose("high"); await x.pickRow("project"); });
  assert.ok(a.root.textContent.includes(trip.save.edit.backup_display || "backup"), "the backup path shows");
  assert.deepEqual(strips(a.root).map((n) => tag(n, "button").map(text)), [[STRINGS.ed_undo]]);
  assert.ok(saved.startsWith("Saved. settings.json now sets the effort cap to "), saved);
  assert.equal(saved.includes("new session"), false, "the cap applies at once");
  await a.press(STRINGS.ed_undo);
  assert.equal(a.log.undo.length, 1);
  assert.equal(okLine(a.root).includes("new session"), false, "Undo of a cap carries no new session line");
  assert.equal(okLine(a.root), STRINGS.ed_undone_t_neutral.replace("{file}", "settings.json"));
  assert.deepEqual(strips(a.root).map((n) => tag(n, "button").map(text)), [[STRINGS.ed_dismiss, STRINGS.ed_older_link]], "no Undo is left");
});

test("words: a saved model keeps the effort-style undo, and a saved window words the window", async () => {
  const model = await tripOf("model_panel", "model", async (x) => {
    const select = selectOf(x.root);
    select.value = "claude-opus-5-5";
    select.dispatch("change");
    await settle();
    await x.pickRow("project");
  });
  assert.equal(model.saved, T("ed_saved_t_model", { file: "settings.json", level: "Opus 5.5" }).replace("Opus 5.5", model.saved.match(/sets the model to (.*?)\./)[1]));
  assert.ok(model.saved.endsWith(STRINGS.ed_saved_t_model.split("{level}.")[1].trim()), "the model line keeps the new session sentence");
  await model.a.press(STRINGS.ed_undo);
  assert.equal(okLine(model.a.root), T("ed_undone_t", { file: "settings.json" }));
  const win = await tripOf("window_panel", "autoCompactWindow", async (x) => { await typeIn(numberBox(x.root), "300000"); await x.pickRow("project"); });
  assert.ok(win.saved.startsWith("Saved. settings.json now sets the compact window to "), win.saved);
  await win.a.press(STRINGS.ed_undo);
  assert.equal(okLine(win.a.root).includes("new session"), false);
});

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

test("review rail: a diff with no lines says so, drops the runs line, and keeps the screen-reader text in step", () => {
  const empty = bkPv({ diff: { file_display: "project/.claude/settings.json", hunks: [] } });
  const rail = backupMod.backRail(bkBack({ pv: empty }), {});
  assert.equal(text(byClass(rail, "s4-sub")[0]), T("ed_back_replace_t", { file: BKFILE }));
  assert.equal(text(byClass(rail, "s4-note")[0]), STRINGS.ed_back_no_diff_t);
  assert.equal(byClass(rail, "s4-runs").length, 0, "a restored hidden value can still matter, so no runs line");
  const say = byClass(backupMod.backFoot(bkBack({ pv: empty }), {}), "sr");
  assert.equal(text(say[0]), T("ed_back_replace_t", { file: BKFILE }) + " " + STRINGS.ed_back_no_diff_t);
  // A diff with lines, an unparsed file with no diff, and a no-change preview do not get the line.
  const lines = backupMod.backRail(bkBack({ pv: bkPv() }), {});
  assert.equal(byClass(lines, "s4-note").map(text).includes(STRINGS.ed_back_no_diff_t), false);
  assert.equal(byClass(lines, "s4-runs").length, 1);
  const unparsed = backupMod.backRail(bkBack({ pv: bkPv({ file_unparsed: true, diff: null }) }), {});
  assert.equal(byClass(unparsed, "s4-note").map(text).includes(STRINGS.ed_back_no_diff_t), false);
  const same = backupMod.backRail(bkBack({ pv: bkPv({ no_change: true, diff: { file_display: "x", hunks: [] } }) }), {});
  assert.equal(byClass(same, "s4-note").map(text).includes(STRINGS.ed_back_no_diff_t), false);
});

test("answers: refusals reload the history, and a restore words a damaged backup and a missing folder its own way", async () => {
  const damagedRestore = await confirmed(bad("error", 409, { error: "backup_damaged", backup_display: BKPATH }), { kind: "restore" });
  assert.equal(noteHead(damagedRestore.root), "✕" + STRINGS.ed_restore_backup_damaged_h);
  assert.equal(noteBody(damagedRestore.root), T("ed_backup_damaged_t", { path: BKPATH }));
  assert.equal(damagedRestore.log.refresh, 1, "a dead Undo anyway doesn't come back after Dismiss");
  const damagedUndo = await confirmed(bad("error", 409, { error: "backup_damaged", backup_display: BKPATH }));
  assert.equal(noteHead(damagedUndo.root), "✕" + STRINGS.ed_backup_damaged_h);
  assert.equal(damagedUndo.log.refresh, 1);
  const gone = { error: "config_dir_missing", file_unchanged: true, config_dir_display: "~/gone/.claude" };
  const dirRestore = await confirmed(bad("error", 409, gone), { kind: "restore" });
  assert.equal(noteHead(dirRestore.root), "✕" + STRINGS.ed_restore_fail_h);
  assert.equal(noteBody(dirRestore.root), T("ed_restore_fail_config_dir_t", { config_dir: "~/gone/.claude" }));
  assert.equal(dirRestore.log.refresh, 1);
  const dirUndo = await confirmed(bad("error", 409, gone));
  assert.equal(noteHead(dirUndo.root), "✕" + STRINGS.ed_undo_fail_h);
  assert.equal(noteBody(dirUndo.root), T("ed_undo_fail_config_dir_t", { config_dir: "~/gone/.claude" }));
});

test("stale: the fresh review scrolls its notice into view", async () => {
  const calls = [];
  const original = FElement.prototype.scrollIntoView;
  FElement.prototype.scrollIntoView = function scrollIntoView(arg) { calls.push([this, arg]); };
  try {
    const stale = { error: "stale", changed: "file", changed_files: [], preview: bkPv({ base_file: "HASH2" }) };
    const a = bkApp([rNewest()], { backend: { undoAnyway: async () => bad("stale", 409, stale) } });
    a.page.media.matches = true;
    await a.press(STRINGS.ed_anyway_btn);
    const before = calls.length;
    footButtons(a)[0].click();
    await settle();
    assert.equal(flowMod.S.back.stale, true);
    assert.equal(calls.length, before + 1);
    // The stale notice is drawn above the heading, so it is what scrolls.
    const last = calls[calls.length - 1][0];
    assert.ok(hasClass(last, "nt"));
    assert.equal(last, byClass(a.rail(), "nt")[0]);
  } finally {
    if (original) FElement.prototype.scrollIntoView = original; else delete FElement.prototype.scrollIntoView;
  }
});

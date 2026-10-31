// Browser-free checks of the Change effort card and the undo strip, run by tests/test_edit_card_js.py. They load
// pages/trail.js and js/edit_card.js from dashboard/static/js against the fake DOM in fakedom.mjs, and give the
// trail a ctx shaped like the one app.js builds: ctx.edit holds the mode, the targets, the history and the
// preview, save, undo and reload actions. The answers are real route answers that the Python test writes into
// the folder named by MR_PAYLOADS. Bodies a real run can't reach (unverified, raced, a failed write) are
// written here by hand. Nothing opens a browser or a socket, and every value is made up. A failed check prints
// its name and the reason, and the exit code is 1.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
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
const trail = await import(JS + "pages/trail.js");

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
const radios = (root) => root.find((n) => n.tagName === "input" && n.getAttribute("type") === "radio");
const radio = (root, level) => radios(root).find((r) => r.value === level);
const links = (root) => root.find((n) => n.tagName === "a" && hasClass(n, "lnk") && text(n) === STRINGS.ed_this);
const notes = (root) => byClass(root, "nt").filter((n) => hasClass(n, "p2-nt"));
const strips = (root) => byClass(root, "p2-strip");
const nts = (root, kind) => notes(root).filter((n) => hasClass(n, "p2-nt-" + kind));
const headNote = (root) => text(byClass(byClass(root, "p2-head")[0], "runs")[0]);
const slotOf = (root, name) => root.find((n) => n.getAttribute("data-edit") === name)[0] || null;
const anyKey = (root) => /\bed_[a-z_]+\b/.test(root.textContent);

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

// A page with the edit session faked. data holds the settings, targets and history bodies. backend holds the
// preview, save, undo and reload answers. A save and an undo draw the page again before they resolve, as app.js
// does when it loads the new data, so the card has to live through it.
function app({ mode = "ready", data = {}, backend = {}, route = { agent: "@main", setting: "effortLevel" } } = {}) {
  const page = createPage({ narrow: false });
  const root = page.sections.trail;
  const key = "p" + (++uid);
  const st = { mode, settings: data.settings, targets: wrap(data.targets), history: wrap(data.history) };
  const log = { preview: [], save: [], undo: [], reload: 0, refresh: 0, draws: 0 };
  const a = { page, root, st, log, key };
  const makeCtx = () => ({
    route: { name: "trail", params: { ...route } },
    project: { key, name: "P" },
    data: { settings: { ok: true, status: 200, data: st.settings } },
    hashFor: (name, params) => router.hashFor(name, params, { project: key }),
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
        if (backend.reload) { Object.assign(st, backend.reload(a)); a.draw(); }
      },
      refresh: async () => {
        log.refresh += 1;
        if (backend.refresh) { Object.assign(st, backend.refresh(a)); a.draw(); }
      },
    },
  });
  const after = (out) => {
    if (out.kind === "locked") {
      st.mode = "locked";
      a.draw();
    } else if (out.after) {
      if (out.after.settings) st.settings = out.after.settings;
      if (out.after.targets) st.targets = wrap(out.after.targets);
      if (out.after.history) st.history = wrap(out.after.history);
      a.draw();
    }
    return out;
  };
  a.makeCtx = makeCtx;
  a.draw = () => { log.draws += 1; trail.render(root, makeCtx()); };
  a.panel = () => root.find((n) => n.getAttribute("id") === "trail")[0];
  a.title = () => byClass(root, "tr-title")[0];
  a.choose = async (level) => { radio(root, level).dispatch("change"); await settle(); };
  a.press = async (label) => { const b = btn(root, label); assert.ok(b, "a button named " + label); b.click(); await settle(); };
  a.setMode = (m) => { st.mode = m; };
  a.draw();
  return a;
}

// Scenario helpers.
const S = real("base");
const baseData = (over = {}) => ({ settings: S.start.settings, targets: S.start.targets, history: S.start.history, ...over });
const previewFrom = (scn, ...pathParts) => pathParts.reduce((x, p) => x[p], scn);
const entryLayer = (n) => {
  for (let node = n; node; node = node.parentNode) {
    if (hasClass(node, "en")) return text(byClass(node, "ly")[0] || { textContent: "" });
  }
  return "";
};
const linkFor = (root, layerWord) => links(root).find((l) => entryLayer(l) === layerWord);

// ---------------------------------------------------------------- #87: the card at rest

test("#87 levels: the card shows low, medium, high and xhigh from levels[] on load with no preview call", () => {
  const a = app({ data: baseData() });
  assert.deepEqual(radios(a.root).map((r) => r.value), ["low", "medium", "high", "xhigh"]);
  assert.equal(a.log.preview.length, 0);
  assert.equal(text(byClass(a.root, "cd-h")[0]), STRINGS.ed_card);
  assert.equal(text(byClass(a.root, "p2-lab")[0]), STRINGS.ed_q);
  const group = byClass(a.root, "p2-segs")[0];
  assert.equal(group.getAttribute("role"), "radiogroup");
  assert.equal(group.getAttribute("aria-label"), STRINGS.ed_level_group_sr);
  assert.deepEqual(byClass(a.root, "p2-sn").map(text), [STRINGS.ed_seg_now]);
  assert.deepEqual(byClass(a.root, "p2-hint").map(text), [STRINGS.ed_hint, STRINGS.ed_new_session]);
  assert.equal(radios(a.root).filter((r) => r.hasAttribute("checked")).length, 0);
  assert.equal(anyKey(a.root), false);
});

test("card: it sits between the meta block and the Winner card, and the strip slot between the head and the tiles", () => {
  const a = app({ data: baseData() });
  const meta = a.panel().childNodes.findIndex((n) => hasClass(n, "meta"));
  const card = a.panel().childNodes.findIndex((n) => n.getAttribute("data-edit") === "card");
  const winner = a.panel().childNodes.findIndex((n) => n.tagName === "details");
  assert.ok(meta >= 0 && card === meta + 1 && winner === card + 1, [meta, card, winner].join());
  const top = a.root.childNodes.map((n) => n.getAttribute("class") || n.getAttribute("data-edit") || n.getAttribute("id"));
  assert.deepEqual(top.slice(0, 3), ["ph", "strip", "tiles"]);
});

test("card: the level notes are now, raise cap, can't reach and none", () => {
  const cap = real("nomodel_cap");
  const a = app({ data: { settings: cap.settings, targets: cap.targets, history: cap.history } });
  assert.deepEqual(byClass(a.root, "p2-sn").map(text), [STRINGS.ed_seg_now, STRINGS.ed_seg_cap, STRINGS.ed_seg_cap, STRINGS.ed_seg_cap]);
  const shell = real("shell");
  const b = app({ data: { settings: shell.settings, targets: shell.targets, history: shell.history } });
  assert.deepEqual(byClass(b.root, "p2-sn").map(text), [STRINGS.ed_seg_stopped, STRINGS.ed_seg_stopped, STRINGS.ed_seg_now, STRINGS.ed_seg_stopped]);
  const model = real("model_limit");
  const c = app({ data: { settings: model.settings, targets: model.targets, history: model.history } });
  assert.deepEqual(byClass(c.root, "p2-sn").map(text), [STRINGS.ed_seg_now, STRINGS.ed_seg_stopped]);
});

test("mode: null adds nothing, and a row other than the main effort is drawn as before", () => {
  const plain = app({ mode: null, data: baseData() });
  assert.equal(slotOf(plain.root, "card"), null);
  assert.equal(slotOf(plain.root, "strip"), null);
  assert.equal(byClass(plain.root, "p2-hint").length, 0);
  const model = app({ data: baseData(), route: { agent: "@main", setting: "model" } });
  assert.equal(slotOf(model.root, "card"), null);
  assert.equal(slotOf(model.root, "strip"), null);
  assert.equal(links(model.root).length, 0);
  assert.equal(radios(model.root).length, 0);
  const classes = flat(model.root).map((n) => n.getAttribute && n.getAttribute("class") || "").join(" ");
  assert.equal(/\bp2-/.test(classes), false);
});

test("#87 off: editing off shows one quiet line naming --allow-edits and nothing else", () => {
  const a = app({ mode: "off", data: baseData() });
  const hints = byClass(a.root, "p2-hint");
  assert.equal(hints.length, 1);
  assert.equal(text(hints[0]), STRINGS.ed_off);
  assert.match(text(hints[0]), /--allow-edits/);
  assert.equal(radios(a.root).length + links(a.root).length + buttons(a.root).length, 0);
  assert.equal(strips(a.root).length + byClass(a.root, "p2-lock").length, 0);
});

test("#87 locked: Change links, the picker, lock lines and the strip are gone, and the line says to open the printed link", () => {
  const sh = real("shell");
  const a = app({ mode: "locked", data: { settings: sh.settings, targets: sh.targets, history: real("changed_since_save").history } });
  const hints = byClass(a.root, "p2-hint");
  assert.deepEqual(hints.map(text), [STRINGS.ed_locked]);
  assert.match(STRINGS.ed_locked, /printed in the terminal/);
  assert.equal(radios(a.root).length + links(a.root).length + buttons(a.root).length, 0);
  assert.equal(strips(a.root).length + byClass(a.root, "p2-lock").length, 0);
});

test("mode: ready with targets not loaded draws no card, and a failed answer draws the network line", () => {
  const none = app({ data: { settings: S.start.settings, targets: null, history: S.start.history } });
  assert.equal(radios(none.root).length, 0);
  assert.equal(byClass(none.root, "p2-hint").length, 0);
  assert.equal(byClass(none.root, "cd-h").filter((n) => text(n) === STRINGS.ed_card).length, 0);
  const failed = app({ data: { settings: S.start.settings, targets: { fail: true }, history: S.start.history } });
  assert.equal(radios(failed.root).length, 0);
  assert.deepEqual(byClass(failed.root, "p2-hint").map(text), [STRINGS.ed_err_network]);
});

// ---------------------------------------------------------------- #87: levels_state

test("#87 no_effort_support: the card has no picker and no entry has a Change link or a lock line", () => {
  const h = real("haiku");
  const a = app({ data: { settings: h.settings, targets: h.targets, history: h.history } });
  assert.equal(h.targets.levels_state, "no_effort_support");
  assert.equal(radios(a.root).length, 0);
  assert.equal(links(a.root).length, 0);
  assert.deepEqual(byClass(a.root, "p2-lock").map(text), [STRINGS.ed_levels_no_support]);
  assert.equal(byClass(a.root, "p2-head").length, 0, "runs_as is null, so no head");
  const withRuns = clone(h.targets);
  withRuns.runs_as = "high";
  const b = app({ data: { settings: h.settings, targets: withRuns, history: h.history } });
  assert.deepEqual(byClass(b.root, "p2-head").map(text), ["high"]);
  assert.equal(byClass(b.root, "p2-lock").length, 1);
});

test("#87 model_unknown: the second hint sits under the radios and the group points at it", () => {
  const m = real("nomodel_project");
  const a = app({ data: { settings: m.settings, targets: m.targets, history: m.history } });
  assert.equal(m.targets.levels_state, "model_unknown");
  const hint = byClass(a.root, "p2-hint").find((n) => text(n) === STRINGS.ed_levels_model_unknown);
  assert.ok(hint);
  assert.equal(byClass(a.root, "p2-segs")[0].getAttribute("aria-describedby"), hint.getAttribute("id"));
  const plain = app({ data: baseData() });
  assert.equal(byClass(plain.root, "p2-segs")[0].getAttribute("aria-describedby"), null);
});

test("#87 certain false: the hint and the headline note say the model may still lower the level, and Save is on", async () => {
  const m = real("nomodel_project");
  const a = app({
    data: { settings: m.settings, targets: m.targets, history: m.history },
    backend: { preview: async (target, level) => ok(m.previews.project[level]) },
  });
  await a.choose("medium");
  assert.equal(m.targets.levels.find((l) => l.level === "medium").certain, false);
  assert.ok(byClass(a.root, "p2-hint").some((n) => text(n) === STRINGS.ed_certain_note));
  assert.equal(headNote(a.root), T("ed_runs_uncertain", { level: "medium" }));
  const save = btn(a.root, T("ed_save_to", { file: "settings.json" }));
  assert.ok(save && !save.hasAttribute("disabled"));
});

// ---------------------------------------------------------------- #87: preview

test("#87 reachable: a level opens the preview with the headline, the trail after saving and the diff", async () => {
  const a = app({ data: baseData(), backend: { preview: async (target, level) => ok(S.previews[level]) } });
  await a.choose("high");
  const level = S.start.targets.levels.find((l) => l.level === "high");
  assert.deepEqual(a.log.preview, [[level.target, "high"]]);
  assert.deepEqual(byClass(a.root, "p2-big").map(text), ["low", "→", "high"]);
  assert.equal(text(byClass(a.root, "p2-head")[0].find((n) => hasClass(n, "sr"))[0]), STRINGS.ed_to);
  assert.equal(headNote(a.root), STRINGS.ed_runs);
  // the table
  const table = byClass(a.root, "p2-tbl")[0];
  assert.equal(text(tag(table, "caption")[0]), STRINGS.ed_tbl_cap);
  assert.deepEqual(tag(table, "th").map(text), [STRINGS.ed_th_value, STRINGS.ed_th_now, STRINGS.ed_th_after]);
  const rows = tag(table, "tr").slice(1);
  const before = S.previews.high.before;
  const mainRow = before.rows.find((r) => r.agent === "@main" && r.setting === "effortLevel");
  assert.equal(rows.length, mainRow.entries.length);
  const changed = rows.filter((r) => hasClass(r, "p2-tr-on"));
  assert.equal(changed.length, 1);
  assert.match(text(changed[0]), new RegExp(STRINGS.ed_tag_changes));
  assert.match(text(changed[0]), /Project settings/);
  assert.match(text(changed[0]), /low.*In effect.*high.*In effect/);
  assert.deepEqual(tag(changed[0], "td").map((td) => td.getAttribute("data-l")), [STRINGS.ed_th_value, STRINGS.ed_th_now, STRINGS.ed_th_after]);
  // the diff
  assert.equal(text(byClass(a.root, "p2-sub")[0]), T("ed_file_h", { file: "settings.json", line: 2 }));
  const figure = byClass(a.root, "p2-df")[0];
  assert.equal(text(byClass(figure, "pa")[0]), S.previews.high.diff.file_display);
  const ol = tag(figure, "ol");
  assert.equal(ol.length, S.previews.high.diff.hunks.length);
  assert.equal(ol[0].getAttribute("aria-label"), T("ed_diff_sr", { file: "settings.json" }));
  const lines = tag(ol[0], "li");
  assert.equal(lines.length, S.previews.high.diff.hunks[0].lines.length);
  const del = lines.find((l) => hasClass(l, "p2-del"));
  const add = lines.find((l) => hasClass(l, "p2-add"));
  assert.equal(text(tag(del, "code")[0]), '  "effortLevel": "low"'.trim());
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
  // the card is the active one, and the actions are the plain ones
  assert.ok(hasClass(slotOf(a.root, "card").childNodes[0], "p2-on"));
  const ctl = byClass(a.root, "p2-ctl")[0];
  assert.ok(hasClass(ctl, "p2-stick"));
  assert.deepEqual(tag(ctl, "button").map(text), [T("ed_save_to", { file: "settings.json" }), STRINGS.ed_cancel]);
  assert.ok(hasClass(tag(ctl, "button")[0], "p2-pri"));
  assert.equal(text(byClass(ctl, "p2-hint")[0]), STRINGS.ed_nothing_yet);
  assert.ok(byClass(a.root, "p2-hint").some((n) => text(n) === STRINGS.ed_shared));
  assert.equal(anyKey(a.root), false);
});

test("#87 status: every status in the review shows its mark glyph and its word", async () => {
  const a = app({ data: baseData(), backend: { preview: async (target, level) => ok(S.previews[level]) } });
  await a.choose("xhigh");
  const chips = byClass(byClass(a.root, "p2-tbl")[0], "st");
  assert.ok(chips.length >= 2);
  for (const chip of chips) {
    assert.equal(byClass(chip, "mk").length, 1);
    assert.match(text(chip), /^(In effect|Lowered|Overridden|Ignored|Invalid|Default|Unknown)$/);
  }
  const marks = new Set(["✓", "▲", "✕"]);
  const w = real("overridden");
  const b = app({ data: { settings: w.settings, targets: w.targets, history: w.history }, backend: { preview: async (t, v) => ok(w.previews.project[v]) } });
  links(b.root).find((l) => entryLayer(l) === "Project settings").click();
  await b.choose("high");
  for (const n of byClass(b.root, "p2-nt")) {
    const mk = byClass(n, "p2-mk")[0];
    assert.ok(marks.has(text(mk)));
    assert.equal(mk.getAttribute("aria-hidden"), "true");
    assert.ok(text(byClass(n, "p2-nt-h")[0]).length > 1, "a word beside the mark");
  }
});

test("preview: other agents that move go in a second group headed Also changes", async () => {
  const pv = clone(S.previews.high);
  const line = (value) => ({ value, status: "in_effect", layer: "user", file: "config/settings.json", line: 3, runs_as: value });
  pv.changes.push({ agent: "reviewer", setting: "effort", before: line("xhigh"), after: line("medium") });
  const a = app({ data: baseData(), backend: { preview: async () => ok(pv) } });
  await a.choose("high");
  const bodies = tag(byClass(a.root, "p2-tbl")[0], "tbody");
  assert.equal(bodies.length, 2);
  assert.equal(text(byClass(bodies[1], "p2-tr-h")[0]), STRINGS.ed_also);
  assert.equal(byClass(bodies[1], "p2-tr-h")[0].find((n) => n.tagName === "th")[0].getAttribute("colspan"), "3");
  const row = tag(bodies[1], "tr")[1];
  assert.match(text(row), new RegExp(T("ed_also_agent", { agent: "reviewer" })));
  assert.match(text(row), /xhigh.*In effect.*medium.*In effect/);
});

test("preview: with no runs_as the was half and the arrow are dropped", async () => {
  const m = clone(S.start.targets);
  m.runs_as = null;
  const a = app({ data: baseData({ targets: m }), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await a.choose("high");
  assert.deepEqual(byClass(a.root, "p2-big").map(text), ["high"]);
  assert.equal(byClass(a.root, "p2-arrow").length, 0);
});

test("preview: no_change draws the note and Cancel only", async () => {
  const n = real("no_change");
  const a = app({ data: { settings: n.settings, targets: n.targets, history: n.history }, backend: { preview: async () => ok(n.preview_same) } });
  links(a.root).find((l) => entryLayer(l) === "Project settings").click();
  await a.choose("high");
  assert.equal(n.preview_same.no_change, true);
  const ctl = byClass(a.root, "p2-ctl")[0];
  assert.deepEqual(tag(ctl, "button").map(text), [STRINGS.ed_cancel]);
  assert.equal(text(byClass(ctl, "p2-hint")[0]), STRINGS.ed_no_change_note);
  assert.equal(buttons(a.root).filter((b) => /^Save/.test(text(b))).length, 0);
});

test("preview: picking now returns to rest and runs no preview", async () => {
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await a.choose("high");
  assert.equal(byClass(a.root, "p2-tbl").length, 1);
  await a.choose("low");
  assert.equal(a.log.preview.length, 1);
  assert.equal(byClass(a.root, "p2-tbl").length, 0);
  assert.deepEqual(byClass(a.root, "p2-hint").map(text), [STRINGS.ed_hint, STRINGS.ed_new_session]);
});

test("preview: an older answer that lands after a newer pick is dropped", async () => {
  const waits = {};
  const a = app({
    data: baseData(),
    backend: {
      preview: (target, level) => new Promise((resolve) => { waits[level] = () => resolve(ok(S.previews[level])); }),
    },
  });
  radio(a.root, "medium").dispatch("change");
  radio(a.root, "high").dispatch("change");
  await settle();
  waits.high();
  await settle();
  waits.medium();
  await settle();
  assert.deepEqual(byClass(a.root, "p2-big").map(text), ["low", "→", "high"]);
  assert.equal(a.log.preview.length, 2);
  // cancel also drops an answer on its way
  const b = app({ data: baseData(), backend: { preview: (t2, level) => new Promise((resolve) => { waits.late = () => resolve(ok(S.previews[level])); }) } });
  radio(b.root, "medium").dispatch("change");
  await settle();
  radio(b.root, "low").dispatch("change");
  await settle();
  waits.late();
  await settle();
  assert.equal(byClass(b.root, "p2-tbl").length, 0);
});

// ---------------------------------------------------------------- #87: the warning

test("#87 warning: it shows before the Save action and doesn't block it", async () => {
  const w = real("overridden");
  const a = app({ data: { settings: w.settings, targets: w.targets, history: w.history }, backend: { preview: async (t, v) => ok(w.previews.project[v]), save: async () => bad("error", 500, { error: "write_failed" }) } });
  const link = linkFor(a.root, "Project settings");
  assert.ok(link);
  link.click();
  assert.equal(text(byClass(a.root, "cd-h")[0]), T("ed_card_line", { file: "settings.json", line: 2 }));
  assert.equal(text(byClass(a.root, "p2-lab")[0]), STRINGS.ed_field);
  await a.choose("high");
  assert.deepEqual(a.log.preview, [[w.project_target, "high"]]);
  const warn = byClass(a.root, "p2-nt-warn")[0];
  assert.equal(warn.getAttribute("role"), "status");
  assert.equal(text(byClass(warn, "p2-nt-h")[0]), "▲" + STRINGS.ed_warn_h);
  const paras = tag(warn, "p").map(text);
  assert.equal(paras[0], STRINGS.ed_warn_overridden_t);
  assert.match(paras[1], new RegExp(T("ed_limit_winner", { value: "medium", file: "project/.claude/settings.local.json", line: 2 })));
  const go = btn(a.root, STRINGS.ed_save_anyway);
  assert.ok(go && !go.hasAttribute("disabled"));
  assert.ok(order(a.root, warn) < order(a.root, go), "the warning comes first");
  assert.ok(warn.contains(go));
  assert.deepEqual(tag(warn, "button").map(text), [STRINGS.ed_save_anyway, STRINGS.ed_cancel]);
  assert.equal(buttons(a.root).filter((b) => /^Save to/.test(text(b))).length, 0);
  assert.equal(headNote(a.root), STRINGS.ed_nochange);
  assert.deepEqual(byClass(a.root, "p2-big").map(text), ["medium", "→", "medium"]);
  // A winner limit that is editable carries no lock text, and nothing builds a key from null.
  assert.equal(w.previews.project.high.warning.limits[0].lock_reason, null);
  assert.equal(anyKey(a.root), false);
  go.click();
  await settle();
  assert.equal(a.log.save.length, 1);
  assert.equal(a.log.save[0].target, w.project_target);
  assert.equal(a.log.save[0].value, "high");
  assert.equal(a.log.save[0].pv, w.previews.project.high);
});

test("warning: a cap that lowers the level names the caps and says the effort that runs moves", async () => {
  const w = real("lowered");
  const a = app({ data: { settings: w.settings, targets: w.targets, history: w.history }, backend: { preview: async (t, v) => ok(w.previews[v]) } });
  links(a.root).find((l) => entryLayer(l) === "Project settings").click();
  await a.choose("xhigh");
  const warn = byClass(a.root, "p2-nt-warn")[0];
  assert.equal(text(byClass(warn, "p2-nt-h")[0]), "▲" + STRINGS.ed_warn_part_h);
  const paras = tag(warn, "p").map(text);
  assert.equal(paras[0], STRINGS.ed_warn_cap_t);
  assert.equal(paras.length, 3, "the text and one line for each of the two caps, and no cap_later lock line");
  assert.match(paras[1], /Effort cap of medium in config\/settings\.json, line 3/);
  assert.match(paras[2], /Effort cap of high in project\/\.claude\/settings\.json, line 3/);
  assert.deepEqual(byClass(a.root, "p2-big").map(text), ["low", "→", "medium"]);
  assert.equal(headNote(a.root), STRINGS.ed_runs);
  // A cap that another reason holds is not cap_later, so its lock line replaces the cap text.
  const other = clone(w.previews.xhigh);
  other.warning.limits[0].lock_reason = "managed";
  const b = app({ data: { settings: w.settings, targets: w.targets, history: w.history }, backend: { preview: async () => ok(other) } });
  links(b.root).find((l) => entryLayer(l) === "Project settings").click();
  await b.choose("xhigh");
  const lines = tag(byClass(b.root, "p2-nt-warn")[0], "p").map(text);
  assert.equal(lines.includes(STRINGS.ed_warn_cap_t), false);
  assert.ok(lines.includes(STRINGS.ed_lock_managed));
});

test("warning: no model and a cap below the level says the cap still applies", async () => {
  const c = real("nomodel_cap");
  const a = app({ data: { settings: c.settings, targets: c.targets, history: c.history }, backend: { preview: async (t, v) => ok(c.previews.project[v]) } });
  links(a.root).find((l) => entryLayer(l) === "Project settings").click();
  await a.choose("high");
  assert.equal(c.previews.project.high.warning.status, "in_effect");
  assert.equal(tag(byClass(a.root, "p2-nt-warn")[0], "p").map(text)[0], STRINGS.ed_warn_nomodel_cap_t);
  assert.equal(text(byClass(a.root, "p2-nt-h")[0]), "▲" + STRINGS.ed_warn_h);
});

test("warning: a model limit and each winner status use their own text", async () => {
  const w = real("overridden");
  const wants = { overridden: STRINGS.ed_warn_overridden_t, ignored: STRINGS.ed_warn_ignored_t, invalid: STRINGS.ed_warn_invalid_t, unknown: STRINGS.ed_warn_unknown_t };
  for (const [status, line] of Object.entries(wants)) {
    const pv = clone(w.previews.project.high);
    pv.warning.status = status;
    const a = app({ data: { settings: w.settings, targets: w.targets, history: w.history }, backend: { preview: async () => ok(pv) } });
    linkFor(a.root, "Project settings").click();
    await a.choose("high");
    assert.equal(tag(byClass(a.root, "p2-nt-warn")[0], "p").map(text)[0], line, status);
  }
  const pv = clone(w.previews.project.high);
  pv.warning = { status: "lowered", reason: "r", rule_ids: [], in_effect_changes: true, limits: [{ kind: "model", value: "high", layer: null, file_display: null, line: null, editable: false, target: null, lock_reason: "model" }] };
  const a = app({ data: { settings: w.settings, targets: w.targets, history: w.history }, backend: { preview: async () => ok(pv) } });
  linkFor(a.root, "Project settings").click();
  await a.choose("high");
  assert.deepEqual(tag(byClass(a.root, "p2-nt-warn")[0], "p").map(text), [STRINGS.ed_warn_model_t, STRINGS.ed_lock_model]);
});

test("warning: an unknown status says the dashboard can't tell, in the heading and the saved banner", async () => {
  const w = real("overridden");
  const barOf = async (warning) => {
    const pv = clone(w.previews.project.high);
    if (warning) Object.assign(pv.warning, warning);
    else delete pv.warning;
    const a = app({
      data: { settings: w.settings, targets: w.targets, history: w.history },
      backend: { preview: async () => ok(pv), save: async () => ({ ...ok(S.save), after: S.after_save }) },
    });
    linkFor(a.root, "Project settings").click();
    await a.choose("high");
    const heading = warning ? text(byClass(byClass(a.root, "p2-nt-warn")[0], "p2-nt-h")[0]) : null;
    btn(a.root, warning ? STRINGS.ed_save_anyway : T("ed_save_to", { file: "settings.json" })).click();
    await settle();
    const bar = strips(a.root)[0];
    const line = text(tag(bar, "span").find((n) => !hasClass(n, "p2-mk") && !hasClass(n, "pa")));
    return { heading, line, ok: hasClass(bar, "p2-nt-ok") };
  };
  const slots = { file: "settings.json", level: "high" };
  const backup = " " + T("ed_saved_backup", { path: S.save.edit.backup_display });
  const none = await barOf(null);
  assert.equal(none.line, T("ed_saved_t", slots) + backup);
  const noEffect = await barOf({ status: "overridden", in_effect_changes: false });
  assert.equal(noEffect.heading, "▲" + STRINGS.ed_warn_h);
  assert.equal(noEffect.line, T("ed_saved_no_effect_t", slots) + backup);
  const part = await barOf({ status: "lowered", in_effect_changes: true });
  assert.equal(part.heading, "▲" + STRINGS.ed_warn_part_h);
  assert.equal(part.line, T("ed_saved_part_t", slots) + backup);
  for (const changes of [false, true]) {
    const unknown = await barOf({ status: "unknown", in_effect_changes: changes });
    assert.equal(unknown.heading, "▲" + STRINGS.ed_warn_unknown_h);
    assert.equal(unknown.line, T("ed_saved_unknown_t", slots) + backup);
    assert.ok(unknown.ok);
  }
});

test("warning: an unknown status says the dashboard can't tell what runs, ahead of the no change note", async () => {
  const w = real("overridden");
  for (const changes of [false, true]) {
    const pv = clone(w.previews.project.high);
    Object.assign(pv.warning, { status: "unknown", in_effect_changes: changes });
    const a = app({ data: { settings: w.settings, targets: w.targets, history: w.history }, backend: { preview: async () => ok(pv) } });
    linkFor(a.root, "Project settings").click();
    await a.choose("high");
    assert.equal(headNote(a.root), STRINGS.ed_nochange_unknown, String(changes));
  }
  assert.equal(STRINGS.ed_nochange_unknown, "can't tell what runs");
});

test("write_failed: a missing config folder names the folder under the same heading, on the card and in the strip", async () => {
  const answer = { error: "config_dir_missing", file_unchanged: true, config_dir_display: "~/gone/.claude" };
  const a = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("error", 500, answer) } });
  await a.choose("high");
  btn(a.root, T("ed_save_to", { file: "settings.json" })).click();
  await settle();
  const alert = byClass(a.root, "p2-nt-err")[0];
  assert.equal(alert.getAttribute("role"), "alert");
  assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + STRINGS.ed_fail_h);
  assert.equal(text(tag(alert, "p")[0]), T("ed_fail_config_dir_t", { config_dir: answer.config_dir_display }));
  assert.deepEqual(byClass(alert, "pa").map(text), [answer.config_dir_display]);
  assert.equal(byClass(a.root, "p2-tbl").length, 1, "the review stays");
  assert.ok(btn(a.root, STRINGS.ed_try_again));
  const u = app({
    data: { settings: S.after_save.settings, targets: S.after_save.targets, history: S.after_save.history },
    backend: { ...saveFlow(), undo: async () => bad("error", 500, answer) },
  });
  await u.press(STRINGS.ed_undo);
  const note = byClass(u.root, "p2-nt-err")[0];
  assert.equal(text(byClass(note, "p2-nt-h")[0]), "✕" + STRINGS.ed_fail_h);
  assert.equal(text(tag(note, "p")[0]), T("ed_fail_config_dir_t", { config_dir: answer.config_dir_display }));
  assert.deepEqual(byClass(note, "pa").map(text), [answer.config_dir_display]);
  assert.deepEqual(tag(note, "button").map(text), [STRINGS.ed_dismiss]);
  assert.equal(anyKey(u.root), false);
});

// ---------------------------------------------------------------- #87: the stop panel

test("#87 stopped: a level opens the stop panel that names the cap, with no preview call", async () => {
  const c = real("nomodel_cap");
  const a = app({ data: { settings: c.settings, targets: c.targets, history: c.history }, backend: { preview: async () => { throw new Error("no preview"); } } });
  await a.choose("high");
  assert.equal(a.log.preview.length, 0);
  const panel = byClass(a.root, "p2-nt-warn")[0];
  assert.equal(text(byClass(panel, "p2-nt-h")[0]), "▲" + T("ed_stop_h", { level: "high" }));
  const paras = tag(panel, "p").map(text);
  assert.equal(paras[0], T("ed_stop_cap_t", { level: "high" }));
  assert.match(paras[1], /Effort cap of low in config\/settings\.json, line 2/);
  assert.equal(paras.length, 2);
  assert.deepEqual(tag(panel, "button").map(text), [STRINGS.ed_cancel]);
  assert.equal(byClass(a.root, "p2-tbl").length, 0);
  assert.ok(hasClass(radio(a.root, "high").parentNode, "is-active"));
  // Cancel returns to rest.
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.equal(byClass(a.root, "p2-nt").length, 0);
  assert.equal(radios(a.root).filter((r) => r.hasAttribute("checked")).length, 0);
});

test("#87 two changes: a level that needs the cap changed stops and points to the cap", async () => {
  const c = real("nomodel_cap");
  const a = app({ data: { settings: c.settings, targets: c.targets, history: c.history } });
  await a.choose("xhigh");
  const lines = tag(byClass(a.root, "p2-nt-warn")[0], "p").map(text);
  assert.equal(lines[0], T("ed_stop_cap_t", { level: "xhigh" }));
  assert.match(lines[0], /effort cap/i);
  assert.match(lines[0], /change the cap by hand/i);
});

test("stop panel: a cap another reason holds, a shell winner, the model and an unknown model each use their own text", async () => {
  const run = async (name, level) => {
    const s = real(name);
    const a = app({ data: { settings: s.settings, targets: s.targets, history: s.history } });
    await a.choose(level);
    return tag(byClass(a.root, "p2-nt-warn")[0], "p").map(text);
  };
  const managed = await run("managed_cap", "high");
  assert.equal(managed.includes(T("ed_stop_cap_t", { level: "high" })), false);
  assert.match(managed[0], /Effort cap of medium in managed\/managed-settings\.json, line 2/);
  assert.equal(managed[1], STRINGS.ed_lock_managed);
  const shell = await run("shell", "xhigh");
  assert.equal(shell[0], T("ed_stop_winner_t", { level: "xhigh" }));
  assert.match(shell[1], /^high in Shell$/);
  assert.equal(shell[2], STRINGS.ed_lock_env_shell);
  const model = await run("model_limit", "xhigh");
  assert.equal(model[0], T("ed_stop_model_t", { level: "xhigh", runs_as: "high" }));
  assert.equal(model[1], STRINGS.ed_lock_model);
  const unknown = await run("user_unknown", "high");
  assert.equal(unknown[0], T("ed_stop_unknown_t", { level: "high" }));
  assert.equal(unknown[1], STRINGS.ed_lock_model_unknown);
  assert.equal(unknown.length, 2, "a limit with no file draws no line");
  const sealed = real("user_unknown");
  const b = app({ data: { settings: sealed.settings, targets: sealed.targets, history: sealed.history } });
  await b.choose("high");
  assert.equal(text(byClass(byClass(b.root, "p2-nt-warn")[0], "p2-nt-h")[0]), "▲" + T("ed_stop_unknown_h", { level: "high" }));
});

// ---------------------------------------------------------------- #87: save and undo

const saveFlow = () => ({
  preview: async (t, v) => ok(S.previews[v]),
  save: async () => ({ ...ok(S.save), after: S.after_save }),
  undo: async () => ({ ...ok(S.undo), after: S.after_undo }),
});

test("#87 saved: the strip shows the backup path and Undo, and the card goes back to rest", async () => {
  const gate = {};
  const a = app({
    data: baseData(),
    backend: { ...saveFlow(), save: () => new Promise((resolve) => { gate.go = () => resolve({ ...ok(S.save), after: S.after_save }); }) },
  });
  await a.choose("high");
  btn(a.root, T("ed_save_to", { file: "settings.json" })).click();
  await settle();
  // in flight: the buttons are off and the state survives a draw from new data
  a.draw();
  const busy = btn(a.root, STRINGS.ed_saving);
  assert.ok(busy.hasAttribute("disabled") && busy.getAttribute("aria-busy") === "true");
  assert.ok(btn(a.root, STRINGS.ed_cancel).hasAttribute("disabled"));
  assert.ok(radios(a.root).every((r) => r.hasAttribute("disabled")));
  assert.ok(byClass(a.root, "sr").some((n) => text(n) === T("ed_saving_sr", { file: "settings.json" })));
  assert.equal(byClass(a.root, "p2-tbl").length, 1);
  gate.go();
  await settle();
  const bar = strips(a.root)[0];
  assert.ok(hasClass(bar, "p2-nt-ok"));
  assert.equal(bar.getAttribute("role"), "status");
  assert.equal(text(byClass(bar, "p2-mk")[0]), "✓");
  assert.equal(text(tag(bar, "span").find((n) => !hasClass(n, "p2-mk") && !hasClass(n, "pa"))), T("ed_saved_t", { file: "settings.json", level: "high" }) + " " + T("ed_saved_backup", { path: S.save.edit.backup_display }));
  assert.equal(text(byClass(bar, "pa")[0]), S.save.edit.backup_display);
  assert.deepEqual(tag(bar, "button").map(text), [STRINGS.ed_undo]);
  // the card is at rest, with the new level now
  assert.equal(byClass(a.root, "p2-tbl").length, 0);
  assert.deepEqual(byClass(a.root, "p2-sn").map(text), [STRINGS.ed_seg_now]);
  assert.equal(byClass(a.root, "p2-sn")[0].parentNode.find((n) => hasClass(n, "p2-sv"))[0].textContent, "high");
  assert.equal(a.log.save.length, 1);
  assert.equal(a.log.save[0].value, "high");
  assert.equal(a.log.save[0].target, S.start.targets.levels.find((l) => l.level === "high").target);
  assert.equal(anyKey(a.root), false);
});

test("#87 undo: one undo level shows, and after an undo no Undo shows and the strip names the restored-from path", async () => {
  const a = app({ data: { settings: S.after_save.settings, targets: S.after_save.targets, history: S.after_save.history }, backend: saveFlow() });
  const bar = strips(a.root)[0];
  assert.deepEqual(tag(bar, "button").map(text), [STRINGS.ed_undo]);
  assert.equal(strips(a.root).length, 1);
  assert.equal(S.after_save.history.rows.length, 1);
  await a.press(STRINGS.ed_undo);
  assert.deepEqual(a.log.undo, [S.save.edit.id]);
  const done = strips(a.root)[0];
  assert.ok(hasClass(done, "p2-nt-ok"));
  assert.equal(done.getAttribute("role"), "status");
  assert.deepEqual(tag(done, "button").map(text), [STRINGS.ed_dismiss]);
  assert.equal(buttons(a.root).filter((b) => text(b) === STRINGS.ed_undo).length, 0);
  assert.deepEqual(byClass(done, "pa").map(text), [S.undo.restored_from_display]);
  assert.notEqual(S.undo.restored_from_display, S.undo.edit.backup_display);
  assert.equal(text(done).includes(S.undo.edit.backup_display), false);
  assert.match(text(done), new RegExp(T("ed_undone_t", { file: "settings.json" }).slice(0, 30)));
  assert.equal(FElement.focused, tag(done, "button")[0], "focus goes to Dismiss, because Undo is gone");
  // Dismiss brings back the row of the newest ledger entry, an undo, with one path and no Undo.
  tag(done, "button")[0].click();
  await settle();
  const rest = strips(a.root)[0];
  assert.equal(S.after_undo.history.rows[0].kind, "undo");
  assert.equal(tag(rest, "button").length, 0);
  assert.equal(byClass(rest, "p2-mk").length, 0);
  assert.deepEqual(byClass(rest, "pa").map(text), [S.after_undo.history.rows[0].restored_from_display]);
  assert.equal(anyKey(a.root), false);
});

test("strip: the newest row on load is a quiet line with its time, the values, the backup path and Undo", () => {
  const row = S.after_save.history.rows[0];
  const a = app({ data: { settings: S.after_save.settings, targets: S.after_save.targets, history: S.after_save.history } });
  const bar = strips(a.root)[0];
  assert.equal(bar.getAttribute("role"), null);
  assert.ok(!hasClass(bar, "p2-nt-ok") && !hasClass(bar, "p2-nt-warn"));
  assert.equal(byClass(bar, "p2-mk").length, 0);
  const line = T("ed_last_t", { when: format.fmtTime(row.time), old: "low", new: "high", file: "settings.json" });
  assert.equal(text(byClass(bar, "p2-t")[0]), line + " " + T("ed_saved_backup", { path: row.backup_display }));
  assert.deepEqual(byClass(bar, "pa").map(text), [row.backup_display]);
  assert.deepEqual(tag(bar, "button").map(text), [STRINGS.ed_undo]);
});

test("#87 changed file: the row shows no Undo, names the backup path, and a press answer says the same with Dismiss", async () => {
  const c = real("changed_since_save");
  assert.equal(c.history.rows[0].not_undoable_reason, "changed_since_save");
  const rest = app({ data: { settings: c.settings, targets: c.targets, history: c.history } });
  const bar = strips(rest.root)[0];
  assert.ok(hasClass(bar, "p2-nt-warn"));
  assert.equal(text(byClass(bar, "p2-mk")[0]), "▲");
  assert.equal(tag(bar, "button").length, 0);
  assert.deepEqual(byClass(bar, "pa").map(text), [c.history.rows[0].backup_display]);
  assert.match(text(bar), new RegExp(T("ed_undo_stale_h", { file: "settings.json" })));
  assert.equal(buttons(rest.root).filter((b) => text(b) === STRINGS.ed_undo).length, 0);
  // The page showed Undo (an older history), and the server answered 409.
  const press = app({
    data: { settings: S.after_save.settings, targets: S.after_save.targets, history: S.after_save.history },
    backend: { undo: async () => bad("error", 409, c.undo_answer), refresh: () => ({ settings: c.settings, targets: wrap(c.targets), history: wrap(c.history) }) },
  });
  await press.press(STRINGS.ed_undo);
  assert.equal(press.log.refresh, 1, "the answer loads the page data again");
  const warn = strips(press.root)[0];
  assert.ok(hasClass(warn, "p2-nt-warn"));
  assert.equal(warn.getAttribute("role"), "status");
  assert.deepEqual(byClass(warn, "pa").map(text), [c.undo_answer.backup_display]);
  assert.deepEqual(tag(warn, "button").map(text), [STRINGS.ed_dismiss]);
  tag(warn, "button")[0].click();
  await settle();
  const back = strips(press.root)[0];
  assert.deepEqual(tag(back, "button").map(text), [], "the row's own strip is back, with no dead Undo");
  assert.ok(hasClass(back, "p2-nt-warn"));
  assert.match(text(back), new RegExp(T("ed_undo_stale_h", { file: "settings.json" })));
});

test("#87 backup_damaged: at rest a warning with no buttons, and on a press an alert that replaces the strip", async () => {
  const d = real("backup_damaged");
  const rest = app({ data: { settings: d.settings, targets: d.targets, history: d.history } });
  const bar = strips(rest.root)[0];
  assert.ok(hasClass(bar, "p2-nt-warn"));
  assert.equal(tag(bar, "button").length, 0);
  assert.equal(text(byClass(bar, "p2-t")[0]).slice(1), T("ed_backup_damaged_rest", { path: d.history.rows[0].backup_display }));
  const press = app({ data: { settings: S.after_save.settings, targets: S.after_save.targets, history: S.after_save.history }, backend: { undo: async () => bad("error", 409, d.undo_answer) } });
  await press.press(STRINGS.ed_undo);
  assert.equal(strips(press.root).length, 0, "the alert replaces the strip");
  const slot = slotOf(press.root, "strip");
  const alert = byClass(slot, "p2-nt-err")[0];
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
  const b = app({ data: { settings: S.after_save.settings, targets: S.after_save.targets, history: S.after_save.history }, backend: { undo: async () => bad("error", 409, n.undo_answer) } });
  await b.press(STRINGS.ed_undo);
  const alert = byClass(slotOf(b.root, "strip"), "p2-nt-err")[0];
  assert.equal(alert.getAttribute("role"), "alert");
  assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + STRINGS.ed_not_undoable);
  assert.equal(FElement.focused, tag(alert, "button")[0]);
});

test("#87 unverified: a save shows its own alert with the backup path and Dismiss, with no table, no diff and no retry", async () => {
  for (const stage of ["reread", "fsync"]) {
    const body = { error: "unverified", stage, file_unchanged: false, backup_display: "config/routing-dashboard/backups/x/000001-a.bak" };
    const a = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("unverified", 500, body) } });
    await a.choose("high");
    btn(a.root, T("ed_save_to", { file: "settings.json" })).click();
    await settle();
    const alert = byClass(a.root, "p2-nt-err")[0];
    assert.equal(alert.getAttribute("role"), "alert");
    const h = stage === "fsync" ? STRINGS.ed_unverified_fsync_h : STRINGS.ed_unverified_reread_h;
    assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + h);
    assert.deepEqual(byClass(alert, "pa").map(text), [body.backup_display]);
    assert.equal(byClass(a.root, "p2-tbl").length + byClass(a.root, "p2-df").length, 0);
    const labels = buttons(a.root).map(text);
    assert.equal(labels.includes(STRINGS.ed_try_again) || labels.includes(STRINGS.ed_saving) || labels.some((l) => /^Save/.test(l)), false);
    const dismiss = btn(a.root, STRINGS.ed_dismiss);
    assert.equal(FElement.focused, dismiss);
    assert.equal(radios(a.root).length, 4, "the picker stays");
    dismiss.click();
    await settle();
    assert.equal(byClass(a.root, "p2-nt").length, 0);
    assert.equal(radios(a.root).filter((r) => r.hasAttribute("checked")).length, 0, "back to the fresh picker");
  }
  const body = { error: "unverified", stage: "reread", file_unchanged: false, backup_display: "config/b/000001-z.bak" };
  const u = app({ data: { settings: S.after_save.settings, targets: S.after_save.targets, history: S.after_save.history }, backend: { undo: async () => bad("unverified", 500, body) } });
  await u.press(STRINGS.ed_undo);
  const alert = byClass(slotOf(u.root, "strip"), "p2-nt-err")[0];
  assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + STRINGS.ed_unverified_reread_h);
  assert.deepEqual(byClass(alert, "pa").map(text), [body.backup_display]);
  assert.equal(FElement.focused, tag(alert, "button")[0]);
});

test("#87 raced: a save and an undo each show their own warning, and Dismiss goes back to the picker", async () => {
  const path = "config/routing-dashboard/backups/x/000001-a.bak";
  const a = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("raced", 409, { error: "raced", edit: S.save.edit, backup_display: path, settings: S.save.settings }) } });
  await a.choose("high");
  btn(a.root, T("ed_save_to", { file: "settings.json" })).click();
  await settle();
  const warn = byClass(a.root, "p2-nt-warn")[0];
  assert.equal(warn.getAttribute("role"), "status");
  assert.equal(text(byClass(warn, "p2-nt-h")[0]), "▲" + T("ed_raced_h", { file: "settings.json" }));
  assert.equal(text(tag(warn, "p")[0]), T("ed_raced_t", { path }));
  assert.deepEqual(byClass(warn, "pa").map(text), [path]);
  assert.equal(byClass(a.root, "p2-tbl").length, 0);
  assert.equal(FElement.focused, btn(a.root, STRINGS.ed_dismiss));
  btn(a.root, STRINGS.ed_dismiss).click();
  await settle();
  assert.equal(byClass(a.root, "p2-nt").length, 0);
  const restored = "config/routing-dashboard/backups/x/000002-b.bak";
  const u = app({ data: { settings: S.after_save.settings, targets: S.after_save.targets, history: S.after_save.history }, backend: { undo: async () => bad("raced", 409, { error: "raced", edit: S.undo.edit, backup_display: path, settings: S.undo.settings, matches_backup: false, restored_from_display: restored }) } });
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
  btn(a.root, T("ed_save_to", { file: "settings.json" })).click();
  await settle();
  const alert = byClass(a.root, "p2-nt-err")[0];
  assert.equal(alert.getAttribute("role"), "alert");
  assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + STRINGS.ed_fail_h);
  assert.equal(text(tag(alert, "p")[0]), T("ed_fail_t", { file: "settings.json" }));
  assert.equal(byClass(a.root, "p2-tbl").length, 1);
  const again = btn(a.root, STRINGS.ed_try_again);
  assert.equal(FElement.focused, again);
  assert.ok(btn(a.root, STRINGS.ed_cancel));
  again.click();
  await settle();
  assert.equal(a.log.save.length, 2);
  assert.equal(strips(a.root).length, 1);
});

test("#87 stale: a changed file returns to the new preview with a warning, and a changed trail names the files", async () => {
  const s = real("stale");
  const a = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("stale", 409, s.stale_file) } });
  await a.choose("high");
  btn(a.root, T("ed_save_to", { file: "settings.json" })).click();
  await settle();
  const warn = byClass(a.root, "p2-nt-warn")[0];
  assert.equal(warn.getAttribute("role"), "status");
  assert.equal(text(byClass(warn, "p2-nt-h")[0]), "▲" + T("ed_stale_file_h", { file: "settings.json" }));
  assert.equal(text(tag(warn, "p")[0]), STRINGS.ed_stale_file_t);
  assert.equal(tag(warn, "button").length, 0);
  assert.ok(order(a.root, warn) < order(a.root, byClass(a.root, "p2-tbl")[0]), "the notice sits over the new preview");
  assert.equal(byClass(a.root, "p2-df").length, 1);
  assert.ok(btn(a.root, T("ed_save_to", { file: "settings.json" })), "the new preview's own actions");
  assert.ok(radio(a.root, "high").hasAttribute("checked"));
  const t2 = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("stale", 409, s.stale_trail) } });
  await t2.choose("high");
  btn(t2.root, T("ed_save_to", { file: "settings.json" })).click();
  await settle();
  const trailNote = byClass(t2.root, "p2-nt-warn")[0];
  assert.equal(text(byClass(trailNote, "p2-nt-h")[0]), "▲" + STRINGS.ed_stale_trail_h);
  assert.equal(text(tag(trailNote, "p")[0]), T("ed_stale_trail_t", { files: "settings.json" }));
  const general = clone(s.stale_trail);
  general.changed_files = [];
  const g = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("stale", 409, general) } });
  await g.choose("high");
  btn(g.root, T("ed_save_to", { file: "settings.json" })).click();
  await settle();
  assert.equal(text(tag(byClass(g.root, "p2-nt-warn")[0], "p")[0]), STRINGS.ed_stale_trail_general_t);
  // A null preview: the line is gone, so the notice sits over the picker.
  const gone = clone(s.stale_file);
  gone.preview = null;
  const n = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("stale", 409, gone) } });
  await n.choose("high");
  btn(n.root, T("ed_save_to", { file: "settings.json" })).click();
  await settle();
  const note = byClass(n.root, "p2-nt-warn")[0];
  assert.equal(text(byClass(note, "p2-nt-h")[0]), "▲" + T("ed_stale_file_h", { file: "settings.json" }));
  assert.equal(text(tag(note, "p")[0]), STRINGS.ed_stale_gone_t);
  assert.equal(byClass(n.root, "p2-tbl").length, 0);
  assert.equal(radios(n.root).length, 4);
  assert.equal(anyKey(n.root), false);
});

test("#87 token: a locked outcome from a press draws the alert where the press was, then the Locked line", async () => {
  const card = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("locked", 403, { error: "bad_token" }) } });
  await card.choose("high");
  btn(card.root, T("ed_save_to", { file: "settings.json" })).click();
  await settle();
  const alert = byClass(slotOf(card.root, "card"), "p2-nt-err")[0];
  assert.equal(alert.getAttribute("role"), "alert");
  assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + STRINGS.ed_token_h);
  assert.equal(text(tag(alert, "p")[0]), STRINGS.ed_token_t);
  assert.deepEqual(byClass(slotOf(card.root, "card"), "p2-hint").map(text), [STRINGS.ed_locked]);
  assert.equal(radios(card.root).length + buttons(card.root).length + links(card.root).length, 0);
  const undo = app({ data: { settings: S.after_save.settings, targets: S.after_save.targets, history: S.after_save.history }, backend: { undo: async () => bad("locked", 403, { error: "bad_token" }) } });
  await undo.press(STRINGS.ed_undo);
  const where = byClass(slotOf(undo.root, "strip"), "p2-nt-err")[0];
  assert.equal(text(byClass(where, "p2-nt-h")[0]), "✕" + STRINGS.ed_token_h);
  assert.deepEqual(byClass(slotOf(undo.root, "card"), "p2-hint").map(text), [STRINGS.ed_locked]);
  assert.equal(radios(undo.root).length + buttons(undo.root).length, 0);
});

test("locked: the flow resets, and the picker is fresh when the mode is ready again", async () => {
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await a.choose("high");
  assert.equal(byClass(a.root, "p2-tbl").length, 1);
  a.setMode("locked");
  a.draw();
  assert.equal(byClass(a.root, "p2-tbl").length + radios(a.root).length, 0);
  a.setMode("ready");
  a.draw();
  assert.equal(byClass(a.root, "p2-tbl").length, 0);
  assert.equal(radios(a.root).filter((r) => r.hasAttribute("checked")).length, 0);
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
    const alert = byClass(a.root, "p2-nt-err")[0];
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
  btn(s.root, T("ed_save_to", { file: "settings.json" })).click();
  await settle();
  assert.equal(text(byClass(byClass(s.root, "p2-nt-err")[0], "p2-nt-h")[0]), "✕" + STRINGS.ed_err_bad_value);
  assert.equal(byClass(s.root, "p2-tbl").length, 1);
});

// ---------------------------------------------------------------- #87: the damaged ledger

test("#87 ledger: at rest a warning names each damaged record, above the row's own strip", () => {
  const l = real("ledger");
  assert.equal(l.history.damaged_ledgers.length, 1);
  const only = app({ data: { settings: l.settings, targets: l.targets, history: l.history } });
  const bars = strips(only.root);
  assert.equal(bars.length, 1);
  assert.ok(hasClass(bars[0], "p2-nt-warn"));
  assert.equal(bars[0].getAttribute("role"), null);
  assert.equal(tag(bars[0], "button").length, 0);
  assert.deepEqual(byClass(bars[0], "pa").map(text), [l.history.damaged_ledgers[0].ledger_display]);
  assert.equal(text(byClass(bars[0], "p2-t")[0]).slice(1), T("ed_ledger_rest_t", { file: "settings.local.json", path: l.history.damaged_ledgers[0].ledger_display }));
  const both = clone(l.history);
  both.damaged_ledgers.push({ layer: "user", file_display: "config/settings.json", ledger_display: "config/routing-dashboard/backups/zz/ledger.json" });
  both.rows = S.after_save.history.rows;
  const two = app({ data: { settings: l.settings, targets: l.targets, history: both } });
  const list = strips(two.root);
  assert.equal(list.length, 3);
  assert.ok(hasClass(list[0], "p2-nt-warn") && hasClass(list[1], "p2-nt-warn"));
  assert.deepEqual(tag(list[2], "button").map(text), [STRINGS.ed_undo]);
  const off = app({ mode: "off", data: { settings: l.settings, targets: l.targets, history: l.history } });
  assert.equal(strips(off.root).length, 0);
});

test("#87 ledger: a preview of the damaged file draws no Save while another file's preview does", async () => {
  const l = real("ledger");
  const a = app({
    data: { settings: l.settings, targets: l.targets, history: l.history },
    backend: { preview: async (target, level) => ok(target === l.local_target ? l.previews.local[level] : l.previews.project[level]) },
  });
  // The local file's record is damaged.
  const winnerLink = links(a.root).find((x) => entryLayer(x) === "Local settings");
  winnerLink.click();
  await a.choose("high");
  assert.equal(buttons(a.root).filter((b) => /^Save/.test(text(b))).length, 0);
  assert.equal(byClass(a.root, "p2-tbl").length, 1, "the full preview stays");
  assert.equal(byClass(a.root, "p2-df").length, 1);
  const notice = nts(a.root, "warn")[0];
  assert.equal(text(byClass(notice, "p2-nt-h")[0]), "▲" + T("ed_ledger_preview_t", { file: "settings.local.json" }));
  assert.deepEqual(tag(notice, "button").map(text), [STRINGS.ed_cancel]);
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  // The project file's record is sound, so its preview keeps a Save.
  linkFor(a.root, "Project settings").click();
  await a.choose("high");
  assert.ok(btn(a.root, STRINGS.ed_save_anyway), "a Save action for the other file");
  assert.equal(a.log.save.length, 0);
});

test("#87 ledger: a save answered 500 ledger_damaged shows the alert with the record's path, and Dismiss loads the data again", async () => {
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
  btn(a.root, T("ed_save_to", { file: "settings.json" })).click();
  await settle();
  const alert = byClass(a.root, "p2-nt-err")[0];
  assert.equal(alert.getAttribute("role"), "alert");
  assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + T("ed_ledger_h", { file: "settings.json" }));
  assert.deepEqual(byClass(alert, "pa").map(text), [l.save_answer.ledger_display]);
  assert.equal(buttons(a.root).filter((b) => /^Save|Try/.test(text(b))).length, 0);
  assert.equal(FElement.focused, btn(a.root, STRINGS.ed_dismiss));
  assert.equal(a.log.reload, 0);
  btn(a.root, STRINGS.ed_dismiss).click();
  await settle();
  assert.equal(a.log.reload, 1);
  assert.equal(draws, 1);
  const u = app({ data: { settings: S.after_save.settings, targets: S.after_save.targets, history: S.after_save.history }, backend: { undo: async () => bad("error", 500, l.save_answer) } });
  await u.press(STRINGS.ed_undo);
  const where = byClass(slotOf(u.root, "strip"), "p2-nt-err")[0];
  assert.equal(text(byClass(where, "p2-nt-h")[0]), "✕" + T("ed_ledger_h", { file: "settings.json" }));
  btn(u.root, STRINGS.ed_dismiss).click();
  await settle();
  assert.equal(u.log.reload, 1);
});

test("flow: the state is kept for a project and reset when the project changes", async () => {
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await a.choose("high");
  assert.equal(byClass(a.root, "p2-tbl").length, 1);
  a.draw(); // the same project, drawn again from new data
  assert.equal(byClass(a.root, "p2-tbl").length, 1, "the review survives a draw");
  const other = a.makeCtx();
  other.project = { key: a.key + "-other", name: "Other" };
  trail.render(a.root, other);
  assert.equal(byClass(a.root, "p2-tbl").length, 0, "another project starts at rest");
  assert.equal(radios(a.root).filter((r) => r.hasAttribute("checked")).length, 0);
});

// ---------------------------------------------------------------- Change links and lock lines

test("links: a Change this value link matches an entry to its target, opens the card on that target and keeps the keyboard", async () => {
  const w = real("overridden");
  const a = app({ data: { settings: w.settings, targets: w.targets, history: w.history }, backend: { preview: async (t, v) => ok(w.previews.project[v]) } });
  const list = links(a.root);
  assert.equal(list.length, 2, "the winner and the other value are targets");
  const link = linkFor(a.root, "Project settings");
  assert.equal(link.getAttribute("href"), "#/settings/@main/effortLevel?project=" + a.key);
  assert.ok(hasClass(link.parentNode, "p2-act"));
  let prevented = 0;
  link.dispatch("click", { preventDefault() { prevented += 1; } });
  assert.equal(prevented, 1);
  assert.equal(text(byClass(a.root, "cd-h")[0]), T("ed_card_line", { file: "settings.json", line: 2 }));
  assert.equal(text(byClass(a.root, "p2-lab")[0]), STRINGS.ed_field);
  // now marks the value this line holds
  const now = radios(a.root).find((r) => byClass(r.parentNode, "p2-sn").length);
  assert.equal(now.value, "low");
  assert.equal(text(byClass(now.parentNode, "p2-sn")[0]), STRINGS.ed_seg_now);
  assert.equal(byClass(a.root, "p2-sn").length, 1);
  assert.equal(FElement.focused.getAttribute("type"), "radio", "focus moves into the picker");
  await a.choose("xhigh");
  assert.deepEqual(a.log.preview, [[w.project_target, "xhigh"]]);
  // Cancel returns to the main card.
  btn(a.root, STRINGS.ed_cancel).click();
  await settle();
  assert.equal(text(byClass(a.root, "cd-h")[0]), STRINGS.ed_card);
});

test("links: a blocked entry gets a lock line, and no entry gets one in off or locked mode", () => {
  const s = real("shell");
  const a = app({ data: { settings: s.settings, targets: s.targets, history: s.history } });
  const locks = byClass(a.panel(), "p2-lock");
  assert.equal(locks.length, 1);
  assert.equal(text(locks[0]), STRINGS.ed_lock_env_shell);
  assert.equal(byClass(locks[0], "ic").length, 1);
  assert.equal(entryLayer(locks[0]), "");
  assert.match(text(locks[0].parentNode), /Set by CLAUDE_CODE_EFFORT_LEVEL/);
  assert.equal(links(a.root).length, 1, "the overridden project line is a target");
  for (const mode of ["off", "locked"]) {
    const b = app({ mode, data: { settings: s.settings, targets: s.targets, history: s.history } });
    assert.equal(byClass(b.root, "p2-lock").length + links(b.root).length, 0, mode);
  }
  // A blocked row with no reason draws nothing, and builds no key.
  const none = clone(s.targets);
  none.blocked[0].reason = null;
  const c = app({ data: { settings: s.settings, targets: none, history: s.history } });
  assert.equal(byClass(c.panel(), "p2-lock").length, 0);
  assert.equal(anyKey(c.root), false);
  assert.equal(/ed_lock_null/.test(c.root.textContent), false);
  // A model with no effort levels gets no link and no lock line.
  const h = real("haiku");
  const d = app({ data: { settings: h.settings, targets: h.targets, history: h.history } });
  assert.equal(byClass(d.panel(), "p2-lock").length, 1);
  assert.equal(links(d.root).length, 0);
});

test("links: an entry that matches nothing makes the page load the targets again, once", async () => {
  const w = real("overridden");
  const broken = clone(w.targets);
  for (const t of broken.targets) t.ref = t.ref + "x";
  const a = app({ data: { settings: w.settings, targets: broken, history: w.history } });
  assert.equal(links(a.root).length, 0);
  await settle();
  assert.equal(a.log.reload, 1, "one load for all the missing entries");
  a.draw();
  a.draw();
  await settle();
  assert.equal(a.log.reload, 1, "a miss that stays doesn't loop");
  // A pass with every entry matched resets the guard.
  a.st.targets = wrap(w.targets);
  a.draw();
  a.st.targets = wrap(broken);
  a.draw();
  await settle();
  assert.equal(a.log.reload, 2);
});

// ---------------------------------------------------------------- focus

test("focus: an edit control that held focus has it again after a draw from new data, and the heading does not take it", async () => {
  const a = app({ data: baseData(), backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await a.choose("high");
  const high = radio(a.root, "high");
  high.focus();
  const before = a.title();
  a.draw();
  assert.notEqual(radio(a.root, "high"), high, "the nodes were rebuilt");
  assert.equal(FElement.focused, radio(a.root, "high"));
  assert.ok(radio(a.root, "high").hasAttribute("checked"));
  assert.equal(a.title().focusCalls || 0, 0, "title.focus did not fire from an edit control");
  assert.ok(before);
  const cancel = btn(a.root, STRINGS.ed_cancel);
  cancel.focus();
  a.draw();
  assert.equal(FElement.focused, btn(a.root, STRINGS.ed_cancel));
  assert.equal(a.title().focusCalls || 0, 0);
  // A link keeps it too.
  const link = links(a.root)[0];
  link.focus();
  a.draw();
  assert.equal(FElement.focused.getAttribute("data-edit-focus"), link.getAttribute("data-edit-focus"));
  // The strip lives outside the panel, and its button keeps focus as well.
  const s = app({ data: { settings: S.after_save.settings, targets: S.after_save.targets, history: S.after_save.history } });
  const undo = btn(s.root, STRINGS.ed_undo);
  undo.focus();
  s.draw();
  assert.equal(FElement.focused, btn(s.root, STRINGS.ed_undo));
  assert.notEqual(FElement.focused, undo);
});

test("focus: a focus inside the panel that is not an edit control still goes to the heading", () => {
  const a = app({ data: baseData() });
  byClass(a.panel(), "win")[0].focus();
  a.draw();
  assert.equal(a.title().focusCalls, 1);
});

test("focus: picking a radio redraws only the card's node, and the strip's node stays", async () => {
  const a = app({ data: { settings: S.after_save.settings, targets: S.after_save.targets, history: S.after_save.history }, backend: { preview: async (t, v) => ok(S.previews[v]) } });
  const strip = slotOf(a.root, "strip");
  const bar = strips(a.root)[0];
  const winner = byClass(a.root, "win")[0];
  const title = a.title();
  await a.choose("medium");
  assert.equal(slotOf(a.root, "strip"), strip);
  assert.equal(strips(a.root)[0], bar);
  assert.equal(byClass(a.root, "win")[0], winner);
  assert.equal(a.title(), title);
  assert.equal(a.log.draws, 1, "the page was drawn once, at the start");
});

// ---------------------------------------------------------------- text nodes

const HOSTILE = ["<img src=x onerror=alert(1)>", "</code><script>alert(1)</script>"];

test("#87 text nodes: diff lines are drawn as text, never as markup, even when they hold tags", async () => {
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

test("text nodes: every server value in the card is text, so a hostile path and value make no element", async () => {
  const evil = HOSTILE[0];
  const pv = clone(S.previews.high);
  pv.diff.file_display = evil;
  pv.before.entries.forEach((e) => { if (e.file) e.file = e.file; });
  const targets = clone(S.start.targets);
  targets.targets[0].file_display = evil;
  targets.runs_as = evil;
  const history = clone(S.after_save.history);
  history.rows[0].backup_display = evil;
  history.rows[0].file_display = evil;
  history.rows[0].old_value = evil;
  const a = app({ data: { settings: S.start.settings, targets, history }, backend: { preview: async () => ok(pv) } });
  await a.choose("high");
  assert.equal(a.root.find((n) => n.tagName === "img").length, 0);
  assert.ok(a.root.textContent.includes(evil));
  assert.equal(parsed.length, 0);
});

test("text nodes: edit_card.js holds no call that parses markup, no style, and every diff text goes through h()", () => {
  const source = fs.readFileSync(new URL("js/edit_card.js", STATIC), "utf8");
  for (const banned of ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "DOMParser", "createContextualFragment"]) {
    assert.equal(source.includes(banned), false, banned);
  }
  assert.equal(/\.style\b|\bstyle\s*:/.test(source.replace(/\/\/.*$/gm, "")), false);
  // The diff text is the argument of h("code", ...), and h() makes a text node of a string child.
  assert.match(source, /h\("code", null, parts \|\| text\(line\.text\)\)/);
  const h = fs.readFileSync(new URL("js/h.js", STATIC), "utf8");
  assert.match(h, /document\.createTextNode\(String\(child\)\)/);
});

test("css: no element in the card, the review or the strips carries a style", async () => {
  const a = app({ data: { settings: S.after_save.settings, targets: S.after_save.targets, history: S.after_save.history }, backend: { preview: async (t, v) => ok(S.previews[v]) } });
  await a.choose("high");
  for (const n of flat(a.root)) {
    if (n.styleMap) assert.deepEqual(Object.keys(n.styleMap), [], n.tagName);
    if (n.getAttribute) assert.equal(n.getAttribute("style"), null);
  }
});

// ---------------------------------------------------------------- review fixes

test("fix: an answer with a status and an unknown code is never the network line", async () => {
  const a = app({ data: baseData(), backend: { preview: async () => bad("error", 500, { error: "write_failed" }) } });
  await a.choose("high");
  const alert = byClass(a.root, "p2-nt-err")[0];
  assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + STRINGS.ed_err_forbidden);
  assert.notEqual(STRINGS.ed_err_forbidden, STRINGS.ed_err_network);
  const none = app({ data: baseData(), backend: { preview: async () => bad("error", 0, null) } });
  await none.choose("high");
  assert.equal(text(byClass(byClass(none.root, "p2-nt-err")[0], "p2-nt-h")[0]), "✕" + STRINGS.ed_err_network);
});

test("fix: an undo that answers write_failed shows the failed-write strip with Dismiss and no Try again", async () => {
  const a = app({
    data: { settings: S.after_save.settings, targets: S.after_save.targets, history: S.after_save.history },
    backend: { ...saveFlow(), undo: async () => bad("error", 500, { error: "write_failed" }) },
  });
  await a.press(STRINGS.ed_undo);
  const alert = byClass(a.root, "p2-nt-err")[0];
  assert.equal(text(byClass(alert, "p2-nt-h")[0]), "✕" + STRINGS.ed_fail_h);
  assert.equal(text(tag(alert, "p")[0]), T("ed_fail_t", { file: "settings.json" }));
  assert.deepEqual(tag(alert, "button").map(text), [STRINGS.ed_dismiss]);
  assert.equal(btn(a.root, STRINGS.ed_try_again), undefined);
  assert.equal(FElement.focused, tag(alert, "button")[0]);
  assert.equal(anyKey(a.root), false);
});

test("fix: after a save, focus goes to Undo when the edit can be undone, else to the picker", async () => {
  const a = app({ data: baseData(), backend: saveFlow() });
  await a.choose("high");
  btn(a.root, T("ed_save_to", { file: "settings.json" })).click();
  await settle();
  assert.equal(S.save.edit.undoable, true);
  assert.equal(FElement.focused, btn(a.root, STRINGS.ed_undo));
  const body = clone(S.save);
  body.edit.undoable = false;
  const b = app({ data: baseData(), backend: { ...saveFlow(), save: async () => ({ ...ok(body), after: S.after_save }) } });
  await b.choose("high");
  btn(b.root, T("ed_save_to", { file: "settings.json" })).click();
  await settle();
  assert.equal(FElement.focused.getAttribute("type"), "radio");
});

test("fix: a stale save reloads the edit data once, does not save again, and keeps the new preview and notice", async () => {
  const s = real("stale");
  const a = app({ data: baseData(), backend: { ...saveFlow(), save: async () => bad("stale", 409, s.stale_file), refresh: () => ({}) } });
  await a.choose("high");
  btn(a.root, T("ed_save_to", { file: "settings.json" })).click();
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
  assert.ok(btn(a.root, T("ed_save_to", { file: "settings.json" })));
  assert.equal(a.log.refresh, 1);
  assert.equal(a.log.save.length, 1);
});

test("fix: a stale save refreshes the tiles and the trail too, not only the targets and history", async () => {
  const s = real("stale");
  const fresh = S.after_save.settings;
  const a = app({
    data: baseData(),
    backend: { ...saveFlow(), save: async () => bad("stale", 409, s.stale_file), refresh: () => ({ settings: fresh }) },
  });
  const old = text(a.root);
  await a.choose("high");
  btn(a.root, T("ed_save_to", { file: "settings.json" })).click();
  await settle();
  assert.equal(a.log.refresh, 1);
  assert.deepEqual(a.st.settings, fresh, "the settings came back from the refresh");
  assert.notEqual(text(a.root), old, "the page drew the new settings");
  assert.equal(byClass(a.root, "p2-nt-warn").length, 1, "the notice survives the refresh");
  assert.ok(btn(a.root, T("ed_save_to", { file: "settings.json" })), "the review survives the refresh");
});

test("fix: a level stopped by a managed cap says can't reach, not raise cap", () => {
  const m = real("managed_cap");
  const stopped = m.targets.levels.filter((l) => l.result === "stopped");
  assert.ok(stopped.some((l) => l.limits.some((x) => x.kind === "cap" && x.lock_reason !== "cap_later")));
  const a = app({ data: { settings: m.settings, targets: m.targets, history: m.history } });
  const notes = byClass(a.root, "p2-sn").map(text);
  assert.equal(notes.includes(STRINGS.ed_seg_cap), false);
  assert.ok(notes.includes(STRINGS.ed_seg_stopped));
});

// ---------------------------------------------------------------- run

let failed = 0;
for (const [name, fn] of tests) {
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

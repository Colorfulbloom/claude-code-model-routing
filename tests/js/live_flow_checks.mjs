// Browser-free checks of the Live page's "Dispatches in this session" card, run by tests/test_live_flow_js.py. They load
// pages/live.js (which builds pages/live_flow.js) and the shared modules from dashboard/static/js against the small
// fake DOM in fakedom.mjs, with fake timers, a fake tab visibility and a fake phone media query. Nothing here opens a
// browser or a socket. The payloads are the flow_*.json files in tests/fixtures/live, named by MR_LIVE_FIXTURES, and
// the run reads times in America/New_York (the TZ the wrapper sets). A failed check prints its name and the reason,
// and the exit code is 1.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { FElement, createPage } from "./fakedom.mjs";

const STATIC = new URL("../../dashboard/static/", import.meta.url);
const JS = new URL("js/", STATIC).href;
const STRINGS = JSON.parse(fs.readFileSync(new URL("strings.json", STATIC), "utf8"));
const FIXTURES = process.env.MR_LIVE_FIXTURES;
assert.ok(FIXTURES, "MR_LIVE_FIXTURES names the folder of fixture payloads");
assert.equal(process.env.TZ, "America/New_York", "the checks read clock times in New York");

const fixture = (name) => JSON.parse(fs.readFileSync(path.join(FIXTURES, name + ".json"), "utf8"));
const copy = (value) => JSON.parse(JSON.stringify(value));

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

const format = await import(JS + "format.js");
format.setStrings(STRINGS);
const router = await import(JS + "router.js");
const { createLive } = await import(JS + "pages/live.js");
const { POLL_MS } = await import(JS + "live_poll.js");

// The setter below catches any attempt to parse text as markup.
const parsed = [];
Object.defineProperty(FElement.prototype, "innerHTML", { set(v) { parsed.push(String(v)); }, get() { return ""; } });
Object.defineProperty(FElement.prototype, "outerHTML", { set(v) { parsed.push(String(v)); }, get() { return ""; } });

const KEY = "tidewater-reporting";
const SID1 = "c57d41c0-3a1e-4b7a-9d52-6a8f0e1b2c34";
const SID2 = "8e22b6f1-9c4d-4e0a-b1f7-52d3a7c9e610";
const MAIN = "@main";
// The run ids of the fixtures, written out so a check reads like the board.
const DR = "d00a1b2c3d4e";
const SC1 = "5c01a9e0b1c2";
const SC2 = "5c02a9e0b1c3";
const FW1 = "f301a9e0b1c4";
const FW2 = "f302a9e0b1c5";
const TW = "7e0a1b2c3d4f";
const JD = "1d0a1b2c3d50";
const MOTION = ["lv-fl-enter", "lv-fl-draw", "lv-fl-renew"];

// ---------------------------------------------------------------- helpers

const settle = () => new Promise((resolve) => setImmediate(resolve));
const hasClass = (n, c) => Boolean(n.classList && n.classList.contains(c));
const byClass = (root, c) => root.find((n) => hasClass(n, c));
const byTag = (root, tag) => root.find((n) => n.tagName === tag);
const one = (root, c) => {
  const found = byClass(root, c);
  assert.equal(found.length, 1, "one ." + c + ", found " + found.length);
  return found[0];
};
const text = (n) => n.textContent;
const ok = (data) => ({ ok: true, status: 200, data });

function makeClock() {
  let now = 0;
  let seq = 0;
  const timers = new Map();
  return {
    get now() { return now; },
    set: (fn, wait) => { seq += 1; timers.set(seq, { at: now + wait, fn }); return seq; },
    clear: (id) => { timers.delete(id); },
    async advance(ms) {
      const end = now + ms;
      for (;;) {
        const due = [...timers].filter(([, x]) => x.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break;
        now = due[1].at;
        timers.delete(due[0]);
        due[1].fn();
        await settle();
      }
      now = end;
    },
  };
}

// A Live page on the fake DOM, with a phone media query a check can flip.
function boot({ key = KEY, narrow = false } = {}) {
  const page = createPage();
  const section = page.sections.live;
  const clock = makeClock();
  const pending = [];
  const ticker = { seq: 0, fns: new Map() };
  const media = { matches: narrow, listeners: [], addEventListener(_type, fn) { this.listeners.push(fn); } };
  const env = {
    setTimer: clock.set,
    clearTimer: clock.clear,
    startTick: (fn) => { ticker.seq += 1; ticker.fns.set(ticker.seq, fn); return ticker.seq; },
    stopTick: (id) => { ticker.fns.delete(id); },
    now: () => clock.now,
    isVisible: () => true,
    listenVisibility: () => () => {},
    matchNarrow: () => media,
  };
  const live = createLive(env);
  const makeCtx = (k) => ({
    route: { name: "live", params: {}, query: { project: k } },
    project: { key: k, name: "Tidewater reporting" },
    transcriptsDir: "~/.claude/projects",
    hashFor: (name, params, patch) => router.hashFor(name, params, Object.assign({ project: k }, patch)),
    live: () => new Promise((resolve) => { pending.push(resolve); }),
  });
  let ctx = makeCtx(key);
  const app = {
    section, clock, media, pending,
    start() { live.setActive(true, ctx); live.render(section, ctx); },
    go(next) { ctx = makeCtx(next); live.setActive(true, ctx); live.render(section, ctx); },
    tick() { for (const fn of [...ticker.fns.values()]) fn(); },
    async reply(res) {
      assert.ok(pending.length > 0, "a request is waiting for an answer");
      pending.shift()(res);
      await settle();
    },
    // The next poll fires, and the server answers it.
    async poll(payload) {
      await clock.advance(POLL_MS);
      await app.reply(ok(payload));
    },
    flip(narrowNow) {
      media.matches = narrowNow;
      media.listeners.forEach((fn) => fn({ matches: narrowNow }));
    },
    sr: () => section.childNodes[0],
  };
  return app;
}

let etagSeq = 0;
// A changed answer: a new etag, a new server time, and whatever the check changes in the session.
function changed(payload, iso, mutate) {
  const next = copy(payload);
  etagSeq += 1;
  next.etag = String(etagSeq).padStart(16, "0");
  if (iso) next.server_time = iso;
  if (mutate) mutate(next.session);
  return next;
}

const flowCard = (app) => one(app.section, "lv-fl");
const cards = (app) => byClass(app.section, "lv-fl-node").filter((n) => !hasClass(n, "lv-fl-stub"));
const stubs = (app) => byClass(app.section, "lv-fl-stub");
const cardOf = (app, id) => {
  const found = cards(app).filter((n) => n.getAttribute("data-run") === id);
  assert.equal(found.length, 1, "one card for " + id);
  return found[0];
};
const part = (n, c) => text(one(n, c));
const edges = (app) => byClass(app.section, "lv-fl-e");
const edgeOf = (app, key) => {
  const found = edges(app).filter((n) => n.getAttribute("data-edge") === key);
  assert.equal(found.length, 1, "one connector " + key);
  return found[0];
};
const edgeKeys = (app) => edges(app).map((n) => n.getAttribute("data-edge")).sort();
const chips = (app) => byClass(app.section, "lv-fl-chip");
const srItems = (app) => byTag(one(app.section, "lv-fl-sr"), "li");
const moving = (app) => app.section.find((n) => MOTION.some((c) => hasClass(n, c)));
const hiddenAbove = (n) => {
  for (let x = n; x && x.getAttribute; x = x.parentNode) if (x.getAttribute("aria-hidden") === "true") return true;
  return false;
};
const px = (n) => n.styleMap;
const addRun = (session, patch) => {
  const base = copy(session.runs.find((r) => r.run_id === JD));
  const run = Object.assign(base, patch);
  session.runs.push(run);
  return run;
};
const NEW_RUN = {
  run_id: "9a9a00000001", route_key: "reviewer", agent: "reviewer", label_n: null, parent: DR, parent_known: true, dispatch_order: 8,
  together: null, started: "2026-10-30T16:24:30-04:00", last_request: "2026-10-30T16:24:44-04:00", active_at: "2026-10-30T16:24:44-04:00",
  state: "working", rounds: [{ n: 1, started: "2026-10-30T16:24:30-04:00", last_request: "2026-10-30T16:24:44-04:00", by: DR }], tokens: 1200, cost: 0.01,
};

// ---------------------------------------------------------------- the card, wide

test("flow: the card sits between the charts and the latest requests", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("flow_busy")));
  const kinds = one(app.section, "lv-stack").childNodes.map((n) => (hasClass(n, "kpis") ? "kpis" : hasClass(n, "lv-g21") ? "grid"
    : hasClass(n, "lv-fl") ? "flow" : hasClass(n, "cd") ? "requests" : hasClass(n, "foot") ? "foot" : "?"));
  assert.deepEqual(kinds, ["kpis", "grid", "flow", "requests", "foot"]);
  const card = flowCard(app);
  assert.equal(card.tagName, "section");
  assert.equal(card.hidden, false);
  assert.equal(part(card, "cd-h"), "Dispatches in this session");
  assert.equal(part(card, "cd-sub"), "Who dispatched whom, and in what order?");
  assert.equal(byClass(card, "cd-ic").length, 1, "the card has its icon");
});

test("flow: eight cards with the board's names, badges, states, times and figures", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("flow_busy")));
  assert.equal(cards(app).length, 8);
  const names = (ids) => ids.map((id) => part(cardOf(app, id), "lv-fl-name"));
  assert.deepEqual(names([MAIN, DR, SC1, SC2, FW1, FW2, TW, JD]),
    ["Main session", "deep-reasoner", "scout 1", "scout 2", "fast-worker 1", "fast-worker 2", "tech-writer", "judge"], "label_n follows the name");
  assert.deepEqual([MAIN, DR, SC1, SC2, FW1, FW2, TW, JD].map((id) => part(cardOf(app, id), "lv-fl-n")), ["", "1", "2", "3", "4", "5", "6", "7"]);
  assert.deepEqual([MAIN, DR, SC1, FW1, TW, JD].map((id) => part(cardOf(app, id), "lv-fl-bdg")),
    ["Opus 5.5 · high", "Opus 5.5 · high", "Haiku 5.5 · medium", "Sonnet 5.5 · medium", "Opus 5.5 · medium", "Sonnet 5.5 · high"]);
  assert.deepEqual([MAIN, DR, SC1, SC2, FW1, FW2, TW, JD].map((id) => cardOf(app, id).getAttribute("data-s")),
    ["idle", "working", "done", "done", "done", "done", "working", "working"]);
  assert.deepEqual([MAIN, DR, SC1, TW].map((id) => part(cardOf(app, id), "lv-fl-st")), ["Idle", "Working", "Done", "Working"]);
  assert.equal(one(cardOf(app, SC1), "lv-fl-st").getAttribute("data-s"), "done");
  assert.deepEqual([MAIN, DR, SC1, SC2, FW1, FW2, TW, JD].map((id) => part(cardOf(app, id), "lv-fl-meta")),
    ["Started 4:01 PM", "Started 4:02 PM", "Ran for 3 min", "Ran for 4 min", "Ran for 7 min", "Ran for 3 min", "Started 4:22 PM", "Started 4:17 PM"],
    "the current round's start while it runs, the summed spans when done");
  assert.deepEqual([MAIN, DR, SC1, TW].map((id) => part(cardOf(app, id), "lv-fl-tc")), ["503K · $0.71", "312K · $0.41", "48K · $0.02", "41K · $0.06"]);
  const rounds = cards(app).filter((n) => byClass(n, "lv-fl-rnd").length);
  assert.deepEqual(rounds.map((n) => n.getAttribute("data-run")), [TW], "only the resumed run wears a Round badge");
  assert.equal(part(rounds[0], "lv-fl-rnd"), "Round 2");
  assert.equal(byClass(cardOf(app, TW), "lv-fl-bot").length, 1, "and has a bottom port");
  assert.equal(byClass(cardOf(app, DR), "lv-fl-bot").length, 0);
  assert.equal(byClass(cardOf(app, MAIN), "lv-fl-in").length, 0, "the main session has no in port");
  assert.equal(byClass(cardOf(app, DR), "lv-fl-in").length, 1);
  assert.equal(byClass(cardOf(app, DR), "lv-fl-out").length, 1);
});

test("flow: the layout is depth columns, siblings in start order, 252 by 84 with 104 and 14 gaps", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("flow_busy")));
  const at = (id) => [px(cardOf(app, id)).left, px(cardOf(app, id)).top];
  assert.deepEqual(at(MAIN), ["24px", "24px"]);
  assert.deepEqual(at(DR), ["380px", "24px"], "one column of 252 plus 104 to the right of the main session, on its row");
  assert.deepEqual(at(SC1), ["736px", "24px"]);
  assert.deepEqual(at(SC2), ["736px", "122px"], "98 px a row");
  assert.deepEqual(at(FW1), ["736px", "220px"]);
  assert.deepEqual(at(FW2), ["736px", "318px"]);
  assert.deepEqual(at(JD), ["736px", "416px"], "the judge, dispatched after the others, is last under deep-reasoner");
  assert.deepEqual(at(TW), ["380px", "514px"], "the main session's second child waits for the first one's whole subtree");
  const stage = one(app.section, "lv-fl-stage");
  assert.equal(px(stage).width, "1012px");
  assert.equal(px(stage).height, "662px");
  const canvas = one(app.section, "lv-fl-canvas");
  assert.ok(!hasClass(canvas, "lv-fl-narrow"));
  assert.equal(one(app.section, "lv-fl-edges").getAttribute("width"), "1012");
});

test("flow: port to port connectors, a shared trunk with a chip, and a loop with a Round chip", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("flow_busy")));
  assert.deepEqual(edgeKeys(app), ["b:" + FW1, "b:" + FW2, "b:" + SC1, "b:" + SC2, "e:" + DR, "e:" + JD, "e:" + TW, "l:" + TW + ":2", "t:" + FW1, "t:" + SC1].sort());
  assert.equal(edgeOf(app, "e:" + DR).getAttribute("d"), "M276,54 C328,54 328,54 380,54", "out port to in port, a cubic");
  assert.equal(edgeOf(app, "t:" + SC1).getAttribute("d"), "M632,54 C664,54 664,103 696,103", "the trunk ends at a junction between the two");
  assert.equal(edgeOf(app, "b:" + SC2).getAttribute("d"), "M696,103 C726,103 706,152 736,152");
  const cls = (key) => edgeOf(app, key).getAttribute("class").split(" ");
  assert.ok(cls("e:" + DR).includes("lv-fl-e-live"), "a working child's line is live");
  assert.ok(!cls("t:" + SC1).includes("lv-fl-e-live") && !cls("b:" + SC1).includes("lv-fl-e-live"), "a done pair's lines are not");
  assert.ok(cls("e:" + JD).includes("lv-fl-e-live"));
  assert.ok(cls("l:" + TW + ":2").includes("lv-fl-e-loop") && cls("l:" + TW + ":2").includes("lv-fl-e-live"));
  assert.ok(edges(app).every((n) => !hasClass(n, "lv-fl-e-guess")));
  const loop = edgeOf(app, "l:" + TW + ":2").getAttribute("d");
  assert.ok(loop.startsWith("M276,54 H338 Q350,54 350,66 V"), "the main session resumed it, so the loop leaves its out port into the gutter 30 px before the card: " + loop);
  assert.ok(loop.endsWith("V603"), "and ends at the bottom port, 5 px under the card: " + loop);
  assert.deepEqual(chips(app).map(text).sort(), ["2 agents at once", "2 agents at once", "Round 2 · 4:22 PM"]);
  const together = byClass(app.section, "lv-fl-chip-g");
  assert.equal(together.length, 2);
  assert.equal(px(together.find((c) => c.getAttribute("data-chip") === "g:" + SC1)).left, "688px");
  assert.equal(px(together.find((c) => c.getAttribute("data-chip") === "g:" + SC1)).top, "93px");
  assert.equal(byClass(app.section, "lv-fl-chip-r").length, 1);
});

test("flow: Done, Working and Idle words, the legend, and no scroll hints when everything fits", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("flow_busy")));
  const note = byClass(app.section, "lv-fl-note").find((n) => !hasClass(n, "lv-fl-unlinked"));
  assert.equal(note.hidden, false);
  assert.equal(text(note), "Lines show who dispatched whom. A line into the bottom of a card starts a new round.");
  assert.equal(byClass(app.section, "lv-fl-unlinked")[0].hidden, true, "every run has a dispatcher");
  assert.ok(byClass(app.section, "lv-fl-more").every((n) => n.hidden));
  assert.equal(byClass(app.section, "lv-fl-empty").length, 0);
});

// ---------------------------------------------------------------- the screen reader list

test("flow: only the canvas layers are aria-hidden, and the list says what the cards say, in dispatch order", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("flow_busy")));
  assert.equal(one(app.section, "lv-fl-edges").getAttribute("aria-hidden"), "true");
  assert.equal(one(app.section, "lv-fl-cards").getAttribute("aria-hidden"), "true");
  const srw = one(app.section, "lv-fl-srw");
  assert.ok(!hiddenAbove(srw), "the list is exposed");
  assert.equal(text(byTag(srw, "h3")[0]), "Agents in dispatch order");
  assert.equal(byTag(srw, "ol").length, 1);
  const items = srItems(app);
  assert.deepEqual(items.map((li) => li.getAttribute("data-run")), [MAIN, DR, SC1, SC2, FW1, FW2, TW, JD]);
  assert.deepEqual(items.map(text), [
    "Main session, Opus 5.5 high, Idle. 503K tokens · $0.71",
    "deep-reasoner, Opus 5.5 high, Working. Dispatched by Main session. 312K tokens · $0.41",
    "scout 1, Haiku 5.5 medium, Done. Dispatched by deep-reasoner. 48K tokens · $0.02",
    "scout 2, Haiku 5.5 medium, Done. Dispatched by deep-reasoner. 61K tokens · $0.03",
    "fast-worker 1, Sonnet 5.5 medium, Done. Dispatched by deep-reasoner. 140K tokens · $0.12",
    "fast-worker 2, Sonnet 5.5 medium, Done. Dispatched by deep-reasoner. 22K tokens · $0.02",
    "tech-writer, Opus 5.5 medium, Working. Dispatched by Main session. Round 2 of 2. 41K tokens · $0.06",
    "judge, Sonnet 5.5 high, Working. Dispatched by deep-reasoner. 54K tokens · $0.05",
  ]);
  assert.ok(items.every((li) => !text(li).includes("{")), "no slot is left unfilled");
});

test("flow: a run with no recorded dispatcher hangs off Main session on a dashed line, with its own notes", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("flow_unlinked")));
  const [LK, UA, UB, UC] = ["1c1c00000004", "0a0a00000001", "0b0b00000002", "0c0c00000003"];
  assert.equal(cards(app).length, 5);
  assert.deepEqual(edgeKeys(app), ["b:" + UA, "b:" + UB, "e:" + LK, "e:" + UC, "t:" + UA].sort());
  const dashed = edges(app).filter((n) => hasClass(n, "lv-fl-e-guess"));
  assert.deepEqual(dashed.map((n) => n.getAttribute("data-edge")).sort(), ["b:" + UA, "b:" + UB, "e:" + UC, "t:" + UA].sort(), "the linked scout's line is solid");
  assert.equal(edgeOf(app, "b:" + UA).getAttribute("d").includes(" C"), false, "a dashed branch is an elbow with its own vertical");
  assert.ok(edgeOf(app, "b:" + UA).getAttribute("d").startsWith("M308,"), "the junction sits 72 px before the cards, 42 px clear of the loop gutter");
  assert.equal(edgeOf(app, "e:" + UC).getAttribute("d"), "M276,54 C306,54 278,348 308,348 H380", "a dashed single line turns 72 px before the card");
  assert.deepEqual([LK, UA, UB, UC].map((id) => cardOf(app, id).getAttribute("data-link")), ["known", "guess", "guess", "guess"]);
  assert.ok(dashed.every((n) => n.getAttribute("pathLength") === null), "a dashed line cannot carry the one-unit draw length");
  assert.equal(edgeOf(app, "e:" + LK).getAttribute("pathLength"), "1");
  const note = one(app.section, "lv-fl-unlinked");
  assert.equal(note.hidden, false);
  assert.equal(text(note), "3 agents have no recorded dispatcher, so they're listed under Main session. An agent running in the foreground gets linked when it finishes.");
  assert.deepEqual(chips(app).map(text), ["2 agents at once"], "unlinked siblings still share a trunk");
  const items = srItems(app).map(text);
  assert.equal(items[1], "scout, Haiku 5.5 medium, Done. Dispatched by Main session. 20K tokens · $0.01");
  assert.equal(items[2], "reviewer 1, Sonnet 5.5 xhigh, Working. Dispatcher not recorded, so it's listed under Main session. 220K tokens · $0.14");
  assert.ok(!items[2].includes("Dispatched by"), "never Dispatched by Main session for an unlinked run");
  assert.equal(items[4], "Unnamed agent, Sonnet 5.5 effort not recorded, Done. Dispatcher not recorded, so it's listed under Main session. 900 tokens · Not priced");
  assert.equal(items[0], "Main session, Opus 5.5 high, Working. 503K tokens · $0.71", "nothing about a dispatcher for the main session");
  assert.equal(part(cardOf(app, UC), "lv-fl-name"), "Unnamed agent");
  assert.equal(part(cardOf(app, UC), "lv-fl-bdg"), "Sonnet 5.5 · effort not recorded");
  assert.equal(part(cardOf(app, UC), "lv-fl-tc"), "900 · Not priced");
  const single = fixture("flow_unlinked");
  single.session.runs[2].parent_known = true;
  single.session.runs[3].parent_known = true;
  const other = boot();
  other.start();
  await other.reply(ok(single));
  assert.equal(text(one(other.section, "lv-fl-unlinked")), "1 agent has no recorded dispatcher, so it's listed under Main session. An agent running in the foreground gets linked when it finishes.");
});

// ---------------------------------------------------------------- later rounds

test("flow: a later round loops in from its resumer, or from the dispatcher when the resumer is unknown", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("flow_round2")));
  const [LD, RV, WK, WR, HP] = ["1e0a00000001", "0e0a00000002", "a00a00000003", "70aa00000004", "0e1a00000005"];
  assert.equal(cards(app).length, 6);
  const loop = (id, n) => edgeOf(app, "l:" + id + ":" + n).getAttribute("d");
  assert.ok(loop(WR, 3).startsWith("M276,54 H"), "the main session resumed it: " + loop(WR, 3));
  assert.ok(loop(HP, 2).startsWith("M632,54 H"), "nobody is named, so it leaves the dispatcher: " + loop(HP, 2));
  assert.equal(loop(WK, 2), "M632,332 H694 Q706,332 706,320 V151 Q706,139 718,139 H777 Q789,139 789,127 V113",
    "the resumer sits below, so the same route runs up the gutter at 706 (736 minus 30), never behind a card");
  for (const id of [WK, WR, HP, MAIN]) {
    const d = (edges(app).find((n) => n.getAttribute("data-edge").startsWith("l:" + id)) || { getAttribute: () => "" }).getAttribute("d");
    assert.ok(d === "" || (!d.includes(" C") && d.includes(" H") && d.endsWith(" V" + (parseFloat(px(cardOf(app, id)).top) + 89))), "one rule for every loop: " + id + " " + d);
  }
  assert.deepEqual([WK, HP, RV, WR].map((id) => px(cardOf(app, id)).top), ["24px", "163px", "302px", "400px"],
    "a resumed card leaves 55 px under it for its loop and chip, so the next card in its column never sits on them");
  assert.deepEqual(chips(app).map(text).sort(), ["Round 2 · 4:18 PM", "Round 2 · 4:20 PM", "Round 3 · 4:22 PM"]);
  assert.deepEqual([WK, WR, HP].map((id) => part(cardOf(app, id), "lv-fl-rnd")), ["Round 2", "Round 3", "Round 2"]);
  assert.deepEqual([WK, WR, HP].map((id) => byClass(cardOf(app, id), "lv-fl-bot").length), [1, 1, 1]);
  assert.equal(part(cardOf(app, HP), "lv-fl-tc"), "9,000 · Not priced");
  assert.ok(edgeOf(app, "e:" + WK), "the first connector stays beside the loop");
  assert.equal(srItems(app).map(text)[4], "tech-writer, Opus 5.5 medium, Working. Dispatched by Main session. Round 3 of 3. 41K tokens · $0.06");
  const done = fixture("flow_round2");
  done.session.runs.find((r) => r.run_id === WR).state = "done";
  const fin = boot();
  fin.start();
  await fin.reply(ok(done));
  assert.equal(part(cardOf(fin, WR), "lv-fl-meta"), "Ran for 4 min", "the spans of three rounds add up: 60 + 60 + 145 s");
  assert.ok(!edgeOf(fin, "l:" + WR + ":3").getAttribute("class").includes("lv-fl-e-live"), "a done run's loop is not live");
});

test("flow: a run that ran under a minute reads seconds", async () => {
  const app = boot();
  app.start();
  const payload = fixture("flow_busy");
  const run = payload.session.runs.find((r) => r.run_id === SC1);
  run.rounds[0].last_request = "2026-10-30T16:03:50-04:00";
  await app.reply(ok(payload));
  assert.equal(part(cardOf(app, SC1), "lv-fl-meta"), "Ran for 45 s");
});

// ---------------------------------------------------------------- motion

test("flow: nothing moves on the first answer, on an unchanged one or on a tick", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("flow_busy")));
  assert.equal(moving(app).length, 0, "the first answer animates nothing");
  await app.clock.advance(5000);
  app.tick();
  assert.equal(moving(app).length, 0, "a tick adds no class");
  await app.poll(fixture("unchanged"));
  assert.equal(moving(app).length, 0, "an unchanged answer adds none");
});

test("flow: a new run enters and its connector draws, once, and the classes come off at the next changed answer", async () => {
  const app = boot();
  app.start();
  const first = fixture("flow_busy");
  await app.reply(ok(first));
  const before = new Map(cards(app).map((n) => [n.getAttribute("data-run"), n]));
  const pathsBefore = new Map(edges(app).map((n) => [n.getAttribute("data-edge"), n]));
  await app.poll(changed(first, "2026-10-30T16:24:50-04:00", (s) => { s.runs.push(copy(NEW_RUN)); }));
  assert.equal(cards(app).length, 9);
  const entered = byClass(app.section, "lv-fl-enter");
  assert.deepEqual(entered.map((n) => n.getAttribute("data-run")), [NEW_RUN.run_id], "only the new card");
  assert.deepEqual(byClass(app.section, "lv-fl-draw").map((n) => n.getAttribute("data-edge")), ["e:" + NEW_RUN.run_id], "only its connector");
  assert.equal(byClass(app.section, "lv-fl-renew").length, 0);
  for (const [id, node] of before) assert.equal(cardOf(app, id), node, "a card that stays keeps its element: " + id);
  for (const [key, node] of pathsBefore) assert.equal(edgeOf(app, key), node, "a connector that stays keeps its element: " + key);
  assert.equal(px(cardOf(app, TW)).top, "612px", "the main session's second child moved down a row, in place");
  assert.equal(part(cardOf(app, NEW_RUN.run_id), "lv-fl-name"), "reviewer");
  assert.equal(srItems(app).length, 9);
  await app.poll(changed(first, "2026-10-30T16:24:55-04:00", (s) => { s.runs.push(copy(NEW_RUN)); s.totals.tokens += 1; }));
  assert.equal(moving(app).length, 0, "the next changed answer takes the classes off, and adds none");
});

test("flow: a new round flashes its card, draws its loop, and keeps the card's element", async () => {
  const app = boot();
  app.start();
  const first = fixture("flow_busy");
  await app.reply(ok(first));
  const tw = cardOf(app, TW);
  await app.poll(changed(first, "2026-10-30T16:24:50-04:00", (s) => {
    const run = s.runs.find((r) => r.run_id === TW);
    run.rounds.push({ n: 3, started: "2026-10-30T16:24:46-04:00", last_request: "2026-10-30T16:24:49-04:00", by: MAIN });
    run.active_at = "2026-10-30T16:24:49-04:00";
    run.last_request = "2026-10-30T16:24:49-04:00";
  }));
  assert.equal(cardOf(app, TW), tw);
  assert.deepEqual(byClass(app.section, "lv-fl-renew"), [tw], "the resumed card renews");
  assert.equal(byClass(app.section, "lv-fl-enter").length, 0, "and does not enter again");
  assert.equal(part(tw, "lv-fl-rnd"), "Round 3");
  assert.equal(part(tw, "lv-fl-meta"), "Started 4:24 PM");
  assert.deepEqual(byClass(app.section, "lv-fl-draw").map((n) => n.getAttribute("data-edge")), ["l:" + TW + ":3"], "the new loop draws, the old one is gone");
  assert.equal(edges(app).filter((n) => n.getAttribute("data-edge") === "l:" + TW + ":2").length, 0);
  assert.deepEqual(chips(app).map(text).filter((x) => x.startsWith("Round")), ["Round 3 · 4:24 PM"]);
});

test("flow: a project switch and a session switch animate nothing", async () => {
  const app = boot();
  app.start();
  const first = fixture("flow_busy");
  await app.reply(ok(first));
  app.go("beta");
  const other = changed(first, null, () => {});
  other.project = "beta";
  await app.reply(ok(other));
  assert.equal(cards(app).length, 8);
  assert.equal(moving(app).length, 0, "a project switch");
  await app.poll(Object.assign(changed(other, "2026-10-30T16:24:50-04:00", (s) => { s.session_id = SID2; s.runs.push(copy(NEW_RUN)); }), { project: "beta" }));
  assert.equal(cards(app).length, 9);
  assert.equal(moving(app).length, 0, "another session of the same project is not a change");
  await app.poll(Object.assign(changed(other, "2026-10-30T16:24:56-04:00", (s) => { s.session_id = SID2; s.runs.push(copy(NEW_RUN)); s.runs.push(Object.assign(copy(NEW_RUN), { run_id: "9a9a00000002", dispatch_order: 9 })); }), { project: "beta" }));
  assert.equal(byClass(app.section, "lv-fl-enter").length, 1, "but a change inside that session animates");
});

// ---------------------------------------------------------------- the clock

test("flow: Working turns to Idle on the page's clock, 60 seconds after active_at, and Done stays", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("flow_busy")));
  const dr = cardOf(app, DR);
  assert.equal(dr.getAttribute("data-s"), "working", "3 seconds after its last request");
  const keep = cards(app).slice();
  await app.clock.advance(57000);
  app.tick();
  assert.equal(dr.getAttribute("data-s"), "working", "exactly 60 seconds is still working, as on the Agents card");
  assert.equal(part(dr, "lv-fl-st"), "Working");
  await app.clock.advance(1000);
  app.tick();
  assert.equal(dr.getAttribute("data-s"), "idle");
  assert.equal(part(dr, "lv-fl-st"), "Idle");
  assert.equal(one(dr, "lv-fl-st").getAttribute("data-s"), "idle");
  assert.equal(cardOf(app, SC1).getAttribute("data-s"), "done", "done comes from the server");
  assert.equal(cardOf(app, MAIN).getAttribute("data-s"), "idle");
  assert.equal(cardOf(app, TW).getAttribute("data-s"), "idle", "tech-writer's round 2 ran its last request 14 seconds before the answer");
  assert.equal(srItems(app).map(text)[1], "deep-reasoner, Opus 5.5 high, Idle. Dispatched by Main session. 312K tokens · $0.41", "the list follows");
  cards(app).forEach((n, i) => assert.equal(n, keep[i], "a tick keeps every card"));
  assert.equal(moving(app).length, 0);
});

test("flow: a run that was idle turns Working when an answer brings a newer active_at", async () => {
  const app = boot();
  app.start();
  const first = fixture("flow_busy");
  await app.reply(ok(first));
  assert.equal(cardOf(app, MAIN).getAttribute("data-s"), "idle");
  await app.poll(changed(first, "2026-10-30T16:24:50-04:00", (s) => {
    s.runs[0].last_request = "2026-10-30T16:24:49-04:00";
    s.runs[0].active_at = "2026-10-30T16:24:49-04:00";
    s.runs[0].rounds[0].last_request = "2026-10-30T16:24:49-04:00";
  }));
  assert.equal(cardOf(app, MAIN).getAttribute("data-s"), "working");
  assert.equal(part(cardOf(app, MAIN), "lv-fl-st"), "Working");
});

// ---------------------------------------------------------------- many runs, the collapse button

const FINISHED_UNDER = (payload, parent) => payload.session.runs.filter((r) => r.parent === parent && r.state === "done");
const D1 = "d00a1b2c3d4e";
const D2 = "d51a1b2c3d4e";

test("flow: past 12 cards each lead folds its finished leaves into one button that stays outside the hidden layer", async () => {
  const app = boot();
  app.start();
  const payload = fixture("flow_many");
  await app.reply(ok(payload));
  assert.equal(payload.session.runs.length, 23);
  assert.equal(cards(app).length, 9, "main, two leads, tech-writer, verifier, and four agents still working");
  const found = stubs(app);
  assert.deepEqual(found.map((n) => n.getAttribute("data-run")).sort(), ["stub:" + D1, "stub:" + D2].sort());
  const stub = found.find((n) => n.getAttribute("data-run") === "stub:" + D1);
  assert.equal(stub.tagName, "button");
  assert.equal(stub.getAttribute("type"), "button");
  assert.equal(stub.getAttribute("aria-expanded"), "false");
  assert.equal(part(stub, "lv-fl-name"), "Show 7 finished");
  assert.equal(part(stub, "lv-fl-meta"), "scout, fast-worker, judge", "the agents' names, once each");
  const done = FINISHED_UNDER(payload, D1);
  assert.equal(done.length, 7);
  const tokens = done.reduce((n, r) => n + r.tokens, 0);
  const cost = done.reduce((n, r) => n + r.cost, 0);
  assert.equal(part(stub, "lv-fl-tc"), format.fmtTokens(tokens) + " · " + format.fmtCost(cost), "summed figures");
  assert.equal(part(stub, "lv-fl-st"), "Done");
  assert.ok(!hiddenAbove(stub), "the button is exposed");
  assert.ok(cards(app).every((n) => hiddenAbove(n)), "the cards are not");
  assert.equal(srItems(app).length, 23, "the list still names every run");
  assert.deepEqual(byClass(app.section, "lv-fl-chip-g").map(text), ["2 agents at once", "2 agents at once"], "the two pairs still working, and none for a folded group");
  assert.deepEqual(byClass(app.section, "lv-fl-chip-r").map(text), ["Round 2 · 4:22 PM"]);
  assert.ok(edgeOf(app, "s:stub:" + D1), "the button hangs off its lead");
  const quiet = boot();
  quiet.start();
  await quiet.reply(ok(fixture("flow_busy")));
  assert.equal(stubs(quiet).length, 0, "eight cards never fold");
  const few = fixture("flow_many");
  few.session.runs = few.session.runs.filter((r) => r.parent !== D1 || r.state !== "done" || r.run_id <= "a00000000002");
  assert.equal(FINISHED_UNDER(few, D1).length, 2, "two finished leaves are too few to fold");
  const small = boot();
  small.start();
  await small.reply(ok(few));
  assert.ok(few.session.runs.length > 12);
  assert.deepEqual(stubs(small).map((n) => n.getAttribute("data-run")), ["stub:" + D2], "only the lead with three or more folds");
});

test("flow: pressing the button shows that lead's finished runs, keeps focus and the element, and survives answers", async () => {
  const app = boot();
  app.start();
  const payload = fixture("flow_many");
  await app.reply(ok(payload));
  const stub = stubs(app).find((n) => n.getAttribute("data-run") === "stub:" + D1);
  const other = stubs(app).find((n) => n.getAttribute("data-run") === "stub:" + D2);
  stub.focus();
  stub.click();
  assert.equal(FElement.focused, stub);
  assert.equal(cards(app).length, 16, "seven more cards");
  assert.equal(stub.getAttribute("aria-expanded"), "true");
  assert.equal(part(stub, "lv-fl-name"), "Hide finished");
  assert.equal(other.getAttribute("aria-expanded"), "false", "the other lead keeps its fold");
  assert.equal(stubs(app).length, 2);
  assert.equal(moving(app).length, 0, "a press animates nothing");
  assert.deepEqual([px(stub).left, px(stub).top], ["736px", "24px"], "the button heads its lead's column");
  await app.poll(changed(payload, "2026-10-30T16:24:50-04:00", (s) => { s.totals.tokens += 5; }));
  assert.equal(stubs(app).find((n) => n.getAttribute("data-run") === "stub:" + D1), stub, "the same button after an answer");
  assert.equal(FElement.focused, stub, "with its focus");
  assert.equal(stub.getAttribute("aria-expanded"), "true");
  assert.equal(cards(app).length, 16);
  await app.poll(fixture("unchanged"));
  assert.equal(stub.getAttribute("aria-expanded"), "true");
  stub.click();
  assert.equal(cards(app).length, 9, "pressed again, they fold");
  assert.equal(stub.getAttribute("aria-expanded"), "false");
  assert.equal(part(stub, "lv-fl-name"), "Show 7 finished");
  assert.equal(FElement.focused, stub);
});

test("flow: the choice is kept per session while the page lives", async () => {
  const app = boot();
  app.start();
  const payload = fixture("flow_many");
  await app.reply(ok(payload));
  stubs(app)[0].click();
  assert.equal(cards(app).length, 16);
  await app.poll(changed(payload, "2026-10-30T16:24:50-04:00", (s) => { s.session_id = SID2; }));
  assert.equal(cards(app).length, 9, "another session starts folded");
  await app.poll(changed(payload, "2026-10-30T16:24:56-04:00", () => {}));
  assert.equal(cards(app).length, 16, "and the first one comes back open");
});

test("flow: scroll hints count the cards out of view, below and to the right, and say one in the singular", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("flow_busy")));
  const canvas = one(app.section, "lv-fl-canvas");
  const [below, right] = byClass(app.section, "lv-fl-more");
  const row = one(app.section, "lv-fl-hints");
  assert.equal(row.parentNode, flowCard(app).find((n) => hasClass(n, "cd-bd"))[0], "the hints sit in the card body");
  assert.equal(row.childNodes.length, 2);
  assert.ok(!canvas.contains(below) && !canvas.contains(right), "outside the scroll box, so never on a card or a chip");
  const body = row.parentNode.childNodes;
  assert.ok(body.indexOf(row) === body.indexOf(one(app.section, "lv-fl-box")) + 1, "directly under the box");
  assert.ok(body.indexOf(row) < body.indexOf(byClass(app.section, "lv-fl-note").find((n) => !hasClass(n, "lv-fl-unlinked"))), "above the legend");
  assert.ok(below.hidden && right.hidden);
  Object.assign(canvas, { clientHeight: 300, clientWidth: 1000, scrollTop: 0, scrollLeft: 0 });
  canvas.dispatch("scroll");
  const hidden = cards(app).filter((n) => parseFloat(px(n).top) + 40 > 300).length;
  assert.ok(hidden > 1);
  assert.equal(below.hidden, false);
  assert.equal(text(below), hidden + " more below");
  assert.equal(right.hidden, true, "1000 px is wide enough");
  Object.assign(canvas, { clientHeight: 553 });
  canvas.dispatch("scroll");
  assert.equal(text(below), "1 more below", "the singular form");
  Object.assign(canvas, { clientHeight: 700, clientWidth: 700 });
  canvas.dispatch("scroll");
  assert.equal(below.hidden, true);
  assert.equal(right.hidden, false);
  assert.equal(text(right), "5 more to the right");
  Object.assign(canvas, { clientWidth: 780 });
  canvas.dispatch("scroll");
  assert.equal(text(right), "5 more to the right", "736 plus 40 is 776");
  Object.assign(canvas, { clientWidth: 776 });
  canvas.dispatch("scroll");
  assert.ok(right.hidden, "all of them are in view at 776");
  Object.assign(canvas, { clientWidth: 775 });
  canvas.dispatch("scroll");
  assert.equal(right.hidden, false);
  await app.poll(changed(fixture("flow_busy"), "2026-10-30T16:24:50-04:00", (s) => { s.runs.push(copy(NEW_RUN)); }));
  assert.equal(right.hidden, false, "an answer recounts");
  Object.assign(canvas, { clientHeight: 553, clientWidth: 1400 });
  canvas.dispatch("scroll");
  assert.equal(text(below), "2 more below", "the new row pushed the second child down, so two sit below the fold");
  Object.assign(canvas, { scrollTop: 400 });
  canvas.dispatch("scroll");
  assert.equal(below.hidden, true, "scrolled to the end");
});

// ---------------------------------------------------------------- the phone list

test("flow: at 720 pixels and under the canvas is an indented list in dispatch-tree order with no connectors", async () => {
  const app = boot({ narrow: true });
  app.start();
  await app.reply(ok(fixture("flow_busy")));
  assert.ok(hasClass(one(app.section, "lv-fl-canvas"), "lv-fl-narrow"));
  const order = [MAIN, DR, SC1, SC2, FW1, FW2, JD, TW];
  assert.deepEqual(order.map((id) => px(cardOf(app, id)).order), order.map((_, i) => String(i)), "tree order");
  assert.deepEqual(order.map((id) => px(cardOf(app, id))["margin-left"]), ["0px", "14px", "28px", "28px", "28px", "28px", "28px", "14px"]);
  assert.ok(order.every((id) => !px(cardOf(app, id)).left), "no coordinates");
  assert.equal(edges(app).length, 0);
  assert.equal(chips(app).length, 0);
  assert.equal(part(cardOf(app, TW), "lv-fl-meta"), "Resumed by Main session · 4:22 PM");
  assert.equal(part(cardOf(app, DR), "lv-fl-meta"), "Started 4:02 PM");
  assert.equal(part(cardOf(app, SC1), "lv-fl-meta"), "Ran for 3 min");
  const note = byClass(app.section, "lv-fl-note").find((n) => !hasClass(n, "lv-fl-unlinked"));
  assert.equal(note.hidden, true, "no lines, no legend about them");
  assert.ok(byClass(app.section, "lv-fl-more").every((n) => n.hidden));
  assert.equal(px(one(app.section, "lv-fl-stage")).width, "");
  const round2 = boot({ narrow: true });
  round2.start();
  await round2.reply(ok(fixture("flow_round2")));
  assert.equal(part(cardOf(round2, "a00a00000003"), "lv-fl-meta"), "Resumed by verifier · 4:20 PM", "a peer resumed it");
  assert.equal(part(cardOf(round2, "0e1a00000005"), "lv-fl-meta"), "Round 2 · 4:18 PM", "nobody is named");
  assert.equal(part(cardOf(round2, "70aa00000004"), "lv-fl-meta"), "Resumed by Main session · 4:22 PM");
});

test("flow: crossing the breakpoint redraws in place, and keeps the cards", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("flow_busy")));
  const dr = cardOf(app, DR);
  assert.equal(px(dr).left, "380px");
  app.flip(true);
  assert.equal(cardOf(app, DR), dr, "the same element");
  assert.ok(hasClass(one(app.section, "lv-fl-canvas"), "lv-fl-narrow"));
  assert.equal(px(dr).left, "");
  assert.equal(px(dr)["margin-left"], "14px");
  assert.equal(edges(app).length, 0);
  assert.equal(part(cardOf(app, TW), "lv-fl-meta"), "Resumed by Main session · 4:22 PM");
  app.flip(false);
  assert.equal(cardOf(app, DR), dr);
  assert.equal(px(dr).left, "380px");
  assert.equal(px(dr)["margin-left"], "");
  assert.equal(edges(app).length, 10);
  assert.equal(chips(app).length, 3);
  assert.equal(part(cardOf(app, TW), "lv-fl-meta"), "Started 4:22 PM");
  assert.equal(moving(app).length, 0, "no motion from a resize");
});

// ---------------------------------------------------------------- empty, and an older server

test("flow: only the main session shows its card and No agents yet beside it, below it on a phone", async () => {
  const only = fixture("flow_busy");
  only.session.runs = only.session.runs.slice(0, 1);
  const app = boot();
  app.start();
  await app.reply(ok(only));
  assert.equal(cards(app).length, 1);
  const empty = one(app.section, "lv-fl-empty");
  assert.equal(text(byClass(empty, "es-h")[0]), "No agents yet");
  assert.equal(text(byClass(empty, "es-t")[0]), "When the main session dispatches an agent, its card shows up here after the agent's first request.");
  assert.ok(hasClass(empty, "lv-fl-empty-in"));
  assert.equal(empty.parentNode, one(app.section, "lv-fl-stage"));
  assert.equal(px(empty).left, "316px");
  assert.equal(px(one(app.section, "lv-fl-stage")).height, "132px");
  const note = byClass(app.section, "lv-fl-note").find((n) => !hasClass(n, "lv-fl-unlinked"));
  assert.equal(note.hidden, true, "no legend until there is a line");
  assert.equal(edges(app).length, 0);
  assert.equal(srItems(app).length, 1);
  const phone = boot({ narrow: true });
  phone.start();
  await phone.reply(ok(only));
  const below = one(phone.section, "lv-fl-empty");
  assert.ok(!hasClass(below, "lv-fl-empty-in"));
  assert.equal(below.parentNode, one(phone.section, "lv-fl-slot"));
  await phone.poll(changed(fixture("flow_busy"), "2026-10-30T16:24:50-04:00", () => {}));
  assert.equal(byClass(phone.section, "lv-fl-empty").length, 0, "the note goes when an agent arrives");
  assert.equal(cards(phone).length, 8);
});

test("flow: a payload with no runs hides the card and builds nothing", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(JSON.parse(fs.readFileSync(path.join(FIXTURES, "live.json"), "utf8"))));
  assert.equal(flowCard(app).hidden, true);
  assert.equal(cards(app).length, 0);
  assert.equal(srItems(app).length, 0);
  const wait = boot();
  wait.start();
  assert.equal(flowCard(wait).hidden, true, "before the first answer");
});

// ---------------------------------------------------------------- the polite line

test("announce: agents that started or finished are added to the line once a minute, and the first answer is the baseline", async () => {
  const app = boot();
  app.start();
  const first = fixture("flow_busy");
  await app.reply(ok(first));
  const sr = app.sr();
  assert.equal(text(sr), "Updated at 4:24 PM. 755K tokens, $0.94 estimated cost.", "nothing about agents on the first answer");
  await app.clock.advance(POLL_MS);
  await app.clock.advance(60000);
  await app.reply(ok(changed(first, "2026-10-30T16:25:50-04:00", (s) => {
    s.runs.push(copy(NEW_RUN));
    s.runs.find((r) => r.run_id === JD).state = "done";
  })));
  assert.equal(text(sr), "Updated at 4:25 PM. 755K tokens, $0.94 estimated cost. 1 agent started. 1 agent finished.");
  await app.poll(changed(first, "2026-10-30T16:25:55-04:00", (s) => {
    s.runs.push(copy(NEW_RUN));
    s.runs.push(Object.assign(copy(NEW_RUN), { run_id: "9a9a00000002", dispatch_order: 9 }));
    s.runs.push(Object.assign(copy(NEW_RUN), { run_id: "9a9a00000003", dispatch_order: 10 }));
    s.runs.find((r) => r.run_id === JD).state = "done";
  }));
  assert.equal(text(sr), "Updated at 4:25 PM. 755K tokens, $0.94 estimated cost. 1 agent started. 1 agent finished.", "within the minute nothing is read");
  await app.clock.advance(60000);
  await app.reply(ok(changed(first, "2026-10-30T16:27:00-04:00", (s) => {
    s.runs.push(copy(NEW_RUN));
    s.runs.push(Object.assign(copy(NEW_RUN), { run_id: "9a9a00000002", dispatch_order: 9 }));
    s.runs.push(Object.assign(copy(NEW_RUN), { run_id: "9a9a00000003", dispatch_order: 10 }));
    s.runs.find((r) => r.run_id === JD).state = "done";
    s.runs.find((r) => r.run_id === DR).state = "done";
    s.runs.find((r) => r.run_id === TW).state = "done";
  })));
  assert.equal(text(sr), "Updated at 4:27 PM. 755K tokens, $0.94 estimated cost. 2 agents started. 2 agents finished.", "the changes since the last line, counted together");
});

test("announce: a project switch sets a new baseline and says nothing about the agents already there", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("flow_busy")));
  app.go("beta");
  await app.clock.advance(61000);
  const many = fixture("flow_many");
  many.project = "beta";
  many.server_time = "2026-10-30T16:26:00-04:00";
  await app.reply(ok(many));
  assert.equal(text(app.sr()), "Updated at 4:26 PM. 755K tokens, $0.94 estimated cost.", "23 agents are there, and none is announced");
  await app.clock.advance(POLL_MS);
  await app.clock.advance(60000);
  const next = changed(many, "2026-10-30T16:28:00-04:00", (s) => { s.runs.find((r) => r.run_id === DR).state = "done"; });
  next.project = "beta";
  await app.reply(ok(next));
  assert.equal(text(app.sr()), "Updated at 4:28 PM. 755K tokens, $0.94 estimated cost. 1 agent finished.");
});

test("announce: a session switch sets a new baseline and says nothing about the agents already there", async () => {
  const app = boot();
  app.start();
  const busy = fixture("flow_busy");
  await app.reply(ok(busy));
  await app.clock.advance(61000);
  const other = changed(fixture("flow_many"), "2026-10-30T16:26:00-04:00", (s) => { s.session_id = SID2; });
  await app.reply(ok(other));
  assert.equal(text(app.sr()), "Updated at 4:26 PM. 755K tokens, $0.94 estimated cost.", "the other session's agents are not announced");
  await app.clock.advance(POLL_MS);
  await app.clock.advance(60000);
  const next = changed(other, "2026-10-30T16:28:00-04:00", (s) => { s.runs.push(copy(NEW_RUN)); });
  await app.reply(ok(next));
  assert.equal(text(app.sr()), "Updated at 4:28 PM. 755K tokens, $0.94 estimated cost. 1 agent started.", "a real new run in that session is announced");
});

// ---------------------------------------------------------------- markup safety

test("flow: names from the payload stay text, no style attribute is set and no markup is parsed", async () => {
  const app = boot();
  app.start();
  const payload = fixture("flow_busy");
  const run = payload.session.runs.find((r) => r.run_id === SC1);
  run.agent = "<img src=x onerror=alert(1)>";
  run.route_key = "<img src=x onerror=alert(1)>";
  payload.session.runs.find((r) => r.run_id === JD).model_display = "<b>big</b>";
  await app.reply(ok(payload));
  assert.ok(text(flowCard(app)).includes("<img src=x onerror=alert(1)>"));
  assert.equal(byTag(flowCard(app), "img").length, 0);
  assert.equal(byTag(flowCard(app), "b").length, 0);
  assert.deepEqual(parsed, []);
  assert.ok(flowCard(app).find((n) => n.attrs && n.attrs.has("style")).length === 0, "geometry goes through setProperty only");
});

test("flow: the card reads no field a run does not define, and tolerates a run with missing parts", async () => {
  const app = boot();
  app.start();
  const payload = fixture("flow_busy");
  payload.session.runs.push({ run_id: "bad00000000b", route_key: "ghost", parent: "nobody", parent_known: true, dispatch_order: 8, state: "idle" });
  payload.session.runs.push({ run_id: "bad00000000c", route_key: "loop", parent: "bad00000000d", parent_known: true, dispatch_order: 9, state: "idle" });
  payload.session.runs.push({ run_id: "bad00000000d", route_key: "loop", parent: "bad00000000c", parent_known: true, dispatch_order: 10, state: "idle" });
  payload.session.runs.push(null);
  payload.session.runs.push({ nothing: true });
  await app.reply(ok(payload));
  assert.equal(cards(app).length, 11, "an unknown dispatcher and a cycle both hang off the main session");
  assert.equal(px(cardOf(app, "bad00000000b")).left, "380px");
  assert.equal(px(cardOf(app, "bad00000000c")).left, "380px");
  assert.equal(px(cardOf(app, "bad00000000d")).left, "736px", "a cycle is cut where it closes: one of the two hangs off the other");
  assert.ok(!text(flowCard(app)).includes("NaN") && !text(flowCard(app)).includes("undefined"));
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

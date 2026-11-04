// Browser-free checks of the Live page, run by tests/test_live_js.py. They load pages/live.js, live_poll.js and the
// shared modules from dashboard/static/js against the small fake DOM in fakedom.mjs, with fake timers and a fake
// tab visibility. Nothing here opens a browser or a socket. The payloads are the hand-written files in
// tests/fixtures/live, named by MR_LIVE_FIXTURES, and the run reads times in America/New_York (the TZ the wrapper sets).
// A failed check prints its name and the reason, and the exit code is 1.
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
const { createLivePoller, POLL_MS, RETRY_MS } = await import(JS + "live_poll.js");
const { createApi } = await import(JS + "api.js");
const { createShell } = await import(JS + "shell.js");

// The setter below catches any attempt to parse text as markup.
const parsed = [];
Object.defineProperty(FElement.prototype, "innerHTML", { set(v) { parsed.push(String(v)); }, get() { return ""; } });
Object.defineProperty(FElement.prototype, "outerHTML", { set(v) { parsed.push(String(v)); }, get() { return ""; } });

const SID1 = "c57d41c0-3a1e-4b7a-9d52-6a8f0e1b2c34";
const SID2 = "8e22b6f1-9c4d-4e0a-b1f7-52d3a7c9e610";
const KEY = "tidewater-reporting";

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
const fail = (status) => ({ ok: false, status, data: null });

// A clock that runs the timers the page and the poller set, in order.
function makeClock() {
  let now = 0;
  let seq = 0;
  const timers = new Map();
  return {
    get now() { return now; },
    set: (fn, wait) => { seq += 1; timers.set(seq, { at: now + wait, fn }); return seq; },
    clear: (id) => { timers.delete(id); },
    count: () => timers.size,
    nextIn: () => (timers.size ? Math.min(...[...timers.values()].map((x) => x.at)) - now : null),
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

// A Live page on the fake DOM. The server is a queue of pending requests that a check answers one by one.
function boot({ key = KEY } = {}) {
  const page = createPage();
  const section = page.sections.live;
  const clock = makeClock();
  const vis = { on: true, fn: null };
  const calls = [];
  const pending = [];
  // The one-second ticker is separate from the timers, so a check fires it by hand with app.tick().
  const ticker = { seq: 0, fns: new Map(), started: 0, stopped: 0 };
  const env = {
    setTimer: clock.set,
    clearTimer: clock.clear,
    startTick: (fn) => { ticker.seq += 1; ticker.started += 1; ticker.fns.set(ticker.seq, fn); return ticker.seq; },
    stopTick: (id) => { if (ticker.fns.delete(id)) ticker.stopped += 1; },
    now: () => clock.now,
    isVisible: () => vis.on,
    listenVisibility: (fn) => { vis.fn = fn; return () => { vis.fn = null; }; },
  };
  const live = createLive(env);
  const makeCtx = (k) => ({
    route: { name: "live", params: {}, query: { project: k } },
    project: { key: k, name: k === "all" ? "All projects" : "Tidewater reporting" },
    transcriptsDir: "~/.claude/projects",
    hashFor: (name, params, patch) => router.hashFor(name, params, Object.assign({ project: k }, patch)),
    live: (project, session, etag) => {
      calls.push({ key: project, session, etag });
      return new Promise((resolve) => { pending.push(resolve); });
    },
  });
  const app = {
    page, section, clock, live, vis, calls, pending, ticker, ctx: makeCtx(key),
    ticking: () => ticker.fns.size,
    tick() { for (const fn of [...ticker.fns.values()]) fn(); },
    // The order handle() in app.js uses: setActive first, then render.
    start() { live.setActive(true, app.ctx); live.render(section, app.ctx); },
    go(next) { app.ctx = makeCtx(next); live.setActive(true, app.ctx); live.render(section, app.ctx); },
    leave() { live.setActive(false, app.ctx); },
    async reply(res) {
      assert.ok(pending.length > 0, "a request is waiting for an answer");
      pending.shift()(res);
      await settle();
    },
    state: () => section.getAttribute("data-live"),
    control: () => one(section, "lv-ctl"),
    button: () => byTag(one(section, "lv-ctl"), "button")[0],
    pill: () => one(section, "lv-pill"),
    sr: () => section.childNodes[0],
    kpis: () => byClass(section, "kpi"),
    kpiValues: () => byClass(section, "kpi").map((k) => text(byClass(k, "kpi-v")[0])),
    kpiLines: () => byClass(section, "kpi").map((k) => text(byClass(k, "lv-since")[0])),
    tbody: () => byTag(one(section, "lv-req"), "tbody")[0],
    rows: () => byTag(byTag(one(section, "lv-req"), "tbody")[0], "tr"),
    agents: () => byClass(section, "lv-ag"),
    fresh: () => section.find((n) => hasClass(n, "lv-fresh") || hasClass(n, "lv-tick")),
  };
  return app;
}

const withTime = (payload, iso) => Object.assign(copy(payload), { server_time: iso });

// ---------------------------------------------------------------- the states

test("live: the header, the control and the session line", async () => {
  const app = boot();
  app.start();
  assert.equal(app.state(), "wait");
  assert.equal(app.calls.length, 1, "the first request goes at once");
  await app.reply(ok(fixture("live")));
  assert.equal(app.state(), "live");
  assert.equal(text(byTag(app.section, "h1")[0]), "Live");
  assert.equal(text(one(app.section, "intro")), "The latest session in Tidewater reporting, minute by minute.");
  const sess = one(app.section, "lv-sess");
  assert.equal(sess.hidden, false);
  const words = text(sess);
  assert.ok(words.includes("Working"), words);
  assert.ok(words.includes("Session from October 30, 4:01 PM"), words);
  assert.ok(words.includes("feature/quarter-close"), words);
  assert.ok(words.includes("Started 4:01 PM · 23 min"), words);
  const link = byClass(sess, "lnk")[0];
  assert.equal(link.getAttribute("href"), "#/sessions/" + SID1 + "?project=" + KEY, "the session detail route");
  assert.equal(app.pill().hidden, true, "live has no pill");
  assert.equal(text(one(app.section, "lv-time")), "Last request 3 s ago", "the header shows the age of the newest request");
  assert.equal(text(app.button()), "Pause");
  assert.equal(one(app.section, "lv-gone").hidden, true);
  assert.equal(one(app.section, "lv-lost-nt").hidden, true);
  assert.equal(byTag(sess, "select").length, 0, "one session, no select");
});

test("live: four KPI tiles, each with one line", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("live")));
  assert.equal(app.kpis().length, 4);
  assert.deepEqual(byClass(app.section, "tl-l").map(text), ["Tokens", "Estimated cost", "Cache hit rate", "Requests"]);
  assert.deepEqual(app.kpiValues(), ["755K", "$0.94", "79%", "24"]);
  assert.deepEqual(app.kpiLines(), ["+30K in the last minute", "+$0.02 in the last minute", "64% in the last minute", "2 in the last minute"]);
  const lines = byClass(app.section, "lv-since");
  assert.ok(hasClass(lines[2], "lv-plain"), "the hit rate line is plain");
  assert.ok(lines.every((l) => !hasClass(l, "lv-zero")));
});

test("live: KPI lines for nothing, a tiny cost and an unpriced total", async () => {
  const app = boot();
  app.start();
  const tiny = fixture("live");
  tiny.session.last_minute = { tokens: 0, cost: 0, unpriced_requests: 0, hit_rate: null, requests: 0 };
  tiny.session.totals.hit_rate = null;
  await app.reply(ok(tiny));
  assert.deepEqual(app.kpiLines(), ["None in the last minute", "None in the last minute", "None in the last minute", "None in the last minute"]);
  assert.ok(byClass(app.section, "lv-since").every((l) => hasClass(l, "lv-zero")));
  assert.equal(app.kpiValues()[2], "0%", "a null hit rate shows the placeholder the other pages use");
  await app.clock.advance(POLL_MS);
  const small = withTime(fixture("live"), "2026-10-30T16:24:50-04:00");
  small.etag = "aaaaaaaaaaaaaaaa";
  small.session.last_minute.cost = 0.003;
  small.session.totals.cost = 0;
  small.session.totals.unpriced_requests = 3;
  await app.reply(ok(small));
  assert.equal(app.kpiLines()[1], "Under $0.01 in the last minute");
  assert.equal(app.kpiValues()[1], "Not priced", "a zero total with unpriced requests reads Not priced");
});

test("live: the chart has 30 columns by model, a legend with totals, y ticks and x labels", async () => {
  const app = boot();
  app.start();
  const payload = fixture("live");
  await app.reply(ok(payload));
  const main = one(app.section, "lv-main");
  const svg = one(main, "dbars");
  assert.equal(svg.getAttribute("role"), "img");
  assert.equal(svg.getAttribute("aria-label"), STRINGS.live_chart_sr);
  const drawn = byClass(svg, "col").filter((r) => parseFloat(r.styleMap.height) > 0);
  const want = payload.session.minutes.reduce((n, m) => n + Object.values(m.by_model).filter((v) => v > 0).length, 0);
  assert.equal(drawn.length, want, "one rect per minute and model with tokens");
  assert.ok(byClass(svg, "cat-1").length > 0 && byClass(svg, "cat-2").length > 0 && byClass(svg, "cat-3").length > 0);
  const other = byClass(svg, "cat-other");
  assert.ok(other.length > 0, "a model outside the catalog draws hatched");
  assert.ok(other.every((r) => /^url\(#oth-live-\d+\)$/.test(r.getAttribute("fill"))));
  const columns = new Set(drawn.map((r) => r.getAttribute("x")));
  assert.ok(columns.size <= 30);
  assert.deepEqual(byTag(one(main, "dy"), "span").map(text), ["20K", "10K", "0"], "the main chart's ticks follow the axis over new tokens");
  assert.equal(byClass(main, "dx").length, 0, "the x labels moved under the lane");
  const lane = one(app.section, "lv-lane");
  assert.deepEqual(byTag(one(lane, "dx"), "span").map(text), ["3:59", "4:04", "4:09", "4:14", "4:19", "Now"]);
  assert.equal(one(app.section, "lv-now-x").styleMap.left, "98.33%", "Now sits at the right edge");
  const legend = byTag(one(one(app.section, "lv-row-h"), "klg"), "li");
  assert.equal(legend.length, payload.session.by_model.length);
  assert.ok(text(legend[0]).startsWith("Opus 5.5 "), text(legend[0]));
  assert.ok(text(legend[legend.length - 1]).startsWith("acme-test-model-1 "), text(legend[legend.length - 1]));
  assert.ok(hasClass(byClass(legend[legend.length - 1], "swatch")[0], "cat-other"));
  assert.equal(byClass(legend[0], "swatch")[0].getAttribute("aria-hidden"), "true");
  assert.equal(text(byClass(legend[0], "muted")[0]), format.fmtTokens(payload.session.by_model[0].tokens));
});

test("live: agents show their name, model, effort, pill and last request", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("live")));
  const rows = app.agents();
  assert.equal(rows.length, 3);
  assert.deepEqual(rows.map((r) => text(byClass(r, "lv-ag-n")[0])), ["Main session", "reviewer", "scribe"]);
  assert.deepEqual(rows.map((r) => text(byClass(r, "lv-ag-m")[0])), ["Opus 5.5 · high", "Sonnet 5.5 · xhigh", "acme-test-model-1 · high"]);
  assert.deepEqual(rows.map((r) => text(byClass(r, "lv-act")[0])), ["Idle", "Working", "Working"]);
  assert.deepEqual(rows.map((r) => byClass(r, "lv-act")[0].getAttribute("data-a")), ["idle", "working", "working"]);
  assert.deepEqual(rows.map((r) => text(byClass(r, "lv-ag-last")[0])), ["Last request 3 min ago", "Last request 3 s ago", "Last request 27 s ago"]);
  assert.deepEqual(rows.map((r) => text(byClass(r, "lv-ag-v")[0])), ["503K", "220K", "32K"]);
  assert.equal(byTag(byClass(rows[0], "lv-bar")[0], "span")[0].styleMap.width, "100.00%");
  assert.equal(text(byClass(rows[0], "lv-ag-last")[0]).includes("{"), false);
});

test("live: eight request rows with a New marker, an unpriced row and the footer", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("live")));
  const rows = app.rows();
  assert.equal(rows.length, 8);
  assert.deepEqual(byTag(one(app.section, "lv-req"), "th").map(text),
    ["Time", "Agent", "Model", "Effort", "Tokens", "Cache read", "Output", "Estimated cost"]);
  assert.equal(byClass(app.section, "lv-new").length, 2, "two requests are under 30 seconds old");
  const cells = (row) => byTag(row, "td").map(text);
  assert.deepEqual(cells(rows[0]), ["4:24:41New", "reviewer", "Sonnet 5.5", "xhigh", "23K", "20K", "360", "$0.02"]);
  assert.deepEqual(cells(rows[1]), ["4:24:17New", "scribe", "acme-test-model-1", "high", "6,200", "5,100", "225", "Not priced"]);
  assert.deepEqual(cells(rows[2]).slice(0, 2), ["4:23:31", "scribe"]);
  assert.equal(cells(rows[5])[1], "Main session");
  assert.equal(byClass(rows[0], "lv-new").length, 1);
  assert.equal(text(byClass(rows[0], "lv-new")[0]), "New");
  assert.equal(byTag(rows[0], "td")[2].classList.contains("lv-hide-s"), true, "model hides at 375");
  assert.deepEqual(byTag(one(app.section, "lv-req"), "th").map((n) => hasClass(n, "lv-hide-s")), [false, false, true, true, false, true, true, false]);
  assert.deepEqual(byTag(rows[0], "td").map((n) => hasClass(n, "lv-hide-s")), [false, false, true, true, false, true, true, false], "the Cache read cell hides at 375 too");
  assert.equal(byTag(rows[0], "td")[5].getAttribute("data-l"), "Cache read");
  assert.equal(text(one(app.section, "est")), "Estimated at API list price");
  assert.equal(text(one(app.section, "foot")).startsWith("Read from the transcripts in ~/.claude/projects every second while this tab is in view"), true);
  assert.ok(text(one(app.section, "foot")).endsWith(STRINGS.live_hidden_note));
});

test("live: more than eight requests show eight", async () => {
  const app = boot();
  app.start();
  const payload = fixture("live");
  for (let i = 0; i < 6; i += 1) payload.session.requests.push(Object.assign(copy(payload.session.requests[7]), { id: "00000000000" + i }));
  assert.equal(payload.session.requests.length, 14);
  await app.reply(ok(payload));
  assert.equal(app.rows().length, 8);
});

test("idle: the last request time, no New marker and idle pills", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("idle")));
  assert.equal(app.state(), "idle");
  const sess = one(app.section, "lv-sess");
  assert.ok(text(sess).includes("Idle"));
  assert.ok(text(sess).includes("Last request at 4:24 PM"), text(sess));
  assert.ok(!text(sess).includes("Started"));
  assert.ok(!text(sess).includes("Ended"));
  assert.equal(text(one(app.section, "lv-time")), "Last request 27 min ago");
  assert.equal(app.pill().hidden, true);
  assert.equal(byClass(app.section, "lv-new").length, 0);
  assert.deepEqual(app.agents().map((r) => text(byClass(r, "lv-act")[0])), ["Idle", "Idle", "Idle"]);
  assert.equal(text(byClass(app.agents()[0], "lv-ag-last")[0]), "Last request 30 min ago");
  assert.deepEqual(app.kpiLines(), Array(4).fill("None in the last minute"));
  assert.equal(app.rows().length, 8);
  assert.equal(text(app.button()), "Pause");
});

test("empty: one card with a link to today's Sessions, and the control stays", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("empty")));
  assert.equal(app.state(), "empty");
  assert.equal(text(one(app.section, "es-h")), "No recent session in Tidewater reporting");
  assert.equal(text(one(app.section, "es-t")), STRINGS.live_empty_t);
  const link = byClass(app.section, "btn").find((n) => n.tagName === "a");
  assert.equal(text(link), "See recent sessions");
  assert.equal(link.getAttribute("href"), "#/sessions?project=" + KEY + "&range=today");
  assert.equal(one(app.section, "lv-sess").hidden, true);
  assert.equal(app.button().hidden, false);
  assert.equal(text(app.button()), "Pause");
  assert.equal(byClass(app.section, "kpi").length, 0);
  assert.equal(app.clock.count(), 1, "it keeps polling");
});

test("pick: All projects shows the pick card and fetches nothing", async () => {
  const app = boot({ key: "all" });
  app.start();
  assert.equal(app.state(), "pick");
  assert.equal(app.calls.length, 0);
  assert.equal(app.clock.count(), 0);
  assert.equal(app.vis.fn, null, "no visibility listener while nothing is polled");
  assert.equal(text(one(app.section, "cd-h")), STRINGS.s_pick_project_h);
  assert.equal(text(one(app.section, "es-t")), STRINGS.s_pick_project_t);
  assert.equal(text(byTag(one(app.section, "es"), "button")[0]), STRINGS.s_pick_project_btn);
  assert.equal(app.button().hidden, true);
  await app.clock.advance(60000);
  assert.equal(app.calls.length, 0);
});

test("unknown: a 404 or 400 shows the card and never asks again", async () => {
  for (const status of [404, 400]) {
    const app = boot();
    app.start();
    await app.reply(fail(status));
    assert.equal(app.state(), "unknown", String(status));
    assert.equal(text(one(app.section, "cd-h")), STRINGS.live_unknown_h);
    assert.equal(text(one(app.section, "es-t")), STRINGS.live_unknown_t);
    assert.equal(text(byTag(one(app.section, "es"), "button")[0]), STRINGS.s_pick_project_btn);
    assert.equal(app.clock.count(), 0, "no retry timer");
    await app.clock.advance(120000);
    assert.equal(app.calls.length, 1, "no retry loop");
  }
});

test("unreadable: the transcripts state with the path", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("unreadable")));
  assert.equal(app.state(), "unreadable");
  assert.equal(text(one(app.section, "cd-h")), STRINGS.s_transcripts_h);
  assert.ok(text(one(app.section, "es-t")).includes("~/.claude/projects"));
  assert.equal(text(one(app.section, "es-t")), format.t("s_transcripts_t", { path: "~/.claude/projects" }));
});

// ---------------------------------------------------------------- lost, paused, retry

test("lost: status 0, a 5xx and an unparsable body show Not updating and keep the last data", async () => {
  for (const res of [fail(0), fail(503), fail(200)]) {
    const app = boot();
    app.start();
    await app.reply(ok(fixture("live")));
    await app.clock.advance(POLL_MS);
    await app.reply(res);
    assert.equal(app.state(), "lost", JSON.stringify(res));
    assert.equal(text(app.pill()), "Not updating");
    assert.equal(app.pill().getAttribute("data-s"), "lost");
    assert.equal(app.pill().hidden, false);
    assert.equal(byClass(app.pill(), "lv-mk").length, 1, "the pill carries its mark");
    assert.equal(text(one(app.section, "lv-time")), "Updated 4:24 PM", "the time of the last good answer");
    assert.equal(text(app.button()), "Try now");
    const notice = one(app.section, "lv-lost-nt");
    assert.equal(notice.hidden, false);
    assert.equal(notice.getAttribute("role"), "status");
    assert.equal(text(notice), "The dashboard server isn't answering, so the page tries again every 10 seconds.");
    assert.equal(app.rows().length, 8, "the last good data stays drawn");
  }
});

test("lost: it retries every 10 seconds, Try now asks at once and a good answer clears it", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("live")));
  await app.clock.advance(POLL_MS);
  await app.reply(fail(0));
  assert.equal(app.calls.length, 2);
  await app.clock.advance(RETRY_MS - 1);
  assert.equal(app.calls.length, 2, "not before 10 seconds");
  await app.clock.advance(1);
  assert.equal(app.calls.length, 3);
  await app.reply(fail(0));
  assert.equal(app.state(), "lost");
  app.button().click();
  assert.equal(app.calls.length, 4, "Try now fetches at once");
  assert.equal(app.pending.length, 1, "one request in flight");
  await app.reply(ok(fixture("unchanged")));
  assert.equal(app.state(), "live");
  assert.equal(app.pill().hidden, true);
  assert.equal(one(app.section, "lv-lost-nt").hidden, true);
  assert.equal(app.clock.nextIn(), POLL_MS, "back to the normal pace");
});

test("lost: before any answer the page shows Not updating over the empty cards", async () => {
  const app = boot();
  app.start();
  await app.reply(fail(0));
  assert.equal(app.state(), "lost");
  assert.equal(text(app.pill()), "Not updating");
  assert.equal(app.kpis().length, 4);
  assert.equal(app.rows().length, 8, "the table keeps its height");
});

test("paused: Pause stops the requests, shows the pill and As of, and Resume fetches at once", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("live")));
  assert.equal(text(app.button()), "Pause");
  app.button().click();
  assert.equal(app.state(), "paused");
  assert.equal(text(app.pill()), "Paused");
  assert.equal(app.pill().getAttribute("data-s"), "paused");
  assert.equal(text(one(app.section, "lv-time")), "As of 4:24 PM");
  assert.equal(text(app.button()), "Resume");
  assert.equal(app.clock.count(), 0);
  await app.clock.advance(60000);
  assert.equal(app.calls.length, 1, "no request while paused");
  app.button().click();
  assert.equal(app.calls.length, 2, "Resume fetches at once");
  await app.reply(ok(fixture("unchanged")));
  assert.equal(app.state(), "live");
  assert.equal(app.pill().hidden, true);
  assert.equal(text(app.button()), "Pause");
});

test("paused: the button keeps focus across states because it is one element", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("live")));
  const button = app.button();
  button.focus();
  button.click();
  assert.equal(app.button(), button);
  assert.equal(FElement.focused, button);
});

// ---------------------------------------------------------------- the poller

test("poll: one request per POLL_MS, never two requests in flight", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("live")));
  assert.equal(app.calls.length, 1);
  assert.equal(app.clock.nextIn(), POLL_MS);
  await app.clock.advance(POLL_MS - 1);
  assert.equal(app.calls.length, 1);
  await app.clock.advance(1);
  assert.equal(app.calls.length, 2);
  await app.clock.advance(30000);
  assert.equal(app.calls.length, 2, "the answer is still out, so nothing else goes");
  assert.equal(app.pending.length, 1);
  await app.reply(ok(fixture("unchanged")));
  assert.equal(app.clock.nextIn(), POLL_MS, "the next one is one poll after the answer");
});

test("poll: the session is sticky and the etag of the last full answer is sent", async () => {
  const app = boot();
  app.start();
  assert.deepEqual(app.calls[0], { key: KEY, session: null, etag: null });
  await app.reply(ok(fixture("live")));
  await app.clock.advance(POLL_MS);
  assert.deepEqual(app.calls[1], { key: KEY, session: SID1, etag: "4f2a9c01b7d3e856" });
  await app.reply(ok(fixture("unchanged")));
  await app.clock.advance(POLL_MS);
  assert.deepEqual(app.calls[2], { key: KEY, session: SID1, etag: "4f2a9c01b7d3e856" }, "an unchanged answer keeps both");
  const next = withTime(fixture("live"), "2026-10-30T16:25:00-04:00");
  next.etag = "0123456789abcdef";
  await app.reply(ok(next));
  await app.clock.advance(POLL_MS);
  assert.equal(app.calls[3].etag, "0123456789abcdef");
  assert.equal(app.calls[3].session, SID1);
});

test("poll: a hidden tab stops polling and coming back fetches at once", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("live")));
  assert.equal(app.clock.count(), 1);
  app.vis.on = false;
  app.vis.fn();
  assert.equal(app.clock.count(), 0, "the timer is gone");
  await app.clock.advance(120000);
  assert.equal(app.calls.length, 1);
  app.vis.on = true;
  app.vis.fn();
  assert.equal(app.calls.length, 2, "an immediate fetch");
  await app.reply(ok(fixture("unchanged")));
  assert.equal(app.clock.nextIn(), POLL_MS);
});

test("poll: leaving the page stops it and coming back fetches at once", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("live")));
  app.leave();
  assert.equal(app.clock.count(), 0);
  assert.equal(app.vis.fn, null);
  await app.clock.advance(60000);
  assert.equal(app.calls.length, 1);
  app.start();
  assert.equal(app.calls.length, 2);
  assert.ok(app.vis.fn, "listening again");
});

test("poll: a new project starts clean and an answer still on its way is dropped", async () => {
  const app = boot({ key: "alpha" });
  app.start();
  assert.equal(app.calls.length, 1);
  app.go("beta");
  assert.equal(app.state(), "wait");
  assert.equal(app.calls.length, 1, "the old request is still out, so no second one");
  await app.reply(ok(fixture("live")));
  assert.equal(app.state(), "wait", "the old answer is not drawn");
  assert.equal(app.calls.length, 2);
  assert.deepEqual(app.calls[1], { key: "beta", session: null, etag: null });
});

test("poll: from All projects to a project fetches with no session", async () => {
  const app = boot({ key: "all" });
  app.start();
  app.go(KEY);
  assert.equal(app.state(), "wait");
  assert.deepEqual(app.calls, [{ key: KEY, session: null, etag: null }]);
});

test("poller: a 4xx ends in unknown, a 5xx in lost, and the modes are reported once", async () => {
  const clock = makeClock();
  const states = [];
  const answers = [];
  const replies = [ok(fixture("live")), fail(500), fail(500), fail(404)];
  const poller = createLivePoller({
    fetchLive: () => Promise.resolve(replies.shift()),
    setTimer: clock.set, clearTimer: clock.clear, isVisible: () => true,
    onAnswer: (a) => answers.push(a), onState: (m) => states.push(m),
  });
  poller.setActive(true);
  await settle();
  assert.equal(answers.length, 1);
  assert.equal(poller.session(), SID1);
  assert.equal(poller.etag(), "4f2a9c01b7d3e856");
  await clock.advance(POLL_MS);
  assert.deepEqual(states, ["lost"]);
  await clock.advance(RETRY_MS);
  assert.deepEqual(states, ["lost"], "still lost, so no second report");
  await clock.advance(RETRY_MS);
  assert.deepEqual(states, ["lost", "unknown"]);
  assert.equal(clock.count(), 0);
});

// ---------------------------------------------------------------- unchanged, changed, flash, announce

test("unchanged: the DOM stays, nothing flashes and the relative times move", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("live")));
  assert.equal(app.fresh().length, 0, "the first answer flashes nothing");
  const before = {
    tbody: app.tbody(), rows: app.rows(), kpis: app.kpiValues(), values: byClass(app.section, "kpi-v"),
    time: one(app.section, "lv-time"), sess: one(app.section, "lv-sess"), agents: app.agents(),
  };
  assert.equal(text(byClass(before.agents[1], "lv-ag-last")[0]), "Last request 3 s ago");
  await app.clock.advance(POLL_MS);
  const later = fixture("unchanged");
  later.server_time = "2026-10-30T16:25:20-04:00";
  await app.reply(ok(later));
  assert.equal(app.tbody(), before.tbody);
  app.rows().forEach((row, i) => assert.equal(row, before.rows[i], "same row nodes"));
  assert.deepEqual(app.kpiValues(), before.kpis);
  byClass(app.section, "kpi-v").forEach((n, i) => assert.equal(n, before.values[i]));
  assert.equal(one(app.section, "lv-time"), before.time, "the update time node is not replaced");
  assert.equal(app.fresh().length, 0, "no flash and no blink on an unchanged answer");
  assert.equal(text(byClass(app.agents()[1], "lv-ag-last")[0]), "Last request 39 s ago", "the relative time moved");
  assert.equal(byClass(app.section, "lv-new").length, 0, "the New markers ran out");
  assert.equal(text(one(app.section, "lv-time")), "Last request 39 s ago");
  assert.equal(app.state(), "live");
});

test("unchanged: the page turns idle 60 seconds after the last request, from server_time", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("live")));
  await app.clock.advance(POLL_MS);
  const later = fixture("unchanged");
  later.server_time = "2026-10-30T16:25:41-04:00";
  await app.reply(ok(later));
  assert.equal(app.state(), "live", "exactly 60 seconds is still working");
  await app.clock.advance(POLL_MS);
  later.server_time = "2026-10-30T16:25:42-04:00";
  await app.reply(ok(later));
  assert.equal(app.state(), "idle");
  assert.ok(text(one(app.section, "lv-sess")).includes("Last request at 4:24 PM"));
  assert.deepEqual(app.agents().map((r) => text(byClass(r, "lv-act")[0])), ["Idle", "Idle", "Idle"]);
  assert.equal(app.fresh().length, 0);
});

test("changed: only the new row, the changed values and the update time flash", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("live")));
  const oldTime = one(app.section, "lv-time");
  const oldRows = app.rows();
  await app.clock.advance(POLL_MS);
  const next = withTime(fixture("live"), "2026-10-30T16:24:47-04:00");
  next.etag = "ffeeddccbbaa9988";
  const added = Object.assign(copy(next.session.requests[0]), { id: "ffffffffffff", ts: "2026-10-30T16:24:46-04:00", tokens: 9100 });
  next.session.requests = [added].concat(next.session.requests.slice(0, 7));
  next.session.totals.tokens = 764100;
  next.session.totals.requests = 25;
  await app.reply(ok(next));
  const flashed = app.fresh();
  const rows = app.rows();
  assert.equal(rows.length, 8);
  assert.equal(text(byTag(rows[0], "td")[4]), "9,100");
  assert.ok(hasClass(rows[0], "lv-fresh"), "the new row flashes");
  assert.equal(rows.filter((r) => hasClass(r, "lv-fresh")).length, 1, "and only that row");
  rows.slice(1).forEach((r, i) => assert.equal(r, oldRows[i], "an old row keeps its node"));
  const values = byClass(app.section, "kpi-v");
  assert.deepEqual(values.map((v) => hasClass(v, "lv-fresh")), [true, false, false, true], "tokens and requests changed");
  assert.deepEqual(app.kpiValues(), ["764K", "$0.94", "79%", "25"]);
  const time = one(app.section, "lv-time");
  assert.notEqual(time, oldTime, "the update time is a new node, so it blinks once");
  assert.ok(hasClass(time, "lv-tick"));
  assert.equal(flashed.length, 4, "two values, one row, the time");
  assert.equal(byClass(app.section, "lv-new").length, 3, "the new row and the two requests within 30 seconds of server_time");
});

test("changed: the chart columns are updated in place", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("live")));
  const before = byClass(app.section, "col");
  await app.clock.advance(POLL_MS);
  const next = withTime(fixture("live"), "2026-10-30T16:24:50-04:00");
  next.etag = "1212121212121212";
  const last = next.session.minutes[29];
  last.by_model[Object.keys(last.by_model)[0]] += 20000;
  last.tokens += 20000;
  await app.reply(ok(next));
  const after = byClass(app.section, "col");
  before.forEach((rect) => assert.ok(after.includes(rect), "a column keeps its node, so its height can move with a transition"));
  assert.ok(after.length >= before.length);
});

test("announce: at most once a minute, on a changed answer only", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("live")));
  const sr = app.sr();
  assert.equal(sr.getAttribute("role"), "status");
  assert.equal(sr.getAttribute("aria-live"), "polite");
  assert.ok(hasClass(sr, "sr"), "visually hidden");
  assert.equal(text(sr), "Updated at 4:24 PM. 755K tokens, $0.94 estimated cost.");
  const change = (iso, tokens, etag) => {
    const next = withTime(fixture("live"), iso);
    next.etag = etag;
    next.session.totals.tokens = tokens;
    return next;
  };
  await app.clock.advance(POLL_MS);
  await app.reply(ok(change("2026-10-30T16:24:47-04:00", 760000, "a1a1a1a1a1a1a1a1")));
  assert.equal(text(sr), "Updated at 4:24 PM. 755K tokens, $0.94 estimated cost.", "one poll later: nothing new is read");
  await app.clock.advance(POLL_MS);
  await app.reply(ok(fixture("unchanged")));
  assert.equal(text(sr), "Updated at 4:24 PM. 755K tokens, $0.94 estimated cost.");
  await app.clock.advance(60000 - POLL_MS * 2);
  await app.reply(ok(change("2026-10-30T16:25:44-04:00", 800000, "b2b2b2b2b2b2b2b2")));
  assert.equal(text(sr), "Updated at 4:25 PM. 800K tokens, $0.94 estimated cost.", "a minute on, the change is read");
});

// ---------------------------------------------------------------- sessions

test("session select: two running sessions give a Session select, and a pick is sent and kept", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("two_running")));
  const select = byTag(one(app.section, "lv-sess"), "select")[0];
  assert.ok(select, "a select in the session line");
  const options = byTag(select, "option");
  assert.deepEqual(options.map(text), ["Session from October 30, 4:01 PM · feature/quarter-close", "Session from October 30, 4:12 PM · fix/ledger-rounding"]);
  assert.equal(select.value, SID1);
  assert.equal(text(byTag(one(app.section, "lv-pick"), "label")[0]), "Session");
  select.focus();
  await app.clock.advance(POLL_MS);
  await app.reply(ok(fixture("unchanged")));
  assert.equal(byTag(one(app.section, "lv-sess"), "select")[0], select, "the select is not rebuilt while the list holds");
  assert.equal(FElement.focused, select, "and keeps focus");
  await app.clock.advance(POLL_MS);
  const before = app.calls.length;
  select.value = SID2;
  select.dispatch("change");
  assert.equal(app.pending.length, 1);
  assert.equal(app.calls.length, before, "the answer on its way is for the old choice");
  await app.reply(ok(fixture("unchanged")));
  assert.equal(app.calls[app.calls.length - 1].session, SID2, "the pick goes as session=");
  assert.equal(app.calls[app.calls.length - 1].etag, null, "with no etag");
  assert.equal(app.fresh().length, 0, "a switch of session flashes nothing");
  app.go("all");
  assert.equal(app.state(), "pick");
  app.go(KEY);
  assert.equal(app.calls[app.calls.length - 1].session, SID2, "the pick is kept for the project");
});

test("all projects from an idle poller: no request goes out for project all", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("live")));
  assert.equal(app.pending.length, 0, "nothing in flight before the switch");
  app.go("all");
  assert.equal(app.state(), "pick");
  assert.ok(app.calls.every((c) => c.key !== "all"), "never asks for project all");
  await app.clock.advance(POLL_MS * 4);
  assert.ok(app.calls.every((c) => c.key !== "all"), "and the timer does not either");
});

test("session gone: a muted line, and the page moves to the fallback session", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("live")));
  await app.clock.advance(POLL_MS);
  await app.reply(ok(fixture("session_gone")));
  const note = one(app.section, "lv-gone");
  assert.equal(note.hidden, false);
  assert.equal(text(note), STRINGS.live_session_gone);
  assert.ok(hasClass(note, "muted"));
  assert.ok(text(one(app.section, "lv-sess")).includes("fix/ledger-rounding"));
  assert.equal(app.fresh().length, 0, "the move flashes nothing");
  await app.clock.advance(POLL_MS);
  assert.equal(app.calls[app.calls.length - 1].session, SID2, "the next request asks for the new session");
  const settled = fixture("session_gone");
  settled.session_gone = false;
  settled.etag = "9999999999999999";
  await app.reply(ok(settled));
  assert.equal(one(app.section, "lv-gone").hidden, false, "the line stays until the viewer moves on");
  app.go("all");
  app.go(KEY);
  assert.equal(one(app.section, "lv-gone").hidden, true);
});

// ---------------------------------------------------------------- data and markup safety

test("no message-text-like field is read, and none reaches the page", async () => {
  const app = boot();
  app.start();
  const payload = fixture("live");
  const poison = { message_text: "POISON-1", content: "POISON-2", prompt: "POISON-3", cwd: "/POISON-4", transcript_path: "/POISON-5", text: "POISON-6", tool_input: "POISON-7" };
  Object.assign(payload.session, poison);
  Object.assign(payload, { message: "POISON-8" });
  payload.session.requests.forEach((r) => Object.assign(r, poison));
  payload.session.agents.forEach((a) => Object.assign(a, poison));
  payload.running.forEach((r) => Object.assign(r, poison));
  const read = new Set();
  const spy = (value) => new Proxy(value, {
    get(target, key, receiver) {
      if (typeof key === "string") read.add(key);
      const got = Reflect.get(target, key, receiver);
      return got && typeof got === "object" ? spy(got) : got;
    },
  });
  await app.reply(ok(spy(payload)));
  assert.equal(app.state(), "live");
  for (const key of [...Object.keys(poison), "message"]) assert.ok(!read.has(key), "the page read " + key);
  assert.ok(!text(app.section).includes("POISON"));
});

test("markup in data stays text, and no innerHTML is set", async () => {
  const app = boot();
  app.start();
  const payload = fixture("live");
  payload.session.branch = "<img src=x onerror=alert(1)>";
  payload.session.agents[1].agent = "<b>reviewer</b>";
  payload.session.agents[1].route_key = "<b>reviewer</b>";
  payload.session.requests[0].agent = "<i>x</i>";
  payload.session.requests[0].route_key = "<i>x</i>";
  await app.reply(ok(payload));
  assert.ok(text(app.section).includes("<img src=x onerror=alert(1)>"));
  assert.equal(byTag(app.section, "img").length, 0);
  assert.equal(byTag(app.section, "b").length, 0);
  assert.deepEqual(parsed, []);
});

// ---------------------------------------------------------------- the chart card: session bar, New tokens, cache lane, Now band

const KINDS = [["cache_read", "Cache read", "rk-1"], ["input", "Input", "rk-2"], ["cache_write", "Cache write", "rk-3"], ["output", "Output", "rk-4"]];
const laneRects = (app) => byClass(one(app.section, "lv-lane"), "lv-cr");
const mainBand = (app) => one(one(app.section, "lv-main"), "lv-nowband");
const laneBand = (app) => one(one(app.section, "lv-lane"), "lv-nowband");
const titleOf = (n) => text(byTag(n, "title")[0]);

test("session bar: one row by kind, segments and a legend of four totals", async () => {
  const app = boot();
  app.start();
  const payload = fixture("live");
  await app.reply(ok(payload));
  const meter = one(app.section, "lv-meter");
  assert.equal(byClass(meter, "sb-row").length, 1);
  assert.equal(text(one(meter, "sb-n")), STRINGS.live_kinds_h);
  assert.equal(text(one(meter, "sb-v")), "755K");
  const totals = payload.session.totals;
  const segs = byClass(meter, "sb-seg");
  assert.deepEqual(segs.map((n) => n.getAttribute("class").replace("sb-seg ", "")), KINDS.map((k) => k[2]));
  segs.forEach((seg, i) => {
    assert.equal(seg.styleMap.width, ((100 * totals[KINDS[i][0]]) / totals.tokens).toFixed(2) + "%");
    assert.equal(text(byClass(seg, "sr")[0]), KINDS[i][1] + " " + format.fmtTokens(totals[KINDS[i][0]]));
  });
  const legend = byTag(one(meter, "klg"), "li");
  assert.deepEqual(legend.map(text), KINDS.map((k) => k[1] + " " + format.fmtTokens(totals[k[0]])));
  assert.deepEqual(legend.map(text), ["Cache read 640K", "Input 41K", "Cache write 61K", "Output 13K"]);
  assert.equal(byClass(legend[0], "swatch")[0].getAttribute("aria-hidden"), "true");
});

test("session bar: a kind with nothing still shows in the legend, and a new answer rebuilds the bar", async () => {
  const app = boot();
  app.start();
  const zero = fixture("live");
  zero.session.totals.cache_read = 0;
  zero.session.totals.tokens = 115000;
  await app.reply(ok(zero));
  const meter = one(app.section, "lv-meter");
  assert.equal(byClass(meter, "sb-seg").length, 3, "no segment for a kind of zero");
  const legend = byTag(one(meter, "klg"), "li").map(text);
  assert.equal(legend.length, 4);
  assert.equal(legend[0], "Cache read 0");
  await app.clock.advance(POLL_MS);
  const next = withTime(fixture("live"), "2026-10-30T16:24:50-04:00");
  next.etag = "2323232323232323";
  await app.reply(ok(next));
  assert.equal(one(app.section, "lv-meter"), meter, "the wrapper stays");
  assert.equal(byClass(meter, "sb-seg").length, 4);
  assert.equal(byTag(one(meter, "klg"), "li").map(text)[0], "Cache read 640K");
});

test("chart: the New tokens head carries the model legend with new-token totals", async () => {
  const app = boot();
  app.start();
  const payload = fixture("live");
  await app.reply(ok(payload));
  const head = one(app.section, "lv-row-h");
  assert.equal(text(one(head, "lv-row-t")), STRINGS.live_new_h);
  assert.equal(head.childNodes[0], one(head, "lv-row-t"), "the label comes first");
  const legend = byTag(one(head, "klg"), "li");
  assert.deepEqual(legend.map(text), payload.session.by_model.map((m) => m.display_name + " " + format.fmtTokens(m.tokens)));
  assert.equal(text(legend[0]), "Opus 5.5 113K");
  assert.equal(text(one(app.section, "lv-note")), STRINGS.live_chart_note);
  assert.equal(text(one(one(app.section, "lv-lane-h"), "lv-row-t")), "Cache reads");
  assert.ok(hasClass(byClass(one(app.section, "lv-lane-h"), "swatch")[0], "rk-1"));
});

test("lane: one rect per minute with cache reads, a peak label and a title like the model bars", async () => {
  const app = boot();
  app.start();
  const payload = fixture("live");
  await app.reply(ok(payload));
  const lane = one(app.section, "lv-lane");
  const svg = one(lane, "lv-lane-svg");
  assert.equal(svg.getAttribute("viewBox"), "0 0 600 48");
  assert.equal(svg.getAttribute("aria-hidden"), "true");
  assert.equal(svg.getAttribute("preserveAspectRatio"), "none");
  const minutes = payload.session.minutes;
  const rects = laneRects(app);
  assert.equal(rects.length, minutes.filter((m) => m.cache_read > 0).length);
  const peak = Math.max(...minutes.map((m) => m.cache_read));
  assert.deepEqual(byTag(one(lane, "dy"), "span").map(text), [format.fmtTokens(peak), "0"]);
  assert.equal(text(byTag(one(lane, "dy"), "span")[0]), "66K");
  const tall = rects.filter((r) => r.getAttribute("height") === "46.00");
  assert.equal(tall.length, 2, "the two peak minutes (4:10 and 4:15) fill the lane minus its two units");
  assert.equal(tall[0].getAttribute("y"), "2.00");
  assert.equal(titleOf(tall[0]), "4:10 PM Cache reads 66K");
  assert.equal(tall[0].getAttribute("x"), "303.60");
  assert.equal(tall[0].getAttribute("width"), "12.80");
  assert.equal(tall[0].getAttribute("vector-effect"), "non-scaling-stroke");
  assert.ok(rects.every((r) => hasClass(r, "lv-cr") && !r.attrs.has("style")), "geometry is attributes, never a style attribute");
  assert.equal(byClass(svg, "base").length, 1);
  assert.equal(one(svg, "lv-nowband").parentNode, svg);
});

test("lane: a session with no cache reads draws the baseline and labels only 0", async () => {
  const app = boot();
  app.start();
  const payload = fixture("live");
  payload.session.minutes.forEach((m) => { m.cache_read = 0; });
  await app.reply(ok(payload));
  const lane = one(app.section, "lv-lane");
  assert.equal(laneRects(app).length, 0);
  assert.deepEqual(byTag(one(lane, "dy"), "span").map(text), ["0"]);
  assert.equal(byClass(lane, "base").length, 1);
  assert.ok(!text(lane).includes("NaN") && !text(lane).includes("Infinity"));
  assert.ok(byClass(lane, "lv-nowband").every((n) => !Number.isNaN(Number(n.getAttribute("height")))));
});

test("now band: it covers the current minute in the chart and the lane and stops above the bar", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("live")));
  const slot = (581.6).toFixed(1);
  for (const band of [mainBand(app), laneBand(app)]) {
    assert.equal(band.getAttribute("x"), slot);
    assert.equal(band.getAttribute("width"), "16.8");
    assert.equal(band.getAttribute("y"), "0");
    assert.equal(titleOf(band), "", "the minute has requests, so the band says nothing");
    assert.ok(!band.attrs.has("style"));
  }
  const bars = byClass(one(app.section, "lv-main"), "col").filter((r) => r.getAttribute("x") === "583.60" && parseFloat(r.styleMap.height) > 0);
  assert.equal(bars.length, 2);
  const barTop = Math.min(...bars.map((r) => parseFloat(r.styleMap.y)));
  assert.equal(mainBand(app).getAttribute("height"), (barTop - 1).toFixed(2), "one unit above the bar");
  assert.equal(mainBand(app).parentNode.childNodes[0], mainBand(app), "drawn under the bars");
  const laneBar = laneRects(app).find((r) => r.getAttribute("x") === "583.60");
  assert.equal(laneBand(app).getAttribute("height"), (Number(laneBar.getAttribute("y")) - 1).toFixed(2));
});

test("now band: an empty current minute gets the full height and the Current minute title, and it follows the data", async () => {
  const app = boot();
  app.start();
  const empty = fixture("live");
  Object.assign(empty.session.minutes[29], { tokens: 0, by_model: {}, cache_read: 0 });
  await app.reply(ok(empty));
  assert.equal(mainBand(app).getAttribute("height"), "150.00");
  assert.equal(laneBand(app).getAttribute("height"), "48.00");
  assert.equal(titleOf(mainBand(app)), "Current minute, no requests yet");
  assert.equal(titleOf(laneBand(app)), STRINGS.live_now_sr);
  assert.equal(mainBand(app).getAttribute("x"), "581.6");
  await app.clock.advance(POLL_MS);
  const next = withTime(fixture("live"), "2026-10-30T16:25:05-04:00");
  next.etag = "3434343434343434";
  next.session.minutes = next.session.minutes.slice(1).concat([{ start: "2026-10-30T16:25:00-04:00", tokens: 0, by_model: {}, cache_read: 0 }]);
  await app.reply(ok(next));
  assert.equal(mainBand(app).getAttribute("x"), "581.6", "a new minute shifts the columns, and the band stays on the last one");
  assert.equal(mainBand(app).getAttribute("height"), "150.00", "the new minute is empty");
  await app.clock.advance(POLL_MS);
  const still = withTime(fixture("live"), "2026-10-30T16:25:09-04:00");
  still.etag = "4545454545454545";
  await app.reply(ok(still));
  assert.notEqual(mainBand(app).getAttribute("height"), "150.00", "a request in the minute pulls the band down to the bar");
  assert.equal(titleOf(mainBand(app)), "");
});

// ---------------------------------------------------------------- the clock: header age, tick, wait line

test("header age: it moves on a tick, switches to minutes at 60 s and the agents and pills agree", async () => {
  const app = boot();
  app.start();
  assert.equal(app.ticking(), 0, "no tick before an answer");
  await app.reply(ok(withTime(fixture("live"), "2026-10-30T16:25:38-04:00")));
  const age = () => text(one(app.section, "lv-time"));
  const reviewer = () => text(byClass(app.agents()[1], "lv-ag-last")[0]);
  assert.equal(app.state(), "live");
  assert.equal(age(), "Last request 57 s ago");
  assert.equal(app.ticking(), 1);
  await app.clock.advance(1000);
  assert.equal(age(), "Last request 57 s ago", "nothing moves between ticks");
  app.tick();
  assert.equal(age(), "Last request 58 s ago");
  assert.equal(reviewer(), "Last request 58 s ago", "the agent line reads the same clock");
  await app.clock.advance(2000);
  app.tick();
  assert.equal(age(), "Last request 1 min ago", "60 seconds reads in minutes");
  assert.equal(app.state(), "live", "exactly 60 seconds is still working");
  await app.clock.advance(1000);
  app.tick();
  assert.equal(app.state(), "idle", "61 seconds is idle, and the tick keeps going");
  assert.equal(age(), "Last request 1 min ago");
  assert.deepEqual(byClass(app.section, "lv-act").map((n) => n.getAttribute("data-a")), ["idle", "idle", "idle", "idle"]);
  assert.equal(app.ticking(), 1);
});

test("header age: Pause shows As of and stops the ticker, and Resume repaints at once", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(withTime(fixture("live"), "2026-10-30T16:25:38-04:00")));
  app.button().click();
  assert.equal(app.state(), "paused");
  assert.equal(text(one(app.section, "lv-time")), "As of 4:25 PM");
  assert.equal(app.ticking(), 0, "the ticker is stopped on pause");
  await app.clock.advance(5000);
  app.tick();
  assert.equal(text(one(app.section, "lv-time")), "As of 4:25 PM", "a stopped ticker repaints nothing");
  app.button().click();
  assert.equal(app.ticking(), 1, "restarted on resume");
  assert.equal(text(one(app.section, "lv-time")), "Last request 1 min ago", "and repainted before the next tick: 57 + 5 seconds");
});

test("header age: a hidden tab and a page left both stop the ticker, and coming back repaints", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(withTime(fixture("live"), "2026-10-30T16:24:50-04:00")));
  const age = () => text(one(app.section, "lv-time"));
  assert.equal(age(), "Last request 9 s ago");
  app.vis.on = false;
  app.vis.fn();
  assert.equal(app.ticking(), 0, "stopped on hide");
  await app.clock.advance(10000);
  app.vis.on = true;
  app.vis.fn();
  assert.equal(app.ticking(), 1, "restarted on show");
  assert.equal(age(), "Last request 19 s ago", "repainted at once");
  app.leave();
  assert.equal(app.ticking(), 0, "stopped on setActive(false)");
  app.start();
  assert.equal(app.ticking(), 1, "and back when the page returns");
  assert.equal(app.ticker.started - app.ticker.stopped, 1, "never more than one ticker");
});

test("header age: lost, empty, pick and wait run no ticker, and Updated returns for lost", async () => {
  const app = boot();
  app.start();
  assert.equal(app.ticking(), 0);
  await app.reply(ok(fixture("live")));
  assert.equal(app.ticking(), 1);
  await app.clock.advance(POLL_MS);
  await app.reply(fail(0));
  assert.equal(app.state(), "lost");
  assert.equal(app.ticking(), 0);
  assert.equal(text(one(app.section, "lv-time")), "Updated 4:24 PM");
  const other = boot();
  other.start();
  await other.reply(ok(fixture("empty")));
  assert.equal(other.ticking(), 0);
  const all = boot({ key: "all" });
  all.start();
  assert.equal(all.ticking(), 0);
});

test("blink: only an answer that brings a new newest request blinks, never a tick", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("live")));
  const time = one(app.section, "lv-time");
  assert.ok(!hasClass(time, "lv-tick"), "the first answer does not blink");
  await app.clock.advance(POLL_MS);
  app.tick();
  assert.equal(app.section.find((n) => hasClass(n, "lv-tick")).length, 0, "a tick does not blink");
  assert.equal(one(app.section, "lv-time"), time, "and keeps the node");
  const sr = text(app.sr());
  const other = withTime(fixture("live"), "2026-10-30T16:25:00-04:00");
  other.etag = "5656565656565656";
  other.session.totals.tokens = 760000;
  other.session.last_minute.tokens = 31000;
  await app.reply(ok(other));
  assert.equal(one(app.section, "lv-time"), time, "a changed answer with the same newest request keeps the node");
  assert.equal(app.section.find((n) => hasClass(n, "lv-tick")).length, 0, "no blink for other numbers");
  assert.deepEqual(byClass(app.section, "kpi-v").map((v) => hasClass(v, "lv-fresh")), [true, false, false, false], "the value still flashes");
  await app.clock.advance(POLL_MS);
  const added = withTime(fixture("live"), "2026-10-30T16:25:02-04:00");
  added.etag = "6767676767676767";
  const request = Object.assign(copy(added.session.requests[0]), { id: "123456789abc", ts: "2026-10-30T16:25:01-04:00" });
  added.session.requests = [request].concat(added.session.requests.slice(0, 7));
  added.session.last_request = request.ts;
  await app.reply(ok(added));
  const blinked = one(app.section, "lv-time");
  assert.notEqual(blinked, time);
  assert.ok(hasClass(blinked, "lv-tick"), "a new newest request blinks");
  assert.equal(text(blinked), "Last request 1 s ago");
  await app.clock.advance(1000);
  app.tick();
  assert.equal(text(one(app.section, "lv-time")), "Last request 2 s ago");
  assert.equal(one(app.section, "lv-time"), blinked, "a tick changes the text and keeps the node");
  assert.equal(text(app.sr()), sr, "the screen reader line is answer-driven");
});

test("blink: a tick never writes to the screen reader line", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("live")));
  const sr = app.sr();
  const before = text(sr);
  assert.ok(before.startsWith("Updated at 4:24 PM"));
  for (let i = 0; i < 5; i += 1) {
    await app.clock.advance(100);
    app.tick();
  }
  assert.equal(text(sr), before);
  assert.equal(app.sr(), sr);
});

test("wait line: hidden at 14 s, shown at 15 s, in Working and in Idle, and hidden when paused, lost and waiting", async () => {
  const wait = (app) => one(app.section, "lv-wait");
  const at = (iso) => withTime(fixture("live"), iso);
  const app = boot();
  app.start();
  assert.equal(app.state(), "wait");
  assert.equal(wait(app).hidden, true, "nothing to wait for before the first answer");
  const early = boot();
  early.start();
  await early.reply(ok(at("2026-10-30T16:24:55-04:00")));
  assert.equal(wait(early).hidden, true, "14 seconds");
  assert.equal(text(wait(early)), STRINGS.live_wait);
  await early.clock.advance(1000);
  early.tick();
  assert.equal(wait(early).hidden, false, "15 seconds, moved in by a tick");
  assert.equal(early.state(), "live");
  const working = boot();
  working.start();
  await working.reply(ok(at("2026-10-30T16:24:56-04:00")));
  assert.equal(wait(working).hidden, false, "15 seconds at load");
  assert.equal(working.state(), "live");
  working.button().click();
  assert.equal(working.state(), "paused");
  assert.equal(wait(working).hidden, true, "paused hides it");
  working.button().click();
  assert.equal(wait(working).hidden, false, "resume shows it again");
  await working.clock.advance(POLL_MS);
  await working.reply(fail(0));
  assert.equal(working.state(), "lost");
  assert.equal(wait(working).hidden, true, "lost hides it");
  const idle = boot();
  idle.start();
  await idle.reply(ok(fixture("idle")));
  assert.equal(idle.state(), "idle");
  assert.equal(wait(idle).hidden, false, "idle shows it too");
  const empty = boot();
  empty.start();
  await empty.reply(ok(fixture("empty")));
  assert.equal(byClass(empty.section, "lv-wait").length, 0, "the card states have no chart card");
});

test("one clock: the header, the wait line, the agents and the New markers all move with env.now", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("live")));
  assert.equal(byClass(app.section, "lv-new").length, 2);
  await app.clock.advance(20000);
  await app.reply(ok(fixture("unchanged")));
  assert.equal(byClass(app.section, "lv-new").length, 2, "at 16:24:47 the older request is 30 seconds old");
  await app.clock.advance(5000);
  app.tick();
  assert.equal(byClass(app.section, "lv-new").length, 1, "a tick ages out the older marker");
  assert.equal(text(one(app.section, "lv-time")), "Last request 11 s ago", "server_time 16:24:47 plus 5 seconds of tick");
  assert.equal(text(byClass(app.agents()[2], "lv-ag-last")[0]), "Last request 35 s ago");
  assert.equal(one(app.section, "lv-wait").hidden, true, "11 seconds");
  await app.clock.advance(4000);
  app.tick();
  assert.equal(one(app.section, "lv-wait").hidden, false, "15 seconds");
  assert.equal(text(one(app.section, "lv-time")), "Last request 15 s ago");
});

// ---------------------------------------------------------------- the wiring

test("router: #/live is a route, a page and a nav item", () => {
  assert.equal(router.PAGES[0], "live");
  const route = router.parseHash("#/live?project=a");
  assert.deepEqual([route.name, route.known, route.query.project], ["live", true, "a"]);
  assert.equal(router.hashFor("live", {}, { project: "a" }), "#/live?project=a");
  assert.equal(router.sectionFor(route, "a"), "live");
  assert.equal(router.sectionFor(route, "all"), "live", "All projects keeps the live section and shows the pick card");
  assert.equal(router.navFor(route), "live");
  assert.equal(router.parseHash("#/live/extra").known, false);
});

test("shell: Live is the first item of This project with the pulse icon", () => {
  const page = createPage();
  createShell({ sidebar: page.sidebar, topbar: page.topbar, onProject() {} });
  const links = byTag(page.sidebar, "a");
  assert.equal(text(links[0]), "Live");
  assert.equal(text(links[1]), "Overview");
  assert.equal(byTag(links[0], "path")[0].getAttribute("d"), "M3 12h4l2.5-6 5 12 2.5-6h4");
  assert.equal(byTag(links[0], "svg")[0].getAttribute("stroke-width"), "1.75");
});

test("api: live() builds the address and never caches", async () => {
  const urls = [];
  const api = createApi((address) => { urls.push(address); return Promise.resolve({ ok: true, status: 200, data: {} }); });
  await api.live("a b", "s1", "e1");
  await api.live("a b", null, null);
  await api.live("a b", "s1", "e1");
  assert.deepEqual(urls, ["/api/live?project=a%20b&session=s1&etag=e1", "/api/live?project=a%20b", "/api/live?project=a%20b&session=s1&etag=e1"]);
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

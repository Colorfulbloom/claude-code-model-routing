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
  const env = {
    setTimer: clock.set,
    clearTimer: clock.clear,
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
    page, section, clock, live, vis, calls, pending, ctx: makeCtx(key),
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
  assert.equal(text(one(app.section, "lv-time")), "Updated 4:24 PM");
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
  const svg = one(app.section, "dbars");
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
  assert.deepEqual(byTag(one(app.section, "dy"), "span").map(text), ["150K", "100K", "50K", "0"]);
  assert.deepEqual(byTag(one(app.section, "dx"), "span").map(text), ["3:59", "4:04", "4:09", "4:14", "4:19", "Now"]);
  assert.equal(one(app.section, "lv-now-x").styleMap.left, "98.33%", "Now sits at the right edge");
  const legend = byTag(one(app.section, "klg"), "li");
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
    ["Time", "Agent", "Model", "Effort", "Tokens", "Output", "Estimated cost"]);
  assert.equal(byClass(app.section, "lv-new").length, 2, "two requests are under 30 seconds old");
  const cells = (row) => byTag(row, "td").map(text);
  assert.deepEqual(cells(rows[0]), ["4:24:41New", "reviewer", "Sonnet 5.5", "xhigh", "23K", "360", "$0.02"]);
  assert.deepEqual(cells(rows[1]), ["4:24:17New", "scribe", "acme-test-model-1", "high", "6,200", "225", "Not priced"]);
  assert.deepEqual(cells(rows[2]).slice(0, 2), ["4:23:31", "scribe"]);
  assert.equal(cells(rows[5])[1], "Main session");
  assert.equal(byClass(rows[0], "lv-new").length, 1);
  assert.equal(text(byClass(rows[0], "lv-new")[0]), "New");
  assert.equal(byTag(rows[0], "td")[2].classList.contains("lv-hide-s"), true, "model hides at 375");
  assert.equal(text(one(app.section, "est")), "Estimated at API list price");
  assert.equal(text(one(app.section, "foot")).startsWith("Read from the transcripts in ~/.claude/projects every 3 seconds"), true);
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
  assert.equal(text(one(app.section, "lv-time")), "Updated 4:52 PM");
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
  assert.equal(app.clock.nextIn(), POLL_MS, "back to 3 seconds");
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

test("poll: every 3 seconds, never two requests in flight", async () => {
  const app = boot();
  app.start();
  await app.reply(ok(fixture("live")));
  assert.equal(app.calls.length, 1);
  assert.equal(app.clock.nextIn(), 3000);
  await app.clock.advance(2999);
  assert.equal(app.calls.length, 1);
  await app.clock.advance(1);
  assert.equal(app.calls.length, 2);
  await app.clock.advance(30000);
  assert.equal(app.calls.length, 2, "the answer is still out, so nothing else goes");
  assert.equal(app.pending.length, 1);
  await app.reply(ok(fixture("unchanged")));
  assert.equal(app.clock.nextIn(), 3000, "the next one is 3 seconds after the answer");
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
  assert.equal(text(one(app.section, "lv-time")), "Updated 4:25 PM");
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
  assert.equal(text(sr), "Updated at 4:24 PM. 755K tokens, $0.94 estimated cost.", "3 seconds later: nothing new is read");
  await app.clock.advance(POLL_MS);
  await app.reply(ok(fixture("unchanged")));
  assert.equal(text(sr), "Updated at 4:24 PM. 755K tokens, $0.94 estimated cost.");
  await app.clock.advance(57000 - POLL_MS * 0);
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

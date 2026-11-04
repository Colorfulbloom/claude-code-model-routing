// Live, at #/live. One session of one project, minute by minute, read from /api/live every second while this page is
// the visible section, the tab is in view and the page is not paused (js/live_poll.js does the asking).
//
// The page is built once and then updated in place, so a focused button or select keeps focus between answers, a
// column can grow with a transition and a changed value can flash. section data-live names the state:
//   wait        no answer yet                      live      a session with a request in the last minute
//   idle        its last request is over a minute  paused    the viewer paused the page
//   lost        the server did not answer          empty     no session with a request in the last 30 minutes
//   pick        All projects, nothing is fetched   unknown   the server does not know the project (4xx)
//   unreadable  the transcripts folder cannot be read
//
// One clock serves every relative time: nowMs() is the newest answer's server_time plus the time that passed since the
// answer landed. The "Last request n s ago" text in the header, the agents' last request lines, the activity pills, the
// New markers, the Working and Idle state and the wait line all read it, with session.last_request as the newest
// request, so they always agree. A one-second clock moves the "Last request n s ago" text between answers. It runs
// only while the page is active, the tab is in view and the state is live or idle, and it repaints the words that
// depend on the clock (paint) and nothing else. Reduced motion does not stop it, because a changing number is not
// motion, and Pause does. Flashes, the blink on the age and the screen reader line happen on a changed answer only,
// and the blink only when that answer brings a new newest request. The wait line ("A request shows up here once it's
// written to the transcript") shows while the state is live or idle and the newest request is 15 seconds old or more.
// The payload holds usage fields, never message text, and nothing here reads any.
//
// createLive(env) holds all the state, so a check can run it with fake timers and a fake ticker. render and setActive
// at the bottom are the page module's two exports, bound to one instance that uses the real timers and the tab's
// visibility.

import { h, s, clear, setLocalHref } from "../h.js";
import {
  t, fmtClock, fmtTime, fmtTokens, fmtTick, fmtCost, pct,
} from "../format.js";
import { card, emptyState } from "../components.js";
import { modelClass, patternId, hatchDefs, stackedTokens, kindsLegend } from "../charts.js";
import { ALL_KEY, MAIN_KEY } from "../router.js";
import { createLivePoller, RETRY_MS } from "../live_poll.js";

const UNNAMED_KEY = "@unnamed";
const ACTIVE_MS = 60000; // a session with a request in the last minute is working
const NEW_MS = 30000; // a request in the last 30 seconds wears the New marker
const ANNOUNCE_MS = 60000; // the screen reader hears at most one update a minute
const MAX_ROWS = 8;
const COLS = 30; // one column per minute
const H = 150; // the chart's height in its own units
const W = 600;
const LH = 48; // the cache lane's height in its own units
const STEP_BACK_MS = 2000; // the most a poll's latency can pull the clock back
const WAIT_MS = 15000; // a request not yet in the transcript: the wait line shows from this age
const NBSP = " ";

let secondsFormat = null;

// "4:23:47", the time of a request with its seconds and no AM or PM, as the design shows it.
function clockSeconds(date) {
  if (!secondsFormat) {
    secondsFormat = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit", hourCycle: "h12" });
  }
  const out = {};
  for (const p of secondsFormat.formatToParts(date)) out[p.type] = p.value;
  return out.hour + ":" + out.minute + ":" + out.second;
}

const dateOf = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
};
const ms = (iso) => {
  const d = dateOf(iso);
  return d ? d.getTime() : null;
};
const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : 0);
const list = (v) => (Array.isArray(v) ? v : []);

// A route key names the agent: "@main" is the main session, "@unnamed" an agent with no name.
function agentName(row) {
  if (row.route_key === MAIN_KEY) return t("row_main");
  if (row.route_key === UNNAMED_KEY) return t("agent_unnamed");
  return row.agent || row.route_key || "";
}

const modelName = (row) => row.model_display || row.model || "";
const effortText = (row) => (row.effort === null || row.effort === undefined || row.effort === "" ? t("effort_not_recorded_inline") : row.effort);

// "~/.claude/projects" is the transcripts folder, and the footer sentence adds "/projects" itself.
const configDirOf = (dir) => String(dir).replace(/\/projects\/?$/, "");

function activityPill() {
  return h("span", { class: "lv-act", "data-a": "idle" }, t("live_idle"));
}

function setActivity(pill, working) {
  pill.setAttribute("data-a", working ? "working" : "idle");
  pill.textContent = working ? t("live_working") : t("live_idle");
}

function toSelect() {
  const select = document.getElementById("project");
  if (select) select.focus();
}

export function createLive(env) {
  const S = {
    ctx: null,
    key: null,
    active: false,
    mode: "ok", // the poller's: ok, lost or unknown
    paused: false,
    payload: null, // the last full answer
    serverTime: null, // Date of the newest answer, full or unchanged
    receivedAt: null, // env.now() when that answer landed
    lastNow: null, // the newest nowMs() handed out, so a poll's latency never steps the clock back
    prevIds: new Set(), // request ids of the answer before the last full one
    flash: false, // the next paint follows a changed answer
    blink: false, // the next paint follows a changed answer with a new newest request
    gone: false, // the viewer's session ended and the page moved to another
    picks: new Map(), // project key to the session its viewer picked
    announcedAt: null,
    quiet: false, // the next changed answer is for another project or session, so nothing flashes
  };
  let view = null;
  let unlisten = null;
  let tickId = null;

  const poller = createLivePoller({
    fetchLive: (session, etag) => S.ctx.live(S.key, session, etag),
    setTimer: env.setTimer,
    clearTimer: env.clearTimer,
    isVisible: env.isVisible,
    onAnswer: (answer) => onAnswer(answer),
    onState: (mode) => { S.mode = mode; paint(); },
  });

  // ---------------------------------------------------------------- state

  function session() {
    return S.payload && S.payload.session && typeof S.payload.session === "object" ? S.payload.session : null;
  }

  // The one clock: the newest answer's server time plus what passed since it landed.
  function nowMs() {
    if (!S.serverTime || S.receivedAt === null) return null;
    const at = S.serverTime.getTime() + (env.now() - S.receivedAt);
    // A step back under STEP_BACK_MS is the request's latency, so hold the clock. A bigger one is a real clock change.
    if (S.lastNow !== null && at < S.lastNow && S.lastNow - at < STEP_BACK_MS) return S.lastNow;
    S.lastNow = at;
    return at;
  }

  // Seconds since the newest request, or null when the clock or the request time is missing.
  function sinceLast() {
    const shown = session();
    const now = nowMs();
    const last = shown ? ms(shown.last_request) : null;
    return now === null || last === null ? null : Math.max(0, Math.floor((now - last) / 1000));
  }

  const working = (lastRequest) => {
    const last = ms(lastRequest);
    const now = nowMs();
    return last !== null && now !== null && now - last <= ACTIVE_MS;
  };

  function stateOf() {
    if (S.key === ALL_KEY) return "pick";
    if (S.mode === "unknown") return "unknown";
    if (!S.payload) return S.mode === "lost" ? "lost" : "wait";
    if (typeof S.payload.unreadable === "string" && S.payload.unreadable) return "unreadable";
    if (S.paused) return "paused";
    if (S.mode === "lost") return "lost";
    const shown = session();
    if (!shown) return "empty";
    return working(shown.last_request) ? "live" : "idle";
  }

  // ---------------------------------------------------------------- the page, built once

  function tile(label, plain) {
    const value = h("div", { class: "kpi-v" }, NBSP);
    const line = h("span", { class: ["lv-since", "lv-zero", plain && "lv-plain"] }, NBSP);
    return { el: h("div", { class: "kpi" }, h("div", { class: "kpi-top" }, h("span", { class: "tl-l" }, label)), value, line), value, line };
  }

  // The Now band is the current minute's slot, drawn under the bars. fillChart sets its geometry.
  function nowBand() {
    const title = s("title", null);
    const rect = s("rect", { class: "lv-nowband", y: 0, height: 0, width: 0 }, title);
    rect.lvTitle = title;
    return rect;
  }

  function buildChart() {
    const id = patternId("oth-live");
    const dy = h("div", { class: "dy", "aria-hidden": "true" });
    const grid = s("g", null);
    const band = nowBand();
    const bars = s("g", null, band);
    const svg = s("svg", {
      class: "dbars", viewBox: "0 0 " + W + " " + H, preserveAspectRatio: "none", role: "img", "aria-label": t("live_chart_sr"),
    }, hatchDefs(id), grid, s("line", { x1: 0, y1: H, x2: W, y2: H, class: "base" }), bars);
    // The cache lane has its own scale and shares the x labels under it.
    const laneDy = h("div", { class: "dy", "aria-hidden": "true" });
    const laneBand = nowBand();
    const laneBars = s("g", null);
    const laneSvg = s("svg", {
      class: "dbars lv-lane-svg", viewBox: "0 0 " + W + " " + LH, preserveAspectRatio: "none", "aria-hidden": "true",
    }, laneBand, laneBars, s("line", { x1: 0, y1: LH, x2: W, y2: LH, class: "base" }));
    const dx = h("div", { class: "dx dx-min", "aria-hidden": "true" });
    return {
      id, dy, grid, bars, svg, band, dx, laneDy, laneBand, laneBars, rects: new Map(), order: [],
      el: h("div", { class: "dchart lv-main" }, dy, svg),
      laneEl: h("div", { class: "dchart lv-lane" }, laneDy, laneSvg, dx),
    };
  }

  function buildDash() {
    const tiles = [tile(t("kpi_tokens")), tile(t("kpi_cost")), tile(t("kpi_hit"), true), tile(t("h_requests"))];
    const chart = buildChart();
    const meter = h("div", { class: "lv-meter" });
    const legend = h("ul", { class: "klg" });
    const rowHead = h("div", { class: "lv-row-h" }, h("span", { class: "lv-row-t" }, t("live_new_h")), legend);
    const laneHead = h("div", { class: "lv-lane-h" },
      h("span", { class: "swatch rk-1 lv-sw-rk1", "aria-hidden": "true" }), h("span", { class: "lv-row-t" }, t("live_lane_h")));
    const note = h("p", { class: "lv-note" }, t("live_chart_note"));
    const wait = h("p", { class: "lv-wait", hidden: true }, t("live_wait"));
    const agents = h("div", { class: "lv-ags" });
    const cols = [t("live_col_time"), t("h_agent"), t("f_model"), t("f_effort"), t("kpi_tokens"), t("k_cache_read"), t("k_output"), t("kpi_cost")];
    const hide = [false, false, true, true, false, true, true, false];
    const tbody = h("tbody", null);
    const table = h("table", { class: "dt lv-req" },
      h("thead", null, h("tr", null, cols.map((c, i) => h("th", { scope: "col", class: hide[i] && "lv-hide-s" }, c)))), tbody);
    const foot = h("p", { class: "foot" });
    const grid = h("div", { class: "lv-g21" },
      card({
        title: t("live_chart_h"), sub: t("live_chart_sub"), icon: "pulse",
        body: [meter, rowHead, chart.el, laneHead, chart.laneEl, note, wait],
      }),
      card({ title: t("live_agents_h"), sub: t("live_agents_sub"), icon: "agents", body: agents }));
    const requests = card({ title: t("live_req_h"), sub: t("live_req_sub"), icon: "list", body: [table, h("p", { class: "est" }, t("est_short"))] });
    return {
      nodes: [h("div", { class: "kpis" }, tiles.map((x) => x.el)), grid, requests, foot],
      tiles, chart, meter, legend, wait, agents, agentRows: new Map(), tbody, rows: new Map(), foot, hide, cols,
    };
  }

  function buildView(root) {
    clear(root);
    const sr = h("div", { class: "sr", role: "status", "aria-live": "polite", "aria-atomic": "true" });
    const notice = h("div", { class: "nt lv-lost-nt", role: "status", hidden: true }, h("p", { class: "nt-t" }, t("live_lost_detail", { n: RETRY_MS / 1000 })));
    const intro = h("p", { class: "intro" });
    const sessPill = activityPill();
    const sessLink = h("a", { class: "lnk" });
    const branch = h("span", { class: "mono" });
    const when = h("span", { class: "muted" });
    const pickSlot = h("span", { class: "sw lv-pick" });
    const sess = h("div", { class: "lv-sess", hidden: true }, sessPill, sessLink, branch, when, pickSlot);
    const gone = h("p", { class: "lv-gone muted", hidden: true }, t("live_session_gone"));
    const mark = h("i", { class: "lv-mk", "aria-hidden": "true" });
    const word = h("span", null);
    const pill = h("span", { class: "lv-pill", hidden: true }, mark, word);
    let time = h("span", { class: "lv-time" });
    const button = h("button", { type: "button", class: "btn", on: { click: onControl } }, t("live_pause"));
    const ctl = h("div", { class: "lv-ctl" }, pill, time, button);
    const body = h("div", { class: "lv-stack" });
    const head = h("div", { class: "ph" }, h("div", { class: "ph-row" },
      h("div", null, h("h1", null, t("live_title")), intro, sess, gone), h("div", { class: "lv-ph-r" }, ctl)));
    root.appendChild(sr);
    root.appendChild(notice);
    root.appendChild(head);
    root.appendChild(body);
    view = {
      root, sr, notice, intro, sess, sessPill, sessLink, branch, when, pickSlot, pickKey: "", select: null, gone, ctl, pill, word, button,
      get time() { return time; },
      set time(node) { time = node; },
      body, dash: null, filled: undefined, shown: "",
    };
  }

  // ---------------------------------------------------------------- the controls

  function onControl() {
    const state = stateOf();
    if (state === "paused") {
      S.paused = false;
      poller.setPaused(false);
      paint();
    } else if (state === "lost") {
      poller.tryNow();
    } else {
      S.paused = true;
      poller.setPaused(true);
      paint();
    }
  }

  function drawControl(state) {
    const v = view;
    const hasControl = state !== "pick" && state !== "unknown";
    v.button.hidden = !hasControl;
    const stamp = S.serverTime ? fmtClock(S.serverTime) : "";
    let word = null;
    let label = t("live_pause");
    let timeText = stamp ? t("live_updated", { time: stamp }) : "";
    if (state === "paused") {
      word = t("live_paused");
      label = t("live_resume");
      timeText = stamp ? t("live_paused_at", { time: stamp }) : "";
    } else if (state === "lost") {
      word = t("live_lost");
      label = t("live_retry");
    }
    v.pill.hidden = word === null;
    if (word !== null) {
      v.pill.setAttribute("data-s", state);
      v.word.textContent = word;
    }
    v.button.textContent = label;
    if ((state === "live" || state === "idle") && sinceLast() !== null) {
      const seconds = sinceLast();
      timeText = seconds < 60 ? t("live_agent_last_s", { n: seconds }) : t("live_agent_last_min", { n: Math.floor(seconds / 60) });
    }
    if (!hasControl) timeText = "";
    // One blink when a changed answer brings a new newest request: a new node starts its animation, an old one only
    // changes its text. A tick never blinks.
    if (S.blink && (state === "live" || state === "idle")) {
      const next = h("span", { class: "lv-time lv-tick" }, timeText);
      v.time.replaceWith(next);
      v.time = next;
    } else if (v.time.textContent !== timeText) {
      v.time.textContent = timeText;
    }
    v.notice.hidden = state !== "lost";
  }

  // ---------------------------------------------------------------- the header

  function pickSession(running, shown) {
    const v = view;
    const key = JSON.stringify(running.map((r) => [r.session_id, r.started, r.branch]));
    if (running.length < 2) {
      if (v.pickKey !== "") { clear(v.pickSlot); v.select = null; v.pickKey = ""; }
      return;
    }
    if (v.pickKey !== key) {
      const options = running.map((r) => h("option", { value: r.session_id },
        t("session_from", { time: fmtTime(r.started) }) + (r.branch ? " · " + r.branch : "")));
      v.select = h("select", { id: "lv-session", on: { change: (event) => choose(event.target.value) } }, options);
      clear(v.pickSlot);
      v.pickSlot.appendChild(h("label", { for: "lv-session", class: "lv-pick-l" }, t("live_session_pick")));
      v.pickSlot.appendChild(v.select);
      v.pickKey = key;
    }
    v.select.value = shown.session_id;
  }

  function choose(id) {
    if (!id) return;
    S.picks.set(S.key, id);
    S.gone = false;
    S.quiet = true;
    poller.setSession(id);
    paint();
  }

  function drawHead(state) {
    const v = view;
    const shown = state === "pick" || state === "unknown" || state === "unreadable" ? null : session();
    v.intro.textContent = state === "pick" ? "" : t("live_intro", { project: S.ctx.project.name });
    v.sess.hidden = !shown;
    v.gone.hidden = !(S.gone && shown);
    if (!shown) {
      pickSession([], null);
      return;
    }
    const isWorking = working(shown.last_request);
    const now = nowMs();
    setActivity(v.sessPill, isWorking);
    v.sessLink.textContent = t("session_from", { time: fmtTime(shown.started) });
    setLocalHref(v.sessLink, S.ctx.hashFor("session-detail", { id: shown.session_id }));
    v.branch.textContent = shown.branch || "";
    v.branch.hidden = !shown.branch;
    const last = dateOf(shown.last_request);
    if (isWorking) {
      const start = ms(shown.started);
      const minutes = start !== null && now !== null ? Math.max(0, Math.floor((now - start) / 60000)) : 0;
      v.when.textContent = t("live_started", { time: fmtClock(new Date(shown.started)), n: minutes });
    } else {
      v.when.textContent = last ? t("live_last_at", { time: fmtClock(last) }) : "";
    }
    pickSession(list(S.payload.running), shown);
  }

  // ---------------------------------------------------------------- the dashboard body

  function setLine(tl, text, zero) {
    tl.line.textContent = text;
    tl.line.classList.toggle("lv-zero", zero);
  }

  function setValue(tl, text, fresh) {
    if (tl.value.textContent === text) return;
    if (fresh) {
      const next = h("div", { class: "kpi-v lv-fresh" }, text);
      tl.value.replaceWith(next);
      tl.value = next;
    } else {
      tl.value.textContent = text;
    }
  }

  function fillKpis(d, shown, fresh) {
    const [tokens, cost, hit, requests] = d.tiles;
    if (!shown) {
      for (const tl of d.tiles) { setValue(tl, NBSP, false); setLine(tl, NBSP, true); }
      return;
    }
    const totals = shown.totals || {};
    const last = shown.last_minute || {};
    setValue(tokens, fmtTokens(num(totals.tokens)), fresh);
    setLine(tokens, num(last.tokens) > 0 ? t("live_last_min", { n: fmtTokens(num(last.tokens)) }) : t("live_last_min_none"), !(num(last.tokens) > 0));
    setValue(cost, fmtCost(totals.cost, totals.unpriced_requests), fresh);
    if (num(last.cost) <= 0) setLine(cost, t("live_last_min_none"), true);
    else if (num(last.cost) < 0.005) setLine(cost, t("live_last_min_small"), false);
    else setLine(cost, t("live_last_min", { n: fmtCost(last.cost) }), false);
    setValue(hit, pct(totals.hit_rate), fresh);
    const rate = last.hit_rate;
    setLine(hit, rate === null || rate === undefined ? t("live_last_min_none") : t("live_last_min_count", { n: pct(rate) }), rate === null || rate === undefined);
    setValue(requests, num(totals.requests).toLocaleString("en-US"), fresh);
    setLine(requests, num(last.requests) > 0 ? t("live_last_min_count", { n: num(last.requests).toLocaleString("en-US") }) : t("live_last_min_none"), !(num(last.requests) > 0));
  }

  // The Now band covers the current minute's slot, from the top of the plot down to one unit above that minute's bar.
  // Its title says so when the minute has no requests yet, and is empty otherwise.
  function placeBand(rect, index, bw, bottom, full, empty) {
    if (index < 0) {
      rect.setAttribute("width", "0");
      rect.setAttribute("height", "0");
      rect.lvTitle.textContent = "";
      return;
    }
    rect.setAttribute("x", (index * bw + bw * 0.18 - 2).toFixed(1));
    rect.setAttribute("width", (bw * 0.64 + 4).toFixed(1));
    rect.setAttribute("y", "0");
    rect.setAttribute("height", (bottom >= full ? full : Math.max(bottom - 1, 0)).toFixed(2));
    rect.lvTitle.textContent = empty ? t("live_now_sr") : "";
  }

  // The cache lane: one rect per minute with cache reads, on its own scale (the peak minute fills the lane).
  function fillLane(c, minutes, bw, mainBottom) {
    const reads = minutes.map((m) => num(m.cache_read));
    const peak = Math.max(0, ...reads);
    clear(c.laneBars);
    clear(c.laneDy);
    if (peak > 0) c.laneDy.appendChild(h("span", null, fmtTokens(peak)));
    c.laneDy.appendChild(h("span", null, "0"));
    let laneBottom = LH;
    minutes.forEach((m, i) => {
      if (reads[i] <= 0) return;
      const height = (reads[i] / peak) * (LH - 2);
      const stamp = dateOf(m.start);
      c.laneBars.appendChild(s("rect", {
        class: "lv-cr", x: (i * bw + bw * 0.18).toFixed(2), width: (bw * 0.64).toFixed(2),
        y: (LH - height).toFixed(2), height: height.toFixed(2), "vector-effect": "non-scaling-stroke",
      }, s("title", null, (stamp ? fmtClock(stamp) + " " : "") + t("live_lane_h") + " " + fmtTokens(reads[i]))));
      if (i === minutes.length - 1) laneBottom = LH - height;
    });
    const last = minutes.length - 1;
    const empty = last >= 0 && num(minutes[last].tokens) <= 0 && reads[last] <= 0;
    placeBand(c.band, last, bw, mainBottom, H, empty);
    placeBand(c.laneBand, last, bw, laneBottom, LH, empty);
  }

  function fillChart(c, shown) {
    const minutes = shown ? list(shown.minutes).slice(-COLS) : [];
    const axis = shown && shown.axis ? shown.axis : null;
    const ticks = axis ? list(axis.ticks).filter((x) => typeof x === "number") : [];
    const top = (axis && num(axis.top) > 0 ? axis.top : Math.max(0, ...ticks)) || 1;
    const names = new Map();
    const order = [];
    if (shown) {
      for (const row of list(shown.by_model)) { order.push(row.model); names.set(row.model, row.display_name || row.model); }
      for (const m of minutes) for (const model of Object.keys(m.by_model || {})) if (!order.includes(model)) order.push(model);
    }
    for (const model of order) if (!c.order.includes(model)) c.order.push(model);
    const bw = W / COLS;
    let lastBottom = H; // the top of the current minute's stack
    minutes.forEach((m, i) => {
      let bottom = H;
      const stamp = dateOf(m.start);
      for (const model of c.order) {
        const tokens = num((m.by_model || {})[model]);
        const key = i + "|" + model;
        let rect = c.rects.get(key);
        if (!rect && tokens <= 0) continue;
        if (!rect) {
          const title = s("title", null);
          rect = s("rect", {
            class: "col " + modelClass(model), x: (i * bw + bw * 0.18).toFixed(2), width: (bw * 0.64).toFixed(2),
            fill: modelClass(model) === "cat-other" ? "url(#" + c.id + ")" : null,
          }, title);
          rect.lvTitle = title;
          c.rects.set(key, rect);
          c.bars.appendChild(rect);
        }
        const height = tokens > 0 ? Math.max((tokens / top) * H - 1, 0.5) : 0;
        const y = tokens > 0 ? bottom - (tokens / top) * H : bottom;
        rect.style.setProperty("y", y + "px");
        rect.style.setProperty("height", height + "px");
        if (tokens > 0) {
          rect.lvTitle.textContent = (stamp ? fmtClock(stamp) + " " : "") + (names.get(model) || model) + " " + fmtTokens(tokens);
          bottom = y;
        }
      }
      lastBottom = bottom;
    });
    // A column with no minute (the wait state, or a shorter list) holds nothing.
    for (const [key, rect] of c.rects) {
      if (Number(key.split("|")[0]) >= minutes.length) rect.style.setProperty("height", "0px");
    }
    clear(c.grid);
    for (const tick of ticks) {
      if (tick <= 0) continue;
      const y = (H - (H * tick) / top).toFixed(1);
      c.grid.appendChild(s("line", { x1: 0, y1: y, x2: W, y2: y, class: "grid" }));
    }
    clear(c.dy);
    for (const tick of ticks.slice().reverse()) c.dy.appendChild(h("span", null, fmtTick(tick)));
    fillLane(c, minutes, bw, lastBottom);
    clear(c.dx);
    minutes.forEach((m, i) => {
      if (i % 5 !== 4 || i >= minutes.length - 1) return;
      const stamp = dateOf(m.start);
      if (stamp) c.dx.appendChild(h("span", { style: { left: (((i + 0.5) / COLS) * 100).toFixed(2) + "%" } }, fmtClock(stamp).replace(/\s?[AP]M$/, "")));
    });
    if (minutes.length) {
      c.dx.appendChild(h("span", { class: "lv-now-x", style: { left: (((minutes.length - 0.5) / COLS) * 100).toFixed(2) + "%" } }, t("live_now")));
    }
  }

  // The session bar by kind with its legend, rebuilt on each changed answer. The legend lists all four kinds.
  function fillMeter(d, shown) {
    clear(d.meter);
    if (!shown) return;
    const totals = shown.totals || {};
    const kinds = {
      tokens: num(totals.tokens), input: num(totals.input), output: num(totals.output),
      cache_read: num(totals.cache_read), cache_write: num(totals.cache_write),
    };
    d.meter.appendChild(stackedTokens([{ label: t("live_kinds_h"), a: kinds }]));
    d.meter.appendChild(kindsLegend(kinds));
  }

  function fillLegend(d, shown) {
    clear(d.legend);
    if (!shown) return;
    for (const row of list(shown.by_model)) {
      d.legend.appendChild(h("li", null,
        h("span", { class: "swatch " + modelClass(row.model), "aria-hidden": "true" }),
        (row.display_name || row.model) + " ", h("span", { class: "muted" }, fmtTokens(num(row.tokens)))));
    }
  }

  function fillAgents(d, shown) {
    const rows = shown ? list(shown.agents) : [];
    const biggest = rows.reduce((m, r) => Math.max(m, num(r.tokens)), 0) || 1;
    const seen = new Set();
    for (const row of rows) {
      seen.add(row.route_key);
      let r = d.agentRows.get(row.route_key);
      if (!r) {
        r = {
          name: h("div", { class: "lv-ag-n" }), meta: h("div", { class: "lv-ag-m" }), pill: activityPill(),
          fill: h("span", null), value: h("span", { class: "lv-ag-v" }), last: h("div", { class: "lv-ag-last" }), data: row,
        };
        r.el = h("div", { class: "lv-ag" }, h("div", null, r.name, r.meta), r.pill,
          h("div", { class: "lv-ag-bar" }, h("div", { class: "lv-bar" }, r.fill), r.value), r.last);
        d.agentRows.set(row.route_key, r);
      }
      r.data = row;
      r.name.textContent = agentName(row);
      r.meta.textContent = modelName(row) + " · " + effortText(row);
      r.fill.style.setProperty("width", ((100 * num(row.tokens)) / biggest).toFixed(2) + "%");
      r.value.textContent = fmtTokens(num(row.tokens));
      d.agents.appendChild(r.el);
    }
    for (const [key, r] of d.agentRows) {
      if (!seen.has(key)) { d.agents.removeChild(r.el); d.agentRows.delete(key); }
    }
  }

  function buildRow(d) {
    const cells = d.cols.map((name, i) => h("td", { "data-l": name, class: d.hide[i] && "lv-hide-s" }));
    const stamp = h("span", null);
    cells[0].appendChild(stamp);
    return { cells, stamp, mark: null, el: h("tr", null, cells), data: null };
  }

  function fillRequests(d, shown, fresh) {
    const rows = shown ? list(shown.requests).slice(0, MAX_ROWS) : [];
    d.tbody.setAttribute("aria-hidden", shown ? "false" : "true");
    if (!shown) {
      // The wait state keeps the rows at their final height with nothing in them.
      if (d.rows.size) { clear(d.tbody); d.rows.clear(); }
      if (d.tbody.firstChild === null) {
        for (let i = 0; i < MAX_ROWS; i += 1) {
          const r = buildRow(d);
          r.stamp.textContent = NBSP;
          d.tbody.appendChild(r.el);
          d.skeleton = (d.skeleton || []).concat(r);
        }
      }
      return;
    }
    if (d.skeleton) { clear(d.tbody); d.skeleton = null; }
    const seen = new Set();
    for (const rec of rows) {
      seen.add(rec.id);
      let r = d.rows.get(rec.id);
      if (!r) {
        r = buildRow(d);
        if (fresh && !S.prevIds.has(rec.id)) r.el.classList.add("lv-fresh");
        d.rows.set(rec.id, r);
      }
      r.data = rec;
      const at = dateOf(rec.ts);
      r.stamp.textContent = at ? clockSeconds(at) : "";
      const cost = rec.cost === null || rec.cost === undefined ? t("not_priced")
        : rec.cost > 0 && rec.cost < 0.005 ? t("live_cost_lt_cent") : fmtCost(rec.cost);
      const texts = [null, agentName(rec), modelName(rec), effortText(rec), fmtTokens(num(rec.tokens)), fmtTokens(num(rec.cache_read)), fmtTokens(num(rec.output)), cost];
      texts.forEach((text, i) => { if (i > 0 && r.cells[i].textContent !== text) r.cells[i].textContent = text; });
      d.tbody.appendChild(r.el);
    }
    for (const [id, r] of d.rows) {
      if (!seen.has(id)) { d.tbody.removeChild(r.el); d.rows.delete(id); }
    }
  }

  // The words that depend on the clock: the agents' last request, the New markers and the foot.
  function drawTimes(d) {
    const now = nowMs();
    for (const r of d.agentRows.values()) {
      const last = ms(r.data.last_request);
      const isWorking = now !== null && last !== null && now - last <= ACTIVE_MS;
      setActivity(r.pill, isWorking);
      if (last === null || now === null) { r.last.textContent = ""; continue; }
      const seconds = Math.max(0, Math.floor((now - last) / 1000));
      r.last.textContent = seconds < 60 ? t("live_agent_last_s", { n: seconds }) : t("live_agent_last_min", { n: Math.floor(seconds / 60) });
    }
    for (const r of d.rows.values()) {
      const at = ms(r.data.ts);
      const isNew = now !== null && at !== null && now - at <= NEW_MS;
      if (isNew && !r.mark) {
        r.mark = h("span", { class: "lv-new" }, t("live_new"));
        r.cells[0].appendChild(r.mark);
      } else if (!isNew && r.mark) {
        r.cells[0].removeChild(r.mark);
        r.mark = null;
      }
    }
    // The wait line: a request is written to the transcript a moment after it is made, so the newest one can be late.
    const age = sinceLast();
    const state = stateOf();
    d.wait.hidden = !((state === "live" || state === "idle") && age !== null && age * 1000 >= WAIT_MS);
    const dir = S.ctx.transcriptsDir;
    const foot = dir ? t("live_foot", { config_dir: configDirOf(dir) }) + " " + t("live_hidden_note") : "";
    if (d.foot.textContent !== foot) d.foot.textContent = foot;
    d.foot.hidden = !foot;
  }

  function fillDash(d) {
    const shown = S.payload ? session() : null;
    if (view.filled !== S.payload) {
      const fresh = S.flash && view.filled !== undefined && view.filled !== null;
      fillKpis(d, shown, fresh);
      fillMeter(d, shown);
      fillChart(d.chart, shown);
      fillLegend(d, shown);
      fillAgents(d, shown);
      fillRequests(d, shown, fresh);
      view.filled = S.payload;
    }
    drawTimes(d);
  }

  // ---------------------------------------------------------------- the card states

  function stateCard(state) {
    if (state === "pick") {
      return card({
        title: t("s_pick_project_h"), icon: "overview",
        body: h("div", { class: "es" },
          h("p", { class: "es-t" }, t("s_pick_project_t")),
          h("button", { type: "button", class: "btn", on: { click: toSelect } }, t("s_pick_project_btn"))),
      });
    }
    if (state === "unknown") {
      return card({
        title: t("live_unknown_h"), icon: "overview",
        body: h("div", { class: "es" },
          h("p", { class: "es-t" }, t("live_unknown_t")),
          h("button", { type: "button", class: "btn", on: { click: toSelect } }, t("s_pick_project_btn"))),
      });
    }
    if (state === "unreadable") return emptyState(t("s_transcripts_h"), t("s_transcripts_t", { path: S.payload.unreadable }));
    return h("section", { class: "cd" }, h("div", { class: "lv-empty" },
      h("p", { class: "es-h" }, t("live_empty_h", { project: S.ctx.project.name })),
      h("p", { class: "es-t" }, t("live_empty_t")),
      h("a", { class: "btn", href: S.ctx.hashFor("sessions", {}, { range: "today" }) }, t("live_empty_go"))));
  }

  function drawBody(state) {
    const v = view;
    const cards = ["pick", "unknown", "unreadable", "empty"].includes(state);
    const want = cards ? state + "|" + S.key + "|" + (state === "unreadable" ? S.payload.unreadable : "") : "dash";
    if (cards) {
      if (v.shown !== want) {
        clear(v.body);
        v.body.appendChild(stateCard(state));
        v.shown = want;
      }
      return;
    }
    if (!v.dash) v.dash = buildDash();
    if (v.shown !== "dash") {
      clear(v.body);
      for (const node of v.dash.nodes) v.body.appendChild(node);
      v.shown = "dash";
    }
    fillDash(v.dash);
  }

  // ---------------------------------------------------------------- paint

  function paint() {
    if (!view || !S.ctx) return;
    const state = stateOf();
    view.root.setAttribute("data-live", state);
    drawControl(state);
    drawHead(state);
    drawBody(state);
    S.flash = false;
    S.blink = false;
    syncTick(state);
  }

  // The one-second clock runs only while the page is active, the tab is in view and the state is live or idle.
  // The state is never live or idle while paused, lost or waiting, so those stop it too. A tick only paints.
  function syncTick(state) {
    const want = S.active && env.isVisible() && (state === "live" || state === "idle");
    if (want && tickId === null) tickId = env.startTick(paint);
    else if (!want && tickId !== null) { env.stopTick(tickId); tickId = null; }
  }

  function onVisibility() {
    poller.visibilityChanged();
    if (env.isVisible()) paint(); // coming back repaints at once, so the age does not wait for the next tick
    else syncTick(stateOf());
  }

  // ---------------------------------------------------------------- answers

  function announce() {
    const shown = session();
    if (!view || !shown || !S.serverTime) return;
    const at = env.now();
    if (S.announcedAt !== null && at - S.announcedAt < ANNOUNCE_MS) return;
    S.announcedAt = at;
    const totals = shown.totals || {};
    view.sr.textContent = t("live_sr_update", {
      time: fmtClock(S.serverTime), tokens: fmtTokens(num(totals.tokens)), cost: fmtCost(totals.cost, totals.unpriced_requests),
    });
  }

  function onAnswer({ data, unchanged }) {
    if (data.project !== undefined && data.project !== S.key) return; // an answer for the project the page left
    const at = dateOf(data.server_time);
    if (at) { S.serverTime = at; S.receivedAt = env.now(); }
    if (unchanged) {
      paint();
      return;
    }
    const before = session();
    S.prevIds = new Set(before ? list(before.requests).map((r) => r.id) : []);
    S.payload = data;
    if (data.session_gone === true && session()) S.gone = true;
    if (!session()) S.gone = false;
    S.flash = !S.quiet && data.session_gone !== true;
    // The age blinks only when this answer brings a newer newest request than the one before.
    const newest = session() ? list(session().requests)[0] : null;
    S.blink = S.flash && Boolean(newest) && !S.prevIds.has(newest.id);
    S.quiet = false;
    paint();
    announce();
  }

  // ---------------------------------------------------------------- the page module's calls

  function stopListening() {
    if (unlisten) { unlisten(); unlisten = null; }
  }

  function resetFor(key) {
    S.key = key;
    S.payload = null;
    S.serverTime = null;
    S.receivedAt = null;
    S.lastNow = null;
    S.prevIds = new Set();
    S.paused = false;
    S.gone = false;
    S.mode = "ok";
    S.flash = false;
    S.blink = false;
    if (view) { view.filled = undefined; if (view.dash) view.shown = ""; }
    S.quiet = true;
    poller.reset(S.picks.get(key) || null);
    poller.setPaused(false);
  }

  return {
    render(root, ctx) {
      S.ctx = ctx;
      if (!view || view.root !== root) buildView(root);
      paint();
    },
    setActive(on, ctx) {
      if (ctx) S.ctx = ctx;
      if (!on) {
        S.active = false;
        poller.setActive(false);
        stopListening();
        syncTick("");
        return;
      }
      const key = S.ctx.project.key;
      // All projects never asks the server, so the poller stops before the reset that would ask at once.
      if (key === ALL_KEY) poller.setActive(false);
      if (key !== S.key) resetFor(key);
      S.active = true;
      if (key === ALL_KEY) {
        poller.setActive(false);
        stopListening();
      } else {
        if (!unlisten) unlisten = env.listenVisibility(onVisibility);
        poller.setActive(true);
      }
      paint();
    },
    // For checks: what the page and the poller hold.
    peek: () => ({ state: stateOf(), payload: S.payload, mode: S.mode, paused: S.paused, session: poller.session(), etag: poller.etag(), busy: poller.busy() }),
  };
}

const live = createLive({
  setTimer: (fn, wait) => setTimeout(fn, wait),
  clearTimer: (id) => clearTimeout(id),
  startTick: (fn) => setInterval(fn, 1000),
  stopTick: (id) => clearInterval(id),
  now: () => Date.now(),
  isVisible: () => document.visibilityState !== "hidden",
  listenVisibility: (fn) => {
    document.addEventListener("visibilitychange", fn);
    return () => document.removeEventListener("visibilitychange", fn);
  },
});

export function render(root, ctx) {
  live.render(root, ctx);
}

export function setActive(on, ctx) {
  live.setActive(on, ctx);
}
